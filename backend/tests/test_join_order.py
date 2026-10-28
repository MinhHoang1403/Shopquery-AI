"""Synthetic authenticated metadata reproduces JOIN order and error classification."""

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

import pytest
from sqlglot import exp, parse_one

from app.core.errors import SqlUnsupportedError, SqlValidationError
from app.datasets.context import DatasetSqlContext, build_dataset_sql_context
from app.datasets.parser import ColumnSpec
from app.datasets.repository import DatasetInfo, DatasetTableInfo
from app.routing.router import RouteDecision, RouteLabel
from app.routing.service import DatasetChatService, _sql_refusal
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.join_policy import ApprovedJoin, validate_uploaded_join
from app.text_to_sql.planner import QueryPlanner
from app.text_to_sql.query_plan import PlanDecision
from app.text_to_sql.validator import SqlValidator
from tests.plan_fixtures import decision_from_sql
from tests.sql_validation_fixtures import FixtureGenerator, SqlFixture, ValidationPipeline

DIMENSION = "dataset_11111111111111111111111111111111"
FACT = "dataset_22222222222222222222222222222222"
RELATION = ApprovedJoin("synthetic", FACT, "student_id", DIMENSION, "id", "revision")
FORWARD = f"FROM uploaded_data.{FACT} p INNER JOIN uploaded_data.{DIMENSION} s ON p.student_id=s.id"
REVERSE = f"FROM uploaded_data.{DIMENSION} s INNER JOIN uploaded_data.{FACT} p ON p.student_id=s.id"


def authenticated_context() -> DatasetSqlContext:
    dimension = DatasetTableInfo(
        "students",
        None,
        DIMENSION,
        (ColumnSpec("Id", "id", "BIGINT"), ColumnSpec("Name", "name", "TEXT")),
        2,
        original_filename="students.csv",
        dataset_table_id=9,
    )
    fact = DatasetTableInfo(
        "payments",
        None,
        FACT,
        (
            ColumnSpec("Id", "id", "BIGINT"),
            ColumnSpec("Student id", "student_id", "BIGINT"),
            ColumnSpec("Amount", "amount", "NUMERIC"),
        ),
        3,
        original_filename="payments.csv",
        dataset_table_id=10,
    )
    return build_dataset_sql_context(
        DatasetInfo(
            5,
            "Synthetic JOIN order",
            None,
            None,
            None,
            None,
            datetime(2026, 10, 20, tzinfo=UTC),
            dimension,
            tables=(dimension, fact),
            owner_user_id=UUID(int=101),
        ),
        approved_joins=(RELATION,),
        join_v1_enabled=True,
    )


def validator(relationships: tuple[ApprovedJoin, ...] = (RELATION,)) -> SqlValidator:
    context = authenticated_context()
    return SqlValidator(
        context.table_columns,
        context.allowed_schemas,
        max_tables=2,
        approved_joins=relationships,
        column_types=context.column_types,
        join_v1_enabled=True,
    )


@pytest.mark.parametrize(
    "sql,relationships,code",
    [
        (f"SELECT SUM(p.amount) {REVERSE}", (RELATION,), "join_direction"),
        (
            f"SELECT SUM(p.amount) {REVERSE.replace('p.student_id=s.id', 'p.id=s.id')}",
            (RELATION,),
            "join_key",
        ),
        (f"SELECT SUM(s.id) {FORWARD}", (RELATION,), "join_aggregate"),
        (f"SELECT SUM(p.amount) {FORWARD}", (), "join_relationship"),
        (f"SELECT SUM(p.amount) {FORWARD}", (RELATION, RELATION), "join_relationship"),
    ],
)
def test_policy_distinguishes_direction_key_aggregate_and_missing_relation(
    sql: str,
    relationships: tuple[ApprovedJoin, ...],
    code: str,
) -> None:
    context = authenticated_context()
    root = parse_one(sql, read="postgres")
    aliases = {table.alias: table.name for table in root.find_all(exp.Table)}
    with pytest.raises(SqlUnsupportedError) as error:
        validate_uploaded_join(
            root, aliases, relationships, context.column_types, context.table_columns
        )
    assert error.value.code == code


