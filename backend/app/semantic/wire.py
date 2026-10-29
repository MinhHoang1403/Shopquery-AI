"""Flat provider transport converted into the single SemanticTask domain contract."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.semantic.task import (
    Condition,
    Ordering,
    OutputName,
    OutputSelection,
    PolicyRequirement,
    Population,
    Predicate,
    PredicateGroup,
    Projection,
    ScalarValue,
    SemanticTask,
)
from app.text_to_sql.generation_contract import (
    GenerationExpression,
    GenerationField,
    apply_catalog_schema,
    enrich_reference_schema,
)
from app.text_to_sql.query_plan import ExpressionOperation, PlanExpression, PlanSort

PREDICATE_OPERATIONS = frozenset(
    {"eq", "ne", "gt", "gte", "lt", "lte", "in", "is_null", "is_not_null", "and", "or"}
)


def _count_operation_schema(schema: dict) -> None:
    schema["enum"] = [
        "non_null_count" if item == "value_count" else item
        for item in schema["enum"]
        if item not in PREDICATE_OPERATIONS
    ]
    schema["description"] = (
        "row_count counts records with zero arguments. non_null_count counts only non-NULL "
        "values of one column; names and identifiers do not prove equivalence to record count."
    )


class TaskExpression(GenerationExpression):
    """Clarify nullable-value counting on the wire; preserve the compiler's operator."""

    operation: ExpressionOperation = Field(json_schema_extra=_count_operation_schema)

    @field_validator("operation", mode="before")
    @classmethod
    def canonical_count(cls, value: str) -> str:
        return "value_count" if value == "non_null_count" else value


def _projection_schema(schema: dict) -> None:
    enrich_reference_schema(schema, allow_empty=True)
    schema["properties"]["aggregation"].pop("default", None)
    schema["properties"]["aggregation"]["description"] = (
        "none selects the referenced value; row_count counts records with reference=''; "
        "non_null_count counts only non-NULL source-column values. sum/avg/min/max use a source."
    )
    schema["required"] = ["reference", "alias", "aggregation"]


class TaskField(GenerationField):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_projection_schema)

    alias: OutputName = Field(
        description="Internal lower_snake_case ASCII name, at most 63 characters."
    )
    aggregation: Literal["none", "sum", "avg", "min", "max", "row_count", "value_count"] = Field(
        default="none", json_schema_extra=_count_operation_schema
    )

    @field_validator("aggregation", mode="before")
    @classmethod
    def canonical_count(cls, value: str) -> str:
        return "value_count" if value == "non_null_count" else value


def _condition_schema(schema: dict) -> None:
    enrich_reference_schema(schema, field="left", allow_empty=True)


class TaskCondition(BaseModel):
    """A comparison leaf or a Boolean group; never a value-expression node."""

    model_config = ConfigDict(extra="forbid", json_schema_extra=_condition_schema)
    kind: Literal["comparison", "all", "any"]
    left: str = Field(max_length=128)
    operator: Literal["none", "eq", "ne", "gt", "gte", "lt", "lte", "in", "is_null", "is_not_null"]
    values: list[str] = Field(max_length=100)
    value_type: Literal[
        "none", "TEXT", "NUMERIC", "BIGINT", "BOOLEAN", "DATE", "TIMESTAMP", "TIMESTAMPTZ"
    ]
    children: list[str] = Field(max_length=80)


def _proposal_schema(schema: dict) -> None:
    apply_catalog_schema(schema)
    schema["properties"]["conditions"].pop("default", None)
    if "conditions" not in schema["required"]:
        schema["required"].append("conditions")


