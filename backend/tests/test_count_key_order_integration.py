"""Prove INNER-key COUNT ordering equivalence on synthetic PostgreSQL data."""

import json

import pytest
from sqlglot import parse_one

from app.database.session import get_readonly_engine
from app.dependencies import build_dataset_chat_service
from app.routing.router import RouteDecision, RouteLabel
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.query_plan import PlanDecision
from app.text_to_sql.validator import ValidatedSql
from tests.join_domains import DOMAINS
from tests.plan_fixtures import decision_from_sql
from tests.test_join_domains_integration import (
    domain_workspace,  # noqa: F401
    golden_sql,
    oracle,
)
from tests.test_three_table_join_integration import scoped_validator

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "domain_workspace",
    [(d, 7) for d in DOMAINS],
    indirect=True,
    ids=[d.name for d in DOMAINS],
)
@pytest.mark.parametrize("tables_count", [2, 3])
@pytest.mark.parametrize("selected_key", [False, True])
def test_count_key_order_differential(
    domain_workspace,  # noqa: F811
    monkeypatch,
    tables_count,
    selected_key,
):
    domain, _, _, dataset, settings, context, facts = domain_workspace
    expected = oracle(facts, tables_count, filtered=domain.name == "energy")
    expected.sort(key=lambda row: (-row["fact_row_count"], row["entity_id"]))
    expected = expected[:2]
    canonical = golden_sql(domain, dataset, tables_count, filtered=domain.name == "energy")
    canonical = canonical.replace(
        "ORDER BY entity_id", "ORDER BY fact_row_count DESC NULLS LAST,entity_id LIMIT 2"
    )
    key_count = f"COUNT(f.{domain.keys[1]})"
    draft = (
        canonical.replace("COUNT(*) AS fact_row_count", f"{key_count} AS fact_row_count")
        if selected_key
        else canonical
    )
    draft = draft.replace(
        "ORDER BY fact_row_count", "ORDER BY " + ("COUNT(*)" if selected_key else key_count)
    )
    executor = SqlExecutor(get_readonly_engine(), timeout_ms=5000, max_rows=200)
    # Only test-authored synthetic SQL bypasses validation to establish the independent proof.
    assert executor.execute(ValidatedSql(canonical, frozenset())) == expected
    assert executor.execute(ValidatedSql(draft, frozenset())) == expected
    validated = scoped_validator(context).validate(draft)
    assert "ORDER BY fact_row_count DESC" in validated.statement
    before, after = (
        parse_one(draft, read="postgres"),
        parse_one(validated.statement, read="postgres"),
    )
    for clause in ("where", "group", "limit"):
        assert before.args.get(clause) == after.args.get(clause)
    # A verified star may reorder its two INNER edges; predicates and multiplicity may not change.
    assert sorted(j.args["on"].sql(dialect="postgres") for j in before.args["joins"]) == sorted(
        j.args["on"].sql(dialect="postgres") for j in after.args["joins"]
    )
    assert before.args["from_"].this == after.args["from_"].this
    assert (
        before.args["order"].expressions[0].args["desc"]
        == after.args["order"].expressions[0].args["desc"]
    )
    assert (
        before.args["order"].expressions[0].args["nulls_first"]
        == after.args["order"].expressions[0].args["nulls_first"]
    )
    assert scoped_validator(context).validate(validated.statement) == validated

    class Gateway:
        def generate_structured(self, prompt, schema):
            if schema is RouteDecision:
                return RouteDecision(route=RouteLabel.SQL, reason="Synthetic offline")
            assert schema is PlanDecision
            return decision_from_sql(draft, prompt)

        def generate_text(self, prompt):
            assert json.dumps(expected, ensure_ascii=False) in prompt
            return json.dumps(expected)

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    model = "gemini" if selected_key else "inetcloud-knowledge"
    response = build_dataset_chat_service(
        settings.model_copy(update={"ai_default_model": model}), context
    ).chat(domain.question)
    assert response.route == RouteLabel.SQL and response.rows == expected
    assert json.loads(response.answer) == expected
    assert response.used_model == model and not response.fallback_used


