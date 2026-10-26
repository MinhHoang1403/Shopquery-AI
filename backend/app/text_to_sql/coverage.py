"""Pre-execution coverage for one source-bound, all-row entity aggregate."""

from dataclasses import dataclass
from typing import Literal

from sqlglot import exp, parse_one

from app.core.diagnostics import diagnostic_stage, record_facts
from app.core.errors import ErrorContext, ModelResponseError
from app.text_to_sql.compiler import CompiledQuery, SchemaReferences
from app.text_to_sql.query_plan import PlanExpression, PlanField, QueryPlan


@dataclass(frozen=True)
class EvidenceCoverageRequirement:
    source: str
    identity: str
    metric: str
    aggregate: Literal["sum", "avg", "row_count", "value_count"]
    relationships: tuple[str, ...] = ()
    selection: Literal["all", "qualified", "not_qualified"] = "all"
    entity_count: int | None = None

    def plan(self) -> QueryPlan:
        return QueryPlan(
            source=self.source,
            fields=[
                PlanField(reference=self.identity, alias="entity_id"),
                PlanField(reference="e0", alias="metric_value"),
            ],
            expressions=[
                PlanExpression(
                    operation=self.aggregate,
                    arguments=[] if self.aggregate == "row_count" else [self.metric],
                )
            ],
            group_by=[self.identity],
            relationships=list(self.relationships),
        )


def coverage_error() -> ModelResponseError:
    return ModelResponseError(
        "Chưa đủ bằng chứng đầy đủ để phân loại theo chính sách. "
        "Hãy hỏi rõ đối tượng và phạm vi cần đánh giá.",
        error_context=ErrorContext(
            phase="verification",
            error_category="insufficient_evidence",
            reason_code="planning_scope_violation",
        ),
    )


def validate_plan_coverage(plan: QueryPlan, requirement: EvidenceCoverageRequirement) -> None:
    with diagnostic_stage("plan_coverage_validation"):
        record_facts(coverage_requirement="full_entity_classification")
        if (
            plan.grouping != "entity"
            or plan.where
            or plan.having
            or plan.filters
            or plan.limit is not None
            or plan.source != requirement.source
            or set(plan.relationships) != set(requirement.relationships)
            or plan.group_by != [requirement.identity]
            or len(plan.fields) != 2
        ):
            raise coverage_error()
        identities, metrics = 0, 0
        for field in plan.fields:
            if field.reference == requirement.identity and field.aggregate is None:
                identities += 1
                continue
            operation, arguments = field.aggregate, [field.reference] if field.reference else []
            if operation is None and field.reference and field.reference.startswith("e"):
                try:
                    node = plan.expressions[int(field.reference[1:])]
                except (ValueError, IndexError):
                    raise coverage_error() from None
                operation, arguments = node.operation, node.arguments
            if operation == requirement.aggregate and arguments == (
                [] if operation == "row_count" else [requirement.metric]
            ):
                metrics += 1
        if identities != 1 or metrics != 1:
            raise coverage_error()


def validate_compiled_coverage(
    compiled: CompiledQuery,
    requirement: EvidenceCoverageRequirement,
    references: SchemaReferences,
) -> None:
    """Recheck emitted AST lineage before the executor; compiler security stays independent."""
    with diagnostic_stage("plan_coverage_validation"):
        record_facts(coverage_requirement="full_entity_classification")
        root = parse_one(compiled.evidence_sql, read="postgres")
        if root != parse_one(compiled.validated.statement, read="postgres") or compiled.parameters:
            raise coverage_error()
        if not isinstance(root, exp.Select) or any(
            root.args.get(key) for key in ("where", "having", "limit", "offset", "distinct")
        ):
            raise coverage_error()
        aliases = {t.alias_or_name: t.name for t in root.find_all(exp.Table)}

        def location(column: exp.Expression) -> tuple[str, str] | None:
            if not isinstance(column, exp.Column):
                return None
            table = (
                aliases.get(column.table)
                if column.table
                else (next(iter(aliases.values())) if len(aliases) == 1 else None)
            )
            return (table, column.name) if table is not None else None

        identity = references.columns[requirement.identity]
        metric = references.columns[requirement.metric] if requirement.metric else None
        source = references.tables[requirement.source]
        if requirement.relationships and compiled.validated.fact_table != source:
            raise coverage_error()
        expected_tables = {source}
        for key in requirement.relationships:
            edge = references.relationships[key]
            expected_tables.update((edge.source_table, edge.target_table))
        group = root.args.get("group")
        if (
            set(aliases.values()) != expected_tables
            or group is None
            or len(group.expressions) != 1
            or location(group.expressions[0]) != identity
            or len(root.expressions) != 2
        ):
            raise coverage_error()
        projections = [p.this if isinstance(p, exp.Alias) else p for p in root.expressions]
        aggregates = [p for p in projections if isinstance(p, (exp.Sum, exp.Avg, exp.Count))]
        if len(aggregates) != 1 or sum(location(p) == identity for p in projections) != 1:
            raise coverage_error()
        aggregate = aggregates[0]
        expected_type = {
            "sum": exp.Sum,
            "avg": exp.Avg,
            "row_count": exp.Count,
            "value_count": exp.Count,
        }[requirement.aggregate]
        if not isinstance(aggregate, expected_type):
            raise coverage_error()
        if requirement.aggregate == "row_count":
            if not isinstance(aggregate.this, exp.Star):
                raise coverage_error()
        elif location(aggregate.this) != metric or metric[0] != source:
            raise coverage_error()