class TaskProposal(BaseModel):
    """Wire-only DTO; no ownership, permission, threshold or verification fields."""

    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, json_schema_extra=_proposal_schema
    )

    operation: Literal["query", "explain", "apply_policy", "combine", "unsupported", "clarify"]
    reason: str = Field(max_length=500)
    subject: str = Field(max_length=256)
    source: str
    grouping: Literal["entity", "category", "records"]
    fields: list[TaskField] = Field(max_length=30)
    expressions: list[TaskExpression] = Field(max_length=80)
    conditions: list[TaskCondition] = Field(default_factory=list, max_length=80)
    group_by: list[str] = Field(max_length=30)
    relationships: list[str] = Field(max_length=3)
    where: str = Field(max_length=32, pattern=r"^(?:p[0-9]+)?$")
    having: str = Field(max_length=32, pattern=r"^(?:p[0-9]+)?$")
    sort: list[PlanSort] = Field(max_length=10)
    limit: int = Field(strict=True, ge=0, le=1000)
    policy_description: str = Field(max_length=2000)
    policy_metric: str = Field(max_length=63)
    selection: Literal["none", "all", "qualified", "not_qualified"] = Field(
        alias="policy_selection",
        description="Document-policy verdict selection, only for apply_policy; otherwise none. "
        "Ordinary SQL WHERE conditions never use this field.",
    )
    unresolved: list[str] = Field(max_length=20)

    def task(
        self, question: str, *, column_references: dict[str, str] | None = None
    ) -> SemanticTask:
        """Preserve AND/OR/typed literals and output predicates, never infer a population."""

        def canonical(reference: str) -> str:
            if reference.startswith("column:"):
                if column_references is None or reference not in column_references:
                    raise ValueError("Column address was not issued for this request")
                return column_references[reference]
            return reference

        # Only the backend-issued lookup changes wire addresses into compiler IDs.
        # Never infer a column from a model's output alias or repair its choice.
        nodes = [
            node.model_copy(
                update={"arguments": [canonical(arg) for arg in node.arguments]}
            ).expression()
            for node in self.expressions
        ]
        # Check all DAG edges, including nodes not selected for output. Otherwise a
        # malformed/cyclic wire node could disappear during canonicalization.
        for index, node in enumerate(nodes):
            if node.operation in PREDICATE_OPERATIONS:
                raise ValueError("Comparisons and Boolean groups belong to conditions, not values")
            for ref in node.arguments:
                if ref.startswith("e") and (not ref[1:].isdigit() or int(ref[1:]) >= index):
                    raise ValueError("Expression must reference an earlier node")
        if self.operation in {"explain", "unsupported", "clarify"}:
            if any(
                (
                    self.source,
                    nodes,
                    self.fields,
                    self.conditions,
                    self.where,
                    self.having,
                    self.group_by,
                    self.relationships,
                    self.sort,
                    self.limit,
                    self.policy_description,
                    self.policy_metric,
                    self.selection != "none",
                )
            ):
                raise ValueError("Non-table task cannot contain a hidden query or selection")
            return SemanticTask(
                operation=self.operation,
                question=question,
                subject=self.subject,
                unresolved=tuple(self.unresolved or ([self.reason] if self.reason else [])),
            )
        if self.reason or self.operation in {"query", "combine"} and self.selection != "none":
            raise ValueError("Conflicting task operation and policy selection")
        if self.operation != "apply_policy" and any((self.policy_description, self.policy_metric)):
            raise ValueError("Only policy application may request a policy binding")
        retained: list[PlanExpression] = []
        mapping: dict[str, str] = {}
        for index, node in enumerate(self.conditions):
            if node.kind == "comparison":
                if not node.left or node.operator == "none" or node.children:
                    raise ValueError("Comparison needs a left value, operator and no children")
                if (node.value_type == "none") != (not node.values):
                    raise ValueError("Comparison values require their explicit scalar type")
            else:
                if (
                    node.left
                    or node.operator != "none"
                    or node.values
                    or node.value_type != "none"
                    or not node.children
                ):
                    raise ValueError("Boolean group cannot hide comparison fields")
                if any(
                    not child.startswith("p") or not child[1:].isdigit() or int(child[1:]) >= index
                    for child in node.children
                ):
                    raise ValueError("Condition groups reference only earlier conditions")

        def expression(reference: str) -> str:
            reference = canonical(reference)
            if reference in mapping:
                return mapping[reference]
            if not reference.startswith("e"):
                return reference
            if re.fullmatch(r"e(?:0|[1-9][0-9]*)", reference) is None:
                raise ValueError("Expression reference was not issued")
            try:
                node = nodes[int(reference[1:])]
            except (ValueError, IndexError) as exc:
                raise ValueError("Unknown expression") from exc
            if node.operation in PREDICATE_OPERATIONS:
                raise ValueError("Boolean predicate cannot masquerade as a value")
            args = [expression(arg) for arg in node.arguments]
            mapped = f"e{len(retained)}"
            retained.append(node.model_copy(update={"arguments": args}))
            mapping[reference] = mapped
            return mapped

        visited: set[str] = set()
        expanded = 0

        def condition(reference: str, depth: int = 1) -> Condition:
            nonlocal expanded
            expanded += 1
            if (
                expanded > 80
                or depth > 8
                or not reference.startswith("p")
                or not reference[1:].isdigit()
            ):
                raise ValueError("Condition exceeds the bounded predicate contract")
            try:
                node = self.conditions[int(reference[1:])]
            except (ValueError, IndexError) as exc:
                raise ValueError("Unknown predicate") from exc
            visited.add(reference)
            if node.kind in {"all", "any"}:
                return PredicateGroup(
                    kind=node.kind,
                    children=tuple(condition(child, depth + 1) for child in node.children),
                )
            return Predicate(
                reference=expression(node.left),
                operator=node.operator,
                values=tuple(
                    ScalarValue(data_type=node.value_type, value=value) for value in node.values
                ),
            )

        fields = tuple(
            Projection(
                reference=expression(f.reference) if f.reference else None,
                alias=f.alias,
                aggregate=None if f.aggregation == "none" else f.aggregation,
            )
            for f in self.fields
        )
        group_by = tuple(expression(ref) for ref in self.group_by)
        aliases = {f.alias for f in fields}
        ordering = tuple(
            Ordering(
                field=s.field if s.field in aliases else expression(s.field),
                direction=s.direction,
                nulls=s.nulls,
            )
            for s in self.sort
        )
        population = Population(
            source=self.source or None,
            grouping=self.grouping,
            group_by=group_by,
            relationships=tuple(self.relationships),
            predicates=condition(self.where) if self.where else None,
        )
        output = OutputSelection(
            fields=fields,
            classification=self.selection,
            ordering=ordering,
            limit=self.limit or None,
            predicates=condition(self.having) if self.having else None,
        )
        if visited != {f"p{i}" for i in range(len(self.conditions))}:
            raise ValueError("Unreferenced condition would silently lose a requested clause")
        if len(mapping) != len(nodes):
            raise ValueError("Unreferenced value expression cannot be silently discarded")
        return SemanticTask(
            operation=self.operation,
            question=question,
            subject=self.subject,
            population=population,
            output=output,
            expressions=tuple(retained),
            policy=PolicyRequirement(
                description=self.policy_description, metric=self.policy_metric or None
            )
            if self.operation == "apply_policy"
            else None,
            unresolved=tuple(self.unresolved),
        )
