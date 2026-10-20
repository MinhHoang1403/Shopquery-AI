"""Authenticated context and guarded SQL run only on disposable PostgreSQL."""

from decimal import Decimal
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import ResourceConflictError, ResourceNotFoundError, SqlUnsupportedError
from app.database.session import get_readonly_engine, get_setup_engine
from app.datasets.relationship_repository import RelationshipRepository
from app.datasets.relationships import RelationshipConfirm, RelationshipInput
from app.datasets.repository import DatasetRepository
from app.dependencies import build_dataset_chat_service, build_workspace_context
from app.routing.router import RouteDecision, RouteLabel
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.generator import SqlDraft, SqlGenerator
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
            assert "fact_value_count counts non-NULL values" in prompt
            assert "Neither counts dimension entities" in prompt
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


@pytest.fixture
def aggregate_workspace():
    repository = DatasetRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
    dataset = repository.create_workspace("Synthetic aggregate semantics " + uuid4().hex)
    try:
        dataset = repository.add_table(
            dataset.dataset_id,
            parse("students.csv", b"Id,Name,Fee\n101,An,99.00\n102,Binh,100.00\n103,Null,900.00\n"),
        )
        dataset = repository.add_table(
            dataset.dataset_id,
            parse(
                "payments.csv",
                (
                    b"Id,Student id,Amount,Units\n1,101,20.00,1\n,101,,2\n3,102,0.00,0\n"
                    b"4,103,,3\n5,101,12345678901234567890.12,9007199254740993\n"
                ),
            ),
        )
        dimension, fact = dataset.tables
        with get_setup_engine().begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE uploaded_data.{fact.physical_table_name} "
                    "ALTER COLUMN units SET NOT NULL"
                )
            )
            constraints = dict(
                connection.execute(
                    text(
                        "SELECT attname, attnotnull FROM pg_attribute "
                        "WHERE attrelid=to_regclass(:table) AND attname IN ('id','units')"
                    ),
                    {"table": f"uploaded_data.{fact.physical_table_name}"},
                ).all()
            )
            assert constraints == {"id": False, "units": True}
            counts = connection.execute(
                text(
                    f"SELECT COUNT(*),COUNT(id),COUNT(units),COUNT(student_id) "
                    f"FROM uploaded_data.{fact.physical_table_name}"
                )
            ).one()
            assert tuple(counts) == (5, 4, 5, 5)
        relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
        relation = RelationshipInput(
            source_table_id=str(fact.dataset_table_id),
            source_column="student_id",
            target_table_id=str(dimension.dataset_table_id),
            target_column="id",
        )
        preview = relations.preview(dataset.dataset_id, relation)
        assert preview.valid
        relations.confirm(
            dataset.dataset_id,
            RelationshipConfirm(**relation.model_dump(), revision=preview.revision, confirmed=True),
        )
        settings = get_settings().model_copy(update={"sql_join_v1_enabled": True})
        yield dataset, relations, build_workspace_context(settings, dataset, repository)
    finally:
        repository.delete(dataset.dataset_id, delete_conversations=True)


