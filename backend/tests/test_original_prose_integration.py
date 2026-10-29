"""Original saved prose, real scoped PostgreSQL retrieval/execution, fake providers."""

import json
import re

import pytest

from app.routing.hybrid import HybridAnswerDraft
from app.routing.router import RouteLabel
from app.semantic.wire import TaskProposal
from app.text_to_sql.query_plan import PlanDecision
from tests.gate_d_fixture import QUESTIONS
from tests.hybrid_fixtures import classification_draft
from tests.plan_fixtures import decision_from_sql
from tests.semantic_fixtures import assert_policy_rows, proposal_for_evidence, proposal_from_plan
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
            if schema is TaskProposal:
                _task_route = RouteLabel.HYBRID
                _task_operation = "apply_policy" if _task_route == RouteLabel.HYBRID else "query"
            if schema is TaskProposal:
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
                                "sort": [
                                    item.model_copy(update={"field": identity})
                                    if item.field == plan.fields[0].alias
                                    else item
                                    for item in plan.sort
                                ],
                            }
                        )
                    )
                proposal = proposal_from_plan(decision, _task_operation)
                if prompt.rsplit("Current request:\n", 1)[-1].startswith("Vậy còn"):
                    proposal.selection = "not_qualified"
                return proposal
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
        path + "/messages",
        json={"message": QUESTIONS["H"], "model_id": model},
    )
    assert sent.status_code == 200
    response = sent.json()["assistant_message"]["response"]
    if unsafe:
        assert response["error"] and response["rows"] == [] and response["sources"] == []
        assert response["sql"] is None and "Qualified:" not in response["answer"]
        assert actors.a.client.get(path).json()["messages"][-1]["response"] == response
        assert actors.b.client.get(path).status_code == 404
        assert calls == ["TaskProposal"]
        return
    assert response["error"] is None, response["error"]
    assert response["route"] == "HYBRID"
    assert response["verification_status"] == "verified_classification"
    # The omitted dimension key is a backend-issued output; never guessed from a label.
    assert_policy_rows(response["rows"], expected, "kho_id", response["answer_row_indices"])
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
    assert calls == ["TaskProposal"]
    followup = actors.a.client.post(
        path + "/messages", json={"message": "Vậy còn những kho chưa đạt KPI?", "model_id": model}
    )
    answer = followup.json()["assistant_message"]["response"]
    assert answer["error"] is None and answer["route"] == "HYBRID"
    assert set(re.search(r"Chưa đạt: ([^.]+)\.", answer["answer"])[1].split(", ")) == {
        "KHO01",
        "KHO04",
    }
    assert answer["sources"][0]["chunk_id"] == response["sources"][0]["chunk_id"]
    assert answer["verification_status"] == "verified_classification"
    assert calls == ["TaskProposal", "TaskProposal"]


@pytest.mark.parametrize("model", ["inetcloud-knowledge", "gemini"])
def test_verified_policy_premise_survives_real_history_and_retrieves_fresh_evidence(
    gate_d_workspace,  # noqa: F811
    monkeypatch,
    model,
):
    actors, dataset, facts, embedder = gate_d_workspace
    dataset = add_policy(actors, dataset, embedder, ORIGINAL)
    expected = {row["kho_id"]: row["total"] for row in independent_oracle(facts, "H")}
    calls = []

    class Gateway:
        def generate_structured(self, prompt, schema):
            calls.append(schema.__name__)
            assert schema is TaskProposal
            selection = (
                "not_qualified"
                if prompt.rsplit("Current request:\n", 1)[-1].startswith("Vậy còn")
                else "all"
            )
            if selection == "not_qualified":
                assert "Previous user questions" in prompt and "task_reference" in prompt
                assert "KHO02" not in prompt and "KHO03" not in prompt
                assert "Account 1" not in prompt
            return proposal_for_evidence("both", selection)

        def generate_text(self, prompt):
            raise AssertionError("Verified policy uses backend arithmetic, not model verdicts")

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    created = actors.a.client.post("/api/conversations", json={"dataset_id": dataset.dataset_id})
    path = "/api/conversations/" + created.json()["conversation_id"]
    questions = [
        "Theo chính sách KPI, những kho nào đạt và kho nào chưa đạt?",
        "Vậy còn những kho chưa đạt KPI?",
    ]
    for question in questions:
        sent = actors.a.client.post(
            path + "/messages", json={"message": question, "model_id": model}
        )
        assert sent.status_code == 200
        response = sent.json()["assistant_message"]["response"]
        assert response["error"] is None
        assert response["verification_status"] == "verified_classification"
        assert {row["entity_id"]: row["metric_value"] for row in response["rows"]} == expected
        assert set(re.search(r"Chưa đạt: ([^.]+)\.", response["answer"])[1].split(", ")) == {
            "KHO01",
            "KHO04",
        }
        assert response["sources"][0]["content"] == ORIGINAL.split("\n\n", 1)[1].strip()
        assert actors.a.client.get(path).json()["messages"][-1]["response"] == response
        assert actors.b.client.get(path).status_code == 404
    assert calls == ["TaskProposal", "TaskProposal"]
