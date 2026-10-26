"""Differential PostgreSQL checks of selected COUNT sorting, with offline gateways."""

import json

import pytest

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
    [(domain, (0, 7, 19)[index % 3]) for index, domain in enumerate(DOMAINS)],
    indirect=True,
    ids=[domain.name for domain in DOMAINS],
)
@pytest.mark.parametrize("tables_count", [2, 3])
@pytest.mark.parametrize("value_count", [False, True])
def test_selected_count_sort_matches_independent_oracle(
    domain_workspace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tables_count: int,
    value_count: bool,
) -> None:
    domain, _, _, dataset, settings, context, facts = domain_workspace
    expected = oracle(facts, tables_count, filtered=domain.name == "energy")
    alias = "fact_value_count" if value_count else "fact_row_count"
    expected.sort(key=lambda row: (-row[alias], row["entity_id"]))
    canonical = golden_sql(domain, dataset, tables_count, filtered=domain.name == "energy")
    canonical = canonical.replace("ORDER BY entity_id", f"ORDER BY {alias} DESC,entity_id")
    count = f"COUNT(f.{domain.measure})" if value_count else "COUNT(*)"
    repeated = canonical.replace(f"ORDER BY {alias}", f"ORDER BY {count}")
    executor = SqlExecutor(get_readonly_engine(), timeout_ms=5000, max_rows=200)
    # Execute only these test-authored synthetic statements directly to establish SQL semantics.
    assert executor.execute(ValidatedSql(canonical, frozenset())) == expected
    assert executor.execute(ValidatedSql(repeated, frozenset())) == expected
    scoped_validator(context).validate(repeated)
    calls: list[str] = []

    class Gateway:
        def generate_structured(self, prompt, response_model):
            calls.append(response_model.__name__)
            if response_model is RouteDecision:
                return RouteDecision(route=RouteLabel.SQL, reason="Offline scripted route")
            assert response_model is PlanDecision
            return decision_from_sql(repeated, prompt)

        def generate_text(self, prompt: str) -> str:
            calls.append("answer")
            assert json.dumps(expected, ensure_ascii=False) in prompt
            return json.dumps(expected, ensure_ascii=False)

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    model = "gemini" if tables_count == 3 else "inetcloud-knowledge"
    service = build_dataset_chat_service(
        settings.model_copy(update={"ai_default_model": model}), context
    )
    question = (
        "Theo từng mã và tên, tính tổng, trung bình, đếm dòng và giá trị; sắp giảm dần."
        if value_count
        else "Liệt kê theo mã riêng và tên, tổng, trung bình, số dòng và số giá trị có dữ liệu."
    )
    response = service.chat(question)
    assert response.route == RouteLabel.SQL
    assert response.rows == expected
    assert response.rows == expected and response.answer
    assert response.used_model == model and response.fallback_used is False
    assert calls == ["RouteDecision", "PlanDecision"]
    assert f"ORDER BY {alias}" in response.sql
