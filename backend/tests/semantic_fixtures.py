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
