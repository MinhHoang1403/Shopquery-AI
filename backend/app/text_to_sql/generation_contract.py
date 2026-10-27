"""Flat provider contract; the complete QueryPlan remains the validation authority."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.core.errors import ContractConversionError, ErrorContext, validation_context
from app.text_to_sql.query_plan import (
    ExpressionOperation,
    PlanDecision,
    PlanExpression,
    PlanField,
    PlanFilter,
    PlanSort,
    QueryPlan,
)

GENERATION_INSTRUCTIONS = (
    "\nReturn the flat GenerationDecision schema: outcome=query with an empty reason; "
    "zero limit and empty where/having mean absent. Every expression has value='' and "
    "value_type=none unless it is a literal. For unsupported, give reason and make "
    "source/where/having empty, limit=0, and all arrays empty. No enclosing plan object."
)

MAX_EXPRESSIONS = 80
_catalog: ContextVar[dict[str, tuple[str, ...]] | None] = ContextVar(
    "generation_catalog", default=None
)
_wire_constraints: ContextVar[bool] = ContextVar("generation_wire_constraints", default=True)


@contextmanager
def generation_schema_constraints(*, enabled: bool) -> Iterator[None]:
    """Select provider grammar enrichment without changing local plan validation."""
    token = _wire_constraints.set(enabled)
    try:
        yield
    finally:
        _wire_constraints.reset(token)


@contextmanager
def generation_catalog(
    tables: tuple[str, ...], columns: tuple[str, ...], relationships: tuple[str, ...]
) -> Iterator[None]:
    """Scope wire enums to this request's issued IDs; never share one owner's catalog."""
    token = _catalog.set(
        {
            "tables": tables,
            "references": columns + tuple(f"e{i}" for i in range(MAX_EXPRESSIONS)),
            "relationships": relationships,
        }
    )
    try:
        yield
    finally:
        _catalog.reset(token)


def apply_catalog_schema(schema: dict[str, Any]) -> None:
    if not _wire_constraints.get():
        return
    catalog = _catalog.get()
    if catalog is not None:
        schema["properties"]["source"]["enum"] = ["", *catalog["tables"]]
        schema["properties"]["group_by"]["items"]["enum"] = list(catalog["references"])
        if catalog["relationships"]:
            schema["properties"]["relationships"]["items"]["enum"] = list(catalog["relationships"])


def _field_schema(schema: dict[str, Any]) -> None:
    if not _wire_constraints.get():
        return
    catalog = _catalog.get()
    if catalog is not None:
        schema["properties"]["reference"]["enum"] = list(catalog["references"])


def _expression_schema(schema: dict[str, Any]) -> None:
    """Express the existing conditional contract on the wire without if/then.

    The two disjoint operation enums make anyOf unambiguous. Local conversion
    remains authoritative if a compatible endpoint ignores schema constraints.
    """
    if not _wire_constraints.get():
        return
    catalog = _catalog.get()
    if catalog is not None:
        schema["properties"]["arguments"]["items"]["enum"] = list(catalog["references"])
    literal = deepcopy(schema)
    operation = deepcopy(schema)
    literal["properties"]["operation"]["enum"] = ["literal"]
    literal["properties"]["value_type"]["enum"].remove("none")
    operation["properties"]["operation"]["enum"].remove("literal")
    operation["properties"]["value"]["enum"] = [""]
    operation["properties"]["value_type"]["enum"] = ["none"]
    schema.clear()
    schema["anyOf"] = [literal, operation]


class GenerationExpression(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_expression_schema)

    operation: ExpressionOperation
    arguments: list[str] = Field(max_length=100)
    value: str = Field(max_length=8000)
    value_type: Literal[
        "none", "TEXT", "NUMERIC", "BIGINT", "BOOLEAN", "DATE", "TIMESTAMP", "TIMESTAMPTZ"
    ]

    def expression(self) -> PlanExpression:
        if self.operation == "literal":
            if self.value_type == "none":
                raise ContractConversionError(
                    ErrorContext(
                        validation_branch="literal_type_missing", validation_location=["value_type"]
                    )
                )
            return PlanExpression(
                operation=self.operation,
                arguments=self.arguments,
                value=self.value,
                value_type=self.value_type,
            )
        if self.value:
            raise ContractConversionError(
                ErrorContext(validation_branch="nonliteral_value", validation_location=["value"])
            )
        if self.value_type != "none":
            raise ContractConversionError(
                ErrorContext(
                    validation_branch="nonliteral_type", validation_location=["value_type"]
                )
            )
        return PlanExpression(operation=self.operation, arguments=self.arguments)


class GenerationField(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_field_schema)

    reference: str
    alias: str = Field(min_length=1, max_length=63)


class GenerationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=apply_catalog_schema)

    outcome: Literal["query", "unsupported"]
    reason: str = Field(max_length=300)
    source: str
    grouping: Literal["entity", "category"] = "entity"
    fields: list[GenerationField] = Field(max_length=30)
    expressions: list[GenerationExpression] = Field(max_length=MAX_EXPRESSIONS)
    filters: list[PlanFilter] = Field(max_length=30)
    group_by: list[str] = Field(max_length=30)
    sort: list[PlanSort] = Field(max_length=10)
    limit: int = Field(strict=True, ge=0, le=1000)
    relationships: list[str] = Field(max_length=3)
    where: str = Field(max_length=32)
    having: str = Field(max_length=32)

    @field_validator("where", "having")
    @classmethod
    def predicate_reference(cls, value: str) -> str:
        if value:
            QueryPlan.predicate_reference(value)
        return value

    @model_validator(mode="after")
    def validate_outcome(self) -> "GenerationDecision":
        if self.outcome == "query" and self.reason:
            raise PydanticCustomError(
                "outcome_conflict", "A query cannot include an unsupported reason"
            )
        if self.outcome == "unsupported":
            if not self.reason.strip():
                raise PydanticCustomError("outcome_missing", "Unsupported needs a reason")
            if any(
                (
                    self.source,
                    self.fields,
                    self.expressions,
                    self.filters,
                    self.group_by,
                    self.sort,
                    self.limit,
                    self.relationships,
                    self.where,
                    self.having,
                )
            ):
                raise PydanticCustomError("outcome_conflict", "Unsupported cannot contain a query")
        return self

    def decision(self) -> PlanDecision:
        if self.outcome == "unsupported":
            if any(
                (
                    self.source,
                    self.fields,
                    self.expressions,
                    self.filters,
                    self.group_by,
                    self.sort,
                    self.limit,
                    self.relationships,
                    self.where,
                    self.having,
                )
            ):
                raise ContractConversionError(
                    ErrorContext(
                        validation_branch="outcome_conflict", response_outcome=self.outcome
                    )
                )
            return PlanDecision(unsupported_reason=self.reason)
        if self.reason:
            raise ContractConversionError(
                ErrorContext(validation_branch="outcome_conflict", response_outcome=self.outcome)
            )
        expressions = []
        for index, node in enumerate(self.expressions):
            try:
                expressions.append(node.expression())
            except ContractConversionError as exc:
                raise ContractConversionError(
                    exc.error_context.model_copy(
                        update={
                            "validation_location": [
                                "expressions",
                                index,
                                *exc.error_context.validation_location,
                            ],
                            "response_outcome": self.outcome,
                        }
                    )
                ) from exc
        try:
            plan = QueryPlan(
                source=self.source,
                grouping=self.grouping,
                fields=[PlanField(**field.model_dump()) for field in self.fields],
                expressions=expressions,
                filters=self.filters,
                group_by=self.group_by,
                sort=self.sort,
                limit=self.limit or None,
                relationships=self.relationships,
                where=self.where or None,
                having=self.having or None,
            )
        except ValidationError as exc:
            raise ContractConversionError(
                ErrorContext(
                    **{"validation_branch": "query_plan_contract", **validation_context(exc)},
                    response_outcome=self.outcome,
                )
            ) from exc
        try:
            return PlanDecision(plan=plan)
        except ValidationError as exc:
            raise ContractConversionError(
                ErrorContext(
                    **{"validation_branch": "plan_decision_contract", **validation_context(exc)},
                    response_outcome=self.outcome,
                )
            ) from exc
