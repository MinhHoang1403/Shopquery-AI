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


def routing_fixture(payload):
    return RouteDecision.model_validate(
        {
            "policy_intent": "none",
            "policy_scope": "unspecified",
            **payload,
        }
    )


def test_automatic_wire_contract_requires_evidence_intent_and_scope():
    assert {"evidence_requirement", "policy_intent", "policy_scope"}.issubset(
        RouteDecision.model_json_schema()["required"]
    )


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_missing_classification_metadata_never_silently_dispatches_sql(monkeypatch, provider):
    payload = json.dumps(
        {"route": "HYBRID", "reason": "Current evidence needs both", "evidence_requirement": "both"}
    )
    gateway, calls = gateway_harness(monkeypatch, provider, [response(provider, payload)])
    sql, rag, hybrid = Mock(), Mock(), Mock()
    try:
        with pytest.raises(ModelResponseError):
            DatasetChatService(QueryRouter(gateway), sql, rag, hybrid).chat(
                "Đối chiếu các đối tượng với điều kiện trong tài liệu."
            )
        assert len(calls) == 1
        for pipeline in (sql, rag, hybrid):
            pipeline.run.assert_not_called()
    finally:
        gateway.close()


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
    gateway.generate_structured.return_value = routing_fixture(
        {
            "route": "HYBRID",
            "reason": "Untrusted explanation",
            "evidence_requirement": evidence,
            "policy_intent": "qualified" if evidence == "both" else "none",
            "policy_scope": "all_entities" if evidence == "both" else "unspecified",
        }
    )
    decision = QueryRouter(gateway).route("Câu hỏi không được dùng làm keyword override")
    assert decision.route == expected
    if expected != RouteLabel.HYBRID:
        assert decision.policy_intent == "none" and decision.policy_scope == "unspecified"
    gateway.generate_structured.assert_called_once()


def test_missing_evidence_fails_closed_without_sql_rag_or_second_classifier():
    gateway, sql, rag, hybrid = Mock(), Mock(), Mock(), Mock()
    gateway.generate_structured.return_value = RouteDecision.model_construct(
        route="HYBRID", reason="Legacy only"
    )
    with pytest.raises(ModelResponseError):
        DatasetChatService(QueryRouter(gateway), sql, rag, hybrid).chat("Quy định?")
    gateway.generate_structured.assert_called_once()
    for pipeline in (sql, rag, hybrid):
        pipeline.run.assert_not_called()


