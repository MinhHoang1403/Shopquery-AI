"""Provider compatibility and whole-turn fallback without live service calls."""

import json
from types import SimpleNamespace

import httpx2
import pytest
from langchain_openai import ChatOpenAI

from app.ai.chat import ModelChatService
from app.ai.inetcloud import InetCloudGateway
from app.core.config import Settings
from app.core.errors import (
    ChatTurnError,
    ConfigurationError,
    ModelResponseError,
    ProviderError,
    RetrievalError,
    SqlExecutionError,
    SqlValidationError,
)
from app.main import app
from app.routing.router import RouteDecision, RouteLabel
from app.routing.service import ChatResult
from tests.auth_helpers import TestClient


def settings(**kwargs) -> Settings:
    values = dict(
        _env_file=None,
        inetcloud_base_url="https://provider.example/v1",
        gemini_api_key="fixture-key",
        ai_gemini_fallback_enabled=True,
    )
    values.update(kwargs)
    return Settings(**values)


def harness(monkeypatch, responses, **overrides):
    calls = []
    queue = iter(responses)

    def handle(request):
        calls.append(request)
        response = next(queue)
        if isinstance(response, Exception):
            raise response
        return response

    def client(**kwargs):
        kwargs.pop("http_client").close()
        return ChatOpenAI(
            **kwargs, http_client=httpx2.Client(transport=httpx2.MockTransport(handle))
        )

    monkeypatch.setattr("app.ai.inetcloud.ChatOpenAI", client)
    return InetCloudGateway(settings(**overrides)), calls


def test_closing_one_gateway_does_not_close_next_turn_client(monkeypatch):
    def http_client(**kwargs):
        return httpx2.Client(transport=httpx2.MockTransport(lambda request: completion("OK")))

    monkeypatch.setattr("app.ai.inetcloud.DefaultHttpxClient", http_client)
    first = InetCloudGateway(settings())
    assert first.generate_text("Q") == "OK"
    first.close()
    second = InetCloudGateway(settings())
    try:
        assert second.generate_text("Q") == "OK"
    finally:
        second.close()


def completion(content):
    return httpx2.Response(
        200,
        json={
            "id": "fixture-completion",
            "model": "knowledge",
            "object": "chat.completion",
            "created": 1,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }
            ],
        },
    )


def test_chatopenai_sends_verified_completion_schema_and_placeholder(monkeypatch):
    gateway, calls = harness(monkeypatch, [completion('{"route":"SQL","reason":"Rows"}')])
    try:
        result = gateway.generate_structured("Classify", RouteDecision)
    finally:
        gateway.close()
    assert result.route == RouteLabel.SQL
    assert len(calls) == 1
    assert calls[0].url.path == "/v1/chat/completions"
    assert calls[0].headers["authorization"] == "Bearer not-required"
    payload = json.loads(calls[0].content)
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["temperature"] == 0
    assert "max_tokens" not in payload
    assert "tools" not in payload


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504, 400, 401, 403, 404])
def test_http_error_classification_and_sdk_retry_bound(monkeypatch, status):
    gateway, calls = harness(
        monkeypatch, [httpx2.Response(status, json={"error": {"message": "fixture"}})]
    )
    with pytest.raises(ProviderError) as error:
        gateway.generate_text("Question")
    gateway.close()
    assert len(calls) == 1
    assert error.value.fallback_allowed == (status in {408, 429, 500, 502, 503, 504})


def test_malformed_structured_fails_without_another_paid_request(monkeypatch):
    gateway, calls = harness(
        monkeypatch, [completion("bad-json"), completion('{"route":"SQL","reason":"Rows"}')]
    )
    with pytest.raises(ProviderError) as error:
        gateway.generate_structured("Classify", RouteDecision)
    gateway.close()
    assert error.value.fallback_allowed
    assert len(calls) == 1


def test_network_timeout_is_transient(monkeypatch):
    gateway, calls = harness(monkeypatch, [httpx2.ReadTimeout("fixture")])
    with pytest.raises(ProviderError) as error:
        gateway.generate_text("Question")
    gateway.close()
    assert error.value.fallback_allowed
    assert len(calls) == 1


