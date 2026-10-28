"""PostgreSQL schema, seed, read-only, and pgvector integration tests."""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.loader import load_seed_csv
from app.database.models import Category, DocumentChunk, Order, OrderItem, Product
from app.database.session import get_readonly_engine, get_setup_engine
from app.database.setup import create_schema
from app.rag.chunking import chunk_document
from app.rag.documents import load_markdown_documents
from app.rag.repository import DocumentRepository
from app.text_to_sql.executor import SqlExecutor, _json_safe
from app.text_to_sql.validator import SqlValidator
from tests.test_sql_validator import VALID_QUERIES


class KeywordEmbedder:
    """Deterministic test vectors; these are not claimed as Gemini embeddings."""

    def embed_document(self, title: str, content: str) -> list[float]:
        return self._vector(f"{title} {content}")

    def embed_query(self, content: str) -> list[float]:
        return self._vector(content)

    @staticmethod
    def _vector(content: str) -> list[float]:
        vector = [0.001] * 768
        lowered = content.lower()
        keywords = ["vận chuyển", "đổi trả", "bảo hành", "doanh thu", "bán chạy"]
        for index, keyword in enumerate(keywords):
            if keyword in lowered:
                vector[index] = 1.0
        return vector


@pytest.fixture(scope="module")
def database() -> Iterator[Engine]:
    settings = get_settings()
    engine = get_setup_engine()
    create_schema(engine)
    load_seed_csv(engine, settings.seed_directory)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM document_chunks"))
    yield engine
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM document_chunks"))


@pytest.mark.integration
def test_schema_counts_constraints_and_revenue(database: Engine) -> None:
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Category)) == 8
        assert session.scalar(select(func.count()).select_from(Product)) == 150
        assert session.scalar(select(func.count()).select_from(Order)) == 2_000
        assert session.scalar(select(func.count()).select_from(OrderItem)) == 4_019
        invalid_statuses = session.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.status.not_in(["pending", "completed", "cancelled"]))
        )
        assert invalid_statuses == 0
        revenue = session.scalar(
            select(func.sum(OrderItem.quantity * OrderItem.unit_price))
            .join(Order)
            .where(Order.status == "completed")
        )
        assert int(revenue) == 151_687_001_000


@pytest.mark.integration
def test_default_factory_plan_revenue_matches_independent_seed_oracle(database, monkeypatch):
    from app.dependencies import _build_chat_service
    from app.text_to_sql.compiler import QueryCompiler
    from app.text_to_sql.query_plan import (
        PlanDecision,
        PlanExpression,
        PlanField,
        PlanFilter,
        PlanSort,
        QueryPlan,
    )
    from app.text_to_sql.schema_context import default_sql_context
    from tests.test_plan_providers import response
    from tests.test_providers import completion, harness
    from tests.test_query_compiler import field, source

    context = default_sql_context()
    compiler = QueryCompiler(context, default_schema=True)
    category = field(compiler, "categories", "category_code")
    decision = PlanDecision(
        plan=QueryPlan(
            source=source(compiler, "order_items"),
            relationships=list(compiler.references.relationships),
            expressions=[
                PlanExpression(
                    operation="multiply",
                    arguments=[
                        field(compiler, "order_items", "quantity"),
                        field(compiler, "order_items", "unit_price"),
                    ],
                ),
                PlanExpression(operation="sum", arguments=["e0"]),
            ],
            fields=[
                PlanField(reference=category, alias="category"),
                PlanField(reference="e1", alias="revenue"),
            ],
            filters=[
                PlanFilter(
                    reference=field(compiler, "orders", "status"),
                    operator="eq",
                    values=["completed"],
                )
            ],
            group_by=[category],
            sort=[PlanSort(field="category")],
        )
    )
    gateway, calls = harness(
        monkeypatch,
        [
            completion('{"route": "SQL", "reason": "Revenue", "evidence_requirement": "tables"}'),
            response("knowledge", decision.model_dump_json()),
        ],
    )
    try:
        result = _build_chat_service(get_settings(), gateway).chat("Revenue per category")
    finally:
        gateway.close()
    with database.connect() as connection:
        oracle = connection.execute(
            text(
                "SELECT c.category_code, SUM(i.quantity*i.unit_price) FROM order_items i "
                "JOIN products p ON p.product_id=i.product_id "
                "JOIN categories c ON c.category_id=p.category_id "
                "JOIN orders o ON o.order_id=i.order_id WHERE o.status='completed' "
                "GROUP BY c.category_code ORDER BY c.category_code"
            )
        ).all()
    assert [(r["category"], Decimal(r["revenue"])) for r in result.rows] == oracle
    assert sum(Decimal(r["revenue"]) for r in result.rows) == 151_687_001_000
    assert len(calls) == 2


@pytest.mark.integration
def test_seed_load_is_idempotent(database: Engine) -> None:
    settings = get_settings()
    first = load_seed_csv(database, settings.seed_directory)
    second = load_seed_csv(database, settings.seed_directory)
    assert (
        first
        == second
        == {
            "categories": 8,
            "products": 150,
            "orders": 2_000,
            "order_items": 4_019,
        }
    )


@pytest.mark.integration
def test_readonly_role_rejects_writes(database: Engine) -> None:
    readonly = get_readonly_engine()
    with readonly.connect() as connection, pytest.raises(DBAPIError):
        connection.execute(text("DELETE FROM orders"))


@pytest.mark.integration
@pytest.mark.parametrize("sql", VALID_QUERIES)
def test_representative_sql_executes_and_matches_reference(database: Engine, sql: str) -> None:
    validated = SqlValidator().validate(sql)
    actual = SqlExecutor(get_readonly_engine(), timeout_ms=5_000, max_rows=200).execute(validated)
    with database.connect() as connection:
        connection.execute(text("SET LOCAL TIME ZONE 'Asia/Ho_Chi_Minh'"))
        expected = [dict(row) for row in connection.execute(text(validated.statement)).mappings()]
    normalized_expected = [
        {key: _json_safe(value) for key, value in row.items()} for row in expected
    ]
    assert actual == normalized_expected


@pytest.mark.integration
def test_pgvector_ingestion_is_idempotent_and_retrieves_shipping(database: Engine) -> None:
    settings = get_settings()
    documents = load_markdown_documents(settings.documents_directory)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    repository = DocumentRepository(database)
    embedder = KeywordEmbedder()

    first = repository.sync(chunks, embedder)
    second = repository.sync(chunks, embedder)
    results = repository.retrieve(embedder.embed_query("miễn phí vận chuyển"), top_k=5)

    assert first == {"total": 25, "embedded": 25, "removed": 0}
    assert second == {"total": 25, "embedded": 0, "removed": 0}
    assert results[0].source_file == "shipping_policy.md"
    with Session(database) as session:
        dimensions = session.scalar(select(func.vector_dims(DocumentChunk.embedding)).limit(1))
        assert dimensions == 768
