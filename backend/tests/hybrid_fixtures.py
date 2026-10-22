"""Synthetic final-stage drafts; no provider or model-derived policy oracle."""

import hashlib
import json
import re

from app.rag.repository import DocumentScope, RetrievedChunk
from app.routing.hybrid_evidence import HybridAnswerDraft


def scoped_chunk(chunk_id, source_file, section_title, content, cosine_distance):
    return RetrievedChunk(
        chunk_id,
        source_file,
        section_title,
        content,
        cosine_distance,
        DocumentScope(
            "synthetic",
            hashlib.sha256(content.encode()).hexdigest(),
            (chunk_id,),
            0,
            None,
            ((chunk_id, hashlib.sha256(content.encode()).hexdigest()),),
        ),
    )


def prose_policy(
    entity_column: str,
    metric_column: str,
    threshold: str,
    aggregate="sum",
    unit="source units",
    operator="at least",
) -> str:
    subject = entity_column.removesuffix("_id").removesuffix("_code")
    return (
        f"Each {subject} qualifies when {aggregate} of {metric_column} "
        f"is {operator} {threshold} {unit}. "
        f"Include all rows. Identify each {subject} by {entity_column}."
    )


def explanation_draft(prompt: str, chunk_ids: list[int] | None = None) -> HybridAnswerDraft:
    evidence = prompt.split("Document evidence:\n", 1)[1]
    chunks = re.findall(r"\[chunk_id=(\d+);[^\n]*\]\n(.*?)(?=\n\n\[chunk_id=|\Z)", evidence, re.S)
    selected = chunk_ids if chunk_ids is not None else [int(chunks[0][0])]
    by_id = {int(i): content for i, content in chunks}
    return HybridAnswerDraft(
        mode="explanation",
        language="vi",
        identity_fields=[],
        metric_field=None,
        rule_id=None,
        decisions=[],
        notes=[{"chunk_id": i, "quote": by_id.get(i, "invalid citation")} for i in selected],
        used_chunk_ids=selected,
    )


def rule_block(
    entity_column: str,
    metric_column: str,
    threshold: str,
    *,
    aggregate: str = "sum",
    operator: str = "gte",
) -> str:
    return (
        "```shopquery-rule-v1\n"
        + json.dumps(
            {
                "version": 1,
                "rule_id": "synthetic-policy",
                "entity_column": entity_column,
                "metric_column": metric_column,
                "aggregate": aggregate,
                "operator": operator,
                "threshold": threshold,
                "unit": "source",
                "scope": "all_rows",
            }
        )
        + "\n```"
    )


def classification_draft(
    rows: list[dict],
    statuses: list[str],
    chunk_id: int,
    *,
    identity_field: str = "entity_id",
    metric_field: str = "total",
    verified: bool = True,
) -> HybridAnswerDraft:
    return HybridAnswerDraft(
        mode="classification",
        language="en",
        identity_fields=[identity_field],
        metric_field=metric_field,
        rule_id="synthetic-policy" if verified else None,
        decisions=[
            {
                "entity_values": [str(row[identity_field])],
                "status": status,
                "supporting_chunk_ids": [chunk_id],
            }
            for row, status in zip(rows, statuses, strict=True)
        ],
        notes=[],
        used_chunk_ids=[chunk_id],
    )


def assert_decision_summary(answer: str, rows: list[dict], statuses: list[str]) -> None:
    summary = answer.split("|", 1)[0]
    labels = {
        "qualified": "Qualified",
        "not_qualified": "Not qualified",
        "insufficient_evidence": "Insufficient evidence",
        "unverified": "Unverified",
    }
    for status, label in labels.items():
        expected = [
            str(row["entity_id"]) for row, s in zip(rows, statuses, strict=True) if s == status
        ]
        if expected:
            assert f"{label}: {', '.join(expected)}." in summary
    details = [line for line in answer.splitlines() if line.startswith("| ")][2:]
    assert len(details) == len(rows)
    for line, row, status in zip(details, rows, statuses, strict=True):
        assert str(row["entity_id"]) in line
        assert line.endswith(f"| {labels[status]} |")
