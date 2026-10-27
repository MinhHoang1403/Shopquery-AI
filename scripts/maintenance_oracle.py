"""Independent Decimal answers calculated from source CSVs, never generator targets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from generate_maintenance_demo import POLICY
from maintenance_documents import SERVICE_GROUPS

KPI_THRESHOLD = Decimal("8000000")  # Fixed policy in 04_KPI_trung_tam.md, checked below.
SOURCE_FILES = (
    "01_trung_tam.csv",
    "02_dich_vu.csv",
    "03_phieu_bao_tri.csv",
    "04_KPI_trung_tam.md",
    "05_quy_trinh_bao_tri.docx",
    "06_so_tay_dich_vu.pdf",
)
MAX_SOURCE_BYTES = 16 * 1024 * 1024  # Bound a local fixture input, never an upload limit.


def read_sources(folder: Path) -> tuple[list[dict[str, str]], ...]:
    result = []
    required = (
        {"ma_trung_tam", "ten_trung_tam"},
        {"ma_dich_vu", "ten_dich_vu", "nhom_dich_vu"},
        {
            "ma_phieu",
            "ma_trung_tam",
            "ma_dich_vu",
            "phi_bao_tri_vnd",
            "ngay_tiep_nhan",
            "ngay_hoan_thanh",
            "trang_thai",
            "ghi_chu",
        },
    )
    for filename, columns in zip(SOURCE_FILES[:3], required, strict=True):
        with (folder / filename).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = reader.fieldnames or []
            if len(headers) != len(set(headers)) or not columns <= set(headers):
                raise ValueError(f"Missing or duplicated CSV headers in {filename}")
            rows = list(reader)
            if len(rows) > 3000 or any(None in row or None in row.values() for row in rows):
                raise ValueError("Malformed CSV or fixture exceeds 3000 rows")
            result.append(rows)
    return tuple(result)


def grouped(rows: list[dict[str, str]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    result = []
    for values, members in sorted(groups.items()):
        fees = [Decimal(row["phi_bao_tri_vnd"]) for row in members]
        result.append(
            {
                **dict(zip(keys, values, strict=True)),
                "so_phieu": len(members),
                "tong_phi": format(sum(fees, Decimal(0)), ".2f"),
                "phi_trung_binh": format(sum(fees, Decimal(0)) / len(fees), "f"),
            }
        )
    return result


def specifications(answers: dict[str, Any]) -> list[dict[str, Any]]:
    # Tokens C,S,F are replaced with registered table names only by the offline harness.
    sql_cases = [
        (
            "S01",
            "Có tất cả bao nhiêu phiếu bảo trì?",
            "SELECT COUNT(*) AS so_phieu FROM {F}",
            [{"so_phieu": answers["counts"]["tickets"]}],
        ),
        (
            "S02",
            "Tổng phí bảo trì thực tế của tất cả phiếu là bao nhiêu?",
            "SELECT SUM(phi_bao_tri_vnd) AS tong_phi FROM {F}",
            [{"tong_phi": answers["total_fee"]}],
        ),
        (
            "S03",
            "Mỗi trung tâm có bao nhiêu phiếu và tổng phí bảo trì thực tế bao nhiêu?",
            (
                "SELECT c.ma_trung_tam,c.ten_trung_tam,COUNT(*) AS "
                "so_phieu,SUM(f.phi_bao_tri_vnd) AS tong_phi FROM {F} f JOIN {C} c ON "
                "f.ma_trung_tam=c.ma_trung_tam GROUP BY c.ma_trung_tam,c.ten_trung_tam ORDER BY "
                "c.ma_trung_tam"
            ),
            answers["centers"],
        ),
        (
            "S04",
            "Năm trung tâm nào có tổng phí bảo trì cao nhất, sắp giảm dần và phân biệt theo mã?",
            (
                "SELECT c.ma_trung_tam,c.ten_trung_tam,COUNT(*) AS "
                "so_phieu,SUM(f.phi_bao_tri_vnd) AS tong_phi FROM {F} f JOIN {C} c ON "
                "f.ma_trung_tam=c.ma_trung_tam GROUP BY c.ma_trung_tam,c.ten_trung_tam ORDER BY "
                "SUM(f.phi_bao_tri_vnd) DESC,c.ma_trung_tam LIMIT 5"
            ),
            answers["top_centers"],
        ),
        (
            "S05",
            "Có bao nhiêu phiếu ở từng trạng thái?",
            (
                "SELECT trang_thai,COUNT(*) AS so_phieu FROM {F} GROUP BY trang_thai ORDER BY "
                "trang_thai"
            ),
            answers["statuses"],
        ),
        (
            "S06",
            "Theo tháng tiếp nhận trong năm 2026, tổng phí và số phiếu là bao nhiêu?",
            (
                "SELECT to_char(date_trunc('month',ngay_tiep_nhan),'YYYY-MM') AS thang,COUNT(*) "
                "AS so_phieu,SUM(phi_bao_tri_vnd) AS tong_phi FROM {F} GROUP BY "
                "to_char(date_trunc('month',ngay_tiep_nhan),'YYYY-MM') ORDER BY thang"
            ),
            answers["months"],
        ),
        (
            "S07",
            "Theo từng mã và tên dịch vụ, phí bảo trì thực tế trung bình và số phiếu là bao nhiêu?",
            (
                "SELECT s.ma_dich_vu,s.ten_dich_vu,COUNT(*) AS so_phieu,AVG(f.phi_bao_tri_vnd) AS"
                " phi_trung_binh FROM {F} f JOIN {S} s ON f.ma_dich_vu=s.ma_dich_vu GROUP BY "
                "s.ma_dich_vu,s.ten_dich_vu ORDER BY s.ma_dich_vu"
            ),
            answers["service_averages"],
        ),
        (
            "S08",
            (
                "Theo từng mã và tên trung tâm, chỉ những phiếu Hoàn thành có tổng phí và số "
                "phiếu là bao nhiêu?"
            ),
            (
                "SELECT c.ma_trung_tam,c.ten_trung_tam,COUNT(*) AS "
                "so_phieu,SUM(f.phi_bao_tri_vnd) AS tong_phi FROM {F} f JOIN {C} c ON "
                "f.ma_trung_tam=c.ma_trung_tam WHERE f.trang_thai='Hoàn thành' GROUP BY "
                "c.ma_trung_tam,c.ten_trung_tam ORDER BY c.ma_trung_tam"
            ),
            answers["completed_centers"],
        ),
        (
            "S09",
            (
                "Dịch vụ nào được dùng nhiều nhất? Cho năm dịch vụ đầu theo số phiếu giảm dần, "
                "kèm tổng phí thực tế và mã để phân biệt."
            ),
            (
                "SELECT s.ma_dich_vu,s.ten_dich_vu,COUNT(*) AS so_phieu,SUM(f.phi_bao_tri_vnd) AS"
                " tong_phi FROM {F} f JOIN {S} s ON f.ma_dich_vu=s.ma_dich_vu GROUP BY "
                "s.ma_dich_vu,s.ten_dich_vu ORDER BY COUNT(*) DESC,s.ma_dich_vu LIMIT 5"
            ),
            answers["popular_services"],
        ),
        (
            "S10",
            (
                "Tại từng trung tâm, mỗi nhóm dịch vụ phát sinh bao nhiêu phiếu và tổng phí thực "
                "tế bao nhiêu? Liên kết cả ba bảng, phân biệt trung tâm theo mã."
            ),
            (
                "SELECT c.ma_trung_tam,c.ten_trung_tam,s.nhom_dich_vu,COUNT(*) AS "
                "so_phieu,SUM(f.phi_bao_tri_vnd) AS tong_phi FROM {F} f JOIN {C} c ON "
                "f.ma_trung_tam=c.ma_trung_tam JOIN {S} s ON f.ma_dich_vu=s.ma_dich_vu GROUP BY "
                "c.ma_trung_tam,c.ten_trung_tam,s.nhom_dich_vu ORDER BY "
                "c.ma_trung_tam,s.nhom_dich_vu"
            ),
            answers["center_service_groups"],
        ),
        (
            "S11",
            (
                "Từ ngày 01/03/2026 đến trước ngày 01/06/2026 theo ngày tiếp nhận, có bao nhiêu "
                "phiếu và tổng phí là bao nhiêu?"
            ),
            (
                "SELECT COUNT(*) AS so_phieu,SUM(phi_bao_tri_vnd) AS tong_phi FROM {F} WHERE "
                "ngay_tiep_nhan >= '2026-03-01' AND ngay_tiep_nhan < '2026-06-01'"
            ),
            answers["date_range"],
        ),
        (
            "S12",
            (
                "Có bao nhiêu dòng phiếu và bao nhiêu phiếu có ghi chú? Đếm ghi chú khác NULL, "
                "không thay COUNT(*) bằng COUNT(ghi_chu)."
            ),
            "SELECT COUNT(*) AS so_phieu,COUNT(ghi_chu) AS co_ghi_chu FROM {F}",
            answers["nullable_counts"],
        ),
        (
            "S13",
            "Những phiếu có phí đúng bằng 0 gồm bao nhiêu phiếu và tổng phí bao nhiêu?",
            (
                "SELECT COUNT(*) AS so_phieu,SUM(phi_bao_tri_vnd) AS tong_phi FROM {F} WHERE "
                "phi_bao_tri_vnd=0"
            ),
            answers["zero_fees"],
        ),
        (
            "S14",
            (
                "Ba trung tâm nào có tổng phí thấp nhất? Cho mã, tên, tổng phí và số phiếu, sắp "
                "tăng dần theo tổng phí."
            ),
            (
                "SELECT c.ma_trung_tam,c.ten_trung_tam,COUNT(*) AS "
                "so_phieu,SUM(f.phi_bao_tri_vnd) AS tong_phi FROM {F} f JOIN {C} c ON "
                "f.ma_trung_tam=c.ma_trung_tam GROUP BY c.ma_trung_tam,c.ten_trung_tam ORDER BY "
                "SUM(f.phi_bao_tri_vnd),c.ma_trung_tam LIMIT 3"
            ),
            answers["bottom_centers"],
        ),
    ]
    questions = [
        {
            "id": id_,
            "group": "SQL",
            "question": question,
            "expected_route": "SQL",
            "oracle_sql": sql,
            "expected": expected,
            "evidence": "registered PostgreSQL tables",
            "tolerance": (
                "exact integer/cents; AVG exact rational with PostgreSQL NUMERIC display rounding"
            ),
            "offline": "PENDING",
            "live": "NOT_RUN",
        }
        for id_, question, sql, expected in sql_cases
    ]
    rag = [
        (
            "R01",
            "Quy trình tiếp nhận phiếu bảo trì gồm những việc gì?",
            "05_quy_trinh_bao_tri.docx",
            "Ghi nhận yêu cầu",
            ["ma_phieu", "ma_trung_tam", "ma_dich_vu", "ngay_tiep_nhan"],
        ),
        (
            "R02",
            "Khi nào được chuyển phiếu sang Hoàn thành?",
            "05_quy_trinh_bao_tri.docx",
            "Điều kiện hoàn thành",
            ["kiểm tra an toàn", "kiểm soát chất lượng", "ngay_hoan_thanh"],
        ),
        (
            "R03",
            "Phiếu thiếu thông tin phải xử lý thế nào?",
            "05_quy_trinh_bao_tri.docx",
            "Phiếu thiếu thông tin",
            ["Mới tiếp nhận", "bổ sung", "Không tạo mã giả"],
        ),
        (
            "R04",
            "Nếu có khiếu nại về phí, bộ phận nào kiểm tra và cần đối chiếu gì?",
            "05_quy_trinh_bao_tri.docx",
            "Khiếu nại và kiểm tra kết quả",
            ["kiểm soát chất lượng", "Đối soát", "phi_tham_khao_vnd"],
        ),
        (
            "R05",
            "Sổ tay phân chia dịch vụ thành những nhóm nào?",
            "06_so_tay_dich_vu.pdf",
            "Trang 1",
            SERVICE_GROUPS,
        ),
        (
            "R06",
            "Dịch vụ mức Chuyên sâu cần xử lý và phân công thế nào?",
            "06_so_tay_dich_vu.pdf",
            "Trang 2",
            ["kỹ thuật chuyên trách", "Kiểm soát chất lượng", "Tạm ngưng"],
        ),
        (
            "R07",
            (
                "Phí tham khảo và phí thực tế khác nhau thế nào? Dẫn cả phần nói về phí danh mục "
                "và phí của phiếu."
            ),
            "06_so_tay_dich_vu.pdf",
            "Trang 3",
            ["phi_tham_khao_vnd", "phi_bao_tri_vnd", "125000.50", "123456.78"],
        ),
        (
            "R08",
            "Tài liệu KPI quy định điều kiện một trung tâm đạt là gì?",
            "04_KPI_trung_tam.md",
            "KPI trung tâm",
            ["8000000", "phi_bao_tri_vnd", "ma_trung_tam"],
        ),
        (
            "R09",
            "Chính sách KPI có loại phiếu Hủy ra khỏi phép tính tổng không?",
            "04_KPI_trung_tam.md",
            "KPI trung tâm",
            ["Tính tất cả trạng thái", "SUM", "số 0"],
        ),
        (
            "R10",
            "Tài liệu quy định mức bồi thường bằng tiền cho khiếu nại bảo trì là bao nhiêu?",
            "06_so_tay_dich_vu.pdf",
            "Trang 4",
            ["không có", "thiếu căn cứ"],
        ),
    ]
    questions += [
        {
            "id": id_,
            "group": "RAG",
            "question": question,
            "expected_route": "RAG",
            "expected": {"required_concepts": concepts, "safe_refusal": id_ == "R10"},
            "evidence": {"source_file": file, "section": section},
            "tolerance": "source-grounded concepts and real scoped chunk IDs",
            "offline": "PENDING",
            "live": "NOT_RUN",
        }
        for id_, question, file, section, concepts in rag
    ]
    hybrid = [
        ("H01", "Theo tài liệu KPI, trung tâm nào đạt và trung tâm nào chưa đạt?", "all", None),
        ("H02", "Theo chính sách KPI, những trung tâm nào chưa đạt?", "not_qualified", None),
        ("H03", "Trung tâm nào đạt KPI theo tài liệu?", "qualified", None),
        (
            "H04",
            "Vậy những trung tâm chưa đạt KPI là trung tâm nào?",
            "not_qualified",
            "H01 verified_classification in the same conversation",
        ),
        (
            "H05",
            (
                "Kết hợp tổng phí bảo trì thực tế ở mọi trạng thái với chính sách KPI, cho biết "
                "kết luận từng trung tâm."
            ),
            "all",
            None,
        ),
        (
            "H06",
            "Chỉ riêng tháng 3, theo chính sách KPI mọi trạng thái thì trung tâm nào đạt?",
            "EXPECTED_SAFE_REFUSAL",
            None,
        ),
    ]
    questions += [
        {
            "id": id_,
            "group": "Hybrid" if id_ != "H04" else "Follow-up",
            "question": question,
            "expected_route": "HYBRID",
            "premise": premise,
            "expected": {"selection": selection, "classification": answers["kpi"]},
            "evidence": {"source_file": "04_KPI_trung_tam.md", "sql_rows_before_presentation": 30},
            "tolerance": (
                "exact cents, source-bound rule and backend verified_classification; refusal for "
                "unsupported scope"
            ),
            "offline": "PENDING",
            "live": "NOT_RUN",
        }
        for id_, question, selection, premise in hybrid
    ]
    for id_, question, expected in [
        ("A01", "Tổng phí bảo trì thực tế là bao nhiêu?", "SQL"),
        ("A02", "Theo quy trình, ai chịu trách nhiệm xử lý phiếu thiếu thông tin?", "RAG"),
        ("A03", "Đối chiếu mọi phiếu với chính sách KPI, phân loại từng trung tâm.", "HYBRID"),
        ("A04", "Ngày mai tỷ giá đô la ở Mỹ là bao nhiêu?", "UNSUPPORTED"),
    ]:
        questions.append(
            {
                "id": id_,
                "group": "Auto Routing",
                "question": question,
                "expected_route": expected,
                "expected": "bounded source capabilities; route_hint omitted",
                "evidence": "actual router metadata",
                "tolerance": "exact route and provider attribution",
                "offline": "PENDING",
                "live": "NOT_RUN",
            }
        )
    negatives = [
        "foreign_key_null",
        "orphan_key",
        "duplicate_dimension_key",
        "many_to_many",
        "ambiguous_path",
        "fanout",
        "count_alias",
        "metric_from_dimension",
        "kpi_where",
        "kpi_having",
        "kpi_limit",
        "decimal_boundary",
        "null_vs_zero",
        "unrelated_document",
        "fabricated_citation",
        "missing_policy",
        "conflicting_policy",
        "document_prompt_injection",
        "cross_owner_preview",
        "cross_owner_retrieval",
        "cross_workspace_context",
        "unverified_followup",
    ]
    questions += [
        {
            "id": f"N{i:02d}",
            "group": "Security/Negative",
            "question": name,
            "expected_route": "not applicable to offline security boundary",
            "expected": "EXPECTED_SAFE_REFUSAL or exact documented semantics",
            "evidence": "isolated fixtures/mocks only; never corrupt the demo workspace",
            "tolerance": "guard remains enforced",
            "offline": "PENDING",
            "live": "NOT_RUN",
        }
        for i, name in enumerate(negatives, 1)
    ]
    return questions


def build_oracle(folder: Path) -> dict[str, Any]:
    if not folder.is_absolute() or not folder.is_dir():
        raise ValueError("Input must be an existing explicit absolute directory")
    for filename in SOURCE_FILES:
        path = folder / filename
        if (
            path.is_symlink()
            or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_SOURCE_BYTES
        ):
            raise ValueError(f"Missing, linked or oversized fixture source: {filename}")
    if (folder / "04_KPI_trung_tam.md").read_text(encoding="utf-8") != POLICY:
        raise ValueError("Fixture policy differs from the supported maintenance policy")
    with localcontext() as context:
        context.prec = 50
        centers, services, facts = read_sources(folder)
        for rows, key in ((centers, "ma_trung_tam"), (services, "ma_dich_vu"), (facts, "ma_phieu")):
            if any(not row[key] or row[key] != row[key].strip() for row in rows):
                raise ValueError(
                    "Fixture identifiers must be nonempty and have no surrounding space"
                )
        center_map = {r["ma_trung_tam"]: r for r in centers}
        service_map = {r["ma_dich_vu"]: r for r in services}
        if len(center_map) != len(centers) or len(centers) != 30:
            raise ValueError("Expected 30 centers with unique keys")
        if len(service_map) != len(services) or len(services) != 60:
            raise ValueError("Expected 60 services with unique keys")
        if len({r["ma_phieu"] for r in facts}) != len(facts) or len(facts) != 3000:
            raise ValueError("Expected 3000 tickets with unique keys")
        for row in facts:
            if row["ma_trung_tam"] not in center_map or row["ma_dich_vu"] not in service_map:
                raise ValueError("Ticket references an unknown dimension key")
            fee = Decimal(row["phi_bao_tri_vnd"])
            if not fee.is_finite() or not 0 <= fee <= Decimal("9999999999999999.99"):
                raise ValueError("Fee must be finite, nonnegative and within NUMERIC bounds")
            if fee.as_tuple().exponent < -2:
                raise ValueError("Fee has more than two decimal places")
            received = date.fromisoformat(row["ngay_tiep_nhan"])
            completed = (
                date.fromisoformat(row["ngay_hoan_thanh"]) if row["ngay_hoan_thanh"] else None
            )
            if not date(2026, 1, 1) <= received <= date(2026, 10, 26):
                raise ValueError("Receipt date is outside the documented fixture range")
            if completed and not received <= completed <= date(2026, 10, 26):
                raise ValueError("Completion date is inconsistent")
            if row["trang_thai"] not in {"Hoàn thành", "Đang xử lý", "Mới tiếp nhận", "Hủy"}:
                raise ValueError("Unknown ticket status")
            if bool(completed) != (row["trang_thai"] == "Hoàn thành"):
                raise ValueError("Completion date and status disagree")
        for row in facts:
            row.update(
                {
                    "ten_trung_tam": center_map[row["ma_trung_tam"]]["ten_trung_tam"],
                    "ten_dich_vu": service_map[row["ma_dich_vu"]]["ten_dich_vu"],
                    "nhom_dich_vu": service_map[row["ma_dich_vu"]]["nhom_dich_vu"],
                    "thang": row["ngay_tiep_nhan"][:7],
                }
            )

        def select(rows, keys, avg=False):
            fields = (*keys, "so_phieu", "phi_trung_binh" if avg else "tong_phi")
            return [{key: row[key] for key in fields} for row in grouped(rows, keys)]

        center_totals = select(facts, ("ma_trung_tam", "ten_trung_tam"))
        kpi = [
            {
                **r,
                "status": "qualified"
                if Decimal(r["tong_phi"]) >= KPI_THRESHOLD
                else "not_qualified",
            }
            for r in center_totals
        ]
        service_averages = select(facts, ("ma_dich_vu", "ten_dich_vu"), avg=True)
        # Store exact numerators/denominators; repeating AVG cannot be an exact finite decimal.
        service_totals = select(facts, ("ma_dich_vu", "ten_dich_vu"))
        result = {
            "fixture_id": "maintenance-demo-20261026",
            "workspace_name": "Kiểm thử bảo trì thiết bị",
            "as_of": "2026-10-26",
            "counts": {"centers": len(centers), "services": len(services), "tickets": len(facts)},
            "total_fee": format(
                sum((Decimal(row["phi_bao_tri_vnd"]) for row in facts), Decimal(0)), ".2f"
            ),
            "average_fee_rational": {
                "numerator": format(sum(Decimal(r["phi_bao_tri_vnd"]) for r in facts), ".2f"),
                "denominator": len(facts),
            },
            "statuses": [
                {"trang_thai": key, "so_phieu": value}
                for key, value in sorted(Counter(r["trang_thai"] for r in facts).items())
            ],
            "months": select(facts, ("thang",)),
            "centers": center_totals,
            "service_totals": service_totals,
            "service_averages": service_averages,
            "top_centers": sorted(
                center_totals, key=lambda r: (-Decimal(r["tong_phi"]), r["ma_trung_tam"])
            )[:5],
            "bottom_centers": sorted(
                center_totals, key=lambda r: (Decimal(r["tong_phi"]), r["ma_trung_tam"])
            )[:3],
            "popular_services": sorted(
                service_totals, key=lambda r: (-r["so_phieu"], r["ma_dich_vu"])
            )[:5],
            "completed_centers": select(
                [r for r in facts if r["trang_thai"] == "Hoàn thành"],
                ("ma_trung_tam", "ten_trung_tam"),
            ),
            "center_service_groups": select(
                facts, ("ma_trung_tam", "ten_trung_tam", "nhom_dich_vu")
            ),
            "date_range": select(
                [r for r in facts if "2026-03-01" <= r["ngay_tiep_nhan"] < "2026-06-01"], ()
            ),
            "nullable_counts": [
                {
                    "so_phieu": len(facts),
                    "co_ghi_chu": sum(bool(r["ghi_chu"].strip()) for r in facts),
                }
            ],
            "zero_fees": select([r for r in facts if Decimal(r["phi_bao_tri_vnd"]) == 0], ()),
            "kpi": kpi,
            "threshold_equal": [
                r["ma_trung_tam"] for r in kpi if Decimal(r["tong_phi"]) == KPI_THRESHOLD
            ],
            "avg_semantics": (
                "Exact rational total/count; display must match PostgreSQL NUMERIC rounding, no "
                "float tolerance."
            ),
            "source_hashes": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (folder / name for name in SOURCE_FILES)
            },
        }
        result["questions"] = specifications(result)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, required=True, help="Absolute synthetic bundle directory"
    )
    parser.add_argument("--output", type=Path, required=True, help="Absolute new JSON file")
    args = parser.parse_args()
    if not args.output.is_absolute() or not args.output.parent.is_dir():
        parser.error("Output must be an absolute JSON file with an existing parent")
    if args.output.exists() or args.output.is_symlink():
        parser.error("Output exists; nothing was overwritten")
    try:
        result = build_oracle(args.input)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
    except (ValueError, KeyError, ArithmeticError, OSError) as exc:
        parser.exit(1, f"Cannot calculate fixture oracle: {exc}\n")
    print(
        json.dumps(
            {
                "counts": result["counts"],
                "total_fee": result["total_fee"],
                "questions": len(result["questions"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
