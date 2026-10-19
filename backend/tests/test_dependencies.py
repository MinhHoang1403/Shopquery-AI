"""Runtime repositories never perform schema setup and always bind an owner."""

from uuid import uuid4

import pytest

from app.dependencies import (
    build_conversation_repository,
    build_dataset_repository,
    build_document_repository,
)


@pytest.mark.parametrize(
    "factory", [build_conversation_repository, build_dataset_repository, build_document_repository]
)
def test_repository_construction_requires_owner_without_schema_writes(monkeypatch, factory):
    monkeypatch.setattr("app.dependencies.get_setup_engine", lambda: object())
    monkeypatch.setattr("app.dependencies.get_readonly_engine", lambda: object())
    monkeypatch.setattr(
        "app.database.setup.create_schema", lambda engine: pytest.fail("Runtime DDL")
    )
    owner = uuid4()
    repository = factory(owner)
    assert repository._owner_user_id == owner
    with pytest.raises(TypeError):
        factory()
