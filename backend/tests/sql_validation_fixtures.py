"""Run fixed SQL security fixtures through the production execution/grounding stages.

This harness tests the independent validator, not provider planning. Production factories
always use QueryPlanner and QueryCompiler; their regression fixtures use PlanDecision.
"""

from pydantic import BaseModel

from app.core.errors import SqlUnsupportedError
from app.text_to_sql.compiler import CompiledQuery
from app.text_to_sql.pipeline import TextToSqlPipeline


class SqlFixture(BaseModel):
    sql: str
    unsupported_reason: str | None = None


class FixtureGenerator:
    """Deliver a fixed adversarial SQL fixture to validator tests without AI planning."""

    def __init__(self, gateway, reference_date, schema_context=""):
        self.gateway = gateway
        self.schema_context = schema_context

    def generate(self, question, *, evidence_context=None):
        draft = self.gateway.generate_structured(
            self.schema_context + "\n" + (evidence_context or "") + "\nQuestion: " + question,
            SqlFixture,
        )
        if draft.unsupported_reason:
            raise SqlUnsupportedError("Unsupported fixed SQL fixture", code="generator_unsupported")
        return draft.sql


class ValidationCompiler:
    def __init__(self, validator):
        self.validator = validator

    def compile(self, sql):
        validated = self.validator.validate(sql)
        return CompiledQuery(validated, {}, validated.statement)


class FixtureExecutor:
    def __init__(self, executor):
        self.executor = executor

    def execute(self, validated, parameters):
        assert not parameters
        return self.executor.execute(validated)


class ValidationPipeline(TextToSqlPipeline):
    def run(self, question, *, task=None, **kwargs):
        # Fixed adversarial SQL is this harness's input, not a generated task.
        # Task-to-compiler integration has its own semantic execution tests.
        return super().run(question, **kwargs)

    def __init__(self, generator, validator, executor, gateway, execution_guard=None):
        super().__init__(
            generator,
            ValidationCompiler(validator),
            FixtureExecutor(executor),
            gateway,
            execution_guard,
        )
