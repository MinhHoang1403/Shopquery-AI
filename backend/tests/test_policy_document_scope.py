"""Complete scoped regulations need source, whole-document and full-row proofs."""

import hashlib
from dataclasses import replace
from unittest.mock import Mock

import pytest

from app.core.errors import ModelResponseError
from app.rag.repository import DocumentScope, RetrievedChunk
from app.routing.hybrid import HybridPipeline
from app.routing.hybrid_policy import complete_policy_evidence, policy_content
from app.routing.natural_policy import parse_prose
from tests.test_evidence_coverage import pipeline
from tests.test_hybrid_policy_binding import relationship_fixture


def regulation(entity="cơ sở", metric="value_amount", identity="site_key", threshold="75,50"):
    return (
        f"QUY ĐỊNH KPI TỔNG PHÍ THEO {entity.upper()} SOP-KPI-2032-04 | "
        f"Ban hành cho bộ dữ liệu tổng hợp | "
        "Hiệu lực kiểm thử: 01–24/04/2032 1. Phạm vi và số liệu cần dùng "
        f"Chính sách này áp dụng cho từng {entity} trong kỳ từ ngày "
        f"01/04/2032 đến hết ngày 24/04/2032. "
        "Bộ dữ liệu kiểm thử chỉ gồm các phiếu đã xác nhận trong kỳ này. "
        "Đơn vị tiền là đồng Việt Nam (VND). "
        "2. Định nghĩa chỉ tiêu KPI Chỉ tiêu duy nhất dùng để đánh giá là tổng phí "
        f"của tất cả phiếu xác nhận thuộc một {entity} trong kỳ. "
        f"Tổng phí phải được lấy từ trường {metric} của bảng sự kiện, gom nhóm theo {identity}. "
        f"Tên {entity} lấy từ bảng danh mục {entity} bằng liên kết khóa {entity} đã xác minh. "
        "3. Ngưỡng đánh giá và trường hợp bằng ngưỡng "
        f"Một {entity} được xếp loại ĐẠT KPI khi tổng phí lớn hơn hoặc bằng {threshold} VND. "
        f"{entity.capitalize()} có tổng phí nhỏ hơn {threshold} VND được xếp loại CHƯA ĐẠT KPI. "
        f"Trường hợp tổng phí bằng đúng {threshold} VND phải được coi là "
        f"ĐẠT KPI, không được xếp vào nhóm chưa đạt. "
        f"4. Quy tắc kết luận Đánh giá riêng từng {entity}, không dùng phí "
        f"bình quân mỗi phiếu để thay thế tổng phí. "
        "Không cộng trùng phí khi kết nối bảng danh mục dịch vụ. "
        f"Mỗi {entity} phải xuất hiện đúng một lần trong kết quả tổng hợp theo {entity}. "
        f"Nếu thiếu sự kiện, thiếu liên kết {entity} đã được kiểm chứng "
        f"hoặc thiếu số liệu cần thiết, "
        "kết quả phải ghi là chưa đủ bằng chứng; không tự gán doanh thu "
        "bằng 0 rồi kết luận chưa đạt. "
        "5. Phân biệt tài liệu quy định và số liệu vận hành "
        f"Tài liệu này chỉ mô tả quy tắc KPI và không công bố tổng phí "
        f"thực tế của bất kỳ {entity} nào. "
        f"Muốn trả lời {entity} nào đạt/chưa đạt, phải kết hợp tài liệu chính sách này với số liệu "
        "trong các bảng CSV của cùng workspace. Ghi chú: Tất cả tên doanh nghiệp, cơ sở, phiếu "
        "và số liệu trong bộ kiểm thử đều là dữ liệu tổng hợp giả lập, "
        "không đại diện cho giao dịch thật."
    )


def evidence(entity="cơ sở", metric="value_amount", identity="site_key", threshold="75,50"):
    _, _, context = relationship_fixture(False, True)
    edge = replace(context.approved_joins[0], source_column=identity, target_column=identity)
    context = replace(
        context,
        approved_joins=(edge,),
        table_columns={
            "random_f": {identity, metric, "event_date", "state"},
            "random_d": {identity, "name"},
        },
        column_types={
            "random_f": {
                identity: "TEXT",
                metric: "NUMERIC",
                "event_date": "DATE",
                "state": "TEXT",
            },
            "random_d": {identity: "TEXT", "name": "TEXT"},
        },
        table_labels={"random_f": "02_sự_kiện", "random_d": "01_" + entity},
        categorical_values={"random_f": {"state": ("Xác nhận",)}},
        column_profiles={
            "random_f": {
                "event_date": (6, 6, "2032-04-01", "2032-04-24"),
                "state": (6, 6, "Xác nhận", "Xác nhận"),
            }
        },
        table_row_counts={"random_d": 3, "random_f": 6},
    )
    words = regulation(entity, metric, identity, threshold).split()
    split = len(words) // 2
    title = f"01_quy_dinh_kpi_{entity.replace(' ', '_')}_thang_04_2032 > Trang 1"
    parts = (
        (71, title, " ".join(words[:split])),
        (72, title, " ".join(words[split - 30 :])),
    )
    scope = DocumentScope(
        11,
        "registered-content-hash",
        (71, 72),
        context.dataset_id,
        context.owner_user_id,
        tuple((i, hashlib.sha256(c.encode()).hexdigest()) for i, _, c in parts),
        parts,
    )
    return context, [RetrievedChunk(i, "regulation.pdf", t, c, 0.1, scope) for i, t, c in parts]


