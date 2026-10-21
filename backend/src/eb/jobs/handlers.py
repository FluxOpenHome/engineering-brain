"""Import every module that registers job handlers so the worker knows them."""

from eb.ingest import jobs as _ingest_jobs  # noqa: F401

try:  # optional modules register themselves when present
    from eb.wiki import jobs as _wiki_jobs  # noqa: F401
except ImportError:  # pragma: no cover
    pass
try:
    from eb.compliance import jobs as _compliance_jobs  # noqa: F401
except ImportError:  # pragma: no cover
    pass
