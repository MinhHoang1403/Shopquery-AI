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
