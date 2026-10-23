import json
from unittest.mock import Mock

import pytest

from app.core.errors import RetrievalError
from app.routing.hybrid import HybridPipeline
from app.text_to_sql.validator import SqlValidator
from tests.sql_validation_fixtures import FixtureGenerator, SqlFixture, ValidationPipeline
from tests.test_hybrid_answer_consistency import fixture


def test_evidence_is_available_before_sql_and_redundant_grounding_is_skipped():
    result, chunks, draft = fixture()
    events = []

    def retrieve(question):
        events.append("retrieve_and_rerank")
        return chunks

    def execute(question, *, evidence_context, ground_answer):
        events.append("sql")
        context = json.loads(evidence_context)
        assert context["chunks"][0]["content"] == chunks[0].content
        assert context["policy_candidates_not_verified"][0]["metric_column"] == "measure"
        assert ground_answer is False
        return result

    gateway = Mock(generate_structured=Mock(return_value=draft))
    HybridPipeline(Mock(run=execute), Mock(retrieve=retrieve), gateway).run("Which qualify?")
    assert events == ["retrieve_and_rerank", "sql"]
    gateway.generate_structured.assert_called_once()
    gateway.generate_text.assert_not_called()


def test_missing_evidence_prevents_any_sql_or_generation():
    sql, gateway = Mock(), Mock()
    rag = Mock(retrieve=Mock(side_effect=RetrievalError("No evidence")))
    with pytest.raises(RetrievalError):
        HybridPipeline(sql, rag, gateway).run("Which qualify?")
    sql.run.assert_not_called()
    gateway.generate_structured.assert_not_called()


def test_sql_only_execution_does_not_need_evidence_or_extra_generation():
    gateway = Mock(
        generate_structured=Mock(
            return_value=SqlFixture(sql="SELECT COUNT(*) AS total FROM products")
        )
    )
    executor = Mock(execute=Mock(return_value=[{"total": 2}]))
    pipeline = ValidationPipeline(
        FixtureGenerator(gateway, "2026-10-22"), SqlValidator(), executor, gateway
    )
    result = pipeline.run("How many?", evidence_context="source metric hint", ground_answer=False)
    assert result.rows == [{"total": 2}]
    assert "source metric hint" in gateway.generate_structured.call_args.args[0]
    assert result.answer == ""
    gateway.generate_text.assert_not_called()
