"""Independent document and SQL oracles for two non-logistics Hybrid policies."""

import json
import re
from decimal import Decimal

import pytest

from app.core.diagnostics import diagnostic_request
from app.dependencies import (
    build_dataset_chat_service,
    build_document_repository,
    build_workspace_context,
)
from app.rag.upload_parser import parse_document_file
from app.routing.hybrid import HybridAnswerDraft
from app.routing.router import RouteDecision, RouteLabel
from app.text_to_sql.generator import SqlDraft
from tests.auth_helpers import TEST_OWNER
from tests.hybrid_fixtures import assert_decision_summary, classification_draft, rule_block
from tests.join_domains import DOMAINS
from tests.test_guest_integration import OfflineEmbedder
from tests.test_join_domains_integration import (
    domain_workspace,  # noqa: F401
    golden_sql,
    oracle,
)

pytestmark = pytest.mark.integration
POLICIES = {
    "tuition": "Mỗi course đạt nếu tổng amount_paid >= 30.00 source. "
    "Tính tất cả dòng. Phân biệt từng course theo mã course_id.",
    "staffing": "Mỗi department đạt nếu tổng hours >= 12.50 source. "
    "Tính tất cả dòng. Phân biệt từng department theo mã department_id.",
}


@pytest.mark.parametrize(
    "domain_workspace",
    [(d, 19) for d in DOMAINS if d.name in POLICIES],
    indirect=True,
    ids=list(POLICIES),
)
@pytest.mark.parametrize("model", ["inetcloud-knowledge", "gemini"])
@pytest.mark.parametrize("filtered", [False, True])
@pytest.mark.parametrize("business_aliases", [False, True])
def test_hybrid_policy_and_count_order_with_explicit_filter(
    domain_workspace,  # noqa: F811
    monkeypatch,
    model,
    filtered,
    business_aliases,
):
    domain, _, repository, dataset, settings, _, facts = domain_workspace
    policy = POLICIES[domain.name]
    # The document oracle reads its own fixture; no threshold is inferred from SQL/model output.
    threshold = Decimal(re.search(r">= (\d+\.\d+)", policy).group(1))
    if not filtered:
        policy += "\n" + rule_block(domain.keys[0], domain.measure, str(threshold))
    embedder = OfflineEmbedder()
    filename = domain.keys[0].removesuffix("_id") + "_policy.md"
    build_document_repository(TEST_OWNER).add_document(
        dataset.dataset_id,
        parse_document_file(filename, policy.encode(), max_bytes=10000),
        embedder,
    )
    dataset = repository.get(dataset.dataset_id)
    context = build_workspace_context(settings, dataset, repository)
    expected = oracle(facts, 3, filtered)
    qualified = [
        r["entity_id"]
        for r in expected
        if r["total"] is not None and Decimal(r["total"]) >= threshold
    ]
    statuses = [
        "insufficient_evidence"
        if r["total"] is None
        else "unverified"
        if filtered
        else "qualified"
        if r["entity_id"] in qualified
        else "not_qualified"
        for r in expected
    ]
    sql = golden_sql(domain, dataset, 3, filtered)
    sql = sql.replace("COUNT(*) AS fact_row_count", f"COUNT(f.{domain.keys[1]}) AS fact_row_count")
    sql = sql.replace("ORDER BY entity_id", "ORDER BY COUNT(*) DESC,entity_id")
    expected.sort(key=lambda row: (-row["fact_row_count"], row["entity_id"]))
    if business_aliases:
        sql = sql.replace("AS fact_row_count", "AS event_rows").replace(
            "AS fact_value_count", "AS measured_values"
        )
        for row in expected:
            row["event_rows"] = row.pop("fact_row_count")
            row["measured_values"] = row.pop("fact_value_count")
    calls = []

    class Gateway:
        def generate_structured(self, prompt, schema):
            calls.append(schema.__name__)
            if schema is RouteDecision:
                return RouteDecision(route=RouteLabel.HYBRID, reason="Scripted policy test")
            if schema is SqlDraft:
                assert "document conditions are applied after SQL execution" in prompt
                assert "Preserve filters explicitly requested" in prompt
                assert policy not in prompt
                assert str(threshold) not in prompt
                return SqlDraft(sql=sql)
            assert schema is HybridAnswerDraft
            if business_aliases:
                assert '"field": "event_rows", "kind": "row_count"' in prompt
                assert '"field": "measured_values", "kind": "non_null_value_count"' in prompt
            assert policy in prompt and json.dumps(expected, ensure_ascii=False) in prompt
            ids = [int(value) for value in re.findall(r"\[chunk_id=(\d+)", prompt)]
            assert len(ids) == 1
            return classification_draft(expected, statuses, ids[0], verified=not filtered)

        def generate_text(self, prompt):
            calls.append("answer")
            assert json.dumps(expected, ensure_ascii=False) in prompt
            return json.dumps(expected)

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    monkeypatch.setattr("app.dependencies.build_embedding_gateway", lambda _: embedder)
    question = domain.question + "; đối chiếu điều kiện trong tài liệu, không đoán ngưỡng."
    if filtered:
        question += " Chỉ xét tháng 9/2025 theo giờ Việt Nam."
    with diagnostic_request() as trace:
        response = build_dataset_chat_service(
            settings.model_copy(update={"ai_default_model": model}),
            context,
        ).chat(question)
    assert response.route == RouteLabel.HYBRID and response.rows == expected
    assert_decision_summary(response.answer, expected, statuses)
    assert response.used_model == model and not response.fallback_used
    assert len(response.sources) == 1 and response.sources[0].source_file == filename
    assert response.sources[0].content == policy
    assert calls == ["RouteDecision", "SqlDraft", "answer", "HybridAnswerDraft"]
    assert trace.facts["sql_validated"] and trace.facts["execution_reached"]
    assert ("2025-09-01" in response.sql) is filtered
