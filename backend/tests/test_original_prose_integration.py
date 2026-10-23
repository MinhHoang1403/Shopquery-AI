"""Original saved prose, real scoped PostgreSQL retrieval/execution, fake providers."""

import json

import pytest

from app.routing.hybrid import HybridAnswerDraft
from app.routing.router import RouteDecision, RouteLabel
from app.text_to_sql.query_plan import PlanDecision
from tests.gate_d_fixture import QUESTIONS
from tests.hybrid_fixtures import classification_draft
from tests.plan_fixtures import decision_from_sql
from tests.test_auth_integration import accounts  # noqa: F401
from tests.test_gate_d_replay_integration import (
    add_policy,
    draft_sql,
    gate_d_workspace,  # noqa: F401
    independent_oracle,
)
from tests.test_natural_policy import ORIGINAL

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("model", ["inetcloud-knowledge", "gemini"])
@pytest.mark.parametrize("business_alias", [False, True])
@pytest.mark.parametrize("unsafe", [None, "exception", "unit_conflict"])
def test_original_prose_exact_kh_acceptance_and_history(
    gate_d_workspace,  # noqa: F811
    monkeypatch,
    model,
    business_alias,  # noqa: F811
    unsafe,
):
    actors, dataset, facts, embedder = gate_d_workspace
    policy = ORIGINAL
    if unsafe == "exception":
        policy += " Except warehouses on probation."
    elif unsafe == "unit_conflict":
        policy = policy.replace("VND", "USD")
    dataset = add_policy(actors, dataset, embedder, policy)
    expected = independent_oracle(facts, "H")
    if business_alias:
        for row in expected:
            row["so_dong_don"] = row.pop("fact_row_count")
    statuses = ["not_qualified", "qualified", "qualified", "not_qualified", "qualified"]
    calls = []
    candidates = []

    class Gateway:
        def generate_structured(self, prompt, schema):
            calls.append(schema.__name__)
            if schema is RouteDecision:
                if "Vậy còn" in prompt:
                    assert "Previous successful turns" in prompt
                    assert "KHO02, KHO03, KHO05" in prompt
                    assert "Account 1" not in prompt
                return RouteDecision(route=RouteLabel.HYBRID, reason="Offline original prose")
            if schema is PlanDecision:
                sql = draft_sql(dataset, "H")
                decision = decision_from_sql(
                    sql.replace("AS fact_row_count", "AS so_dong_don") if business_alias else sql,
                    prompt,
                )
                if not unsafe:
                    plan = decision.plan
                    identity = plan.fields[0].reference
                    decision = PlanDecision(
                        plan=plan.model_copy(
                            update={
                                "source": identity.split(".")[0],
                                "relationships": [],
                                "fields": plan.fields[1:],
                                "group_by": [ref for ref in plan.group_by if ref != identity],
                            }
                        )
                    )
                return decision
            assert schema is HybridAnswerDraft
            candidates.extend(
                json.loads(prompt.split("Backend policy candidates: ", 1)[1].split("\n", 1)[0])
            )
            assert unsafe and not candidates
            import re

            ids = [int(i) for i in re.findall(r"\[chunk_id=(\d+)", prompt)]
            draft = classification_draft(expected, statuses, ids[0], identity_field="kho_id")
            draft.rule_id = "invented-rule"
            return draft

        def generate_text(self, prompt):
            calls.append("answer")
            return "Intermediate text is not a second final decision set"

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    created = actors.a.client.post("/api/conversations", json={"dataset_id": dataset.dataset_id})
    path = "/api/conversations/" + created.json()["conversation_id"]
    sent = actors.a.client.post(
        path + "/messages", json={"message": QUESTIONS["H"], "model_id": model}
    )
    assert sent.status_code == 200
    response = sent.json()["assistant_message"]["response"]
    if unsafe:
        assert response["error"] and response["rows"] == [] and response["sources"] == []
        assert response["sql"] is None and "Qualified:" not in response["answer"]
        assert actors.a.client.get(path).json()["messages"][-1]["response"] == response
        assert actors.b.client.get(path).status_code == 404
        assert calls == ["RouteDecision", "PlanDecision", "HybridAnswerDraft"]
        return
    assert response["error"] is None, response["error"]
    assert response["route"] == "HYBRID"
    # The omitted dimension key is a backend-issued output; never guessed from a label.
    assert response["rows"] == expected
    assert response["used_model"] == model and not response["fallback_used"]
    assert "Đạt: KHO02, KHO03, KHO05." in response["answer"]
    assert response["sources"][0]["content"] == ORIGINAL.split("\n\n", 1)[1].strip()
    assert response["sources"][0]["source_file"] == "live_gate_d_kpi.md"
    lines = [
        line
        for line in response["answer"].splitlines()
        if line.startswith("| ") and any(row["kho_id"] in line for row in expected)
    ]
    assert len(lines) == 5
    for line, row, status in zip(lines, expected, statuses, strict=True):
        assert row["kho_id"] in line and row["total"] in line
        assert line.endswith("| Đạt |" if status == "qualified" else "| Chưa đạt |")
    assert actors.a.client.get(path).json()["messages"][-1]["response"] == response
    assert actors.b.client.get(path).status_code == 404
    assert calls == ["RouteDecision", "PlanDecision"]
    followup = actors.a.client.post(
        path + "/messages", json={"message": "Vậy còn những kho chưa đạt KPI?", "model_id": model}
    )
    answer = followup.json()["assistant_message"]["response"]
    assert answer["error"] is None and answer["route"] == "HYBRID"
    assert "Chưa đạt: KHO01, KHO04." in answer["answer"]
    assert answer["sources"][0]["chunk_id"] == response["sources"][0]["chunk_id"]
    assert calls == ["RouteDecision", "PlanDecision"] * 2
