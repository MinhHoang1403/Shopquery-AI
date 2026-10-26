"""Present verified rows without inventing units, formulas or business conclusions."""

from typing import Any

from app.text_to_sql.count_contract import CountMetric
from app.text_to_sql.number_format import format_number


def compose_sql_answer(rows: list[dict[str, Any]], counts: tuple[CountMetric, ...]) -> str:
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
                label = "bản ghi" if metric.kind == "row_count" else "giá trị có dữ liệu"
                return f"Truy vấn ghi nhận {format_number(value)} {label}."
            if (
                isinstance(value, (int, float))
                or isinstance(value, str)
                and value.replace(".", "", 1).lstrip("-").isdigit()
            ):
                return f"Kết quả là {format_number(value)}."
        return "Tôi đã tìm thấy một kết quả phù hợp. Chi tiết nằm trong bảng dữ liệu."
    return (
        f"Tôi đã tìm thấy {format_number(len(rows))} kết quả phù hợp. "
        "Bạn có thể xem chi tiết trong bảng dữ liệu."
    )
