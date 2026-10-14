"""Orchestration for SQL generation, validation, execution, and grounding."""

import json
from dataclasses import dataclass
from typing import Any

from app.ai.gemini import GenerationGateway
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.generator import SqlGenerator
from app.text_to_sql.validator import SqlValidator


@dataclass
class SqlResult:
    answer: str
    sql: str
    rows: list[dict[str, Any]]


class TextToSqlPipeline:
    def __init__(
        self,
        generator: SqlGenerator,
        validator: SqlValidator,
        executor: SqlExecutor,
        gateway: GenerationGateway,
    ) -> None:
        self._generator = generator
        self._validator = validator
        self._executor = executor
        self._gateway = gateway

    def run(self, question: str) -> SqlResult:
        sql = self._generator.generate(question)
        validated = self._validator.validate(sql)
        rows = self._executor.execute(validated)
        answer = self._ground_answer(question, rows)
        return SqlResult(answer=answer, sql=validated.statement, rows=rows)

    def _ground_answer(self, question: str, rows: list[dict[str, Any]]) -> str:
        prompt = f"""
Answer the user's question in the same language as the question.
Use only the JSON query result below. Do not invent, estimate, or supplement numbers.
If the result is empty, clearly say that no matching data was found.

Question: {question}
Query result: {json.dumps(rows, ensure_ascii=False)}
""".strip()
        return self._gateway.generate_text(prompt)
