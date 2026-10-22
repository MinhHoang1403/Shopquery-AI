from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    limit: int | None = Field(default=None, ge=1, le=1000)
    relationships: list[str] = Field(default_factory=list, max_length=2)


class PlanDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: QueryPlan | None = None
    unsupported_reason: str | None = Field(default=None, max_length=300)
