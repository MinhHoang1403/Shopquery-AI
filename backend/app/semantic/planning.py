"""Deterministic semantic-task lowering; no provider calls or SQL execution."""

from app.semantic.task import Condition, Predicate, SemanticTask
from app.text_to_sql.query_plan import PlanExpression, PlanField, PlanSort, QueryPlan


def task_query_plan(task: SemanticTask) -> QueryPlan:
    """Preserve represented predicates; this does not verify natural-language understanding.

    Policy applicability needs source-bound validation before it can change a population.
    Policy output ordering/limit is deliberately deferred until all verdicts are verified.
    """
    task = SemanticTask.model_validate(task.model_dump())
    if (
        task.unresolved
        or task.population is None
        or task.output is None
        or task.population.source is None
        or not task.output.fields
    ):
        raise ValueError("Task is unresolved or does not require SQL")
    if task.policy is not None and task.policy.applicability is not None:
        raise ValueError("Policy applicability must be bound before SQL planning")
    expressions: list[PlanExpression] = [
        PlanExpression.model_validate(node.model_dump()) for node in task.expressions
    ]

    def emit(expression: PlanExpression) -> str:
        expressions.append(expression)
        return f"e{len(expressions) - 1}"

    def predicate(node: Condition) -> str:
        if isinstance(node, Predicate):
            arguments = [node.reference]
            arguments.extend(
                emit(PlanExpression(operation="literal", value=v.value, value_type=v.data_type))
                for v in node.values
            )
            return emit(PlanExpression(operation=node.operator, arguments=arguments))
        children = [predicate(child) for child in node.children]
        if len(children) == 1:
            return children[0]
        return emit(
            PlanExpression(operation="and" if node.kind == "all" else "or", arguments=children)
        )

    fields = []
    for projection in task.output.fields:
        reference = projection.reference
        if projection.aggregate is not None:
            reference = emit(
                PlanExpression(
                    operation=projection.aggregate,
                    arguments=[] if reference is None else [reference],
                )
            )
        fields.append(PlanField(reference=reference, alias=projection.alias))
    where = predicate(task.population.predicates) if task.population.predicates else None
    having = (
        predicate(task.output.predicates)
        if (task.operation in {"query", "combine"} and task.output.predicates)
        else None
    )
    return QueryPlan(
        source=task.population.source,
        grouping="category" if task.population.grouping == "category" else "entity",
        fields=fields,
        expressions=expressions,
        where=where,
        having=having,
        group_by=list(task.population.group_by),
        relationships=list(task.population.relationships),
        sort=[PlanSort(**order.model_dump()) for order in task.output.ordering]
        if task.operation in {"query", "combine"}
        else [],
        limit=task.output.limit if task.operation in {"query", "combine"} else None,
    )


def verify_task_plan(task: SemanticTask, plan: QueryPlan) -> None:
    """Reject omission, inversion or relocation of represented requirements before SQL.

    The planner is deterministic. Alias/key completion belongs to the existing binder
    after this check, never to a second model plan that could silently lose a predicate.
    """
    expected = task_query_plan(task)
    if expected.model_dump() != plan.model_dump():
        raise ValueError("QueryPlan does not preserve the semantic task")
