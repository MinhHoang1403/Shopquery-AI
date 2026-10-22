"""Bind complete policy evidence to authorized registry columns and validated SQL."""

import hashlib
import re
from decimal import Decimal
from typing import Any, NoReturn

from sqlglot import exp, parse_one

from app.core.errors import ModelResponseError
from app.datasets.context import DatasetSqlContext
from app.rag.repository import RetrievedChunk
from app.routing.hybrid_policy import NumericPolicy, numeric_policies
from app.routing.natural_policy import normalized, parse_prose
from app.text_to_sql.count_contract import output_field_name
from app.text_to_sql.pipeline import SqlResult


def _fail() -> NoReturn:
    raise ModelResponseError("Hybrid policy evidence could not be verified")


def projection_bindings(result: SqlResult) -> tuple[exp.Select, dict[str, exp.Expression]]:
    root = parse_one(result.sql, read="postgres")
    if not isinstance(root, exp.Select):
        _fail()
    bindings = {
        output_field_name(p): p.this if isinstance(p, exp.Alias) else p for p in root.expressions
    }
    if len(bindings) != len(root.expressions) or "" in bindings:
        _fail()
    return root, bindings


def validate_policy_binding(
    result: SqlResult, identity_fields: list[str], metric_field: str | None, policy: NumericPolicy
) -> None:
    root, bindings = projection_bindings(result)
    if root.args.get("where") or root.args.get("having") or root.args.get("limit"):
        _fail()
    if len(identity_fields) != 1 or metric_field is None:
        _fail()
    identity = bindings[identity_fields[0]]
    if identity.name != policy.entity_column:
        _fail()
    metric = bindings.get(metric_field)
    if policy.aggregate in {"sum", "avg"}:
        expected = exp.Sum if policy.aggregate == "sum" else exp.Avg
        if not isinstance(metric, expected) or not isinstance(metric.this, exp.Column):
            _fail()
        if metric.this.name != policy.metric_column:
            _fail()
    else:
        matches = [m for m in result.count_metrics if m.output_alias == metric_field]
        if len(matches) != 1 or matches[0].kind.value != policy.aggregate:
            _fail()
        if policy.aggregate == "row_count":
            if policy.metric_column != "*":
                _fail()
        elif matches[0].fact_column != policy.metric_column:
            _fail()
    if any(metric_field not in row for row in result.rows):
        _fail()


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
        _fail()
    return table, context.column_headers.get(table, {}).get(column.name, column.name)


def _bind_prose(
    result: SqlResult,
    chunk: RetrievedChunk,
    policy: NumericPolicy,
    context: DatasetSqlContext | None,
    content: str,
) -> NumericPolicy:
    prose = parse_prose(content)
    if prose is None or context is None or chunk.document_scope is None:
        _fail()
    scope = chunk.document_scope
    if scope.dataset_id != context.dataset_id or scope.owner_user_id != context.owner_user_id:
        _fail()
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
    if prose.relative_record and any(
        normalized(w) not in record_words for w in prose.relative_record.split()
    ):
        _fail()
    if prose.record_reference:
        if normalized(prose.record_reference) != normalized(fact_label):
            _fail()
        if not any(
            prose.status_example in values
            for values in context.categorical_values.get(fact, {}).values()
        ):
            _fail()
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
    if not title_words <= title_vocabulary:
        _fail()
    for field, expression in bindings.items():
        if isinstance(expression, exp.Column):
            table, header = source_column(root, expression, context)
            if normalized(prose.identity_reference) in {
                normalized(expression.name),
                normalized(header),
            }:
                target_key = any(
                    r.target_table == table and r.target_column == expression.name
                    for r in context.approved_joins
                )
                conventional = expression.name in {"id", "code"} or expression.name.endswith(
                    ("_id", "_code")
                )
                if not target_key and not conventional:
                    _fail()
                term = re.sub(r"_(id|code)$", "", expression.name)
                label = context.table_labels.get(table, "")
                label = re.sub(r"^\d+[ _-]*", "", label)
                if normalized(prose.subject).removesuffix("s") not in {
                    normalized(term).removesuffix("s"),
                    normalized(label).removesuffix("s"),
                }:
                    _fail()
                identities.append(expression.name)
                identity_tables.append(table)
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
                _fail()
            count_units = (
                {"source", "source units", "rows", "dòng"}
                if prose.aggregate == "row_count"
                else {"source", "source units", "values"}
            )
            if prose.unit not in count_units:
                _fail()
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
        if prose.aggregate in {"sum", "avg"} and prose.unit not in {"source", "source units"}:
            units = {
                normalized(w) for w in re.findall(r"[^\W_]+", header + " " + expression.this.name)
            }
            if normalized(prose.unit) not in units:
                _fail()
        if prose.criterion or prose.presentation_reference:
            vocabulary = {
                normalized(w) for w in re.findall(r"[^\W_]+", header + " " + expression.this.name)
            }
            vocabulary.update({"tong", "sum", "total", "trung", "binh", "average"})
            references = (prose.criterion or "") + " " + (prose.presentation_reference or "")
            if any(normalized(w) not in vocabulary for w in references.split()):
                _fail()
        metrics.append(expression.this.name)
    if len(identities) != 1 or len(metrics) != 1:
        _fail()
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
            _fail()
    return policy.model_copy(update={"entity_column": identities[0], "metric_column": metrics[0]})


def verified_policies(
    result: SqlResult, chunks: list[RetrievedChunk], context: DatasetSqlContext | None = None
) -> dict[str, tuple[NumericPolicy, int]]:
    root, _ = projection_bindings(result)
    if root.args.get("where") or root.args.get("having") or root.args.get("limit"):
        return {}
    candidates = numeric_policies(chunks)
    by_id = {c.chunk_id: c for c in chunks}
    verified = {}
    for rule_id, (policy, chunk_id) in candidates.items():
        chunk = by_id[chunk_id]
        scope = chunk.document_scope
        # Only a whole, single-chunk document is in this grammar's authority scope.
        if scope is None or scope.chunk_ids != (chunk_id,) or not scope.content_hash:
            continue
        if (
            dict(scope.text_hashes).get(chunk_id)
            != hashlib.sha256(chunk.content.encode()).hexdigest()
        ):
            continue
        if context is not None and (
            scope.dataset_id != context.dataset_id or scope.owner_user_id != context.owner_user_id
        ):
            continue
        if re.search(
            r"\b(except|unless|exceptions|only|if|not|ngoại lệ|trừ|chỉ|nếu|không|"
            r"tháng|năm)\b|[0-9<>=]",
            chunk.section_title,
            re.I,
        ):
            continue
        try:
            if rule_id.startswith("prose-"):
                policy = _bind_prose(result, chunk, policy, context, chunk.content)
            else:
                # A structured block does not override conflicting or unknown prose.
                rest = re.sub(
                    r"```shopquery-rule-v1\n.*?\n```", "", chunk.content, flags=re.S
                ).strip()
                if rest:
                    prose = parse_prose(rest)
                    if prose is None:
                        continue
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
                        continue
            verified[rule_id] = policy, chunk_id
        except ModelResponseError:
            continue
    if len(candidates) > 1 or len(verified) != len(candidates):
        return {}
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
