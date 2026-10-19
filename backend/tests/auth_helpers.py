"""Authenticated contract clients; the real cookie/CSRF dependency still runs."""

from contextlib import nullcontext
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient as FastApiTestClient

from app.auth.repository import Principal, csrf_token
from app.core.config import get_settings

TEST_OWNER = UUID("00000000-0000-4000-8000-000000000001")
TEST_TOKEN = "contract-session-token-not-a-real-secret-1234"


def TestClient(app):
    settings = get_settings()
    return FastApiTestClient(
        app,
        cookies={settings.session_cookie_name: TEST_TOKEN},
        headers={
            "Origin": settings.app_origin,
            "X-CSRF-Token": csrf_token(TEST_TOKEN),
        },
    )


@pytest.fixture
def contract_session(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "auth_invited_emails": ["contract@example.invalid"],
            "beta_provider_data_enabled": True,
        }
    )

    def authenticate(raw):
        if raw != TEST_TOKEN:
            raise HTTPException(401, "Invalid session")
        return Principal(
            TEST_OWNER, "contract@example.invalid", "Contract user", "hash", csrf_token(raw)
        )

    monkeypatch.setattr("app.auth.dependencies.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.auth.dependencies.auth_repository",
        lambda: SimpleNamespace(
            authenticate=authenticate,
        ),
    )
    monkeypatch.setattr("app.auth.limits.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.api.routes.resource_control",
        lambda: SimpleNamespace(
            work=lambda *args: nullcontext(),
            storage=lambda *args, **kwargs: None,
        ),
    )
