"""Present verified rows without inventing units, formulas or business conclusions."""

import json
from typing import Any

from app.text_to_sql.count_contract import CountMetric


def compose_sql_answer(rows: list[dict[str, Any]], counts: tuple[CountMetric, ...]) -> str:
    if not rows:
        return "Truy vấn không trả về dòng dữ liệu nào."

    def cell(value: Any) -> str:
        text = "NULL" if value is None else str(value)
        return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    columns = list(dict.fromkeys(key for row in rows for key in row))
    table = [
        "| " + " | ".join(cell(key) for key in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
        *["| " + " | ".join(cell(row.get(key)) for key in columns) + " |" for row in rows],
    ]
    notes = ["Kết quả truy vấn đã xác minh. NULL là giá trị thiếu, khác số 0."]
    if counts and not any(metric.kind == "row_count" for metric in counts):
        notes.append("Truy vấn chỉ đếm giá trị khác NULL; chưa có bằng chứng số dòng nguồn.")
    for metric in counts:
        kind = (
            "số dòng nguồn khớp truy vấn" if metric.kind == "row_count" else "số giá trị khác NULL"
        )
        notes.append(f"{json.dumps(metric.output_alias, ensure_ascii=False)}: {kind}.")
    return "\n\n".join([*notes, "\n".join(table)])
