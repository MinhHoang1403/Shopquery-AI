> HISTORICAL snapshot. Current architecture/status: [Stage 1 report](../../stage1_implementation_report.md).

# Báo cáo độ tin cậy hệ thống ShopQuery AI

Ngày kiểm tra: 2026-10-16 (Asia/Saigon)

Workspace: `C:\Work\ShopQuery AI`

Baseline: nhánh `main`, commit `95f744948b245fa252d7ca824bf2769268b2db8d`

## A. Môi trường và Git

- ShopQuery AI chạy tại Nginx `127.0.0.1:8080`, API container được ánh xạ cục bộ sang `127.0.0.1:8001`, PostgreSQL sang `127.0.0.1:54321`; kết nối nội bộ Nginx vẫn là `api:8000`.
- ReconEngine đang dùng host ports 5173/8000 và không bị dừng hoặc chỉnh sửa.
- Ba service `db`, `api`, `web` healthy; Compose config, Docker build API/web, Nginx config, PostgreSQL readiness, API health và web HTTP 200 đều đạt.
- Working tree ban đầu sạch. `.env`, API key, virtual environment, cache và artifact không được đưa vào Git.

## B. Lỗi SQL trả NULL

### Tái hiện và ground truth

- Dataset: `shopquery_don_hang_thu_nghiem`, 120 dòng, bảng vật lý `uploaded_data.dataset_f349728215f144d69976f1d658f077fb`.
- SQL gây lỗi đã lưu trong conversation dùng `khu_vuc = 'Miền Bắc'`; dữ liệu thật chỉ có `Bắc`, `Trung`, `Nam`, nên `SUM(thanh_tien_vnd)` trả `NULL` vì không có dòng khớp.
- Ground truth độc lập từ CSV nguồn và PostgreSQL: 31 đơn có `trang_thai = 'Hoàn thành'` và `khu_vuc = 'Bắc'`; không có giá trị NULL/zero ở cột cần cộng; tổng là `32.465.000`.

### Root cause và bản sửa

`backend/app/datasets/context.py` trước đây chỉ cung cấp tên/kiểu cột. Gemini đã dịch cách nói “miền Bắc” thành literal không tồn tại `Miền Bắc`. PostgreSQL và import không sai; `NULL` là triệu chứng của bộ lọc sai.

- `backend/app/datasets/repository.py`: đọc riêng từng dataset bằng role read-only và chỉ trả giá trị TEXT có cardinality thấp, tối đa 20 giá trị/cột và 80 ký tự/giá trị.
- `backend/app/datasets/context.py`, `backend/app/api/routes.py`: đưa các giá trị thật có giới hạn vào context của đúng dataset; cell được đánh dấu là dữ liệu, không phải instruction.
- `backend/app/text_to_sql/generator.py`: cấm tự thêm filter không được hỏi; yêu cầu `matched_row_count` cho SUM/AVG cần phân biệt dữ liệu thiếu.
- Prompt giới hạn alias `matched_row_count` cho `COUNT(*)` bổ trợ, không dùng alias này cho SUM/AVG hoặc business metric trong bảng evidence.
- `backend/app/text_to_sql/pipeline.py`: grounding phân biệt tập rỗng, không có dòng khớp, có dòng nhưng toàn NULL và tổng thực sự bằng 0.

Sau sửa, live `/api/chat` sinh điều kiện `khu_vuc = 'Bắc'`, trả `total_thanh_tien = 32465000`, `matched_row_count = 31` và câu trả lời đúng. Dataset isolation vẫn được SQLGlot và allowlist theo request bảo vệ.

## C. Lỗi XLSX

### Tái hiện và root cause

- File thật: `shopquery_ton_kho_thu_nghiem.xlsx`, hai sheet `Ton_kho` và `Nhap_kho`.
- Trước sửa, `POST /api/datasets/preview` qua Nginx trả HTTP 500.
- Workbook hợp lệ nhưng XML worksheet không có thẻ `<dimension>`. Với openpyxl read-only, `worksheet.max_column` là `None`; phép so sánh với giới hạn cột gây `TypeError` sau khi workbook đã mở.

