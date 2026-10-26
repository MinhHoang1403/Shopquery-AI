"""Owned table previews use PostgreSQL without altering imported data or relationships."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.database.session import get_readonly_engine, get_setup_engine
from app.datasets.repository import DatasetRepository
from tests.test_auth_integration import accounts  # noqa: F401
from tests.test_dataset_parser import parse

pytestmark = pytest.mark.integration


def test_preview_is_scoped_exact_readonly_and_does_not_discover(accounts):  # noqa: F811
    a, b = accounts.a, accounts.b
    dataset = a.datasets.create_workspace("Preview " + uuid4().hex)
    a.datasets.add_table(
        dataset.dataset_id,
        parse("fees.csv", "Tên,Phí\nTiếng Việt,9007199254740993.01\nZero,0.00\nThiếu,\n".encode()),
    )
    dataset = a.datasets.add_table(dataset.dataset_id, parse("other.csv", b"Value\nOTHER\n"))
    first, second = dataset.tables
    path = f"/api/datasets/{dataset.dataset_id}/tables/{first.dataset_table_id}/preview"
    engine, reader = get_setup_engine(), get_readonly_engine()
    with engine.connect() as connection:
        count_before = connection.scalar(
            text("SELECT count(*) FROM dataset_relationships WHERE dataset_id=:id"),
            {"id": dataset.dataset_id},
        )
    response = a.client.get(path + "?limit=2")
    assert response.status_code == 200
    assert response.json()["rows"] == [
        {"Tên": "Tiếng Việt", "Phí": "9007199254740993.01"},
        {"Tên": "Zero", "Phí": "0.00"},
    ]
    assert a.client.get(path).json()["rows"][-1]["Phí"] is None
    assert b.client.get(path).status_code == 404
    assert (
        a.client.get(
            path.replace(str(first.dataset_table_id) + "/preview", "999999/preview")
        ).status_code
        == 404
    )
    other = a.client.get(
        f"/api/datasets/{dataset.dataset_id}/tables/{second.dataset_table_id}/preview"
    )
    assert other.json()["rows"] == [{"Value": "OTHER"}]
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM dataset_relationships WHERE dataset_id=:id"),
                {"id": dataset.dataset_id},
            )
            == count_before
        )
    repository = DatasetRepository(engine, reader, a.user_id)
    assert len(repository.preview_rows(dataset.dataset_id, 50, first.dataset_table_id)) == 3
