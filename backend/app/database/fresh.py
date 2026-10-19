"""Explicit fresh installation, without demo records or a synthetic owner."""

from sqlalchemy import Engine, text

from app.database.setup import create_schema

FRESH_VERSION = "001_fresh_install"


def initialize_fresh_database(engine: Engine) -> None:
    """Refuse existing schemas; repeated completed installs never alter user data."""
    with engine.connect() as guard:
        guard.execute(text("SELECT pg_advisory_lock(71948102)"))
        guard.commit()
        try:
            marker = guard.scalar(text("SELECT to_regclass('public.schema_migrations')"))
            if marker and guard.scalar(
                text("SELECT 1 FROM schema_migrations WHERE version = :version"),
                {"version": FRESH_VERSION},
            ):
                return
            if guard.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_tables "
                    "WHERE schemaname IN ('public', 'uploaded_data'))"
                )
            ):
                raise ValueError(
                    "Fresh installation requires a database without application tables"
                )
            guard.commit()
            create_schema(engine)
            with engine.begin() as connection:
                connection.execute(
                    text("""
                    ALTER TABLE datasets ADD CONSTRAINT uq_datasets_owner_reference
                      UNIQUE(dataset_id, owner_user_id);
                    ALTER TABLE chat_conversations
                      ADD CONSTRAINT fk_conversation_dataset_owner
                      FOREIGN KEY(dataset_id, owner_user_id)
                      REFERENCES datasets(dataset_id, owner_user_id) ON DELETE RESTRICT;
                    CREATE TABLE schema_migrations (
                      version TEXT PRIMARY KEY,
                      applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                      owner_user_id UUID
                    );
                    REVOKE ALL ON schema_migrations FROM shopquery_reader;
                """)
                )
                connection.execute(
                    text("INSERT INTO schema_migrations(version) VALUES (:version)"),
                    {"version": FRESH_VERSION},
                )
        finally:
            guard.execute(text("SELECT pg_advisory_unlock(71948102)"))
            guard.commit()