@pytest.mark.parametrize("reverse", [False, True], ids=["fact-first", "dimension-first"])
@pytest.mark.parametrize(
    "projection,oracle,grouped,student,code",
    [
        ("COUNT(*) AS fact_row_count", "COUNT(*) AS fact_row_count", True, None, None),
        ("COUNT(*) AS matched_row_count", "COUNT(*) AS matched_row_count", False, None, None),
        ("COUNT(p.id) AS fact_row_count", None, False, None, "join_aggregate"),
        ("COUNT(p.units) AS fact_row_count", None, False, None, "join_aggregate"),
        ("COUNT(p.student_id) AS fact_row_count", None, False, None, "join_aggregate"),
        (
            "COUNT(p.student_id) AS fact_value_count",
            "COUNT(student_id) AS fact_value_count",
            True,
            None,
            None,
        ),
        (
            "COUNT(p.amount) AS fact_value_count",
            "COUNT(amount) AS fact_value_count",
            True,
            None,
            None,
        ),
        ("COUNT(p.amount) AS fact_row_count", None, False, None, "join_aggregate"),
        ("COUNT(*) AS fact_value_count", None, False, None, "join_aggregate"),
        ("COUNT(s.id) AS fact_row_count", None, False, None, "join_aggregate"),
        ("COUNT(DISTINCT p.id) AS fact_value_count", None, False, None, "join_aggregate"),
        (
            "COUNT(p.amount) AS fact_value_count",
            "COUNT(amount) AS fact_value_count",
            False,
            103,
            None,
        ),
        ("COUNT(p.id) AS fact_value_count", "COUNT(id) AS fact_value_count", True, None, None),
        ("SUM(p.amount) AS total", "SUM(amount) AS total", True, None, None),
        ("AVG(p.amount) AS average", "AVG(amount) AS average", True, None, None),
        ("SUM(p.units) AS total", "SUM(units) AS total", True, None, None),
        ("AVG(p.units) AS average", "AVG(units) AS average", True, None, None),
        ("SUM(s.fee) AS total", None, False, None, "join_aggregate"),
        ("AVG(s.fee) AS average", None, False, None, "join_aggregate"),
        (
            "SUM(p.amount) AS total, COUNT(*) AS matched_row_count",
            "SUM(amount) AS total, COUNT(*) AS matched_row_count",
            False,
            102,
            None,
        ),
        (
            "AVG(p.amount) AS average, COUNT(*) AS matched_row_count",
            "AVG(amount) AS average, COUNT(*) AS matched_row_count",
            False,
            103,
            None,
        ),
        (
            "SUM(p.amount) AS total, AVG(p.amount) AS average, COUNT(*) AS matched_row_count",
            "SUM(amount) AS total, AVG(amount) AS average, COUNT(*) AS matched_row_count",
            False,
            999,
            None,
        ),
        ("SUM(p.amount * p.units) AS total", None, False, None, "join_aggregate"),
        ("SUM(p.amount) / COUNT(*) AS average", None, False, None, "join_aggregate"),
        ("SUM(CAST(p.amount AS DOUBLE PRECISION)) AS total", None, False, None, "join_aggregate"),
        ("SUM(p.amount) FILTER(WHERE p.amount>0) AS total", None, False, None, "join_aggregate"),
        (
            "SUM(p.amount) AS total, AVG(p.amount) AS average, COUNT(*) AS fact_row_count, "
            "COUNT(p.amount) AS fact_value_count",
            "SUM(amount) AS total, AVG(amount) AS average, COUNT(*) AS fact_row_count, "
            "COUNT(amount) AS fact_value_count",
            True,
            None,
            None,
        ),
    ],
)
def test_aggregate_drafts_guarded_execution_and_independent_fact_oracle(
    aggregate_workspace,
    reverse: bool,
    projection: str,
    oracle: str | None,
    grouped: bool,
    student: int | None,
    code: str | None,
) -> None:
    dataset, relations, context = aggregate_workspace
    dimension, fact = dataset.tables
    fact_binding = f"uploaded_data.{fact.physical_table_name} p"
    dimension_binding = f"uploaded_data.{dimension.physical_table_name} s"
    first, second = (
        (dimension_binding, fact_binding) if reverse else (fact_binding, dimension_binding)
    )
    sql = (
        f"SELECT {'s.id AS student_id, ' if grouped else ''}{projection} "
        f"FROM {first} INNER JOIN {second} ON p.student_id=s.id"
        + (f" WHERE p.student_id={student}" if student is not None else "")
        + (" GROUP BY s.id ORDER BY s.id" if grouped else "")
    )
    gateway = Mock()
    gateway.generate_structured.return_value = SqlDraft(sql=sql)
    gateway.generate_text.return_value = "Synthetic aggregate evidence only"
    executor = Mock(wraps=SqlExecutor(get_readonly_engine(), 1000, 100))
    guard = Mock(
        side_effect=lambda validated: relations.execution_guard(
            dataset.dataset_id, context.approved_joins, validated
        )
    )
    pipeline = TextToSqlPipeline(
        SqlGenerator(gateway, "2026-10-20", context.schema_context),
        join_validator(context),
        executor,
        gateway,
        execution_guard=guard,
    )
    if code:
        with pytest.raises(SqlUnsupportedError) as error:
            pipeline.run("Synthetic aggregate variant")
        assert error.value.code == code
        guard.assert_not_called()
        executor.execute.assert_not_called()
        gateway.generate_text.assert_not_called()
        return
    result = pipeline.run("Synthetic aggregate variant")
    guard.assert_called_once()
    executor.execute.assert_called_once()
    assert result.fact_table == fact.physical_table_name
    oracle_sql = (
        f"SELECT {'student_id, ' if grouped else ''}{oracle} "
        f"FROM uploaded_data.{fact.physical_table_name}"
        + (f" WHERE student_id={student}" if student is not None else "")
        + (" GROUP BY student_id ORDER BY student_id" if grouped else "")
    )
    with get_setup_engine().connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        expected = connection.execute(text(oracle_sql)).mappings().all()
    assert len(result.rows) == len(expected)
    for actual, row in zip(result.rows, expected, strict=True):
        assert actual.keys() == row.keys()
        for key, value in row.items():
            if isinstance(value, Decimal):
                assert actual[key] == format(value, "f")
            elif isinstance(value, int) and abs(value) > 9_007_199_254_740_991:
                assert actual[key] == str(value)
            else:
                assert actual[key] == value
    prompt = gateway.generate_text.call_args.args[0]
    assert "fact_value_count counts non-NULL values" in prompt
    assert "only JSON null means null" in prompt


