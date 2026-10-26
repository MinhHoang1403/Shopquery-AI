from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

ExpressionOperation = Literal[
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


class PlanExpression(BaseModel):
    """A flat DAG: e0, e1, ... may reference only earlier nodes or schema columns."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: ExpressionOperation
    arguments: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="Earlier expression/column IDs; row_count takes no arguments. "
        "An aggregate takes a non-aggregate input; value_count takes one source column.",
    )
    value: str | None = Field(default=None, max_length=8000)
    value_type: (
        Literal["TEXT", "NUMERIC", "BIGINT", "BOOLEAN", "DATE", "TIMESTAMP", "TIMESTAMPTZ"] | None
    ) = None


def _projection_schema(schema: dict[str, Any]) -> None:
    """Generation uses the existing expression DAG; direct aggregates remain internal DTOs."""
    schema["properties"].pop("aggregate")
    schema["properties"]["reference"] = {
        "type": "string",
        "description": "Column or expression ID. Aggregation belongs to expression nodes, "
        "not projection fields. Reference the aggregate expression's ID for its output.",
    }
    schema["required"] = ["reference", "alias"]


class PlanField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=_projection_schema)

    reference: str | None = Field(
        default=None,
        description="Column or expression ID. Must be null for field aggregate row_count. "
        "When referencing an aggregate expression, aggregate must be null.",
    )
    alias: str = Field(min_length=1, max_length=63)
    aggregate: Literal["sum", "avg", "min", "max", "row_count", "value_count"] | None = Field(
        default=None,
        description="Applies an aggregate to reference, not a label for its result. "
        "Use null if reference already contains an aggregate. "
        "row_count requires reference=null; value_count requires a source column.",
    )

    @model_validator(mode="after")
    def row_count_has_no_reference(self) -> "PlanField":
        if self.aggregate == "row_count" and self.reference is not None:
            raise ValueError("Row count does not take a value column")
        return self


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
    grouping: Literal["entity", "category"] = "entity"
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
        expanded_sizes: dict[str, int] = {}
        for index, expression in enumerate(self.expressions):
            depth = 1
            expanded_size = 1
            for reference in expression.arguments:
                if reference.startswith("e"):
                    if reference not in depths:
                        raise PydanticCustomError(
                            "expression_forward_reference",
                            "Expressions must reference earlier nodes",
                        )
                    depth = max(depth, depths[reference] + 1)
                    expanded_size += expanded_sizes[reference]
                else:
                    expanded_size += 1
            if depth > 8:
                raise PydanticCustomError("expression_depth", "Expression depth exceeds eight")
            if expanded_size > 512:
                raise PydanticCustomError(
                    "expression_expansion", "Expression expansion exceeds 512 nodes"
                )
            depths[f"e{index}"] = depth
            expanded_sizes[f"e{index}"] = expanded_size
        return self


class PlanDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: QueryPlan | None = None
    unsupported_reason: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def one_outcome(self) -> "PlanDecision":
        reason = bool(self.unsupported_reason and self.unsupported_reason.strip())
        if self.plan is not None and reason:
            raise PydanticCustomError("outcome_conflict", "Return only one planning outcome")
        if self.plan is None and not reason:
            raise PydanticCustomError("outcome_missing", "A planning outcome is required")
        return self