@pytest.mark.parametrize(
    "suffix", [FORWARD, REVERSE, REVERSE.replace("p.student_id=s.id", "(s.id=p.student_id)")]
)
def test_equivalent_inner_join_draft_is_canonicalized_without_changing_aliases(suffix: str) -> None:
    draft = SqlFixture(
        sql="SELECT s.name, SUM(p.amount) AS total, AVG(p.amount) AS average, "
        "COUNT(*) AS fact_row_count " + suffix + " GROUP BY s.id,s.name ORDER BY s.name"
    )
    gateway = Mock()
    gateway.generate_structured.return_value = draft
    generated = FixtureGenerator(gateway, "2026-10-20", authenticated_context().schema_context)
    validated = validator().validate(generated.generate("Synthetic students/payments"))
    root = parse_one(validated.statement, read="postgres")
    assert root.args["from_"].this.name == FACT
    assert root.args["from_"].this.alias == "p"
    assert root.args["joins"][0].this.name == DIMENSION
    assert validated.fact_table == FACT and validated.relationship_id == RELATION.relationship_id
    assert validated.tables == frozenset({FACT, DIMENSION})
    assert validator().validate(validated.statement) == validated
    assert draft.sql.endswith("GROUP BY s.id,s.name ORDER BY s.name")


def test_fact_identity_does_not_depend_on_alias_spelling() -> None:
    result = validator().validate(
        f"SELECT SUM(d.amount) AS total FROM uploaded_data.{DIMENSION} f "
        f"INNER JOIN uploaded_data.{FACT} d ON d.student_id=f.id"
    )
    assert result.fact_table == FACT
    assert f"FROM uploaded_data.{FACT} AS d INNER JOIN uploaded_data.{DIMENSION} AS f" in (
        result.statement
    )


@pytest.mark.parametrize("bindings", [FORWARD, REVERSE])
@pytest.mark.parametrize("alias", ["fact_row_count", "matched_row_count"])
def test_count_verified_fact_join_key_has_row_semantics(bindings, alias):
    result = validator().validate(f"SELECT COUNT(p.student_id) AS {alias} {bindings}")
    assert f"COUNT(p.student_id) AS {alias}" in result.statement
    assert result.count_metrics[0].kind.value == "row_count"
    assert result.relationship_id == RELATION.relationship_id
    assert validator().validate(result.statement) == result
    assert result.fact_table == FACT


@pytest.mark.parametrize(
    "projection",
    [
        "SUM(s.id)",
        "AVG(s.id)",
        "COUNT(s.id) AS fact_value_count",
        "COUNT(p.id) AS fact_row_count",
        "SUM(p.name)",
        "SUM(x.amount)",
    ],
)
def test_reversed_join_never_relabels_dimension_or_invalid_alias_as_fact(projection: str) -> None:
    executor, gateway = Mock(), Mock()
    pipeline = ValidationPipeline(
        Mock(generate=Mock(return_value=f"SELECT {projection} {REVERSE}")),
        validator(),
        executor,
        gateway,
    )
    with pytest.raises(SqlValidationError):
        pipeline.run("Synthetic negative")
    executor.execute.assert_not_called()
    gateway.generate_text.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        lambda sql: sql.replace("p.student_id=s.id", "p.id=s.id"),
        lambda sql: sql.replace("p.student_id=s.id", "p.student_id=s.id OR 1=1"),
        lambda sql: sql.replace("p.student_id=s.id", "p.student_id=s.id AND p.amount>0"),
        lambda sql: sql.replace("INNER JOIN", "LEFT JOIN"),
        lambda sql: sql.replace("INNER JOIN", "CROSS JOIN"),
        lambda sql: sql.replace("p ON", "s ON"),
        lambda sql: sql.replace("uploaded_data.", "public.", 1),
        lambda sql: sql + " FOR UPDATE",
        lambda sql: sql + "; DELETE FROM users",
    ],
)
def test_normalization_does_not_repair_unsafe_join_inputs(change) -> None:
    with pytest.raises(SqlValidationError):
        validator().validate(change(f"SELECT p.amount {REVERSE}"))


def test_internal_code_logs_no_sql_or_detail_and_does_not_change_frontend_copy(caplog) -> None:
    with caplog.at_level("INFO", logger="app.routing.service"):
        response = _sql_refusal(
            SqlUnsupportedError(
                "private synthetic SQL literal", reason="calculation", code="join_key"
            )
        )
    assert "join_key" in caplog.text and "private synthetic SQL literal" not in caplog.text
    assert response.answer == (
        "Mình chưa thể tính chính xác kết quả này từ dữ liệu hiện có. "
        "Bạn thử hỏi theo cách khác nhé."
    )
    assert response.sql is None and not response.rows and not response.sources


