# ShopQuery AI

ShopQuery AI là ứng dụng trợ lý dữ liệu E-commerce giả lập gồm giao diện React, FastAPI, PostgreSQL và Gemini. Ứng dụng nhận câu hỏi tiếng Việt hoặc tiếng Anh và chọn một trong bốn route:

- `SQL`: Gemini sinh một câu SELECT, SQLGlot kiểm tra AST, PostgreSQL thực thi bằng role read-only.
- `RAG`: Gemini Embedding 2 tạo vector truy vấn, pgvector lấy policy chunks gần nhất và Gemini trả lời có nguồn.
- `HYBRID`: dùng lại cả SQL và RAG rồi đối chiếu dữ liệu với điều kiện chính sách.
- `UNSUPPORTED`: từ chối câu hỏi ngoài dữ liệu cửa hàng mà không bịa thông tin.

React hiển thị hội thoại và bằng chứng; Nginx phục vụ SPA và chuyển tiếp nguyên đường dẫn `/api` tới FastAPI. MVP chạy local, chưa có authentication hay cloud deployment.

## Kiến trúc

```text
Question
   |
Gemini Router
   +-- SQL ------> SQL generation -> SQLGlot -> read-only PostgreSQL -> grounded answer
   +-- RAG ------> query embedding -> pgvector top 3 -> grounded answer + citations
   +-- HYBRID ---> SQL pipeline + RAG retrieval -> evidence comparison
   +-- UNSUPPORTED
```

Luồng triển khai local: `Browser -> Nginx (:8080) -> FastAPI (:8000) -> PostgreSQL/Gemini`. Frontend chỉ gọi API cùng origin và không chứa Gemini API key.

Các lớp bảo vệ SQL không phụ thuộc prompt: allowlist AST, chỉ bốn bảng nghiệp vụ, role database chỉ SELECT, read-only transaction, statement timeout và giới hạn 200 dòng.

## Công nghệ

Python 3.11, FastAPI, Pydantic, SQLAlchemy, PostgreSQL 17, pgvector, SQLGlot, Google GenAI SDK, React 19, TypeScript, Vite, Vitest, Nginx, Docker và Docker Compose. Dependency được khóa trong `backend/uv.lock` và `frontend/package-lock.json`.

## Cấu trúc repository

```text
.
├── backend/
│   ├── app/
│   │   ├── ai/             # Adapter Google GenAI
│   │   ├── api/            # Pydantic contracts và FastAPI routes
│   │   ├── core/           # Configuration, logging, errors
│   │   ├── database/       # Models, schema, seed loader
│   │   ├── rag/            # Markdown, chunking, pgvector, RAG
│   │   ├── routing/        # Router, Hybrid, top-level service
│   │   └── text_to_sql/    # Generation, validation, execution
│   ├── scripts/            # Generate, setup, load, ingest
│   ├── sql/                # PostgreSQL bootstrap role/extension
│   ├── tests/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── uv.lock
├── data/
│   ├── documents/          # 6 tài liệu Markdown
│   └── seed/               # 4 CSV tái lập
├── frontend/                 # React/Vite UI, tests và web image
├── infrastructure/nginx/    # SPA hosting và /api reverse proxy
├── .github/workflows/ci.yml
├── docs/technical_references.md
├── compose.yaml
├── .env.example
└── AGENTS.md
```

## Yêu cầu môi trường

- Windows PowerShell.
- Docker Desktop với Docker Compose, hoặc PostgreSQL có extension pgvector.
- Python 3.11 và `uv` nếu chạy backend trực tiếp.
- Node.js 24 và npm nếu chạy frontend trực tiếp.
- Gemini API key để chạy generation, embedding và ingestion thật. Health endpoint, sinh dữ liệu và unit tests không cần key.

## Cấu hình `.env`

Từ thư mục gốc:

```powershell
Copy-Item .env.example .env
notepad .env
```

Điền `GEMINI_API_KEY`. `GEMINI_GENERATION_MODEL` mặc định là `gemini-3.5-flash-lite`; `GEMINI_EMBEDDING_MODEL` bắt buộc là `gemini-embedding-2` và dimensions bắt buộc là 768. Mỗi lời gọi Gemini có timeout mặc định 30 giây và tối đa 3 attempts với exponential backoff cho lỗi tạm thời. File `.env` đã bị Git ignore.

`DATABASE_SETUP_URL` có quyền tạo/nạp dữ liệu. `DATABASE_READONLY_URL` là credential riêng để thực thi SQL do model sinh. Các giá trị password trong Compose chỉ là credential phát triển local, không dùng cho production.

## Chạy bằng Docker Compose

