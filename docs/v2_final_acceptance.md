# Nghiệm thu hệ thống hiện hành

**Đã chuyển sang giai đoạn sử dụng và bảo trì trong phạm vi khả năng đã nghiệm thu.**
Không release tag/full Stage2, không enterprise/public-ready hoặc bảo đảm mọi schema.
Một source main, một ShopQuery8080, một Langfuse3000. Runtime/image/config chính xác
ở [deployment](deployment.md); quyết định cleanup/Git/tests cuối ở [handoff](operational_handoff.md).

**Cập nhật28/10/2026:** API `4ab2c5a`/image2d27fba1 và Webde0572e/b2188879 đang chạy8080.
**APPLICATION_ACCEPTED_WITH_UPSTREAM_LIMITATIONS**: AutoRAG policy-only/citation23,
exactCOUNT+SUM192/24360000,16khách sạn và Hybrid/follow-up/RAG trong cùng hội thoại đã
PASS đúng oracle/tài liệu. Một Hybrid failure trên candidate trước được giữ trong scorecard;
API đã rollback rồi sửa contract và nghiệm thu3câu mới thành công. Không chọn riêng caPASS.
Knowledge generation sau403/timeout vẫn chưa được nghiệm thu,giữmanual/fallbackOFF.
Các PASS cũ bên dưới có phạm vi/timestamp riêng, không phải khả năng tổng quát vô hạn.
Root causes/functions, CI, scorecard và ngân sách: [correctness review](correctness_review.md).
Tổng7requests mới/13generation/5query/0document,attempts1,khôngretry/fallback; cửa sổđãđóng.
Strict88modules/source/configPASS,36objects/316messagescũ nguyênvẹn; thêm14messages.

## Bằng chứng đang dùng

| Phạm vi | Kết luận / giới hạn | Nguồn |
| --- | --- | --- |
| Gemini SQL | PASS bounded live: tổng phiên/phí, JOIN và Khách sạn; không general SQL guarantee | [Live6 câu](observability_acceptance.md) |
| Knowledge SQL | PARTIAL: JOIN live mới PASS; đợt rộng hơn15 PASS/1 UNKNOWN recorder, chưa promote default | [Scorecard/root cause](architecture_audit.md) |
| RAG | PASS bounded: workspace scope, citation 23, chính sách đã lưu | [Live Q3](observability_acceptance.md) |
| Hybrid | PASS bounded: đủ 12entity metrics,6 đạt/6 chưa, exact Decimal, source-bound policy | [Live Q4](observability_acceptance.md) |
| Follow-up | PASS trong cùng conversation sau verified premise; không nhận unverified/cross-owner context | [Live Q5](observability_acceptance.md), CI context tests |
| Authentication | Existing Google session/reload/history PASS; OIDC/CSRF/owner negatives ở CI. Không coi reload là fresh sign-in | [Auth](authentication.md) |
| Upload | PDF NUL correction từng upload thật 1lần/3 chunks-vectors PASS; parser/limits/CSV-XLSX/DOCX regressions ở CI | Application b48cfc2; hồ sơ Git bên dưới |
| Relationships | Auto-discovery/approval N:1, full-data verification/revision guard, không fanout | [Capabilities](capabilities.md), CI integration |
| Frontend | SQL inline/table preview/workspace/model/history/citation và mock E2E PASS | Live baseline và CI |
| Langfuse | READY_WITH_LIMITATIONS:234 observations,6 root,10 generation/3 query, usage/privacy PASS | [Telemetry acceptance](observability_acceptance.md) |
| BGE/GPU | NOT_ACCEPTED production; vector-only đang dùng, không benchmark lại | Operator baseline |
| Public deployment | NOT_VERIFIED: TLS/least-privilege/offsite restore/capacity chưa nghiệm thu | [Security](security.md) |

## Workflow và invariants được bảo toàn

Authentication/owner scope trước truy cập dữ liệu → bounded conversation context →
Auto Router → SQL/RAG/Hybrid hoặc safe refusal → verified/presented evidence →
persistence → UI. Langfuse export metadata async, không trở thành điều kiện chatbot
thành công. Stages/model calls chỉ có khi thực chạy.

- Structured generation giữ Pydantic validation và deterministic conversion vào QueryPlan;
  không free-form SQL, không repair/retry loop hay đổi provider để che refusal.
- Catalog IDs/relationships được cấp theo owner/workspace. Binder chỉ hoàn thiện cấu trúc
  duy nhất từ metadata đã duyệt, không bỏ WHERE/HAVING/LIMIT hoặc đoán fact/category grain.
