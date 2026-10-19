"""Explicit ownership migration: no application request calls this module."""

from uuid import UUID

from sqlalchemy import Engine, text

from app.database.setup import create_schema

OWNERSHIP_VERSION = "001_user_ownership"


def migrate_ownership(engine: Engine, owner_user_id: UUID) -> None:
    """Assign every legacy resource to an explicitly selected, existing identity."""
    with engine.connect() as guard:
        guard.execute(text("SELECT pg_advisory_lock(71948102)"))
        guard.commit()
        try:
            _apply_ownership(engine, owner_user_id)
        finally:
            guard.execute(text("SELECT pg_advisory_unlock(71948102)"))
            guard.commit()


def _apply_ownership(engine: Engine, owner_user_id: UUID) -> None:
    create_schema(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "owner_user_id UUID NOT NULL)"
            )
        )
        applied = connection.scalar(
            text("SELECT owner_user_id FROM schema_migrations WHERE version = :version"),
            {"version": OWNERSHIP_VERSION},
        )
        if applied:
            if applied != owner_user_id:
                raise ValueError("Migration was already applied with a different explicit owner")
            return
        if not connection.scalar(
            text("SELECT 1 FROM users WHERE user_id = :owner"), {"owner": owner_user_id}
        ):
            raise ValueError("Explicit migration owner must already exist")
        for table in ("datasets", "chat_conversations"):
            connection.execute(
                text(f"UPDATE {table} SET owner_user_id = :owner WHERE owner_user_id IS NULL"),
                {"owner": owner_user_id},
            )
        mismatch = connection.scalar(
            text(
                "SELECT count(*) FROM chat_conversations c JOIN datasets d USING(dataset_id) "
                "WHERE c.owner_user_id <> d.owner_user_id"
            )
        )
        if mismatch:
            raise ValueError("Conversation and dataset ownership mismatch; migration rolled back")
        connection.execute(text("ALTER TABLE datasets DROP CONSTRAINT IF EXISTS datasets_name_key"))
        connection.execute(text("DROP INDEX IF EXISTS uq_datasets_name_ci"))
        for table in ("datasets", "chat_conversations"):
            connection.execute(text(f"ALTER TABLE {table} ALTER COLUMN owner_user_id SET NOT NULL"))
            connection.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS ix_{table}_owner_user_id ON {table}(owner_user_id)"
                )
            )
        connection.execute(
            text("""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_datasets_owner') THEN
                ALTER TABLE datasets ADD CONSTRAINT fk_datasets_owner
                  FOREIGN KEY(owner_user_id) REFERENCES users(user_id);
              END IF;
              IF NOT EXISTS (SELECT 1 FROM pg_constraint
                             WHERE conname='fk_conversations_owner') THEN
                ALTER TABLE chat_conversations ADD CONSTRAINT fk_conversations_owner
                  FOREIGN KEY(owner_user_id) REFERENCES users(user_id);
              END IF;
              IF NOT EXISTS (SELECT 1 FROM pg_constraint
                             WHERE conname='uq_datasets_owner_reference')
              THEN ALTER TABLE datasets ADD CONSTRAINT uq_datasets_owner_reference
                UNIQUE(dataset_id, owner_user_id);
              END IF;
              IF NOT EXISTS (SELECT 1 FROM pg_constraint
                             WHERE conname='fk_conversation_dataset_owner')
              THEN ALTER TABLE chat_conversations ADD CONSTRAINT fk_conversation_dataset_owner
                FOREIGN KEY(dataset_id, owner_user_id)
                REFERENCES datasets(dataset_id, owner_user_id) ON DELETE RESTRICT;
              END IF;
            END $$
        """)
        )
        connection.execute(
            text("INSERT INTO schema_migrations(version, owner_user_id) VALUES (:version, :owner)"),
            {"version": OWNERSHIP_VERSION, "owner": owner_user_id},
        )
