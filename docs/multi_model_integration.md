# Tích hợp hai model generation

## Provider và hợp đồng

Ứng dụng có hai ID cố định: `inetcloud-knowledge` và `gemini`. Registry được phục vụ từ `GET /api/models`, chỉ trả label/provider/configured, default và setting fallback; `configured` không có nghĩa server đang online. Endpoint công ty chỉ nằm trong `.env` local, không nằm trong source hoặc CI.

Knowledge sử dụng `langchain-openai` và Chat Completions, `use_responses_api=False`, `stream_usage=False`, JSON Schema strict + Pydantic validation. Placeholder `not-required` không phải secret và không lấy từ Gemini key. Probe thực tế ngày 18/10/2026 xác nhận DNS, HTTPS/TLS, `/models`, no-auth và placeholder Bearer, system/user, Unicode, JSON mode và JSON Schema. Cả RouteDecision, SqlDraft, RagAnswerDraft và HybridAnswerDraft đã được gọi qua ChatOpenAI. `temperature=0` được bật sau probe xác nhận server chấp nhận tham số.

Không dùng tool calling, Responses API hoặc tham số giới hạn token chưa kiểm chứng. Thay server/model cần chạy compatibility probe lại; server tương thích OpenAI cơ bản không bảo đảm mọi tính năng nâng cao. Xem [tài liệu ChatOpenAI chính thức](https://docs.langchain.com/oss/python/integrations/chat/openai).

## Retry, fallback và bảo mật

- SDK thử tối đa `INETCLOUD_RETRY_ATTEMPTS` lần (1–3, mặc định 1), timeout `INETCLOUD_TIMEOUT_SECONDS` mỗi lần (1–120 giây, mặc định 60). Không có vòng retry transport riêng của ứng dụng.
- Native structured response sai được gọi lại tối đa một lần, mỗi lượt chịu retry SDK như trên. Cận trên là `2 × INETCLOUD_RETRY_ATTEMPTS` network attempts cho một generation structured lỗi output, không retry vô hạn.
- Chỉ ProviderError đã phân loại là transient/output mới đủ điều kiện fallback. Knowledge 400/401/403/404 hoặc lỗi chưa xác định không fallback. SQL validation, database, retrieval và citation validation không được xem là provider outage.
- Fallback yêu cầu setting bật và Gemini key có mặt. Backend tạo lại router/generator/synthesizer và chạy lại toàn bộ logical turn với cùng dataset context. Gateway chính được đóng trước fallback, mỗi gateway sở hữu HTTP client riêng.
- Chỉ lưu user message và một response cuối. Lỗi cuối được lưu dưới role `error` với `used_model=null`. Khi hai provider đều thất bại, metadata vẫn ghi đã thử fallback nhưng không gán tác giả cho đáp án không tồn tại.
- Gemini SDK giữ retry/timeout hiện có. Chọn Gemini thủ công đi thẳng tới Gemini, không có fallback ngược.
- Fallback generation mặc định tắt. Khi bật, schema, categorical values, câu hỏi, rows và evidence có thể rời môi trường công ty tới Google. Gemini Embedding vẫn độc lập và cần key kể cả khi generation dùng Knowledge. Không có key, SQL Knowledge vẫn chạy; RAG báo thiếu cấu hình embedding.
- Không log prompts/headers; tắt HTTP client INFO logs để tránh ghi URL công ty. LangSmith không được bật trong cấu hình dự án; không bật tracing ngoài hệ thống cho dữ liệu chưa được phép.

## API và lưu trữ

`POST /api/chat` và `POST /api/conversations/{id}/messages` nhận optional `model_id`. Model ID ngoài allowlist trả 422. Không nhận base URL hay provider model từ request.

`POST /api/conversations` nhận optional `model_id`, mặc định theo Settings. `PATCH /api/conversations/{id}` nhận `title` và/hoặc `model_id`. Gửi message có model ID cập nhật preference trước khi generation; response không ghi đè preference mới hơn khi hoàn thành.

ChatResponse giữ `answer/route/sql/rows/sources/error` và thêm `requested_model/used_model/fallback_used/fallback_reason`. Metadata được lưu nguyên trong assistant/error message. Row cũ không có các field này vẫn đọc được. Workspace rỗng không tạo provider client và trả `used_model=null` vì không gọi AI.

Migration thêm duy nhất `chat_conversations.model_id VARCHAR(40) NULL`, không backfill hoặc sửa message metadata. Row legacy NULL được đọc là Gemini vì toàn bộ lịch sử trước nâng cấp dùng Gemini. Setup có thể chạy lặp; cần backup và kiểm thử restore trên database tạm trước database chính. Không thay embeddings hoặc ingest lại corpus.

## Kiểm thử

Các lệnh backend chạy trong `backend`, frontend trong `frontend`. Live tests không chạy trong CI, không sử dụng database chính và chỉ dùng dữ liệu giả lập.

```powershell
uv run ruff check app scripts tests
uv run pytest -m "not integration and not live"
# Trỏ DATABASE_SETUP_URL và DATABASE_READONLY_URL vào database test riêng trước:
$env:RUN_DATABASE_TESTS = "1"
uv run pytest -m integration
$env:RUN_LIVE_AI = "1"
uv run pytest tests/test_multimodel_live.py -v
```

Live backend matrix gồm 2 SQL (150 sản phẩm và doanh thu completed 151.687.001.000), 2 RAG (đổi trả/vận chuyển), 2 Hybrid (top sản phẩm + vận chuyển/bảo hành), 1 Unsupported và Gemini SQL thủ công. Ground truth top-N lấy trực tiếp PostgreSQL, chấp nhận sản phẩm đồng hạng ở vị trí thứ năm. Citation IDs chỉ được chấp nhận nếu pipeline đã retrieve đúng scope.

```powershell
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
# Web test và API test đã healthy:
$env:SHOPQUERY_E2E_BASE_URL = "http://127.0.0.1:5174"
$env:SHOPQUERY_LIVE_MODELS = "1"
npm run test:e2e:models-live
$env:SHOPQUERY_LIVE_WORKSPACE = "1"
npm run test:e2e:workspace-live
```

Native select trong composer hỗ trợ bàn phím, Escape và focus bằng control chuẩn của browser/OS. Selector bị khóa khi đang gửi/lưu để giữ nguyên model của request hiện tại. Browser mock xác minh model IDs thực gửi, fallback notice và reload ở năm viewport 1440/1280/768/390/320. Failure injection chỉ dùng stub trong test, không cung cấp endpoint gây lỗi ở production và không gây sự cố server thật.

## Giới hạn chất lượng

Kết quả nghiệm thu local ngày 18/10/2026: Ruff pass; 142 unit/API tests và 17 PostgreSQL integration tests pass trên database riêng; frontend ESLint/TypeScript/build pass, Vitest 17/17; Playwright mock 25/25 trên năm viewport; live backend 8/8; live browser lựa chọn model 1/1 và workspace đa nguồn 1/1. Probe từ container Docker cũng xác nhận DNS, `/models` 200 và router qua ChatOpenAI chọn SQL. Các kết quả này là live snapshot, không phải cam kết uptime hoặc độ chính xác cho mọi câu hỏi.

Schema hợp lệ không chứng minh đáp án đúng. Các probe ban đầu đã phát hiện router phân loại sai, SQL sai cột/hàm và Hybrid thiếu mã danh mục; validator chặn SQL sai và không dùng fallback để vượt guardrail. Prompt được làm rõ về capability, alias, top-N, mã danh mục và câu trả lời theo từng sản phẩm. Live evaluation vẫn là một tập mẫu nhỏ, không bảo đảm mọi câu hỏi đều đúng; server cũng đã có lượt timeout. Giữ evidence toolbar để người dùng kiểm chứng kết quả thực tế.

Public clone không có endpoint công ty hoặc Gemini key nên cần cấu hình local trước khi chat. Không thay đổi giới hạn OCR, JOIN của uploaded workspaces, authentication hoặc multi-tenant trong nâng cấp này.
