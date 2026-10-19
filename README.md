# ShopQuery AI

[![CI](https://github.com/MinhHoang1403/Shopquery-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/MinhHoang1403/Shopquery-AI/actions/workflows/ci.yml)

ShopQuery AI là trợ lý phân tích bảng dữ liệu và tài liệu đa lĩnh vực, từ bán hàng đến học phí, nhân sự và vận hành. React, FastAPI, iNetCloud Knowledge/Gemini và PostgreSQL/pgvector hỗ trợ SQL, RAG và Hybrid; đây chưa phải dịch vụ production công khai.

## Authentication & multi-user — thay đổi cần đọc trước khi chạy

Mở website là thấy chatbot Guest; Google login là tùy chọn để sử dụng không gian cá nhân lưu lâu dài. API dữ liệu/model cũ vẫn yêu cầu Google OIDC invite-only, PostgreSQL sessions, CSRF và ownership. Guest chỉ dùng namespace `/api/guest/*`, không được đọc history/datasets cá nhân. Logout thành công quay về Guest trống; lỗi logout không được coi là đã revoke session.

**Main local 8080 đã có Guest upload tạm và database authentication riêng, giữ nguyên tài khoản Google hiện có.** Người dùng đã xác nhận đăng nhập Google thành công trước đợt Guest. Không reset database hoặc tự gán dữ liệu cũ cho người đăng nhập đầu tiên. Volume cũ và backups vẫn được giữ.

Xem [báo cáo ổn định mới nhất](docs/regression_stabilization.md), [báo cáo Guest Mode trước ổn định](docs/guest_mode.md), [checkpoint nâng cấp auth trước đó](docs/main_auth_upgrade.md). Cài mới mặc định tắt `BETA_PROVIDER_DATA_ENABLED` và `GUEST_AI_ENABLED`. **Main local 8080 ngày 19-10-2026 đã bật cả hai theo yêu cầu chủ hệ thống:** dùng được AI/embedding cho Guest và tài khoản; không tự bật Gemini fallback. Knowledge/Gemini SQL/RAG/Hybrid đã kiểm thử live với dữ liệu giả lập. Chỉ tải dữ liệu được phép gửi cho các provider. Khi tắt gate, Guest vẫn parse/xem trước 6 định dạng; lưu tài liệu RAG vào tài khoản cần embedding nên trả 403 rõ ràng.

Guest mặc định có 5 câu hỏi/phiên, 8 tệp × tối đa 5 MiB, 5.000 dòng/30 cột và TTL 10 phút. RAM ước tính cho dữ liệu parse tối đa 32 MiB/phiên, 128 MiB toàn hệ thống; tối đa 32 chunks/phiên. Không đảm bảo mọi tổ hợp 8 tệp lớn đều vừa RAM. Preview và commit có quota riêng: xử lý tệp 180 lượt/IP/giờ và 40 lượt/phiên (tính cả parse khi commit); thêm tệp 60 lượt/IP/giờ. Chat nằm trong memory của trang; refresh không khôi phục. Backend dọn bằng reset best-effort và TTL định kỳ, không phụ thuộc riêng unload. SQL dùng PostgreSQL TEMP trên connection riêng; RAG dùng chunks/vectors trong RAM, không ghi vào corpus/lịch sử cá nhân. TEMP có thể dùng disk nội bộ PostgreSQL; không hứa forensic zero-copy. Local chỉ chạy một API worker.

Ô nhập chat vẫn chỉnh sửa được khi AI bị tắt, hết lượt hoặc chưa có dataset; thao tác gửi giải thích nguyên nhân và giữ draft, không tạo câu trả lời giả. Upload đã đăng nhập mặc định 60 lượt ghi/giờ, preview riêng 180 lượt/giờ; vẫn giữ CSRF, owner scope, giới hạn workspace/dung lượng và provider gate. UI đọc hạn mức upload từ backend. Giá trị trong `.env` cũ có thể ghi đè mặc định mới.

Compose chỉ tin IP forwarded từ dịch vụ `web` được cấu hình; Nginx ghi đè header client, không chấp nhận IP tùy ý từ Internet/direct API. Docker Desktop/NAT vẫn có thể gom nhiều trình duyệt vào cùng client IP; các giới hạn phiên và toàn hệ thống vẫn áp dụng, IP không phải danh tính người dùng. Xem [báo cáo ổn định regression](docs/regression_stabilization.md) để phân biệt test mock, live và hạng mục chưa nghiệm thu.

Upload qua Nginx đã sửa giới hạn mặc định 1 MB: proxy nhận tối đa 11 MB để đủ multipart cho file tài khoản 10 MB; backend vẫn áp dụng cap riêng. Không vượt quota bằng cách refresh; preview/import đều tính request upload.

Đọc [hướng dẫn authentication, cấu hình và migration](docs/authentication.md) trước mọi lệnh setup/seed bên dưới. Các bảng kết quả live ở phần tiếp theo là bằng chứng lịch sử trước auth, không phải kết quả live mới của bản multi-user. Không seed/ingest lại database cũ chỉ để bật auth.

## Kết quả lịch sử trước authentication — 19/10/2026

Các kết quả dưới đây được ghi nhận trước nâng cấp authentication, khi database còn chứa demo. **Không phải kết quả live của bản main sạch hiện tại.** Chưa nghiệm thu production công khai.

| Chức năng | iNetCloud Knowledge | Gemini |
| --- | --- | --- |
| SQL top 5 tháng 9/2025 | Pass: 5 dòng khớp PostgreSQL, đúng giờ Việt Nam | Pass: cùng kết quả đối chứng |
| RAG chính sách đổi trả | Pass: 3 nguồn thật, thời hạn 14 ngày | Pass: 3 nguồn thật, thời hạn 14 ngày |
| Hybrid top 5 + vận chuyển | Pass: 5 SQL rows + 3 nguồn | Pass: 5 SQL rows + 3 nguồn |
| Lưu và khôi phục lịch sử | Pass: 6 tin nhắn, đúng model và evidence | Pass: 6 tin nhắn, đúng model và evidence |

Không ghi nhận lỗi API/console hoặc nguồn giả trong 6 lượt này. [CI baseline đã xác minh](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39189762428): Ruff pass, 147 backend unit tests, 57 PostgreSQL integration tests (không skip), 24 frontend tests; ESLint/typecheck/build pass. Live AI không chạy trong CI.

Xem [báo cáo nghiệm thu cuối](docs/final_audit_report.md) để biết câu hỏi, số liệu đối chứng, thời gian, cách kiểm tra lịch sử và giới hạn. Đây là smoke trên dữ liệu mẫu, không bảo đảm mọi câu hỏi/dataset đều đúng hoặc upstream luôn khả dụng.

## Chức năng

- **Text-to-SQL (`SQL`)**: tạo câu `SELECT`, kiểm tra AST bằng SQLGlot và thực thi bằng PostgreSQL role chỉ đọc. Ví dụ: “Top 5 sản phẩm bán chạy nhất tháng 9/2025 là gì?”
- **Múi giờ bán hàng**: SQL dùng `Asia/Ho_Chi_Minh` trong transaction cho cả Knowledge, Gemini và Hybrid; lọc tháng theo biên `[đầu tháng, đầu tháng kế tiếp)` giờ Việt Nam, không đổi timezone toàn database.
- **RAG (`RAG`)**: tạo embedding cho câu hỏi, truy hồi các đoạn tài liệu gần nhất bằng pgvector rồi trả lời kèm nguồn. Ví dụ: “Chính sách đổi trả của cửa hàng như thế nào?”
- **Kết hợp (`HYBRID`)**: dùng cả kết quả SQL và bằng chứng tài liệu. Ví dụ: “Top 5 sản phẩm bán chạy nhất có thuộc danh mục được miễn phí vận chuyển không?”
- **Ngoài phạm vi (`UNSUPPORTED`)**: từ chối câu hỏi không thuộc dữ liệu và tài liệu của cửa hàng. Ví dụ: “Thời tiết Hà Nội hôm nay thế nào?”
- **Lịch sử hội thoại**: lưu conversation và từng message trong PostgreSQL; hỗ trợ tạo mới, chuyển, đổi tên, xóa và khôi phục sau khi tải lại trang.
- **Dataset workspace**: tạo bộ dữ liệu rỗng, thêm nhiều bảng CSV/XLSX và nhiều tài liệu PDF/DOCX/TXT/MD, sau đó dùng SQL, RAG hoặc Hybrid trong đúng workspace đã chọn.
- **Workspace đa lĩnh vực**: prompt dựa trên schema/tài liệu được chọn, không ép bảng upload theo mô hình bán hàng. Đã kiểm tra dữ liệu giả lập về doanh thu, học phí, giờ làm, vận tải và điện năng với cả Knowledge/Gemini; xem [báo cáo đa lĩnh vực](docs/multidomain_evaluation.md). Mỗi truy vấn upload vẫn chỉ dùng một bảng, chưa JOIN; quyền truy cập được lọc theo owner ở backend.
- **Giao diện responsive**: light theme, sidebar thu gọn/off-canvas, composer đa dòng và evidence toolbar gọn với các nút **Bảng dữ liệu**, **SQL** và **Nguồn tham khảo**; mỗi lần chỉ mở một panel.

## Công nghệ

| Thành phần | Công nghệ |
| --- | --- |
| Giao diện | React 19, TypeScript, Vite |
| API | FastAPI, Pydantic, Uvicorn |
| AI | iNetCloud Knowledge qua LangChain ChatOpenAI; Gemini qua Google GenAI SDK |
| Truy vấn | SQLGlot, SQLAlchemy, Psycopg |
| Dữ liệu | PostgreSQL 17, pgvector |
| Triển khai local | Nginx, Docker, Docker Compose |
| Chất lượng | Ruff, Pytest, ESLint, Vitest, Playwright, GitHub Actions |

## Kiến trúc

```text
Browser
  -> Nginx
    -> FastAPI
      +-> Conversations/Dataset workspaces -> PostgreSQL metadata + uploaded_data
      +-> Document ingestion -> bounded parser -> Gemini Embedding -> pgvector
      -> Model selection: Knowledge (default) / Gemini (manual)
        -> Router -> SQL / RAG / HYBRID / UNSUPPORTED
        +-> SQL ------> selected generation -> SQLGlot -> PostgreSQL read-only
        +-> RAG ------> Gemini Embedding -> pgvector -> selected generation
        +-> HYBRID ---> SQL + RAG -> selected generation
        +-> UNSUPPORTED
        -> Optional whole-turn fallback: Knowledge -> Gemini
```

Nginx phục vụ React SPA và chuyển tiếp nguyên đường dẫn `/api` đến FastAPI. Router dùng structured output và chỉ được chọn những nhánh mà workspace thực sự hỗ trợ: chỉ bảng có SQL, chỉ tài liệu có RAG, cả hai có thêm Hybrid. SQL allowlist và điều kiện RAG `dataset_id` đều được áp dụng ở backend theo từng request. Default corpus dùng `dataset_id = NULL` và không được dùng để bù cho tài liệu thiếu trong workspace upload. Frontend không giữ Gemini API key.

## Yêu cầu môi trường

### Chạy hoàn toàn bằng Docker

- Git.
- Docker Desktop có Docker Compose.
- Địa chỉ HTTPS Knowledge do công ty cung cấp nếu dùng Knowledge; Gemini API key cho Gemini generation, embedding và ingestion. Muốn kiểm tra đủ cả hai model cùng SQL/RAG/Hybrid cần cấu hình cả hai.

Python, Node.js, PostgreSQL và Nginx được cung cấp trong container nên không cần cài riêng trên Windows.

### Phát triển native

- Python 3.11; dự án khai báo `>=3.11,<3.13` nhưng kiểm thử và Docker dùng Python 3.11.
- `uv` là công cụ Python được ưu tiên; `pip` là phương án thay thế cho runtime.
- Node.js 24 và npm để chạy frontend.
- Docker Desktop/Compose để chạy PostgreSQL có pgvector.
- Địa chỉ Knowledge do công ty cung cấp; Gemini API key cho Gemini generation, embedding, ingestion và các live tests tương ứng.

## Clone repository

```powershell
git clone https://github.com/MinhHoang1403/Shopquery-AI.git
Set-Location Shopquery-AI
```

Mọi lệnh không ghi thư mục khác đều được chạy từ thư mục gốc repository.

## Cấu hình môi trường

Tạo file cấu hình local:

```powershell
Copy-Item .env.example .env
notepad .env
```

Điền `INETCLOUD_BASE_URL` bằng địa chỉ HTTPS do công ty cung cấp trong `.env` local. Điền `GEMINI_API_KEY` để dùng Gemini thủ công, embedding hoặc fallback được bật. SQL-only bằng Knowledge không cần Gemini key. Không commit `.env` và không đưa key vào frontend hoặc GitHub Actions.

Các biến chính:

| Biến | Vai trò |
| --- | --- |
| `AI_DEFAULT_MODEL` | `inetcloud-knowledge` (mặc định) hoặc `gemini` |
| `INETCLOUD_BASE_URL` | Base URL HTTPS Chat Completions của công ty; chỉ cấu hình local |
| `INETCLOUD_MODEL` | Model gửi provider, bắt buộc `knowledge` |
| `INETCLOUD_TIMEOUT_SECONDS` | Timeout hữu hạn mỗi lần gọi, mặc định 60 giây |
| `INETCLOUD_RETRY_ATTEMPTS` | Tổng số lần thử SDK, 1–3, mặc định 1 |
| `AI_GEMINI_FALLBACK_ENABLED` | Mặc định `false`; cho phép fallback generation tới Google |
| `GEMINI_API_KEY` | Xác thực Google Gemini; không có giá trị mặc định |
| `GEMINI_GENERATION_MODEL` | Model generation/router, mặc định `gemini-3.5-flash-lite` |
| `GEMINI_EMBEDDING_MODEL` | Bắt buộc `gemini-embedding-2` |
| `EMBEDDING_DIMENSIONS` | Bắt buộc 768 chiều |
| `GEMINI_REQUEST_TIMEOUT_MS` | Timeout mỗi request Gemini, mặc định 30.000 ms |
| `GEMINI_RETRY_ATTEMPTS` | Tổng số lần thử có giới hạn cho lỗi tạm thời, mặc định 3 |
| `DATABASE_SETUP_URL` | Kết nối có quyền tạo schema và nạp dữ liệu khi chạy native |
| `DATABASE_READONLY_URL` | Kết nối chỉ đọc cho SQL do model sinh khi chạy native |
| `CORS_ORIGINS` | Danh sách JSON các origin được phép gọi API trực tiếp |
| `DEMO_REFERENCE_DATE` | Ngày tham chiếu ổn định cho dữ liệu demo |

Compose tự dùng hostname `db` cho các container. Các URL mặc định trong `.env.example` dùng `127.0.0.1:54321` cho backend chạy native.

Trong composer, chọn **iNetCloud Knowledge** hoặc **Gemini** trước khi gửi. Lựa chọn được lưu theo conversation; đổi model không sửa nhãn câu trả lời cũ. Mỗi response ghi `requested_model`, `used_model`, `fallback_used` và `fallback_reason`. Conversation cũ chưa có preference được hiểu là Gemini; New Chat dùng default cấu hình.

Knowledge không yêu cầu key. `ChatOpenAI` dùng placeholder công khai `not-required` để đáp ứng constructor của SDK; đây không phải credential và server đã được probe chấp nhận Bearer header này. Generation dùng Chat Completions và JSON Schema đã kiểm chứng, không dùng tool calling hay Responses API. Structured output sai được thử tối đa hai lượt, không sửa JSON hoặc bỏ SQL validation.

Fallback chỉ chạy lại toàn bộ lượt chat một lần khi Knowledge lỗi mạng/timeout, HTTP 408/429/500/502/503/504 hoặc structured output hết giới hạn. Lỗi cấu hình 400/401/403/404, SQL validation/execution, không có tài liệu và citation sai không kích hoạt fallback. Nếu Gemini cũng lỗi, response trả lỗi và không tạo đáp án giả.

Chỉ bật `AI_GEMINI_FALLBACK_ENABLED=true` khi được phép gửi câu hỏi, schema, giá trị phân loại, SQL rows và document chunks tới Google. Tắt fallback generation không tắt Gemini Embedding: RAG và ingestion vẫn gửi dữ liệu embedding tới Google như trước. Không dùng dữ liệu công ty chưa được phép cho các live test.

Chi tiết API, giới hạn và cách kiểm thử: [Multi-model integration](docs/multi_model_integration.md).

## Khởi động nhanh bằng Docker Compose

### Thiết lập lần đầu

Chỉ áp dụng cho database mới hoàn toàn. Database hiện hữu phải theo [quy trình migration](docs/authentication.md), không chạy seed/ingest lại. Cấu hình Google OAuth, allowlist và provider permission trong `.env` trước khi nghiệm thu đăng nhập:

```powershell
docker compose up -d --build
docker compose ps
docker compose exec api python scripts/setup_database.py --confirm-database shopquery --fresh
```

Chờ ba service `db`, `api`, `web` healthy rồi mở `http://127.0.0.1:8080`. API trực tiếp ở `http://127.0.0.1:8000` và PostgreSQL ở `127.0.0.1:54321`. Nếu cổng host 8000 đang bị chiếm, có thể đổi riêng ánh xạ host của service `api`; kết nối nội bộ Nginx vẫn luôn dùng `api:8000`.

Đây là cổng **mặc định của repository**. Môi trường nghiệm thu dùng override local API 8001 và PostgreSQL 15432, web vẫn 8080; không cần sao chép override đó trên máy mới. Khi đổi cổng host PostgreSQL, cập nhật hai database URL cho backend native/test; URL giữa các container vẫn dùng `db:5432`.

API không tự setup/migration khi khởi động hoặc nhận request. `--fresh` chỉ khởi tạo database chưa có bảng ứng dụng, thêm final ownership constraints và version marker, không tạo user giả. Cài mới thành công có thể chạy lại mà không xoá dữ liệu; schema cũ bị từ chối. Lệnh không có `--fresh` vẫn là expansion cho quy trình legacy, không thay thế migration ownership.

Ở máy nghiệm thu hiện tại phải dùng cùng hai Compose files trong mọi lệnh vận hành, để giữ đúng cổng và volume sạch đã chọn:

```powershell
docker compose -p shopquery-ai -f compose.yaml -f .env.compose-ui.yaml up -d
```

File override local này không chứa secrets và không commit. Không chạy base Compose một mình trên máy này: mặc định vẫn tham chiếu volume cũ. Máy cài mới không cần sao chép override; có thể chọn volume bằng `POSTGRES_VOLUME_NAME` trước khi khởi tạo. Không đổi volume trên database đang dùng nếu chưa backup và kiểm tra target.

Với database legacy quan trọng cần backup, restore rehearsal và xác nhận owner trước mọi thay đổi. Ví dụ expansion sau khi được phép:

```powershell
cd backend
uv run python scripts/setup_database.py --confirm-database shopquery
```

`ingest_documents.py` gọi Gemini Embedding và có thể tiêu thụ quota. Chỉ cần ingest lần đầu hoặc khi tài liệu thay đổi; `content_hash` giúp bỏ qua các chunk không đổi.

### Những lần chạy sau

```powershell
docker compose up -d
docker compose ps
```

Không cần tạo schema, nạp seed hay ingest lại nếu volume và tài liệu không đổi. Dừng bình thường bằng:

```powershell
docker compose down
```

Volume `postgres_data` giữ dữ liệu. Không dùng `docker compose down -v` nếu muốn bảo toàn database.

### Kiểm tra sử dụng sau khi khởi động

Database mới không có demo: đăng nhập Google được mời, chọn **Thêm dữ liệu**, tạo workspace và preview/import CSV hoặc XLSX của bạn. Upload bảng không gọi AI; upload tài liệu cần embedding và bị chặn khi gate chưa được bật riêng. Chưa được phép gửi dữ liệu tới providers thì không chạy chat live. Các bước đối chứng sau **chỉ áp dụng môi trường demo riêng đã seed trước đây**, không phải main sạch:

1. Chọn **Dữ liệu cửa hàng mẫu**, tạo chat mới và chọn model trong composer.
2. Hỏi “Top 5 sản phẩm bán chạy nhất tháng 9/2025 là gì?”; mở bảng và SQL. Đối chứng mẫu: product IDs `10, 47, 120, 123, 135` với quantity `15, 14, 11, 11, 10`; hai sản phẩm quantity 11 có thể đổi thứ tự.
3. Hỏi “Chính sách đổi trả của cửa hàng như thế nào?”; mở nguồn để đối chiếu thời hạn 14 ngày.
4. Hỏi “Top 5 sản phẩm bán chạy nhất tháng 9/2025 có thuộc danh mục được miễn phí vận chuyển không?”; phải có cả bảng/SQL và nguồn. Trong top 5 này chỉ sản phẩm ID 10 thuộc `PHONE` được miễn phí tiêu chuẩn.
5. Đổi tên chat, tải lại trang và mở lại từ lịch sử; kiểm tra model, câu trả lời và bằng chứng vẫn còn. Lặp lại với model còn lại.

Các lượt này gọi dịch vụ AI thật và tiêu thụ quota. Kết quả đối chứng chỉ áp dụng seed/corpus mẫu chưa bị thay đổi, không áp dụng cho workspace upload. Kiểm tra `/api/health` chỉ chứng minh API sống; `/api/models` chỉ báo có cấu hình, không chứng minh provider đang hoạt động.

## Phát triển trên Windows

Không chạy đồng thời container `api` và FastAPI native trên cổng 8000. Nếu full stack Docker đang chạy, dừng hai service ứng dụng trước:

```powershell
docker compose stop web api
docker compose up -d db
```

### Terminal 1 — backend

```powershell
Set-Location backend
uv sync --locked --python 3.11
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Nếu đây là database mới, khởi tạo schema sạch trước lệnh Uvicorn (không seed/ingest):

```powershell
uv run python scripts/setup_database.py --confirm-database shopquery --fresh
```

### Terminal 2 — frontend

```powershell
Set-Location frontend
npm ci
npm run dev
```

Mở `http://127.0.0.1:5173`. Vite chuyển tiếp `/api` đến `http://127.0.0.1:8000`, nên backend phải chạy trước. Bản Docker qua Nginx vẫn dùng `http://127.0.0.1:8080`.

## Python virtual environment

Virtual environment (venv) cô lập Python và package của dự án khỏi Python toàn hệ thống. ShopQuery AI chỉ dùng `backend/.venv`.

### Cách ưu tiên: uv

```powershell
Set-Location backend
uv sync --locked --python 3.11
```

Lệnh này tái tạo `backend/.venv` từ `pyproject.toml` và `uv.lock`, gồm cả công cụ development. Không commit thư mục `.venv`.

### Phương án thay thế: pip

```powershell
py -3.11 -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r .\requirements.txt
```

`requirements.txt` chỉ chứa runtime dependencies được export từ `uv.lock`; nó không cài Ruff, Pytest hoặc frontend. Dùng `uv sync --locked --python 3.11` khi cần đầy đủ công cụ lint/test.

### Tự kích hoạt trong Antigravity/VS Code

Repository cấu hình `.vscode/settings.json` để chọn `backend/.venv/Scripts/python.exe`. Antigravity hiện không cung cấp các proposed terminal API mà Microsoft Python Environments cần để tự kích hoạt bằng chế độ `command`, nên workspace dùng profile `ShopQuery PowerShell` để chạy `Activate.ps1` khi tạo Terminal mới. Cấu hình này chỉ áp dụng cho repository, không sửa PowerShell `$PROFILE`, Registry hoặc ExecutionPolicy.

Sau khi chạy `uv sync`, đóng Terminal cũ rồi mở Terminal PowerShell mới. Kiểm tra:

```powershell
python -c "import sys; print(sys.executable); print(sys.version); print(sys.prefix != sys.base_prefix)"
```

Kết quả đúng phải trỏ đến `backend\.venv\Scripts\python.exe`, dùng Python 3.11 và dòng cuối là `True`. Nếu terminal không dùng profile mặc định của workspace, chạy **Terminal: Select Default Profile**, chọn `ShopQuery PowerShell`, rồi mở Terminal mới. Nếu IDE chưa chọn đúng interpreter, dùng **Python: Select Interpreter** và chọn file trên.

Kích hoạt thủ công từ thư mục gốc khi IDE không hỗ trợ:

```powershell
.\backend\.venv\Scripts\Activate.ps1
```

Thoát venv bằng `deactivate`. Docker không cần venv Windows vì Python và dependencies nằm trong image backend.

## Quản lý dependencies

- `backend/pyproject.toml`: khai báo direct dependencies và nhóm development.
- `backend/uv.lock`: khóa đầy đủ phiên bản Python; đây là nguồn để tái tạo môi trường backend.
- `requirements.txt`: export runtime có pinned versions và hashes từ `backend/uv.lock`, phục vụ `pip` từ thư mục gốc.
- `frontend/package.json` và `frontend/package-lock.json`: khai báo và khóa dependencies React/Node.js.
- `backend/Dockerfile`, `frontend/Dockerfile` và `compose.yaml`: định nghĩa môi trường container.

Một file `requirements.txt` không cài React, PostgreSQL, Nginx hoặc Docker. Khi dependencies backend thay đổi hợp lệ, cập nhật lockfile rồi export lại:

```powershell
Set-Location backend
uv export --locked --no-dev --no-emit-project --format requirements.txt --output-file ..\requirements.txt
```

## Kiểm thử

### Backend không gọi dịch vụ thật

```powershell
Set-Location backend
uv run ruff check app scripts tests
uv run pytest -m "not integration and not live"
```

### PostgreSQL integration trong database tách biệt

Khởi động `db`, tạo database test riêng rồi trỏ hai kết nối vào đó:

```powershell
docker compose up -d db
docker compose exec db psql -U shopquery_setup -d postgres -c "CREATE DATABASE shopquery_test_local OWNER shopquery_setup;"
Set-Location backend
$env:DATABASE_SETUP_URL = "postgresql+psycopg://shopquery_setup:setup_password@127.0.0.1:54321/shopquery_test_local"
$env:DATABASE_READONLY_URL = "postgresql+psycopg://shopquery_reader:readonly_password@127.0.0.1:54321/shopquery_test_local"
$env:SHOPQUERY_TEST_DATABASE_URL = $env:DATABASE_SETUP_URL
$env:RUN_DATABASE_TESTS = "1"
uv run pytest -m "integration and not live"
Remove-Item Env:DATABASE_SETUP_URL, Env:DATABASE_READONLY_URL, Env:SHOPQUERY_TEST_DATABASE_URL, Env:RUN_DATABASE_TESTS
Set-Location ..
docker compose exec db psql -U shopquery_setup -d postgres -c "DROP DATABASE shopquery_test_local;"
```

Không chạy integration tests với `shopquery` nếu cần giữ nguyên database chính. Test integration dùng embedding giả lập có tính quyết định, không phải kết quả Gemini thật.

GitHub CI chạy PostgreSQL 17/pgvector với database `shopquery_ci` riêng, `RUN_DATABASE_TESTS=1` và `SHOPQUERY_TEST_DATABASE_URL` khớp target. Ngoài regression múi giờ/upload/delete còn có session, CSRF, A/B isolation, quota và migration checks. Không cần Google hoặc AI credentials. Live tests không chạy trong CI; service database được hủy sau job, không kết nối database đang sử dụng của ứng dụng. Số test mới và giới hạn nghiệm thu ghi trong [báo cáo auth](docs/authentication.md).

### Frontend

```powershell
Set-Location frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

### Browser E2E

Mock E2E không gọi providers. Ưu tiên Vite riêng để không phụ thuộc session hoặc database của main:

```powershell
Set-Location frontend
npx playwright install chromium
$env:SHOPQUERY_E2E_START_SERVER = '1'
$env:SHOPQUERY_E2E_BASE_URL = 'http://127.0.0.1:5173'
npm run test:e2e
```

Mock E2E chạy ở năm viewport 1440, 1280, 768, 390 và 320 px. `npm run test:e2e:live` gọi API thật, database và Gemini cho dữ liệu cửa hàng mẫu.

`npm run test:e2e:workspace-live` kiểm tra qua giao diện việc tạo workspace, preview/import CSV và XLSX có chọn sheet, upload PDF/DOCX/TXT/MD, chat SQL/RAG/Hybrid và khôi phục hội thoại. Bắt buộc dùng database test riêng và API test, không trỏ bài này vào database `shopquery`:

```powershell
# Terminal frontend dev, API test đang chạy ở cổng 8002
$env:SHOPQUERY_API_PROXY_TARGET = "http://127.0.0.1:8002"
npm run dev -- --port 5174 --strictPort

# Terminal Playwright
$env:SHOPQUERY_LIVE_WORKSPACE = "1"
$env:SHOPQUERY_E2E_BASE_URL = "http://127.0.0.1:5174"
npm run test:e2e:workspace-live
```

Các live suite dùng quota của provider được chọn và Gemini Embedding khi có RAG/ingestion. Chỉ chạy khi API/database test tương ứng healthy. GitHub Actions có ba jobs: Ruff/backend unit, PostgreSQL integration trên database riêng và frontend quality; không nhận API key và không gọi live tests. Xem [workflow CI](.github/workflows/ci.yml).

### Docker Compose

```powershell
docker compose config --quiet
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-WebRequest http://127.0.0.1:8080/api/health -UseBasicParsing
```

## API

Ngoài health và OIDC login/callback, các API cần session cookie hợp lệ. Thiếu session trả 401; POST/PATCH/DELETE/upload cần Origin và X-CSRF-Token lấy từ `/api/auth/me`. Không chia sẻ cookie/token thật. Xem [auth contract](docs/authentication.md).

### `GET /api/health`

Kiểm tra liveness mà không gọi Gemini:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

### `POST /api/chat`

```powershell
$body = @{
  message = "Top 5 sản phẩm bán chạy nhất tháng 9/2025 là gì?"
  model_id = "gemini"
} | ConvertTo-Json
$utf8Body = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat `
  -ContentType "application/json; charset=utf-8" -Body $utf8Body
```

Response ổn định có dạng:

```json
{
  "answer": "...",
  "route": "SQL",
  "sql": "SELECT ...",
  "rows": [],
  "sources": [],
  "error": null,
  "requested_model": "gemini",
  "used_model": "gemini",
  "fallback_used": false,
  "fallback_reason": null
}
```

`route` là `SQL`, `RAG`, `HYBRID` hoặc `UNSUPPORTED`. `sql`/`rows` chỉ có dữ liệu cho SQL và Hybrid; `sources` chỉ có dữ liệu cho RAG và Hybrid. Với lỗi nghiệp vụ đã dự kiến, API hiện có thể trả HTTP 200 cùng `route: null` và nội dung trong trường `error`; client phải kiểm tra trường này.

`POST /api/chat` là API stateless, **không lưu lịch sử**. Bỏ `model_id` để dùng default hoặc chọn `inetcloud-knowledge`/`gemini`. Có thể truyền thêm `dataset_id`; router sẽ giới hạn route theo số bảng/tài liệu của workspace và không tự ghép corpus demo. Muốn lưu hỏi–đáp như giao diện, dùng Conversations API bên dưới.

### Conversations

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| `GET` | `/api/conversations?limit=50&offset=0` | Danh sách mới cập nhật trước |
| `POST` | `/api/conversations` | Tạo chat với JSON `{"dataset_id": null, "model_id": "gemini"}`; các field tùy chọn |
| `GET` | `/api/conversations/{id}` | Metadata và toàn bộ messages |
| `PATCH` | `/api/conversations/{id}` | Đổi tên và/hoặc model với JSON `{"title": "...", "model_id": "gemini"}` |
| `DELETE` | `/api/conversations/{id}` | Xóa conversation và messages liên quan |
| `POST` | `/api/conversations/{id}/messages` | Gửi JSON `{"message": "...", "model_id": "gemini"}` và lưu cả câu hỏi/câu trả lời; model tùy chọn |

Tiêu đề mặc định được thay bằng phần đầu câu hỏi đầu tiên, trừ khi người dùng đã đặt tên. Mỗi conversation gắn với đúng một dataset; muốn chuyển dataset, giao diện yêu cầu xác nhận và bắt đầu chat mới. Request đang chạy bị hủy khi người dùng đổi chat, nên response cũ không bị đưa vào chat mới.

### Datasets và upload

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| `GET` | `/api/datasets` | Dataset demo và các dataset đã import |
| `POST` | `/api/datasets` | Tạo workspace rỗng với JSON `{"name": "..."}` |
| `GET` | `/api/datasets/{id}` | Metadata cùng các dòng preview |
| `GET` | `/api/datasets/{id}/preview?limit=10` | Đọc tối đa 50 dòng bằng role chỉ đọc |
| `POST` | `/api/datasets/preview` | Multipart `file`, tùy chọn `sheet_name`; chưa ghi database |
| `POST` | `/api/datasets/import` | Multipart `file`, `dataset_name`, tùy chọn `sheet_name` |
| `GET` | `/api/datasets/{id}/tables` | Danh sách bảng của workspace |
| `POST` | `/api/datasets/{id}/tables/preview` | Preview CSV/XLSX trước khi thêm bảng |
| `POST` | `/api/datasets/{id}/tables/import` | Thêm bảng với `file`, `display_name`, `sheet_name` tùy chọn |
| `GET` | `/api/datasets/{id}/documents` | Danh sách tài liệu đã ingest |
| `POST` | `/api/datasets/{id}/documents` | Parse, chunk, embed và lưu tài liệu |
| `GET` | `/api/datasets/{id}/documents/{document_id}` | Metadata một tài liệu |
| `DELETE` | `/api/datasets/{id}/documents/{document_id}` | Xóa đúng tài liệu và chunks của nó |

Luồng giao diện: chọn **Quản lý dữ liệu** → **Tạo bộ dữ liệu mới** hoặc **Quản lý bộ hiện có**. Sau khi tạo workspace rỗng, có thể preview/thêm nhiều CSV/XLSX và ingest nhiều PDF/DOCX/TXT/MD. Bộ chọn trên header hiển thị gọn số bảng và tài liệu.

Trong **Quản lý bộ hiện có**, chọn đúng bộ rồi dùng nút thùng rác để xóa từng bảng hoặc tài liệu, hoặc **Xóa bộ dữ liệu** để xóa toàn bộ nguồn trong bộ đó. Mọi thao tác đều cần xác nhận và không thể hoàn tác từ giao diện; file gốc trên máy không bị xóa. Với XLSX, mỗi bảng là một sheet đã import, không tự xóa các sheet/bảng khác cùng tên file.

Xóa bảng sẽ xóa bảng vật lý và metadata; xóa tài liệu sẽ xóa cả chunks/embeddings. Lịch sử chat vẫn giữ kết quả/trích đoạn cũ khi chỉ xóa một nguồn. Nếu xóa cả bộ đã có chat, cần tích **Xóa cả lịch sử chat gắn với bộ dữ liệu này** hoặc xóa các chat đó trước; API trả `409` nếu chưa đồng ý. Không tự chuyển chat sang nguồn mặc định. Bộ cửa hàng mẫu không có thao tác xóa. Chỉ owner được quản lý nguồn; thiếu session trả 401, sai owner trả 404. Thao tác xoá không dùng AI/API key.

API quản lý xóa: `DELETE /api/datasets/{dataset_id}/tables/{table_id}`, `DELETE /api/datasets/{dataset_id}/documents/{document_id}` và `DELETE /api/datasets/{dataset_id}?delete_conversations=false` (chỉ đặt `true` khi đồng ý xóa chat liên quan). Các endpoint thành công trả `204`, nguồn không tồn tại/không thuộc bộ trả `404`. Xóa bộ/bảng dùng một PostgreSQL transaction, chỉ DROP bảng đăng ký trong `uploaded_data`, không dùng `DROP CASCADE` ([PostgreSQL dependency tracking](https://www.postgresql.org/docs/current/ddl-depend.html), [SQLAlchemy Table.drop](https://docs.sqlalchemy.org/en/20/core/metadata.html#sqlalchemy.schema.Table.drop)).

Chi tiết kiểm thử tự động, live UI và đối chiếu bảo toàn dữ liệu: [nghiệm thu chức năng xóa](docs/dataset_deletion.md).

Giới hạn bảng mặc định là 10 MB, 5.000 dòng và 30 cột. CSV phải là UTF-8/UTF-8 BOM. XLSX được đọc read-only, không hỗ trợ macro và không thực thi công thức. Mỗi lần import tạo một bảng; XLSX nhiều sheet yêu cầu chọn một sheet.

Tài liệu tối đa 10 MB; PDF tối đa 100 trang và phải có text layer. DOCX được kiểm tra số entry, tổng kích thước giải nén, tỷ lệ nén và đường dẫn archive. TXT/MD phải là UTF-8. Hệ thống không hỗ trợ OCR, PDF scan, DOC cũ, macro, URL ingestion hoặc ảnh. MVP chỉ lưu metadata, extracted text/chunks và embedding, không lưu binary gốc để tải lại. Nội dung tài liệu luôn được coi là dữ liệu không tin cậy. Nếu embedding 429/503, transaction không tạo metadata/chunks dở dang; hãy chờ quota/dịch vụ rồi tải lại.

Dữ liệu bảng nằm trong `uploaded_data` với tên vật lý ngẫu nhiên. Context chỉ đưa các bảng của workspace đang chọn vào allowlist. Trong bản này, mỗi SQL chỉ được tham chiếu đúng một bảng; mọi JOIN bị từ chối vì chưa có relationship metadata, kể cả khi tên cột giống nhau. RAG lọc `dataset_id` ngay trong truy vấn pgvector. Hybrid tái sử dụng SQL và RAG đã scope trong cùng workspace, không suy đoán thuộc tính hoặc nguồn thiếu.

## Cấu trúc dự án

```text
.
├── .github/workflows/ci.yml       # GitHub Actions
├── .vscode/                       # Interpreter và auto-activation portable
├── backend/
│   ├── app/
│   │   ├── ai/                    # Knowledge/Gemini adapters và fallback
│   │   ├── api/                   # FastAPI routes và contracts
│   │   ├── core/                  # Cấu hình, logging, errors
│   │   ├── conversations/         # Persistence lịch sử chat
│   │   ├── database/              # Models, session, schema, loader
│   │   ├── datasets/              # Parse, metadata, import và SQL context
│   │   ├── rag/                   # Chunking, pgvector, RAG
│   │   ├── routing/               # Router, Hybrid, chat service
│   │   └── text_to_sql/           # Sinh, kiểm tra, thực thi SQL
│   ├── scripts/                   # Setup, seed, ingestion
│   ├── sql/bootstrap.sql          # Role và extension PostgreSQL
│   ├── tests/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── uv.lock
├── data/
│   ├── documents/                 # 6 tài liệu Markdown giả lập
│   └── seed/                      # 4 file CSV tái lập
├── frontend/                      # React/Vite, Vitest, Playwright
├── infrastructure/nginx/          # SPA và reverse proxy /api
├── docs/                           # Tài liệu kỹ thuật và báo cáo đánh giá
├── compose.yaml
├── requirements.txt               # Runtime Python export từ backend/uv.lock
└── .env.example
```

## Xử lý sự cố

- **Không tìm thấy `python`**: chạy `py --list`, bảo đảm có Python 3.11 rồi tạo venv bằng `uv sync --locked --python 3.11` hoặc `py -3.11 -m venv backend/.venv`. Không thay đổi Python mặc định toàn Windows chỉ để chạy dự án.
- **Không tìm thấy `uv`**: cài theo [tài liệu chính thức của uv](https://docs.astral.sh/uv/getting-started/installation/) hoặc dùng phương án `pip` cho runtime.
- **Sai phiên bản Python**: kiểm tra `backend\.venv\Scripts\python.exe --version`; phải là 3.11 cho môi trường đã nghiệm thu.
- **Venv không tự kích hoạt**: chạy **Terminal: Select Default Profile**, chọn `ShopQuery PowerShell`, đóng Terminal cũ và mở Terminal mới. Có thể chạy `.\backend\.venv\Scripts\Activate.ps1` thủ công để phân biệt lỗi profile IDE với lỗi venv.
- **PowerShell chặn `Activate.ps1`**: vẫn có thể dùng `uv run ...`. Nếu cần activation, chỉ nới cho process hiện tại bằng `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`, không đổi policy toàn máy.
- **Docker không phản hồi**: mở Docker Desktop, chờ engine sẵn sàng rồi chạy `docker compose ps`.
- **Cổng 8000, 8080, 5173 hoặc 54321 bị chiếm**: dùng `Get-NetTCPConnection -State Listen` để tìm tiến trình; dừng instance trùng hoặc đổi cấu hình một cách có chủ đích.
- **Thiếu/sai Gemini key**: kiểm tra `GEMINI_API_KEY` trong `.env`, không in key ra Terminal và không commit file.
- **Gemini 503/504**: đây có thể là lỗi upstream tạm thời. SDK chỉ retry lỗi tạm thời theo giới hạn; chờ rồi thử một request, kiểm tra quota/status thay vì đổi model hoặc gọi lặp liên tục.
- **Gemini 429**: free tier có giới hạn request/phút. Chờ đúng cửa sổ quota rồi thử lại một lần; không tăng retry hoặc đổi model để né quota.
- **Upload bị từ chối**: kiểm tra đúng `.csv`/`.xlsx`, encoding UTF-8, header duy nhất và các giới hạn kích thước/dòng/cột. Preview không ghi dữ liệu nếu validation thất bại.
- **RAG không có nguồn**: kiểm tra đã chạy `ingest_documents.py` và database có document chunks; ingestion dùng quota Gemini.
- **CORS hoặc network error**: dùng đúng URL frontend, kiểm tra backend health và `CORS_ORIGINS`. Bản Nginx dùng same-origin `/api`; Vite dùng proxy cổng 8000.

## Giới hạn của MVP

- Dữ liệu bán hàng và tài liệu đều là dữ liệu giả lập.
- Có auth/session/CSRF/ownership và giới hạn beta; Google login thật và migration chính cần nghiệm thu riêng. Chưa production-ready.
- Chỉ hỗ trợ tập con SQL trên bốn bảng nghiệp vụ mẫu hoặc bảng upload đúng workspace; CTE, subquery và câu lệnh ghi bị từ chối.
- Mỗi lần upload bảng chỉ chọn một sheet; workspace có thể chứa nhiều bảng nhưng chưa khai báo quan hệ nên không hỗ trợ JOIN.
- PDF scan cần OCR không được hỗ trợ; binary tài liệu gốc không được lưu.
- Có endpoint xoá workspace, từng bảng/tài liệu và conversation, đều yêu cầu owner; xoá source không xoá evidence snapshot trong history đã lưu.
- Upload có parser validation, ownership và quota beta, chưa có antivirus/object storage hoặc kiểm chứng tải production. Không gửi dữ liệu chưa được phép tới AI providers.
- Corpus chỉ có sáu tài liệu và chưa có benchmark chứng minh cấu hình retrieval là tối ưu.
- Chưa triển khai VPS hoặc website public.
- Chất lượng và khả dụng live phụ thuộc Knowledge/Gemini, mạng, cấu hình và quota; chưa kiểm thử tải hoặc bảo đảm uptime.
- Không đưa demo chứa API key lên Internet công khai khi chưa bổ sung xác thực, giới hạn lưu lượng và quản lý secret phù hợp.

Repository: [github.com/MinhHoang1403/Shopquery-AI](https://github.com/MinhHoang1403/Shopquery-AI). Xem [nghiệm thu mới nhất](docs/final_audit_report.md), [cơ sở kỹ thuật](docs/technical_references.md) và [đánh giá lịch sử](docs/evaluation_report.md).
