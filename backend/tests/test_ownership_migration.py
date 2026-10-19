"""Legacy migration rehearsal in a newly created, disposable PostgreSQL database."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.auth.repository import AuthRepository
from app.conversations.repository import ConversationRepository
from app.database.integrity import legacy_fingerprints
from app.database.migrations import migrate_ownership
from app.database.session import get_setup_engine
from app.database.setup import create_schema
from app.database.test_safety import require_test_database
from app.datasets.parser import parse_tabular_file
from app.datasets.repository import DatasetRepository
from app.rag.repository import DocumentRepository
from app.rag.upload_parser import parse_document_file
from tests.test_auth_integration import OfflineEmbedder

pytestmark = pytest.mark.integration


def test_legacy_migration_preserves_values_vectors_ids_and_repeats(monkeypatch):
    parent = get_setup_engine()
    require_test_database(parent.url.render_as_string(hide_password=False))
    name = "shopquery_test_migration_" + uuid4().hex
    with parent.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(parent.url.set(database=name))
    try:
        monkeypatch.setenv(
            "SHOPQUERY_TEST_DATABASE_URL", engine.url.render_as_string(hide_password=False)
        )
        require_test_database(engine.url.render_as_string(hide_password=False))
        create_schema(engine)
        auth = AuthRepository(engine)
        owner = auth.identity("rehearsal-owner", "migration@example.invalid", "Migration owner")
        datasets = DatasetRepository(engine, engine, owner)
        dataset = datasets.create(
            "Legacy dataset",
            parse_tabular_file(
                "fees.csv",
                b"Student,Fee\n001,100\n002,200\n",
                max_bytes=1000,
                max_rows=10,
                max_columns=10,
            ),
        )
        document = DocumentRepository(engine, engine, owner).add_document(
            dataset.dataset_id,
            parse_document_file("policy.md", b"# Policy\n\nLegacy policy.", max_bytes=1000),
            OfflineEmbedder(),
        )
        chats = ConversationRepository(engine, owner)
        conversation = chats.create(dataset.dataset_id, "gemini")
        chats.add_user_message(conversation.conversation_id, "Legacy question")
        metadata = {
            "sql": "SELECT 300",
            "rows": [{"total": 300}],
            "sources": [{"document_id": document.document_id}],
            "requested_model": "inetcloud-knowledge",
            "used_model": "gemini",
        }
        chats.add_response_message(
            conversation.conversation_id,
            content="Legacy answer",
            response_metadata=metadata,
            is_error=False,
        )
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE datasets DROP COLUMN owner_user_id CASCADE"))
            connection.execute(
                text("ALTER TABLE chat_conversations DROP COLUMN owner_user_id CASCADE")
            )
            connection.execute(
                text("ALTER TABLE datasets ADD CONSTRAINT datasets_name_key UNIQUE(name)")
            )
            connection.execute(
                text("CREATE UNIQUE INDEX uq_datasets_name_ci ON datasets(lower(name))")
            )
        before = legacy_fingerprints(engine)
        with pytest.raises(ValueError, match="must already exist"):
            migrate_ownership(engine, uuid4())
        assert before == legacy_fingerprints(engine)
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT count(*) FROM datasets WHERE owner_user_id IS NULL"))
                == 1
            )
        migrate_ownership(engine, owner)
        assert before == legacy_fingerprints(engine)
        assert chats.get(conversation.conversation_id).messages[-1].response_metadata == metadata
        assert (
            datasets.get(dataset.dataset_id).table.physical_table_name
            == dataset.table.physical_table_name
        )
        migrate_ownership(engine, owner)
        assert before == legacy_fingerprints(engine)
        other = auth.identity("other-owner", "other@example.invalid", "Other")
        DatasetRepository(engine, engine, other).create_workspace("Legacy dataset")
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM chat_conversations c "
                        "JOIN datasets d USING(dataset_id) "
                        "WHERE c.owner_user_id <> d.owner_user_id"
                    )
                )
                == 0
            )
    finally:
        engine.dispose()
        # This exact name was created above; never drop a user-provided database.
        assert name.startswith("shopquery_test_migration_") and len(name) == 57
        with parent.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{name}"'))
