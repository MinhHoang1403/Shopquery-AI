"""Complete only uniquely authorized JOIN structure and dimension identities."""

from itertools import combinations

from pydantic import ValidationError

from app.core.diagnostics import diagnostic_stage
from app.core.errors import ErrorContext, SqlUnsupportedError, SqlValidationError
from app.text_to_sql.compiler import SchemaReferences
from app.text_to_sql.join_policy import resolve_join_tree
from app.text_to_sql.query_plan import PlanField, QueryPlan

AGGREGATES = {"sum", "avg", "min", "max", "row_count", "value_count"}


@diagnostic_stage("plan_binding", annotate_error=False)
def bind_approved_grain(plan: QueryPlan, references: SchemaReferences) -> QueryPlan:
    def context(branch: str) -> ErrorContext:
        return ErrorContext(
            origin_stage="plan_binding",
            phase="compilation",
            error_category="sql_validation",
            response_outcome="query",
            validation_branch=branch,
        )

    if plan.source not in references.tables:
        raise SqlValidationError(
            "Unknown source or relationship reference", error_context=context("unknown_source")
        )
    if any(key not in references.relationships for key in plan.relationships):
        raise SqlValidationError(
            "Unknown source or relationship reference",
            error_context=context("unknown_relationship"),
        )
    selected = [references.relationships[key] for key in plan.relationships]
    requested_source = references.tables[plan.source]
    if len(set(plan.relationships)) != len(plan.relationships):
        raise SqlValidationError(
            "Duplicate relationship requirements", error_context=context("duplicate_relationship")
        )
    refs = set(plan.group_by)
    refs.update(field.reference for field in plan.fields if field.reference)
    refs.update(item.reference for item in plan.filters)
    refs.update(arg for node in plan.expressions for arg in node.arguments)
    refs.update(ref for ref in (plan.where, plan.having) if ref is not None)
    issued = set(references.columns) | {f"e{i}" for i in range(len(plan.expressions))}
    aliases = {field.alias for field in plan.fields}
    if refs - issued or any(item.field not in issued | aliases for item in plan.sort):
        raise SqlValidationError(
            "Unknown column or expression reference", error_context=context("unknown_reference")
        )
    refs.update(item.field for item in plan.sort)
    tables = {references.columns[ref][0] for ref in refs if ref in references.columns}
    tables.add(requested_source)
    tables.update(table for edge in selected for table in (edge.source_table, edge.target_table))
    measures = {
        references.columns[node.arguments[0]][0]
        for node in plan.expressions
        if node.operation in AGGREGATES - {"row_count"}
        and len(node.arguments) == 1
        and node.arguments[0] in references.columns
    }
    measures.update(
        references.columns[field.reference][0]
        for field in plan.fields
        if field.aggregate in AGGREGATES - {"row_count"} and field.reference in references.columns
    )
    # Only direct source measures establish a fact; row_count alone does not name an entity.
    if len(measures) > 1:
        raise SqlUnsupportedError(
            "Measures require different fact grains",
            code="join_grain",
            grain_reason="multiple_fact_measures",
            error_context=context("multiple_fact_measures"),
        )
    fact = next(iter(measures)) if measures else requested_source
    tables.add(fact)
    if len(tables) == 1 and not selected:
        return plan.model_copy(
            update={
                "source": next(ref for ref, table in references.tables.items() if table == fact)
            }
        )
    candidates = []
    edges = list(references.relationships.values())
    for size in (1, 2):
        for path in combinations(edges, size):
            if not set(selected) <= set(path):
                continue
            try:
                root = path[0].source_table if size == 1 else resolve_join_tree(path).fact_table
            except SqlUnsupportedError:
                continue
            names = {table for edge in path for table in (edge.source_table, edge.target_table)}
            if size == 2 and any(
                edge.source_table == fact
                and tables <= {edge.source_table, edge.target_table}
                and set(selected) <= {edge}
                for edge in path
            ):
                continue
            if root == fact and tables <= names:
                candidates.append(path)
    if len(candidates) != 1:
        raise SqlUnsupportedError(
            "No unique approved fact path",
            code="join_graph",
            error_context=context("missing_path" if not candidates else "ambiguous_path"),
        )
    path = candidates[0]
    fields, groups = list(plan.fields), list(plan.group_by)
    aggregated = any(node.operation in AGGREGATES for node in plan.expressions) or any(
        field.aggregate for field in fields
    )
    if aggregated and plan.grouping == "entity":
        dimension_refs = set(groups) | {field.reference for field in fields if not field.aggregate}
        dimension_tables = {
            references.columns[ref][0] for ref in dimension_refs if ref in references.columns
        }
        for edge in path:
            if edge.target_table not in dimension_tables:
                continue
            key = next(
                ref
                for ref, location in references.columns.items()
                if location == (edge.target_table, edge.target_column)
            )
            if key not in groups:
                groups.append(key)
            if key in plan.group_by:
                # A verified N:1 target key determines its direct attributes. Adding
                # those projections to GROUP BY preserves this explicitly selected grain.
                for field in fields:
                    if (
                        field.aggregate is None
                        and field.reference in references.columns
                        and references.columns[field.reference][0] == edge.target_table
                        and field.reference not in groups
                    ):
                        groups.append(field.reference)
            if not any(field.reference == key for field in fields):
                alias = edge.target_column
                if any(field.alias == alias for field in fields):
                    raise SqlValidationError(
                        "Identity output alias collision",
                        error_context=context("identity_alias_collision"),
                    )
                fields.append(PlanField(reference=key, alias=alias))
    try:
        return QueryPlan.model_validate(
            {
                **plan.model_dump(),
                "source": next(ref for ref, table in references.tables.items() if table == fact),
                "relationships": [
                    ref for ref, edge in references.relationships.items() if edge in path
                ],
                "fields": fields,
                "group_by": groups,
            }
        )
    except ValidationError as exc:
        raise SqlValidationError(
            "Bound plan exceeds the query contract", error_context=context("bound_contract")
        ) from exc
