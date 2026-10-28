"""Evidence dispatch contracts; scripted intents do not measure LLM accuracy."""

import json
from unittest.mock import Mock

import pytest

from app.core.diagnostics import diagnostic_request, record_facts
from app.core.errors import ModelResponseError
from app.core.observability import safe_metadata
from app.routing.router import QueryRouter, RouteDecision, RouteLabel
from app.routing.service import DatasetChatService
from tests.test_plan_providers import gateway_harness, response


@pytest.mark.parametrize(
    "evidence,expected",
    [
        ("documents", RouteLabel.RAG),
        ("tables", RouteLabel.SQL),
        ("both", RouteLabel.HYBRID),
        ("unavailable", RouteLabel.UNSUPPORTED),
        ("unclear", RouteLabel.UNSUPPORTED),
    ],
)
def test_evidence_requirement_controls_dispatch_even_when_model_label_disagrees(evidence, expected):
    gateway = Mock()
    gateway.generate_structured.return_value = RouteDecision.model_validate(
        {
            "route": "HYBRID",
            "reason": "Untrusted explanation",
            "evidence_requirement": evidence,
            "policy_intent": "qualified",
            "policy_scope": "all_entities",
        }
    )
    decision = QueryRouter(gateway).route("Câu hỏi không được dùng làm keyword override")
    assert decision.route == expected
    if expected != RouteLabel.HYBRID:
        assert decision.policy_intent == "none" and decision.policy_scope == "unspecified"
    gateway.generate_structured.assert_called_once()


def test_missing_evidence_fails_closed_without_sql_rag_or_second_classifier():
    gateway, sql, rag, hybrid = Mock(), Mock(), Mock(), Mock()
    gateway.generate_structured.return_value = RouteDecision(route="HYBRID", reason="Legacy only")
    with pytest.raises(ModelResponseError):
        DatasetChatService(QueryRouter(gateway), sql, rag, hybrid).chat("Quy định?")
    gateway.generate_structured.assert_called_once()
    for pipeline in (sql, rag, hybrid):
        pipeline.run.assert_not_called()


@pytest.mark.parametrize("evidence", ["tables", "documents", "both"])
def test_required_evidence_cannot_downgrade_to_an_available_but_wrong_pipeline(evidence):
    gateway = Mock(
        generate_structured=Mock(
            return_value=RouteDecision.model_validate(
                {
                    "route": "RAG",
                    "reason": "fixture",
                    "evidence_requirement": evidence,
                }
            )
        )
    )
    assert QueryRouter(gateway).route("Câu hỏi", frozenset({RouteLabel.UNSUPPORTED})).route == (
        RouteLabel.UNSUPPORTED
    )


# Development topics: logistics, energy, hotel. Library is held out from prompt examples.
CASES = [
    ("Giao nhận", "Điều kiện nào để kho đạt KPI?", "documents"),
    ("Giao nhận", "Khi tính tổng phí, chính sách có loại đơn hủy không?", "documents"),
    ("Giao nhận", "Kho nào đạt theo chính sách đã lưu?", "both"),
    ("Giao nhận", "Tổng phí theo kho?", "tables"),
    ("Xe điện", "Dieu kien de tram dat KPI la gi?", "documents"),
    (
        "Xe điện",
        "Cho tôi biết cách xác định KPI trong tài liệu, chưa cần tính số liệu.",
        "documents",
    ),
    ("Xe điện", "Trạm nào đạt khi đối chiếu số liệu với quy định?", "both"),
    ("Xe điện", "So sánh tổng phí và số phiên từng trạm.", "tables"),
    ("Khách sạn", "Chính sách tính thưởng theo số phòng là gì?", "documents"),
    ("Khách sạn", "Khách sạn nào có hơn 100 phòng?", "tables"),
    ("Khách sạn", "Khách sạn nào đủ điều kiện thưởng trong tài liệu?", "both"),
    ("Thư viện", "Quy định SQL trong hướng dẫn xuất danh mục nói gì?", "documents"),
    ("Thư viện", "Xếp hạng số lượt mượn của từng chi nhánh.", "tables"),
    ("Thư viện", "Áp dụng chính sách, chi nhánh nào được khen thưởng?", "both"),
    ("Thư viện", "Thời tiết ngày mai?", "unavailable"),
    ("Thư viện", "Còn cái kia thì sao?", "unclear"),
]


