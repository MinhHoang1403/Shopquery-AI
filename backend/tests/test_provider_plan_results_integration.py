"""Provider serialization reaches real SELECT execution and independent numeric oracles."""

import json
from decimal import Decimal

import pytest

from app.dependencies import _build_dataset_chat_service
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.query_plan import PlanDecision, PlanExpression, PlanField, PlanSort, QueryPlan
from tests.join_domains import DOMAINS
from tests.test_join_domains_integration import domain_workspace, oracle  # noqa: F401
from tests.test_plan_providers import gateway_harness, response
from tests.test_query_compiler import field, source

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize("case", ["count", "sum", "count_sum", "group", "join_two", "join_three"])
@pytest.mark.parametrize("domain_workspace", [(DOMAINS[4], 19), (DOMAINS[5], 19)], indirect=True)
def test_provider_count_sum_group_and_approved_joins_match_oracle(
    monkeypatch,
    provider,
    case,
    domain_workspace,  # noqa: F811
):
    domain, _, _, dataset, settings, context, facts = domain_workspace
    tables = {table.display_name: table.physical_table_name for table in dataset.tables}
    outer, inner, fact = (tables[name] for name in domain.labels)
    compiler = QueryCompiler(context)
    total = sum((Decimal(row[4]) for row in facts if row[4] is not None), Decimal("0.00"))
    grouped = case in {"group", "join_two", "join_three"}
    table_count = 3 if case == "join_three" else 2 if case == "join_two" else 1
    entity = outer if table_count == 3 else inner if table_count == 2 else fact
    key = domain.keys[0] if table_count == 3 else domain.keys[1]
    projections, group_by, relationships = [], [], []
    if grouped:
        identity = field(compiler, entity, key)
        projections.append(PlanField(reference=identity, alias="entity_id"))
        group_by.append(identity)
        if table_count >= 2:
            name = domain.names[0] if table_count == 3 else domain.names[1]
            label = field(compiler, entity, name)
            projections.append(PlanField(reference=label, alias="entity_name"))
            group_by.append(label)
            relationships = [
                key
                for key, edge in compiler.references.relationships.items()
                if table_count == 3 or (edge.source_table == fact and edge.target_table == inner)
            ]
    expressions = []
    if case != "sum":
        expressions.append(PlanExpression(operation="row_count", arguments=[]))
        projections.append(PlanField(reference="e0", alias="fact_row_count"))
    if case != "count":
        projections.append(PlanField(reference=f"e{len(expressions)}", alias="total"))
        expressions.append(
            PlanExpression(operation="sum", arguments=[field(compiler, fact, domain.measure)])
        )
    decision = PlanDecision(
        plan=QueryPlan(
            source=source(compiler, fact),
            fields=projections,
            expressions=expressions,
            relationships=relationships,
            group_by=group_by,
            sort=[PlanSort(field="entity_id", direction="asc")] if grouped else [],
        )
    )
    if grouped:
        expected = [
            {
                key: row[key]
                for key in ("entity_id", "entity_name", "fact_row_count", "total")
                if key in row
            }
            for row in oracle(facts, table_count)
        ]
    else:
        expected = [
            {
                **({"fact_row_count": len(facts)} if case != "sum" else {}),
                **({"total": format(total, "f")} if case != "count" else {}),
            }
        ]
    gateway, calls = gateway_harness(
        monkeypatch,
        provider,
        [
            response(
                provider,
                '{"route":"SQL","reason":"Synthetic fixture","evidence_requirement":"tables",'
                '"policy_intent":"none","policy_scope":"unspecified"}',
            ),
            response(provider, decision.model_dump_json()),
        ],
    )
    try:
        result = _build_dataset_chat_service(settings, context, gateway).chat(domain.question)
        assert result.rows == expected
        assert result.sql.count("JOIN") == table_count - 1
        assert "WHERE" not in result.sql and len(calls) == 2
        assert "GenerationDecision" in json.dumps(json.loads(calls[1].content))
    finally:
        gateway.close()
