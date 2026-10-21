"""Compliance job handlers (registered by eb.jobs.handlers)."""

from __future__ import annotations

from uuid import UUID

from eb.compliance.check import run_check
from eb.jobs import job


@job("compliance.run")
def handle_run(payload: dict) -> None:
    run_check(UUID(payload["run_id"]))
