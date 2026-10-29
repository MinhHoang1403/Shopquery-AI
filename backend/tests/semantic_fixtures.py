"""Scripted provider proposals for dispatch tests; not semantic-model accuracy gold."""

from app.semantic.wire import TaskProposal


def assert_policy_rows(rows, expected, identity_field, answer_row_indices=None):
    """Check all evidence by identity, then the separate requested presentation order.

    Policy SQL deliberately has no output ordering/limit before classification.
    Expected values still come from the independent PostgreSQL oracle; this helper
    only accounts for the explicit row-index presentation contract.
    """
    assert len(rows) == len(expected)
    actual = {row[identity_field]: row for row in rows}
    gold = {row[identity_field]: row for row in expected}
    assert len(actual) == len(rows) and len(gold) == len(expected)
    assert actual == gold
    indices = range(len(rows)) if answer_row_indices is None else answer_row_indices
    assert [rows[index] for index in indices] == expected


def proposal(operation="query"):
    return {
        "operation": operation,
        "reason": "",
        "subject": "records",
        "source": "t0",
        "grouping": "entity",
        "fields": [{"reference": "e0", "alias": "rows", "aggregation": "none"}],
        "expressions": [
            {"operation": "row_count", "arguments": [], "value": "", "value_type": "none"}
        ],
        "conditions": [],
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
    if operation == "apply_policy":
        data.update(
            selection="all", policy_description="Apply the saved policy to these source metrics."
        )
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
    return compact_proposal(data)


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


def compact_proposal(data):
    """Translate test-authored legacy expression predicates into semantic clauses.

    No natural-language interpretation and no production repair path. Values and
    Boolean topology come only from the independently authored static test plan.
    """
    from copy import deepcopy

    from app.semantic.wire import PREDICATE_OPERATIONS

    data = deepcopy(data)
    original = data["expressions"]
    retained, conditions = [], []
    value_map, condition_map = {}, {}

    def value(reference):
        if not reference.startswith("e"):
            return reference
        if reference in value_map:
            return value_map[reference]
        node = original[int(reference[1:])]
        if node["operation"] in PREDICATE_OPERATIONS:
            raise AssertionError("A predicate fixture cannot masquerade as a value")
        arguments = [value(arg) for arg in node["arguments"]]
        result = f"e{len(retained)}"
        retained.append({**node, "arguments": arguments})
        value_map[reference] = result
        return result

    def condition(reference):
        if reference in condition_map:
            return condition_map[reference]
        node = original[int(reference[1:])]
        operation = node["operation"]
        if operation in {"and", "or"}:
            children = [condition(arg) for arg in node["arguments"]]
            result = {
                "kind": "all" if operation == "and" else "any",
                "left": "",
                "operator": "none",
                "values": [],
                "value_type": "none",
                "children": children,
            }
        else:
            literals = [original[int(arg[1:])] for arg in node["arguments"][1:]]
            assert all(item["operation"] == "literal" for item in literals)
            kinds = {item["value_type"] for item in literals}
            assert len(kinds) <= 1
            result = {
                "kind": "comparison",
                "left": value(node["arguments"][0]),
                "operator": operation,
                "values": [item["value"] for item in literals],
                "value_type": next(iter(kinds)) if kinds else "none",
                "children": [],
            }
        reference_id = f"p{len(conditions)}"
        conditions.append(result)
        condition_map[reference] = reference_id
        return reference_id

    data["fields"] = [
        {
            **field,
            "reference": value(field["reference"]),
            "aggregation": field.get("aggregation", "none"),
        }
        for field in data["fields"]
    ]
    data["group_by"] = [value(ref) for ref in data["group_by"]]
    aliases = {field["alias"] for field in data["fields"]}
    data["sort"] = [
        {**order, "field": order["field"] if order["field"] in aliases else value(order["field"])}
        for order in data["sort"]
    ]
    data["where"] = condition(data["where"]) if data["where"] else ""
    data["having"] = condition(data["having"]) if data["having"] else ""
    data["expressions"], data["conditions"] = retained, conditions
    return TaskProposal.model_validate(data)