@pytest.mark.parametrize(
    "question,projection,joined",
    [
        ("Có bao nhiêu khoản thanh toán của mỗi sinh viên?", "COUNT(*) AS fact_row_count", True),
        ("Đếm số lần thanh toán theo sinh viên.", "COUNT(*) AS fact_row_count", True),
        ("Tổng tiền từng sinh viên đã đóng?", "SUM(p.amount) AS total_amount", True),
        (
            "Số giá trị học phí không bị thiếu của mỗi sinh viên?",
            "COUNT(p.amount) AS fact_value_count",
            True,
        ),
        ("Giá trị trung bình mỗi khoản thanh toán?", "AVG(amount) AS average_amount", False),
        ("Có bao nhiêu sinh viên?", "COUNT(*) AS entity_count", False),
        ("Có bao nhiêu đơn hàng?", None, False),
        ("Đếm bao nhiêu dòng dữ liệu?", "COUNT(*) AS fact_row_count", False),
    ],
)
def test_assembled_aggregate_contract_and_structured_intent_drafts(
    question: str, projection: str | None, joined: bool
) -> None:
    """Intent labels/drafts are fixtures, not a claim about live model accuracy."""
    context = authenticated_context()
    source = DIMENSION if "sinh viên?" in question else FACT
    sql = (
        f"SELECT s.name, {projection} {FORWARD} GROUP BY s.id,s.name"
        if joined
        else f"SELECT {projection} FROM uploaded_data.{source}"
    )

    class Gateway:
        def generate_structured(self, prompt, schema):
            assert schema is PlanDecision
            assert all(f'"name": "{name}"' in prompt for name in context.table_columns)
            assert "Row count has zero arguments" in prompt
            assert "value count requires a direct source column" in prompt
            assert "Do not confuse COUNT rows with non-NULL value counts" in prompt
            assert "aliases as semantic proof" in prompt
            assert "No relationships means exactly one table" in prompt
            assert "Question: " + question in prompt
            return (
                decision_from_sql(sql, prompt)
                if projection
                else PlanDecision(unsupported_reason="No order source")
            )

    generator = QueryPlanner(Gateway(), "2026-10-20", context)
    if projection is None:
        with pytest.raises(SqlUnsupportedError):
            generator.generate(question)
    else:
        validated = QueryCompiler(context).compile(generator.generate(question)).validated
        assert len(validated.tables) == (2 if joined else 1)
        assert (validated.fact_table == FACT) is joined


