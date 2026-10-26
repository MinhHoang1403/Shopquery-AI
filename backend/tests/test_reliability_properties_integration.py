"""Differential and metamorphic checks against an isolated PostgreSQL TEMP table."""

import csv
import io
import random
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.database.guest_access import configure_guest_access
from app.database.session import get_setup_engine
from app.datasets.context import DatasetSqlContext
from app.guest.pipeline import GuestSqlDatabase
from app.guest.worker import parse_guest_file
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.query_plan import PlanExpression, PlanField, PlanFilter, PlanSort, QueryPlan
from tests.test_query_compiler import field

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("seed", range(8))
def test_permutations_partition_exact_decimal_null_and_numeric_boundaries(seed):
    rng = random.Random(seed)
    rows = [
        (
            f"{i:06d}",
            f"Nhóm {i % 4}",
            None if i % 5 == 0 else Decimal(rng.randrange(-5000, 10000)) / 100,
            99 + i % 3,
        )
        for i in range(32)
    ]
    oracle = {}
    for _, key, amount, _ in rows:
        n, present, total = oracle.get(key, (0, 0, Decimal(0)))
        oracle[key] = (n + 1, present + (amount is not None), total + (amount or Decimal(0)))
    rng.shuffle(rows)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Mã", "Nhóm", "Tiền", "Số phòng"])
    writer.writerows(rows)
    settings = get_settings()
    configure_guest_access(get_setup_engine())
    file = parse_guest_file("metrics.csv", stream.getvalue().encode(), None, settings)
    database = GuestSqlDatabase(settings, [file])
    context = DatasetSqlContext(
        "",
        {"table_1": {c.name for c in file.table.columns}},
        {"table_1": "pg_temp"},
        column_types={"table_1": {c.name: c.data_type for c in file.table.columns}},
    )
    compiler = QueryCompiler(context)
    key, amount, rooms = (field(compiler, "table_1", name) for name in ("nhom", "tien", "so_phong"))
    plan = QueryPlan(
        source="t0",
        fields=[
            PlanField(reference=key, alias="category"),
            PlanField(reference="e0", alias="n"),
            PlanField(reference="e1", alias="present"),
            PlanField(reference="e2", alias="total"),
        ],
        expressions=[
            PlanExpression(operation="row_count"),
            PlanExpression(operation="value_count", arguments=[amount]),
            PlanExpression(operation="sum", arguments=[amount]),
        ],
        group_by=[key],
        sort=[PlanSort(field="category")],
    )
    try:
        compiled = compiler.compile(plan)
        actual = SqlExecutor(database.engine, 3000, 200).execute(
            compiled.validated, compiled.parameters
        )
        assert {
            r["category"]: (r["n"], r["present"], Decimal(r["total"])) for r in actual
        } == oracle
        assert sum(r["n"] for r in actual) == len(rows)
        assert sum(Decimal(r["total"]) for r in actual) == sum(
            (r[2] or Decimal(0) for r in rows), Decimal(0)
        )
        for operator, sql in [("gt", ">"), ("gte", ">=")]:
            filtered = QueryPlan(
                source="t0",
                fields=[PlanField(reference="e0", alias="n")],
                expressions=[PlanExpression(operation="row_count")],
                filters=[PlanFilter(reference=rooms, operator=operator, values=["100"])],
            )
            compiled = compiler.compile(filtered)
            result = SqlExecutor(database.engine, 3000, 200).execute(
                compiled.validated, compiled.parameters
            )
            with database.engine.connect() as c:
                c.execute(text("SET TRANSACTION READ ONLY"))
                c.execute(text("SET LOCAL statement_timeout='3000ms'"))
                expected = c.scalar(
                    text(f"SELECT COUNT(*) FROM pg_temp.table_1 WHERE so_phong {sql} 100")
                )
            assert result == [{"n": expected}]
    finally:
        database.close()
