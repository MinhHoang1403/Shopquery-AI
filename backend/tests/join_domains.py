"""Deterministic, domain-specific data; business expectations do not come from model SQL."""

import csv
import io
import random
from dataclasses import dataclass

from openpyxl import Workbook


@dataclass(frozen=True)
class Domain:
    name: str
    labels: tuple[str, str, str]
    keys: tuple[str, str]
    names: tuple[str, str]
    measure: str
    question: str
    star: bool = False


DOMAINS = (
    Domain(
        "tuition",
        ("courses", "students", "payments"),
        ("course_id", "student_id"),
        ("course_title", "student_name"),
        "amount_paid",
        "Tổng học phí và số dòng thanh toán theo khóa học",
    ),
    Domain(
        "logistics",
        ("01_kho_dieu_phoi", "02_tai_xe", "03_don_giao_hang"),
        ("kho_id", "tai_xe_id"),
        ("ten_kho", "ten_tai_xe"),
        "phi_giao_vnd",
        "Tên kho, số đơn giao hàng và tổng phí, tất cả trạng thái",
    ),
    Domain(
        "sales",
        ("categories", "products", "order_lines"),
        ("category_id", "product_id"),
        ("category_name", "product_name"),
        "line_amount",
        "Tổng giá trị và số dòng đơn theo danh mục",
    ),
    Domain(
        "staffing",
        ("departments", "employees", "work_logs"),
        ("department_id", "employee_id"),
        ("department_name", "employee_name"),
        "hours",
        "Tổng và trung bình giờ làm theo phòng ban",
    ),
    Domain(
        "energy",
        ("locations", "devices", "readings"),
        ("location_id", "device_id"),
        ("location_name", "device_name"),
        "kwh",
        "Tổng điện năng theo địa điểm",
    ),
    Domain(
        "maintenance_holdout",
        ("technicians", "assets", "service_events"),
        ("technician_id", "asset_id"),
        ("technician_name", "asset_name"),
        "downtime_hours",
        "Tổng thời gian dừng máy theo kỹ thuật viên",
        True,
    ),
)


def dataset_rows(domain: Domain, seed: int):
    outer = [(f"K{i}", "Trùng tên" if i < 3 else f"Địa điểm {i}") for i in range(1, 5)]
    inner = [
        (f"D{i}", "Cùng tên" if i < 3 else f"Đối tượng {i}", f"K{(i + 1) // 2}")
        for i in range(1, 6)
    ]
    facts = [
        ("D1", "20.00"),
        ("D1", "0.00"),
        ("D2", "10.00"),
        ("D3", "12.50"),
        ("D3", "0.00"),
        ("D5", None),
        ("D5", None),
    ]
    if domain.name == "logistics":
        outer = [(f"K{i}", "Kho trùng tên" if i < 3 else f"Kho {i}") for i in range(1, 6)]
        inner = [(f"D{i}", f"Tài xế {i}", f"K{(i - 1) // 3 + 1}") for i in range(1, 16)]
        facts = []
        for warehouse, fee in enumerate((45000, 50000, 52500, 47500, 52250), 1):
            for n in range(10):
                amount = f"{fee}.00"
                if n == 0:
                    amount = "0.00" if warehouse == 1 else None
                if n == 1:
                    amount = f"{fee * 2}.00"
                facts.append((f"D{(warehouse - 1) * 3 + n % 3 + 1}", amount))
    lookup = {row[0]: row[2] for row in inner}
    named_outer, named_inner = dict(outer), {row[0]: row[1] for row in inner}
    event_rows, oracle_rows = [], []
    for index, (identity, amount) in enumerate(facts):
        group = lookup[identity]
        timestamp = "2025-08-31T17:00:00+00:00" if index % 2 == 0 else "2025-09-30T17:00:00+00:00"
        row = [f"E{index + 1:03}", identity, amount, timestamp]
        if domain.star:
            row.append(group)
        event_rows.append(row)
        oracle_rows.append(
            (identity, named_inner[identity], group, named_outer[group], amount, timestamp)
        )
    if seed:
        rng = random.Random(seed)
        rng.shuffle(outer)
        rng.shuffle(inner)
        rng.shuffle(event_rows)
    return outer, inner, event_rows, oracle_rows


def uploads(domain: Domain, seed: int):
    outer, inner, facts, oracle = dataset_rows(domain, seed)
    outer_key, inner_key = domain.keys
    specifications = [
        ([outer_key, domain.names[0]], outer),
        (
            [inner_key, domain.names[1]] + ([] if domain.star else [outer_key]),
            [row[:2] if domain.star else row for row in inner],
        ),
        (
            ["event_id", inner_key, domain.measure, "recorded_at"]
            + ([outer_key] if domain.star else []),
            facts,
        ),
    ]
    files = []
    for label, (headers, rows) in zip(domain.labels, specifications, strict=True):
        if seed == 19:
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = label
            sheet.append(headers)
            for row in rows:
                sheet.append(row)
            buffer = io.BytesIO()
            workbook.save(buffer)
            workbook.close()
            files.append((label + ".xlsx", buffer.getvalue()))
        else:
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer)
            writer.writerow(headers)
            writer.writerows(rows)
            files.append((label + ".csv", buffer.getvalue().encode("utf-8")))
    return (list(reversed(files)) if seed == 7 else files), oracle
