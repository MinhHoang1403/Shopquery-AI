"""Synthetic logistics replay of the saved Gate D fixture, not provider-generated SQL."""

import csv
from decimal import Decimal
from io import StringIO

QUESTIONS = {
    "1": "Liệt kê don_id, phi_giao_vnd và trang_thai của toàn bộ đơn giao hàng, tính tất "
    "cả trạng thái; sắp xếp don_id tăng dần. Giữ nguyên giá trị 0 và NULL, không "
    "thay NULL bằng 0.",
    "2": "Theo từng tài xế, cho biết mã tai_xe_id, tên ten_tai_xe, tổng phi_giao_vnd và "
    "số dòng đơn giao hàng, tính tất cả trạng thái. Phân biệt tài xế theo mã ID; "
    "đếm dòng đơn, không đếm tài xế.",
    "3": "Theo từng kho, cho biết mã kho_id, tên ten_kho, tổng phi_giao_vnd và số dòng "
    "đơn giao hàng, tính tất cả trạng thái. Dùng liên kết đơn giao hàng → tài xế "
    "→ kho; phân biệt kho theo mã ID.",
    "H": "Theo tài liệu live_gate_d_kpi.md, những kho nào đạt KPI tổng phí? Với từng "
    "kho, cho biết mã kho_id, tên ten_kho, tổng phi_giao_vnd của tất cả trạng thái, "
    "số dòng đơn và kết luận đạt/chưa đạt. Kết hợp dữ liệu đơn giao hàng → tài xế "
    "→ kho với điều kiện trong tài liệu, phân biệt kho theo mã ID.",
}
FEES = [
    "56500",
    "85500",
    "50500",
    "71000",
    "42000",
    "null",
    "35500",
    "57000",
    "86000",
    "48500",
    "0",
    "42500",
    "64500",
    "36000",
    "55000",
    "86500",
    "49000",
    "72000",
    "43000",
    "null",
    "36500",
    "55500",
    "87000",
    "49500",
    "70000",
    "43500",
    "0",
    "37000",
    "56000",
    "85000",
    "50000",
    "70500",
    "null",
    "63500",
    "35000",
    "56500",
    "85500",
    "50500",
    "71000",
    "0",
    "64000",
    "35500",
    "57000",
    "86000",
    "48500",
    "null",
    "42500",
    "64500",
    "36000",
    "55000",
]
DRIVERS = (
    "Nguyễn Hoàng Minh",
    "Trần Quốc Huy",
    "Lê Anh Tuấn",
    "Phạm Ngọc Lan",
    "Võ Thành Đạt",
    "Đặng Minh Khang",
    "Bùi Thanh Hà",
    "Đỗ Tuấn Kiệt",
    "Hoàng Đức Anh",
    "Ngô Thùy Trang",
    "Dương Nhật Nam",
    "Phan Trọng Nghĩa",
    "Cao Nhật Linh",
    "Mai Quốc Bảo",
    "Lý Mỹ Duyên",
)
POLICY = (
    "# Synthetic KPI\n\nKho đạt KPI nếu tổng phi_giao_vnd của tất cả trạng thái "
    ">= 500000.00. Xác định kho qua tài xế và kho_id; phân biệt kho theo ID. "
    "SUM bỏ qua NULL; giữ số 0 hợp lệ."
)


def csv_bytes(headers: list[str], rows: list[list]) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def uploads() -> tuple[list[tuple[str, bytes]], list[dict]]:
    cities = ("Hà Nội", "Hải Phòng", "Đà Nẵng", "TP. Hồ Chí Minh", "Cần Thơ")
    warehouses = ("Kho Hà Nội", "Kho Hải Phòng", "Kho Đà Nẵng", "Kho TP.HCM", "Kho Cần Thơ")
    outer = [
        [
            f"KHO{i + 1:02}",
            name,
            cities[i],
            ("Miền Bắc", "Miền Bắc", "Miền Trung", "Miền Nam", "Miền Nam")[i],
        ]
        for i, name in enumerate(warehouses)
    ]
    drivers = [
        [
            f"TX{i + 1:03}",
            name,
            f"KHO{i % 5 + 1:02}",
            ("Xe máy", "Xe tải nhẹ", "Xe van")[i % 3],
            (i * 2) % 9 + 1,
        ]
        for i, name in enumerate(DRIVERS)
    ]
    receivers = ("Huế", "TP. Hồ Chí Minh", "Hải Phòng", "Nha Trang", "Cần Thơ", "Đà Nẵng", "Hà Nội")
    facts, business = [], []
    for i, fee in enumerate(FEES, 1):
        driver = (7 * i + 3) % 15 + 1
        warehouse = (driver - 1) % 5 + 1
        status = "Đã giao"
        if i in {5, 13, 22, 36, 49}:
            status = "Đã hủy"
        elif i in {7, 17, 31, 47}:
            status = "Đang giao"
        elif i in {10, 29, 43}:
            status = "Hoàn hàng"
        amount = None if fee == "null" else format(Decimal(fee).quantize(Decimal("0.00")), "f")
        facts.append(
            [
                f"DG{i:04}",
                f"TX{driver:03}",
                f"2026-10-{(11 * i) % 26 + 1:02}",
                status,
                (i * 2) % 5 + 1,
                amount,
                Decimal("5") + (Decimal("8.5") * i) % 65,
                receivers[(i - 1) % 7],
            ]
        )
        business.append(
            {
                "don_id": f"DG{i:04}",
                "tai_xe_id": f"TX{driver:03}",
                "ten_tai_xe": DRIVERS[driver - 1],
                "kho_id": f"KHO{warehouse:02}",
                "ten_kho": warehouses[warehouse - 1],
                "phi_giao_vnd": amount,
                "trang_thai": status,
            }
        )
    return [
        ("01_kho_dieu_phoi.csv", csv_bytes(["kho_id", "ten_kho", "thanh_pho", "loai_kho"], outer)),
        (
            "02_tai_xe.csv",
            csv_bytes(["tai_xe_id", "ten_tai_xe", "kho_id", "loai_xe", "tham_nien_nam"], drivers),
        ),
        (
            "03_don_giao_hang.csv",
            csv_bytes(
                [
                    "don_id",
                    "tai_xe_id",
                    "ngay_giao",
                    "trang_thai",
                    "so_kien",
                    "phi_giao_vnd",
                    "quang_duong_km",
                    "thanh_pho_nhan",
                ],
                facts,
            ),
        ),
    ], business
