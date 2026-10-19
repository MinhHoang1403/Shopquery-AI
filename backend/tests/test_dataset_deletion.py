"""Deletion HTTP contracts without database or provider access."""

import pytest

from app.core.errors import ResourceConflictError, ResourceNotFoundError
from app.main import app
from tests.auth_helpers import TestClient

pytestmark = pytest.mark.usefixtures("contract_session")


class DeletionRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int | bool]] = []

    def delete(self, dataset_id: int, *, delete_conversations: bool = False) -> None:
        if dataset_id != 7:
            raise ResourceNotFoundError("Không tìm thấy bộ dữ liệu.")
        if not delete_conversations:
            raise ResourceConflictError("Bộ dữ liệu có lịch sử chat.")
        self.calls.append((dataset_id, delete_conversations))

    def delete_table(self, dataset_id: int, table_id: int) -> None:
        if (dataset_id, table_id) != (7, 12):
            raise ResourceNotFoundError("Không tìm thấy bảng trong bộ dữ liệu.")
        self.calls.append((dataset_id, table_id))


def test_dataset_delete_requires_explicit_history_consent(monkeypatch) -> None:
    repository = DeletionRepository()
    monkeypatch.setattr("app.api.routes.build_dataset_repository", lambda owner: repository)
    client = TestClient(app)

    assert client.delete("/api/datasets/7").status_code == 409
    assert repository.calls == []
    deleted = client.delete("/api/datasets/7?delete_conversations=true")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert repository.calls == [(7, True)]


@pytest.mark.parametrize("dataset_id", [0, -1, 99])
def test_dataset_delete_missing_or_default_cannot_delete(monkeypatch, dataset_id: int) -> None:
    repository = DeletionRepository()
    monkeypatch.setattr("app.api.routes.build_dataset_repository", lambda owner: repository)
    assert TestClient(app).delete(f"/api/datasets/{dataset_id}").status_code == 404
    assert repository.calls == []


def test_table_delete_is_scoped_and_returns_empty_response(monkeypatch) -> None:
    repository = DeletionRepository()
    monkeypatch.setattr("app.api.routes.build_dataset_repository", lambda owner: repository)
    client = TestClient(app)
    for path in ("/api/datasets/8/tables/12", "/api/datasets/7/tables/99"):
        assert client.delete(path).status_code == 404
    deleted = client.delete("/api/datasets/7/tables/12")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert repository.calls == [(7, 12)]


@pytest.mark.parametrize(
    "path",
    [
        "/api/datasets/default",
        "/api/datasets/7/tables/products",
        "/api/datasets/7?delete_conversations=invalid",
    ],
)
def test_delete_rejects_invalid_identifiers_and_consent(path: str) -> None:
    assert TestClient(app).delete(path).status_code == 422
