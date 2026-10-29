"""Resolve a narrow classification request against complete policy and registry evidence."""

import re
from typing import Literal

from app.core.diagnostics import diagnostic_stage
from app.core.errors import ModelResponseError, SqlValidationError
from app.datasets.context import DatasetSqlContext
from app.rag.repository import RetrievedChunk
from app.routing.hybrid_policy import numeric_policies, policy_content
from app.routing.hybrid_policy_binding import identity_source, verification_error, verified_policies
from app.routing.natural_policy import ProseRule, normalized, parse_prose
from app.text_to_sql.compiler import QueryCompiler, SchemaReferences
from app.text_to_sql.coverage import EvidenceCoverageRequirement, coverage_error
from app.text_to_sql.pipeline import SqlResult
from app.text_to_sql.plan_binding import bind_approved_grain

Selection = Literal["all", "qualified", "not_qualified"]


def classification_selection(
    question: str,
    prose: ProseRule,
    context: DatasetSqlContext,
) -> Selection | None:
    """Consume the entire current request; unknown filters/qualifiers never get dropped."""
    question = re.sub(r"^\s*/hybrid\s+", "", question, flags=re.I).strip().casefold()
    mentions = {prose.subject.casefold()}
    words = prose.subject.casefold().split()
    # An abbreviated entity noun must uniquely name an approved entity in this workspace.
    entity_labels = {
        normalized(re.sub(r"^\d+[ _-]*", "", context.table_labels.get(r.target_table, "")))
        for r in context.approved_joins
    }
    if (
        len(words) > 1
        and sum(label.startswith(normalized(words[0])) for label in entity_labels) == 1
    ):
        mentions.add(words[0])
    for mention in mentions:
        entity = re.escape(mention)
        if re.fullmatch(
            rf"(?:theo (?:tài liệu|chính sách)(?: kpi)?,? )?(?:những )?"
            rf"{entity} nào đạt(?: kpi)? và (?:{entity} nào )?chưa đạt(?: kpi)?[?.]?",
            question,
        ) or re.fullmatch(rf"which {entity}s? qualify and which do not\??", question):
            return "all"
        match = (
            re.fullmatch(
                rf"(?:theo (?:tài liệu|chính sách)(?: kpi)?,? )?(?:vậy (?:còn )?)?"
                rf"(?:những )?{entity} (?P<status>chưa đạt|đạt)(?: kpi)? "
                rf"(?:là )?(?:{entity} )?nào[?.]?",
                question,
            )
            or re.fullmatch(
                rf"(?:theo (?:tài liệu|chính sách)(?: kpi)?,? )?{entity} nào "
                rf"(?P<status>chưa đạt|đạt)(?: kpi)?[?.]?",
                question,
            )
            or re.fullmatch(
                rf"vậy còn (?:những )?{entity} (?P<status>chưa đạt|đạt)(?: kpi)?[?.]?",
                question,
            )
        )
        if match:
            return "not_qualified" if match["status"] == "chưa đạt" else "qualified"
        match = re.fullmatch(rf"which {entity}s? (?P<status>qualify|do not qualify)\??", question)
        if match:
            return "qualified" if match["status"] == "qualify" else "not_qualified"
    return None


def resolve_coverage(
    question: str,
    chunks: list[RetrievedChunk],
    context: DatasetSqlContext | None,
    *,
    classification: Selection | None = None,
) -> EvidenceCoverageRequirement | None:
    # A legacy classification flag contains no population/predicate evidence.
    # Production uses SemanticTask; this compatibility resolver must never turn
    # that flag into an all-entity execution grant.
    if classification is not None:
        return None
    if context is None:
        return None
    candidates = numeric_policies(chunks)
    if len(candidates) != 1:
        return None
    policy, chunk_id = next(iter(candidates.values()))
    chunk = next(c for c in chunks if c.chunk_id == chunk_id)
    content = policy_content(chunk, chunks)
    prose = parse_prose(content) if content is not None else None
    if prose is None or prose.aggregate not in {"sum", "avg"}:
        return None
    selection = (
        classification
        if classification is not None
        else classification_selection(question, prose, context)
    )
    if selection is None:
        return None
    with diagnostic_stage("plan_coverage_validation"):
        references = SchemaReferences.from_context(context)
        identities = set()
        for table, columns in context.table_columns.items():
            for column in columns:
                header = context.column_headers.get(table, {}).get(column, column)
                if normalized(prose.identity_reference) not in {
                    normalized(column),
                    normalized(header),
                }:
                    continue
                try:
                    identities.add(identity_source(table, column, context))
                except ModelResponseError:
                    continue
        measures = [
            (table, column)
            for table, columns in context.table_columns.items()
            for column in columns
            if context.column_types.get(table, {}).get(column) in {"NUMERIC", "BIGINT"}
            and normalized(prose.metric_reference)
            in {
                normalized(column),
                normalized(context.column_headers.get(table, {}).get(column, column)),
            }
        ]
        valid = []
        failure = None
        reverse = {location: key for key, location in references.columns.items()}
        for fact, measure in measures:
            for identity in sorted(identities):
                requirement = EvidenceCoverageRequirement(
                    source=next(key for key, table in references.tables.items() if table == fact),
                    identity=reverse[identity],
                    metric=reverse[(fact, measure)],
                    aggregate=prose.aggregate,
                    selection=selection,
                )
                try:
                    plan = bind_approved_grain(requirement.plan(), references)
                    requirement = EvidenceCoverageRequirement(
                        requirement.source,
                        requirement.identity,
                        requirement.metric,
                        requirement.aggregate,
                        tuple(plan.relationships),
                        selection,
                        context.table_row_counts.get(identity[0]),
                    )
                    compiled = QueryCompiler(context).compile(plan)
                    result = SqlResult(
                        "",
                        compiled.evidence_sql,
                        [],
                        compiled.validated.fact_table,
                        compiled.validated.count_metrics,
                    )
                    verified = verified_policies(result, chunks, context, require_verified=True)
                    if len(verified) == 1:
                        valid.append(requirement)
                except (ModelResponseError, SqlValidationError) as exc:
                    failure = exc
        if len(valid) != 1:
            if len(valid) > 1:
                raise verification_error("policy_ambiguous")
            if isinstance(failure, ModelResponseError):
                raise failure
            raise coverage_error()
        return valid[0]
