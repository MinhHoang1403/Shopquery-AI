"""Lossless task representation; model proposals never constitute execution authority."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.text_to_sql.query_plan import PlanExpression

ColumnReference = Annotated[str, Field(pattern=r"^t\d+\.c\d+$")]
ValueReference = Annotated[str, Field(pattern=r"^(?:t\d+\.c\d+|e\d+)$")]
OutputName = Annotated[str, Field(pattern=r"^[a-z_][a-z0-9_]{0,62}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RequestContext(Contract):
    """Server-owned identity, deliberately separate from the generated task proposal."""

    owner_user_id: UUID | None
    conversation_id: UUID | None
    dataset_id: int | None = Field(strict=True, ge=0)
    principal: Literal["authenticated", "guest"] = "authenticated"
    guest_request_id: UUID | None = None
    catalog_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    question: str = Field(min_length=1, max_length=2000)
    reference_date: date
    time_zone: str
    authorized_capabilities: tuple[Literal["query", "explain", "apply_policy", "combine"], ...] = (
        "query",
        "explain",
        "apply_policy",
        "combine",
    )

    @model_validator(mode="after")
    def valid_request(self) -> RequestContext:
        if self.principal == "authenticated":
            if (
                self.owner_user_id is None
                or self.dataset_id == 0
                or self.guest_request_id is not None
            ):
                raise ValueError("Authenticated scope requires a real owner and workspace")
        elif (
            self.owner_user_id is not None
            or self.dataset_id != 0
            or self.conversation_id is not None
            or self.guest_request_id is None
        ):
            raise ValueError("Guest scope is temporary and request-local")
        if not self.question.strip():
            raise ValueError("Question must not be blank")
        try:
            ZoneInfo(self.time_zone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown business time zone") from exc
        return self


class ScalarValue(Contract):
    data_type: Literal["TEXT", "BIGINT", "NUMERIC", "BOOLEAN", "DATE", "TIMESTAMP", "TIMESTAMPTZ"]
    value: str = Field(max_length=8000)

    @model_validator(mode="after")
    def valid_value(self) -> ScalarValue:
        try:
            if self.data_type in {"BIGINT", "NUMERIC"}:
                number = Decimal(self.value)
                if not number.is_finite():
                    raise ValueError("Non-finite number")
                if self.data_type == "BIGINT" and (
                    not re.fullmatch(r"[+-]?\d+", self.value)
                    or number != number.to_integral_value()
                    or not -(2**63) <= number < 2**63
                ):
                    raise ValueError("Invalid BIGINT")
            elif self.data_type == "BOOLEAN" and self.value not in {"true", "false"}:
                raise ValueError("Boolean must be true or false")
            elif self.data_type == "DATE":
                date.fromisoformat(self.value)
            elif self.data_type in {"TIMESTAMP", "TIMESTAMPTZ"}:
                temporal = datetime.fromisoformat(self.value.replace("Z", "+00:00"))
                if (temporal.utcoffset() is not None) != (self.data_type == "TIMESTAMPTZ"):
                    raise ValueError("Timestamp offset does not match its type")
        except (ValueError, InvalidOperation) as exc:
            raise ValueError("Value does not match its declared type") from exc
        return self


class Predicate(Contract):
    kind: Literal["comparison"] = "comparison"
    reference: ValueReference
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "is_null", "is_not_null"]
    values: tuple[ScalarValue, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def valid_arity(self) -> Predicate:
        expected = 0 if self.operator in {"is_null", "is_not_null"} else 1
        if self.operator == "in":
            if not self.values:
                raise ValueError("IN needs values")
        elif len(self.values) != expected:
            raise ValueError("Wrong predicate arity")
        if len({v.data_type for v in self.values}) > 1:
            raise ValueError("Predicate values must share a type")
        return self


class PredicateGroup(Contract):
    kind: Literal["all", "any"]
    children: tuple[Annotated[Predicate | PredicateGroup, Field(discriminator="kind")], ...] = (
        Field(min_length=1, max_length=30)
    )


Condition = Annotated[Predicate | PredicateGroup, Field(discriminator="kind")]


class Population(Contract):
    source: str | None = Field(default=None, pattern=r"^t\d+$")
    grouping: Literal["entity", "category", "records"]
    group_by: tuple[ValueReference, ...] = Field(default=(), max_length=30)
    predicates: Condition | None = None
    relationships: tuple[Annotated[str, Field(pattern=r"^r\d+$")], ...] = Field(
        default=(), max_length=3
    )

    @model_validator(mode="after")
    def valid_grain(self) -> Population:
        if len(set(self.group_by)) != len(self.group_by):
            raise ValueError("Duplicate grouping key")
        if len(set(self.relationships)) != len(self.relationships):
            raise ValueError("Duplicate relationship")
        if self.grouping == "records" and self.group_by:
            raise ValueError("Record output cannot introduce aggregation grain")
        return self


class Projection(Contract):
    alias: OutputName
    reference: ValueReference | None = None
    aggregate: Literal["sum", "avg", "min", "max", "row_count", "value_count"] | None = None

    @model_validator(mode="after")
    def valid_measure(self) -> Projection:
        if (self.reference is None) != (self.aggregate == "row_count"):
            raise ValueError("Only row_count has no source column")
        return self


class Ordering(Contract):
    field: OutputName | ValueReference
    direction: Literal["asc", "desc"]
    nulls: Literal["first", "last"] = "last"


class OutputSelection(Contract):
    fields: tuple[Projection, ...] = Field(default=(), max_length=30)
    classification: Literal["none", "all", "qualified", "not_qualified"] = "none"
    ordering: tuple[Ordering, ...] = Field(default=(), max_length=10)
    limit: int | None = Field(default=None, strict=True, ge=1, le=1000)
    predicates: Condition | None = None

    @model_validator(mode="after")
    def valid_output(self) -> OutputSelection:
        aliases = [field.alias for field in self.fields]
        if len(aliases) != len(set(aliases)):
            raise ValueError("Duplicate output name")
        if aliases and any(
            order.field not in aliases and not re.fullmatch(r"(?:t\d+\.c\d+|e\d+)", order.field)
            for order in self.ordering
        ):
            raise ValueError("Order must reference a selected output")
        return self


class PolicyRequirement(Contract):
    """A requested policy binding, not a model-issued threshold or verified rule."""

    description: str = Field(min_length=1, max_length=2000)
    metric: OutputName | None = None
    applicability: Condition | None = None


class SemanticTask(Contract):
    operation: Literal["query", "explain", "apply_policy", "combine", "unsupported", "clarify"]
    question: str = Field(min_length=1, max_length=2000)
    subject: str = Field(default="", max_length=256)
    expressions: tuple[PlanExpression, ...] = Field(default=(), max_length=80)
    population: Population | None = None
    output: OutputSelection | None = None
    policy: PolicyRequirement | None = None
    unresolved: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = Field(
        default=(), max_length=20
    )

    @model_validator(mode="after")
    def consistent_task(self) -> SemanticTask:
        if not self.question.strip():
            raise ValueError("Question must not be blank")
        if self.operation in {"explain", "unsupported", "clarify"}:
            if self.population is not None or self.output is not None or self.policy is not None:
                raise ValueError("Document explanation cannot authorize a table query")
            if self.expressions:
                raise ValueError("Document/non-executable task cannot carry SQL expressions")
        else:
            if self.population is None or self.output is None:
                raise ValueError("Table tasks need population and output")
            classification = self.output.classification
            if self.operation in {"query", "combine"} and (
                not self.population.source or not self.output.fields
            ):
                raise ValueError("Query needs an explicit source and selected fields")
            if self.operation == "query" and (self.policy or classification != "none"):
                raise ValueError("SQL cannot assert policy classification")
            if self.operation == "apply_policy":
                if self.policy is None or classification == "none":
                    raise ValueError("Policy task needs explicit policy and selection")
                metric = next(
                    (p for p in self.output.fields if p.alias == self.policy.metric), None
                )
                if self.policy.metric is not None and metric is None and self.output.fields:
                    raise ValueError("Policy metric must be a selected aggregate")
            roots = [self.population.predicates, self.output.predicates]
            if self.policy:
                roots.append(self.policy.applicability)
            pending = [(root, 1) for root in roots if root is not None]
            count = 0
            while pending:
                node, depth = pending.pop()
                count += 1
                if count > 80 or depth > 8:
                    raise ValueError("Predicate complexity exceeds supported bounds")
                if isinstance(node, PredicateGroup):
                    pending.extend((child, depth + 1) for child in node.children)
        return self