- JOIN uploaded tối đa 3 tables, approved N:1/revision/full-data key verification. Chặn
  many-to-many, fanout, ambiguous path, dimension aggregates, invalid COUNT provenance.
- Compiler/SQLGlot kiểm cả bound SQL và evidence SQL, chỉ allowed SELECT/functions;
  read-only reader/timeout/row cap. NULL khác 0, NUMERIC giữ decimal strings và exact digits.
- Hybrid retrieval → policy requirements → SQL → binding/coverage → policy verification.
  Plan và compiled coverage kiểm trước execution; classification giữ đủ entity set,
  không để WHERE/HAVING/LIMIT làm mất entity rồi suy toàn bộ là đạt.
- Decimal verdict chỉ cho một policy đủ source/hash/unit/metric/identity scope. Multiple,
  conflicting, unsupported qualifiers hoặc thiếu citation phải refusal/unverified.
- Persistence giữ verification_status. Context chỉ cùng owner/conversation/dataset,
  Hybrid premise cần verified_classification, bounded 2turns; không coi history là evidence mới.
- Upload/parse/chunk/retrieval/citation owner-scoped; không OCR hoặc cross-workspace corpus.

Chi tiết implementation và failing reproductions được giữ trong
[architecture audit](architecture_audit.md), không tạo pipeline hoặc luật nghiệp vụ mới.

## Baseline live27/10/2026 — cửa sổ đã đóng

Ngày 27/10/2026, source 3fe4cc2/API d8ad8aa5, Web 02d5cbb/ae181335:
Gemini SQL 360/33066538.03, Knowledge JOIN 12trạm, RAG citation 23, Hybrid 6đạt/6 chưa,
follow-up6chưa cùng conversation, Khách sạn16rows>100 phòng đều đúng oracle/tài liệu.
10/20 generation stages,3/8 query embeddings,0 document, attempts1, không retry/fallback.
32601 generation tokens khớp SDK/diagnostics/Langfuse. Mọi embedding token/cost thiếu
upstream vẫn UNKNOWN. Mỗi trace đã mở trên Dashboard và đọc lại qua API.

Fingerprints 33data objects +238 old messages không đổi, thêm12messages nghiệm thu.
Đợt consolidation này không gọi paid provider hoặc tái dùng phần dư ngân sách đó;
không re-embed/upload fixture hoặc chạy main migrations.

## CI và runtime

CI source 3fe4cc2 đã PASS1391 backend unit/857 PostgreSQL integration/85 frontend/
125 mockE2E,132 targeted telemetry và10 Compose checks. Consolidation thêm 10 maintenance
tests, gộp duplicate observability workflow vào CI chính; số exact-head cuối ghi tại
[handoff](operational_handoff.md), không cộng các suite có overlap.

Strict verifier kiểm 88app modules và effective Compose/image/env. Docs/scripts không
đổi app inputs nên không rebuild/redeploy để ép OCI label bằng docs HEAD. Web và main DB
không recreate; protected volume/datasets/documents/vectors/relationships/history giữ.

## Các giới hạn thực tế

- Knowledge broad acceptance còn UNKNOWN; manual selection được giữ, Gemini default.
- BGE chưa production acceptance; không full retrieval-quality/latency/capacity benchmark.
- Embedding usage không được SDK trả token trong responses đã đo; Knowledge cost UNKNOWN,
  Gemini inferred cost estimated. Không coi UNKNOWN là miễn phí.
- Langfuse retention edition hiện tại chưa có cơ chế nghiệm thu; backup/restore chưa drill.
- Runtime setup DB role vẫn có quyền cao cho quản lý workspace; không phải least-privilege
  public deployment, không có RLS hoặc database riêng cho từng owner.
- Existing session/reload không thay fresh Google sign-in test; upload parser/mock không
  thay live upload mới. Không tạo thêm paid calls chỉ để đổi các nhãn đó thành PASS.

## Hồ sơ lịch sử và ngân sách

Nhật ký trước consolidation giữ nguyên tại
[acceptance24ab3c8](https://github.com/MinhHoang1403/Shopquery-AI/blob/24ab3c8d89d63c2d6b80ec3932c45c3c82edd1b8/docs/v2_final_acceptance.md).
Bao gồm PDF NUL live acceptance b48cfc2/3 chunks, coverage/context 3364da4 và follow-up,
Knowledge HTTP503/upstream limitations, wire/binding corrections và các paid windows.
Các cửa sổ đó đã đóng; không dùng lại quota hoặc runtime/gate lịch sử làm hiện hành.
