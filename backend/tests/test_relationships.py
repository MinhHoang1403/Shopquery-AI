"""Relationship contracts reject untrusted identifiers and temporal mismatches."""

import pytest
from pydantic import ValidationError

from app.datasets.relationships import RelationshipConfirm, RelationshipInput


def test_confirmation_is_explicit_and_revision_bound() -> None:
    values = dict(
        source_table_id="1",
        source_column="student_id",
        target_table_id="2",
        target_column="student_id",
    )
    for confirmation in (False, 1, "true", None):
        with pytest.raises(ValidationError):
            RelationshipConfirm(**values, revision="a" * 64, confirmed=confirmation)
    with pytest.raises(ValidationError):
        RelationshipConfirm(**values, confirmed=True)
    assert RelationshipConfirm(**values, revision="a" * 64, confirmed=True).confirmed


def test_client_cannot_supply_physical_tables_sql_or_composite_keys() -> None:
    values = dict(source_table_id="1", source_column="id", target_table_id="2", target_column="id")
    for extra in ({"sql": "SELECT 1"}, {"physical_table_name": "someone_else"}):
        with pytest.raises(ValidationError):
            RelationshipInput(**values, **extra)
    with pytest.raises(ValidationError):
        RelationshipInput(**{**values, "source_column": ["id", "other"]})


@pytest.mark.usefixtures("contract_session")
def test_discovery_api_keeps_authentication_csrf_owner_and_feature_gate(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.core.config import get_settings
    from app.core.errors import ResourceNotFoundError
    from app.datasets.relationships import RelationshipDiscoveryResponse
    from app.main import app
    from tests.auth_helpers import TEST_OWNER, TestClient

    settings = get_settings().model_copy(update={"sql_join_v1_enabled": True})
    monkeypatch.setattr("app.api.relationship_routes.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.relationship_routes.get_setup_engine", lambda: "engine")
    control = MagicMock()
    control.work.side_effect = lambda *args: nullcontext()
    monkeypatch.setattr("app.api.relationship_routes.resource_control", lambda: control)
    repository = MagicMock()
    repository.discover.return_value = RelationshipDiscoveryResponse(
        relationships=[],
        suggestions=[],
        truncated=False,
    )
    factory = MagicMock(return_value=repository)
    monkeypatch.setattr("app.api.relationship_routes.RelationshipRepository", factory)
    client = TestClient(app)
    path = "/api/datasets/15/relationships/discover"
    response = client.post(path)
    assert response.status_code == 200 and response.json()["truncated"] is False
    factory.assert_called_once_with("engine", TEST_OWNER)
    repository.discover.assert_called_once_with(15)
    control.work.assert_called_once_with(TEST_OWNER, "preview")
    repository.discover.reset_mock()
    assert client.post(path, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    invalid_client = TestClient(app)
    invalid_client.cookies.set(settings.session_cookie_name, "invalid")
    assert invalid_client.post(path).status_code == 401
    repository.discover.assert_not_called()
    repository.discover.side_effect = ResourceNotFoundError("Không tìm thấy workspace.")
    assert client.post(path).status_code == 404
    off = SimpleNamespace(sql_join_v1_enabled=False)
    monkeypatch.setattr("app.api.relationship_routes.get_settings", lambda: off)
    repository.discover.reset_mock()
    assert client.post(path).status_code == 403
    repository.discover.assert_not_called()


def test_rescan_stores_only_verified_automatic_links_and_is_idempotent(monkeypatch):
    from types import SimpleNamespace

    from app.datasets.relationship_repository import RelationshipRepository
    from tests.test_relationship_detection import ev_tables, verification_connection

    monkeypatch.setattr(RelationshipRepository, "_tables", lambda *args: ev_tables())
    connection = verification_connection()
    discovery = RelationshipRepository._discover_and_store(connection, 15, None)
    inserts = [
        args[0]
        for args, _ in connection.execute.call_args_list
        if getattr(args[0], "is_insert", False)
    ]
    assert len(discovery.automatic) == len(inserts) == 2
    for statement in inserts:
        params = statement.compile().params
        assert params["dataset_id"] == 15
        assert params["statistics"]["origin"] == "automatic"
        assert params["statistics"]["confirmed"] is False
        assert params["statistics"]["orphan_rows"] == 0
    connection = verification_connection()
    connection.execute.return_value.__iter__.return_value = iter(
        [
            SimpleNamespace(source_table_id=3, target_table_id=1),
            SimpleNamespace(source_table_id=3, target_table_id=2),
        ]
    )
    again = RelationshipRepository._discover_and_store(connection, 15, None)
    assert again.automatic == [] and again.suggestions == []
    connection.execute.return_value.one.assert_not_called()
    assert not any(
        getattr(args[0], "is_insert", False) for args, _ in connection.execute.call_args_list
    )


def test_rescan_denies_an_unowned_workspace_before_discovery(monkeypatch):
    from unittest.mock import MagicMock

    from app.core.errors import ResourceNotFoundError
    from app.datasets.relationship_repository import RelationshipRepository
    from tests.auth_helpers import TEST_OWNER

    session = MagicMock()
    session.scalar.return_value = None
    factory = MagicMock()
    factory.return_value.__enter__.return_value = session
    monkeypatch.setattr("app.datasets.relationship_repository.Session", factory)
    discovery = MagicMock()
    monkeypatch.setattr(RelationshipRepository, "_discover_and_store", discovery)
    with pytest.raises(ResourceNotFoundError):
        RelationshipRepository(MagicMock(), TEST_OWNER).discover(15)
    discovery.assert_not_called()
    params = session.scalar.call_args.args[0].compile().params
    assert params["owner_user_id_1"] == TEST_OWNER and params["dataset_id_1"] == 15
