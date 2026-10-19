"""No advertised or generated demo results when the default corpus is empty."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.main import app
from tests.auth_helpers import TestClient

pytestmark = pytest.mark.usefixtures("contract_session")


@pytest.mark.parametrize("has_demo", [False, True])
def test_demo_is_only_listed_when_it_has_data(monkeypatch, has_demo):
    repository = SimpleNamespace(list=lambda: [], has_demo_data=lambda: has_demo)
    monkeypatch.setattr("app.api.routes.build_dataset_repository", lambda owner: repository)
    response = TestClient(app).get("/api/datasets")
    assert response.status_code == 200
    assert len(response.json()) == int(has_demo)


@pytest.mark.parametrize("conversation", [False, True])
def test_empty_default_does_not_call_a_provider_or_persist_a_turn(monkeypatch, conversation):
    repository = SimpleNamespace(has_demo_data=lambda: False)
    monkeypatch.setattr("app.api.routes.build_dataset_repository", lambda owner: repository)
    service = Mock(side_effect=AssertionError("Must not build a provider"))
    monkeypatch.setattr("app.api.routes.build_chat_service", service)
    chats = SimpleNamespace(get=lambda id: SimpleNamespace(dataset_id=None))
    monkeypatch.setattr("app.api.routes.build_conversation_repository", lambda owner: chats)
    path = f"/api/conversations/{uuid4()}/messages" if conversation else "/api/chat"
    response = TestClient(app).post(path, json={"message": "Total revenue?"})
    assert response.status_code == 409
    assert "Chưa có dữ liệu" in response.json()["detail"]
    service.assert_not_called()