def test_sdk_transient_retry_succeeds_without_app_retry_layer(monkeypatch):
    gateway, calls = harness(
        monkeypatch,
        [
            httpx2.Response(503, json={"error": {"message": "temporary"}}),
            completion("OK"),
        ],
        inetcloud_retry_attempts=2,
    )
    try:
        assert gateway.generate_text("Q") == "OK"
    finally:
        gateway.close()
    assert len(calls) == 2


def test_sdk_retry_exhaustion_is_bounded(monkeypatch):
    gateway, calls = harness(
        monkeypatch,
        [
            httpx2.Response(503, json={"error": {"message": "temporary"}}),
            httpx2.Response(503, json={"error": {"message": "temporary"}}),
        ],
        inetcloud_retry_attempts=2,
    )
    with pytest.raises(ProviderError):
        gateway.generate_text("Q")
    gateway.close()
    assert len(calls) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_sdk_does_not_retry_configuration_errors_when_retries_enabled(monkeypatch, status):
    gateway, calls = harness(
        monkeypatch,
        [httpx2.Response(status, json={"error": {"message": "configuration"}})],
        inetcloud_retry_attempts=3,
    )
    with pytest.raises(ProviderError) as error:
        gateway.generate_text("Q")
    gateway.close()
    assert not error.value.fallback_allowed
    assert len(calls) == 1


@pytest.mark.parametrize("selected", ["inetcloud-knowledge", "gemini"])
def test_success_calls_only_selected_provider(monkeypatch, selected):
    calls = []
    monkeypatch.setattr(
        "app.ai.chat.build_generation_gateway", lambda cfg, model: calls.append(model) or model
    )

    def pipeline(gateway):
        return SimpleNamespace(chat=lambda question: ChatResult(gateway, RouteLabel.SQL))

    result = ModelChatService(settings(ai_default_model=selected), pipeline).chat("Question")
    assert calls == [selected]
    assert result.used_model == selected
    assert not result.fallback_used


def test_failure_after_router_restarts_entire_pipeline(monkeypatch):
    stages = []
    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda cfg, model: model)

    def pipeline(model):
        def chat(question):
            stages.append((model, "router", question))
            stages.append((model, "sql", question))
            if model == "inetcloud-knowledge":
                raise ProviderError("temporary", fallback_allowed=True)
            return ChatResult("final", RouteLabel.SQL)

        return SimpleNamespace(chat=chat)

    result = ModelChatService(settings(), pipeline).chat("same dataset question")
    assert [stage[:2] for stage in stages] == [
        ("inetcloud-knowledge", "router"),
        ("inetcloud-knowledge", "sql"),
        ("gemini", "router"),
        ("gemini", "sql"),
    ]
    assert result.requested_model == "inetcloud-knowledge"
    assert result.used_model == "gemini"
    assert result.fallback_used


@pytest.mark.parametrize(
    "failure",
    [
        SqlValidationError("unsafe"),
        SqlExecutionError("database"),
        RetrievalError("no evidence"),
        ModelResponseError("invalid citations"),
        ConfigurationError("configuration"),
        ProviderError("401"),
    ],
)
def test_non_provider_failures_never_fallback(monkeypatch, failure):
    calls = []
    monkeypatch.setattr(
        "app.ai.chat.build_generation_gateway", lambda cfg, model: calls.append(model) or model
    )

    def chat(question):
        raise failure

    with pytest.raises(ChatTurnError):
        ModelChatService(settings(), lambda gateway: SimpleNamespace(chat=chat)).chat("Question")
    assert calls == ["inetcloud-knowledge"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"ai_gemini_fallback_enabled": False},
        {"gemini_api_key": None},
        {"ai_default_model": "gemini"},
    ],
)
def test_fallback_requires_explicit_setting_and_gemini_configuration(monkeypatch, overrides):
    calls = []
    monkeypatch.setattr(
        "app.ai.chat.build_generation_gateway", lambda cfg, model: calls.append(model) or model
    )

    def fail(question):
        raise ProviderError("unavailable", fallback_allowed=True)

    with pytest.raises(ChatTurnError):
        ModelChatService(settings(**overrides), lambda gateway: SimpleNamespace(chat=fail)).chat(
            "Q"
        )
    assert len(calls) == 1


