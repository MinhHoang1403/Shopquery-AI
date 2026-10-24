"""Flat provider contract; the complete QueryPlan remains the validation authority."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.text_to_sql.query_plan import (
    ExpressionOperation,
    PlanDecision,
    PlanExpression,
    PlanField,
    PlanFilter,
    PlanSort,
    QueryPlan,
)


class GenerationExpression(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: ExpressionOperation
    arguments: list[str] = Field(max_length=100)
    value: str = Field(max_length=8000)
    value_type: Literal[
        "none", "TEXT", "NUMERIC", "BIGINT", "BOOLEAN", "DATE", "TIMESTAMP", "TIMESTAMPTZ"
    ]

    def expression(self) -> PlanExpression:
        if self.operation == "literal":
            if self.value_type == "none":
                raise ValueError("A literal needs its declared type")
            return PlanExpression(
                operation=self.operation,
                arguments=self.arguments,
                value=self.value,
                value_type=self.value_type,
            )
        if self.value or self.value_type != "none":
            raise ValueError("Only literals take a value/type")
        return PlanExpression(operation=self.operation, arguments=self.arguments)


class GenerationField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str
    alias: str = Field(min_length=1, max_length=63)


class GenerationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["query", "unsupported"]
    reason: str = Field(max_length=300)
    source: str
    fields: list[GenerationField] = Field(max_length=30)
    expressions: list[GenerationExpression] = Field(max_length=80)
    filters: list[PlanFilter] = Field(max_length=30)
    group_by: list[str] = Field(max_length=30)
    sort: list[PlanSort] = Field(max_length=10)
    limit: int = Field(strict=True, ge=0, le=1000)
    relationships: list[str] = Field(max_length=3)
    where: str
    having: str

    @model_validator(mode="after")
    def validate_outcome(self) -> "GenerationDecision":
        if self.outcome == "query" and self.reason:
            raise ValueError("A query cannot include an unsupported reason")
        if self.outcome == "unsupported":
            if not self.reason.strip():
                raise ValueError("Unsupported needs a reason")
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
                raise ValueError("Unsupported outcome cannot contain a query")
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
                raise ValueError("Unsupported outcome cannot contain a query")
            return PlanDecision(unsupported_reason=self.reason)
        if self.reason:
            raise ValueError("A query cannot include an unsupported reason")
        return PlanDecision(
            plan=QueryPlan(
                source=self.source,
                fields=[PlanField(**field.model_dump()) for field in self.fields],
                expressions=[node.expression() for node in self.expressions],
                filters=self.filters,
                group_by=self.group_by,
                sort=self.sort,
                limit=self.limit or None,
                relationships=self.relationships,
                where=self.where or None,
                having=self.having or None,
            )
        )
