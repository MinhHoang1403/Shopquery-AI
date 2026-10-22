from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import SqlValidationError
from app.database.guest_access import configure_guest_access
from app.database.session import get_setup_engine
from app.datasets.context import DatasetSqlContext
from app.guest.pipeline import GuestSqlDatabase
from app.guest.worker import parse_guest_file
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.query_plan import PlanExpression, PlanField, PlanSort, QueryPlan
from tests.test_query_compiler import field

pytestmark = pytest.mark.integration


@pytest.fixture
def expression_database():
    settings = get_settings()
    configure_guest_access(get_setup_engine())
    file = parse_guest_file(
        "metrics.csv",
        (
            b"Key,Price,Quantity,Instant\n"
            b"A,10.25,2,2026-09-30T17:00:00Z\n"
            b"A,0.00,0,2026-10-31T16:59:59Z\n"
            b"B,20.50,-1,2026-12-31T17:00:00Z\n"
            b"B,,3,2027-01-01T00:00:00+07:00\n"
            b"C,,0,\n"
        ),
        None,
        settings,
    )
    database = GuestSqlDatabase(settings, [file])
    context = DatasetSqlContext(
        "",
        {"table_1": {c.name for c in file.table.columns}},
        {"table_1": "pg_temp"},
        column_types={"table_1": {c.name: c.data_type for c in file.table.columns}},
    )
    try:
        yield database, QueryCompiler(context)
    finally:
        database.close()


def node(operation, *arguments, **kwargs):
    return PlanExpression(operation=operation, arguments=list(arguments), **kwargs)


def run(database, compiler, plan):
    result = compiler.compile(plan)
    return SqlExecutor(database.engine, 3000, 100).execute(result.validated, result.parameters)


@pytest.mark.parametrize(
    "operation,oracle",
    [
        ("add", [Decimal("12.25"), Decimal("0.00"), Decimal("19.50"), None, None]),
        ("subtract", [Decimal("8.25"), Decimal("0.00"), Decimal("21.50"), None, None]),
        ("multiply", [Decimal("20.50"), Decimal("0.00"), Decimal("-20.50"), None, None]),
        ("divide", [Decimal("5.125"), None, Decimal("-20.50"), None, None]),
    ],
)
def test_arithmetic_independent_decimal_oracle(expression_database, operation, oracle):
    database, compiler = expression_database
    price, quantity = (field(compiler, "table_1", name) for name in ("price", "quantity"))
    plan = QueryPlan(
        source="t0",
        expressions=[node(operation, price, quantity)],
        fields=[PlanField(reference="e0", alias="metric")],
    )
    rows = run(database, compiler, plan)
    assert [None if r["metric"] is None else Decimal(r["metric"]) for r in rows] == oracle


def test_grouped_aggregate_division_counts_and_having(expression_database):
    database, compiler = expression_database
    price = field(compiler, "table_1", "price")
    key = field(compiler, "table_1", "key")
    plan = QueryPlan(
        source="t0",
        expressions=[node("sum", price), node("value_count", price), node("divide", "e0", "e1")],
        fields=[
            PlanField(reference=key, alias="key"),
            PlanField(reference="e2", alias="average"),
            PlanField(aggregate="row_count", alias="rows"),
            PlanField(reference=price, aggregate="value_count", alias="present"),
        ],
        group_by=[key],
        sort=[PlanSort(field="key")],
    )
    rows = run(database, compiler, plan)
    assert [
        (r["key"], None if r["average"] is None else Decimal(r["average"]), r["rows"], r["present"])
        for r in rows
    ] == [
        ("A", Decimal("5.125"), 2, 2),
        ("B", Decimal("20.50"), 2, 1),
        ("C", None, 1, 0),
    ]
    with database.engine.connect() as connection:
        oracle = connection.execute(
            text(
                "SELECT key, SUM(price)/NULLIF(COUNT(price),0) FROM pg_temp.table_1 "
                "GROUP BY key ORDER BY key"
            )
        ).all()
    assert [r[1] for r in oracle] == [Decimal("5.125"), Decimal("20.50"), None]
    having = plan.model_copy(
        update={
            "expressions": plan.expressions
            + [
                node("literal", value="10", value_type="NUMERIC"),
                node("gt", "e0", "e3"),
            ],
            "having": "e4",
        }
    )
    assert [r["key"] for r in run(database, compiler, having)] == ["A", "B"]


