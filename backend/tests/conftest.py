"""Test fixtures. Uses a dedicated test database so dev data is never touched."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

TEST_DB = os.environ.get("EB_TEST_DB_NAME", "engineering_brain_test")
ADMIN_URL = os.environ.get("EB_TEST_ADMIN_URL", "postgresql://eb:eb@localhost:5432/postgres")
TEST_URL = os.environ.get("EB_TEST_DATABASE_URL",
                          f"postgresql://eb:eb@localhost:5432/{TEST_DB}")


def _recreate_db() -> None:
    import psycopg

    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (TEST_DB,)
        )
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
        conn.execute(f"CREATE DATABASE {TEST_DB}")


@pytest.fixture(scope="session", autouse=True)
def _env(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    wiki = tmp_path_factory.mktemp("wiki")
    os.environ.update(
        {
            "EB_DATABASE_URL": TEST_URL,
            "EB_DATA_DIR": str(data),
            "EB_WIKI_DIR": str(wiki),
            "EB_LLM_PROVIDER": "fake",
            "EB_EMBEDDING_PROVIDER": "hash",
            "EB_AUTH_MODE": "dev",
            "EB_PARSER": "pypdf",
        }
    )
    subprocess.run(["git", "init", "-q", str(wiki)], check=True)
    subprocess.run(["git", "-C", str(wiki), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(wiki), "config", "user.name", "test"], check=True)
    _recreate_db()
    from eb.config import get_settings
    from eb.db import close_pool, migrate

    get_settings.cache_clear()
    migrate()
    yield
    close_pool()


@pytest.fixture
def db():
    from eb.db import connection

    yield connection
    # Truncate mutable tables between tests, keeping groups.
    with connection() as conn:
        conn.execute(
            "TRUNCATE documents, jobs, wiki_pages, wiki_proposals, requirement_sets, "
            "conversations CASCADE"
        )


@pytest.fixture
def user(db):
    from eb.auth import ensure_user

    return ensure_user("tester@example.com", "Tester")


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from eb.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def fake_llm():
    from eb.llm import FakeLLM, set_llm

    llm = FakeLLM()
    set_llm(llm)
    yield llm
    set_llm(None)


SAMPLE_SPEC = """# PS-100 Centrifugal Pump Specification

## 1 Scope

This specification covers horizontal centrifugal pumps for cooling water service.

## 4 Design Requirements

4.1 The pump shall deliver a rated flow of 250 m3/h at a differential head of 45 m.

4.2 The design pressure of the pump casing shall be not less than 16 bar(g).

4.3 Motor shall be rated for 400 V, 50 Hz, 3-phase supply with a service factor of 1.15.

4.4 Casing material shall be ASTM A216 WCB carbon steel.

## 5 Testing

5.1 A performance test per ISO 9906 Grade 2B shall be witnessed by the purchaser.

| Parameter | Value | Unit |
| --- | --- | --- |
| Rated flow | 250 | m3/h |
| Differential head | 45 | m |
| Design pressure | 16 | bar(g) |
"""

SAMPLE_DATASHEET = """# Supplier Data Sheet: Model CX-250 Pump

Rated capacity: 250 m3/h at 48 m head.
Maximum allowable working pressure of casing: 20 bar(g) at 38 degC.
Motor: 400 V, 50 Hz, three phase, service factor 1.0.
Casing material: ductile iron ASTM A395.
Performance test: ISO 9906 Grade 2B, witnessed on request.
"""


@pytest.fixture
def sample_spec() -> str:
    return SAMPLE_SPEC


@pytest.fixture
def sample_datasheet() -> str:
    return SAMPLE_DATASHEET


@pytest.fixture
def tmp_file():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)
