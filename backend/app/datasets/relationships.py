"""Bounded full-data verification of explicit fact-to-dimension relationships."""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import Connection, column, func, select, table
from sqlalchemy.sql.elements import ColumnClause

from app.core.errors import ResourceNotFoundError
from app.datasets.parser import ColumnSpec

MAX_RELATIONSHIPS = 20
KEY_TYPES = {"TEXT", "BIGINT", "NUMERIC", "BOOLEAN", "DATE", "TIMESTAMP", "TIMESTAMPTZ"}


class RelationshipInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_table_id: str = Field(min_length=1, max_length=64, strict=True)
    source_column: str = Field(pattern=r"^[a-z_][a-z0-9_]{0,62}$")
    target_table_id: str = Field(min_length=1, max_length=64, strict=True)
    target_column: str = Field(pattern=r"^[a-z_][a-z0-9_]{0,62}$")


class RelationshipConfirm(RelationshipInput):
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Confirmation must be the boolean true")
        return value


class RelationshipPreview(RelationshipInput):
    revision: str
    valid: bool
    cardinality: Literal["many-to-one", "one-to-one"] | None
    source_rows: int
    target_rows: int
    source_nulls: int
    target_nulls: int
    target_duplicates: int
    orphan_rows: int | None
    reasons: list[str]


class RelationshipRecord(RelationshipPreview):
    relationship_id: str
    confirmed: bool = True
    origin: Literal["manual", "automatic"] = "manual"

    @model_validator(mode="after")
    def confirmation_origin(self) -> "RelationshipRecord":
        if self.confirmed != (self.origin == "manual"):
            raise ValueError("Automatic verification is not a user's confirmation")
        return self


class RelationshipSuggestion(BaseModel):
    relationship: RelationshipInput
    preview: RelationshipPreview
    reason: str


class RelationshipDiscoveryResponse(BaseModel):
    relationships: list[RelationshipRecord]
    suggestions: list[RelationshipSuggestion]
    truncated: bool


@dataclass(frozen=True)
class RelationshipTable:
    table_id: str
    physical_name: str
    columns: tuple[ColumnSpec, ...]
    row_count: int
    schema: str = "uploaded_data"
    display_name: str = ""


def relationship_revision(
    request: RelationshipInput,
    tables: dict[str, RelationshipTable],
) -> str:
    source, target = relationship_tables(request, tables)
    metadata = [
        [
            item.table_id,
            item.table_id if item.schema == "pg_temp" else item.physical_name,
            item.schema,
            item.row_count,
            [col.as_dict() for col in item.columns],
        ]
        for item in (source, target)
    ]
    encoded = json.dumps(
        [request.model_dump(include=set(RelationshipInput.model_fields)), metadata],
        sort_keys=True,
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def relationship_tables(
    request: RelationshipInput,
    tables: dict[str, RelationshipTable],
) -> tuple[RelationshipTable, RelationshipTable]:
    source, target = tables.get(request.source_table_id), tables.get(request.target_table_id)
    if source is None or target is None:
        raise ResourceNotFoundError("Không tìm thấy hai bảng trong workspace/phiên hiện tại.")
    if source.table_id == target.table_id or source.physical_name == target.physical_name:
        raise ResourceNotFoundError("Cần chọn hai bảng khác nhau.")
    for item, name in ((source, request.source_column), (target, request.target_column)):
        if not any(col.name == name for col in item.columns):
            raise ResourceNotFoundError("Không tìm thấy cột khóa trong bảng đã chọn.")
    return source, target


def verify_relationship(
    connection: Connection,
    request: RelationshipInput,
    tables: dict[str, RelationshipTable],
) -> RelationshipPreview:
    source, target = relationship_tables(request, tables)
    fact = table(source.physical_name, column(request.source_column), schema=source.schema)
    dimension = table(target.physical_name, column(request.target_column), schema=target.schema)
    source_key, target_key = fact.c[request.source_column], dimension.c[request.target_column]
    source_type = next(c.data_type for c in source.columns if c.name == request.source_column)
    target_type = next(c.data_type for c in target.columns if c.name == request.target_column)

    def counts(key: ColumnClause) -> tuple[int, int, int]:
        row = connection.execute(
            select(func.count(), func.count(key), func.count(key.distinct())).select_from(key.table)
        ).one()
        return row[0], row[1], row[2]

    source_rows, source_nonnull, source_distinct = counts(source_key)
    target_rows, target_nonnull, target_distinct = counts(target_key)
    reasons: list[str] = []
    compatible = source_type == target_type and source_type in KEY_TYPES
    if not compatible:
        reasons.append("Kiểu khóa phải giống hệt nhau; v1 không tự cast/chuẩn hóa khóa.")
    if not source_rows or not target_rows:
        reasons.append("Hai bảng phải có dữ liệu để xác nhận quan hệ.")
    if source_nonnull != source_rows or target_nonnull != target_rows:
        reasons.append("Khóa nguồn/đích có NULL; INNER JOIN v1 không được âm thầm bỏ dòng.")
    if target_nonnull != target_distinct:
        reasons.append("Khóa đích bị trùng; JOIN sẽ nhân bản fact rows và sai tổng.")
    orphans = None
    if compatible:
        orphans = connection.scalar(
            select(func.count())
            .select_from(fact.outerjoin(dimension, source_key == target_key))
            .where(source_key.is_not(None), target_key.is_(None))
        )
        if orphans:
            reasons.append(
                "Có dòng nguồn không tìm thấy khóa đích; chưa được kích hoạt INNER JOIN."
            )
    return RelationshipPreview(
        **request.model_dump(include=set(RelationshipInput.model_fields)),
        revision=relationship_revision(request, tables),
        valid=not reasons,
        cardinality=("one-to-one" if source_distinct == source_rows else "many-to-one")
        if not reasons
        else None,
        source_rows=source_rows,
        target_rows=target_rows,
        source_nulls=source_rows - source_nonnull,
        target_nulls=target_rows - target_nonnull,
        target_duplicates=target_nonnull - target_distinct,
        orphan_rows=orphans,
        reasons=reasons,
    )