def test_boolean_precedence_and_temporal_grouping(expression_database):
    database, compiler = expression_database
    key, price, instant = (field(compiler, "table_1", name) for name in ("key", "price", "instant"))
    expressions = [
        node("month_label", instant),
        node("literal", value="A", value_type="TEXT"),
        node("eq", key, "e1"),
        node("is_null", price),
        node("or", "e2", "e3"),
        node("literal", value="2026-10-01T00:00:00+07:00", value_type="TIMESTAMPTZ"),
        node("gte", instant, "e5"),
        node("and", "e4", "e6"),
    ]
    plan = QueryPlan(
        source="t0",
        expressions=expressions,
        where="e7",
        fields=[
            PlanField(reference="e0", alias="month"),
            PlanField(aggregate="row_count", alias="rows"),
        ],
        group_by=["e0"],
        sort=[PlanSort(field="month")],
    )
    assert run(database, compiler, plan) == [
        {"month": "2026-10", "rows": 2},
        {"month": "2027-01", "rows": 1},
    ]


@pytest.mark.parametrize(
    "operation,expected",
    [
        (
            "day",
            [
                ("2026-10-01T00:00:00", 1),
                ("2026-10-31T00:00:00", 1),
                ("2027-01-01T00:00:00", 2),
                (None, 1),
            ],
        ),
        ("year", [("2026-01-01T00:00:00", 2), ("2027-01-01T00:00:00", 2), (None, 1)]),
        ("date_label", [("2026-10-01", 1), ("2026-10-31", 1), ("2027-01-01", 2), (None, 1)]),
    ],
)
def test_calendar_grouping_year_boundary_and_null(expression_database, operation, expected):
    database, compiler = expression_database
    plan = QueryPlan(
        source="t0",
        expressions=[node(operation, field(compiler, "table_1", "instant"))],
        fields=[
            PlanField(reference="e0", alias="period"),
            PlanField(aggregate="row_count", alias="rows"),
        ],
        group_by=["e0"],
        sort=[PlanSort(field="period")],
    )
    assert [(r["period"], r["rows"]) for r in run(database, compiler, plan)] == expected


def test_numeric_aggregate_and_fact_expression_oracles(expression_database):
    database, compiler = expression_database
    price, quantity = (field(compiler, "table_1", name) for name in ("price", "quantity"))
    plan = QueryPlan(
        source="t0",
        expressions=[node("multiply", price, quantity)],
        fields=[
            *[
                PlanField(reference=price, alias=operation, aggregate=operation)
                for operation in ("sum", "avg", "min", "max")
            ],
            PlanField(reference="e0", alias="weighted_sum", aggregate="sum"),
        ],
    )
    result = run(database, compiler, plan)[0]
    assert {k: Decimal(v) for k, v in result.items()} == {
        "sum": Decimal("30.75"),
        "avg": Decimal("10.25"),
        "min": Decimal("0.00"),
        "max": Decimal("20.50"),
        "weighted_sum": Decimal("0.00"),
    }


def test_count_nullable_boolean_counts_false_as_present():
    settings = get_settings()
    configure_guest_access(get_setup_engine())
    file = parse_guest_file("flags.csv", b"Key,Active\na,true\nb,false\nc,\n", None, settings)
    assert file.table.columns[1].data_type == "BOOLEAN"
    database = GuestSqlDatabase(settings, [file])
    context = DatasetSqlContext(
        "",
        {"table_1": {"active", "key"}},
        {"table_1": "pg_temp"},
        column_types={"table_1": {"active": "BOOLEAN", "key": "TEXT"}},
    )
    compiler = QueryCompiler(context)
    plan = QueryPlan(
        source="t0",
        expressions=[node("value_count", "t0.c0")],
        fields=[
            PlanField(reference="t0.c0", aggregate="value_count", alias="present"),
            PlanField(reference="e0", alias="also_present"),
            PlanField(aggregate="row_count", alias="rows"),
        ],
    )
    try:
        assert run(database, compiler, plan) == [{"present": 2, "also_present": 2, "rows": 3}]
    finally:
        database.close()


@pytest.mark.parametrize(
    "change",
    [
        [node("literal", value="0", value_type="NUMERIC"), node("divide", "t0.c0", "e0")],
        [node("add", "t0.c0", "unknown")],
        [node("sum", "t0.c0"), node("avg", "e0")],
    ],
)
def test_invalid_expression_never_reaches_execution(expression_database, change):
    _, compiler = expression_database
    with pytest.raises(SqlValidationError):
        compiler.compile(
            QueryPlan(
                source="t0",
                expressions=change,
                fields=[PlanField(reference=f"e{len(change) - 1}", alias="x")],
            )
        )
