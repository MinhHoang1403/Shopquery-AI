"""Orchestration for SQL generation, validation, execution, and grounding."""

from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack, nullcontext
from dataclasses import dataclass
from typing import Any

from app.ai.gemini import GenerationGateway
from app.core.diagnostics import diagnostic_stage, record_facts
from app.text_to_sql.answer import compose_sql_answer
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.count_contract import CountMetric
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.planner import QueryPlanner
from app.text_to_sql.validator import ValidatedSql


@dataclass
class SqlResult:
    answer: str
    sql: str
    rows: list[dict[str, Any]]
    fact_table: str | None = None
    count_metrics: tuple[CountMetric, ...] = ()


class TextToSqlPipeline:
    def __init__(
        self,
        planner: QueryPlanner,
        compiler: QueryCompiler,
        executor: SqlExecutor,
        gateway: GenerationGateway,
        execution_guard: Callable[[ValidatedSql], AbstractContextManager] | None = None,
    ) -> None:
        self._planner = planner
        self._compiler = compiler
        self._executor = executor
        self._gateway = gateway
        self._execution_guard = execution_guard

    def run(
        self, question: str, *, evidence_context: str | None = None, ground_answer: bool = True
    ) -> SqlResult:
        with diagnostic_stage("generator_unsupported"):
            plan = (
                self._planner.generate(question, evidence_context=evidence_context)
                if evidence_context is not None
                else self._planner.generate(question)
            )
        with diagnostic_stage("plan_compilation"):
            compiled = self._compiler.compile(plan)
        validated = compiled.validated
        record_facts(sql_validated=True)
        guard = self._execution_guard(validated) if self._execution_guard else nullcontext()
        with ExitStack() as stack:
            with diagnostic_stage("execution_guard"):
                stack.enter_context(guard)
            with diagnostic_stage("sql_execution"):
                record_facts(execution_reached=True)
                rows = self._executor.execute(validated, compiled.parameters)
                record_facts(result_rows=len(rows))
        answer = ""
        if ground_answer:
            with diagnostic_stage("answer_grounding"):
                answer = compose_sql_answer(rows, validated.count_metrics)
        return SqlResult(
            answer=answer,
            sql=compiled.evidence_sql,
            rows=rows,
            fact_table=validated.fact_table,
            count_metrics=validated.count_metrics,
        )
