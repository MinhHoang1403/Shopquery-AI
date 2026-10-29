"""Bind complete policy evidence to authorized registry columns and validated SQL."""

import hashlib
import re
from decimal import Decimal
from typing import Any, NoReturn

from sqlglot import exp, parse_one

from app.core.diagnostics import record_facts
from app.core.errors import ErrorContext, ModelResponseError, VerificationReason
from app.datasets.context import DatasetSqlContext
from app.rag.repository import RetrievedChunk
from app.routing.hybrid_policy import NumericPolicy, numeric_policies, policy_content
from app.routing.natural_policy import normalized, parse_prose, regulation_title_supported
from app.text_to_sql.count_contract import output_field_name
from app.text_to_sql.pipeline import SqlResult


def verification_error(reason: VerificationReason) -> ModelResponseError:
    return ModelResponseError(
        "Chưa đủ bằng chứng để kết luận chính xác từ dữ liệu hiện có.",
        error_context=ErrorContext(
            phase="verification",
            error_category="insufficient_evidence",
            reason_code=reason,
        ),
    )


def _fail(reason: VerificationReason) -> NoReturn:
    raise verification_error(reason)


def identity_source(table: str, column: str, context: DatasetSqlContext) -> tuple[str, str]:
    """Resolve an approved foreign key to its unique entity key without adding a JOIN."""
    targets = {
        (edge.target_table, edge.target_column)
        for edge in context.approved_joins
        if edge.source_table == table and edge.source_column == column
    }
    if len(targets) > 1:
        _fail("policy_join_path_ambiguous")
    if targets:
        target = next(iter(targets))
        if target[1] not in context.table_columns.get(target[0], set()):
            _fail("policy_identity_unbound")
        return target
    if any(
        edge.target_table == table and edge.target_column == column
        for edge in context.approved_joins
    ):
        return table, column
    if column in {"id", "code"} or column.endswith(("_id", "_code")):
        return table, column
    _fail("policy_identity_unbound")


def projection_bindings(result: SqlResult) -> tuple[exp.Select, dict[str, exp.Expression]]:
    root = parse_one(result.sql, read="postgres")
    if not isinstance(root, exp.Select):
        _fail("answer_draft_inconsistent")
    bindings = {
        output_field_name(p): p.this if isinstance(p, exp.Alias) else p for p in root.expressions
    }
    if len(bindings) != len(root.expressions) or "" in bindings:
        _fail("answer_draft_inconsistent")
    return root, bindings


def validate_policy_binding(
    result: SqlResult, identity_fields: list[str], metric_field: str | None, policy: NumericPolicy,
    context: DatasetSqlContext | None = None,
) -> None:
    root, bindings = projection_bindings(result)
    if (root.args.get("having") or root.args.get("limit") or (
        root.args.get("where") and not entity_population_filter(root, context)
    )):
        _fail("policy_sql_scope_incomplete")
    if len(identity_fields) != 1 or metric_field is None:
        _fail("policy_identity_unbound")
    identity = bindings.get(identity_fields[0])
    if not isinstance(identity, exp.Column) or identity.name != policy.entity_column:
        _fail("policy_identity_unbound")
    metric = bindings.get(metric_field)
    if policy.aggregate in {"sum", "avg"}:
        expected = exp.Sum if policy.aggregate == "sum" else exp.Avg
        if not isinstance(metric, expected) or not isinstance(metric.this, exp.Column):
            _fail("policy_aggregate_mismatch")
        if metric.this.name != policy.metric_column:
            _fail("policy_metric_unbound")
    else:
        matches = [m for m in result.count_metrics if m.output_alias == metric_field]
        if len(matches) != 1 or matches[0].kind.value != policy.aggregate:
            _fail("policy_aggregate_mismatch")
        if policy.aggregate == "row_count":
            if policy.metric_column != "*":
                _fail("policy_metric_unbound")
        elif matches[0].fact_column != policy.metric_column:
            _fail("policy_metric_unbound")
    if any(metric_field not in row for row in result.rows):
        _fail("policy_metric_unbound")


def source_column(
    root: exp.Select, column: exp.Column, context: DatasetSqlContext
) -> tuple[str, str]:
    aliases = {t.alias_or_name: t.name for t in root.find_all(exp.Table)}
    table = (
        aliases.get(column.table)
        if column.table
        else next(iter(aliases.values()))
        if len(aliases) == 1
        else None
    )
    if table not in context.table_columns or column.name not in context.table_columns[table]:
        _fail("policy_source_table_mismatch")
    return table, context.column_headers.get(table, {}).get(column.name, column.name)


