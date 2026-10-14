"""Idempotent database schema setup."""

from sqlalchemy import Engine, text

from app.database.models import Base


def create_schema(engine: Engine) -> None:
    """Create pgvector, application tables, and reader grants if absent."""

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("GRANT USAGE ON SCHEMA public TO shopquery_reader"))
        connection.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO shopquery_reader"))
