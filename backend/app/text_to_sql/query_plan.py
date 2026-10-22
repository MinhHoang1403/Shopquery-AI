from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanExpression(BaseModel):
    """A flat DAG: e0, e1, ... may reference only earlier nodes or schema columns."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal[
        "literal",
        "add",
        "subtract",
        "multiply",
        "divide",
        "sum",
        "avg",
        "min",
        "max",
        "row_count",
        "value_count",
        "eq",
        "ne",
        "gt",
        "gte",
        "lt",
        "lte",
        "and",
        "or",
        "is_null",
        "is_not_null",
        "in",
        "day",
        "month",
        "year",
        "month_label",
        "date_label",
    ]
    arguments: list[str] = Field(default_factory=list, max_length=100)
    value: str | None = Field(default=None, max_length=8000)
    value_type: (
        Literal["TEXT", "NUMERIC", "BIGINT", "BOOLEAN", "DATE", "TIMESTAMP", "TIMESTAMPTZ"] | None
    ) = None


class PlanField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reference: str | None = None
    alias: str = Field(min_length=1, max_length=63)
    aggregate: Literal["sum", "avg", "min", "max", "row_count", "value_count"] | None = None


class PlanFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reference: str
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "is_null", "is_not_null"]
    values: list[str] = Field(default_factory=list, max_length=100)


class PlanSort(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    direction: Literal["asc", "desc"] = "asc"
    nulls: Literal["first", "last"] = "last"


class QueryPlan(BaseModel):
    """References are backend-issued IDs, never model-supplied SQL fragments."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    fields: list[PlanField] = Field(min_length=1, max_length=30)
    filters: list[PlanFilter] = Field(default_factory=list, max_length=30)
    group_by: list[str] = Field(default_factory=list, max_length=30)
    sort: list[PlanSort] = Field(default_factory=list, max_length=10)
    limit: int | None = Field(default=None, strict=True, ge=1, le=1000)
    relationships: list[str] = Field(default_factory=list, max_length=3)
    expressions: list[PlanExpression] = Field(default_factory=list, max_length=80)
    where: str | None = None
    having: str | None = None

    @model_validator(mode="after")
    def bounded_expressions(self) -> "QueryPlan":
        depths: dict[str, int] = {}
        for index, expression in enumerate(self.expressions):
            depth = 1
            for reference in expression.arguments:
                if reference.startswith("e"):
                    if reference not in depths:
                        raise ValueError("Expressions must reference earlier nodes")
                    depth = max(depth, depths[reference] + 1)
            if depth > 8:
                raise ValueError("Expression depth exceeds eight")
            depths[f"e{index}"] = depth
        return self


class PlanDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: QueryPlan | None = None
    unsupported_reason: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def one_outcome(self) -> "PlanDecision":
        if (self.plan is None) == (
            not bool(self.unsupported_reason and self.unsupported_reason.strip())
        ):
            raise ValueError("Return either a plan or a nonempty unsupported reason")
        return self
