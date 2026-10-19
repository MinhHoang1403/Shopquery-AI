"""Relationship APIs retain Guest capability, explicit confirmation and RAM quotas."""

from unittest.mock import Mock

import pytest

from app.datasets.relationships import RelationshipPreview, RelationshipRecord
from app.guest import routes
from tests.test_guest import guest_api as api_fixture  # noqa: F401
from tests.test_guest import new_guest


def test_guest_confirmation_csrf_scope_reset_and_worker_expiry(api_fixture, monkeypatch):  # noqa: F811
    api = api_fixture
    api.settings.sql_join_v1_enabled = True
    for name, value in (
        ("get_settings", lambda: api.settings),
        ("guest_store", lambda: api.store),
        ("guest_control", lambda: routes.guest_control()),
    ):
        monkeypatch.setattr(f"app.guest.relationship_routes.{name}", value)
    monkeypatch.setattr("app.api.relationship_routes.get_settings", lambda: api.settings)
    a, b = new_guest(api), new_guest(api)
    ids = []
    for filename in ("students.csv", "payments.csv"):
        response = api.client.post(
            f"/api/guest/files?filename={filename}", headers=a, content=b"Id,Amount\n101,2\n"
        )
        ids.append(response.json()["preview"]["file_id"])
    body = {
        "source_table_id": ids[1],
        "source_column": "id",
        "target_table_id": ids[0],
        "target_column": "id",
    }
    preview = RelationshipPreview(
        **body,
        revision="a" * 64,
        valid=True,
        cardinality="one-to-one",
        source_rows=1,
        target_rows=1,
        source_nulls=0,
        target_nulls=0,
        target_duplicates=0,
        orphan_rows=0,
        reasons=[],
    )
    worker = Mock(return_value=preview)
    monkeypatch.setattr("app.guest.relationship_routes.run_isolated", worker)
    path = "/api/guest/relationships"
    for bad_headers in (
        {},
        {"X-Guest-Token": a["X-Guest-Token"]},
        {**a, "Origin": "https://attacker.invalid"},
    ):
        assert api.client.post(path + "/preview", headers=bad_headers, json=body).status_code in {
            401,
            403,
        }
    worker.assert_not_called()
    assert api.client.post(path + "/preview", headers=a, json=body).status_code == 200
    assert api.client.get(path, headers=a).json()["relationships"] == []
    confirmation = {**body, "revision": preview.revision, "confirmed": True}
    record = api.client.post(path, headers=a, json=confirmation)
    assert record.status_code == 200
    relation_path = path + "/" + record.json()["relationship_id"]
    assert api.client.post(path, headers=b, json=confirmation).status_code == 404
    assert api.client.get(path, headers=b).json()["relationships"] == []
    assert api.client.delete(relation_path + "?confirmed=true", headers=b).status_code == 404
    assert api.client.delete(relation_path, headers=a).status_code == 409
    assert api.client.delete(relation_path + "?confirmed=true", headers=a).status_code == 204
    assert len(api.client.get("/api/guest/limits", headers=a).json()["files"]) == 2
    api.client.post(path, headers=a, json=confirmation)
    assert api.client.post("/api/guest/reset", headers=a, json={}).status_code == 204
    fresh = new_guest(api)
    assert api.client.get(path, headers=fresh).json()["relationships"] == []
    assert api.client.get(path, headers=a).status_code in {401, 410}
    # A worker result arriving after reset must not repopulate released session RAM.
    for filename in ("a.csv", "b.csv"):
        api.client.post(
            f"/api/guest/files?filename={filename}", headers=fresh, content=b"Id\n101\n"
        )
    context = next(c for c in api.store._contexts.values() if len(c.files) == 2)
    worker.side_effect = lambda *args: (api.store.reset(context), preview)[1]
    assert api.client.post(path + "/preview", headers=fresh, json=body).status_code == 410
    assert context.relationships == [] and context.cancelled.is_set()


def test_guest_relation_memory_budget_and_flag_off(api_fixture, monkeypatch):  # noqa: F811
    api = api_fixture
    monkeypatch.setattr("app.guest.relationship_routes.guest_store", lambda: api.store)
    monkeypatch.setattr("app.guest.relationship_routes.get_settings", lambda: api.settings)
    monkeypatch.setattr("app.api.relationship_routes.get_settings", lambda: api.settings)
    headers = new_guest(api)
    assert api.client.get("/api/guest/relationships", headers=headers).json()["enabled"] is False
    body = {
        "source_table_id": "a",
        "source_column": "id",
        "target_table_id": "b",
        "target_column": "id",
    }
    assert (
        api.client.post("/api/guest/relationships/preview", headers=headers, json=body).status_code
        == 403
    )
    from fastapi import HTTPException

    from app.guest.worker import parse_guest_file

    context = next(iter(api.store._contexts.values()))
    for name in ("a.csv", "b.csv"):
        api.store.add_file(context, parse_guest_file(name, b"Id\n101\n", None, api.settings))
    record = RelationshipRecord(
        source_table_id=context.files[0].file_id,
        target_table_id=context.files[1].file_id,
        source_column="id",
        target_column="id",
        revision="a" * 64,
        relationship_id="ram",
        valid=True,
        cardinality="one-to-one",
        source_rows=1,
        target_rows=1,
        source_nulls=0,
        target_nulls=0,
        target_duplicates=0,
        orphan_rows=0,
        reasons=[],
    )
    api.settings.guest_max_session_bytes = api.store._memory_bytes(context)
    with pytest.raises(HTTPException) as error:
        api.store.confirm_relationship(context, record)
    assert error.value.status_code == 429 and context.relationships == []
