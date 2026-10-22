"""Typed numeric candidates from explicit blocks or a closed prose grammar."""

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.errors import ModelResponseError
from app.rag.repository import RetrievedChunk
from app.routing.natural_policy import parse_prose


class NumericPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    rule_id: str = Field(min_length=1, max_length=100)
    entity_column: str = Field(min_length=1, max_length=63)
    metric_column: str = Field(min_length=1, max_length=63)
    aggregate: Literal["sum", "avg", "row_count", "non_null_value_count"]
    operator: Literal["gte", "gt", "lte", "lt", "eq"]
    threshold: str = Field(max_length=100)
    unit: Literal["source"]
    scope: Literal["all_rows"]


def decimal_value(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ModelResponseError("Hybrid numeric evidence is not exact")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ModelResponseError("Hybrid numeric evidence is invalid") from exc
    if not result.is_finite():
        raise ModelResponseError("Hybrid numeric evidence is not finite")
    return result


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate policy property")
        result[key] = value
    return result


def numeric_policies(chunks: list[RetrievedChunk]) -> dict[str, tuple[NumericPolicy, int]]:
    """Parse candidates only; source completeness, bindings and verdict need verification."""
    policies: dict[str, tuple[NumericPolicy, int]] = {}
    for chunk in chunks:
        lines = chunk.content.splitlines()
        index = 0
        while index < len(lines):
            if lines[index] != "```shopquery-rule-v1":
                index += 1
                continue
            index += 1
            body = []
            while index < len(lines) and lines[index] != "```":
                body.append(lines[index])
                index += 1
            if index == len(lines):
                raise ModelResponseError("Hybrid policy block is incomplete")
            try:
                policy = NumericPolicy.model_validate(
                    json.loads("\n".join(body), object_pairs_hook=_unique_object)
                )
                decimal_value(policy.threshold)
            except (ValueError, ValidationError) as exc:
                raise ModelResponseError("Hybrid policy block is invalid") from exc
            if policy.rule_id in policies:
                raise ModelResponseError("Hybrid policy identity is ambiguous")
            policies[policy.rule_id] = policy, chunk.chunk_id
            index += 1
        if "```shopquery-rule-v1" not in chunk.content:
            prose = parse_prose(chunk.content)
            if prose is not None:
                rule_id = "prose-" + hashlib.sha256(chunk.content.encode()).hexdigest()[:20]
                policy = NumericPolicy(
                    version=1,
                    rule_id=rule_id,
                    entity_column=prose.identity_reference,
                    metric_column=prose.metric_reference,
                    aggregate=prose.aggregate,
                    operator=prose.operator,
                    threshold=prose.threshold,
                    unit="source",
                    scope="all_rows",
                )
                policies[rule_id] = policy, chunk.chunk_id
    return policies


def evaluate(value: object, policy: NumericPolicy) -> str:
    if value is None:
        return "insufficient_evidence"
    actual, threshold = decimal_value(value), decimal_value(policy.threshold)
    passed = {
        "gte": actual >= threshold,
        "gt": actual > threshold,
        "lte": actual <= threshold,
        "lt": actual < threshold,
        "eq": actual == threshold,
    }[policy.operator]
    return "qualified" if passed else "not_qualified"
