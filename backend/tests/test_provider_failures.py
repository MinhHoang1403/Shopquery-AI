"""Transport/response failures through pinned SDKs, with no external requests."""

from unittest.mock import Mock

import httpx
import httpx2
import pytest

from app.core.diagnostics import diagnostic_request
from app.core.errors import ModelResponseError, ProviderError
from app.routing.router import QueryRouter, RouteDecision
from app.routing.service import DatasetChatService
from tests.test_gemini import _build_harness
from tests.test_providers import harness


@pytest.mark.parametrize("provider", ["gemini", "knowledge"])
@pytest.mark.parametrize(
    "status,category",
    [
        (401, "authentication_failed"),
        (402, "payment_required"),
        (403, "permission_denied"),
        (404, "resource_not_found"),
        (408, "timeout"),
        (504, "timeout"),
        (429, "quota_or_rate_limit"),
        (400, "request_rejected"),
        (500, "transient_unavailable"),
        (502, "transient_unavailable"),
        (503, "transient_unavailable"),
    ],
)
def test_provider_http_boundary_is_specific_safe_and_stops_before_execution(
    monkeypatch, caplog, provider, status, category
):
    payload = {"error": {"code": status, "message": "PRIVATE upstream payload"}}
    if provider == "gemini":
        run = _build_harness(monkeypatch, [httpx.Response(status, json=payload)], attempts=1)
        gateway, calls = run.gateway, run.calls
    else:
        gateway, calls = harness(monkeypatch, [httpx2.Response(status, json=payload)])
    sql = Mock()
    service = DatasetChatService(QueryRouter(gateway), sql, None, None)
    try:
        with diagnostic_request() as trace, pytest.raises(ModelResponseError) as caught:
            service.chat("PRIVATE user question")
    finally:
        gateway.close()
    context = caught.value.error_context
    assert context.provider == provider
    assert context.http_status == status
    assert context.error_category == category
    assert context.phase == "request" and context.origin_stage == "routing"
    assert context.attempt == 1 and len(calls) == 1
    assert trace.facts["generation_calls"] == 1
    assert not trace.facts["execution_reached"]
    sql.run.assert_not_called()
    assert "PRIVATE" not in context.model_dump_json() + str(trace.events) + caplog.text


@pytest.mark.parametrize("operation", ["structured", "text"])
@pytest.mark.parametrize("kind", ["prompt_block", "candidate_block", "empty"])
def test_gemini_block_or_empty_is_not_misclassified_as_invalid_json(monkeypatch, operation, kind):
    payload = (
        {"promptFeedback": {"blockReason": "SAFETY"}}
        if kind == "prompt_block"
        else {"candidates": [{"finishReason": "PROHIBITED_CONTENT", "content": {"parts": []}}]}
        if kind == "candidate_block"
        else {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": " "}]}}]}
    )
    run = _build_harness(monkeypatch, [httpx.Response(200, json=payload)], attempts=1)
    try:
        with diagnostic_request() as trace, pytest.raises(ProviderError) as caught:
            if operation == "structured":
                run.gateway.generate_structured("PRIVATE", RouteDecision)
            else:
                run.gateway.generate_text("PRIVATE")
    finally:
        run.close()
    assert caught.value.error_context.error_category == (
        "invalid_response" if kind == "empty" else "model_refusal"
    )
    assert caught.value.error_context.phase == "response"
    assert len(run.calls) == 1 and trace.facts["generation_calls"] == 1
    assert "total_tokens" not in trace.facts


def test_gemini_nonempty_invalid_json_still_has_decode_boundary(monkeypatch):
    payload = {"candidates": [{"content": {"parts": [{"text": "PRIVATE bad json"}]}}]}
    run = _build_harness(monkeypatch, [httpx.Response(200, json=payload)], attempts=1)
    try:
        with pytest.raises(ModelResponseError) as caught:
            run.gateway.generate_structured("PRIVATE", RouteDecision)
    finally:
        run.close()
    assert caught.value.error_context.error_category == "invalid_json"
    assert caught.value.error_context.phase == "json_decode"
    assert len(run.calls) == 1


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404])
@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_nontransient_status_never_retries_even_when_sdk_policy_allows_three_attempts(
    monkeypatch, provider, status
):
    payload = {"error": {"code": status, "message": "PRIVATE"}}
    if provider == "knowledge":
        gateway, calls = harness(
            monkeypatch, [httpx2.Response(status, json=payload)], inetcloud_retry_attempts=3
        )
    else:
        run = _build_harness(monkeypatch, [httpx.Response(status, json=payload)], attempts=3)
        gateway, calls = run.gateway, run.calls
    try:
        with pytest.raises(ProviderError):
            gateway.generate_text("PRIVATE")
    finally:
        gateway.close()
    assert len(calls) == 1


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize(
    "kind,category", [("timeout", "timeout"), ("connect", "connection_failure")]
)
def test_transport_exception_has_no_hidden_attempt_or_sensitive_detail(
    monkeypatch, provider, kind, category
):
    if provider == "knowledge":
        failure = (
            httpx2.ReadTimeout("PRIVATE") if kind == "timeout" else httpx2.ConnectError("PRIVATE")
        )
        gateway, calls = harness(monkeypatch, [failure])
    else:
        run = _build_harness(monkeypatch, [], attempts=1)
        failure = (
            httpx.ReadTimeout("PRIVATE") if kind == "timeout" else httpx.ConnectError("PRIVATE")
        )
        calls = []

        def action(**kwargs):
            calls.append(kwargs)
            raise failure

        monkeypatch.setattr(run.gateway._client.models, "generate_content", action)
        gateway = run.gateway
    try:
        with pytest.raises(ProviderError) as caught:
            gateway.generate_text("PRIVATE")
    finally:
        gateway.close()
    assert caught.value.error_context.error_category == category
    assert caught.value.error_context.phase == "request"
    assert len(calls) == 1
    assert "PRIVATE" not in caught.value.error_context.model_dump_json()


def test_missing_credentials_and_unknown_registry_model_do_not_dispatch(monkeypatch):
    from app.ai.gemini import GeminiGateway
    from app.ai.inetcloud import InetCloudGateway
    from app.ai.providers import build_generation_gateway
    from app.core.config import Settings
    from app.core.errors import ConfigurationError

    client = Mock(side_effect=AssertionError("No client without configuration"))
    monkeypatch.setattr("app.ai.gemini.genai.Client", client)
    monkeypatch.setattr("app.ai.inetcloud.ChatOpenAI", client)
    settings = Settings(_env_file=None, gemini_api_key=None, inetcloud_base_url=None)
    for action in (
        lambda: GeminiGateway(settings),
        lambda: InetCloudGateway(settings),
        lambda: build_generation_gateway(settings, "unknown"),
    ):
        with pytest.raises(ConfigurationError):
            action()
    client.assert_not_called()
