"""Post-fix library schema: renamed columns, reordered inputs and fresh PG oracles.

This tests deterministic execution, not the accuracy of a scripted language model.
Runs exclusively in the CI database guarded by the shared integration fixtures.
"""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.database.guest_access import configure_guest_access
from app.database.session import get_setup_engine
from app.datasets.context import build_dataset_sql_context
from app.datasets.relationships import RelationshipInput, verify_relationship
from app.datasets.repository import DatasetInfo
from app.guest.pipeline import GuestSqlDatabase
from app.guest.worker import parse_guest_file
from app.routing.hybrid_evidence import compose_answer, verified_classification
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.join_policy import ApprovedJoin
from app.text_to_sql.pipeline import SqlResult
from app.text_to_sql.planner import QueryPlanner
from app.text_to_sql.query_plan import QueryPlan
from tests.hybrid_fixtures import rule_block, scoped_chunk
from tests.plan_fixtures import decision_from_sql

pytestmark = pytest.mark.integration


def csv_file(name, headers, rows, settings, *, reverse):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers[::-1] if reverse else headers)
    writer.writerows(row[::-1] if reverse else row for row in rows)
    return parse_guest_file(name, stream.getvalue().encode(), None, settings)


@pytest.mark.parametrize("variant", [0, 1, 2])
def test_library_transformations_preserve_semantics_against_independent_pg_oracles(variant):
    configure_guest_access(get_setup_engine())
    settings = get_settings().model_copy(update={"sql_join_v1_enabled": True})
    # Names, identifiers, values and column order differ; no production rule knows them.
    key, book_key, fee, day = (
        ("branch_code", "book_code", "penalty", "loan_date")
        if variant == 0
        else (
            f"site_{variant}_code",
            f"item_{variant}_code",
            f"measure_{variant}",
            f"day_{variant}",
        )
    )
    values = [Decimal("10.25") + variant, Decimal("0.00"), None, Decimal("20.50") + variant]
    branch_ids = [f"00{variant}1", f"00{variant}2"]
    book_ids = [f"01{variant}1", f"01{variant}2"]
    files = [
        csv_file(
            "branches.csv",
            [key, "name"],
            [[branch_ids[0], "Bắc"], [branch_ids[1], "Nam"]],
            settings,
            reverse=bool(variant),
        ),
        csv_file(
            "books.csv",
            [book_key, key, "name"],
            [[book_ids[i], branch_ids[i], "Trùng tên"] for i in range(2)],
            settings,
            reverse=bool(variant),
        ),
        csv_file(
            "loans.csv",
            ["record_code", book_key, fee, day, "unused"],
            [[f"00{i}", book_ids[i // 2], values[i], f"2032-04-0{i + 1}", "X"] for i in range(4)],
            settings,
            reverse=bool(variant),
        ),
    ]
    database = GuestSqlDatabase(settings, files)
    try:
        joins = []
        for child, parent, column in [(2, 1, book_key), (1, 0, key)]:
            request = RelationshipInput(
                source_table_id=files[child].file_id,
                source_column=column,
                target_table_id=files[parent].file_id,
                target_column=column,
            )
            with database.engine.connect() as connection:
                proof = verify_relationship(connection, request, database.file_tables)
            assert proof.valid
            joins.append(
                ApprovedJoin(
                    f"r{child}",
                    f"table_{child + 1}",
                    column,
                    f"table_{parent + 1}",
                    column,
                    proof.revision,
                )
            )
        info = DatasetInfo(
            0,
            "Library held-out",
            None,
            None,
            None,
            None,
            datetime.now(UTC),
            database.tables[0],
            tables=tuple(database.tables),
        )
        context = build_dataset_sql_context(
            info, schema_name="pg_temp", approved_joins=tuple(joins), join_v1_enabled=True
        )
        compiler = QueryCompiler(context, join_v1_enabled=True)
        gateway = Mock()
        planner = QueryPlanner(gateway, "2032-04-01", context, join_v1_enabled=True)
        cases = [
            (
                f"SELECT COUNT(*) AS n,COUNT({fee}) AS present,"
                f"SUM({fee}) AS total,AVG({fee}) AS mean "
                "FROM pg_temp.table_3",
                "scalar",
            ),
            (
                f"SELECT record_code,{day},{fee} FROM pg_temp.table_3 WHERE {fee}>0 "
                f"AND {day}>=DATE '2032-04-02' ORDER BY record_code",
                "filter",
            ),
            (
                f"SELECT b.{key},b.name,COUNT(*) AS n,SUM(f.{fee}) AS total "
                "FROM pg_temp.table_3 f JOIN pg_temp.table_2 k "
                f"ON f.{book_key}=k.{book_key} JOIN pg_temp.table_1 b ON k.{key}=b.{key} "
                f"GROUP BY b.{key},b.name ORDER BY b.{key}",
                "chain",
            ),
            (
                f"SELECT k.{book_key},k.name,SUM(f.{fee}) AS total FROM pg_temp.table_3 f "
                f"JOIN pg_temp.table_2 k ON f.{book_key}=k.{book_key} "
                f"GROUP BY k.{book_key},k.name ORDER BY total DESC LIMIT 1",
                "ranking",
            ),
        ]
        for statement, kind in cases:
            gateway.generate_structured.side_effect = lambda prompt, schema, statement=statement: (
                decision_from_sql(statement, prompt)
            )
            plan = planner.generate("Scripted held-out execution fixture; no language model")
            assert isinstance(plan, QueryPlan)
            compiled = compiler.compile(plan)
            actual = SqlExecutor(database.engine, 3000, 100).execute(
                compiled.validated, compiled.parameters
            )
            # Oracles use only the fact rows and explicit independent key maps, not the plan SQL.
            with database.engine.connect() as connection:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                oracle = (
                    connection.execute(
                        text(
                            f'SELECT record_code,"{book_key}" AS item,'
                            f'"{fee}" AS value,"{day}" AS day '
                            "FROM pg_temp.table_3 ORDER BY record_code"
                        )
                    )
                    .mappings()
                    .all()
                )
            if kind == "scalar":
                present = [r.value for r in oracle if r.value is not None]
                with database.engine.connect() as connection:
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    mean = connection.scalar(text(f'SELECT AVG("{fee}") FROM pg_temp.table_3'))
                assert len(actual) == 1
                assert actual[0]["n"] == 4 and actual[0]["present"] == 3
                assert Decimal(actual[0]["total"]) == sum(present)
                assert Decimal(actual[0]["mean"]) == mean
            elif kind == "filter":
                assert actual == [{"record_code": "003", day: "2032-04-04", fee: str(values[3])}]
                assert compiled.result_columns[1].data_type == "DATE"
                assert not compiled.result_columns[1].numeric
            elif kind == "chain":
                expected = {
                    branch_ids[i]: sum(
                        r.value for r in oracle if r.item == book_ids[i] and r.value is not None
                    )
                    for i in range(2)
                }
                assert {r[key]: Decimal(r["total"]) for r in actual} == expected
                assert all(r["n"] == 2 for r in actual)
                threshold = Decimal("20.50") + variant
                chunk = scoped_chunk(
                    91, "library_policy.md", "Điều kiện", rule_block(key, fee, str(threshold)), 0.01
                )
                result = SqlResult(
                    "",
                    compiled.evidence_sql,
                    actual,
                    compiled.validated.fact_table,
                    compiled.validated.count_metrics,
                    compiled.result_columns,
                )
                draft = verified_classification(result, [chunk], context, "vi")
                assert draft is not None
                assert {item.entity_values[0]: item.status for item in draft.decisions} == {
                    identity: "qualified" if total >= threshold else "not_qualified"
                    for identity, total in expected.items()
                }
                assert draft.used_chunk_ids == [91]
                summary = compose_answer(result, [chunk], draft, context)
                assert "**1 đối tượng đạt yêu cầu**" in summary
                assert "**1 đối tượng chưa đạt**" in summary
            else:
                assert actual == [
                    {book_key: book_ids[1], "name": "Trùng tên", "total": str(values[3])}
                ]
    finally:
        database.close()