### Bản sửa và kết quả

- `backend/app/datasets/parser.py` gọi `calculate_dimension(force=True)`, phân tích biên bằng `range_boundaries`, chuẩn hóa ô chỉ có ngày thành `date`, và chuyển XML worksheet hỏng thành lỗi validation 422 rõ ràng.
- Preview file thật: `Ton_kho` 60 dòng × 8 cột; `Nhap_kho` 28 dòng × 6 cột; chọn sheet hoạt động.
- Import trên database tạm: cả hai sheet thành công. Ground truth: tổng tồn hiện tại `2.229`, 20 dòng dưới tồn tối thiểu; tổng số lượng nhập `732`.
- Live API và Chromium qua Vite proxy tạm cùng đạt; câu hỏi trên sheet `Nhap_kho` trả `732` từ 28 dòng.
- Duplicate dataset trả 409; sheet không tồn tại, archive giả và XML hỏng trả 422; không tạo metadata/bảng mồ côi.

## D. Đánh giá logic và AI

### Ma trận xác định

95 test được thu thập: 81 unit/API/parser/security và 14 PostgreSQL integration. Bảng dưới liệt kê 30 nhóm ca đại diện; tất cả đều pass và không dùng output Gemini làm expected result.

| # | Ca xác định | Lớp kiểm tra | Kết quả |
| ---: | --- | --- | --- |
| 1 | CSV UTF-8 BOM, Unicode, mã có số 0 đầu | Parser | Pass |
| 2 | CSV header rỗng/trùng, sai số cột, encoding sai | Parser | Pass |
| 3 | CSV giới hạn byte/dòng/cột | Parser | Pass |
| 4 | CSV delimiter trong quote, số âm, cell giống prompt | Parser | Pass |
| 5 | CSV formula-like và mixed type không bị thực thi | Parser | Pass |
| 6 | XLSX nhiều sheet và chọn sheet | Parser/API | Pass |
| 7 | XLSX thiếu dimension metadata | Parser/API/file thật | Pass |
| 8 | XLSX date/datetime/boolean/decimal/blank/mixed | Parser | Pass |
| 9 | XLSX header rỗng/trùng và giới hạn | Parser | Pass |
| 10 | XLSX XML hỏng/archive giả/unknown sheet | Parser/API | Pass |
| 11 | Import transaction rollback và duplicate name | PostgreSQL | Pass |
| 12 | CSV/XLSX metadata, preview và SQL sau import | PostgreSQL | Pass |
| 13 | Dataset A không thấy categorical value của B | PostgreSQL | Pass |
| 14 | Dataset SQL không truy cập public/dataset khác | SQL security | Pass |
| 15 | Role read-only từ chối ghi | PostgreSQL | Pass |
| 16 | DDL/DML, multi-statement, catalog, subquery, sleep bị chặn | SQL security | Pass |
| 17 | Row limit và statement timeout contract | Executor | Pass |
| 18 | SUM có dòng hợp lệ | PostgreSQL | Pass |
| 19 | SUM không có dòng khớp | PostgreSQL/grounding | Pass |
| 20 | SUM có dòng nhưng toàn NULL | PostgreSQL/grounding | Pass |
| 21 | Tổng thực sự bằng zero | PostgreSQL/grounding | Pass |
| 22 | Số lớn, ngày, Unicode và nhiều nhóm | Grounding | Pass |
| 23 | Router SQL/RAG/HYBRID/UNSUPPORTED | Unit | Pass |
| 24 | RAG chỉ giữ chunk ID đã truy hồi | Unit | Pass |
| 25 | Hybrid dùng cả SQL rows và policy citation | Unit | Pass |
| 26 | Hybrid không suy danh mục từ tên sản phẩm | Prompt/unit | Pass |
| 27 | Gemini 503 retry rồi thành công | Unit | Pass |
| 28 | Gemini 503 hết retry và không tạo kết quả | Unit/API | Pass |
| 29 | Lỗi authentication không retry | Unit | Pass |
| 30 | Conversation persist/rename/isolate/delete | PostgreSQL/API | Pass |