def entity_population_filter(root: exp.Select, context: DatasetSqlContext | None) -> bool:
    """Prove WHERE selects entities, rather than discarding some facts per entity.

    The existing compiler/approved N:1 guards remain prerequisites. Only predicates
    on the single grouped entity's attributes or its equivalent fact foreign key
    qualify. A service/status/date filter on other tables is not such a proof.
    """
    if context is None or root.args.get("where") is None or root.args.get("group") is None:
        return False
    aliases = {table.alias_or_name: table.name for table in root.find_all(exp.Table)}
    identities = set()
    for expression in root.args["group"].expressions:
        if not isinstance(expression, exp.Column):
            continue
        table = aliases.get(expression.table)
        try:
            if table is not None:
                identities.add(identity_source(table, expression.name, context))
        except ModelResponseError:
            continue
    if len(identities) != 1:
        return False
    entity = next(iter(identities))
    dimension_key = any(
        edge.target_table == entity[0] and edge.target_column == entity[1]
        for edge in context.approved_joins
    )
    columns = list(root.args["where"].find_all(exp.Column))
    if not columns:
        return False
    for column in columns:
        table = aliases.get(column.table)
        if table == entity[0] and (dimension_key or column.name == entity[1]):
            continue
        try:
            if table is not None and identity_source(table, column.name, context) == entity:
                continue
        except ModelResponseError:
            pass
        return False
    return True


