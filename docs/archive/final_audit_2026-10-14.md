# Báo cáo nghiệm thu cuối cùng ShopQuery AI

> Bản lưu lịch sử ngày 14/10/2026, không đại diện cho trạng thái hiện tại.
> Xem [báo cáo nghiệm thu mới nhất](2026-10/final_audit_report.md).

Ngày kiểm tra: 2026-10-14 (Asia/Saigon)
Phạm vi source được nghiệm thu: commit `5f5d8e35085b3f3d0adecd40b15281e59aa8f23a` trên `main`.

Kết luận: **FINAL AUDIT — PASSED**. Không phát hiện lỗi blocking, regression, secret bị commit hoặc sai lệch dữ liệu. Source code và giao diện không cần sửa; thay đổi duy nhất của đợt audit là hiệu chỉnh ba mô tả trong README và bổ sung báo cáo này.

## A. Repository

- Workspace đúng: `C:\Work\ShopQuery AI`; remote đúng: `https://github.com/MinhHoang1403/Shopquery-AI.git`.
- Branch `main`; local và `origin/main` cùng SHA `5f5d8e35085b3f3d0adecd40b15281e59aa8f23a` khi bắt đầu audit; working tree ban đầu sạch.
- `.gitignore` loại trừ `.env`, venv, cache, logs, database dumps, build/test artifacts và Playwright screenshots. `.env.example` được giữ lại có chủ đích và không chứa API key.
- Không force-push, không tạo branch/tag/release và không thao tác repository khác.

## B. Architecture

- Frontend React 19/TypeScript/Vite gọi API tương đối `/api`; Nginx phục vụ SPA và proxy đến `api:8000` trong mạng Compose.
- Backend FastAPI tách routes/contracts, Gemini gateway, router, Text-to-SQL, RAG, Hybrid, conversations và datasets theo trách nhiệm.
- Generation/router dùng `gemini-3.5-flash-lite`; embedding dùng `gemini-embedding-2`, 768 chiều. Structured output vẫn được kiểm tra ở tầng ứng dụng.
- PostgreSQL 17/pgvector lưu dữ liệu demo, chunks, lịch sử chat và metadata dataset; dữ liệu import nằm trong schema `uploaded_data`.
- Docker images ghim Python 3.11.9, uv 0.12.15, Node 24.21.0 và Nginx 1.31.6. Services chỉ bind vào `127.0.0.1`.

## C. Functional Tests

- Conversations: integration và Playwright mock bao phủ tạo, lưu user/assistant messages, refresh/khôi phục, tạo chat thứ hai, chuyển chat, rename, delete và gắn dataset; không trộn messages.
- Dataset: CSV/XLSX preview/import, sheet selection, duplicate name 409, validation 422, rollback, metadata, role read-only và isolation đều được kiểm thử. Live query dataset 1 (fixture 5 dòng) trả tổng doanh thu `1.600.000`.
- SQL live: route `SQL`, không lỗi, có SQL và 5 rows; kết quả top 5 tháng 9/2025 khớp truy vấn PostgreSQL độc lập.
- RAG live: route `RAG`, không lỗi, không SQL/rows giả, trả 3 nguồn có thật (`304`, `310`, `312`) hỗ trợ thời hạn 14 ngày và các điều kiện đổi trả.
- Hybrid live: route `HYBRID`, không lỗi, có 5 SQL rows và 3 chunks có thật (`303`, `315`, `316`); kết luận chỉ `LAPTOP` được miễn phí vận chuyển dựa trên `category_code` và policy.
- Unsupported: không chạy lại live để tránh tiêu tốn quota khi code AI không đổi; bộ đánh giá đã lưu, unit/API và Playwright mock hiện tại đều xác nhận không tạo SQL, rows hoặc citations giả.
- Error handling: tests bao phủ network error, HTTP 422/500, HTTP 200 có `error`, Gemini transient/non-retryable/exhausted retry và không tự tạo response khi generation thất bại.

## D. Data Integrity & Security

- Database chính chỉ được đọc trong audit. Số liệu: 8 categories, 150 products, 2.000 orders, 4.019 order items, 25 document chunks, 9 conversations, 50 messages, 1 dataset và 1 dataset table.
- Không có orphan product/category, order item/order, order item/product, message/conversation hoặc dataset table/dataset. Bảng vật lý uploaded dataset tồn tại, tên ngẫu nhiên hợp lệ và row/column metadata khớp.
- `shopquery_reader` chỉ có quyền `SELECT`, không phải superuser/createdb/createrole. `shopquery_setup` là role bootstrap đặc quyền của môi trường Docker; SQL do model sinh không dùng role này.
- SQLGlot chỉ cho phép một root `SELECT`, áp dụng allowlist bảng/cột/hàm và từ chối DDL, DML, CTE/subquery ngoài phạm vi, catalog và cross-dataset access. Read-only transaction, statement timeout và row limit vẫn được áp dụng.
- Parser giới hạn loại file/kích thước/dòng/cột, kiểm tra header và row shape, không thực thi công thức, chặn XLSX bất thường và tạo identifier vật lý từ UUID thay vì tên file/người dùng.
- Không phát hiện Gemini key/private key trong file tracked hoặc frontend bundle; không có `.env`, user uploads, dump, log, screenshot hay test artifact bị commit. Seed CSV và test fixtures là dữ liệu giả lập có chủ đích.
- Hệ thống chưa có authentication, tenant isolation, antivirus, production secret manager hoặc rate limiting; **không phù hợp để mở công khai trên Internet** trước khi bổ sung các kiểm soát này.

