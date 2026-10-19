"""Fail closed before test fixtures can mutate a PostgreSQL database."""

import os
import re
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url


def require_test_database(database_url: str) -> None:
    explicit = os.getenv("SHOPQUERY_TEST_DATABASE_URL")
    if not explicit:
        raise RuntimeError(
            "SHOPQUERY_TEST_DATABASE_URL must explicitly identify the isolated test DB"
        )
    target = make_url(database_url)
    if target != make_url(explicit) or not re.fullmatch(
        r"shopquery_(?:ci|test_[a-z0-9_]+)", target.database or ""
    ):
        raise RuntimeError("Refusing tests against a non-isolated database")
    root = Path(__file__).resolve().parents[3]
    for file in (root / ".env", root / "backend" / ".env"):
        primary = dotenv_values(file).get("DATABASE_SETUP_URL") if file.exists() else None
        if primary:
            app = make_url(primary)
            if (target.host, target.port, target.database) == (app.host, app.port, app.database):
                raise RuntimeError("Refusing tests against the configured application database")
