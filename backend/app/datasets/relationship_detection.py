"""Identifier evidence proposes joins; full-data verification alone activates none."""

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from time import monotonic

from sqlalchemy import Connection

from app.core.diagnostics import diagnostic_stage
from app.datasets.parser import ColumnSpec
from app.datasets.relationships import (
    RelationshipInput,
    RelationshipPreview,
    RelationshipSuggestion,
    RelationshipTable,
    verify_relationship,
)

MAX_DISCOVERY_CHECKS = 20
MAX_DISCOVERY_SECONDS = 2.0
_KEY_MARKERS = {"id", "code", "ma", "ref", "key", "number", "no"}
_KEY_FAMILIES = {
    "id": "id",
    "ref": "id",
    "key": "id",
    "code": "code",
    "ma": "code",
    "number": "number",
    "no": "number",
}
_TABLE_WRAPPERS = (
    ("danh", "sach"),
    ("danh", "muc"),
    ("list", "of"),
    ("catalog",),
    ("catalogue",),
    ("list",),
    ("master",),
    ("ds",),
    ("dm",),
)


def _words(label: str) -> tuple[str, ...]:
    value = unicodedata.normalize("NFKD", label.replace("đ", "d").replace("Đ", "D"))
    value = value.encode("ascii", "ignore").decode()
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    words = re.findall(r"[a-z0-9]+", value.lower())
    return tuple(
        word[:-3] + "y"
        if word.endswith("ies")
        else word[:-1]
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss")
        else word
        for word in words
    )


def _table_words(label: str) -> tuple[str, ...]:
    words = _words(label)
    while words and words[0].isdigit():
        words = words[1:]
    for wrapper in _TABLE_WRAPPERS:
        if words[: len(wrapper)] == wrapper:
            words = words[len(wrapper) :]
        if words[-len(wrapper) :] == wrapper:
            words = words[: -len(wrapper)]
    return words


def _key(column: ColumnSpec) -> tuple[tuple[str, ...], str] | None:
    if column.data_type not in {"TEXT", "BIGINT"}:
        return None
    # The original header preserves camelCase boundaries lost by SQL normalization.
    words = _words(column.source_name)
    if not words:
        return None
    if words[0] in _KEY_MARKERS:
        return words[1:], words[0]
    if words[-1] in _KEY_MARKERS:
        return words[:-1], words[-1]
    return None


def _entity_label(table: RelationshipTable, entity: tuple[str, ...]) -> bool:
    for column in table.columns:
        words = _words(column.source_name)
        if words in {("ten", *entity), (*entity, "name"), (*entity, "label")}:
            return True
    return False


@dataclass(frozen=True)
class _Candidate:
    request: RelationshipInput
    strong: bool
    score: int


def _candidates(tables: dict[str, RelationshipTable]) -> list[_Candidate]:
    result = []
    for source in tables.values():
        for key in source.columns:
            identity = _key(key)
            if not identity or not identity[0]:
                continue
            entity, marker = identity
            for target in tables.values():
                if source.table_id == target.table_id:
                    continue
                label = _table_words(target.display_name)
                exact = label == entity
                if label[: len(entity)] != entity:
                    continue
                for column in target.columns:
                    target_identity = _key(column)
                    if column.data_type != key.data_type or target_identity is None:
                        continue
                    if _KEY_FAMILIES[marker] != _KEY_FAMILIES[target_identity[1]]:
                        continue
                    if target_identity[0] not in {entity, ()}:
                        continue
                    explicit = target_identity[0] == entity
                    support = _entity_label(target, entity)
                    single_role = all(
                        target_key[0] == entity
                        for c in target.columns
                        if (target_key := _key(c)) is not None
                    )
                    strong = exact or (explicit and support and single_role)
                    if marker in {"number", "no"} or target_identity[1] in {"number", "no"}:
                        strong = strong and (
                            support
                            or any(
                                _words(c.source_name) in {("name",), ("ten",)}
                                for c in target.columns
                                if c.name != column.name
                            )
                        )
                    result.append(
                        _Candidate(
                            RelationshipInput(
                                source_table_id=source.table_id,
                                source_column=key.name,
                                target_table_id=target.table_id,
                                target_column=column.name,
                            ),
                            strong,
                            2 * int(exact) + int(explicit) + int(support),
                        )
                    )
    return sorted(result, key=lambda c: (-c.score, c.request.model_dump_json()))


