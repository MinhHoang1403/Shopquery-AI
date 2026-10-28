"""Context ordering and unrelated tables must not change verified JOIN semantics."""

from dataclasses import replace
from uuid import uuid4

import pytest

from app.core.errors import SqlUnsupportedError
from app.datasets.context import build_dataset_sql_context
from app.datasets.parser import ColumnSpec
from app.datasets.repository import DatasetTableInfo
from app.dependencies import build_dataset_chat_service
from app.routing.router import RouteDecision, RouteLabel
from app.text_to_sql.query_plan import PlanDecision
from app.text_to_sql.validator import SqlValidator
from tests import test_join_domains_integration as domain_tests
from tests.join_domains import DOMAINS
from tests.plan_fixtures import decision_from_sql
from tests.test_join_domains_integration import golden_sql, oracle

pytestmark = pytest.mark.integration
domain_workspace = domain_tests.domain_workspace


@pytest.mark.parametrize(
    "domain_workspace",
    [(domain, 19) for domain in DOMAINS],
    indirect=True,
    ids=[domain.name for domain in DOMAINS],
)
@pytest.mark.parametrize("model", ["inetcloud-knowledge", "gemini"])
@pytest.mark.parametrize("reverse_columns", [False, True])
def test_context_permutations_and_multiple_unrelated_tables_keep_oracle(
    domain_workspace, monkeypatch: pytest.MonkeyPatch, model: str, reverse_columns: bool
) -> None:
    domain, _, _, dataset, settings, original, facts = domain_workspace
    extra = tuple(
        DatasetTableInfo(
            f"Unrelated {index}",
            None,
            "dataset_" + uuid4().hex,
            (ColumnSpec("External code", "external_code", "TEXT"),),
            0,
        )
        for index in range(2)
    )
    tables = (
        tuple(
            replace(table, columns=table.columns[::-1] if reverse_columns else table.columns)
            for table in dataset.tables[::-1]
        )
        + extra
    )
    context = build_dataset_sql_context(
        replace(dataset, tables=tables, table=tables[0]),
        approved_joins=original.approved_joins,
        join_v1_enabled=True,
    )
    assert context.table_columns == {
        **original.table_columns,
        **{table.physical_table_name: {"external_code"} for table in extra},
    }
    assert context.approved_joins == original.approved_joins
    expected = oracle(facts, 3)

    class Gateway:
        def generate_structured(self, prompt, schema):
            assert all(table.physical_table_name in prompt for table in tables)
            if schema is RouteDecision:
                return RouteDecision(
                    evidence_requirement="tables",
                    route=RouteLabel.SQL,
                    reason="Offline permutation",
                )
            assert schema is PlanDecision
            return decision_from_sql(golden_sql(domain, dataset, 3), prompt)

        def generate_text(self, prompt):
            return "Offline synthetic answer"

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    result = build_dataset_chat_service(
        settings.model_copy(update={"ai_default_model": model}), context
    ).chat(domain.question)
    assert result.route == RouteLabel.SQL and result.rows == expected
    assert result.used_model == model and not result.fallback_used
    checked = SqlValidator(
        context.table_columns,
        context.allowed_schemas,
        max_tables=3,
        approved_joins=context.approved_joins,
        column_types=context.column_types,
        join_v1_enabled=True,
    )
    for table in extra:
        fact = next(t for t in dataset.tables if t.display_name == domain.labels[2])
        with pytest.raises(SqlUnsupportedError) as caught:
            checked.validate(
                f"SELECT a.{domain.keys[1]} FROM uploaded_data.{fact.physical_table_name} a "
                f"INNER JOIN uploaded_data.{table.physical_table_name} b "
                f"ON a.{domain.keys[1]}=b.external_code"
            )
        assert caught.value.code == "join_relationship"
