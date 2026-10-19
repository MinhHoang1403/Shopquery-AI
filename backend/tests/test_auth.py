"""Offline protocol, guest access and test-environment safety checks."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import RSAKey
from starlette.requests import Request

from app.auth.oidc import google_client, verified_identity
from app.core.config import Settings
from app.database.test_safety import require_test_database
from app.main import app


@pytest.fixture(scope="module")
def signing_key():
    return RSAKey.generate_key(2048, parameters={"kid": "offline-fixture"})


def oidc_settings():
    return Settings(
        _env_file=None,
        google_client_id="fixture-client",
        google_client_secret="fixture-secret",
        auth_invited_emails=["a@example.invalid"],
    )


@pytest.mark.parametrize("endpoint", ["login", "callback"])
def test_login_budget_uses_verified_proxy_client_ip(monkeypatch, endpoint):
    from app.auth import routes

    settings = oidc_settings()
    settings.trusted_proxy_hosts = ["web"]
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    monkeypatch.setattr(routes, "google_client", lambda config: Mock())
    monkeypatch.setattr("socket.getaddrinfo", lambda *args: [(2, 1, 6, "", ("172.20.0.4", 0))])
    control = Mock()
    control.login.side_effect = HTTPException(429, "Synthetic rate check")
    monkeypatch.setattr(routes, "resource_control", lambda: control)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/" + endpoint,
            "client": ("172.20.0.4", 1234),
            "query_string": b"state=test&code=test" if endpoint == "callback" else b"",
            "headers": [(b"x-forwarded-for", b"198.51.100.7"), (b"cookie", b"shopquery_oidc=test")],
        }
    )
    with pytest.raises(HTTPException):
        asyncio.run(getattr(routes, endpoint)(request))
    control.login.assert_called_once_with("198.51.100.7")


@pytest.mark.parametrize(
    "mutation", [None, "issuer", "audience", "expiry", "nonce", "email", "invite", "signature"]
)
def test_oidc_validates_real_signed_claims(signing_key, mutation):
    settings = oidc_settings()
    client = google_client(settings)
    claims = {
        "iss": "https://accounts.google.com",
        "sub": "fixture-subject",
        "aud": "fixture-client",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "nonce": "expected-nonce",
        "email": "a@example.invalid",
        "email_verified": True,
    }
    mutations = {
        "issuer": ("iss", "https://attacker.invalid"),
        "audience": ("aud", "other"),
        "expiry": ("exp", int(time.time()) - 600),
        "nonce": ("nonce", "wrong"),
        "email": ("email_verified", False),
        "invite": ("email", "b@example.invalid"),
    }
    if mutation in mutations:
        name, value = mutations[mutation]
        claims[name] = value
    token = jwt.encode({"alg": "RS256", "kid": "offline-fixture"}, claims, signing_key)
    if mutation == "signature":
        token = token[:-10] + "aaaaaaaaaa"
    client.server_metadata.update(
        {
            "_loaded_at": time.time(),
            "issuer": "https://accounts.google.com",
            "jwks": {"keys": [signing_key.as_dict(private=False)]},
            "id_token_signing_alg_values_supported": ["RS256"],
        }
    )
    client.fetch_access_token = AsyncMock(return_value={"id_token": token})
    call = verified_identity(client, "code", "expected-nonce", "verifier", settings)
    if mutation is None:
        result = asyncio.run(call)
        assert result[:2] == ("fixture-subject", "a@example.invalid")
    else:
        with pytest.raises((JoseError, HTTPException)):
            asyncio.run(call)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/models"),
        ("POST", "/api/chat"),
        ("GET", "/api/conversations"),
        ("POST", "/api/conversations"),
        ("GET", "/api/datasets"),
        ("POST", "/api/datasets"),
        ("GET", "/api/datasets/1"),
        ("DELETE", "/api/datasets/1"),
        ("GET", "/api/datasets/1/preview"),
        ("POST", "/api/datasets/preview"),
        ("POST", "/api/datasets/import"),
        ("GET", "/api/datasets/1/tables"),
        ("POST", "/api/datasets/1/tables/preview"),
        ("POST", "/api/datasets/1/tables/import"),
        ("DELETE", "/api/datasets/1/tables/1"),
        ("GET", "/api/datasets/1/documents"),
        ("POST", "/api/datasets/1/documents"),
        ("GET", "/api/datasets/1/documents/1"),
        ("DELETE", "/api/datasets/1/documents/1"),
        ("GET", "/api/auth/me"),
        ("POST", "/api/auth/logout"),
        *[
            (method, "/api/conversations/00000000-0000-4000-8000-000000000001" + suffix)
            for method, suffix in [
                ("GET", ""),
                ("PATCH", ""),
                ("DELETE", ""),
                ("POST", "/messages"),
            ]
        ],
    ],
)
def test_every_private_operation_rejects_guests(method, path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unauthenticated requests must not access database or providers")

    monkeypatch.setattr("app.auth.dependencies.auth_repository", forbidden)
    for name in (
        "build_chat_service",
        "build_dataset_repository",
        "build_document_repository",
        "build_conversation_repository",
        "GeminiGateway",
    ):
        monkeypatch.setattr(f"app.api.routes.{name}", forbidden)
    response = TestClient(app).request(method, path, json={"message": "Q"})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("origin", ["http://example.invalid", "http://localhost:8080", ""])
def test_csrf_rejects_other_origins(contract_session, origin):
    from tests.auth_helpers import TestClient as SignedClient

    client = SignedClient(app)
    response = client.post("/api/chat", headers={"Origin": origin}, json={"message": "Q"})
    assert response.status_code == 403


@pytest.mark.parametrize("token", ["", "invalid"])
def test_csrf_rejects_missing_or_bad_token(contract_session, token):
    from tests.auth_helpers import TestClient as SignedClient

    response = SignedClient(app).post(
        "/api/chat", headers={"X-CSRF-Token": token}, json={"message": "Q"}
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@localhost/shopquery",
        "postgresql://u:p@localhost/production",
        "postgresql://u:p@localhost/shopquery_test_other",
    ],
)
def test_database_guard_rejects_ambiguous_or_mismatched_targets(monkeypatch, url):
    monkeypatch.setenv("SHOPQUERY_TEST_DATABASE_URL", "postgresql://u:p@localhost/shopquery_ci")
    with pytest.raises(RuntimeError):
        require_test_database(url)


def test_database_guard_requires_explicit_target(monkeypatch):
    monkeypatch.delenv("SHOPQUERY_TEST_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        require_test_database("postgresql://u:p@localhost/shopquery_ci")


def test_production_rejects_insecure_origin_and_uses_host_cookie():
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_environment="production", app_origin="http://127.0.0.1:8080")
    settings = Settings(
        _env_file=None, app_environment="production", app_origin="https://app.invalid"
    )
    assert settings.secure_cookies and settings.session_cookie_name.startswith("__Host-")


def test_login_redirect_is_not_client_controlled():
    assert TestClient(app).get("/api/auth/login?next=https://attacker.invalid").status_code == 400


def test_missing_google_configuration_is_explicit():
    with pytest.raises(HTTPException) as error:
        google_client(Settings(_env_file=None))
    assert error.value.status_code == 503


def test_authlib_builds_pkce_nonce_and_fixed_redirect_without_network():
    settings = oidc_settings()
    client = google_client(settings)
    client.server_metadata.update(
        {
            "_loaded_at": time.time(),
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        }
    )
    result = asyncio.run(
        client.create_authorization_url(
            redirect_uri=settings.oidc_callback_url,
            state="state",
            nonce="nonce",
            code_verifier="v" * 43,
        )
    )
    query = parse_qs(urlsplit(result["url"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == ["state"] and query["nonce"] == ["nonce"]
    assert query["redirect_uri"] == [settings.oidc_callback_url]
    assert query["response_type"] == ["code"]


def test_provider_permission_blocks_generation_before_gateway(contract_session, monkeypatch):
    from tests.auth_helpers import TestClient as SignedClient

    monkeypatch.setattr("app.auth.limits.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(
        "app.api.routes.build_chat_service", lambda settings: pytest.fail("Provider initialized")
    )
    assert SignedClient(app).post("/api/chat", json={"message": "Q"}).status_code == 403
