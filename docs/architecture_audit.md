# Ranh giới kỹ thuật của stable baseline

ShopQuery ngừng phát triển theo chỉ thị29/10/2026. Không triển khai candidate SemanticTask.
Kiến trúc vận hành ở [architecture](architecture.md), giới hạn ở [capabilities](capabilities.md),
nguồn/image/config/khôi phục ở [deployment](deployment.md), bàn giao cuối ở
[PROJECT_CLOSEOUT](PROJECT_CLOSEOUT.md).

## Những điều cần giữ khi vận hành

- Router phân loại evidence/intent/scope; QueryPlanner sinh typed QueryPlan. Hai trách nhiệm
  này đều đang được stable service gọi, không phải hai engine dư thừa.
- Binder chỉ hoàn thiện phần cơ học đã chứng minh bằng approved N:1/metadata. Compiler,
  COUNT provenance, fact/grouping grain, AST validation, bound params, read-only executor,
  timeout/row cap và owner/workspace scope vẫn bắt buộc.
- Hybrid coverage cũ còn active trong stable baseline. Không xóa `hybrid_coverage.py`
  hoặc các readers lịch sử chỉ vì candidate tag có implementation thay thế.
- Decimal/NULL/source lineage và full-policy evidence không được thay bằng model verdict.
  Citation đúng ID không tự chứng minh câu trả lời đầy đủ; conversation trust có giới hạn.
- Auth/CSRF, scoped persistence, Guest limits và telemetry privacy là các boundary riêng;
  mock tests không thay thế live acceptance.

## Giới hạn bằng chứng

Knowledge từng có schema/literal/binding failures,403/timeout; root cause nội bộ upstream
không xác định.15 SQL mẫu lịch sửPASS/1UNKNOWN không phải accuracy tổng quát hoặc SLA.
Generation trên mạng công ty trong candidate tag không promote stable default/fallback.
Gemini mặc định, Knowledge manual, fallbackOFF. Chỉ coi các mẫu trong
[correctness review](correctness_review.md) là bounded acceptance; không hỗ trợ mọi
paraphrase/schema/policy, không full Stage2/public/enterprise-ready.

## Hồ sơ lưu trữ

- [Audit, scorecards, sources và negative evidence đầy đủ](https://github.com/MinhHoang1403/Shopquery-AI/blob/b09ec4ebb21d63e2e11841243210bf23f6d54f26/docs/architecture_audit.md).
- [Nguồn kỹ thuật](technical_references.md), dependency pins nằm trong lockfiles.
- Candidate chưa nghiệm thu: annotated tag `shopquery-core-unaccepted-2026-10-29`,
  commit26168c1; không mergePR5 và không dùng làm release.

Việc rút gọn tài liệu không xóa lịch sử hoặc tests bảo vệ invariants.
