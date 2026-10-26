"""Model selection, attribution persistence, and legacy migration coverage."""

import pytest
from sqlalchemy import text

from app.conversations.repository import ConversationRepository
from app.database.session import get_setup_engine
from app.database.setup import create_schema
from app.main import app
from tests.auth_helpers import TEST_OWNER, TestClient
from tests.test_management_api import FakeChatService, FakeConversationRepository


def test_api_preserves_selection_and_restores_attribution(monkeypatch, contract_session):
    repository = FakeConversationRepository()
    monkeypatch.setattr("app.api.routes.build_conversation_repository", lambda owner: repository)
    selections = []

    def build(settings):
        selections.append(settings.ai_default_model)
        return FakeChatService()

    monkeypatch.setattr("app.api.routes.build_chat_service", build)
    client = TestClient(app)
    created = client.post("/api/conversations", json={"model_id": "gemini"}).json()
    path = f"/api/conversations/{created['conversation_id']}"
    assert created["model_id"] == "gemini"
    assert client.patch(path, json={"model_id": "inetcloud-knowledge"}).status_code == 200
    sent = client.post(path + "/messages", json={"message": "Q", "model_id": "gemini"})
    assert sent.status_code == 200
    assert selections == ["gemini"]
    assert client.get(path).json()["model_id"] == "gemini"
    assert len(client.get(path).json()["messages"]) == 2


def test_fallback_taxonomy_survives_single_pair_persistence_and_reload(
    monkeypatch, contract_session
):
    from types import SimpleNamespace

    from app.ai.chat import ModelChatService
    from app.core.config import Settings
    from app.core.errors import ErrorContext, ProviderError
    from app.routing.router import RouteLabel
    from app.routing.service import ChatResult

    repository = FakeConversationRepository()
    configuration = Settings(
        _env_file=None,
        inetcloud_base_url="https://fixture.example/v1",
        ai_default_model="inetcloud-knowledge",
        gemini_api_key="fixture",
        ai_gemini_fallback_enabled=True,
    )
    monkeypatch.setattr("app.api.routes.get_settings", lambda: configuration)
    monkeypatch.setattr("app.api.routes.build_conversation_repository", lambda owner: repository)
    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda cfg, model: model)
    attempts = []

    def pipeline(model):
        def chat(question, **kwargs):
            attempts.append(model)
            if model == "inetcloud-knowledge":
                raise ProviderError(
                    "PRIVATE raw output",
                    fallback_allowed=True,
                    error_context=ErrorContext(
                        provider="knowledge", error_category="wire_validation"
                    ),
                )
            return ChatResult("Verified fixture answer", RouteLabel.SQL)

        return SimpleNamespace(chat=chat)

    monkeypatch.setattr(
        "app.api.routes.build_chat_service", lambda cfg: ModelChatService(cfg, pipeline)
    )
    client = TestClient(app)
    conversation = client.post("/api/conversations", json={}).json()
    path = f"/api/conversations/{conversation['conversation_id']}"
    assert client.post(path + "/messages", json={"message": "Q"}).status_code == 200
    messages = client.get(path).json()["messages"]
    assert len(messages) == 2 and attempts == ["inetcloud-knowledge", "gemini"]
    metadata = messages[-1]["response"]
    assert metadata["requested_model"] == "inetcloud-knowledge"
    assert metadata["used_model"] == "gemini" and metadata["fallback_used"]
    assert metadata["fallback_reason"] == "primary_provider_wire_validation"
    assert metadata["fallback_error_context"]["error_category"] == "wire_validation"
    assert "PRIVATE" not in str(messages)


@pytest.mark.integration
def test_nullable_model_migration_is_idempotent_and_history_is_preserved():
    engine = get_setup_engine()
    assert engine.url.database != "shopquery", "Migration tests require an isolated test database"
    create_schema(engine)
    repository = ConversationRepository(engine, TEST_OWNER)
    old = repository.create(None, "gemini")
    metadata = {
        "answer": "Legacy answer",
        "route": "SQL",
        "sql": "SELECT 1",
        "rows": [{"x": 1}],
        "sources": [],
        "error": None,
    }
    repository.add_user_message(old.conversation_id, "Legacy question")
    repository.add_response_message(
        old.conversation_id, content="Legacy answer", response_metadata=metadata, is_error=False
    )
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE chat_conversations DROP COLUMN model_id"))
    create_schema(engine)
    create_schema(engine)
    restored = repository.get(old.conversation_id)
    assert restored.model_id == "gemini"
    assert restored.messages[-1].response_metadata == metadata
    assert restored.dataset_id is None
    first = repository.create(None, "inetcloud-knowledge")
    second = repository.create(None, "gemini")
    repository.set_model(first.conversation_id, "gemini")
    repository.set_model(second.conversation_id, "inetcloud-knowledge")
    assert repository.get(first.conversation_id).model_id == "gemini"
    assert repository.get(second.conversation_id).model_id == "inetcloud-knowledge"
    response = dict(
        metadata,
        requested_model="inetcloud-knowledge",
        used_model="gemini",
        fallback_used=True,
        fallback_reason="primary_provider_unavailable",
    )
    repository.add_response_message(
        first.conversation_id, content="answer", response_metadata=response, is_error=False
    )
    assert repository.get(first.conversation_id).messages[-1].response_metadata == response
