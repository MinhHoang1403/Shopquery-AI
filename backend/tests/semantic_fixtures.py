"""Scripted provider proposals for dispatch tests; not semantic-model accuracy gold."""

from app.semantic.wire import TaskProposal


def proposal(operation="query"):
    return {
        "operation": operation,
        "reason": "",
        "subject": "records",
        "source": "t0",
        "grouping": "entity",
        "fields": [{"reference": "e0", "alias": "rows"}],
        "expressions": [
            {"operation": "row_count", "arguments": [], "value": "", "value_type": "none"}
        ],
        "group_by": [],
        "relationships": [],
        "where": "",
        "having": "",
        "sort": [],
        "limit": 0,
        "policy_description": "",
        "policy_metric": "",
        "selection": "none",
        "unresolved": [],
    }


def proposal_for_evidence(evidence, selection="none"):
    operation = {
        "tables": "query",
        "documents": "explain",
        "both": "combine",
        "unavailable": "unsupported",
        "unclear": "clarify",
    }[evidence]
    if evidence == "both" and selection != "none":
        operation = "apply_policy"
    data = proposal(operation)
    if operation in {"explain", "unsupported", "clarify", "apply_policy"}:
        data.update(source="", fields=[], expressions=[], group_by=[])
    if operation == "apply_policy":
        data.update(selection=selection, policy_description="Apply the documented entity policy.")
    if operation in {"unsupported", "clarify"}:
        data["reason"] = (
            "No resolved referent" if operation == "clarify" else "Unavailable capability"
        )
    return TaskProposal.model_validate(data)


def proposal_from_plan(decision, operation="query", context=None):
    """Encode a static test-authored plan in the current provider wire contract.

    This is fixture migration only. Expected rows remain independently authored;
    production never converts model SQL through this helper.
    """
    from app.text_to_sql.query_plan import PlanExpression

    if decision.plan is None:
        return proposal_for_evidence("unavailable")
    plan = decision.plan
    data = proposal(operation)
    expressions = list(plan.expressions)
    fields = []
    for field in plan.fields:
        reference = field.reference
        if field.aggregate is not None:
            reference = f"e{len(expressions)}"
            expressions.append(
                PlanExpression(
                    operation=field.aggregate,
                    arguments=[] if field.aggregate == "row_count" else [field.reference],
                )
            )
        fields.append({"reference": reference, "alias": field.alias})
    where = plan.where
    for condition in plan.filters:
        from app.text_to_sql.compiler import SchemaReferences

        if context is None:
            raise ValueError("Fixture PlanFilter requires explicit catalog types")
        table, column = SchemaReferences.from_context(context).columns[condition.reference]
        kind = context.column_types[table][column]
        arguments = [condition.reference]
        for value in condition.values:
            arguments.append(f"e{len(expressions)}")
            expressions.append(PlanExpression(operation="literal", value=value, value_type=kind))
        reference = f"e{len(expressions)}"
        expressions.append(PlanExpression(operation=condition.operator, arguments=arguments))
        if where is not None:
            conjunction = f"e{len(expressions)}"
            expressions.append(PlanExpression(operation="and", arguments=[where, reference]))
            where = conjunction
        else:
            where = reference
    data.update(
        source=plan.source,
        grouping=plan.grouping,
        fields=fields,
        expressions=[
            {
                "operation": node.operation,
                "arguments": node.arguments,
                "value": node.value or "",
                "value_type": node.value_type or "none",
            }
            for node in expressions
        ],
        group_by=list(plan.group_by),
        relationships=list(plan.relationships),
        where=where or "",
        having=plan.having or "",
        sort=[order.model_dump() for order in plan.sort],
        limit=plan.limit or 0,
    )
    return TaskProposal.model_validate(data)


class ScopedChatFixture:
    """Direct factory tests supply the same principal envelope that API supplies in production."""

    def __init__(self, service, context, reference_date):
        self._service, self._context, self._reference_date = service, context, reference_date

    def __getattr__(self, name):
        return getattr(self._service, name)

    def chat(self, question, **kwargs):
        from app.semantic.request import RequestIdentity, request_active, semantic_request
        from tests.auth_helpers import TEST_OWNER

        if request_active():
            return self._service.chat(question, **kwargs)
        with semantic_request(
            RequestIdentity(
                self._context.owner_user_id or TEST_OWNER,
                None,
                self._context.dataset_id,
                kwargs.get("current_question", question),
                self._reference_date,
            )
        ):
            return self._service.chat(question, **kwargs)


def scoped_dataset_service(settings, context, gateway=None):
    from app.dependencies import _build_dataset_chat_service, build_dataset_chat_service

    service = (
        _build_dataset_chat_service(settings, context, gateway)
        if gateway is not None
        else build_dataset_chat_service(settings, context)
    )
    return ScopedChatFixture(service, context, settings.demo_reference_date)


def scoped_hybrid_run(pipeline, question, selection):
    from app.semantic.request import RequestIdentity, request_active, semantic_request

    context = pipeline._context
    task = proposal_for_evidence("both", selection).task(question)
    if request_active():
        return pipeline.run(question, task=task)
    with semantic_request(
        RequestIdentity(context.owner_user_id, None, context.dataset_id, question, "2026-10-29")
    ):
        return pipeline.run(question, task=task)
