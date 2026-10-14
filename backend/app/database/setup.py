"""Idempotent database schema setup."""

from sqlalchemy import Engine, text

from app.database.models import Base


def create_schema(engine: Engine) -> None:
    """Create pgvector, application tables, and reader grants if absent."""

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS uploaded_data"))
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_datasets_name_ci "
                "ON datasets (lower(name))"
            )
        )
        connection.execute(text("GRANT USAGE ON SCHEMA public TO shopquery_reader"))
        connection.execute(text("GRANT USAGE ON SCHEMA uploaded_data TO shopquery_reader"))
        connection.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO shopquery_reader"))
        connection.execute(
            text("GRANT SELECT ON ALL TABLES IN SCHEMA uploaded_data TO shopquery_reader")
        )
        connection.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA uploaded_data "
                "GRANT SELECT ON TABLES TO shopquery_reader"
            )
        )
