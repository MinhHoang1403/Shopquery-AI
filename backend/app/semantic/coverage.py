"""Request-bound evidence requirements, independent of router classification flags."""

from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from app.core.diagnostics import record_facts
from app.core.errors import ErrorContext, ModelResponseError
from app.semantic.planning import task_query_plan, verify_task_plan
from app.semantic.request import bind_request
from app.semantic.task import RequestContext, SemanticTask
from app.text_to_sql.compiler import CompiledQuery, QueryCompiler
from app.text_to_sql.plan_binding import bind_approved_grain
from app.text_to_sql.query_plan import QueryPlan


@dataclass(frozen=True)
class EvidenceRequirement:
    """Backend snapshot of represented requirements, not a claim of NLP correctness.

    Successful validation is necessary, not sufficient for execution: authorized
    catalog binding, compiler/SQL guards and source-bound policy verification remain
    mandatory. No model-provided classification can construct an all-row shortcut.
    """

    owner_user_id: UUID | None
    conversation_id: UUID | None
    dataset_id: int | None
    request_digest: str
    task_json: str
    sources: tuple[str, ...]


def require_evidence(request: RequestContext, task: SemanticTask) -> EvidenceRequirement:
    request = RequestContext.model_validate(request.model_dump())
    task = SemanticTask.model_validate(task.model_dump())
    if (
        request.question != task.question
        or task.unresolved
        or task.operation not in request.authorized_capabilities
    ):
        raise ValueError("Task does not resolve this current request")
    return EvidenceRequirement(
        request.owner_user_id,
        request.conversation_id,
        request.dataset_id,
        sha256(request.model_dump_json().encode()).hexdigest(),
        task.model_dump_json(),
        ("documents",)
        if task.operation == "explain"
        else ("tables", "documents")
        if task.operation in {"apply_policy", "combine"}
        else ("tables",),
    )


def verify_coverage(
    requirement: EvidenceRequirement,
    request: RequestContext,
    task: SemanticTask,
    plan: QueryPlan,
) -> None:
    """Validate scope, full task snapshot and predicate-preserving lowering before binding."""
    current = require_evidence(request, task)
    if current != requirement:
        raise ValueError("Evidence requirement belongs to a different request or task")
    verify_task_plan(task, plan)
    record_facts(coverage_status="represented")


def prepare_task_plan(task: SemanticTask, compiler: QueryCompiler) -> QueryPlan:
    """Bind task to server principal/catalog before the existing compiler can execute it."""
    try:
        request = bind_request(compiler.context, ("query", "combine", "apply_policy"))
        if request is None:
            raise ValueError("No server request identity")
        requirement = require_evidence(request, task)
        plan = task_query_plan(task)
        verify_coverage(requirement, request, task, plan)
        # The declared demo compiler already validates its four-table relationship
        # tree. Uploaded-data grain completion intentionally supports at most two
        # edges and must not be applied to that distinct, constructor-checked graph.
        return (
            plan
            if compiler.uses_declared_demo_schema
            else bind_approved_grain(plan, compiler.references)
        )
    except (ValueError, TypeError) as exc:
        raise ModelResponseError(
            "Semantic coverage is unresolved",
            error_context=ErrorContext(
                phase="verification",
                error_category="insufficient_evidence",
                reason_code="planning_scope_violation",
            ),
        ) from exc


def verify_compiled_task(
    task: SemanticTask, compiled: CompiledQuery, compiler: QueryCompiler
) -> None:
    """Check the execution artifact still corresponds to the bound semantic requirement.

    Compiler correctness itself is checked by independent execution oracles, not by
    calling this equality check an independent SQL oracle.
    """
    from sqlglot import parse_one

    expected = compiler.compile(prepare_task_plan(task, compiler))
    if (
        compiled.parameters != expected.parameters
        or parse_one(compiled.validated.statement, read="postgres")
        != parse_one(expected.validated.statement, read="postgres")
        or parse_one(compiled.evidence_sql, read="postgres")
        != parse_one(expected.evidence_sql, read="postgres")
        or compiled.validated.relationship_ids != expected.validated.relationship_ids
        or compiled.validated.count_metrics != expected.validated.count_metrics
    ):
        raise ModelResponseError(
            "Compiled evidence differs from the semantic requirement",
            error_context=ErrorContext(
                phase="verification",
                error_category="insufficient_evidence",
                reason_code="planning_scope_violation",
            ),
        )
    record_facts(coverage_status="compiled")
