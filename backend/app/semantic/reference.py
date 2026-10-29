"""Server-issued typed references; history may resolve a task, never authorize a query."""

from typing import Literal

from pydantic import model_validator

from app.datasets.context import DatasetSqlContext
from app.semantic.request import bind_request
from app.semantic.task import Contract, RequestContext, SemanticTask

MAX_REFERENCE_CHARACTERS = 12000


class TaskReference(Contract):
    request: RequestContext
    task: SemanticTask
    evidence: Literal["sql_executed", "classification_verified"]

    @model_validator(mode="after")
    def valid_reference(self) -> "TaskReference":
        if len(self.task.model_dump_json()) > MAX_REFERENCE_CHARACTERS:
            raise ValueError("Task reference exceeds the bounded conversation budget")
        if (
            self.request.principal != "authenticated"
            or self.request.conversation_id is None
            or self.request.question != self.task.question
            or self.task.unresolved
            or self.task.operation not in self.request.authorized_capabilities
        ):
            raise ValueError("Reference has no authenticated completed task scope")
        if self.evidence == "classification_verified" and self.task.operation != "apply_policy":
            raise ValueError("Only a policy task can carry classification evidence")
        if self.task.operation not in {"query", "apply_policy", "combine"}:
            raise ValueError("Document answer claims cannot become verified task evidence")
        if (
            self.task.population is None
            or self.task.population.source is None
            or self.task.output is None
            or not self.task.output.fields
        ):
            raise ValueError("Reference requires the bound execution task")
        if self.evidence == "classification_verified" and (
            self.task.policy is None
            or self.task.policy.metric is None
            or self.task.policy.applicability is not None
            or self.task.output.predicates is not None
        ):
            raise ValueError("Policy reference has unresolved evidence requirements")
        return self


def task_reference(
    task: SemanticTask,
    context: DatasetSqlContext | None,
    evidence: Literal["sql_executed", "classification_verified"],
) -> TaskReference | None:
    if not isinstance(context, DatasetSqlContext):
        return None
    if len(task.model_dump_json()) > MAX_REFERENCE_CHARACTERS:
        return None
    request = bind_request(context, ("query", "explain", "apply_policy", "combine"))
    if request is None or request.principal != "authenticated" or request.conversation_id is None:
        return None
    return TaskReference(request=request, task=task, evidence=evidence)
