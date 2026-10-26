"""Lossless NUMERIC values across execution, preview, API and grounding."""

from decimal import Decimal
from typing import Any

import pytest

from app.main import app
from app.rag.pipeline import RagPipeline
from app.routing.hybrid import HybridAnswerDraft, HybridPipeline
from app.routing.router import RouteLabel
from app.routing.service import ChatResult
from app.text_to_sql.executor import _json_safe
from app.text_to_sql.pipeline import SqlResult
from app.text_to_sql.validator import ValidatedSql
from tests.auth_helpers import TestClient
from tests.sql_validation_fixtures import ValidationPipeline
from tests.test_routing_and_hybrid import FakeGateway, FakeRepository, FakeSqlPipeline
from tests.test_sql_executor import executor_connection
from tests.test_text_to_sql_pipeline import (
    GroundingGateway,
    PassthroughValidator,
    StaticExecutor,
    StaticGenerator,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("12345678901234567890.12"), "12345678901234567890.12"),
        (Decimal("0.000000000000000000000001"), "0.000000000000000000000001"),
        (Decimal("1.123456789012345678901234567890"), "1.123456789012345678901234567890"),
        (Decimal("0.00"), "0.00"),
        (Decimal("-12345678901234567890.12"), "-12345678901234567890.12"),
        (Decimal("1E+20"), "100000000000000000000"),
        (None, None),
        (0, 0),
        (12, 12),
        (9_007_199_254_740_991, 9_007_199_254_740_991),
        (9_007_199_254_740_992, "9007199254740992"),
        (9_007_199_254_740_993, "9007199254740993"),
        (-9_007_199_254_740_993, "-9007199254740993"),
        (True, True),
    ],
)
def test_numeric_json_contract(value: object, expected: object) -> None:
    result = _json_safe(value)
    assert result == expected
    assert type(result) is type(expected)


def test_parser_preview_keeps_native_large_integer_exact() -> None:
    from app.datasets.parser import _json_value

    assert _json_value(9_007_199_254_740_993) == "9007199254740993"


@pytest.mark.parametrize("value", [2**63, -(2**63) - 1])
def test_integer_outside_postgres_bigint_is_rejected_before_import(value: int) -> None:
    from app.core.errors import UploadValidationError
    from tests.test_dataset_parser import parse

    with pytest.raises(UploadValidationError, match="BIGINT"):
        parse("overflow.csv", f"Mã\n{value}\n".encode())


@pytest.mark.usefixtures("contract_session")
def test_executor_to_http_and_grounding_preserve_decimal_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = {
        "large_id": 9_007_199_254_740_993,
        "total": Decimal("12345678901234567890.12"),
        "zero": Decimal("0.00"),
        "missing": None,
        "matched_row_count": 2,
    }
    expected = {
        "large_id": "9007199254740993",
        "total": "12345678901234567890.12",
        "zero": "0.00",
        "missing": None,
        "matched_row_count": 2,
    }
    executor, connection = executor_connection()
    connection.execute.return_value.mappings.return_value.fetchmany.return_value = [raw]
    rows = executor.execute(ValidatedSql("SELECT total FROM fixture", frozenset({"fixture"})))
    gateway = GroundingGateway()
    pipeline = ValidationPipeline(
        StaticGenerator(), PassthroughValidator(), StaticExecutor(rows), gateway
    )
    result = pipeline.run("Tổng chính xác?")
    assert result.rows == [expected]
    assert "12345678901234567890.12" in result.answer
    assert "0.00" in result.answer and "Chưa có dữ liệu" in result.answer
    assert gateway.prompt == ""  # SQL presentation no longer makes a paid generation.

    class Service:
        def chat(self, question: str) -> ChatResult:
            return ChatResult(result.answer, RouteLabel.SQL, result.sql, result.rows)

    monkeypatch.setattr("app.api.routes.build_chat_service", lambda settings: Service())
    response = TestClient(app).post("/api/chat", json={"message": "Tổng chính xác?"})
    assert response.status_code == 200
    assert response.json()["rows"] == [expected]
    assert type(response.json()["rows"][0]["matched_row_count"]) is int


def test_hybrid_grounding_receives_lossless_decimal_evidence() -> None:
    class Sql(FakeSqlPipeline):
        def run(self, question: str, **kwargs) -> SqlResult:
            result = super().run(question)
            result.rows = [{"amount": "12345678901234567890.12"}]
            return result

    class Gateway(FakeGateway):
        prompt = ""

        def generate_structured(self, prompt: str, response_model: type[Any]) -> Any:
            assert response_model is HybridAnswerDraft
            self.prompt = prompt
            return super().generate_structured(prompt, response_model)

    gateway = Gateway()
    HybridPipeline(Sql(), RagPipeline(gateway, gateway, FakeRepository()), gateway).run("Kiểm tra")
    assert '"amount": "12345678901234567890.12"' in gateway.prompt
    assert "decimal strings" in gateway.prompt
