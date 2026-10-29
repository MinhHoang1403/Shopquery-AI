# Langfuse — bằng chứng vận hành được giữ khi closeout

**LANGFUSE_READY_WITH_LIMITATIONS** trong phạm vi nghiệm thu27/10/2026.
Không chạy lại provider trong closeout29/10. Sáu service chính thức và volumes được giữ;
startup/recovery ở [runbook](../ops/langfuse/README.md), hiện trạng cuối ở
[PROJECT_CLOSEOUT](PROJECT_CLOSEOUT.md). Các application revisions sau đó nằm trong
[deployment](deployment.md) và [correctness review](correctness_review.md).

## Invariants và giới hạn

Một correlation/root trace mỗi request; observations chỉ phản ánh stages/calls thực.
Generation/embedding attribution riêng, SDK usage đo được khác missing/estimated/cached.
Không cộng root subtotal vào child tokens.234 observations của6requests có raw input/output
null, no orphan/duplicate IDs, không raw prompts/documents/rows/SQL/keys/emails/session IDs.
Offline tests bảo vệ fail-open/OFF/timeout/export error/queue bound; không cố gây paid lỗi
trong lượt live. Browser render duration không phải backend span.

10generation/3query/0document embeddings,32601generation tokens đã đo trong cửa sổ lịch sử.
Embedding tokens/cost và giá Knowledge UNKNOWN; không coi bằng0 hoặc hóa đơn đầy đủ.
Gemini default, Knowledge manual, fallbackOFF/GuestOFF; runtime gateON giữ nguyên.

## Scorecard lịch sử và trace IDs


| Q | Câu hỏi nguyên văn | Model / route | Oracle / kết quả | Input / output / total đã đo | End-to-end |
| --- | --- | --- | --- | --- | --- |
| 1 | Tổng cộng có bao nhiêu phiên sạc và tổng phí của tất cả phiên là bao nhiêu? | Gemini / SQL |360 phiên,33066538.03; PostgreSQL PASS|7171 /285 /7456|4.591 s|
| 2 | Cho tôi số phiên sạc và tổng phí theo từng trạm sạc. | Knowledge / SQL JOIN |12 trạm, mỗi trạm30phiên; mọi tên/mã/phí khớp oracle|7177 /1673 /8850|13.908 s|
| 3 | Chỉ dựa trên tài liệu KPI đã lưu, điều kiện để một trạm sạc đạt KPI là gì? | Gemini / RAG |threshold2800000, mọi trạng thái, ma_tram; citation 23|4213 /101 /4314|3.900 s|
| 4 | Theo tài liệu KPI, trạm nào đạt và trạm nào chưa đạt? | Gemini / HYBRID |TS07–TS12 đạt;TS01–TS06 chưa đạt; đủ 12metric/citation 23/verified_classification|3291 /43 /3334|2.607 s|
| 5 | Vậy còn những trạm chưa đạt KPI? | Gemini / HYBRID follow-up |cùng conversationQ4;12 evidence rows,6 presentation indices đúngTS01–TS06, verified/citation 23|3613 /48 /3661|2.756 s|
| 6 | Những khách sạn nào có số phòng lớn hơn 100? | Gemini / SQL |16 mã/tên khách sạn khớp PostgreSQL WHERE so_phong>100|4717 /269 /4986|3.722 s|

Oracle được viết độc lập, không thực thi SQL do model tạo để chấm chính nó. SQL
persisted rows so với oracle sau chuẩn hóa thứ tự/aliases; Decimal so chính xác,
không float tolerance. Q5 chỉ gửi sau Q4 metrics/verdict/citation/persistence PASS.
Q6 chuyển workspace qua dialog bắt đầu chat mới; không đưa context Xe điện sang Khách sạn.

| Q | Correlation = trace ID | Spans | Generation / query embedding | Usage status toàn request |
| --- | --- | --- | --- | --- |
|1|b567bb2ef95f4e6a80d4edb5a73ad2c0|34|2 /0|measured|
|2|c9ebd80f61b1457fb7cab384a5f4debc|34|2 /0|measured|
|3|fdc52d81ebf7463ea11930fe46deae1c|16|2 /1|partial: embedding UNKNOWN|
|4|365e680d297e4ed7b016bb141a4c1cfb|58|1 /1|partial: embedding UNKNOWN|
|5|023d32f9301149018f70877c73b437b0|58|1 /1|partial: embedding UNKNOWN|
|6|476c869d29794ee1ba422f1ec1cc6ec4|34|2 /0|measured|

## Retention, storage và backup


Project Settings bản hiện hành không có Data Retention trong menu. Theo
[Langfuse retention](https://langfuse.com/docs/administration/data-retention), tính năng
self-hosted này thuộc Enterprise; mặc định không tự xóa. Không có license được cấu hình,
không chỉnh TTL database/lifecycle blob để vượt edition và không xóa trace kiểm thử.
Đề xuất7ngày khi có tính năng chính thức được cấp phép; hiện giữ dữ liệu, theo dõi disk
và làm maintenance có duyệt trước khi storage đầy. Không có scheduled cleanup mới.

Mẫu trước live: PostgreSQL15439539bytes, ClickHouse256720KiB, MinIO208KiB; đây là
storage thực ở thời điểm kiểm, không dự báo tốc độ tăng từ hai synthetic traces.
Docker logs rotation10m×3/service. Worker xử lý được ingestion; không OOM/restarts.
**BACKUP_RESTORE_NOT_VERIFIED**: runbook bảo vệ cả năm volumes và secrets đã có,
chưa snapshot/restore drill; không sao chép data directory khi database đang ghi.


## Lịch sử

[Ma trận coverage, privacy, usage và scorecard đầy đủ](https://github.com/MinhHoang1403/Shopquery-AI/blob/b09ec4ebb21d63e2e11841243210bf23f6d54f26/docs/observability_acceptance.md).
Sáu câu trên không phải kiểm thử lại bằng lõi candidate. Existing-session reload đã kiểm
trong đợt cũ; không được báo là fresh OAuth hoặc upload/embedding acceptance mới.