@pytest.mark.parametrize(
    "entity,metric,identity,threshold,totals",
    [
        ("cơ sở", "value_amount", "site_key", "75,50", ["75.49", "75.50", "75.51"]),
        ("trạm", "charge_total", "location_key", "12,01", ["12.00", "12.01", "12.02"]),
        ("khách sạn", "booking_amount", "hotel_key", "9.876,54", ["9876.53", "9876.54", "9876.55"]),
    ],
)
def test_renamed_schema_threshold_boundaries_and_complete_citations(
    entity, metric, identity, threshold, totals
):
    context, chunks = evidence(entity, metric, identity, threshold)
    assert parse_prose(policy_content(chunks[0], chunks)) is not None
    assert complete_policy_evidence(chunks[:1]) == chunks
    rows = [{"entity_id": f"E0{i}", "metric_value": value} for i, value in enumerate(totals)]
    sql, executor, gateway = pipeline(context, rows)
    result = HybridPipeline(
        sql, Mock(retrieve=Mock(return_value=chunks[:1])), gateway, context
    ).run("Đánh giá toàn bộ đối tượng theo chính sách.", classification="all")
    assert result.verification_status == "verified_classification"
    assert result.answer_row_indices is None
    assert [s.chunk_id for s in result.sources] == [71, 72]
    assert "Chưa đạt: E00." in result.answer and "Đạt: E01, E02." in result.answer
    executor.execute.assert_called_once()
    gateway.generate_structured.assert_not_called()


@pytest.mark.parametrize(
    "mutation",
    [
        "outside_period",
        "null_date",
        "mixed_status",
        "null_status",
        "ambiguous_date",
        "missing_profile",
        "owner",
        "hash",
        "missing_part",
        "exception",
        "second_rule",
        "header_condition",
        "section_condition",
        "section_period",
    ],
)
def test_incomplete_or_conditional_evidence_never_gains_authority(mutation):
    context, chunks = evidence()
    profiles = {t: dict(v) for t, v in context.column_profiles.items()}
    if mutation == "outside_period":
        profiles["random_f"]["event_date"] = (6, 6, "2032-04-01", "2032-04-25")
    elif mutation == "null_date":
        profiles["random_f"]["event_date"] = (6, 5, "2032-04-01", "2032-04-24")
    elif mutation == "mixed_status":
        profiles["random_f"]["state"] = (6, 6, "Hủy", "Xác nhận")
    elif mutation == "null_status":
        profiles["random_f"]["state"] = (6, 5, "Xác nhận", "Xác nhận")
    elif mutation == "missing_profile":
        profiles = {}
    elif mutation == "ambiguous_date":
        context = replace(
            context,
            column_types={
                **context.column_types,
                "random_f": {**context.column_types["random_f"], "other": "DATE"},
            },
        )
    elif mutation == "owner":
        from uuid import uuid4

        context = replace(context, owner_user_id=uuid4())
    elif mutation == "hash":
        chunks[0] = replace(chunks[0], content=chunks[0].content + "Changed")
    elif mutation == "missing_part":
        scope = replace(chunks[0].document_scope, document_parts=())
        chunks = [replace(chunks[0], document_scope=scope)]
    elif mutation == "section_condition":
        chunks = [replace(c, section_title="KPI > Chỉ áp dụng cho nhóm đặc biệt") for c in chunks]
    elif mutation == "section_period":
        chunks = [replace(c, section_title="KPI tháng 05 năm 2032") for c in chunks]
    elif mutation in {"exception", "second_rule", "header_condition"}:
        content = policy_content(chunks[0], chunks)
        if mutation == "header_condition":
            content = "KHÔNG ÁP DỤNG " + content
        else:
            content += (
                " Trừ cơ sở A." if mutation == "exception" else " Một quy tắc khác: phí >= 1."
            )
        scope = replace(
            chunks[0].document_scope,
            chunk_ids=(71,),
            text_hashes=((71, hashlib.sha256(content.encode()).hexdigest()),),
            document_parts=(),
        )
        chunks = [replace(chunks[0], content=content, document_scope=scope)]
    context = replace(context, column_profiles=profiles)
    sql, executor, gateway = pipeline(context, [])
    with pytest.raises(ModelResponseError):
        HybridPipeline(sql, Mock(retrieve=Mock(return_value=chunks)), gateway, context).run(
            "Đánh giá toàn bộ đối tượng.", classification="all"
        )
    executor.execute.assert_not_called()
    gateway.generate_structured.assert_not_called()
