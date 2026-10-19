"""Explicit additive JOIN metadata installation; never called by application startup."""

from uuid import UUID

from sqlalchemy import Engine, text

from app.database.models import DatasetRelationship

JOIN_VERSION = "002_confirmed_relationships"


def migrate_relationships(engine: Engine, owner_user_id: UUID | None = None) -> None:
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout='3s'"))
        connection.execute(text("SET LOCAL statement_timeout='30s'"))
        connection.execute(text("SELECT pg_advisory_xact_lock(71948102)"))
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, "
                "applied_at TIMESTAMPTZ NOT NULL DEFAULT now(), owner_user_id UUID)"
            )
        )
        if connection.scalar(
            text("SELECT 1 FROM schema_migrations WHERE version=:version"),
            {"version": JOIN_VERSION},
        ):
            return
        owner_required = connection.scalar(
            text(
                "SELECT is_nullable='NO' FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='schema_migrations' "
                "AND column_name='owner_user_id'"
            )
        )
        if owner_required and owner_user_id is None:
            raise ValueError("Existing migration ledger requires an explicit operator owner UUID")
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_dataset_tables_scope "
                "ON dataset_tables(dataset_table_id, dataset_id)"
            )
        )
        DatasetRelationship.__table__.create(connection, checkfirst=True)
        connection.execute(text("REVOKE ALL ON dataset_relationships FROM shopquery_reader"))
        connection.execute(
            text("INSERT INTO schema_migrations(version, owner_user_id) VALUES(:version,:owner)"),
            {"version": JOIN_VERSION, "owner": owner_user_id},
        )