def test_both_providers_fail_without_loop_or_fabricated_answer(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.ai.chat.build_generation_gateway", lambda cfg, model: calls.append(model) or model
    )

    def fail(question):
        raise ProviderError("unavailable", fallback_allowed=True)

    with pytest.raises(ChatTurnError) as error:
        ModelChatService(settings(), lambda gateway: SimpleNamespace(chat=fail)).chat("Q")
    assert calls == ["inetcloud-knowledge", "gemini"]
    assert error.value.fallback_used


def test_models_discovery_is_fixed_and_does_not_call_upstream(monkeypatch, contract_session):
    monkeypatch.setattr("app.api.routes.get_settings", lambda: settings())
    body = TestClient(app).get("/api/models").json()
    assert body["default_model"] == "inetcloud-knowledge"
    assert [model["id"] for model in body["models"]] == ["inetcloud-knowledge", "gemini"]
    assert "provider.example" not in str(body)
    assert "fixture-key" not in str(body)
    assert (
        TestClient(app).post("/api/chat", json={"message": "Q", "model_id": "unknown"}).status_code
        == 422
    )
    assert (
        TestClient(app)
        .post("/api/chat", json={"message": "Q", "base_url": "https://untrusted.example/v1"})
        .status_code
        == 422
    )


def test_sql_only_build_does_not_instantiate_gemini(monkeypatch):
    from app.dependencies import build_chat_service
    from tests.plan_fixtures import decision_from_sql

    class Gateway:
        def generate_structured(self, prompt, response_model):
            if response_model is RouteDecision:
                return response_model(route="SQL", reason="Rows")
            return decision_from_sql("SELECT COUNT(*) AS total FROM products", prompt)

        def generate_text(self, prompt):
            return "150 products"

    def forbidden_gemini(*args, **kwargs):
        pytest.fail("SQL using Knowledge must not instantiate Gemini")

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda cfg, model: Gateway())
    monkeypatch.setattr("app.ai.providers.GeminiGateway", forbidden_gemini)
    monkeypatch.setattr(
        "app.dependencies.SqlExecutor",
        lambda *args: SimpleNamespace(execute=lambda query, parameters: [{"total": 150}]),
    )
    result = build_chat_service(settings(gemini_api_key=None)).chat("Count products")
    assert result.used_model == "inetcloud-knowledge"
    assert result.rows == [{"total": 150}]


def test_missing_embedding_configuration_is_explicit():
    from app.ai.providers import build_embedding_gateway

    with pytest.raises(ConfigurationError, match="Gemini Embedding"):
        build_embedding_gateway(settings(gemini_api_key=None)).embed_query("Q")


def test_empty_workspace_has_no_used_model_or_provider_initialization(monkeypatch):
    from app.datasets.context import DatasetSqlContext
    from app.dependencies import build_dataset_chat_service

    def forbidden(*args, **kwargs):
        pytest.fail("Empty workspaces must not construct a provider")

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", forbidden)
    context = DatasetSqlContext(schema_context="", table_columns={}, allowed_schemas={})
    result = build_dataset_chat_service(settings(inetcloud_base_url=None), context).chat("Q")
    assert result.route == RouteLabel.UNSUPPORTED
    assert result.requested_model == "inetcloud-knowledge"
    assert result.used_model is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ai_default_model": "unknown"},
        {"inetcloud_model": "unknown"},
        {"inetcloud_base_url": "http://provider.example/v1"},
        {"inetcloud_base_url": "https://user:secret@provider.example/v1"},
        {"inetcloud_timeout_seconds": 0},
        {"inetcloud_retry_attempts": 10},
    ],
)
def test_invalid_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        settings(**kwargs)