```powershell
docker compose up -d --build
docker compose exec api python scripts/setup_database.py
docker compose exec api python scripts/load_seed_data.py
docker compose exec api python scripts/ingest_documents.py
docker compose ps
```

Ứng dụng: `http://127.0.0.1:8080`; API trực tiếp: `http://127.0.0.1:8000`. Cả ba cổng web, API và PostgreSQL chỉ bind vào loopback để hỗ trợ kiểm tra local, không bind lên mọi network interface. Volume `postgres_data` giữ dữ liệu qua các lần khởi động lại; không dùng `docker compose down -v` nếu muốn giữ dữ liệu.

Lệnh ingestion gọi Gemini một lần cho mỗi chunk mới. Chạy lại với tài liệu không đổi sẽ dùng `content_hash` và không tạo embedding lại.

## Chạy trực tiếp bằng Python

Khởi động database trước, sau đó:

```powershell
Set-Location backend
uv sync
uv run python scripts/setup_database.py
uv run python scripts/load_seed_data.py
uv run python scripts/ingest_documents.py
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Default native connection dùng `127.0.0.1:54321` để tránh khác biệt phân giải `localhost` trên Windows. Có thể override bằng environment variables.

## Chạy frontend trực tiếp

Vite chuyển tiếp `/api` tới `http://127.0.0.1:8000`, nên cần khởi động backend trước:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Mở `http://127.0.0.1:5173`. Lịch sử hội thoại chỉ tồn tại trong phiên trình duyệt và mỗi câu hỏi là một request độc lập; frontend không gửi lịch sử hội thoại về backend.

## Sinh và nạp lại synthetic data

Generator dùng seed cố định, tạo 8 categories, 150 products, 2.000 orders và 1–3 items mỗi order từ 01/2025 đến hết 09/2026:

```powershell
Set-Location backend
uv run python scripts/generate_synthetic_data.py
uv run python scripts/load_seed_data.py
```

Loader thay thế bốn bảng nghiệp vụ trong một transaction, nên chạy lại không tạo dòng trùng. Doanh thu demo chỉ tính đơn `completed` bằng `SUM(quantity × unit_price)`.

## Kiểm thử

Unit tests không cần Gemini hoặc database:

```powershell
Set-Location backend
uv run ruff check app scripts tests
uv run pytest -m "not integration"
```

Integration tests cần service `db` đang healthy:

```powershell
Set-Location backend
$env:RUN_DATABASE_TESTS = "1"
uv run pytest -m integration
Remove-Item Env:RUN_DATABASE_TESTS
```

Frontend quality gate:

```powershell
Set-Location frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Browser E2E dùng Chromium độc lập do Playwright quản lý. Bộ mặc định chỉ dùng mock API; live smoke gọi Gemini riêng để tránh phụ thuộc secrets trong CI:

```powershell
Set-Location frontend
npx playwright install chromium
npm run test:e2e
npm run test:e2e:live
```

Playwright kiểm tra desktop `1440×900`, mobile `390×844`, console/network và chụp bằng chứng tạm trong `frontend/test-results/`. Thư mục này được Git ignore.

GitHub Actions chạy backend unit/Ruff và toàn bộ frontend quality gate; workflow không cần secrets và không gọi Gemini live.

Không có key thì không chạy live Gemini test. Không được diễn giải fake embeddings trong integration tests là kết quả Gemini thật.

## API

Healthcheck không gọi Gemini:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/api/health
```

Ví dụ chat:

```powershell
$body = @{ message = "Top 5 sản phẩm bán chạy nhất tháng 9/2025?" } | ConvertTo-Json
$utf8Body = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat `
  -ContentType "application/json; charset=utf-8" -Body $utf8Body
```

Response luôn có `answer`, `route`, `sql`, `rows`, `sources`, `error`. SQL chỉ xuất hiện cho SQL/Hybrid; sources chỉ xuất hiện cho RAG/Hybrid.

## Giới hạn MVP

- Chỉ hỗ trợ bốn bảng và các SELECT/JOIN/aggregation cơ bản; CTE, subquery và chức năng SQL phức tạp bị từ chối.
- Corpus chỉ gồm sáu policy/guide documents giả lập; top 3 exact retrieval chưa được benchmark là cấu hình tối ưu.
- Chưa có reranker, semantic chunking, authentication, rate limiting hoặc production secret management.
- Chất lượng Gemini end-to-end phụ thuộc API key, model được cấu hình và quota. Khi thiếu key, hệ thống trả lỗi rõ ràng và không đổi sang model khác.
- Xem cơ sở kỹ thuật tại [docs/technical_references.md](docs/technical_references.md).
