"""Conservative naming candidates followed by the existing full-data JOIN checks."""

import re
import unicodedata
from collections import defaultdict

from sqlalchemy import Connection

from app.core.diagnostics import diagnostic_stage
from app.datasets.relationships import (
    MAX_RELATIONSHIPS,
    RelationshipInput,
    RelationshipPreview,
    RelationshipTable,
    verify_relationship,
)


def _entity_name(label: str) -> str:
    value = unicodedata.normalize("NFKD", label.lower().replace("đ", "d"))
    value = re.sub(r"[^a-z0-9]+", "_", value.encode("ascii", "ignore").decode()).strip("_")
    value = re.sub(r"^\d+_", "", value)
    if value.endswith("ies"):
        return value[:-3] + "y"
    return value[:-1] if value.endswith("s") and not value.endswith("ss") else value


def relationship_candidates(
    tables: dict[str, RelationshipTable], new_table_id: str
) -> list[RelationshipInput]:
    candidates: dict[tuple[str, str], list[RelationshipInput]] = defaultdict(list)
    for source in tables.values():
        for key in source.columns:
            prefix, separator, suffix = key.name.rpartition("_")
            if not separator or suffix not in {"id", "code"} or not prefix:
                continue
            if key.data_type not in {"TEXT", "BIGINT"}:
                continue
            for target in tables.values():
                if source.table_id == target.table_id:
                    continue
                if _entity_name(target.display_name) != prefix:
                    continue
                for column in target.columns:
                    if column.name not in {key.name, suffix} or column.data_type != key.data_type:
                        continue
                    candidates[(source.table_id, key.name)].append(
                        RelationshipInput(
                            source_table_id=source.table_id,
                            source_column=key.name,
                            target_table_id=target.table_id,
                            target_column=column.name,
                        )
                    )
    result = [
        items[0]
        for items in candidates.values()
        if len(items) == 1 and new_table_id in {items[0].source_table_id, items[0].target_table_id}
    ]
    # Do not choose an arbitrary key or direction for the same table pair.
    pairs: dict[frozenset[str], list[RelationshipInput]] = defaultdict(list)
    for item in result:
        pairs[frozenset({item.source_table_id, item.target_table_id})].append(item)
    result = [items[0] for items in pairs.values() if len(items) == 1]
    return result if len(result) <= MAX_RELATIONSHIPS else []


@diagnostic_stage("relationship_discovery")
def detect_relationships(
    connection: Connection,
    tables: dict[str, RelationshipTable],
    new_table_id: str,
    existing_pairs: set[frozenset[str]],
) -> list[RelationshipPreview]:
    result = []
    for request in relationship_candidates(tables, new_table_id):
        if frozenset({request.source_table_id, request.target_table_id}) in existing_pairs:
            continue
        preview = verify_relationship(connection, request, tables)
        # 1:1 direction cannot establish a fact grain automatically.
        if preview.valid and preview.cardinality == "many-to-one":
            result.append(preview)
    return result
