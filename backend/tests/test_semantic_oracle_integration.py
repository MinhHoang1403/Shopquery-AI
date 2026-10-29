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


@pytest.mark.parametrize("direction,expected_id", [("asc", "E1"), ("desc", "E3")])
def test_bound_policy_expression_order_matches_independent_postgres_selection(
    oracle_database, direction, expected_id
):
    from dataclasses import replace

    from app.routing.hybrid import HybridPipeline
    from app.semantic.task import Ordering, PolicyRequirement
    from app.text_to_sql.join_policy import ApprovedJoin
    from app.text_to_sql.query_plan import PlanExpression
    from tests.hybrid_fixtures import prose_policy, scoped_chunk

    selected = context()
    selected = replace(
        selected,
        table_columns={**selected.table_columns, "entities": {"entity_id"}},
        allowed_schemas={**selected.allowed_schemas, "entities": "pg_temp"},
        column_types={**selected.column_types, "entities": {"entity_id": "TEXT"}},
        approved_joins=(
            ApprovedJoin(
                "entity-edge", "events", "entity_id", "entities", "entity_id", "isolated-oracle"
            ),
        ),
    )
    refs = SchemaReferences.from_context(selected)
    amount = next(key for key, source in refs.columns.items() if source == ("events", "amount"))
    identity = next(
        key for key, source in refs.columns.items() if source == ("entities", "entity_id")
    )
    chunk = scoped_chunk(
        41,
        "policy.md",
        "Policy",
        prose_policy("entity_id", "amount", GOLD["policy"]["threshold"]),
        0.1,
    )
    chunk = replace(
        chunk, document_scope=replace(chunk.document_scope, dataset_id=71, owner_user_id=OWNER)
    )
    request = SemanticTask(
        operation="apply_policy",
        question="Select the first qualifying entity by the verified metric.",
        population=Population(
            grouping="entity",
            predicates=Predicate(
                reference=identity,
                operator="in",
                values=tuple(
                    ScalarValue(data_type="TEXT", value=key) for key in ("E1", "E2", "E3")
                ),
            ),
        ),
        output=OutputSelection(
            classification="qualified",
            ordering=(Ordering(field="e0", direction=direction),),
            limit=1,
        ),
        expressions=(PlanExpression(operation="sum", arguments=[amount]),),
        policy=PolicyRequirement(description="Apply the saved policy to the selected entities."),
    )
    gateway = Mock()
    sql = TextToSqlPipeline(
        Mock(), QueryCompiler(selected), SqlExecutor(oracle_database, 3000, 100), gateway
    )
    hybrid = HybridPipeline(sql, Mock(retrieve=Mock(return_value=[chunk])), gateway, selected)
    with semantic_request(RequestIdentity(OWNER, None, 71, request.question, "2032-10-15")):
        result = hybrid.run(request.question, task=request)
    indices = (
        range(len(result.rows)) if result.answer_row_indices is None else result.answer_row_indices
    )
    visible = [result.rows[index] for index in indices]
    with oracle_database.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        independent = (
            connection.execute(
                text(
                    "SELECT d.entity_id, SUM(f.amount) AS total FROM entities d "
                    "JOIN events f ON f.entity_id=d.entity_id "
                    "WHERE d.entity_id IN ('E1','E2','E3') GROUP BY d.entity_id "
                    "HAVING SUM(f.amount) >= CAST(:threshold AS NUMERIC) "
                    f"ORDER BY SUM(f.amount) {direction}, d.entity_id LIMIT 1"
                ),
                {"threshold": GOLD["policy"]["threshold"]},
            )
            .mappings()
            .one()
        )
    assert result.verification_status == "verified_classification"
    assert len(result.rows) == 3 and len(visible) == 1
    assert visible[0]["entity_id"] == independent["entity_id"] == expected_id
    assert Decimal(visible[0]["metric_value"]) == independent["total"]
    assert {row["entity_id"]: row["metric_value"] for row in result.rows}["E2"] == "0.00"
    gateway.generate_structured.assert_not_called()


