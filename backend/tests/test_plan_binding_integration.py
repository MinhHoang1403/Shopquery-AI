"""Approved identity completion preserves independently checked PostgreSQL aggregates."""

import pytest
from sqlalchemy import text

from app.database.session import get_readonly_engine
from app.dependencies import _build_dataset_chat_service
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.query_plan import (
    PlanDecision,
    PlanExpression,
    PlanField,
    PlanFilter,
    QueryPlan,
)
from tests.join_domains import DOMAINS
from tests.test_join_domains_integration import domain_workspace  # noqa: F401
from tests.test_plan_providers import gateway_harness, response
from tests.test_query_compiler import field, source

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("domain_workspace", [(domain, 7) for domain in DOMAINS], indirect=True)
@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize("predicates", [False, True])
def test_dimension_identity_completion_matches_independent_postgresql(
    domain_workspace,  # noqa: F811
    monkeypatch,
    provider,
    predicates,
):
    domain, _, _, dataset, settings, context, _ = domain_workspace
    outer, inner, fact = (table.physical_table_name for table in dataset.tables)
    compiler = QueryCompiler(context)
    key = field(compiler, outer, domain.keys[0])
    name = field(compiler, outer, domain.names[0])
    measure = field(compiler, fact, domain.measure)
    nodes = [
        PlanExpression(operation="sum", arguments=[measure]),
        PlanExpression(operation="row_count"),
    ]
    if predicates:
        nodes += [
            PlanExpression(operation="literal", value="0", value_type="NUMERIC"),
            PlanExpression(operation="gt", arguments=[measure, "e2"]),
            PlanExpression(operation="literal", value="15", value_type="NUMERIC"),
            PlanExpression(operation="gte", arguments=["e0", "e4"]),
        ]
    plan = QueryPlan(
        source=source(compiler, fact),
        fields=[
            PlanField(reference=key, alias="entity_id"),
            PlanField(reference=name, alias="entity_name"),
            PlanField(reference="e0", alias="total"),
            PlanField(reference="e1", alias="n"),
        ],
        expressions=nodes,
        group_by=[key],
        filters=[PlanFilter(reference=measure, operator="ne", values=["10"])] if predicates else [],
        where="e3" if predicates else None,
        having="e5" if predicates else None,
    )
    replies = [
        response(provider, '{"route":"SQL","reason":"Independent fixture"}'),
        response(provider, PlanDecision(plan=plan).model_dump_json()),
    ]
    gateway, calls = gateway_harness(monkeypatch, provider, replies)
    try:
        result = _build_dataset_chat_service(settings, context, gateway).chat(domain.question)
        assert result.route == "SQL" and len(calls) == 2
        assert plan.group_by == [key]
        bindings = f"FROM uploaded_data.{fact} f "
        if domain.star:
            bindings += f"JOIN uploaded_data.{outer} d ON f.{domain.keys[0]}=d.{domain.keys[0]} "
        else:
            bindings += (
                f"JOIN uploaded_data.{inner} i ON f.{domain.keys[1]}=i.{domain.keys[1]} "
                f"JOIN uploaded_data.{outer} d ON i.{domain.keys[0]}=d.{domain.keys[0]} "
            )
        oracle = (
            f"SELECT d.{domain.keys[0]} AS entity_id, d.{domain.names[0]} AS entity_name, "
            f"SUM(f.{domain.measure})::text AS total, COUNT(*) AS n "
            + bindings
            + (f"WHERE f.{domain.measure}<>10 AND f.{domain.measure}>0 " if predicates else "")
            + f"GROUP BY d.{domain.keys[0]}, d.{domain.names[0]} "
            + (f"HAVING SUM(f.{domain.measure})>=15" if predicates else "")
        )
        with get_readonly_engine().connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout='3000ms'"))
            expected = [dict(row) for row in connection.execute(text(oracle)).mappings()]
        assert {row["entity_id"]: row for row in result.rows} == {
            row["entity_id"]: row for row in expected
        }
        assert ("WHERE" in result.sql) is predicates
        assert ("HAVING" in result.sql) is predicates
    finally:
        gateway.close()