@pytest.mark.parametrize("bindings", [FORWARD, REVERSE], ids=["forward", "reverse"])
@pytest.mark.parametrize(
    "projection,amount_type,expected_reason",
    [
        ("SUM(p.amount) FILTER (WHERE p.amount>0)", "NUMERIC", "filter"),
        ("SUM(p.amount)+1", "NUMERIC", "projection_expression"),
        ("COALESCE(SUM(p.amount),0)", "NUMERIC", "projection_expression"),
        ("COUNT(p.id,p.amount) AS fact_value_count", "NUMERIC", "multiple_arguments"),
        ("COUNT(p.amount) AS fact_row_count", "NUMERIC", "count_wrong_argument_semantics"),
        ("COUNT(*) AS fact_value_count", "NUMERIC", "count_wrong_argument_semantics"),
        (
            "COUNT(*) AS clash,COUNT(p.amount) AS clash",
            "NUMERIC",
            "count_projection_alias_ambiguous",
        ),
        ("SUM(p.amount*2)", "NUMERIC", "argument_expression"),
        ("SUM(CAST(p.amount AS DOUBLE PRECISION))", "NUMERIC", "argument_expression"),
        ("COUNT(1) AS fact_row_count", "NUMERIC", "argument_expression"),
        ("COUNT(DISTINCT p.id) AS fact_value_count", "NUMERIC", "argument_expression"),
        ("COUNT(COALESCE(p.amount,0)) AS fact_value_count", "NUMERIC", "argument_expression"),
        ("SUM(s.id)", "NUMERIC", "dimension_column"),
        ("AVG(s.id)", "NUMERIC", "dimension_column"),
        ("COUNT(s.id) AS fact_row_count", "NUMERIC", "dimension_column"),
        ("COUNT(p.id) AS fact_row_count", "NUMERIC", "count_wrong_argument_semantics"),
        ("COUNT(p.amount) AS matched_row_count", "NUMERIC", "count_wrong_argument_semantics"),
        ("MIN(p.amount)", "NUMERIC", "unsupported_function"),
        ("MAX(p.amount)", "NUMERIC", "unsupported_function"),
        ("SUM(p.amount)", "TEXT", "non_numeric_fact"),
        ("AVG(p.amount)", "TEXT", "non_numeric_fact"),
        ("SUM(p.amount)", "DOUBLE PRECISION", "non_numeric_fact"),
    ],
)
def test_aggregate_diagnostic_branch_is_private_and_stops_before_execution(
    bindings: str, projection: str, amount_type: str, expected_reason: str, caplog
) -> None:
    context = authenticated_context()
    column_types = {name: dict(columns) for name, columns in context.column_types.items()}
    column_types[FACT]["amount"] = amount_type
    scoped_validator = SqlValidator(
        context.table_columns,
        context.allowed_schemas,
        max_tables=2,
        approved_joins=context.approved_joins,
        column_types=column_types,
        join_v1_enabled=True,
    )
    sql = f"SELECT {projection} {bindings}"
    gateway = Mock()
    gateway.generate_structured.return_value = SqlFixture(sql=sql)
    executor, guard = Mock(), Mock()
    pipeline = ValidationPipeline(
        FixtureGenerator(gateway, "2026-10-20", context.schema_context),
        scoped_validator,
        executor,
        gateway,
        execution_guard=guard,
    )
    with pytest.raises(SqlUnsupportedError) as caught:
        pipeline.run("Synthetic aggregate diagnosis")
    error = caught.value
    assert error.code == "join_aggregate" and error.reason == "calculation"
    assert error.aggregate_reason == expected_reason
    guard.assert_not_called()
    executor.execute.assert_not_called()
    gateway.generate_text.assert_not_called()
    gateway.generate_structured.assert_called_once()
    with caplog.at_level("INFO", logger="app.routing.service"):
        response = _sql_refusal(error)
    assert f"SQL request refused: join_aggregate ({expected_reason})" in caplog.text
    assert response.route == RouteLabel.UNSUPPORTED
    assert response.answer == (
        "Mình chưa thể tính chính xác kết quả này từ dữ liệu hiện có. "
        "Bạn thử hỏi theo cách khác nhé."
    )
    assert response.sql is None and response.rows == [] and response.sources == []
    for private in (sql, FACT, DIMENSION, projection, str(error), expected_reason):
        assert private not in response.answer
    for private in (sql, FACT, DIMENSION, str(error)):
        assert private not in caplog.text


@pytest.mark.parametrize("route", [RouteLabel.SQL, RouteLabel.HYBRID])
def test_aggregate_diagnosis_never_executes_or_composes_a_hybrid_answer(route, caplog) -> None:
    sql_gateway = Mock()
    sql_gateway.generate_structured.return_value = SqlFixture(
        sql=f"SELECT COUNT(p.id) AS fact_row_count {REVERSE}"
    )
    executor, answer_gateway = Mock(), Mock()
    pipeline = ValidationPipeline(
        FixtureGenerator(sql_gateway, "2026-10-20", authenticated_context().schema_context),
        validator(),
        executor,
        answer_gateway,
    )
    from app.routing.hybrid import HybridPipeline

    rag, router = Mock(), Mock()
    from app.rag.repository import RetrievedChunk

    rag.retrieve.return_value = [RetrievedChunk(1, "policy.md", "Policy", "Threshold 40", 0.1)]
    router.route.return_value = RouteDecision(
        evidence_requirement={
            "SQL": "tables",
            "RAG": "documents",
            "HYBRID": "both",
            "UNSUPPORTED": "unavailable",
        }[route],
        route=route,
        reason="Synthetic branch",
    )
    with caplog.at_level("INFO", logger="app.routing.service"):
        result = DatasetChatService(
            router, pipeline, rag, HybridPipeline(pipeline, rag, answer_gateway)
        ).chat("Synthetic refusal")
    assert result.route == RouteLabel.UNSUPPORTED
    assert result.sql is None and result.rows == [] and result.sources == []
    assert "join_aggregate (count_wrong_argument_semantics)" in caplog.text
    if route == RouteLabel.HYBRID:
        rag.retrieve.assert_called_once()
    else:
        rag.retrieve.assert_not_called()
    executor.execute.assert_not_called()
    answer_gateway.generate_text.assert_not_called()
    answer_gateway.generate_structured.assert_not_called()
