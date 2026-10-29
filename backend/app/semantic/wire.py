"""Flat provider transport converted into the single SemanticTask domain contract."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.semantic.task import (
    Condition,
    Ordering,
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
)
from app.text_to_sql.query_plan import ExpressionOperation, PlanExpression, PlanSort, QueryPlan

PREDICATE_OPERATIONS = frozenset(
    {"eq", "ne", "gt", "gte", "lt", "lte", "in", "is_null", "is_not_null", "and", "or"}
)


def _count_operation_schema(schema: dict) -> None:
    schema["enum"] = [
        "non_null_count" if item == "value_count" else item for item in schema["enum"]
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


class TaskProposal(BaseModel):
    """Wire-only DTO; no ownership, permission, threshold or verification fields."""

    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, json_schema_extra=apply_catalog_schema
    )

    operation: Literal["query", "explain", "apply_policy", "combine", "unsupported", "clarify"]
    reason: str = Field(max_length=500)
    subject: str = Field(max_length=256)
    source: str
    grouping: Literal["entity", "category", "records"]
    fields: list[GenerationField] = Field(max_length=30)
    expressions: list[TaskExpression] = Field(max_length=80)
    group_by: list[str] = Field(max_length=30)
    relationships: list[str] = Field(max_length=3)
    where: str = Field(max_length=32, pattern=r"^(?:e[0-9]+|t[0-9]+\.c[0-9]+)?$")
    having: str = Field(max_length=32, pattern=r"^(?:e[0-9]+|t[0-9]+\.c[0-9]+)?$")
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

    @field_validator("where", "having")
    @classmethod
    def predicate_syntax(cls, value: str) -> str:
        if value:
            QueryPlan.predicate_reference(value)
        return value

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
            for ref in node.arguments:
                if ref.startswith("e") and (not ref[1:].isdigit() or int(ref[1:]) >= index):
                    raise ValueError("Expression must reference an earlier node")
        if self.operation in {"explain", "unsupported", "clarify"}:
            if any(
                (
                    self.source,
                    nodes,
                    self.fields,
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

        def expression(reference: str) -> str:
            reference = canonical(reference)
            if reference in mapping:
                return mapping[reference]
            if not reference.startswith("e"):
                return reference
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

        def condition(reference: str, depth: int = 1) -> Condition:
            if depth > 8 or not reference.startswith("e"):
                raise ValueError("Predicate must be a bounded boolean expression")
            try:
                node = nodes[int(reference[1:])]
            except (ValueError, IndexError) as exc:
                raise ValueError("Unknown predicate") from exc
            if node.operation in {"and", "or"}:
                return PredicateGroup(
                    kind="all" if node.operation == "and" else "any",
                    children=tuple(condition(arg, depth + 1) for arg in node.arguments),
                )
            if node.operation not in PREDICATE_OPERATIONS or not node.arguments:
                raise ValueError("Expected a typed comparison")
            values = []
            for ref in node.arguments[1:]:
                if not ref.startswith("e") or not ref[1:].isdigit():
                    raise ValueError("Comparison values must be typed literals")
                literal = nodes[int(ref[1:])]
                if literal.operation != "literal":
                    raise ValueError("Comparison value cannot be a computed column")
                values.append(ScalarValue(data_type=literal.value_type, value=literal.value))
            return Predicate(
                reference=expression(node.arguments[0]),
                operator=node.operation,
                values=tuple(values),
            )

        fields = tuple(
            Projection(reference=expression(f.reference), alias=f.alias) for f in self.fields
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