def _pair(request: RelationshipInput) -> frozenset[str]:
    return frozenset({request.source_table_id, request.target_table_id})


def _unambiguous(candidates: list[_Candidate]) -> list[_Candidate]:
    keys = Counter((c.request.source_table_id, c.request.source_column) for c in candidates)
    pairs = Counter(_pair(c.request) for c in candidates)
    return [
        c
        for c in candidates
        if c.strong
        and keys[c.request.source_table_id, c.request.source_column] == 1
        and pairs[_pair(c.request)] == 1
    ]


def relationship_candidates(
    tables: dict[str, RelationshipTable],
    new_table_id: str | None,
) -> list[RelationshipInput]:
    """Return naming-unambiguous candidates, never proof of an approved relationship."""
    return [
        c.request
        for c in _unambiguous(_candidates(tables))
        if new_table_id is None or new_table_id in _pair(c.request)
    ]


def _alternate_path(pair: frozenset[str], edges: set[frozenset[str]]) -> bool:
    source, target = sorted(pair)
    graph: dict[str, set[str]] = defaultdict(set)
    for edge in edges - {pair}:
        left, right = sorted(edge)
        graph[left].add(right)
        graph[right].add(left)
    pending, visited = [source], set()
    while pending:
        node = pending.pop()
        if node == target:
            return True
        if node not in visited:
            visited.add(node)
            pending.extend(graph[node] - visited)
    return False


@dataclass
class RelationshipDiscovery:
    automatic: list[RelationshipPreview] = field(default_factory=list)
    suggestions: list[RelationshipSuggestion] = field(default_factory=list)
    truncated: bool = False


@diagnostic_stage("relationship_discovery")
def discover_relationships(
    connection: Connection,
    tables: dict[str, RelationshipTable],
    new_table_id: str | None,
    existing_pairs: set[frozenset[str]],
) -> RelationshipDiscovery:
    candidates = _candidates(tables)
    unambiguous = {c.request.model_dump_json() for c in _unambiguous(candidates)}
    edges = existing_pairs | {_pair(c.request) for c in candidates}
    candidates = [
        c
        for c in candidates
        if _pair(c.request) not in existing_pairs
        and (new_table_id is None or new_table_id in _pair(c.request))
    ]
    result = RelationshipDiscovery(truncated=len(candidates) > MAX_DISCOVERY_CHECKS)
    started = monotonic()
    for candidate in candidates[:MAX_DISCOVERY_CHECKS]:
        if monotonic() - started >= MAX_DISCOVERY_SECONDS:
            result.truncated = True
            break
        request = candidate.request
        preview = verify_relationship(connection, request, tables)
        safe = (
            not result.truncated
            and request.model_dump_json() in unambiguous
            and not _alternate_path(_pair(request), edges)
        )
        if safe and preview.valid and preview.cardinality == "many-to-one":
            result.automatic.append(preview)
        else:
            reason = (
                "Cần xác nhận ý nghĩa khóa, chiều nối hoặc ứng viên/đường nối cạnh tranh."
                if preview.valid
                else "Không kích hoạt: " + " ".join(preview.reasons)
            )
            result.suggestions.append(
                RelationshipSuggestion(
                    relationship=request,
                    preview=preview,
                    reason=reason,
                )
            )
    # A time limit must not make the first visited candidate win over unchecked peers.
    if result.truncated:
        result.suggestions.extend(
            RelationshipSuggestion(
                relationship=p,
                preview=p,
                reason="Đã chạm giới hạn quét; cần kiểm tra và xác nhận thủ công.",
            )
            for p in result.automatic
        )
        result.automatic.clear()
    return result


def detect_relationships(
    connection: Connection,
    tables: dict[str, RelationshipTable],
    new_table_id: str,
    existing_pairs: set[frozenset[str]],
) -> list[RelationshipPreview]:
    return discover_relationships(connection, tables, new_table_id, existing_pairs).automatic
