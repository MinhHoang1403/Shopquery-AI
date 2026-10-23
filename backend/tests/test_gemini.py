"""Gemini SDK retry behavior without external API calls."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from google import genai
from google.genai import types

from app.ai.gemini import TRANSIENT_HTTP_STATUS_CODES, GeminiGateway
from app.core.config import Settings
from app.core.errors import ModelResponseError
from app.routing.router import QueryRouter, RouteLabel


@dataclass
class GatewayHarness:
    gateway: GeminiGateway
    calls: list[httpx.Request]
    http_options: types.HttpOptions

    def close(self) -> None:
        self.gateway._client.close()


def _success_response() -> httpx.Response:
    decision = json.dumps(
        {"route": "SQL", "reason": "Requires commerce rows"}
    )
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": decision}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ]
        },
    )


def _error_response(status_code: int) -> httpx.Response:
    status = "UNAVAILABLE" if status_code == 503 else "UNAUTHENTICATED"
    return httpx.Response(
        status_code,
        json={
            "error": {
                "code": status_code,
                "message": "controlled test error",
                "status": status,
            }
        },
    )


def _build_harness(
    monkeypatch: pytest.MonkeyPatch, responses: list[httpx.Response]
) -> GatewayHarness:
    real_client = genai.Client
    queued: Iterator[httpx.Response] = iter(responses)
    calls: list[httpx.Request] = []
    captured_options: list[types.HttpOptions] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return next(queued)

    def client_factory(**kwargs: Any) -> genai.Client:
        http_options = kwargs["http_options"]
        captured_options.append(http_options)
        http_options.client_args = {"transport": httpx.MockTransport(handler)}
        client = real_client(**kwargs)
        client._api_client._retry.sleep = lambda _: None
        return client

    monkeypatch.setattr("app.ai.gemini.genai.Client", client_factory)
    settings = Settings(
        gemini_api_key="test-key",
        gemini_generation_model="test-model",
        gemini_request_timeout_ms=1_000,
        gemini_retry_attempts=3,
    )
    gateway = GeminiGateway(settings)
    return GatewayHarness(gateway, calls, captured_options[0])


def test_router_retries_transient_503_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _build_harness(
        monkeypatch,
        [_error_response(503), _success_response()],
    )
    try:
        decision = QueryRouter(harness.gateway).route("Top 5 sản phẩm bán chạy?")
    finally:
        harness.close()

    assert decision.route == RouteLabel.SQL
    assert len(harness.calls) == 2
    assert harness.http_options.timeout == 1_000
    assert harness.http_options.retry_options is not None
    assert harness.http_options.retry_options.attempts == 3
    assert (
        harness.http_options.retry_options.http_status_codes
        == TRANSIENT_HTTP_STATUS_CODES
    )


def test_router_reports_503_after_retry_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _build_harness(
        monkeypatch,
        [_error_response(503), _error_response(503), _error_response(503)],
    )
    try:
        with pytest.raises(ModelResponseError, match="after retry attempts"):
            QueryRouter(harness.gateway).route("Top 5 sản phẩm bán chạy?")
    finally:
        harness.close()

    assert len(harness.calls) == 3


def test_router_does_not_retry_authentication_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _build_harness(monkeypatch, [_error_response(401)])
    try:
        with pytest.raises(ModelResponseError, match="verify API configuration"):
            QueryRouter(harness.gateway).route("Top 5 sản phẩm bán chạy?")
    finally:
        harness.close()

    assert len(harness.calls) == 1


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (400, "request_rejected"),
        (401, "authentication_or_permission"),
        (403, "authentication_or_permission"),
        (429, "quota_or_rate_limit"),
        (503, "transient_unavailable"),
    ],
)
def test_error_diagnostics_exclude_provider_payloads(monkeypatch, caplog, status, category):
    response = httpx.Response(
        status,
        json={"error": {"code": status, "message": "private-upstream-payload"}},
    )
    harness = _build_harness(monkeypatch, [response] * 3)
    try:
        with pytest.raises(ModelResponseError):
            QueryRouter(harness.gateway).route("private-question")
    finally:
        harness.close()
    records = [record for record in caplog.records if record.name == "app.ai.gemini"]
    assert len(records) == 1
    assert records[0].getMessage() == (
        "provider_error provider=gemini operation=generation "
        f"http_status={status} category={category}"
    )
    assert records[0].exc_info is None
    assert "private-upstream-payload" not in records[0].getMessage()
    assert "private-question" not in records[0].getMessage()
    assert "test-key" not in records[0].getMessage()


@pytest.mark.parametrize(
    ("message", "category"),
    [
        ("private-payload: schema rejected", "schema_rejected"),
        ("private-payload: schema constraint has too many states", "schema_complexity"),
    ],
)
def test_schema_error_category_does_not_log_the_message(monkeypatch, caplog, message, category):
    harness = _build_harness(
        monkeypatch, [httpx.Response(400, json={"error": {"code": 400, "message": message}})]
    )
    try:
        with pytest.raises(ModelResponseError):
            QueryRouter(harness.gateway).route("private-question")
    finally:
        harness.close()
    records = [record for record in caplog.records if record.name == "app.ai.gemini"]
    assert len(records) == 1
    assert f"category={category}" in records[0].getMessage()
    assert "private-payload" not in records[0].getMessage()
