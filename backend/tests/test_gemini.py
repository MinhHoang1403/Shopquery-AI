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