### Live Gemini có kiểm soát

11 luồng đại diện được chạy trong đợt này; request được giãn theo quota. Ba luồng upload ghi dữ liệu chỉ chạy trên database tạm đã xóa. Tám luồng stateless còn lại đi qua `http://127.0.0.1:8080/api/chat` và không ghi database chính.

| ID | Câu hỏi | Route kỳ vọng/thực tế | SQL/evidence chính | Ground truth và rows | Kết quả |
| --- | --- | --- | --- | --- | --- |
| CSV-TEMP-01 | Tổng thành tiền đơn hoàn thành ở miền Bắc? | SQL/SQL | `SUM(thanh_tien_vnd)`, `Bắc`, `Hoàn thành` | `32.465.000`; 31 dòng | Pass |
| XLSX-01 | Tổng tồn hiện tại là bao nhiêu? | SQL/SQL | `SUM(ton_hien_tai)`, `COUNT(*)` | `2.229`; 60 dòng | Pass |
| XLSX-UI-01 | Tổng số lượng nhập là bao nhiêu? | SQL/SQL | `SUM(so_luong_nhap)`, `COUNT(*)` | `732`; 28 dòng | Pass |
| SQL-01 | Top 5 bán chạy tháng 9/2025 | SQL/SQL | completed, khoảng ngày tháng 9, SUM quantity | `15,14,11,11,10`; đúng tập 5 sản phẩm | Pass |
| SQL-02 | Doanh thu completed tháng 9/2025 | SQL/SQL | SUM `quantity × unit_price`, count 144 dòng hàng | `7.800.668.000` | Pass |
| SQL-03 | Có bao nhiêu đơn completed? | SQL/SQL | `COUNT(*)`, status completed | `1.435` | Pass |
| RAG-01 | Chính sách đổi trả | RAG/RAG | chunks 304/310/312 | 14 ngày; citation tồn tại | Pass |
| RAG-02 | Điện thoại bảo hành bao lâu? | RAG/RAG | chunks 322/306 | PHONE 24 tháng; citation tồn tại | Pass |
| HYBRID-01 | Top 5 bán chạy có miễn phí vận chuyển? | HYBRID/HYBRID | 5 SQL rows + chunks 303/315/316 | Chỉ `LAPTOP` trong top 5 được miễn phí | Pass |
| UNSUPPORTED-01 | Thời tiết Đà Nẵng hôm nay? | UNSUPPORTED/UNSUPPORTED | Không SQL/rows/sources | Từ chối đúng phạm vi | Pass |
| CSV-MAIN-01 | Chạy lại câu hỏi miền Bắc qua Nginx trên dataset hiện có | SQL/SQL | Đúng bảng vật lý, `Bắc`, `Hoàn thành` | `32.465.000`; 31 dòng | Pass |

Không có 429, 503, schema error, citation giả hoặc câu trả lời bịa trong 11 ca. Hai sản phẩm cùng quantity 11 và hai sản phẩm cùng quantity 84 có thể đổi thứ tự nội bộ vì generated SQL chỉ sắp xếp theo aggregate; tập kết quả và kết luận không đổi.

Lần chạy SQL-01 đầu tiên trả đúng số nhưng đặt alias `matched_row_count` cho `SUM(quantity)`. Đây là lỗi tên evidence, không phải lỗi ground truth. Prompt đã được siết để alias đó chỉ dành cho `COUNT(*)` bổ trợ; lần chạy lại qua Nginx trả `SUM(quantity) AS total_quantity`, route SQL, không lỗi và giữ nguyên ground truth `15,14,11,11,10`.

## E. Safe cleanup