@pytest.mark.parametrize("domain,question,evidence", CASES)
def test_cross_domain_intent_contract(domain, question, evidence):
    gateway = Mock(
        generate_structured=Mock(
            return_value=RouteDecision.model_validate(
                {
                    "route": "HYBRID",
                    "reason": "Scripted evidence, not semantic accuracy",
                    "evidence_requirement": evidence,
                }
            )
        )
    )
    pipelines = {route: Mock() for route in (RouteLabel.SQL, RouteLabel.RAG, RouteLabel.HYBRID)}
    for pipeline in pipelines.values():
        pipeline.run.return_value = Mock(
            answer="Có nguồn",
            sql="SELECT ...",
            rows=[],
            sources=[],
            result_columns=(),
            answer_row_indices=None,
            verification_status="unverified",
        )
    service = DatasetChatService(QueryRouter(gateway, domain), *pipelines.values())
    result = service.chat(question)
    expected = {
        "documents": RouteLabel.RAG,
        "tables": RouteLabel.SQL,
        "both": RouteLabel.HYBRID,
    }.get(evidence, RouteLabel.UNSUPPORTED)
    assert result.route == expected
    for route, pipeline in pipelines.items():
        assert pipeline.run.call_count == int(route == expected)
    assert gateway.generate_structured.call_count == 1


def test_current_rule_question_is_distinguished_from_a_verified_comparison_premise():
    gateway = Mock(
        generate_structured=Mock(
            return_value=RouteDecision.model_validate(
                {
                    "route": "HYBRID",
                    "reason": "Policy explanation",
                    "evidence_requirement": "documents",
                }
            )
        )
    )
    current = "Vậy quy định này có áp dụng cho đơn hủy không?"
    contextual = current + "\nPrevious successful turns: Kho K1 đạt, K2 chưa đạt."
    decision = QueryRouter(gateway).route(contextual, current_question=current)
    assert decision.route == RouteLabel.RAG
    prompt = gateway.generate_structured.call_args.args[0]
    assert "Current request:\n" + current in prompt
    assert "Context is not a requirement to repeat the previous route" in prompt


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize("evidence", ["documents", "tables", "both", "unclear"])
def test_evidence_contract_survives_pinned_sdk_wire_and_local_validation(
    monkeypatch, provider, evidence
):
    payload = json.dumps(
        {"route": "HYBRID", "reason": "Synthetic fixture", "evidence_requirement": evidence}
    )
    gateway, calls = gateway_harness(monkeypatch, provider, [response(provider, payload)])
    try:
        with diagnostic_request() as trace:
            decision = QueryRouter(gateway).route("Synthetic schema-independent question")
        assert trace.facts["evidence_requirement"] == evidence
        assert len(calls) == 1
        wire = json.loads(calls[0].content)
        schema = (
            wire["response_format"]["json_schema"]["schema"]
            if provider == "knowledge"
            else wire["generationConfig"]["responseSchema"]
        )
        assert "evidence_requirement" in schema["properties"]
        assert (
            decision.route
            == {
                "documents": RouteLabel.RAG,
                "tables": RouteLabel.SQL,
                "both": RouteLabel.HYBRID,
                "unclear": RouteLabel.UNSUPPORTED,
            }[evidence]
        )
    finally:
        gateway.close()


def test_evidence_telemetry_cannot_export_free_text():
    assert safe_metadata({"evidence_requirement": "PRIVATE question"}) == {}
    with diagnostic_request() as trace:
        record_facts(evidence_requirement="PRIVATE question")
    assert "evidence_requirement" not in trace.facts


def test_unclear_request_asks_for_scope_without_mislabeling_a_provider_failure():
    gateway = Mock(
        generate_structured=Mock(
            return_value=RouteDecision(
                route="UNSUPPORTED", reason="No resolved referent", evidence_requirement="unclear"
            )
        )
    )
    sql = Mock()
    result = DatasetChatService(QueryRouter(gateway), sql, None, None).chat("Còn cái kia?")
    assert "Bạn muốn tra quy định hay tính số liệu" in result.answer
    sql.run.assert_not_called()