@pytest.mark.parametrize(
    "case,code",
    [
        ("reversed", None),
        ("recorded-count-id", "join_aggregate"),
        ("canonical-count", None),
        ("wrong-key", "join_key"),
        ("dimension-sum", "join_aggregate"),
        ("missing-relation", "join_relationship"),
    ],
)
def test_recorded_synthetic_draft_replay(authenticated_workspace, case: str, code: str | None):
    _, dataset, relations, _, _, context = authenticated_workspace
    forward, reverse = statements(dataset)
    draft = reverse if case == "reversed" else forward
    if case == "recorded-count-id":
        dimension, fact = dataset.tables
        draft = (
            "SELECT d.name AS name, SUM(f.amount) AS total, COUNT(f.id) AS fact_row_count "
            f"FROM uploaded_data.{fact.physical_table_name} AS f "
            f"INNER JOIN uploaded_data.{dimension.physical_table_name} AS d "
            "ON f.student_id = d.id GROUP BY d.name ORDER BY d.name"
        )
    elif case == "wrong-key":
        draft = draft.replace("p.student_id=s.id", "p.id=s.id")
    elif case == "dimension-sum":
        draft = draft.replace("SUM(p.amount)", "SUM(s.id)")
    if case == "missing-relation":
        from dataclasses import replace

        context = replace(context, approved_joins=())
    gateway = Mock()
    gateway.generate_structured.return_value = SqlDraft(sql=draft)
    executor = Mock(wraps=SqlExecutor(get_readonly_engine(), 1000, 100))
    guard = Mock(
        side_effect=lambda validated: relations.execution_guard(
            dataset.dataset_id, context.approved_joins, validated
        )
    )
    pipeline = TextToSqlPipeline(
        SqlGenerator(gateway, "2026-10-20", context.schema_context),
        join_validator(context),
        executor,
        gateway,
        execution_guard=guard,
    )
    if code:
        with pytest.raises(SqlUnsupportedError) as error:
            pipeline.run("Synthetic captured draft replay")
        assert error.value.code == code
        guard.assert_not_called()
        executor.execute.assert_not_called()
        gateway.generate_text.assert_not_called()
    else:
        result = pipeline.run("Synthetic captured draft replay")
        with get_setup_engine().connect() as connection:
            oracle = connection.execute(
                text(
                    f"SELECT student_id,SUM(amount) AS total,AVG(amount) AS average,COUNT(*) AS n, "
                    "COUNT(amount) AS measured FROM uploaded_data."
                    f"{dataset.tables[1].physical_table_name} "
                    "GROUP BY student_id ORDER BY student_id"
                )
            ).all()
        assert len(result.rows) == len(oracle)
        for row, expected in zip(result.rows, oracle, strict=True):
            assert int(row["student_id"]) == expected.student_id
            assert row["total"] == (None if expected.total is None else format(expected.total, "f"))
            assert row["average"] == (
                None if expected.average is None else format(expected.average, "f")
            )
            assert (row["fact_row_count"], row["fact_value_count"]) == (
                expected.n,
                expected.measured,
            )
        guard.assert_called_once()
        executor.execute.assert_called_once()


def test_database_proven_not_null_id_does_not_silently_rewrite_count(aggregate_workspace):
    dataset, _, context = aggregate_workspace
    dimension, fact = dataset.tables
    table = f"uploaded_data.{fact.physical_table_name}"
    with get_setup_engine().begin() as connection:
        connection.execute(text(f"UPDATE {table} SET id=999 WHERE id IS NULL"))
        connection.execute(text(f"ALTER TABLE {table} ALTER COLUMN id SET NOT NULL"))
        assert (
            connection.scalar(
                text(
                    "SELECT attnotnull FROM pg_attribute WHERE attrelid=to_regclass(:table) "
                    "AND attname='id'"
                ),
                {"table": table},
            )
            is True
        )
        assert tuple(connection.execute(text(f"SELECT COUNT(*),COUNT(id) FROM {table}")).one()) == (
            5,
            5,
        )
    sql = (
        f"SELECT COUNT(p.id) AS fact_row_count FROM {table} p "
        f"INNER JOIN uploaded_data.{dimension.physical_table_name} s ON p.student_id=s.id"
    )
    with pytest.raises(SqlUnsupportedError) as error:
        join_validator(context).validate(sql)
    assert error.value.code == "join_aggregate"
    validated = join_validator(context).validate(sql.replace("fact_row_count", "fact_value_count"))
    assert "COUNT(p.id)" in validated.statement  # No extra COUNT canonicalizer is enabled.