def _bind_prose(
    result: SqlResult,
    chunk: RetrievedChunk,
    policy: NumericPolicy,
    context: DatasetSqlContext | None,
    content: str,
) -> NumericPolicy:
    prose = parse_prose(content)
    if prose is None:
        _fail("policy_parse_failed")
    if context is None or chunk.document_scope is None:
        _fail("policy_document_scope_invalid")
    scope = chunk.document_scope
    if scope.dataset_id != context.dataset_id or scope.owner_user_id != context.owner_user_id:
        _fail("policy_document_scope_invalid")
    root, bindings = projection_bindings(result)
    aliases = {t.alias_or_name: t.name for t in root.find_all(exp.Table)}
    fact = (
        result.fact_table or next(iter(aliases.values()))
        if len(aliases) == 1
        else result.fact_table
    )
    identities = []
    metrics = []
    identity_tables = []
    fact_label = re.sub(r"^\d+[ _-]*", "", context.table_labels.get(fact, ""))
    record_words = {normalized(w) for w in re.findall(r"[^\W_]+", fact_label)}
    if prose.period is not None:
        profiles = context.column_profiles.get(fact, {})
        temporal = [
            name for name, kind in context.column_types.get(fact, {}).items() if kind == "DATE"
        ]
        statuses = [
            name
            for name, values in context.categorical_values.get(fact, {}).items()
            if any(normalized(value) == normalized(prose.required_status or "") for value in values)
        ]
        if len(temporal) != 1 or len(statuses) != 1:
            _fail("policy_sql_scope_incomplete")
        period, status = profiles.get(temporal[0]), profiles.get(statuses[0])
        if (
            period is None
            or status is None
            or period[0] <= 0
            or period[0] != period[1]
            or status[0] != status[1]
            or period[0] != status[0]
            or period[2] is None
            or period[3] is None
            or not (prose.period[0] <= period[2] <= period[3] <= prose.period[1])
            or status[2] != status[3]
            or normalized(status[2] or "") != normalized(prose.required_status or "")
        ):
            _fail("policy_sql_scope_incomplete")
    if prose.relative_record and any(
        normalized(w) not in record_words for w in prose.relative_record.split()
    ):
        _fail("policy_source_table_mismatch")
    if prose.record_reference:
        if normalized(prose.record_reference) != normalized(fact_label):
            _fail("policy_source_table_mismatch")
        if not any(
            prose.status_example in values
            for values in context.categorical_values.get(fact, {}).values()
        ):
            _fail("policy_unsupported_qualifier")
    title_words = {normalized(w) for w in re.findall(r"[^\W_]+", chunk.section_title)}
    title_vocabulary = {
        normalized(w)
        for w in re.findall(
            r"[^\W_]+",
            prose.metric_reference + " " + prose.identity_reference + " " + prose.subject,
        )
    }
    title_vocabulary.update(
        {
            "policy",
            "synthetic",
            "kpi",
            "rule",
            "explicit",
            "numeric",
            "tong",
            "trung",
            "binh",
            "sum",
            "average",
        }
    )
    if not prose.declared_unit and not title_words <= title_vocabulary:
        _fail("policy_unsupported_qualifier")
    for field, expression in bindings.items():
        if isinstance(expression, exp.Column):
            table, header = source_column(root, expression, context)
            if normalized(prose.identity_reference) in {
                normalized(expression.name),
                normalized(header),
            }:
                entity_table, entity_key = identity_source(table, expression.name, context)
                term = re.sub(r"_(id|code)$", "", entity_key)
                label = context.table_labels.get(entity_table, "")
                label = re.sub(r"^\d+[ _-]*", "", label)
                if normalized(prose.subject).removesuffix("s") not in {
                    normalized(term).removesuffix("s"),
                    normalized(label).removesuffix("s"),
                }:
                    _fail("policy_identity_unbound")
                identities.append(expression.name)
                identity_tables.append(entity_table)
        expected = (
            exp.Sum
            if prose.aggregate == "sum"
            else exp.Avg
            if prose.aggregate == "avg"
            else exp.Count
        )
        if not isinstance(expression, expected):
            continue
        if prose.aggregate in {"row_count", "non_null_value_count"}:
            if prose.criterion or prose.presentation_reference:
                _fail("policy_unsupported_qualifier")
            count_units = (
                {"source", "source units", "rows", "dòng"}
                if prose.aggregate == "row_count"
                else {"source", "source units", "values"}
            )
            if prose.unit not in count_units:
                _fail("policy_unit_mismatch")
            counts = [
                m
                for m in result.count_metrics
                if m.output_alias == field and m.kind.value == prose.aggregate
            ]
            if len(counts) != 1 or counts[0].root_fact != fact:
                continue
            if prose.aggregate == "row_count":
                if normalized(prose.metric_reference) != normalized(
                    context.table_labels.get(fact, "")
                ):
                    continue
                metrics.append("*")
                continue
        if not isinstance(expression.this, exp.Column):
            continue
        table, header = source_column(root, expression.this, context)
        if table != fact or normalized(prose.metric_reference) not in {
            normalized(expression.this.name),
            normalized(header),
        }:
            continue
        if (
            prose.aggregate in {"sum", "avg"}
            and prose.unit not in {"source", "source units"}
            and not prose.declared_unit
        ):
            units = {
                normalized(w) for w in re.findall(r"[^\W_]+", header + " " + expression.this.name)
            }
            if normalized(prose.unit) not in units:
                _fail("policy_unit_mismatch")
        if prose.criterion or prose.presentation_reference:
            vocabulary = {
                normalized(w) for w in re.findall(r"[^\W_]+", header + " " + expression.this.name)
            }
            vocabulary.update({"tong", "sum", "total", "trung", "binh", "average"})
            references = (prose.criterion or "") + " " + (prose.presentation_reference or "")
            if any(normalized(w) not in vocabulary for w in references.split()):
                _fail("policy_unsupported_qualifier")
        metrics.append(expression.this.name)
    if len(identities) != 1:
        _fail("policy_identity_unbound")
    if len(metrics) != 1:
        _fail("policy_metric_unbound")
    if prose.via_reference:
        via = [
            t
            for t in aliases.values()
            if normalized(re.sub(r"^\d+[ _-]*", "", context.table_labels.get(t, "")))
            == normalized(prose.via_reference)
        ]
        if (
            len(via) != 1
            or not any(
                r.source_table == fact and r.target_table == via[0] for r in context.approved_joins
            )
            or not any(
                r.source_table == via[0] and r.target_table == identity_tables[0]
                for r in context.approved_joins
            )
        ):
            _fail("policy_join_path_ambiguous")
    return policy.model_copy(update={"entity_column": identities[0], "metric_column": metrics[0]})


