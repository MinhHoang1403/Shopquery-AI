"""Present verified rows without inventing units, formulas or business conclusions."""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.text_to_sql.count_contract import CountMetric
from app.text_to_sql.number_format import format_number


class ResultColumn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(max_length=63)
    label: str = Field(max_length=256)
    numeric: bool = False


def column_label(value: str) -> str:
    text = " ".join(value.replace("_", " ").split())[:256]
    return text[:1].upper() + text[1:]


def _markdown(value: Any) -> str:
    return re.sub(r"([\\`*_{}\[\]<>()#!|])", r"\\\1", str(value)).replace("\n", " ")


def compose_sql_answer(
    rows: list[dict[str, Any]],
    counts: tuple[CountMetric, ...],
    columns: tuple[ResultColumn, ...] = (),
) -> str:
    if not rows:
        return "Không tìm thấy kết quả thỏa điều kiện trong bộ dữ liệu hiện tại."
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
        metadata = {column.key: column for column in columns}
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
    return f"Tìm thấy **{format_number(len(rows))} kết quả** thỏa điều kiện:"
