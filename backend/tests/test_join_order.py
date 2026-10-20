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
from app.routing.service import _sql_refusal
from app.text_to_sql.generator import SqlDraft, SqlGenerator
from app.text_to_sql.join_policy import ApprovedJoin, validate_uploaded_join
from app.text_to_sql.pipeline import TextToSqlPipeline
from app.text_to_sql.validator import SqlValidator

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
    draft = SqlDraft(
        sql="SELECT s.name, SUM(p.amount) AS total, AVG(p.amount) AS average, "
        "COUNT(*) AS fact_row_count " + suffix + " GROUP BY s.name ORDER BY s.name"
    )
    gateway = Mock()
    gateway.generate_structured.return_value = draft
    generated = SqlGenerator(gateway, "2026-10-20", authenticated_context().schema_context)
    validated = validator().validate(generated.generate("Synthetic students/payments"))
    root = parse_one(validated.statement, read="postgres")
    assert root.args["from_"].this.name == FACT
    assert root.args["from_"].this.alias == "p"
    assert root.args["joins"][0].this.name == DIMENSION
    assert validated.fact_table == FACT and validated.relationship_id == RELATION.relationship_id
    assert validated.tables == frozenset({FACT, DIMENSION})
    assert validator().validate(validated.statement) == validated
    assert draft.sql.endswith("GROUP BY s.name ORDER BY s.name")


def test_fact_identity_does_not_depend_on_alias_spelling() -> None:
    result = validator().validate(
        f"SELECT SUM(d.amount) AS total FROM uploaded_data.{DIMENSION} f "
        f"INNER JOIN uploaded_data.{FACT} d ON d.student_id=f.id"
    )
    assert result.fact_table == FACT
    assert f"FROM uploaded_data.{FACT} AS d INNER JOIN uploaded_data.{DIMENSION} AS f" in (
        result.statement
    )


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
    pipeline = TextToSqlPipeline(
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