@pytest.mark.parametrize("evidence", ["tables", "documents", "both"])
def test_required_evidence_cannot_downgrade_to_an_available_but_wrong_pipeline(evidence):
    gateway = Mock(
        generate_structured=Mock(
            return_value=routing_fixture(
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
            return_value=routing_fixture(
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
            return_value=routing_fixture(
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
@pytest.mark.parametrize("evidence", ["documents", "tables"])
def test_contradictory_classification_never_dispatches_a_pipeline(monkeypatch, provider, evidence):
    payload = json.dumps(
        {
            "route": "RAG",
            "reason": "Contradictory synthetic fixture",
            "evidence_requirement": evidence,
            "policy_intent": "qualified",
            "policy_scope": "all_entities",
        }
    )
    gateway, calls = gateway_harness(monkeypatch, provider, [response(provider, payload)])
    sql, rag, hybrid = Mock(), Mock(), Mock()
    try:
        result = DatasetChatService(QueryRouter(gateway), sql, rag, hybrid).chat(
            "Giải thích điều kiện trong tài liệu."
        )
        assert result.route == RouteLabel.UNSUPPORTED
        assert "chưa xác định" in result.answer
        for pipeline in (sql, rag, hybrid):
            pipeline.run.assert_not_called()
        assert len(calls) == 1
    finally:
        gateway.close()


@pytest.mark.parametrize(
    "current,previous",
    [
        ("Which units meet the documented condition?", "Explain the condition only."),
        ("Explain the condition only.", "Which units meet the documented condition?"),
        ("Tong gia tri theo don vi?", "The previous provider timed out."),
        ("Quy định áp dụng cho kỳ nào?", "The prior classification was not verified."),
    ],
)
def test_current_request_is_last_and_not_duplicated_after_context(current, previous):
    gateway = Mock(
        generate_structured=Mock(
            return_value=routing_fixture(
                {
                    "route": "RAG",
                    "reason": "Scripted contract",
                    "evidence_requirement": "documents",
                }
            )
        )
    )
    contextual = current + "\n\nPrevious successful turns: " + previous
    QueryRouter(gateway, "Synthetic workspace").route(contextual, current_question=current)
    prompt = gateway.generate_structured.call_args.args[0]
    assert prompt.endswith("Current request:\n" + current)
    assert prompt.count(current) == 1
    assert prompt.index(previous) < prompt.index("Current request:\n")
    gateway.generate_structured.assert_called_once()


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize("evidence", ["documents", "tables", "both", "unclear"])
def test_evidence_contract_survives_pinned_sdk_wire_and_local_validation(
    monkeypatch, provider, evidence
):
    payload = json.dumps(
        {
            "route": "HYBRID",
            "reason": "Synthetic fixture",
            "policy_intent": "none",
            "policy_scope": "unspecified",
            "evidence_requirement": evidence,
        }
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
    assert (
        safe_metadata(
            {
                "evidence_requirement": "PRIVATE question",
                "policy_intent": "PRIVATE answer",
                "policy_scope": "PRIVATE scope",
            }
        )
        == {}
    )
    with diagnostic_request() as trace:
        record_facts(evidence_requirement="PRIVATE question")
    assert "evidence_requirement" not in trace.facts


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize("selection", ["all", "qualified", "not_qualified"])
def test_complete_sdk_classification_reaches_coverage_without_a_question_template(
    monkeypatch, provider, selection
):
    from app.routing.hybrid import HybridPipeline
    from tests.test_evidence_coverage import fixture, pipeline

    chunk, context, _ = fixture()
    rows = [
        {"entity_id": "U1", "metric_value": "40.00"},
        {"entity_id": "U2", "metric_value": "0.00"},
    ]
    sql, executor, drafting = pipeline(context, rows)
    payload = json.dumps(
        {
            "route": "HYBRID",
            "reason": "Synthetic evidence requirements",
            "evidence_requirement": "both",
            "policy_intent": selection,
            "policy_scope": "all_entities",
        }
    )
    gateway, calls = gateway_harness(monkeypatch, provider, [response(provider, payload)])
    rag = Mock(retrieve=Mock(return_value=[chunk]))
    try:
        with diagnostic_request() as trace:
            result = DatasetChatService(
                QueryRouter(gateway),
                sql,
                rag,
                HybridPipeline(sql, rag, drafting, context),
            ).chat("Đối chiếu toàn bộ đối tượng với các điều kiện được lưu.")
        assert result.verification_status == "verified_classification"
        assert (
            result.answer_row_indices
            == {
                "all": None,
                "qualified": (0,),
                "not_qualified": (1,),
            }[selection]
        )
        assert trace.facts["policy_intent"] == selection
        assert trace.facts["policy_scope"] == "all_entities"
        assert len(calls) == 1
        executor.execute.assert_called_once()
        drafting.generate_structured.assert_not_called()
    finally:
        gateway.close()


def test_unclear_request_asks_for_scope_without_mislabeling_a_provider_failure():
    gateway = Mock(
        generate_structured=Mock(
            return_value=RouteDecision(
                route="UNSUPPORTED",
                reason="No resolved referent",
                evidence_requirement="unclear",
                policy_intent="none",
                policy_scope="unspecified",
            )
        )
    )
    sql = Mock()
    result = DatasetChatService(QueryRouter(gateway), sql, None, None).chat("Còn cái kia?")
    assert "Bạn muốn tra quy định hay tính số liệu" in result.answer
    sql.run.assert_not_called()
