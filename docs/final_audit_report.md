# Báo cáo nghiệm thu cuối — ShopQuery AI

Ngày kiểm tra: **19/10/2026 (giờ Việt Nam)**.
Source baseline: commit [`fa4e7ad`](https://github.com/MinhHoang1403/Shopquery-AI/commit/fa4e7adc0314ce79d4a78aa2598a2d8bd5a7d8e6), sau bản sửa múi giờ SQL `ba977de`.

## Kết luận và phạm vi

**Đạt nghiệm thu sử dụng local/MVP trong phạm vi đã kiểm chứng.** Không phát hiện lỗi chặn trong 6 lượt live SQL/RAG/Hybrid với Knowledge và Gemini, cùng việc lưu/khôi phục lịch sử. Đây không phải chứng nhận sẵn sàng production công khai, kiểm thử tải hoặc bảo đảm mọi câu hỏi/dataset đều đúng.

Đợt live này không sửa mã, model, cấu hình hoặc dữ liệu nghiệp vụ. Chỉ tạo và giữ hai hội thoại kiểm thử. Bản cập nhật tài liệu sau đó ghi lại kết quả này; SHA và CI của commit tài liệu được bàn giao riêng, không tự ghi SHA của chính nó vào file.

## Môi trường thực tế

- Giao diện `http://127.0.0.1:8080/`: React → Nginx → FastAPI → PostgreSQL 17/pgvector; không mock.
- Model generation/router: iNetCloud `knowledge` và Gemini `gemini-3.5-flash-lite`; embedding Gemini `gemini-embedding-2`, 768 chiều cho RAG của cả hai model.
- Dữ liệu chọn trên UI: **Dữ liệu cửa hàng mẫu**, không phải workspace upload.
- API `/models` xác nhận cả hai model đã cấu hình; `gemini_fallback_enabled=false`. Kết quả live, không phải riêng cờ `configured`, chứng minh khả dụng tại thời điểm thử.
- Container `db`, `api`, `web` đều healthy; `/api/health` trả `ok`.
- Cổng host trong lần nghiệm thu: web 8080, API 8001, PostgreSQL 15432 do override local. Mặc định repository vẫn là 8080/8000/54321; nội bộ Nginx vẫn dùng `api:8000`.

## Ma trận live qua giao diện

Mỗi câu chạy một lần/model, khoảng 09:25–09:30 ngày 19/10/2026:

1. SQL: “Top 5 sản phẩm bán chạy nhất tháng 9/2025 là gì?”
2. RAG: “Chính sách đổi trả của cửa hàng như thế nào?”
3. Hybrid: “Top 5 sản phẩm bán chạy nhất tháng 9/2025 có thuộc danh mục được miễn phí vận chuyển không?”

| Model | Route thực tế | SQL rows | Nguồn | Thời gian server | Kết quả |
| --- | --- | ---: | ---: | ---: | --- |
| Knowledge | SQL | 5 | 0 | 7,909 giây | Pass |
| Knowledge | RAG | 0 | 3 | 5,112 giây | Pass |
| Knowledge | HYBRID | 5 | 3 | 8,566 giây | Pass |
| Gemini | SQL | 5 | 0 | 3,382 giây | Pass |
| Gemini | RAG | 0 | 3 | 2,777 giây | Pass |
| Gemini | HYBRID | 5 | 3 | 5,195 giây | Pass |

Thời gian lấy chênh lệch `created_at` của user message và assistant message; không phải thời gian đo toàn bộ render trình duyệt hoặc benchmark tải. Cả 6 response có `error=null`, `requested_model=used_model`, `fallback_used=false`. Không lấy Gemini fallback để tính Knowledge pass.

### SQL: đối chứng dữ liệu và múi giờ

Đối chứng độc lập qua role `shopquery_reader`:

```sql
SELECT p.product_id, p.product_name, c.category_code,
       SUM(oi.quantity) AS total_quantity
FROM orders AS o
JOIN order_items AS oi USING (order_id)
JOIN products AS p USING (product_id)
JOIN categories AS c USING (category_id)
WHERE o.status = 'completed'
  AND o.order_date >= TIMESTAMPTZ '2025-09-01 00:00:00+07'
  AND o.order_date < TIMESTAMPTZ '2025-10-01 00:00:00+07'
GROUP BY p.product_id, p.product_name, c.category_code
ORDER BY total_quantity DESC, p.product_id
LIMIT 5;
```

| Product ID | Sản phẩm | Danh mục | Tổng quantity |
| --- | --- | --- | ---: |
| 10 | Điện thoại SQ 010 | PHONE | 15 |
| 47 | Thiết bị âm thanh SQ 009 | AUDIO | 14 |
| 120 | Thiết bị gia dụng SQ 006 | HOME | 11 |
| 123 | Thiết bị gia dụng SQ 009 | HOME | 11 |
| 135 | Thiết bị văn phòng SQ 003 | OFFICE | 10 |

Cả 4 response có SQL (SQL và Hybrid của mỗi model) khớp tập sản phẩm/quantity này. Hai sản phẩm đồng hạng 11 có thể đổi thứ tự. SQL sinh ra dùng local `TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh'`, đúng biên tháng Việt Nam. Đã mở SQL và bảng bằng chứng trên UI, không chỉ kiểm tra nhãn route.

Executor dùng timezone transaction-local cho cả hai provider và SQL trong Hybrid; không thay timezone toàn database. Bộ integration hiện có gồm 40 test biên tháng, năm mới, năm nhuận, grouping và không rò timezone khi transaction lỗi. Đợt live này không thay thế hoặc mở rộng kết quả của bộ test đó.

### RAG: nguồn thật và nội dung được hỗ trợ

Cả hai response RAG truy hồi 3 chunks: `faq.md`/304, `return_policy.md`/310 và 312. Câu trả lời nêu đúng thời hạn gửi yêu cầu 14 ngày, xử lý hàng lỗi/giao sai, chi phí đổi trả và hoàn tiền khi hết hàng. Đây là câu trả lời theo 3 đoạn truy hồi, không phải khẳng định đã trình bày toàn bộ mọi điều khoản của tài liệu.

Đã mở nguồn/trích đoạn trên UI và so sánh `chunk_id`, `source_file`, `section_title`, `content` với `document_chunks`: không có sai lệch. Chunk IDs là snapshot của database tại ngày kiểm tra, không phải ID bất biến cho mọi lần ingest.

### Hybrid: kết hợp SQL và tài liệu

Mỗi response Hybrid có 5 SQL rows khớp đối chứng và 3 nguồn thật: `faq.md`/303, `shipping_policy.md`/315 và 316; toàn bộ metadata/nội dung nguồn khớp database.

Chính sách miễn phí tiêu chuẩn áp dụng `PHONE` và `LAPTOP`. Trong top 5 tháng 9/2025 chỉ **Điện thoại SQ 010 (`PHONE`)** đủ điều kiện. Cả hai model kết luận đúng: Knowledge trả lời ngắn gọn 1/5; Gemini liệt kê từng sản phẩm. Không phát hiện số liệu hoặc nguồn giả trong các lượt đã thử.

## Lịch sử hội thoại

Hai chat được tạo và giữ lại trên máy nghiệm thu:

- `Nghiệm thu cuối · Knowledge · 19-10`.
- `Nghiệm thu cuối · Gemini · 19-10`.

Đã đổi tên trên UI, tải lại trang riêng cho mỗi chat và chuyển giữa hai hội thoại. Mỗi chat khôi phục đúng model và đủ 6 tin nhắn (3 user + 3 assistant), đúng thứ tự/nội dung, kèm SQL, bảng và nguồn. Kiểm tra bằng UI, `GET /api/conversations/{id}` và `SELECT` trong PostgreSQL; không chỉ dựa vào trạng thái React còn trong bộ nhớ. Lịch sử cũ không bị sửa hoặc xóa.

## Health và an toàn dữ liệu trong đợt kiểm tra

- Console trình duyệt không ghi nhận warn/error trong phiên kiểm tra.
- API logs từ `2026-10-19T02:25:40Z` đến lần lấy log: 50 access requests, không có HTTP 4xx/5xx hoặc dòng ERROR/Traceback. Đây là cửa sổ quan sát, không phải cam kết uptime.
- Số bản ghi nghiệp vụ ở lần đo giữa và cuối không đổi: 150 products / 2.000 orders / 4.019 order items / 25 chunks / 2 datasets / 2 dataset tables / 0 dataset documents.
- Chỉ đọc dữ liệu đối chứng; không chạy integration fixture ghi/xóa vào database ứng dụng.
- Không đưa API key, endpoint công ty, `.env`, log, dump hoặc screenshot local vào Git. Ảnh bằng chứng được giữ local; kết quả có thể mở lại trong hai chat nêu trên.

## Kiểm thử tự động và GitHub CI

Run đã xác minh trước đợt live: [CI 39189762428](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39189762428), đúng baseline `fa4e7ad`, cả 3 jobs thành công.

| Nhóm | Kết quả đã xác minh |
| --- | --- |
| Ruff | Pass |
| Backend unit/API/parser/security | 147 passed, 65 deselected |
| PostgreSQL integration | 57 passed, 155 deselected, không skip |
| Frontend Vitest | 24 passed |
| ESLint / TypeScript / production build | Pass |

Integration job có service PostgreSQL 17/pgvector riêng, database `shopquery_ci`, role đọc riêng và `RUN_DATABASE_TESTS=1`; không cần API key, không gọi provider thật. Service bị hủy sau job. Hai marker `integration`/`live` được tách khỏi unit job; live tests không chạy trong CI. Không cộng các test deselected vào số test pass.

Không chạy lại Playwright mock, live upload, Unsupported, failure injection hoặc build Docker trong đợt live 19/10 này. Những kết quả lịch sử vẫn giữ đúng ngày/phạm vi tại [đánh giá trước đây](evaluation_report.md), [multi-model](multi_model_integration.md) và [audit 14/10](archive/final_audit_2026-10-14.md); không tính chúng là test mới vừa chạy.

## Những việc chưa được nghiệm thu

- Chưa kiểm thử tải, độ bền dài hạn, mọi câu hỏi tự nhiên hoặc mọi dataset upload trong đợt cuối này.
- Chưa có authentication, phân quyền người dùng/tenant, rate limiting hoặc quản lý secrets đạt yêu cầu production công khai; không mở nguyên bản local ra Internet hoặc đưa dữ liệu nhạy cảm vào bản dùng chung.
- Upstream Knowledge/Gemini, mạng và quota vẫn có thể gây timeout/429/503; smoke thành công không bảo đảm lỗi sẽ không tái diễn.
- Các giới hạn MVP vẫn giữ nguyên: uploaded workspace chưa hỗ trợ JOIN, chưa OCR PDF scan, chưa có endpoint xóa dataset.

Kết luận bàn giao: **sẵn sàng dùng local/MVP cho các luồng đã kiểm chứng; chưa nghiệm thu public production**.
