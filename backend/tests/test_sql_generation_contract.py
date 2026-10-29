"""Synthetic prompt boundaries and equivalent COUNT ordering, without live generation."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlglot import exp, parse_one

from app.core.errors import SqlUnsupportedError, SqlValidationError
from app.datasets.context import DatasetSqlContext, build_dataset_sql_context
from app.datasets.parser import ColumnSpec
from app.datasets.repository import DatasetInfo, DatasetTableInfo
from app.routing.router import QueryRouter
from app.text_to_sql.join_policy import ApprovedJoin
from app.text_to_sql.planner import QueryPlanner
from app.text_to_sql.query_plan import PlanDecision, PlanField, QueryPlan
from app.text_to_sql.validator import SqlValidator
from tests.semantic_fixtures import proposal_for_evidence
from tests.sql_validation_fixtures import FixtureGenerator, SqlFixture, ValidationPipeline
from tests.test_join_order import authenticated_context
from tests.test_three_table_join import CHAIN_ORDERS, PS, SC, validator
from tests.test_workspace_prompts import tuition_context


@pytest.mark.parametrize("edges", [1, 2])
def test_router_keeps_relationship_facts_without_sql_generation_instructions(edges: int) -> None:
    base = authenticated_context()
    tables = tuple(
        DatasetTableInfo(
            name,
            None,
            name,
            tuple(ColumnSpec(column, column, kind) for column, kind in columns.items()),
            3,
            original_filename=name + ".csv",
        )
        for name, columns in {
            "payments": {"student_id": "TEXT", "amount": "NUMERIC"},
            "students": {"student_id": "TEXT", "name": "TEXT", "course_id": "TEXT"},
            "courses": {"course_id": "TEXT", "title": "TEXT"},
        }.items()
    )
    dataset = DatasetInfo(
        13,
        "Synthetic contract",
        None,
        None,
        None,
        None,
        datetime(2026, 10, 21, tzinfo=UTC),
        tables[0],
        tables=tables,
        document_count=1,
        owner_user_id=base.owner_user_id,
    )
    relations = (
        ApprovedJoin("ps", "payments", "student_id", "students", "student_id", "r"),
        ApprovedJoin("sc", "students", "course_id", "courses", "course_id", "r"),
    )[:edges]
    context = build_dataset_sql_context(dataset, approved_joins=relations, join_v1_enabled=True)
    gateway = Mock()
    gateway.generate_structured.return_value = proposal_for_evidence("both")
    QueryRouter(gateway, context.routing_context).route("Kho nào đạt KPI trong tài liệu?")
    prompt = gateway.generate_structured.call_args.args[0]
    assert "Approved INNER relation:" in prompt
    assert "Uploaded document count in this workspace: 1" in prompt
    assert all(name in prompt for name in context.table_columns)
    assert "Required FROM/JOIN fragment" not in prompt
    assert "Supported aggregate syntax example" not in prompt
    assert "Do not reverse FROM and JOIN" not in prompt
    assert "Required FROM/JOIN fragment" in context.schema_context
    assert "COUNT(*) AS fact_row_count" in context.schema_context
    assert context.approved_joins == relations


def test_structured_schema_describes_success_and_empty_sql_refusal_consistently() -> None:
    properties = PlanDecision.model_json_schema()["properties"]
    assert "sql" not in properties and "plan" in properties
    assert PlanDecision(plan=None, unsupported_reason="missing relationship").plan is None
    plan = QueryPlan(source="t0", fields=[PlanField(alias="n", aggregate="row_count")])
    assert PlanDecision(plan=plan).unsupported_reason is None


@pytest.mark.parametrize("context", [tuition_context(1), authenticated_context()])
def test_sql_generation_explicitly_defers_unretrieved_document_conditions(
    context: DatasetSqlContext,
) -> None:
    gateway = Mock()
    gateway.generate_structured.return_value = PlanDecision(
        plan=QueryPlan(source="t0", fields=[PlanField(alias="n", aggregate="row_count")])
    )
    QueryPlanner(gateway, "2026-10-21", context).generate(
        "Lấy tổng và số dòng theo từng mã để đối chiếu KPI trong tài liệu."
    )
    prompt = gateway.generate_structured.call_args.args[0]
    assert "retrieve required metrics, grouping identifiers" in prompt
    assert "Do not apply document thresholds as SQL filters" in prompt
    assert "infer absent policies" in prompt
    assert "nonempty unsupported reason as defined by that schema" in prompt
    assert "never silently drop a required table" in prompt


@pytest.mark.parametrize("three", [False, True])
@pytest.mark.parametrize(
    "count,alias",
    [
        ("COUNT(*)", "fact_row_count"),
        ("COUNT(*)", "matched_row_count"),
        ("COUNT(p.student_id)", "fact_row_count"),
        ("COUNT(p.amount)", "fact_value_count"),
    ],
)
def test_repeated_selected_count_order_is_equivalent_to_its_unique_output_alias(
    three: bool,
    count: str,
    alias: str,
) -> None:
    bindings = (
        CHAIN_ORDERS[0] if three else CHAIN_ORDERS[0].split(" INNER JOIN uploaded_data.courses")[0]
    )
    checked = validator((PS, SC) if three else (PS,))
    selection = f"SELECT s.student_id,s.name,{count} AS {alias} {bindings} "
    grouping = "GROUP BY s.student_id,s.name "
    canonical = checked.validate(selection + grouping + f"ORDER BY {alias} DESC NULLS LAST")
    repeated = checked.validate(selection + grouping + f"ORDER BY {count} DESC NULLS LAST")
    assert repeated == canonical
    assert checked.validate(repeated.statement) == repeated
    root = parse_one(repeated.statement, read="postgres")
    assert isinstance(root.args["order"].expressions[0].this, exp.Column)


@pytest.mark.parametrize(
    "projection,ordering",
    [
        ("COUNT(*) AS payment_count,COUNT(p.amount) AS payment_count", "COUNT(*)"),
        ("COUNT(*) AS fact_value_count", "COUNT(*)"),
        ("COUNT(p.payment_id) AS fact_row_count", "COUNT(p.payment_id)"),
        ("COUNT(s.student_id) AS fact_value_count", "COUNT(s.student_id)"),
        ("SUM(p.amount) AS fact_row_count", "COUNT(*)"),
        ("SUM(p.amount) AS total", "COUNT(*)"),
        ("COUNT(*) AS fact_row_count", "COUNT(p.amount)"),
        ("COUNT(*) AS fact_row_count,COUNT(p.amount) AS fact_row_count", "COUNT(*)"),
        ("COUNT(DISTINCT p.student_id) AS fact_value_count", "COUNT(DISTINCT p.student_id)"),
        ("COUNT(*) AS fact_row_count", "COUNT(*)+1"),
        ("COUNT(*) AS fact_row_count,p.fact_row_count", "COUNT(*)"),
        ("COUNT(*) AS fact_row_count,COUNT(*) AS fact_row_count", "COUNT(*)"),
    ],
)
def test_count_order_does_not_repair_wrong_semantics_or_unselected_aggregates(
    projection: str,
    ordering: str,
) -> None:
    executor, gateway = Mock(), Mock()
    pipeline = ValidationPipeline(
        Mock(
            generate=Mock(
                return_value=(
                    f"SELECT s.student_id,s.name,{projection} {CHAIN_ORDERS[0]} "
                    f"GROUP BY s.student_id,s.name ORDER BY {ordering} DESC"
                )
            )
        ),
        validator(),
        executor,
        gateway,
    )
    with pytest.raises(SqlValidationError):
        pipeline.run("Synthetic unsupported count")
    executor.execute.assert_not_called()
    gateway.generate_text.assert_not_called()


def test_generator_refusal_remains_fail_closed_without_echoing_raw_reason() -> None:
    gateway = Mock()
    gateway.generate_structured.return_value = SqlFixture(
        sql="", unsupported_reason="synthetic private reason"
    )
    with pytest.raises(SqlUnsupportedError) as caught:
        FixtureGenerator(gateway, "2026-10-21", authenticated_context().schema_context).generate(
            "KPI?"
        )
    assert caught.value.code == "generator_unsupported"
    assert "synthetic private reason" not in str(caught.value)
    gateway.generate_structured.assert_called_once()
    gateway.generate_text.assert_not_called()


def test_no_relationship_context_remains_single_table_only() -> None:
    context = replace(tuition_context(1), has_documents=True)
    assert not context.approved_joins
    assert "Never JOIN tables" in context.schema_context
    assert "Never JOIN tables" not in context.routing_context


@pytest.mark.parametrize("quoted", [False, True])
def test_count_order_preserves_selected_alias_quoting_and_top_n(quoted: bool) -> None:
    alias = '"fact_row_count"' if quoted else "FACT_ROW_COUNT"
    sql = (
        f"SELECT s.student_id,COUNT(*) AS {alias} {CHAIN_ORDERS[0]} "
        "GROUP BY s.student_id ORDER BY COUNT(*) DESC NULLS FIRST,s.student_id LIMIT 2"
    )
    checked = validator().validate(sql)
    root = parse_one(checked.statement, read="postgres")
    order = root.args["order"].expressions[0]
    assert order.this.name.lower() == "fact_row_count"
    assert order.this.this.quoted is quoted
    assert order.args["desc"] and order.args["nulls_first"]
    assert root.args["limit"].expression.this == "2"


def test_count_having_is_not_repaired_as_ordering() -> None:
    with pytest.raises(SqlUnsupportedError) as caught:
        validator().validate(
            f"SELECT s.student_id,COUNT(*) AS fact_row_count {CHAIN_ORDERS[0]} "
            "GROUP BY s.student_id HAVING COUNT(*)>1 ORDER BY COUNT(*) DESC"
        )
    assert caught.value.aggregate_reason == "count_having_unsupported"


def test_selected_count_alias_can_shadow_an_unselected_source_column() -> None:
    checked = validator()
    checked._table_columns["payments"].add("fact_row_count")
    sql = (
        f"SELECT s.student_id,COUNT(*) AS fact_row_count {CHAIN_ORDERS[0]} "
        "WHERE p.fact_row_count>0 GROUP BY s.student_id ORDER BY COUNT(*) ASC NULLS LAST"
    )
    result = parse_one(checked.validate(sql).statement, read="postgres")
    assert result.args["where"] == parse_one(sql, read="postgres").args["where"]
    assert result.args["order"].expressions[0].this.sql() == "fact_row_count"


@pytest.mark.parametrize(
    "projection",
    [
        "COUNT(*) AS fact_row_count,p.fact_row_count",
        "COUNT(SUM(p.amount)) AS fact_value_count",
        'COUNT(*) AS "FACT_ROW_COUNT"',
    ],
)
def test_count_normalization_does_not_hide_duplicate_nested_or_quoted_case_errors(
    projection: str,
) -> None:
    checked = validator()
    checked._table_columns["payments"].add("fact_row_count")
    count = "COUNT(SUM(p.amount))" if "SUM" in projection else "COUNT(*)"
    with pytest.raises(SqlValidationError):
        checked.validate(
            f"SELECT s.student_id,{projection} {CHAIN_ORDERS[0]} "
            f"GROUP BY s.student_id ORDER BY {count}"
        )


def test_two_selected_count_sorts_keep_their_distinct_metrics_and_directions() -> None:
    result = validator().validate(
        f"SELECT s.student_id,COUNT(*) AS fact_row_count,"
        f"COUNT(p.amount) AS fact_value_count {CHAIN_ORDERS[0]} "
        "GROUP BY s.student_id ORDER BY COUNT(*) ASC,COUNT(p.amount) DESC NULLS LAST"
    )
    order = parse_one(result.statement, read="postgres").args["order"].expressions
    assert [item.this.sql() for item in order] == ["fact_row_count", "fact_value_count"]
    assert not order[0].args["desc"] and order[1].args["desc"]


@pytest.mark.parametrize("reverse", [False, True])
def test_vietnamese_registry_mapping_retains_unrelated_schema_without_authorizing_it(
    reverse: bool,
) -> None:
    base = authenticated_context()
    dimension, fact = base.table_columns
    context_tables = (
        DatasetTableInfo(
            "01 Học viên",
            None,
            dimension,
            (ColumnSpec("Mã học viên", "id", "BIGINT"), ColumnSpec("Họ tên", "name", "TEXT")),
            2,
            original_filename="01 Học viên.csv",
        ),
        DatasetTableInfo(
            "02 Thanh toán",
            None,
            fact,
            (
                ColumnSpec("Mã giao dịch", "id", "BIGINT"),
                ColumnSpec("Mã học viên", "student_id", "BIGINT"),
                ColumnSpec("Đã đóng (VNĐ)", "amount", "NUMERIC"),
            ),
            3,
            original_filename="02 Thanh toán.xlsx",
        ),
        DatasetTableInfo(
            "03 Mã phụ chưa xác nhận",
            None,
            "dataset_" + uuid4().hex,
            (ColumnSpec("Mã học viên", "id", "BIGINT"),),
            2,
        ),
    )
    context = build_dataset_sql_context(
        DatasetInfo(
            13,
            "Metadata synthetic",
            None,
            None,
            None,
            None,
            datetime(2026, 10, 21, tzinfo=UTC),
            context_tables[0],
            tables=context_tables[::-1] if reverse else context_tables,
            owner_user_id=base.owner_user_id,
        ),
        approved_joins=base.approved_joins,
        join_v1_enabled=True,
    )
    assert context.table_columns[dimension] == {"id", "name"}
    assert 'amount NUMERIC (source header: "Đã đóng (VNĐ)")' in context.schema_context
    assert "01 Học viên" in context.routing_context
    assert len(context.table_columns) == 3 and len(context.approved_joins) == 1
    checked = SqlValidator(
        context.table_columns,
        context.allowed_schemas,
        max_tables=3,
        approved_joins=context.approved_joins,
        column_types=context.column_types,
        join_v1_enabled=True,
    )
    with pytest.raises(SqlUnsupportedError) as caught:
        checked.validate(
            f"SELECT f.id FROM uploaded_data.{fact} f INNER JOIN "
            f"uploaded_data.{context_tables[2].physical_table_name} x ON f.student_id=x.id"
        )
    assert caught.value.code == "join_relationship"
