"""Authenticated context and guarded SQL run only on disposable PostgreSQL."""

from decimal import Decimal
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import ResourceConflictError, ResourceNotFoundError
from app.database.session import get_readonly_engine, get_setup_engine
from app.datasets.relationship_repository import RelationshipRepository
from app.datasets.relationships import RelationshipConfirm, RelationshipInput
from app.datasets.repository import DatasetRepository
from app.dependencies import build_dataset_chat_service, build_workspace_context
from app.routing.router import RouteDecision, RouteLabel
from app.text_to_sql.generator import SqlDraft
from app.text_to_sql.pipeline import TextToSqlPipeline
from app.text_to_sql.validator import SqlValidator
from tests.auth_helpers import TEST_OWNER
from tests.test_dataset_parser import parse

pytestmark = pytest.mark.integration


@pytest.fixture(params=[False, True], ids=["workspace5-shape", "null-decimal-bigint"])
def authenticated_workspace(request):
    edge = request.param
    repository = DatasetRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
    dataset = repository.create_workspace("Synthetic JOIN order " + uuid4().hex)
    try:
        students = "Id,Name\n101,An\n102,Binh\n"
        payments = "Id,Student id,Amount\n1,101,20.00\n2,101,30.00\n3,102,0.00\n"
        if edge:
            students += "9007199254740993,Unknown\n"
            payments += (
                "4,9007199254740993,\n5,101,0.00\n9007199254740993,101,12345678901234567890.12\n"
            )
        dataset = repository.add_table(dataset.dataset_id, parse("students.csv", students.encode()))
        dataset = repository.add_table(dataset.dataset_id, parse("payments.csv", payments.encode()))
        dimension, fact = dataset.tables
        relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
        relation = RelationshipInput(
            source_table_id=str(fact.dataset_table_id),
            source_column="student_id",
            target_table_id=str(dimension.dataset_table_id),
            target_column="id",
        )
        preview = relations.preview(dataset.dataset_id, relation)
        assert preview.valid and preview.source_rows == (6 if edge else 3)
        record = relations.confirm(
            dataset.dataset_id,
            RelationshipConfirm(**relation.model_dump(), revision=preview.revision, confirmed=True),
        )
        settings = get_settings().model_copy(update={"sql_join_v1_enabled": True})
        context = build_workspace_context(settings, dataset, repository)
        yield repository, dataset, relations, record, settings, context
    finally:
        repository.delete(dataset.dataset_id, delete_conversations=True)


def join_validator(context) -> SqlValidator:
    return SqlValidator(
        context.table_columns,
        context.allowed_schemas,
        max_tables=2,
        approved_joins=context.approved_joins,
        column_types=context.column_types,
        join_v1_enabled=True,
    )


def statements(dataset) -> tuple[str, str]:
    dimension, fact = dataset.tables
    projection = (
        "SELECT s.id AS student_id, s.name, SUM(p.amount) AS total, "
        "AVG(p.amount) AS average, COUNT(*) AS fact_row_count, "
        "COUNT(p.amount) AS fact_value_count "
    )
    forward = (
        f"FROM uploaded_data.{fact.physical_table_name} p "
        f"INNER JOIN uploaded_data.{dimension.physical_table_name} s "
    )
    reverse = (
        f"FROM uploaded_data.{dimension.physical_table_name} s "
        f"INNER JOIN uploaded_data.{fact.physical_table_name} p "
    )
    suffix = "ON p.student_id=s.id GROUP BY s.id,s.name ORDER BY s.id"
    return projection + forward + suffix, projection + reverse + suffix


@pytest.mark.parametrize("model", ["gemini", "inetcloud-knowledge"])
def test_reverse_draft_matches_postgres_oracle_through_authenticated_context(
    authenticated_workspace,
    monkeypatch,
    model: str,
) -> None:
    _, dataset, _, _, settings, context = authenticated_workspace
    forward, reverse = statements(dataset)
    with get_setup_engine().connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        original = connection.execute(text(reverse)).mappings().all()
        assert original == connection.execute(text(forward)).mappings().all()
        fact = dataset.tables[1].physical_table_name
        oracle = {
            str(row.student_id): row
            for row in connection.execute(
                text(
                    "SELECT student_id, SUM(amount) AS total, AVG(amount) AS average, "
                    "COUNT(*) AS n, COUNT(amount) AS measured "
                    f"FROM uploaded_data.{fact} GROUP BY student_id"
                )
            )
        }
    print("PostgreSQL raw INNER order equivalence and independent fact oracle: PASS")
    calls = []

    class Gateway:
        def generate_structured(self, prompt, schema):
            calls.append(schema.__name__)
            if schema is RouteDecision:
                assert context.routing_context in prompt
                return RouteDecision(route=RouteLabel.SQL, reason="Synthetic contract")
            assert schema is SqlDraft and context.schema_context in prompt
            return SqlDraft(sql=reverse)

        def generate_text(self, prompt):
            calls.append("answer")
            assert '"total": "0.00"' in prompt
            return "Synthetic rows only"

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    response = build_dataset_chat_service(
        settings.model_copy(update={"ai_default_model": model}), context
    ).chat("Tổng và trung bình thanh toán theo học viên")
    assert calls == ["RouteDecision", "SqlDraft", "answer"]
    assert response.route == RouteLabel.SQL and response.used_model == model
    assert not response.fallback_used
    assert response.sql.startswith("SELECT")
    for row in response.rows:
        expected = oracle[str(row["student_id"])]
        assert row["fact_row_count"] == expected.n
        assert row["fact_value_count"] == expected.measured
        assert (None if row["total"] is None else Decimal(row["total"])) == expected.total
        assert (None if row["average"] is None else Decimal(row["average"])) == expected.average
        if expected.student_id > 9_007_199_254_740_991:
            assert row["student_id"] == "9007199254740993" and row["total"] is None
    canonical = join_validator(context).validate(reverse)
    assert canonical.fact_table == dataset.tables[1].physical_table_name
    assert canonical.relationship_id == context.approved_joins[0].relationship_id


def test_normalized_query_still_uses_owner_workspace_and_revocation_guard(
    authenticated_workspace,
) -> None:
    repository, dataset, relations, record, _, context = authenticated_workspace
    _, reverse = statements(dataset)
    validated = join_validator(context).validate(reverse)
    approved = context.approved_joins
    with (
        pytest.raises(ResourceNotFoundError),
        RelationshipRepository(get_setup_engine(), uuid4()).execution_guard(
            dataset.dataset_id, approved, validated
        ),
    ):
        pytest.fail("Foreign owner reached execution")
    other = repository.create_workspace("Synthetic other scope " + uuid4().hex)
    try:
        with (
            pytest.raises(ResourceConflictError),
            relations.execution_guard(other.dataset_id, approved, validated),
        ):
            pytest.fail("Foreign workspace reached execution")
    finally:
        repository.delete(other.dataset_id)
    relations.delete(dataset.dataset_id, UUID(record.relationship_id))
    executor, gateway = Mock(), Mock()
    pipeline = TextToSqlPipeline(
        Mock(generate=Mock(return_value=reverse)),
        join_validator(context),
        executor,
        gateway,
        execution_guard=lambda sql: relations.execution_guard(dataset.dataset_id, approved, sql),
    )
    with pytest.raises(ResourceConflictError):
        pipeline.run("Synthetic stale request")
    executor.execute.assert_not_called()
    gateway.generate_text.assert_not_called()
