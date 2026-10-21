"""Database access: a psycopg connection pool and a tiny SQL migration runner."""

from __future__ import annotations

import atexit
import re
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from eb.config import get_settings

_pool: ConnectionPool | None = None


def _configure(conn: psycopg.Connection) -> None:
    # The vector type does not exist before the first migration runs; tolerate that and
    # let migrate() reset the pool so later connections register the adapter.
    try:
        register_vector(conn)
    except psycopg.ProgrammingError:
        conn.rollback()


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = ConnectionPool(
            s.database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row, "autocommit": False},
            configure=_configure,
            open=True,
        )
        atexit.register(close_pool)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """A pooled connection with an open transaction; commits on success, rolls back on error."""
    pool = get_pool()
    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


_MIGRATION_RE = re.compile(r"^(\d{4})_.*\.sql$")


def list_migrations() -> list[tuple[str, str]]:
    files = []
    for entry in resources.files("eb.migrations").iterdir():
        if _MIGRATION_RE.match(entry.name):
            files.append((entry.name, entry.read_text(encoding="utf-8")))
    return sorted(files)


def migrate() -> list[str]:
    """Apply unapplied migrations in order. Idempotent. Returns names applied."""
    applied: list[str] = []
    with connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
        for name, sql in list_migrations():
            if name in done:
                continue
            conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (name,))
            applied.append(name)
    if applied:
        close_pool()  # new connections pick up types created by the migrations
    return applied