def verified_policies(
    result: SqlResult,
    chunks: list[RetrievedChunk],
    context: DatasetSqlContext | None = None,
    *,
    require_verified: bool = False,
) -> dict[str, tuple[NumericPolicy, int]]:
    def reject(
        reason: VerificationReason, candidate_count: int = 0
    ) -> dict[str, tuple[NumericPolicy, int]]:
        error = verification_error(reason)
        error.error_context = error.error_context.model_copy(
            update={
                "candidate_count": min(candidate_count, 1000000),
                "verified_policy_count": 0,
                "retrieved_chunk_count": min(len(chunks), 1000000),
                "sql_row_count": min(len(result.rows), 1000000),
            }
        )
        record_facts(policy_verification=error.error_context)
        if require_verified:
            raise error
        return {}

    root, _ = projection_bindings(result)
    if (root.args.get("having") or root.args.get("limit") or (
        root.args.get("where") and not entity_population_filter(root, context)
    )):
        return reject("policy_sql_scope_incomplete")
    if not chunks:
        return reject("policy_not_retrieved")
    try:
        candidates = numeric_policies(chunks)
    except ModelResponseError as exc:
        raise verification_error("policy_parse_failed") from exc
    if not candidates:
        return reject("policy_parse_failed")
    if len(candidates) > 1:
        return reject("policy_multiple_candidates", len(candidates))
    by_id = {c.chunk_id: c for c in chunks}
    verified = {}
    for rule_id, (policy, chunk_id) in candidates.items():
        chunk = by_id[chunk_id]
        scope = chunk.document_scope
        # Only a whole, single-chunk document is in this grammar's authority scope.
        content = policy_content(chunk, chunks)
        if scope is None or content is None or not scope.content_hash:
            return reject("policy_document_scope_invalid", len(candidates))
        if (
            dict(scope.text_hashes).get(chunk_id)
            != hashlib.sha256(chunk.content.encode()).hexdigest()
        ):
            return reject("policy_document_hash_mismatch", len(candidates))
        if context is not None and (
            scope.dataset_id != context.dataset_id or scope.owner_user_id != context.owner_user_id
        ):
            return reject("policy_document_scope_invalid", len(candidates))
        whole_prose = parse_prose(content)
        if (
            whole_prose is not None
            and whole_prose.declared_unit
            and any(
                not regulation_title_supported(c.section_title, whole_prose)
                for c in chunks
                if c.chunk_id in scope.chunk_ids
            )
        ):
            return reject("policy_unsupported_qualifier", len(candidates))
        if not (whole_prose and whole_prose.declared_unit) and re.search(
            r"\b(except|unless|exceptions|only|if|not|ngoại lệ|trừ|chỉ|nếu|không|"
            r"tháng|năm)\b|[0-9<>=]",
            chunk.section_title,
            re.I,
        ):
            return reject("policy_unsupported_qualifier", len(candidates))
        try:
            if rule_id.startswith("prose-"):
                policy = _bind_prose(result, chunk, policy, context, content)
            else:
                # A structured block does not override conflicting or unknown prose.
                rest = re.sub(
                    r"```shopquery-rule-v1\n.*?\n```", "", chunk.content, flags=re.S
                ).strip()
                if rest:
                    prose = parse_prose(rest)
                    if prose is None:
                        return reject("policy_parse_failed", len(candidates))
                    bound = _bind_prose(result, chunk, policy, context, rest)
                    if (
                        bound.entity_column,
                        bound.metric_column,
                        prose.aggregate,
                        prose.operator,
                        Decimal(prose.threshold),
                    ) != (
                        policy.entity_column,
                        policy.metric_column,
                        policy.aggregate,
                        policy.operator,
                        Decimal(policy.threshold),
                    ):
                        return reject("policy_ambiguous", len(candidates))
            verified[rule_id] = policy, chunk_id
        except ModelResponseError as exc:
            return reject(exc.error_context.reason_code or "policy_not_verified", len(candidates))
    record_facts(
        policy_verification=ErrorContext(
            candidate_count=len(candidates),
            verified_policy_count=len(verified),
            retrieved_chunk_count=min(len(chunks), 1000000),
            sql_row_count=min(len(result.rows), 1000000),
        )
    )
    return verified


def policy_evidence(
    result: SqlResult,
    chunks: list[RetrievedChunk],
    context: DatasetSqlContext | None,
) -> list[dict[str, Any]]:
    by_id = {c.chunk_id: c for c in chunks}
    evidence = []
    for policy, chunk_id in verified_policies(result, chunks, context).values():
        chunk = by_id[chunk_id]
        prose = parse_prose(chunk.content)
        evidence.append(
            {
                **policy.model_dump(),
                "chunk_id": chunk_id,
                "quote": chunk.content,
                "span_start": 0,
                "span_end": len(chunk.content),
                "chunk_text_sha256": hashlib.sha256(chunk.content.encode()).hexdigest(),
                "document_hash": chunk.document_scope.content_hash,
                "declared_unit": prose.unit if prose else "source",
                "status": "source_bound_candidate; final AST/coverage/status verification required",
            }
        )
    return evidence
