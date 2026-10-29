"""Bind a semantic policy request using complete document and approved catalog evidence."""

from dataclasses import dataclass

from app.core.errors import ModelResponseError, SqlValidationError
from app.datasets.context import DatasetSqlContext
from app.rag.repository import RetrievedChunk
from app.routing.hybrid_policy import numeric_policies, policy_content
from app.routing.hybrid_policy_binding import identity_source, verification_error, verified_policies
from app.routing.natural_policy import normalized, parse_prose
from app.semantic.planning import task_query_plan
from app.semantic.task import OutputSelection, Population, Predicate, Projection, SemanticTask
from app.text_to_sql.compiler import QueryCompiler, SchemaReferences
from app.text_to_sql.coverage import EvidenceCoverageRequirement
from app.text_to_sql.pipeline import SqlResult
from app.text_to_sql.plan_binding import bind_approved_grain


@dataclass(frozen=True)
class BoundPolicyTask:
    task: SemanticTask
    identity_field: str
    entity_count: int | None
    universe: SemanticTask


def bind_policy_task(
    task: SemanticTask,
    chunks: list[RetrievedChunk],
    context: DatasetSqlContext,
) -> BoundPolicyTask:
    """Only uniquely source-bound metadata may complete missing metric/root/identity.

    A proposed selection never supplies the population. Unknown user clauses stay
    unresolved, and all-row policies cannot silently consume a fact-row subset.
    """
    task = SemanticTask.model_validate(task.model_dump())
    if task.operation != "apply_policy" or task.unresolved or task.population is None:
        raise verification_error("planning_scope_violation")
    candidates = numeric_policies(chunks)
    if len(candidates) != 1:
        raise verification_error(
            "policy_multiple_candidates" if candidates else "policy_parse_failed"
        )
    _, chunk_id = next(iter(candidates.values()))
    chunk = next(c for c in chunks if c.chunk_id == chunk_id)
    content = policy_content(chunk, chunks)
    prose = parse_prose(content) if content is not None else None
    if prose is None or prose.aggregate not in {"sum", "avg"}:
        raise verification_error("policy_parse_failed")
    refs = SchemaReferences.from_context(context)
    reverse = {location: key for key, location in refs.columns.items()}
    identities = set()
    measures = []
    for table, columns in context.table_columns.items():
        for column in columns:
            names = {
                normalized(column),
                normalized(context.column_headers.get(table, {}).get(column, column)),
            }
            if normalized(prose.identity_reference) in names:
                try:
                    identities.add(identity_source(table, column, context))
                except ModelResponseError:
                    continue
            if normalized(prose.metric_reference) in names and context.column_types.get(
                table, {}
            ).get(column) in {"NUMERIC", "BIGINT"}:
                measures.append((table, column))
    valid = []
    compiler = QueryCompiler(context)
    for fact, metric in measures:
        for identity in sorted(identities):
            source = next(key for key, name in refs.tables.items() if name == fact)
            requirement = EvidenceCoverageRequirement(
                source, reverse[identity], reverse[(fact, metric)], prose.aggregate
            )
            try:
                base = bind_approved_grain(requirement.plan(), refs)
                compiled = compiler.compile(base)
                evidence = SqlResult(
                    "",
                    compiled.evidence_sql,
                    [],
                    compiled.validated.fact_table,
                    compiled.validated.count_metrics,
                )
                verified_policies(evidence, chunks, context, require_verified=True)
            except (ModelResponseError, SqlValidationError):
                continue
            valid.append((base, identity, (fact, metric)))
    if len(valid) != 1:
        raise verification_error("policy_ambiguous" if valid else "policy_not_verified")
    base, identity, metric = valid[0]
    if task.population.source is not None and task.population.source != base.source:
        raise verification_error("planning_scope_violation")
    if not set(task.population.relationships).issubset(base.relationships):
        raise verification_error("planning_scope_violation")
    if task.population.grouping != "entity":
        raise verification_error("policy_grouping_mismatch")
    # Registry binding completes missing structure, never overwrites represented filters.
    fields = task.output.fields
    grouping = task.population.group_by
    expressions = task.expressions
    if not fields:
        if grouping and grouping != (reverse[identity],):
            raise verification_error("planning_scope_violation")
        fields = (
            Projection(reference=reverse[identity], alias="entity_id"),
            Projection(reference=reverse[metric], alias="metric_value", aggregate=prose.aggregate),
        )
        grouping = (reverse[identity],)
        metric_alias = "metric_value"
    else:
        metric_alias = task.policy.metric
        if metric_alias is None:
            raise verification_error("policy_metric_unbound")
    population = Population(
        source=base.source,
        grouping="entity",
        group_by=grouping,
        relationships=tuple(base.relationships),
        predicates=task.population.predicates,
    )
    output = task.output.model_copy(update={"fields": fields})
    if output.predicates is not None or task.policy.applicability is not None:
        # These clauses require a separately bound policy applicability/output
        # evaluator. Never discard a represented condition during classification.
        raise verification_error("planning_scope_violation")
    bound = SemanticTask.model_validate(
        {
            **task.model_dump(),
            "population": population.model_dump(),
            "output": output.model_dump(),
            "expressions": [node.model_dump() for node in expressions],
            "policy": {**task.policy.model_dump(), "metric": metric_alias},
        }
    )
    checked = compiler.compile(bind_approved_grain(task_query_plan(bound), refs))
    # Prove the actual population retains all facts for every selected entity.
    verified_policies(
        SqlResult(
            "",
            checked.evidence_sql,
            [],
            checked.validated.fact_table,
            checked.validated.count_metrics,
        ),
        chunks,
        context,
        require_verified=True,
    )
    identity_fields = [
        field.alias for field in bound.output.fields if field.reference == reverse[identity]
    ]
    if len(identity_fields) != 1:
        raise verification_error("policy_identity_unbound")
    if bound.population.predicates is not None:
        # A full table count is not evidence of the filtered subset's size.
        count = None
    else:
        count = context.table_row_counts.get(identity[0])

    def entity_predicate(node):
        if node is None:
            return None
        if isinstance(node, Predicate):
            location = refs.columns.get(node.reference)
            if location is None:
                raise verification_error("planning_scope_violation")
            table, column = location
            if table != identity[0]:
                if identity_source(table, column, context) != identity:
                    raise verification_error("planning_scope_violation")
                location = identity
            return node.model_copy(update={"reference": reverse[location]})
        return node.model_copy(
            update={
                "children": tuple(entity_predicate(child) for child in node.children),
            }
        )

    universe = SemanticTask(
        operation="query",
        question=task.question,
        population=Population(
            source=next(key for key, name in refs.tables.items() if name == identity[0]),
            grouping="records",
            predicates=entity_predicate(bound.population.predicates),
        ),
        output=OutputSelection(
            fields=(Projection(reference=reverse[identity], alias="entity_id"),)
        ),
    )
    return BoundPolicyTask(bound, identity_fields[0], count, universe)