@pytest.mark.parametrize("domain_workspace", [(DOMAINS[0], 7)], indirect=True)
@pytest.mark.parametrize(
    "shape",
    [
        "wrong_alias",
        "bare",
        "order_unselected",
        "having",
        "arithmetic",
        "nested",
        "nullable_row",
        "distinct",
        "dimension",
        "filter",
        "unqualified",
        "quoted_case",
    ],
)
def test_postgresql_legal_count_shapes_remain_outside_the_join_contract(
    domain_workspace,  # noqa: F811
    shape,
):
    from app.core.errors import SqlValidationError

    domain, _, _, dataset, _, context, facts = domain_workspace
    expected = oracle(facts, 3)
    sql = golden_sql(domain, dataset, 3)
    original = "COUNT(*) AS fact_row_count"
    if shape == "wrong_alias":
        sql = sql.replace(original, "COUNT(*) AS wrong")
    elif shape == "bare":
        sql = sql.replace(original, "COUNT(*)")
    elif shape == "order_unselected":
        sql = sql.replace(original + ",", "").replace(
            "ORDER BY entity_id", "ORDER BY COUNT(*) DESC,entity_id"
        )
    elif shape == "having":
        sql = sql.replace("ORDER BY entity_id", "HAVING COUNT(*)>0 ORDER BY entity_id")
    elif shape == "arithmetic":
        sql = sql.replace(original, "COUNT(*)+1 AS fact_row_count")
    elif shape == "nested":
        sql = sql.replace(original, "COALESCE(COUNT(*),0) AS fact_row_count")
    elif shape == "nullable_row":
        sql = sql.replace(original, f"COUNT(f.{domain.measure}) AS fact_row_count")
    elif shape == "distinct":
        sql = sql.replace(original, f"COUNT(DISTINCT f.{domain.keys[1]}) AS fact_row_count")
    elif shape == "dimension":
        sql = sql.replace(original, f"COUNT(k.{domain.keys[0]}) AS fact_row_count")
    elif shape == "filter":
        sql = sql.replace(
            original, f"COUNT(*) FILTER(WHERE f.{domain.measure}>0) AS fact_row_count"
        )
    elif shape == "unqualified":
        sql = sql.replace(original, f"COUNT({domain.measure}) AS fact_row_count")
    else:
        sql = sql.replace(original, 'COUNT(*) AS "FACT_ROW_COUNT"')
    rows = SqlExecutor(get_readonly_engine(), timeout_ms=5000, max_rows=200).execute(
        ValidatedSql(sql, frozenset())
    )
    rows.sort(key=lambda row: row["entity_id"])
    assert [(r["entity_id"], r["total"], r["fact_value_count"]) for r in rows] == [
        (r["entity_id"], r["total"], r["fact_value_count"]) for r in expected
    ]
    expected_counts = [r["fact_row_count"] for r in expected]
    name = "fact_row_count"
    if shape == "wrong_alias":
        name = "wrong"
    elif shape == "bare":
        name = "count"
    elif shape == "quoted_case":
        name = "FACT_ROW_COUNT"
    if shape == "arithmetic":
        expected_counts = [n + 1 for n in expected_counts]
    elif shape in {"nullable_row", "unqualified"}:
        expected_counts = [r["fact_value_count"] for r in expected]
    elif shape == "distinct":
        expected_counts = [2, 1, 1]
    elif shape == "filter":
        expected_counts = [2, 1, 0]
    if shape != "order_unselected":
        assert [r[name] for r in rows] == expected_counts
    if shape in {"wrong_alias", "bare"}:
        checked = scoped_validator(context).validate(sql)
        assert checked.count_metrics[0].kind.value == "row_count"
        assert SqlExecutor(get_readonly_engine(), 5000, 200).execute(checked) == rows
    else:
        with pytest.raises(SqlValidationError):
            scoped_validator(context).validate(sql)
