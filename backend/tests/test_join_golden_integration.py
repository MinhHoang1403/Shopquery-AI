"""Golden PostgreSQL joins across domains, compared with independent Decimal oracles."""

from decimal import Decimal, localcontext
from time import perf_counter
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.core.errors import SqlUnsupportedError
from app.database.session import get_readonly_engine, get_setup_engine
from app.datasets.relationship_repository import RelationshipRepository
from app.datasets.relationships import RelationshipConfirm, RelationshipInput
from app.datasets.repository import DatasetRepository
from app.dependencies import build_workspace_context
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.validator import SqlValidator
from tests.auth_helpers import TEST_OWNER
from tests.test_dataset_parser import parse

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("dimension_name", "fact_name"),
    [
        ("students", "payments"),
        ("customers", "orders"),
        ("products", "transactions"),
        ("departments", "employees"),
        ("classes", "enrollments"),
        ("routes", "shipments"),
        ("meters", "readings"),
    ],
)
def test_join_totals_counts_average_and_calendar_match_fact_oracle(
    dimension_name: str,
    fact_name: str,
) -> None:
    repository = DatasetRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
    dataset = repository.create_workspace("Golden " + str(uuid4()))
    data = [
        (11, 101, "12345678901234567890.12", "2026-09-30T23:59:59+07:00"),
        (12, 101, "0.00", "2026-10-01T00:00:00+07:00"),
        (13, 102, "2.0000", "2026-09-30T17:00:00Z"),
        (14, 102, None, "2026-10-02T00:00:00+07:00"),
        (15, 103, None, "2026-10-01T01:00:00+07:00"),
        (16, 104, "0.000000000000000000000002", "2026-10-01T00:00:00-04:00"),
    ]
    try:
        dataset = repository.add_table(
            dataset.dataset_id,
            parse(
                dimension_name + ".csv",
                (
                    "Id,Name,Parent measure\n101,An,99.00\n102,Bình,88.00\n"
                    "103,C,10.00\n104,D,0.00\n"
                ).encode(),
            ),
        )
        content = "Id,Parent id,Amount,Instant\n" + "\n".join(
            f"{key},{parent},{amount or ''},{instant}" for key, parent, amount, instant in data
        )
        dataset = repository.add_table(
            dataset.dataset_id, parse(fact_name + ".csv", content.encode())
        )
        target, source = dataset.tables
        request = RelationshipInput(
            source_table_id=str(source.dataset_table_id),
            source_column="parent_id",
            target_table_id=str(target.dataset_table_id),
            target_column="id",
        )
        relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
        started = perf_counter()
        preview = relations.preview(dataset.dataset_id, request)
        relations.confirm(
            dataset.dataset_id,
            RelationshipConfirm(**request.model_dump(), revision=preview.revision, confirmed=True),
        )
        verified = perf_counter()
        context = build_workspace_context(
            get_settings().model_copy(update={"sql_join_v1_enabled": True}), dataset, repository
        )
        contextualized = perf_counter()
        validator = SqlValidator(
            context.table_columns,
            context.allowed_schemas,
            max_tables=2,
            join_v1_enabled=True,
            approved_joins=context.approved_joins,
            column_types=context.column_types,
        )
        suffix = (
            f"FROM uploaded_data.{source.physical_table_name} f "
            f"INNER JOIN uploaded_data.{target.physical_table_name} d ON f.parent_id=d.id"
        )
        sql = validator.validate(
            "SELECT d.id, SUM(f.amount) AS total, AVG(f.amount) AS average, "
            "COUNT(*) AS fact_row_count, COUNT(f.amount) AS fact_value_count "
            + suffix
            + " GROUP BY d.id ORDER BY d.id"
        )
        validated = perf_counter()
        executor = SqlExecutor(get_readonly_engine(), 5000, 100)
        with relations.execution_guard(dataset.dataset_id, context.approved_joins, sql):
            rows = executor.execute(sql)
        executed = perf_counter()
        selected = executor.execute(
            validator.validate("SELECT f.id, d.name " + suffix + " WHERE d.id=102 ORDER BY f.id")
        )
        assert selected == [{"id": item[0], "name": "Bình"} for item in data if item[1] == 102]
        with localcontext() as precision:
            precision.prec = 100
            for row in rows:
                values = [item for item in data if item[1] == row["id"]]
                measured = [Decimal(item[2]) for item in values if item[2] is not None]
                assert row["fact_row_count"] == len(values)
                assert row["fact_value_count"] == len(measured)
                if measured:
                    assert Decimal(row["total"]) == sum(measured)
                    assert Decimal(row["average"]) == sum(measured) / len(measured)
                else:
                    assert row["total"] is None and row["average"] is None
            before = executor.execute(
                validator.validate(
                    "SELECT SUM(amount) AS total, COUNT(*) AS n "
                    f"FROM uploaded_data.{source.physical_table_name}"
                )
            )[0]
            assert sum(
                Decimal(row["total"]) for row in rows if row["total"] is not None
            ) == Decimal(before["total"])
            assert sum(row["fact_row_count"] for row in rows) == before["n"] == 6
            monthly = executor.execute(
                validator.validate(
                    "SELECT SUM(f.amount) AS total, COUNT(*) AS fact_row_count "
                    + suffix
                    + " WHERE f.instant >= TIMESTAMPTZ '2026-10-01 00:00:00+07:00' "
                    "AND f.instant < TIMESTAMPTZ '2026-11-01 00:00:00+07:00'"
                )
            )[0]
            assert monthly["fact_row_count"] == 5
            assert Decimal(monthly["total"]) == Decimal("2.000000000000000000000002")
        for aggregate in ("SUM(d.parent_measure)", "AVG(d.parent_measure)", "COUNT(d.id)"):
            with pytest.raises(SqlUnsupportedError):
                validator.validate("SELECT " + aggregate + " " + suffix)
        print(
            {
                "domain": dimension_name,
                "verify_ms": (verified - started) * 1000,
                "context_ms": (contextualized - verified) * 1000,
                "validation_ms": (validated - contextualized) * 1000,
                "execution_ms": (executed - validated) * 1000,
                "extra_ai_calls": 0,
            }
        )
    finally:
        repository.delete(dataset.dataset_id)