## E. Testing Results

| Test group | Passed | Failed | Skipped | Notes |
| --- | ---: | ---: | ---: | --- |
| Ruff | 1 gate | 0 | 0 | `app`, `scripts`, `tests` |
| Pytest unit/API/security/parser | 65 | 0 | 0 | 13 integration tests được tách sang database tạm |
| PostgreSQL integration | 13 | 0 | 0 | Database tạm đã xóa; database chính không bị ghi |
| ESLint | 1 gate | 0 | 0 | Toàn bộ frontend |
| TypeScript | 1 gate | 0 | 0 | `tsc -b --pretty false` |
| Vitest | 13 | 0 | 0 | Component/interaction tests |
| Production build | 1 gate | 0 | 0 | Vite build thành công |
| Playwright mock | 20 | 0 | 0 | 5 viewport, 4 luồng mỗi viewport |
| Playwright live UI | 1 | 0 | 0 | SQL/RAG/Hybrid; database/API audit tạm đã xóa |
| Live stateless `/api/chat` | 4 | 0 | 0 | SQL, RAG, Hybrid, uploaded dataset qua Nginx |
| Docker build | 2 images | 0 | 0 | API và web |
| Infrastructure | 5 checks | 0 | 0 | Compose config, db/api/web health, Nginx config, `/api/health` |

Pytest chỉ phát một `StarletteDeprecationWarning` từ thư viện `TestClient`; đây là cảnh báo non-blocking. `uv.lock` hợp lệ; toàn bộ dependency lines trong root `requirements.txt` khớp export runtime từ lockfile (khác duy nhất dòng header ghi chính lệnh export). `npm ls --depth=0` không thiếu dependency.

## F. AI Evaluation

| Ca live mới | Route | Ground truth/evidence | Kết quả |
| --- | --- | --- | --- |
| Top 5 tháng 9/2025 | SQL | `15, 14, 11, 11, 10`; đúng 5 product IDs theo PostgreSQL độc lập | Pass |
| Chính sách đổi trả | RAG | 14 ngày; chunks `304`, `310`, `312` tồn tại trong `faq.md`/`return_policy.md` | Pass |
| Top 5 và miễn phí vận chuyển | HYBRID | 5 rows khớp PostgreSQL; chunks `303`, `315`, `316`; chỉ category `LAPTOP` miễn phí | Pass |
| Tổng doanh thu dataset fixture | SQL | `1.600.000`, đúng file 5 dòng; không có demo rows/citations | Pass |

Ground truth SQL được tính bằng truy vấn PostgreSQL độc lập, RAG chunks được đối chiếu với metadata tài liệu gốc và dataset được đối chiếu với fixture. Không có quota/503/429 trong smoke mới. Báo cáo đánh giá 15 ca trước đó vẫn nhất quán với source/corpus hiện tại; các lần 429 lịch sử được ghi là sự cố quota tạm thời, không được đổi expected result để tạo pass.

## G. UI & Browser

- Playwright Chromium đạt ở 1440×900, 1280×800, 768×1024, 390×844 và 320×700.
- Sidebar/drawer, header dataset selector, welcome screen, composer, history, upload dialog, message bubbles và loading/error states hoạt động đúng; Enter gửi, Shift+Enter xuống dòng, textarea tự mở rộng và giới hạn 2.000 ký tự.
- Evidence mặc định đóng; toolbar có **Bảng dữ liệu**, **SQL**, **Nguồn tham khảo**; desktop gọn một hàng, mobile wrap không tràn; mỗi message giữ state riêng và chỉ một panel mở tại một thời điểm. SQL copy, rows và citations vẫn còn đầy đủ.
- Không có JavaScript runtime error, page error, request failure hoặc HTTP error ngoài các ca mock chủ đích.
- Screenshots thật đã xem tại `frontend/test-results/**/` gồm `sql-result-expanded.png`, `hybrid-sources-expanded.png`, `mobile-evidence-toolbar.png`, `mobile-sql-table-expanded.png` và `live-conversation.png`. Đây là artifact local bị Git ignore, không commit vào repository.

## H. GitHub

- Source baseline `5f5d8e35085b3f3d0adecd40b15281e59aa8f23a` đã có trên `origin/main`.
- GitHub Actions workflow `CI`, run `38544607455`, trạng thái `completed/success` cho baseline.
- Commit tài liệu cuối của audit được push và xác minh CI sau khi tạo báo cáo; SHA cuối cùng và run tương ứng được ghi trong kết quả bàn giao vì file không thể tự chứa SHA của chính commit tạo ra nó.

## I. Remaining Issues

### Blocking issues

- Không có.

### Non-blocking warnings

- Starlette `TestClient` deprecation warning từ dependency.
- Gemini free-tier có thể trả 429; SDK retry hữu hạn cho lỗi tạm thời và API trả lỗi rõ ràng khi hết retry.
- Host port 8000 có thể bị process local chiếm; lần audit này API container ánh xạ tạm sang 8001, còn Nginx nội bộ vẫn kết nối `api:8000` và hoạt động bình thường.

### Known MVP limitations

- Chưa có authentication/tenant isolation/rate limiting/antivirus và chưa sẵn sàng public Internet.
- Mỗi upload chỉ hỗ trợ một bảng hoặc một sheet, không join nhiều datasets và không dùng RAG/Hybrid của corpus demo.
- Không có endpoint xóa dataset; live LLM vẫn phụ thuộc API key, quota và khả dụng upstream.

**PROJECT COMPLETE — SHOPQUERY AI.**
