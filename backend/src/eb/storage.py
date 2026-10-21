"""Object storage behind one small interface. Local filesystem now; S3-compatible later."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import BinaryIO, Protocol

from eb.config import get_settings


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes | BinaryIO) -> None: ...
    def get(self, key: str) -> bytes: ...
    def open(self, key: str) -> BinaryIO: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...


class LocalStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError(f"key escapes store root: {key!r}")
        return p

    def put(self, key: str, data: bytes | BinaryIO) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        with open(tmp, "wb") as f:
            if isinstance(data, bytes | bytearray):
                f.write(data)
            else:
                shutil.copyfileobj(data, f)
        tmp.replace(p)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def open(self, key: str) -> BinaryIO:
        return open(self._path(key), "rb")

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()


_store: ObjectStore | None = None


def get_store() -> ObjectStore:
    global _store
    if _store is None:
        _store = LocalStore(get_settings().data_dir / "objects")
    return _store


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def object_key(sha256: str, filename: str) -> str:
    """Content-addressed key: objects/ab/cd/<sha>/<filename>."""
    safe = Path(filename).name.replace(" ", "_")
    return f"{sha256[:2]}/{sha256[2:4]}/{sha256}/{safe}"
