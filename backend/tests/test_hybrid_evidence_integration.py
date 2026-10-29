"""Synthetic three-grain evidence verified against independent PostgreSQL VALUES."""

import json
import re
from decimal import Decimal

import pytest

from app.dependencies import (
    build_document_repository,
    build_workspace_context,
)
from app.rag.upload_parser import parse_document_file
from app.routing.hybrid import HybridAnswerDraft
from app.routing.router import RouteLabel
from app.semantic.wire import TaskProposal
from tests.auth_helpers import TEST_OWNER
from tests.hybrid_fixtures import (
    assert_decision_summary,
    classification_draft,
    prose_policy,
    rule_block,
)
from tests.join_domains import DOMAINS
from tests.plan_fixtures import decision_from_sql
from tests.semantic_fixtures import (
    proposal_for_evidence,
    proposal_from_plan,
    scoped_dataset_service,
)
from tests.test_guest_integration import OfflineEmbedder
from tests.test_join_domains_integration import domain_workspace, golden_sql, oracle  # noqa: F401

pytestmark = pytest.mark.integration
THRESHOLDS = {
    "logistics": "500000.00",
    "tuition": "30.00",
    "staffing": "12.50",
    "sales": "40.00",
    "energy": "12.50",
    "maintenance_holdout": "0.00",
}


@pytest.mark.parametrize(
    "domain_workspace", [(d, 19) for d in DOMAINS], indirect=True, ids=[d.name for d in DOMAINS]
)
@pytest.mark.parametrize("tables_count", [1, 2, 3])
@pytest.mark.parametrize("model", ["gemini", "inetcloud-knowledge"])
@pytest.mark.parametrize("natural", [False, True])
def test_structured_hybrid_cross_domain_postgres_oracle(
    domain_workspace,  # noqa: F811
    monkeypatch,
    tables_count,
    model,  # noqa: F811
    natural,
):
    domain, _, repository, dataset, settings, _, facts = domain_workspace
    threshold = THRESHOLDS[domain.name]
    key = domain.keys[0] if tables_count == 3 else domain.keys[1]
    policy = (
        prose_policy(key, domain.measure, threshold)
        if natural
        else rule_block(key, domain.measure, threshold)
    )
    embedder = OfflineEmbedder()
    build_document_repository(TEST_OWNER).add_document(
        dataset.dataset_id,
        parse_document_file("explicit_synthetic_rule.md", policy.encode(), max_bytes=10000),
        embedder,
    )
    dataset = repository.get(dataset.dataset_id)
    context = build_workspace_context(settings, dataset, repository)
    expected = oracle(facts, tables_count)
    # Neither SQL produced by the fake model nor production evaluator supplies this oracle.
    statuses = [
        "insufficient_evidence"
        if r["total"] is None
        else "qualified"
        if Decimal(r["total"]) >= Decimal(threshold)
        else "not_qualified"
        for r in expected
    ]
    calls = []

    class Gateway:
        def generate_structured(self, prompt, schema):
            calls.append(schema.__name__)
            if schema is TaskProposal:
                _task_route = RouteLabel.HYBRID
                if _task_route in {RouteLabel.RAG, RouteLabel.UNSUPPORTED}:
                    return proposal_for_evidence(
                        "documents" if _task_route == RouteLabel.RAG else "unavailable"
                    )
                _task_operation = "apply_policy" if _task_route == RouteLabel.HYBRID else "query"
            if schema is TaskProposal:
                return proposal_from_plan(
                    decision_from_sql(golden_sql(domain, dataset, tables_count), prompt),
                    _task_operation,
                )
            assert schema is HybridAnswerDraft
            assert json.dumps(expected, ensure_ascii=False) in prompt
            ids = [int(i) for i in re.findall(r"\[chunk_id=(\d+)", prompt)]
            assert len(ids) == 1
            # Deliberately reversed to prove identity binding, not model list position.
            draft = classification_draft(expected, statuses, ids[0])
            candidates = json.loads(
                prompt.split("Backend policy candidates: ", 1)[1].split("\n", 1)[0]
            )
            assert len(candidates) == 1
            draft.rule_id = candidates[0]["rule_id"]
            draft.decisions.reverse()
            return draft

        def generate_text(self, prompt):
            calls.append("answer")
            return "Untrusted intermediate narrative must not become final conclusions"

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    monkeypatch.setattr("app.dependencies.build_embedding_gateway", lambda _: embedder)
    response = scoped_dataset_service(
        settings.model_copy(update={"ai_default_model": model}),
        context,
    ).chat(domain.question + "; evaluate the explicit synthetic document rule")
    assert response.route == RouteLabel.HYBRID and response.rows == expected
    assert response.used_model == model and not response.fallback_used
    assert response.sql.count("JOIN") == tables_count - 1
    assert_decision_summary(response.answer, expected, statuses, language="vi")
    assert len(response.sources) == 1 and response.sources[0].content == policy
    assert calls == ["TaskProposal"]
    assert "Untrusted intermediate" not in response.answer
