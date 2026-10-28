"""Deterministic tests for SQL result grounding semantics."""

from typing import Any

import pytest

from app.text_to_sql.validator import ValidatedSql
from tests.sql_validation_fixtures import ValidationPipeline


class StaticGenerator:
    def generate(self, question: str) -> str:
        del question
        return "SELECT 1 AS value"


class PassthroughValidator:
    def validate(self, sql: str) -> ValidatedSql:
        return ValidatedSql(statement=sql, tables=frozenset({"fixture"}))


class StaticExecutor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def execute(self, validated: ValidatedSql) -> list[dict[str, Any]]:
        del validated
        return self._rows


class GroundingGateway:
    def __init__(self) -> None:
        self.prompt = ""

    def generate_text(self, prompt: str) -> str:
        self.prompt = prompt
        return "Câu trả lời đã được grounding."


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"total": None, "matched_row_count": 0}],
        [{"total": None, "matched_row_count": 2}],
        [{"total": 0, "matched_row_count": 3}],
        [{"total": 9_876_543_210, "matched_row_count": 120}],
        [{"ngay": "2026-10-16", "khu_vuc": "Bắc"}],
        [{"category": "A", "total": 10}, {"category": "B", "total": 5}],
    ],
)
def test_deterministic_grounding_preserves_empty_null_zero_and_rows_without_ai(
    rows: list[dict[str, Any]],
) -> None:
    gateway = GroundingGateway()
    pipeline = ValidationPipeline(
        generator=StaticGenerator(),
        validator=PassthroughValidator(),
        executor=StaticExecutor(rows),
        gateway=gateway,
    )

    result = pipeline.run("Tính kết quả")

    assert result.rows == rows
    assert gateway.prompt == ""
    if not rows:
        assert "Không tìm thấy" in result.answer
    elif len(rows) == 1 and rows[0].get("total", 1) is None:
        # This fake validator supplies no typed labels; the summary must not invent them.
        # NULL and the different row counts remain exact in structured evidence above.
        assert "1 kết quả" in result.answer and "bảng dữ liệu" in result.answer
    elif len(rows) > 1:
        assert "2 kết quả" in result.answer
    else:
        assert result.answer
