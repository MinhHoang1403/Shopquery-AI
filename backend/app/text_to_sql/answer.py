"""Present verified rows without inventing units, formulas or business conclusions."""

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.text_to_sql.count_contract import CountMetric
from app.text_to_sql.number_format import format_number


class ResultColumn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(max_length=63)
    label: str = Field(max_length=256)
    numeric: bool = False
    data_type: (
        Literal["TEXT", "BIGINT", "NUMERIC", "BOOLEAN", "DATE", "TIMESTAMP", "TIMESTAMPTZ"] | None
    ) = None
    provenance: Literal["column", "aggregate", "expression", "literal", "unknown"] = "unknown"
    aggregate: Literal["sum", "avg", "min", "max", "row_count", "value_count"] | None = None
    source_label: str | None = Field(default=None, max_length=256)


def column_label(value: str) -> str:
    text = " ".join(value.replace("_", " ").split())[:256]
    return text[:1].upper() + text[1:]


def _markdown(value: Any) -> str:
    return re.sub(r"([\\`*_{}\[\]<>()#!|])", r"\\\1", str(value)).replace("\n", " ")


def compose_sql_answer(
    rows: list[dict[str, Any]],
    counts: tuple[CountMetric, ...],
    columns: tuple[ResultColumn, ...] = (),
    *,
    grouped: bool = False,
    ranking: tuple[str, str] | None = None,
) -> str:
    if not rows:
        return "Không tìm thấy kết quả thỏa điều kiện trong bộ dữ liệu hiện tại."
    metadata = {column.key: column for column in columns}
    if not columns and not counts:
        if len(rows) == 1 and len(rows[0]) == 1 and next(iter(rows[0].values())) is None:
            return "Kết quả chưa có giá trị được ghi nhận."
        return (
            f"Tìm thấy **{format_number(len(rows))} kết quả** thỏa điều kiện. "
            "Mở bảng dữ liệu để xem chi tiết."
        )
    if len(rows) == 1 and any(c.provenance == "aggregate" for c in columns):
        row = rows[0]
        if ranking is not None and ranking[0] in row:
            column = metadata.get(ranking[0])
            attributes = [
                _markdown(row[c.key])
                for c in columns
                if c.provenance == "column" and row.get(c.key) is not None
            ]
            if column is not None and column.aggregate and attributes:
                order = "cao nhất" if ranking[1] == "desc" else "thấp nhất"
                value = (
                    "chưa có dữ liệu" if row[column.key] is None else format_number(row[column.key])
                )
                return (
                    f"Kết quả có **{_markdown(column.label)} {order}** trong phạm vi truy vấn "
                    f"là **{' / '.join(attributes)}**, với giá trị **{value}**."
                )
        parts = []
        for key, value in row.items():
            column = metadata.get(key)
            if column is None:
                continue
            if value is None:
                parts.append(f"**{_markdown(column.label)}** chưa có giá trị được ghi nhận")
            elif column.aggregate in {"row_count", "value_count"}:
                count = next((c for c in counts if c.output_alias == key), None)
                noun = "bản ghi" if count and count.kind == "row_count" else "giá trị có dữ liệu"
                parts.append(f"có **{format_number(value)} {noun}**")
            else:
                display = format_number(value) if column.numeric else _markdown(value)
                parts.append(f"**{_markdown(column.label)}** là **{display}**")
        return "Trong phạm vi dữ liệu truy vấn, " + "; ".join(parts) + "."
    if len(rows) == 1:
        row = rows[0]
        if len(row) == 1:
            alias, value = next(iter(row.items()))
            if value is None:
                return "Kết quả chưa có giá trị được ghi nhận."
            metric = next((item for item in counts if item.output_alias == alias), None)
            if metric is not None:
                column = next((item for item in columns if item.key == alias), None)
                if column is not None:
                    return f"{_markdown(column.label)}: **{format_number(value)}**."
                label = "bản ghi" if metric.kind == "row_count" else "giá trị có dữ liệu"
                return f"Ghi nhận **{format_number(value)} {label}**."
        parts = []
        for alias, value in row.items():
            column = metadata.get(alias)
            numeric = bool(column and column.numeric) or any(
                c.output_alias == alias for c in counts
            )
            display = (
                "Chưa có dữ liệu"
                if value is None
                else format_number(value)
                if numeric
                else _markdown(value)
            )
            label = column.label if column else column_label(alias)
            parts.append(f"{_markdown(label)}: **{display}**")
        return "; ".join(parts) + "."
    if grouped:
        return (
            f"Đã tổng hợp **{format_number(len(rows))} nhóm kết quả** trong phạm vi truy vấn. "
            "Mở bảng dữ liệu để xem số liệu chi tiết."
        )
    return (
        f"Tìm thấy **{format_number(len(rows))} kết quả** thỏa điều kiện. "
        "Mở bảng dữ liệu để xem chi tiết."
    )