def test_compact_generation_measures_and_condition_execute_against_independent_oracle(
    oracle_database,
):
    from app.routing.router import QueryRouter
    from app.semantic.wire import TaskProposal
    from tests.semantic_fixtures import proposal

    selected = context()
    data = proposal()
    data.update(
        fields=[
            {"reference": "", "alias": "row_count", "aggregation": "row_count"},
            {
                "reference": "column:t0.amount",
                "alias": "non_null_values",
                "aggregation": "non_null_count",
            },
            {"reference": "column:t0.amount", "alias": "total", "aggregation": "sum"},
        ],
        expressions=[],
        conditions=[
            {
                "kind": "comparison",
                "left": "column:t0.amount",
                "operator": "gte",
                "values": ["0.00"],
                "value_type": "NUMERIC",
                "children": [],
            }
        ],
        where="p0",
    )
    gateway = Mock(generate_structured=Mock(return_value=TaskProposal.model_validate(data)))
    pipeline = TextToSqlPipeline(
        Mock(), QueryCompiler(selected), SqlExecutor(oracle_database, 3000, 100), gateway
    )
    question = "Count records and sum the selected source values."
    with semantic_request(RequestIdentity(OWNER, None, 71, question, "2032-10-15")):
        task = QueryRouter(gateway, context=selected).route(question).task
        actual = pipeline.run(question, task=task).rows
    with oracle_database.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        independent = dict(
            connection.execute(
                text(
                    "SELECT COUNT(*) AS row_count, COUNT(amount) AS non_null_values, "
                    "SUM(amount)::text AS total FROM events WHERE amount >= CAST(:zero AS NUMERIC)"
                ),
                {"zero": "0.00"},
            )
            .mappings()
            .one()
        )
    assert actual == [independent] == [{"row_count": 5, "non_null_values": 5, "total": "150.00"}]
    gateway.generate_structured.assert_called_once()
    gateway.generate_text.assert_not_called()


@pytest.mark.parametrize("provider", ["inetcloud-knowledge", "gemini"])
def test_captured_provider_filter_executes_against_independent_postgres_oracle(
    oracle_database, provider
):
    from app.routing.router import QueryRouter
    from app.semantic.wire import TaskProposal

    captures = json.loads(
        Path(__file__)
        .with_name("fixtures")
        .joinpath("semantic_provider_proposals.json")
        .read_text(encoding="utf-8")
    )["records"]
    captured = next(c for c in captures if c["provider"] == provider and c["case"] == "p14")
    # Independent boundary values include the strict threshold, NULL, and two matches.
    with oracle_database.begin() as connection:
        connection.execute(
            text(
                "CREATE TEMP TABLE hotels(hotel_id TEXT PRIMARY KEY, name TEXT, "
                "province TEXT, room_count BIGINT)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO hotels VALUES ('H1','A','North',119),('H2','B','South',120),"
                "('H3','C','North',121),('H4','D','South',200),('H5','E','North',NULL)"
            )
        )
    selected = DatasetSqlContext(
        "Synthetic provider execution replay, no live generation",
        {"hotels": {"hotel_id", "name", "province", "room_count"}},
        {"hotels": "pg_temp"},
        dataset_id=71,
        owner_user_id=OWNER,
        column_types={
            "hotels": {
                "hotel_id": "TEXT",
                "name": "TEXT",
                "province": "TEXT",
                "room_count": "BIGINT",
            }
        },
    )
    gateway = Mock(
        generate_structured=Mock(return_value=TaskProposal.model_validate(captured["proposal"]))
    )
    pipeline = TextToSqlPipeline(
        Mock(), QueryCompiler(selected), SqlExecutor(oracle_database, 3000, 100), gateway
    )
    with semantic_request(RequestIdentity(OWNER, None, 71, captured["question"], "2026-10-29")):
        task = QueryRouter(gateway, context=selected).route(captured["question"]).task
        result = pipeline.run(captured["question"], task=task)
    with oracle_database.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        expected = connection.execute(
            text("SELECT name, room_count FROM hotels WHERE room_count > 120 ORDER BY name")
        ).all()
    name_alias = "name" if provider == "inetcloud-knowledge" else "hotel_name"
    assert (
        sorted((r[name_alias], r["room_count"]) for r in result.rows)
        == expected
        == [("C", 121), ("D", 200)]
    )
    assert result.answer
    gateway.generate_structured.assert_called_once()
    gateway.generate_text.assert_not_called()


def test_district_literal_mismatch_is_not_an_equivalent_postgres_population(oracle_database):
    # Counterexample, not a claim that these are pre-existing source rows or a repair map.
    with oracle_database.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        populations = {}
        for value in ("quận 3", "3"):
            populations[value] = (
                connection.execute(
                    text(
                        "SELECT branch_id FROM (VALUES ('B1','quận 3'),('B2','3')) "
                        "AS source(branch_id,district) WHERE district = :value"
                    ),
                    {"value": value},
                )
                .scalars()
                .all()
            )
    assert populations == {"quận 3": ["B1"], "3": ["B2"]}
