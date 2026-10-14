# Báo cáo đánh giá hệ thống ShopQuery AI

Ngày chạy: 2026-10-14 (Asia/Saigon)

## Phạm vi và môi trường

- Full stack Docker: React/Nginx → FastAPI → PostgreSQL 17/pgvector → Gemini.
- Generation/router: `gemini-3.5-flash-lite`; embedding: `gemini-embedding-2`, 768 chiều.
- Corpus: 6 Markdown policy, 25 chunks đang lưu trong PostgreSQL.
- Dữ liệu demo được giữ nguyên: 150 products, 8 categories, 2.000 orders và 4.019 order items.
- Dataset upload đánh giá: `backend/tests/fixtures/upload_sales.csv`, 5 dòng. Ground truth độc lập: tổng doanh thu 1.600.000; doanh thu theo khu vực Nam 760.000, Trung 500.000, Bắc 340.000; tổng số lượng cao nhất là Bút 10.
- API live đi qua `http://127.0.0.1:8080/api`, tức qua Nginx chứ không gọi service Python trực tiếp.

## Kết quả live Gemini

| ID | Câu hỏi/rút gọn | Ground truth hoặc tiêu chí | Route thực tế | Kết quả |
| --- | --- | --- | --- | --- |
| SQL-01 | Top 5 bán chạy tháng 9/2025 | Điện thoại SQ 010: 15; Âm thanh SQ 009: 14; Gia dụng SQ 006: 11; Gia dụng SQ 009: 11; Văn phòng SQ 003: 10 | SQL | Pass |
| SQL-02 | Doanh thu completed tháng 9/2025 | 7.800.668.000 | SQL | Pass |
| SQL-03 | Số đơn completed | 1.435 | SQL | Pass |
| SQL-04 | Doanh thu completed theo category | 8 nhóm; cao nhất CAMERA 41.863.013.000, thấp nhất ACCESSORY 2.315.396.000 | SQL | Pass |
| RAG-01 | Chính sách đổi trả | 14 ngày; điều kiện và ngoại lệ được tài liệu hỗ trợ | RAG | Pass |
| RAG-02 | Bảo hành điện thoại | PHONE: 24 tháng | RAG | Pass |
| RAG-03 | Phí vận chuyển cố định | Tài liệu không nêu mức cố định | RAG | Pass |
| RAG-04 | Thời gian xử lý đơn | Một ngày làm việc sau xác nhận | RAG | Pass |
| HYBRID-01 | Top 5 bán chạy và miễn phí vận chuyển | Top 5 đúng SQL; chỉ LAPTOP trong kết quả được miễn phí, dựa trên category code | HYBRID | Pass |
| HYBRID-02 | Top 3 doanh thu và bảo hành | Cả ba là CAMERA; bảo hành 12 tháng | HYBRID | Pass |
| UNSUPPORTED-01 | Thời tiết Đà Nẵng | Ngoài dữ liệu/tài liệu cửa hàng; không được tạo evidence | UNSUPPORTED | Pass sau retry quota |
| UPLOAD-01 | Tổng số dòng CSV | 5 | SQL | Pass sau retry quota |
| UPLOAD-02 | Tổng doanh thu CSV | 1.600.000 | SQL | Pass sau retry quota |
| UPLOAD-03 | Xếp hạng theo tổng số lượng | Bút 10; Cà phê 5; Áo linen 5; Túi 1 | SQL | Pass |
| UPLOAD-04 | Doanh thu theo khu vực | Nam 760.000; Trung 500.000; Bắc 340.000 | SQL | Pass |

Kết quả cuối: 15 ca pass, 0 ca sai ground truth. Lần chạy đầu có 12 ca pass và 3 ca không hoàn tất vì HTTP 429; ba ca đó pass khi chạy lại một lần sau khi cửa sổ quota hồi phục. Không có ca nào được đổi expected result theo câu trả lời của Gemini.

### Kiểm tra evidence

- SQL được đối chiếu bằng câu lệnh PostgreSQL độc lập, luôn lọc `orders.status = 'completed'` khi câu hỏi yêu cầu số liệu bán hàng/doanh thu.
- RAG trả các `chunk_id` đang tồn tại trong `document_chunks`; ví dụ bảo hành dùng chunks 322/306, phí vận chuyển dùng chunk 316, thời gian xử lý dùng chunk 314.
- Hybrid trả đồng thời SQL rows và policy chunks. Kết luận miễn phí vận chuyển dùng `category_code`, không suy đoán từ tên sản phẩm.
- Dataset upload chỉ trả SQL/rows từ bảng vật lý của dataset 1, không có citations giả và không xuất hiện product/order của dữ liệu demo.
- UNSUPPORTED không trả SQL, rows hoặc sources.

## Availability và retry

Log container xác nhận ba lỗi lần đầu là `429 RESOURCE_EXHAUSTED` cho quota free-tier 15 generation requests/phút của `gemini-3.5-flash-lite`. Google GenAI SDK đã retry hữu hạn theo cấu hình, sau đó ứng dụng trả `route: null`, `error` rõ ràng và không tự tạo câu trả lời. Đây không phải lỗi schema, authentication, SQL validator hay dữ liệu.

Việc chạy lại được thực hiện một lần sau khi cửa sổ quota hồi phục. Không đổi model, không thêm fallback keyword và không nới SQL security. Giới hạn quota vẫn là vấn đề vận hành cần lưu ý.

## Kiểm thử xác định và thủ công

- Ruff: pass.
- Pytest không PostgreSQL: 63 pass.
- PostgreSQL integration trên database tạm: 13 pass, gồm conversation persistence, CSV/XLSX import, rollback, role read-only, row limit và dataset isolation.
- ESLint, TypeScript và production build: pass.
- Vitest: 10 pass.
- Playwright mock: 20 pass trên 1440, 1280, 768, 390 và 320 px.
- Visual review: desktop và mobile drawer không tràn ngang; header/composer không che nội dung; bảng có vùng cuộn riêng.
- Docker build: API và web pass; `db`, `api`, `web` healthy. Nginx `/api/health` và `/api/datasets` pass. Máy đánh giá còn giữ một socket Windows mồ côi ở host port 8000 sau khi dừng Uvicorn (PID không còn trong process table), nên lần nghiệm thu này ánh xạ API host tạm thời sang 8001; kết nối nội bộ Nginx → `api:8000` không thay đổi.
- Playwright live: 1/1 pass cho SQL, RAG và Hybrid qua React/Nginx; không có console error, page error, failed request hoặc response HTTP lỗi.

Các test parser xác định bao phủ UTF-8 BOM, Unicode, mã có số 0 đầu, header trùng/rỗng, row shape, giới hạn file/dòng/cột, công thức dạng text, sheet selection và archive XLSX không hợp lệ. SQL validator test bao phủ DDL/DML, multi-statement, catalog, bảng/schema khác và cross-dataset access.

## Giới hạn còn lại

- Free-tier Gemini có thể trả 429 khi đánh giá dồn nhiều request; UI/API xử lý an toàn nhưng người dùng phải chờ quota.
- Dataset upload hiện là một bảng/một sheet mỗi lần, không join datasets và không dùng RAG/Hybrid của corpus demo.
- Chưa có authentication, tenant isolation, antivirus và endpoint xóa dataset; không phù hợp để nhận dữ liệu nhạy cảm trên Internet.
- Live LLM có tính không tất định. Báo cáo này chỉ phản ánh đúng các request đã chạy ở ngày/ môi trường nêu trên.