| Thành phần | Bằng chứng | Quyết định |
| --- | --- | --- |
| Ruff/ESLint unused imports và variables | Hai linter pass toàn bộ source | Không có source cần xóa |
| `backend/scripts/*` | README, Docker startup và quy trình seed/ingest tham chiếu | Giữ |
| Dockerfiles, Compose, Nginx, CI | Build/config/health và workflow dùng trực tiếp | Giữ |
| Seed, policy Markdown, integration/security tests | Dùng cho ground truth, runtime ingestion và regression | Giữ |
| `frontend/e2e/debug-upload-live.spec.ts`, `frontend/vite.debug.config.ts` | Chỉ là harness tạm của lần test file thật | Đã xóa sau khi test |
| `frontend/test-results/debug-upload-live.png` và `.last-run.json` | Artifact tạm do lần debug này tạo, Git ignored | Xóa sau nghiệm thu local |
| `.env.compose-ui.yaml` | Override local để tránh host port 8000 của ReconEngine; Git ignored | Giữ local, không commit |
| `test-results/final-ui/*` | Bằng chứng visual từ nghiệm thu trước, không do lần debug này tạo | Giữ nguyên |

Không refactor kiến trúc và không xóa file được bảo vệ. Không thêm/nâng dependency; lockfiles không đổi.

## F. Full system testing

| Nhóm | Kết quả |
| --- | --- |
| Ruff | Pass |
| Pytest unit/API/parser/security | 81 pass, 0 fail |
| PostgreSQL integration | 14 pass, 0 fail; database tạm đã xóa |
| ESLint / TypeScript | Pass / Pass |
| Vitest | 13 pass, 0 fail |
| Frontend production build | Pass |
| Playwright mock | 20 pass, 0 fail, 5 viewport |
| Playwright live XLSX thật | 1 pass, 0 fail; Chromium, không console/request error |
| Docker build | API và web pass |
| Compose/Nginx/health | Pass; db/api/web healthy |

Pytest còn một `StarletteDeprecationWarning` từ dependency TestClient; không ảnh hưởng kết quả và không nâng dependency ngoài phạm vi để loại cảnh báo.

## G. Toàn vẹn dữ liệu và bảo mật

Trước và sau nhiệm vụ, database chính giữ nguyên: 8 categories, 150 products, 2.000 orders, 4.019 order items, 25 document chunks, 10 conversations, 64 messages, 2 datasets và 2 dataset tables. Không còn database tên `shopquery_debug_*`.

SQL AST validation, table/column/schema allowlist, read-only role, statement timeout và row limit không bị nới lỏng. Không reset seed, không xóa conversation/dataset, không xóa volume và không chạy `docker compose down -v`. Secret scan trước commit phải xác nhận `.env` và key không được stage.

## H. GitHub

Các file source/test/docs của nhiệm vụ sẽ được commit trên `main`, push không force lên `origin/main`, sau đó đối chiếu local/remote SHA và GitHub Actions. SHA/run cuối được ghi trong bàn giao vì tài liệu không thể tự chứa SHA của commit tạo ra chính nó.

## I. Vấn đề còn lại

### Blocking

- Chưa có tại thời điểm hoàn tất local verification.

### Non-blocking

- Cảnh báo deprecation của Starlette TestClient từ dependency.
- Gemini free tier vẫn có thể trả 429/5xx trong tương lai; SDK retry hữu hạn và API trả lỗi rõ ràng, không tạo kết quả giả.
- Thứ tự giữa các hàng đồng hạng không được bảo đảm nếu model không thêm tie-breaker; dữ liệu/tập top-N vẫn đúng trong các ca đã kiểm tra.

### Giới hạn MVP đã biết

- Chưa có authentication, tenant isolation, antivirus, rate limiting hoặc secret manager production; không nên mở công khai trên Internet.
- Mỗi upload là một bảng/một sheet, không join nhiều dataset và không ghép RAG/Hybrid corpus demo vào dataset upload.
- Không có endpoint xóa dataset; live LLM phụ thuộc API key, quota và availability upstream.
