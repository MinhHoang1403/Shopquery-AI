# ShopQuery AI

[![CI](https://github.com/MinhHoang1403/Shopquery-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/MinhHoang1403/Shopquery-AI/actions/workflows/ci.yml)

ShopQuery AI là ứng dụng trợ lý E-commerce dùng AI để trả lời câu hỏi từ dữ liệu bán hàng và tài liệu chính sách. Dự án dùng dữ liệu giả lập để minh họa toàn bộ luồng từ giao diện React, FastAPI, Gemini đến PostgreSQL/pgvector; đây không phải hệ thống doanh nghiệp hoặc dịch vụ thương mại thật.

## Chức năng

- **Text-to-SQL (`SQL`)**: tạo câu `SELECT`, kiểm tra AST bằng SQLGlot và thực thi bằng PostgreSQL role chỉ đọc. Ví dụ: “Top 5 sản phẩm bán chạy nhất tháng 9/2025 là gì?”
- **RAG (`RAG`)**: tạo embedding cho câu hỏi, truy hồi các đoạn tài liệu gần nhất bằng pgvector rồi trả lời kèm nguồn. Ví dụ: “Chính sách đổi trả của cửa hàng như thế nào?”
- **Kết hợp (`HYBRID`)**: dùng cả kết quả SQL và bằng chứng tài liệu. Ví dụ: “Top 5 sản phẩm bán chạy nhất có thuộc danh mục được miễn phí vận chuyển không?”
- **Ngoài phạm vi (`UNSUPPORTED`)**: từ chối câu hỏi không thuộc dữ liệu và tài liệu của cửa hàng. Ví dụ: “Thời tiết Hà Nội hôm nay thế nào?”

## Công nghệ

| Thành phần | Công nghệ |
| --- | --- |
| Giao diện | React 19, TypeScript, Vite |
| API | FastAPI, Pydantic, Uvicorn |
| AI | Gemini, Google GenAI SDK |
| Truy vấn | SQLGlot, SQLAlchemy, Psycopg |
| Dữ liệu | PostgreSQL 17, pgvector |
| Triển khai local | Nginx, Docker, Docker Compose |
| Chất lượng | Ruff, Pytest, ESLint, Vitest, Playwright, GitHub Actions |

## Kiến trúc

```text
Browser
  -> Nginx
    -> FastAPI
      -> Gemini Router
        +-> SQL ------> Gemini -> SQLGlot -> PostgreSQL read-only
        +-> RAG ------> Gemini Embedding -> pgvector -> Gemini
        +-> HYBRID ---> SQL + RAG -> Gemini tổng hợp
        +-> UNSUPPORTED
```

Nginx phục vụ React SPA và chuyển tiếp nguyên đường dẫn `/api` đến FastAPI. Router dùng structured output để chọn đúng một nhánh. Nhánh SQL chỉ cho phép tập con truy vấn đã định, giới hạn bảng, số dòng và thời gian thực thi; nhánh RAG trả nguồn lấy từ corpus đã ingest. Frontend không giữ Gemini API key.

## Yêu cầu môi trường

### Chạy hoàn toàn bằng Docker

- Git.
- Docker Desktop có Docker Compose.
- Gemini API key.

Python, Node.js, PostgreSQL và Nginx được cung cấp trong container nên không cần cài riêng trên Windows.

### Phát triển native

- Python 3.11; dự án khai báo `>=3.11,<3.13` nhưng kiểm thử và Docker dùng Python 3.11.
- `uv` là công cụ Python được ưu tiên; `pip` là phương án thay thế cho runtime.
- Node.js 24 và npm để chạy frontend.
- Docker Desktop/Compose để chạy PostgreSQL có pgvector.
- Gemini API key cho generation, embedding, ingestion và live tests.

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

Điền `GEMINI_API_KEY` bằng key của bạn. Không commit `.env` và không đưa key vào frontend hoặc GitHub Actions.

Các biến chính:

| Biến | Vai trò |
| --- | --- |
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

## Khởi động nhanh bằng Docker Compose

### Thiết lập lần đầu

Sau khi đã tạo `.env` và điền API key:

```powershell
docker compose up -d --build
docker compose ps
docker compose exec api python scripts/setup_database.py
docker compose exec api python scripts/load_seed_data.py
docker compose exec api python scripts/ingest_documents.py
```

Chờ ba service `db`, `api`, `web` healthy rồi mở `http://127.0.0.1:8080`. API trực tiếp ở `http://127.0.0.1:8000` và PostgreSQL ở `127.0.0.1:54321`.

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

Nếu đây là database mới, chạy ba script thiết lập trước lệnh Uvicorn:

```powershell
uv run python scripts/setup_database.py
uv run python scripts/load_seed_data.py
uv run python scripts/ingest_documents.py
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
Set-Location backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.txt
```

`requirements.txt` chỉ chứa runtime dependencies được export từ `uv.lock`; nó không cài Ruff, Pytest hoặc frontend. Dùng `uv sync --locked --python 3.11` khi cần đầy đủ công cụ lint/test.

### Tự kích hoạt trong Antigravity/VS Code

Repository cấu hình `.vscode/settings.json` để chọn `backend/.venv/Scripts/python.exe`. Microsoft Python Environments dùng chế độ `command` để kích hoạt environment khi một Terminal mới được tạo, không sửa PowerShell `$PROFILE`.

Sau khi chạy `uv sync`, đóng Terminal cũ rồi mở Terminal PowerShell mới. Kiểm tra:

```powershell
python -c "import sys; print(sys.executable); print(sys.version); print(sys.prefix != sys.base_prefix)"
```

Kết quả đúng phải trỏ đến `backend\.venv\Scripts\python.exe`, dùng Python 3.11 và dòng cuối là `True`. Nếu IDE chưa chọn đúng interpreter, dùng lệnh **Python: Select Interpreter**, chọn file trên rồi mở Terminal mới.

Kích hoạt thủ công từ thư mục gốc khi IDE không hỗ trợ:

```powershell
.\backend\.venv\Scripts\Activate.ps1
```

Thoát venv bằng `deactivate`. Docker không cần venv Windows vì Python và dependencies nằm trong image backend.

## Quản lý dependencies

- `backend/pyproject.toml`: khai báo direct dependencies và nhóm development.
- `backend/uv.lock`: khóa đầy đủ phiên bản Python; đây là nguồn để tái tạo môi trường backend.
- `backend/requirements.txt`: export runtime có pinned versions và hashes từ `uv.lock`, phục vụ `pip`.
- `frontend/package.json` và `frontend/package-lock.json`: khai báo và khóa dependencies React/Node.js.
- `backend/Dockerfile`, `frontend/Dockerfile` và `compose.yaml`: định nghĩa môi trường container.

Một file `requirements.txt` không cài React, PostgreSQL, Nginx hoặc Docker. Khi dependencies backend thay đổi hợp lệ, cập nhật lockfile rồi export lại:

```powershell
Set-Location backend
uv export --locked --no-dev --no-emit-project --format requirements.txt --output-file requirements.txt
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
docker compose exec db psql -U shopquery_setup -d postgres -c "CREATE DATABASE shopquery_test OWNER shopquery_setup;"
Set-Location backend
$env:DATABASE_SETUP_URL = "postgresql+psycopg://shopquery_setup:setup_password@127.0.0.1:54321/shopquery_test"
$env:DATABASE_READONLY_URL = "postgresql+psycopg://shopquery_reader:readonly_password@127.0.0.1:54321/shopquery_test"
$env:RUN_DATABASE_TESTS = "1"
uv run pytest -m integration
Remove-Item Env:DATABASE_SETUP_URL, Env:DATABASE_READONLY_URL, Env:RUN_DATABASE_TESTS
Set-Location ..
docker compose exec db psql -U shopquery_setup -d postgres -c "DROP DATABASE shopquery_test;"
```

Không chạy integration tests với `shopquery` nếu cần giữ nguyên database chính. Test integration dùng embedding giả lập có tính quyết định, không phải kết quả Gemini thật.

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

Mock E2E không gọi Gemini nhưng cần web Docker chạy ở cổng 8080:

```powershell
Set-Location frontend
npx playwright install chromium
npm run test:e2e
```

`npm run test:e2e:live` gọi API thật, database và Gemini; chỉ chạy khi full stack đã healthy, đã ingest corpus và muốn dùng quota. GitHub Actions chỉ chạy Ruff/unit tests và frontend quality gates, không nhận Gemini key và không gọi live tests.

### Docker Compose

```powershell
docker compose config --quiet
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-WebRequest http://127.0.0.1:8080/api/health -UseBasicParsing
```

## API

### `GET /api/health`

Kiểm tra liveness mà không gọi Gemini:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

### `POST /api/chat`

```powershell
$body = @{ message = "Top 5 sản phẩm bán chạy nhất tháng 9/2025 là gì?" } | ConvertTo-Json
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
  "error": null
}
```

`route` là `SQL`, `RAG`, `HYBRID` hoặc `UNSUPPORTED`. `sql`/`rows` chỉ có dữ liệu cho SQL và Hybrid; `sources` chỉ có dữ liệu cho RAG và Hybrid. Với lỗi nghiệp vụ đã dự kiến, API hiện có thể trả HTTP 200 cùng `route: null` và nội dung trong trường `error`; client phải kiểm tra trường này.

## Cấu trúc dự án

```text
.
├── .github/workflows/ci.yml       # GitHub Actions
├── .vscode/                       # Interpreter và auto-activation portable
├── backend/
│   ├── app/
│   │   ├── ai/                    # Google GenAI adapter
│   │   ├── api/                   # FastAPI routes và contracts
│   │   ├── core/                  # Cấu hình, logging, errors
│   │   ├── database/              # Models, session, schema, loader
│   │   ├── rag/                   # Chunking, pgvector, RAG
│   │   ├── routing/               # Router, Hybrid, chat service
│   │   └── text_to_sql/           # Sinh, kiểm tra, thực thi SQL
│   ├── scripts/                   # Setup, seed, ingestion
│   ├── sql/bootstrap.sql          # Role và extension PostgreSQL
│   ├── tests/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── requirements.txt
│   └── uv.lock
├── data/
│   ├── documents/                 # 6 tài liệu Markdown giả lập
│   └── seed/                      # 4 file CSV tái lập
├── frontend/                      # React/Vite, Vitest, Playwright
├── infrastructure/nginx/          # SPA và reverse proxy /api
├── docs/technical_references.md
├── compose.yaml
└── .env.example
```

## Xử lý sự cố

- **Không tìm thấy `python`**: chạy `py --list`, bảo đảm có Python 3.11 rồi tạo venv bằng `uv sync --locked --python 3.11` hoặc `py -3.11 -m venv backend/.venv`. Không thay đổi Python mặc định toàn Windows chỉ để chạy dự án.
- **Không tìm thấy `uv`**: cài theo [tài liệu chính thức của uv](https://docs.astral.sh/uv/getting-started/installation/) hoặc dùng phương án `pip` cho runtime.
- **Sai phiên bản Python**: kiểm tra `backend\.venv\Scripts\python.exe --version`; phải là 3.11 cho môi trường đã nghiệm thu.
- **Venv không tự kích hoạt**: cài/enable extension được đề xuất, chọn đúng interpreter, đóng và mở Terminal mới. Có thể chạy `.\backend\.venv\Scripts\Activate.ps1` thủ công.
- **PowerShell chặn `Activate.ps1`**: vẫn có thể dùng `uv run ...`. Nếu cần activation, chỉ nới cho process hiện tại bằng `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`, không đổi policy toàn máy.
- **Docker không phản hồi**: mở Docker Desktop, chờ engine sẵn sàng rồi chạy `docker compose ps`.
- **Cổng 8000, 8080, 5173 hoặc 54321 bị chiếm**: dùng `Get-NetTCPConnection -State Listen` để tìm tiến trình; dừng instance trùng hoặc đổi cấu hình một cách có chủ đích.
- **Thiếu/sai Gemini key**: kiểm tra `GEMINI_API_KEY` trong `.env`, không in key ra Terminal và không commit file.
- **Gemini 503/504**: đây có thể là lỗi upstream tạm thời. SDK chỉ retry lỗi tạm thời theo giới hạn; chờ rồi thử một request, kiểm tra quota/status thay vì đổi model hoặc gọi lặp liên tục.
- **RAG không có nguồn**: kiểm tra đã chạy `ingest_documents.py` và database có document chunks; ingestion dùng quota Gemini.
- **CORS hoặc network error**: dùng đúng URL frontend, kiểm tra backend health và `CORS_ORIGINS`. Bản Nginx dùng same-origin `/api`; Vite dùng proxy cổng 8000.

## Giới hạn của MVP

- Dữ liệu bán hàng và tài liệu đều là dữ liệu giả lập.
- Không có authentication hoặc rate limiting dành cho production.
- Chỉ hỗ trợ tập con SQL và bốn bảng nghiệp vụ; CTE, subquery và câu lệnh ghi bị từ chối.
- Corpus chỉ có sáu tài liệu và chưa có benchmark chứng minh cấu hình retrieval là tối ưu.
- Chưa triển khai VPS hoặc website public.
- Chất lượng và khả dụng live phụ thuộc model, API key và quota Gemini.
- Không đưa demo chứa API key lên Internet công khai khi chưa bổ sung xác thực, giới hạn lưu lượng và quản lý secret phù hợp.

Repository: [github.com/MinhHoang1403/Shopquery-AI](https://github.com/MinhHoang1403/Shopquery-AI). Cơ sở kỹ thuật và nguồn tham khảo nằm tại [docs/technical_references.md](docs/technical_references.md).
