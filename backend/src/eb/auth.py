"""Caller identity. Dev mode: a static user. Production: OIDC bearer tokens (to be wired)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Depends, Header, HTTPException

from eb.config import get_settings
from eb.db import connection


@dataclass
class Principal:
    id: UUID
    email: str
    display_name: str
    group_ids: list[UUID] = field(default_factory=list)
    is_admin: bool = False


def ensure_user(email: str, display_name: str = "", external_id: str | None = None) -> Principal:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO users (email, display_name, external_id) VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name
            RETURNING id, email, display_name
            """,
            (email, display_name or email.split("@")[0], external_id),
        ).fetchone()
        everyone = conn.execute("SELECT id FROM groups WHERE name='everyone'").fetchone()["id"]
        conn.execute(
            "INSERT INTO user_groups (user_id, group_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (row["id"], everyone),
        )
        groups = conn.execute(
            "SELECT g.id, g.name FROM groups g JOIN user_groups ug ON ug.group_id = g.id "
            "WHERE ug.user_id = %s",
            (row["id"],),
        ).fetchall()
    return Principal(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        group_ids=[g["id"] for g in groups],
        is_admin=any(g["name"] == "admins" for g in groups),
    )


def current_user(authorization: str | None = Header(default=None)) -> Principal:
    s = get_settings()
    if s.auth_mode == "dev":
        return ensure_user(s.dev_user_email, "Dev User")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    # OIDC validation is wired in a later phase (ADR pending); fail closed until then.
    raise HTTPException(501, "OIDC auth not configured")


CurrentUser = Depends(current_user)
