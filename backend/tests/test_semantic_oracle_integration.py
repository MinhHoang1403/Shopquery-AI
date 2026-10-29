"""Run locked independent execution gold on the explicitly isolated PostgreSQL test DB."""

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.database.test_safety import require_test_database
from app.datasets.context import DatasetSqlContext
from app.semantic.request import RequestIdentity, semantic_request
from app.semantic.task import (
    OutputSelection,
    Population,
    Predicate,
    PredicateGroup,
    Projection,
    ScalarValue,
    SemanticTask,
)
from app.text_to_sql.compiler import QueryCompiler, SchemaReferences
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.pipeline import TextToSqlPipeline

pytestmark = pytest.mark.integration
GOLD = json.loads(
    Path(__file__).with_name("fixtures").joinpath("semantic_execution_oracle.json").read_text()
)
OWNER = UUID("f425b6ce-7ff0-4329-9948-4e9bf2e93642")


@pytest.fixture
def oracle_database():
    url = get_settings().database_setup_url
    require_test_database(url)
    engine = create_engine(url, poolclass=StaticPool)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TEMP TABLE entities(entity_id TEXT PRIMARY KEY)"))
            connection.execute(
                text(
                    "CREATE TEMP TABLE events(event_id TEXT PRIMARY KEY, "
                    "entity_id TEXT REFERENCES entities(entity_id), amount NUMERIC, "
                    "event_date DATE, region TEXT)"
                )
            )
            connection.execute(
                text("INSERT INTO entities VALUES (:id)"),
                [{"id": key} for key in GOLD["entity_universe"]],
            )
            for values in GOLD["events"]:
                row = dict(zip(GOLD["columns"], values, strict=True))
                connection.execute(
                    text(
                        "INSERT INTO events VALUES (:event_id,:entity_id,"
                        "CAST(:amount AS NUMERIC),CAST(:event_date AS DATE),:region)"
                    ),
                    row,
                )
        yield engine
    finally:
        engine.dispose()


def context():
    return DatasetSqlContext(
        "isolated execution oracle",
        {"events": set(GOLD["columns"])},
        {"events": "pg_temp"},
        dataset_id=71,
        owner_user_id=OWNER,
        column_types={
            "events": {
                "event_id": "TEXT",
                "entity_id": "TEXT",
                "amount": "NUMERIC",
                "event_date": "DATE",
                "region": "TEXT",
            }
        },
    )


def canonical(rows):
    return [
        {
            key: format(value, "f") if isinstance(value, Decimal) else value
            for key, value in row.items()
        }
        for row in rows
    ]


@pytest.mark.parametrize("case_index", [0, 1])
def test_semantic_sql_equals_independent_postgresql_gold(oracle_database, case_index):
    selected = context()
    refs = SchemaReferences.from_context(selected)
    columns = {column: key for key, (_, column) in refs.columns.items()}
    fields = [
        Projection(alias="row_count", aggregate="row_count"),
        Projection(reference=columns["amount"], alias="value_count", aggregate="value_count"),
        Projection(reference=columns["amount"], alias="total", aggregate="sum"),
    ]
    predicates = None
    grouping = ()
    if case_index == 1:
        fields.insert(0, Projection(reference=columns["entity_id"], alias="entity_id"))
        grouping = (columns["entity_id"],)
        predicates = PredicateGroup(
            kind="all",
            children=(
                Predicate(
                    reference=columns["region"],
                    operator="eq",
                    values=(ScalarValue(data_type="TEXT", value="North"),),
                ),
                Predicate(
                    reference=columns["event_date"],
                    operator="gte",
                    values=(ScalarValue(data_type="DATE", value="2032-09-01"),),
                ),
                Predicate(
                    reference=columns["event_date"],
                    operator="lt",
                    values=(ScalarValue(data_type="DATE", value="2032-10-01"),),
                ),
            ),
        )
    task = SemanticTask(
        operation="query",
        question="Calculate the requested source metrics.",
        population=Population(
            source="t0", grouping="entity", group_by=grouping, predicates=predicates
        ),
        output=OutputSelection(fields=tuple(fields)),
    )
    gateway = Mock()
    gateway.generate_structured.side_effect = AssertionError("No generation in execution oracle")
    pipeline = TextToSqlPipeline(
        Mock(), QueryCompiler(selected), SqlExecutor(oracle_database, 3000, 100), gateway
    )
    with semantic_request(RequestIdentity(OWNER, None, 71, task.question, "2032-10-15")):
        actual = pipeline.run(task.question, task=task).rows
    with oracle_database.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        independent = canonical(
            connection.execute(text(GOLD["cases"][case_index]["oracle_sql"])).mappings().all()
        )
    if case_index:
        actual.sort(key=lambda row: row["entity_id"])
    assert actual == independent == GOLD["cases"][case_index]["expected"]
    gateway.generate_structured.assert_not_called()


def test_average_uses_postgresql_and_independent_decimal_oracle(oracle_database):
    selected = context()
    refs = SchemaReferences.from_context(selected)
    amount = next(key for key, location in refs.columns.items() if location == ("events", "amount"))
    task = SemanticTask(
        operation="query",
        question="Compute the average source value.",
        population=Population(source="t0", grouping="entity"),
        output=OutputSelection(
            fields=(Projection(reference=amount, alias="average", aggregate="avg"),)
        ),
    )
    pipeline = TextToSqlPipeline(
        Mock(), QueryCompiler(selected), SqlExecutor(oracle_database, 3000, 100), Mock()
    )
    with semantic_request(RequestIdentity(OWNER, None, 71, task.question, "2032-10-15")):
        actual = pipeline.run(task.question, task=task).rows[0]["average"]
    with oracle_database.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        independent = connection.scalar(text("SELECT AVG(amount) FROM events"))
    values = [Decimal(row[2]) for row in GOLD["events"] if row[2] is not None]
    assert Decimal(actual) == independent == sum(values) / len(values)


def test_policy_oracle_distinguishes_missing_facts_from_zero_and_null(oracle_database):
    # This is the independent classification gold, not a production LEFT JOIN or
    # evidence that the production INNER-only pipeline handles missing entities.
    with oracle_database.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        rows = (
            connection.execute(
                text(
                    "SELECT d.entity_id, COUNT(f.event_id) AS fact_count, "
                    "COUNT(f.amount) AS value_count, SUM(f.amount) AS total "
                    "FROM entities d LEFT JOIN events f ON f.entity_id=d.entity_id "
                    "GROUP BY d.entity_id ORDER BY d.entity_id"
                )
            )
            .mappings()
            .all()
        )
    statuses = {
        row["entity_id"]: "insufficient_evidence"
        if row["total"] is None
        else "qualified"
        if row["total"] >= Decimal(GOLD["policy"]["threshold"])
        else "not_qualified"
        for row in rows
    }
    assert statuses == GOLD["expected_policy_status"]
    by_id = {row["entity_id"]: row for row in rows}
    assert by_id["E4"]["fact_count"] == 0 and by_id["E4"]["total"] is None
    assert by_id["E5"]["fact_count"] == 1 and by_id["E5"]["value_count"] == 0
    assert by_id["E2"]["total"] == Decimal("0.00") and by_id["E2"]["fact_count"] == 2
