"""Rehearse additive installation on a pre-JOIN synthetic database, never main."""

from uuid import uuid4

import pytest
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.conversations.repository import ConversationRepository
from app.core.config import get_settings
from app.database.integrity import legacy_fingerprints
from app.database.join_migration import JOIN_VERSION, migrate_relationships
from app.database.models import Base, DatasetRelationship, User
from app.database.test_safety import require_test_database
from app.datasets.repository import DatasetRepository
from app.rag.repository import DocumentRepository
from app.rag.upload_parser import parse_document_file
from tests.test_dataset_parser import parse
from tests.test_guest_integration import OfflineEmbedder

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("legacy_owner_required", [False, True])
def test_additive_migration_rehearsal_preserves_synthetic_main_shape(
    monkeypatch: pytest.MonkeyPatch,
    legacy_owner_required: bool,
) -> None:
    settings = get_settings()
    require_test_database(settings.database_setup_url)
    admin = create_engine(settings.database_setup_url, isolation_level="AUTOCOMMIT")
    name = "shopquery_test_join_clone_" + uuid4().hex[:12]
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = admin.url.set(database=name)
    monkeypatch.setenv("SHOPQUERY_TEST_DATABASE_URL", url.render_as_string(hide_password=False))
    require_test_database(url.render_as_string(hide_password=False))
    engine = create_engine(url)
    reader = make_url(settings.database_readonly_url).set(database=name)
    reader_engine = create_engine(reader)
    try:
        metadata = MetaData()
        for item in Base.metadata.sorted_tables:
            if item.name != "dataset_relationships":
                item.to_metadata(metadata)
        old_tables = metadata.tables["dataset_tables"]
        for constraint in list(old_tables.constraints):
            if constraint.name == "uq_dataset_tables_scope":
                old_tables.constraints.remove(constraint)
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION vector"))
            connection.execute(text("CREATE SCHEMA uploaded_data"))
            connection.execute(text("GRANT USAGE ON SCHEMA uploaded_data TO shopquery_reader"))
        metadata.create_all(engine)
        owner = uuid4()
        with engine.begin() as connection:
            connection.execute(
                User.__table__.insert(),
                {
                    "user_id": owner,
                    "issuer": "https://accounts.google.com",
                    "subject": uuid4().hex,
                    "email": "synthetic-migration@example.invalid",
                    "display_name": "Synthetic",
                    "active": True,
                },
            )
            owner_nullability = "NOT NULL" if legacy_owner_required else ""
            connection.execute(
                text(
                    "CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, "
                    "applied_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                    f"owner_user_id UUID {owner_nullability})"
                )
            )
        datasets = DatasetRepository(engine, reader_engine, owner)
        workspaces = []
        for index in range(4):
            dataset = datasets.create_workspace(f"Synthetic {index}")
            for table_number in range(1 if index == 3 else 2):
                dataset = datasets.add_table(
                    dataset.dataset_id,
                    parse(
                        f"synthetic_{table_number}.csv",
                        b"Id,Value,Instant\n101,12345678901234567890.12,2026-10-01T00:00:00+07:00\n",
                    ),
                )
            workspaces.append(dataset)
        documents = DocumentRepository(engine, reader_engine, owner)
        for index in range(8):
            documents.add_document(
                workspaces[index % 4].dataset_id,
                parse_document_file(
                    f"policy_{index}.md",
                    f"# Policy {index}\n\nSynthetic rule {index}.".encode(),
                    max_bytes=1000,
                ),
                OfflineEmbedder(),
            )
        conversations = ConversationRepository(engine, owner)
        for index in range(4):
            conversation = conversations.create(workspaces[index % 4].dataset_id)
            for _ in range(3):
                conversations.add_user_message(conversation.conversation_id, "Synthetic question")
                conversations.add_response_message(
                    conversation.conversation_id,
                    content="Synthetic answer",
                    response_metadata={"rows": []},
                    is_error=False,
                )
            conversations.add_user_message(
                conversation.conversation_id, "Synthetic pending question"
            )
        before = legacy_fingerprints(engine)
        with engine.connect() as connection:
            owners = connection.execute(
                text("SELECT dataset_id, owner_user_id FROM datasets ORDER BY 1")
            ).all()
            assert not connection.scalar(text("SELECT to_regclass('dataset_relationships')"))
            assert not connection.scalar(text("SELECT to_regclass('uq_dataset_tables_scope')"))
        if legacy_owner_required:
            with pytest.raises(ValueError, match="explicit"):
                migrate_relationships(engine)
        with monkeypatch.context() as failure:

            def fail_create(*args, **kwargs):
                raise RuntimeError("synthetic DDL failure")

            failure.setattr(DatasetRelationship.__table__, "create", fail_create)
            with pytest.raises(RuntimeError, match="synthetic DDL"):
                migrate_relationships(engine, owner)
        with engine.connect() as connection:
            assert not connection.scalar(text("SELECT to_regclass('uq_dataset_tables_scope')"))
        migrate_relationships(engine, owner)
        migrate_relationships(engine, owner)
        assert legacy_fingerprints(engine) == before
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT dataset_id, owner_user_id FROM datasets ORDER BY 1")
                ).all()
                == owners
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM schema_migrations WHERE version=:version"),
                    {"version": JOIN_VERSION},
                )
                == 1
            )
            assert connection.scalar(text("SELECT count(*) FROM dataset_relationships")) == 0
        with pytest.raises(DBAPIError), reader_engine.connect() as connection:
            connection.execute(text("SELECT * FROM dataset_relationships"))
    finally:
        reader_engine.dispose()
        engine.dispose()
        admin.dispose()
