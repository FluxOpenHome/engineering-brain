"""Git-backed markdown store: the canonical wiki (architecture P3, ADR-0002).

Pages are `<slug>.md` under `settings.wiki_dir` with YAML frontmatter. Every write is a git
commit attributed to the acting user. Postgres (`wiki_pages`) is a derived index over this
store; `service.sync_from_disk` rebuilds it.
"""

from __future__ import annotations

import datetime as dt
import difflib
import fcntl
import hashlib
import re
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter
import structlog

from eb.config import get_settings

log = structlog.get_logger(__name__)

STATUSES = ("proposed", "published", "stale", "archived")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-/]*$")
SLUG_MAX = 200

AGENT_AUTHOR = ("Engineering Brain agent", "agent@engineering-brain.local")


class SlugError(ValueError):
    pass


@dataclass
class Page:
    slug: str
    frontmatter: dict[str, Any]
    body: str
    path: Path = field(repr=False, default=Path())

    @property
    def title(self) -> str:
        return str(self.frontmatter.get("title") or self.slug.rsplit("/", 1)[-1])

    @property
    def status(self) -> str:
        return str(self.frontmatter.get("status") or "published")


def validate_slug(slug: str) -> str:
    """Return the slug if valid, else raise SlugError. Slugs are lowercase kebab paths."""
    if not isinstance(slug, str) or not slug or len(slug) > SLUG_MAX:
        raise SlugError("slug must be 1-200 characters")
    if ".." in slug or "//" in slug or slug.endswith("/") or not SLUG_RE.match(slug):
        raise SlugError("slug must match ^[a-z0-9][a-z0-9-/]*$ with no '..' or empty segments")
    return slug


