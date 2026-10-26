"""Preview accepts registry IDs only and never invokes an AI provider."""

from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ResourceNotFoundError
from app.datasets.parser import ColumnSpec
from app.datasets.repository import DatasetInfo, DatasetRepository, DatasetTableInfo
from app.main import app
from tests.auth_helpers import TEST_OWNER, TestClient

pytestmark = pytest.mark.usefixtures("contract_session")


def workspace():
    first = DatasetTableInfo(
        "Phí",
        None,
        "private_registered",
        (ColumnSpec("Phí", "fee", "NUMERIC"),),
        3,
        dataset_table_id=12,
        original_filename="fees.csv",
        file_type="csv",
    )
    second = DatasetTableInfo(
        "Khác", None, "other_registered", first.columns, 2, dataset_table_id=13
    )
    return DatasetInfo(
        7,
        "Workspace",
        None,
        None,
        None,
        None,
        datetime.now(UTC),
        first,
        tables=(first, second),
        owner_user_id=TEST_OWNER,
    )


def test_preview_uses_exact_workspace_table_limit_and_preserves_values(monkeypatch):
    calls = []
    dataset = workspace()

    def get(dataset_id):
        if dataset_id != 7:
            raise ResourceNotFoundError("Not found")
        return dataset

    def rows(dataset_id, limit, table_id):
        calls.append((dataset_id, limit, table_id))
        return [{"Phí": "9007199254740993.01"}, {"Phí": None}, {"Phí": "0.00"}]

    monkeypatch.setattr(
        "app.api.routes.build_dataset_repository",
        lambda owner: SimpleNamespace(get=get, preview_rows=rows),
    )
    client = TestClient(app)
    result = client.get("/api/datasets/7/tables/12/preview?limit=20&physical_table_name=users")
    assert result.status_code == 200
    body = result.json()
    assert body["dataset_table_id"] == 12 and body["row_count"] == 3
    assert body["columns"][0]["source_name"] == "Phí"
    assert body["rows"] == [{"Phí": "9007199254740993.01"}, {"Phí": None}, {"Phí": "0.00"}]
    assert "private_registered" not in result.text
    assert calls == [(7, 20, 12)]
    for path in ("/api/datasets/8/tables/12/preview", "/api/datasets/7/tables/99/preview"):
        assert client.get(path).status_code == 404
    assert client.get("/api/datasets/7/tables/13/preview").status_code == 200
    assert calls[-1] == (7, 25, 13)
    for limit in (0, 51, -1):
        assert client.get(f"/api/datasets/7/tables/12/preview?limit={limit}").status_code == 422
    assert client.get("/api/datasets/7/tables/users/preview").status_code == 422


def test_preview_keeps_rate_limit_boundary_and_safe_database_errors(monkeypatch):
    work = MagicMock(return_value=nullcontext())
    monkeypatch.setattr("app.api.routes.resource_control", lambda: SimpleNamespace(work=work))
    monkeypatch.setattr(
        "app.api.routes.build_dataset_repository",
        lambda owner: SimpleNamespace(
            get=lambda _: workspace(),
            preview_rows=MagicMock(side_effect=SQLAlchemyError("private SQL")),
        ),
    )
    response = TestClient(app).get("/api/datasets/7/tables/12/preview")
    assert response.status_code == 503 and "private SQL" not in response.text
    work.assert_called_once_with(TEST_OWNER, "preview")


def test_workspace_metadata_does_not_eagerly_read_table_rows(monkeypatch):
    preview = MagicMock(return_value=[])
    monkeypatch.setattr(
        "app.api.routes.build_dataset_repository",
        lambda owner: SimpleNamespace(get=lambda _: workspace(), preview_rows=preview),
    )
    client = TestClient(app)
    response = client.get("/api/datasets/7?include_preview=false")
    assert response.status_code == 200
    assert len(response.json()["tables"]) == 2
    assert response.json()["preview_rows"] == []
    preview.assert_not_called()
    assert client.get("/api/datasets/7").status_code == 200
    preview.assert_called_once_with(7)


def test_reader_query_is_registered_bounded_readonly_and_timed():
    reader = MagicMock()
    connection = reader.connect.return_value.__enter__.return_value
    connection.execute.return_value.mappings.return_value = [{"fee": None}]
    repository = DatasetRepository(MagicMock(), reader, TEST_OWNER)
    repository.get = lambda _: workspace()
    assert repository.preview_rows(7, 25, 12) == [{"Phí": None}]
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert statements[:2] == ["SET TRANSACTION READ ONLY", "SET LOCAL statement_timeout='5s'"]
    assert "uploaded_data.private_registered" in statements[2] and "LIMIT" in statements[2]
    with pytest.raises(ResourceNotFoundError):
        repository.preview_rows(7, 25, 99)
    with pytest.raises(ValueError):
        repository.preview_rows(7, 5000, 12)
