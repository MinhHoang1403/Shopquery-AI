"""Idempotent database schema setup."""

from sqlalchemy import Connection, Engine, text

from app.database.models import Base


def create_schema(engine: Engine) -> None:
    """Create pgvector, application tables, and reader grants if absent."""

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS uploaded_data"))
        _prepare_legacy_schema(connection)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        _finish_workspace_schema(connection)
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_datasets_owner_name_ci "
                "ON datasets (owner_user_id, lower(name))"
            )
        )
        connection.execute(text("GRANT USAGE ON SCHEMA public TO shopquery_reader"))
        connection.execute(text("GRANT USAGE ON SCHEMA uploaded_data TO shopquery_reader"))
        connection.execute(
            text(
                "GRANT SELECT ON categories, products, orders, order_items, datasets, "
                "dataset_tables, dataset_documents, document_chunks TO shopquery_reader"
            )
        )
        connection.execute(
            text(
                "REVOKE ALL ON users, user_sessions, oidc_flows, resource_limits, resource_leases, "
                "chat_conversations, chat_messages "
                "FROM shopquery_reader"
            )
        )
        connection.execute(
            text("GRANT SELECT ON ALL TABLES IN SCHEMA uploaded_data TO shopquery_reader")
        )
        connection.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA uploaded_data "
                "GRANT SELECT ON TABLES TO shopquery_reader"
            )
        )


def _prepare_legacy_schema(connection: Connection) -> None:
    """Add columns required before SQLAlchemy creates dependent objects."""

    connection.execute(
        text(
            """
            DO $$
            BEGIN
              IF to_regclass('public.chat_conversations') IS NOT NULL THEN
                ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS model_id VARCHAR(40);
                ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS owner_user_id UUID;
              END IF;
              IF to_regclass('public.datasets') IS NOT NULL THEN
                ALTER TABLE datasets ADD COLUMN IF NOT EXISTS owner_user_id UUID;
                ALTER TABLE datasets ALTER COLUMN original_filename DROP NOT NULL;
                ALTER TABLE datasets ALTER COLUMN file_type DROP NOT NULL;
                ALTER TABLE datasets ALTER COLUMN row_count DROP NOT NULL;
                ALTER TABLE datasets ALTER COLUMN column_count DROP NOT NULL;
              END IF;
              IF to_regclass('public.dataset_tables') IS NOT NULL THEN
                ALTER TABLE dataset_tables
                  ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255),
                  ADD COLUMN IF NOT EXISTS file_type VARCHAR(10);
                UPDATE dataset_tables AS dt
                SET original_filename = d.original_filename,
                    file_type = d.file_type
                FROM datasets AS d
                WHERE dt.dataset_id = d.dataset_id
                  AND (dt.original_filename IS NULL OR dt.file_type IS NULL);
                ALTER TABLE dataset_tables ALTER COLUMN original_filename SET NOT NULL;
                ALTER TABLE dataset_tables ALTER COLUMN file_type SET NOT NULL;
              END IF;
              IF to_regclass('public.document_chunks') IS NOT NULL THEN
                ALTER TABLE document_chunks
                  ADD COLUMN IF NOT EXISTS dataset_id INTEGER,
                  ADD COLUMN IF NOT EXISTS dataset_document_id INTEGER;
              END IF;
            END $$;
            """
        )
    )


def _finish_workspace_schema(connection: Connection) -> None:
    """Create constraints and indexes that create_all cannot add to old tables."""

    connection.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_dataset_tables_name_ci
              ON dataset_tables (dataset_id, lower(display_name));
            CREATE INDEX IF NOT EXISTS ix_document_chunks_dataset_id
              ON document_chunks (dataset_id);
            CREATE INDEX IF NOT EXISTS ix_document_chunks_document_id
              ON document_chunks (dataset_document_id);
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_document_chunks_scope'
              ) THEN
                ALTER TABLE document_chunks ADD CONSTRAINT ck_document_chunks_scope
                  CHECK ((dataset_id IS NULL AND dataset_document_id IS NULL) OR
                         (dataset_id IS NOT NULL AND dataset_document_id IS NOT NULL));
              END IF;
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_document_chunks_document_scope'
              ) THEN
                ALTER TABLE document_chunks
                  ADD CONSTRAINT fk_document_chunks_document_scope
                  FOREIGN KEY (dataset_document_id, dataset_id)
                  REFERENCES dataset_documents (document_id, dataset_id)
                  ON DELETE CASCADE;
              END IF;
            END $$;
            """
        )
    )