def content_hash(text: str) -> str:
    """sha256 of the body, ignoring leading/trailing whitespace so that the in-memory body and
    the normalised file on disk (`render` strips and adds one newline) hash identically."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------ repo plumbing


def _git(root: Path, *args: str, check: bool = True, author: tuple[str, str] | None = None
         ) -> subprocess.CompletedProcess[str]:
    cmd = ["git", "-C", str(root)]
    if author:
        cmd += ["-c", f"user.name={author[0]}", "-c", f"user.email={author[1]}"]
    cmd += list(args)
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def wiki_root() -> Path:
    """The wiki directory, created and `git init`-ed on first use."""
    root = Path(get_settings().wiki_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        _git(root, "init", "-q")
        log.info("wiki.git_init", root=str(root))
    return root


@contextmanager
def _locked(root: Path) -> Iterator[None]:
    """Serialise writers across processes (API workers, CLI) with an advisory file lock."""
    lock_path = root / ".git" / "eb-wiki.lock"
    with open(lock_path, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def page_path(slug: str, root: Path | None = None) -> Path:
    root = root or wiki_root()
    p = (root / f"{validate_slug(slug)}.md").resolve()
    if root not in p.parents:
        raise SlugError("slug escapes the wiki root")
    return p


def _relpath(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def head_sha(root: Path | None = None) -> str | None:
    root = root or wiki_root()
    r = _git(root, "rev-parse", "--verify", "-q", "HEAD", check=False)
    return r.stdout.strip() or None


# ------------------------------------------------------------------------------ frontmatter


def _normalise(meta: dict[str, Any]) -> dict[str, Any]:
    """YAML gives dates/datetimes back as objects; the API wants plain JSON values."""
    out: dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, dt.datetime | dt.date):
            v = v.isoformat()
        out[k] = v
    return out


def default_frontmatter(title: str, **overrides: Any) -> dict[str, Any]:
    fm: dict[str, Any] = {
        "title": title,
        "status": "published",
        "discipline": [],
        "tags": [],
        "sources": [],
        "generated_by": "human",
        "reviewed_by": None,
        "human_edited": False,
        "updated": dt.date.today().isoformat(),
    }
    fm.update({k: v for k, v in overrides.items() if v is not None or k in fm})
    return fm


def render(frontmatter_dict: dict[str, Any], body: str) -> str:
    post = frontmatter.Post(body.strip() + "\n", **frontmatter_dict)
    return frontmatter.dumps(post) + "\n"


def parse(text: str) -> tuple[dict[str, Any], str]:
    post = frontmatter.loads(text)
    return _normalise(dict(post.metadata)), post.content


# ------------------------------------------------------------------------------ public API


def read_page(slug: str) -> Page | None:
    root = wiki_root()
    p = page_path(slug, root)
    if not p.is_file():
        return None
    meta, body = parse(p.read_text(encoding="utf-8"))
    return Page(slug=slug, frontmatter=meta, body=body, path=p)


def write_page(slug: str, frontmatter_dict: dict[str, Any], body: str, *, message: str,
               author: tuple[str, str]) -> str:
    """Write `<slug>.md` and commit it. Returns the commit sha (HEAD if nothing changed)."""
    root = wiki_root()
    p = page_path(slug, root)
    text = render(frontmatter_dict, body)
    with _locked(root):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        rel = _relpath(root, p)
        _git(root, "add", "--", rel)
        staged = _git(root, "diff", "--cached", "--quiet", "--", rel, check=False)
        if staged.returncode == 0:
            sha = head_sha(root)
            log.info("wiki.write.unchanged", slug=slug, sha=sha)
            return sha or ""
        _git(root, "commit", "-q", "-m", message, "--", rel, author=author)
        sha = head_sha(root) or ""
    log.info("wiki.write", slug=slug, sha=sha, author=author[1])
    return sha


def delete_page(slug: str, *, message: str, author: tuple[str, str]) -> str | None:
    """`git rm` the page and commit. Returns the commit sha, or None if the file did not exist.

    Prefer `service.archive_page`, which keeps the file with status=archived; this is the hard
    delete used to purge pages that should never have existed.
    """
    root = wiki_root()
    p = page_path(slug, root)
    if not p.is_file():
        return None
    with _locked(root):
        rel = _relpath(root, p)
        tracked = _git(root, "ls-files", "--error-unmatch", "--", rel, check=False)
        if tracked.returncode == 0:
            _git(root, "rm", "-q", "--", rel)
            _git(root, "commit", "-q", "-m", message, "--", rel, author=author)
        else:
            p.unlink()
        sha = head_sha(root)
    log.info("wiki.delete", slug=slug, sha=sha)
    return sha


def list_pages() -> list[Page]:
    """Every page on disk whose path is a valid slug (README.md and hidden dirs are skipped)."""
    root = wiki_root()
    pages: list[Page] = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        slug = rel.with_suffix("").as_posix()
        try:
            validate_slug(slug)
        except SlugError:
            continue
        try:
            meta, body = parse(p.read_text(encoding="utf-8"))
        except Exception as e:  # malformed frontmatter must not take the whole sync down
            log.warning("wiki.list.unreadable", slug=slug, error=str(e))
            continue
        if not meta.get("title"):
            continue
        pages.append(Page(slug=slug, frontmatter=meta, body=body, path=p))
    return pages


def history(slug: str, limit: int = 50) -> list[dict[str, str]]:
    root = wiki_root()
    p = page_path(slug, root)
    r = _git(root, "log", f"--max-count={limit}", "--follow", "--format=%H%x1f%an%x1f%ae%x1f%aI%x1f%s",
             "--", _relpath(root, p), check=False)
    out: list[dict[str, str]] = []
    for line in r.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 5:
            continue
        sha, name, email, date, msg = parts
        out.append({"sha": sha, "author": name, "email": email, "date": date, "message": msg})
    return out


def diff(slug: str, old_text: str | None, new_text: str | None) -> str:
    a = (old_text or "").splitlines(keepends=True)
    b = (new_text or "").splitlines(keepends=True)
    fromfile = f"a/{slug}.md" if old_text is not None else "/dev/null"
    tofile = f"b/{slug}.md" if new_text is not None else "/dev/null"
    return "".join(difflib.unified_diff(a, b, fromfile=fromfile, tofile=tofile))
