"""Read-only fingerprints for ownership migration rehearsals."""

import hashlib

from sqlalchemy import Engine, text

LEGACY_TABLES = (
    "categories",
    "products",
    "orders",
    "order_items",
    "datasets",
    "dataset_tables",
    "dataset_documents",
    "document_chunks",
    "chat_conversations",
    "chat_messages",
)


def legacy_fingerprints(engine: Engine) -> dict[str, dict[str, int | str]]:
    result = {}
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL statement_timeout = '30s'"))
        names = [("public", name) for name in LEGACY_TABLES]
        names.extend(
            ("uploaded_data", name)
            for name in connection.scalars(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname='uploaded_data' ORDER BY tablename"
                )
            )
        )
        quote = engine.dialect.identifier_preparer.quote
        for schema, name in names:
            digest, count = hashlib.sha256(), 0
            statement = text(
                f"SELECT (to_jsonb(t) - 'owner_user_id')::text "
                f"FROM {quote(schema)}.{quote(name)} t ORDER BY 1"
            )
            for row in connection.scalars(statement):
                digest.update(row.encode())
                digest.update(b"\n")
                count += 1
            result[f"{schema}.{name}"] = {"count": count, "sha256": digest.hexdigest()}
    return result
