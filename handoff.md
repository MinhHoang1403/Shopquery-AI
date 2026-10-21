# SHOPQUERY AI — HANDOFF TOÀN DIỆN CHO CHATGPT WEB

> Snapshot lịch sử của lượt Gate D. Cập nhật tiếp theo ngày 21/10/2026:
> semantic COUNT đã kiểm chứng offline và triển khai API-only lên8080.
> Đọc `docs/text_to_sql_count_semantic_contract_redesign.md` và
> `docs/text_to_sql_count_deployment_git_delivery.md` cho trạng thái source/runtime/
> Git mới nhất. KH/GH live trên semantic runtime chưa nghiệm thu lại; không dùng
> các kết luận “chưa deploy” bên dưới thay cho báo cáo deployment mới.

Ngày cập nhật: **21/10/2026, múi giờ Việt Nam (Asia/Ho_Chi_Minh, UTC+07:00)**.

Đây là tài liệu chuyển giao ngữ cảnh kỹ thuật và tiến độ, được tổng hợp từ hội
thoại phát triển, source hiện tại, Git, báo cáo nghiệm thu và bằng chứng kiểm thử.
Tài liệu ưu tiên tính chính xác hơn việc mô tả dự án là đã hoàn tất. Không phải
bản sao nguyên văn mọi tin nhắn hoặc mọi file đính kèm trong lịch sử.

**Tài liệu đã loại API keys, OAuth secrets, email/tên tài khoản Google, cookies,
tokens, mật khẩu database, endpoint Knowledge nội bộ và raw dữ liệu người dùng.**
Các con số chi tiết dùng cho JOIN mới nhất bên dưới thuộc fixture synthetic.

## 1. Đọc phần này trước: trạng thái thật hiện tại

ShopQuery AI là chatbot phân tích dữ liệu đa lĩnh vực, đã có frontend, backend,
PostgreSQL/pgvector, upload đa nguồn, SQL/RAG/Hybrid, hai model generation,
Google login tùy chọn, Guest mode, lịch sử cá nhân, quản lý/xóa nguồn và JOIN
tối đa ba bảng qua quan hệ backend kiểm chứng.

**Ứng dụng chạy local; chưa phải sản phẩm public/VPS production-ready.**

Kết luận mới nhất: **PARTIALLY VERIFIED; Gate D live JOIN/Hybrid FAIL**.

- Code và guardrails có bộ regression offline/DB thật đạt CI.
- Single-table SQL mới nhất đạt trên cả Knowledge và Gemini.
- Gemini JOIN hai bảng mới nhất đạt đúng dữ liệu và grounded answer.
- Knowledge JOIN hai/ba bảng và Hybrid chưa đạt trong lượt mới nhất.
- Gemini JOIN ba bảng và Hybrid chưa đạt trong lượt mới nhất.
- Lỗi mới nhất chủ yếu là model không tuân thủ hợp đồng COUNT/alias, hoặc trả
  `unsupported_reason`; không được gọi chung là thiếu relationship.
- Những request bị chặn giữ fail-closed, chưa thực thi SQL, không tạo số liệu giả.
- Lịch sử authenticated UI đã reload và giữ đúng tám responses của lượt mới nhất.
- Dữ liệu nghiệp vụ cũ được kiểm tra fingerprints, không ghi nhận thay đổi.

| Nghiệm thu mới nhất trên Google UI 8080 | Knowledge | Gemini |
| --- | --- | --- |
| SQL một bảng, 50 đơn/Decimal/zero/NULL | PASS | PASS |
| JOIN hai bảng theo từng tài xế | FAIL: count_star_alias | PASS: 15 groups |
| JOIN ba bảng theo từng kho | FAIL: count_star_alias | FAIL: count_column_alias |
| Hybrid ba bảng + tài liệu KPI | FAIL: count_star_alias | FAIL: generator_unsupported |

**3/8 probes PASS, 5/8 FAIL. Không tuyên bố JOIN đã ổn định chỉ vì CI xanh.**

Nhiệm vụ ngay trước handoff là chạy ngân sách live đã duyệt và báo cáo, không
phải sửa code trong lúc thử. Nhiệm vụ hiện tại chỉ là viết handoff. Chưa có bản
sửa mới cho năm live failures này, chưa có lượt live tái nghiệm thu sau chúng.

## 2. Mục tiêu của chủ dự án và cách cộng tác mong muốn

Chủ dự án muốn:

1. Người dùng upload dữ liệu của nhiều lĩnh vực, không chỉ schema bán hàng cố định.
2. Chat được ngay nếu đủ bảng/tài liệu; tự nhận quan hệ an toàn khi có bằng chứng.
3. Truy vấn kết hợp nhiều bảng, hiện đã mở tối đa ba bảng, tránh nhân đôi số liệu.
4. SQL thực thi thật, RAG có nguồn thật, Hybrid kết hợp bằng chứng thật.
5. Dữ liệu tiền/số lớn/thời gian chính xác; không đổi NULL thành zero.
6. Cả Knowledge và Gemini dùng được; model attribution/lịch sử đúng.
7. Guest thử được; người đăng nhập có dữ liệu cá nhân và lịch sử lâu dài.
8. UI gọn, dễ dùng, upload/xóa/quản lý dữ liệu và quan hệ rõ ràng.
9. Test và CI tự động; bảo vệ database, không làm hỏng dữ liệu khi sửa/deploy.
10. Sửa có bằng chứng, không nhiều lần báo xong nhưng UI vẫn không chạy.

Ngôn ngữ giao tiếp/báo cáo: tiếng Việt. Người dùng thường yêu cầu “tiếp tục làm”,
muốn triển khai thực tế hơn là chỉ đưa kế hoạch; nhưng không vì vậy được vượt
phạm vi quyền đã duyệt, tiêu thêm quota, xóa dữ liệu hoặc nới bảo mật.

Không hứa “không còn lỗi nào”. Phải phân biệt implementation, offline tests,
real PostgreSQL, mock UI, real UI, live provider và production readiness.

## 3. Workspace, repository, Git và source snapshot

| Mục | Giá trị |
| --- | --- |
| Workspace Windows | `C:\Work\ShopQuery AI` |
| Shell phát triển | PowerShell |
| Repository | https://github.com/MinhHoang1403/Shopquery-AI |
| Branch hiện tại | `main` |
| HEAD lúc viết handoff | `e2151a3d6b37f3a11e83f68553e5985bbe087deb` |
| Commit code triển khai mới nhất | `50d7bac4e1f6af8adffeb8f317a458f637de7bb0` |
| UI local | `http://127.0.0.1:8080/` |
| API trực tiếp trên máy nghiệm thu | `http://127.0.0.1:8001/` |
| PostgreSQL host port máy nghiệm thu | `127.0.0.1:15432` |

Working tree **không sạch**: trước khi tạo handoff đã có sửa chưa commit tại
`docs/sql_join_root_cause_audit.md`, bổ sung kết quả tám live probes. Handoff này
là file mới. Không tự reset hoặc ghi đè report đó. Trong snapshot đã kiểm tra,
không có production source/Hybrid hunk chưa commit; các cảnh báo Hybrid dirty
trong những báo cáo cũ là lịch sử, không tự suy ra chúng vẫn đang treo hiện nay.

Các commit gần nhất, từ cũ đến mới:

| Commit | Vai trò |
| --- | --- |
| `071b7f5` | Harden JOIN generation và lossless result contracts |
| `eeaffd4` | Báo cáo reliability audit, còn Gemini UI blocker |
| `2a8c113` | Canonicalize INNER JOIN tương đương, vẫn kiểm exact approved keys |
| `be93d5a` | Làm rõ aggregation semantics và replay contracts |
| `7e444c2` | Báo cáo offline aggregation và local deployment |
| `08bfbf0` | Automatic relationship verification và safe three-table JOIN |
| `50d7bac` | Entity grain fail-closed và bảo toàn evidence trong bảng DOCX |
| `e2151a3` | Ghi CI và local acceptance evidence |

Source commit `50d7bac` khác docs HEAD `e2151a3`, nhưng app source triển khai đã
đối chiếu khớp; không phải một bản sửa production khác giữa hai SHA đó.

Handoff không phải yêu cầu commit/push. Chưa commit/push kết quả live mới nhất
hoặc chính file này trong lượt tạo tài liệu.

## 4. Nguyên tắc AGENTS.md và các ranh giới bắt buộc

Nội dung hướng dẫn dự án hiện hành:

- Python rõ ràng, PEP 8, type hints, module theo trách nhiệm.
- Comment/docstring chỉ khi giải thích interface, business rule hoặc logic khó.
- Tên theo chức năng, không đưa mã kế hoạch/trạng thái công việc vào source.
- Quyết định AI/dữ liệu/bảo mật quan trọng dựa tài liệu chính thức hoặc nguồn
  kỹ thuật có thể kiểm chứng.
- Đúng phạm vi; không thêm framework/abstraction/hạ tầng không cần thiết.
- Không tự thay kiến trúc, model bắt buộc hoặc mở rộng sang project khác.
- Chạy tests liên quan sau sửa, báo thật phần đã/chưa kiểm chứng.
- Không commit secrets, `.env`, dữ liệu nhạy cảm, cache, venv hoặc log.

Các ranh giới người dùng đã nhiều lần nhấn mạnh:

- Không đổi framework/model/embedding để né lỗi.
- Không SQL Agent, repair loop tự do hoặc retry vô hạn.
- Không keyword router giả để vượt upstream/structured-output lỗi.
- Không cho AI thực hiện DML/DDL.
- Không JOIN chéo owner/workspace; không lấy nguồn workspace khác để bù.
- Không bỏ security tests hoặc nới validator theo phỏng đoán để làm xanh.
- Không ghi raw production prompts/SQL/rows/credentials vào logs.
- Không tự reset Google accounts/sessions/datasets/documents/embeddings/history.
- Không tự migration/restore/seed/backfill/re-ingest dữ liệu main.
- Không Docker global prune hoặc xóa volumes/dự án Docker khác.
- Không deploy VPS hoặc cài Langfuse/LangSmith trong phạm vi hiện tại.
- Không lấy một lần PASS làm bằng chứng mọi câu hỏi/JOIN luôn đúng.

Quyền trong các lượt trước gắn với hành động/fixture/budget cụ thể, không phải
ủy quyền vĩnh viễn. Những ngân sách live đã sử dụng xong không được tái dùng.

## 5. Kiến trúc tổng thể

```text
Browser: React / TypeScript
  -> Nginx (SPA + same-origin /api proxy)
    -> FastAPI
      -> Google OIDC / opaque sessions / CSRF / quotas / owner scope
      -> Guest capability namespace, RAM data + PostgreSQL TEMP
      -> Dataset workspace registry / uploaded_data physical tables
      -> Document parser -> chunking -> Gemini embedding -> pgvector
      -> Generation model selection: Knowledge hoặc Gemini
        -> Router structured decision: SQL / RAG / HYBRID / UNSUPPORTED
          SQL    -> SqlDraft -> SQLGlot validator -> execution guard
                 -> PostgreSQL readonly transaction -> grounded answer
          RAG    -> query embedding -> dataset-scoped retrieval
                 -> structured answer + validated chunk citations
          HYBRID -> SQL pipeline -> retrieval -> synthesis từ rows + chunks
          UNSUPPORTED -> thông báo ngắn, không tạo kết quả giả
      -> Authenticated conversations/messages/evidence metadata -> PostgreSQL
```

Không có vector database riêng ngoài PostgreSQL/pgvector. Không có SQL Agent
hay mô hình tự học schema ngoài context backend dựng theo request. Relationship
discovery là logic deterministic và kiểm dữ liệu thật, không phải LLM đoán.

Lựa chọn model là generation/router/grounding. **Embedding luôn dùng Gemini**
kể cả người dùng chọn Knowledge để generation. “Knowledge không cần Gemini cho
SQL-only” không có nghĩa RAG/ingest có thể chạy nội bộ không gửi Google.

## 6. Công nghệ và phiên bản đã quan sát

Các phiên bản dưới đây là snapshot môi trường dự án, không khẳng định latest
release toàn cầu. Lockfiles là nguồn tái lập cài đặt.

| Thành phần | Snapshot |
| --- | --- |
| Python kiểm thử/Docker | 3.11; project khai báo >=3.11,<3.13 |
| Python dependencies | `backend/pyproject.toml`, `backend/uv.lock` |
| Runtime requirements export | `requirements.txt` tại root |
| FastAPI trong API container | 0.143.0 |
| google-genai trong API container | 1.75.0 |
| SQLGlot trong API container | 29.0.1 |
| SQLAlchemy trong API container | 2.1.4 |
| Psycopg trong API container | 3.3.6 |
| langchain-openai trong API container | 1.7.2 |
| Authlib trong API container | 1.9.1 |
| PostgreSQL image | `pgvector/pgvector:0.8.1-pg17-trixie` |
| React / ReactDOM | 19.3.0 theo package.json |
| Vite / TypeScript | 8.3.4 / 6.0.3 theo package.json |
| Vitest / Playwright | 5.0.4 / 1.64.0 theo package.json |
| Node CI | 24 |

UI dùng React Markdown + remark-gfm, lucide-react; không đổi UI framework.
Parser dùng openpyxl, pypdf, python-docx. Backend có Ruff/Pytest; FE có ESLint,
TypeScript, Vitest và Playwright.

## 7. Hai model, embedding, retries và fallback

### 7.1 Model registry và cấu hình hiện tại

| Setting / chức năng | Giá trị / hành vi |
| --- | --- |
| `AI_DEFAULT_MODEL` | `inetcloud-knowledge` |
| Knowledge ID UI/API | `inetcloud-knowledge` |
| Knowledge provider model | `knowledge` |
| Knowledge endpoint | HTTPS nội bộ cấu hình private, không đưa vào handoff |
| Gemini ID UI/API | `gemini` |
| Gemini generation/router | `gemini-3.5-flash-lite` |
| Embedding | `gemini-embedding-2` |
| Embedding dimensions | 768, config kiểm bắt buộc |
| `AI_GEMINI_FALLBACK_ENABLED` | false trong runtime nghiệm thu |
| `BETA_PROVIDER_DATA_ENABLED` | true trên main local theo yêu cầu chủ dự án |
| `GUEST_AI_ENABLED` | true trên main local theo yêu cầu chủ dự án |
| `SQL_JOIN_V1_ENABLED` | true trên main local |

Mặc định repository cho provider gate, Guest AI và JOIN là **false**; runtime
main đã bật có chủ đích. Không đổi defaults thành true chỉ để giống máy này.

Gemini API key đã từng bị người dùng thu hồi/thay; không cần và không được yêu
cầu gửi lại secret vào chat. `.env` private tồn tại, `.env.example` không giữ key.

### 7.2 Gemini adapter

`backend/app/ai/gemini.py` tạo `google.genai.Client` với:

- Timeout hiện hành 30.000 ms mỗi request.
- SDK `HttpRetryOptions(attempts=3)`.
- Transient status allowlist: 408, 429, 500, 502, 503, 504.
- Structured output qua JSON MIME + Pydantic response schema; validate JSON trả về.
- Structured generation temperature 0; text grounding temperature 0.1.
- Không thêm vòng transport retry của ứng dụng chồng lên SDK.
- Lỗi cấu hình/auth không thuộc allowlist transient để retry tùy tiện.
- Thông báo phân biệt còn unavailable sau attempts và bị provider từ chối.

Lịch sử từng có Gemini router HTTP 503 dù plain generation smoke thành công.
Không kết luận mọi 503 là do schema hoặc ứng dụng. Lượt live mới nhất không có
bằng chứng 503 là nguyên nhân: đã nhận draft/refusal và bị guard COUNT chặn.

### 7.3 Knowledge adapter

`backend/app/ai/inetcloud.py` dùng `ChatOpenAI` Chat Completions:

- Không Responses API/tool-calling mới.
- JSON Schema strict + Pydantic, `include_raw=True` nội bộ adapter.
- Timeout 60 giây, tổng HTTP attempts hiện tại 1.
- Structured-output-invalid được gọi lại tối đa một lần: vòng lặp hai lượt.
- Placeholder SDK key không phải Gemini key hay credential thật.
- Không log prompts/headers/endpoint hoặc bật tracing bên ngoài.

### 7.4 Fallback và attribution

Fallback Knowledge -> Gemini chỉ là tùy chọn whole-turn, mặc định tắt. Nếu được
bật riêng, chỉ lỗi mạng/timeout/transient/output được phân loại mới đủ điều kiện;
không dùng để vượt SQL validation, wrong grain, retrieval/citation errors.
Chọn Gemini thủ công không fallback ngược về Knowledge.

Response/history có `requested_model`, `used_model`, `fallback_used`,
`fallback_reason`. Model preference lưu theo conversation; response cũ không bị
đổi nhãn khi chọn model mới. Legacy conversation chưa có preference được đọc theo
quy ước Gemini, New Chat dùng default hiện hành.

**Logical call khác HTTP request.** SDK retry và structured-output retry có thể
làm requests/quota/cost cao hơn. Lượt Gate D chỉ đo stage/method calls, không có
transport attempt instrumentation; không được khẳng định HTTP count chính xác.

## 8. Dữ liệu, workspace và schema động

### 8.1 Dữ liệu upload không bị ép vào schema bán hàng

Một dataset workspace có thể chứa nhiều bảng CSV/XLSX và nhiều tài liệu
PDF/DOCX/TXT/MD. Ví dụ các lĩnh vực đã được dùng để test: doanh thu, học phí,
giờ làm, tồn kho, vận tải và điện năng.

Bảng upload được parse/infer kiểu, chuẩn hóa tên cột và lưu source-header mapping.
Backend tạo physical table trong schema `uploaded_data`, thường dạng
`dataset_<random hex>`. LLM phải copy **physical identifier** đầy đủ từ context,
không dùng display label/tên file làm SQL identifier.

CSV/XLSX chỉ thêm bảng, không cần generation hoặc embedding. Tài liệu cần parse,
chunk rồi embedding nên chịu provider-data gate và quota.

Không cam kết “mọi bộ dữ liệu” đều truy vấn được. Phụ thuộc chất lượng header,
type inference, formula/units, semantic clarity, relationship evidence và SQL subset.
Không có catalog metric nghiệp vụ để chứng minh mọi cột số là measure đúng.

### 8.2 Metadata PostgreSQL chính

| Bảng / nhóm | Vai trò |
| --- | --- |
| `users` | Google issuer/subject identity, active/profile |
| `user_sessions` | Hash opaque session, expiry/revocation |
| `oidc_flows` | OIDC state/nonce/PKCE browser-bound flow |
| `datasets` | Workspace và owner |
| `dataset_tables` | Registry bảng vật lý, columns/types/header mappings/rows |
| `dataset_documents` | File metadata/hash/chunk count, không giữ binary gốc |
| `document_chunks` | Text/evidence/hash/vector(768), scope dataset/document |
| `dataset_relationships` | Exact key pair, revision, verified statistics/origin |
| `chat_conversations` | Owner, dataset, title, model preference |
| `chat_messages` | User/assistant/error, content và response evidence snapshot |
| `resource_limits`, `resource_leases` | Quotas/concurrency vận hành |
| `schema_migrations` | Version ledger do migration/setup quản lý |
| `categories/products/orders/order_items` | Schema commerce demo lịch sử |
| `uploaded_data.dataset_*` | Các bảng người dùng upload |

Demo có schema/corpus read-only riêng. Workspace upload không được tự dùng demo
để bù bảng hoặc tài liệu thiếu. Chunks `dataset_id IS NULL` là corpus mặc định,
không phải nguồn dự phòng cho workspace khác.

### 8.3 Xóa nguồn và retention

Đã có UI/backend xóa từng bảng, từng tài liệu và toàn workspace:

- Xóa bảng: đúng physical table + metadata + quan hệ liên quan, không DROP CASCADE
  tùy ý; transaction/locks và identifiers từ registry authorized.
- Xóa tài liệu: metadata/chunks/embeddings của đúng nguồn.
- Xóa riêng nguồn giữ evidence snapshot lịch sử; lịch sử có thể lỗi thời.
- Xóa workspace có chats: mặc định 409; cần xác nhận rõ xóa conversations liên quan.
- Không tự chuyển chat sang demo hoặc workspace khác.
- Không có trash/undo trong UI. Xóa là hành động vĩnh viễn, cần xác nhận mục tiêu.
- Xóa source trong ứng dụng không xóa file gốc trên máy người dùng.

Workspace synthetic ID 8 từng được duyệt xóa trong đợt riêng và đã xóa; quyền đó
không áp dụng workspace 13 hiện tại hoặc bất kỳ dữ liệu nào khác.

## 9. Authentication, isolation và Guest

### 9.1 Google login tùy chọn, invite-only

Người dùng mở trang vào Guest; muốn dữ liệu/history lâu dài thì đăng nhập Google.
OIDC Authorization Code + PKCE S256 qua Authlib; validate signature/JWKS, issuer,
audience/claims, nonce/state và email verified. Identity theo `(issuer, subject)`,
không lấy email làm subject. Backend allowlist bắt buộc, rỗng là từ chối tất cả.

Người test cần được thêm cả Google OAuth test users khi áp dụng và backend
allowlist. Client ID/Secret là OAuth credential riêng, không phải Gemini API key.
Callback local phải đúng `http://127.0.0.1:8080/api/auth/callback`, không trộn
localhost/127.0.0.1 hoặc sai port/path.

Flow lưu PostgreSQL có expiry/binding, consume atomically để chặn replay. Không
lưu OAuth access/refresh/ID tokens lâu dài. Opaque session ở HttpOnly cookie;
DB lưu hash, user FK, expiry/revocation. Session default 12 giờ. Production yêu
cầu HTTPS/Secure và cookie `__Host-`; HTTP chỉ cho local development hợp lệ.

`GET /api/auth/me` trả current identity/CSRF cho UI. CSRF nằm trong memory, không
localStorage. Mutations/upload cần Origin hợp lệ + X-CSRF-Token. Không bypass
Google bằng session giả hoặc lấy cookie/token để đưa vào terminal/chat.

### 9.2 Owner isolation và frontend state

Authorize owner trước khi scan schema/categorical values, parse công việc ứng dụng,
embedding/generation hoặc execution. Dataset/conversation là owner boundary;
tables/documents/chunks/messages kế thừa parent. Foreign resource thường 404,
unauthenticated 401, CSRF/policy 403, quota 429.

SQL allowlist chỉ gồm authorized workspace; RAG filter dataset trong DB. Reader
role không được SELECT session/OIDC/quotas/history/migration metadata. Đây là
application authorization, **không phải RLS hoặc database riêng từng user**.

Frontend AuthBoundary revalidate session/focus, abort/epoch stale responses khi
đổi session/user, không lưu private data/tokens trong browser storage. Bản sửa
regression giữ App khi kiểm tra lại cùng user/CSRF để không mất preview upload
hợp lệ; đổi phiên thực sự thì unmount/clear state.

Google login thật đã thực hiện bởi người dùng trên tab 8080 trong lượt Gate D.
Không coi session đó còn hiệu lực vĩnh viễn; tiếp tục công việc cần kiểm tra lại.

### 9.3 Guest mode

Guest dùng `/api/guest/*`, không mở private endpoints. File/chunks/vectors giữ
RAM theo capability/TTL, SQL chạy PostgreSQL TEMP trên connection riêng với role
giới hạn. Không ghi Guest corpus vào tài khoản hoặc private conversation DB.

Chat Guest là memory trang; refresh về phiên/chat trống, không phải lỗi history.
Không hứa chuyển Guest history/files tự động sang tài khoản sau login.
TEMP có thể dùng disk nội bộ PostgreSQL; không quảng cáo forensic zero-copy.

Defaults hiện hành (runtime `.env` có thể override, cần đọc safe subset khi vận hành):

| Giới hạn Guest | Default |
| --- | --- |
| TTL | 600 giây |
| Questions/session | 5 |
| Files/session | 8 |
| File size | 5 MiB |
| Rows/columns | 5.000 / 30 |
| Parse RAM estimate/session/toàn hệ thống | 32 MiB / 128 MiB |
| Chunks/session | 32 |
| Prompt characters | 2.000 |
| Request timeout | 120 giây |

Local Guest hiện chạy một API worker vì store RAM không phải distributed store.
Có quotas IP/session/global và worker/resource limits; không dùng refresh để né.

Defaults authenticated: 30 chats/user/giờ, 60 writes upload/user/giờ, 180 previews/
user/giờ, concurrency 1/user và 4/system, 20 datasets, storage budget 100 MiB.
Đây là giá trị source hiện hành, không lấy số cũ 10 uploads/h trong tài liệu auth
lịch sử làm cấu hình runtime chắc chắn. Quota storage chưa tính history toàn bộ.

## 10. SQL correctness contracts đã được harden

### 10.1 Thời gian

- Business timezone `Asia/Ho_Chi_Minh` đặt transaction-local trong SQL executor.
- Month boundaries dùng `[start, next_start)` theo giờ Việt Nam.
- TIMESTAMPTZ filters phải thể hiện instant/offset đúng, không cast offset-bearing
  literal sang timestamp-naive làm mất offset.
- Parser phân biệt DATE, TIMESTAMP và TIMESTAMPTZ; mixed aware/naive không được
  âm thầm suy đoán chung rồi import sai.
- Không chỉnh timezone global database hoặc ALTER/backfill timestamps legacy.
- Dữ liệu naive cũ không tự phục hồi offset đã mất; cần file gốc/mapping riêng.

Tests biên tháng/năm, offsets +07/Z/-04, CSV/XLSX, writer UTC/giờ Việt Nam đã có.

### 10.2 Decimal, BIGINT, zero và NULL

- PostgreSQL NUMERIC/Decimal ra JSON dưới dạng decimal string, giữ digits/scale.
- Integer ngoài ±(2^53−1) thành exact string để frontend không mất precision.
- NULL là JSON null; `"0"`/`"0.00"` là giá trị zero thật.
- SUM/AVG all-null không tự COALESCE thành zero.
- COUNT(*) là số dòng; COUNT(column) là non-NULL values, không được đánh tráo.
- Frontend ResultTable và history metadata giữ contract lossless.
- Grounding prompt yêu cầu không invent/round/float/scientific notation.
- Prompt không chứng minh model luôn trả lời đúng; phải so answer với rows/oracle.

### 10.3 Validator/executor

- Chỉ một SELECT trong SQL subset cho phép.
- Cấm DML/DDL, multiple statements, SELECT INTO, locks, catalog/system tables,
  CTE/subquery/window và functions ngoài allowlist.
- Source columns phải tồn tại; output alias không cấp quyền cho cột giả.
- ORDER BY/GROUP BY alias resolution theo scope và collision rules PostgreSQL.
- Wrong owner/schema/table/qualifier, ambiguous bindings bị chặn.
- Executor dùng reader connection, READ ONLY transaction, timeout (default 5s),
  bounded fetch (default 200 rows; vượt cap là lỗi), rollback khi kết thúc.
- Không có câu trả lời tự tạo nếu draft/validation/execution/generation thất bại.

SQL hợp lệ cú pháp + chạy được không đồng nghĩa đúng nghiệp vụ. JOIN grain,
fact measure, entity identity và independent result oracle vẫn là bắt buộc.

## 11. JOIN v1 hiện hỗ trợ gì và không hỗ trợ gì

Tên feature vẫn là JOIN v1 dù đã mở tối đa ba bảng. Không hiểu “v1” là chỉ hai
bảng hoặc là JOIN tùy ý. Flag repository mặc định OFF, local hiện ON.

### 11.1 Contract hai/ba bảng

Hai bảng cần một approved relationship. Ba bảng cần đúng hai approved edges trên
ba bảng, một root fact và graph không mơ hồ:

```text
chain:       fact -> dimension 1 -> dimension 2
hoặc star:   fact -> dimension 1
                  -> dimension 2
```

Giới hạn giữ nguyên:

- Tối đa ba distinct table bindings, hai edges, cùng authorized workspace/owner.
- Chỉ INNER JOIN, ON đúng một equality trên exact approved key pair mỗi cạnh.
- Fact được xác định bằng backend metadata/root graph, không theo vị trí FROM
  hoặc câu hỏi nhắc tên dimension trước.
- Explicit table aliases, qualified source columns.
- Aggregate chỉ root fact measure; intermediate dimension không thành fact mới.
- Không hai facts qua shared dimension, cycles, fan-out, ambiguity/multiple paths.
- Không outer/cross/natural/using/self/composite-key JOIN.
- Không DISTINCT, aggregate arithmetic, FILTER hoặc complex aggregate ngoài contract.
- Không tự thay key/cột/metric/grain để làm query vượt validation.

### 11.2 INNER JOIN đảo chiều

Đã có sửa an toàn cho model sinh dimension-first nhưng ON là đúng approved
equality. AST chỉ được chuẩn hóa khi shape/bindings/graph/keys hợp lệ; sau đó
vẫn qua column/aggregate/grain validation và execution guard.

Không chuẩn hóa wrong key thành right key. Không cho arbitrary JOIN. Cả hai chiều
cần cùng multiset rows với PostgreSQL oracle. Một live draft fact-first PASS
không tự chứng minh normalization đã được exercise trong request đó.

### 11.3 Aggregate aliases — trung tâm blocker hiện tại

| Biểu thức | Contract |
| --- | --- |
| COUNT(*) | Alias `fact_row_count` hoặc `matched_row_count` |
| COUNT(f.column) | Alias `fact_value_count` cho non-NULL fact values |
| COUNT(verified fact join key) với row alias | Có narrow proof cho phép canonicalize COUNT(*) vì INNER equality loại NULL key |
| COUNT(f.other_id) với row alias | Không tự suy ra NOT NULL, vẫn fail-closed |
| SUM/AVG | Direct numeric root fact measure; không dùng reserved count alias |
| SUM/AVG dimension | Bị chặn |
| SUM/AVG verified numeric JOIN identifier | Bị chặn dù có kiểu BIGINT/NUMERIC |

`count_star_alias` nghĩa COUNT(*) không gắn alias được contract chấp nhận.
`count_column_alias` nghĩa COUNT(column) không thỏa alias/semantics được phép;
không tự suy ra chính xác raw column từ code này.

### 11.4 Entity grain hardening mới nhất

Người dùng đã duyệt siết **fail-closed theo ID**, không tự chèn ID vào model SQL:

- Aggregate có dimension attributes phải GROUP BY approved target identifier của
  dimension đó, cùng các display fields cần thiết.
- Chỉ group name có thể gộp hai entity trùng tên, dù tổng toàn cục vẫn đúng.
- Thiếu identity key thì từ chối, không sửa SQL sang grain khác.
- Group theo category chung như thành phố mà không entity ID hiện có thể bị từ
  chối; cần contract grain khác được duyệt riêng nếu muốn hỗ trợ.
- ROLLUP/CUBE/GROUPING SETS không thuộc contract, dù GROUP BY có ID.

### 11.5 Execution guard

Sau validation, trước/đang execution phải xác minh lại owner/workspace/relation
IDs/revision/current metadata dưới locks. Quan hệ bị xóa, đổi nguồn, stale hoặc
không thuộc request được duyệt thì chặn; không chỉ tin snapshot prompt cũ.

## 12. Tự nhận quan hệ khi upload

Đã triển khai trong authenticated và Guest paths. Không cần LLM/provider call.
Nhưng **không tự gán được mọi quan hệ của mọi schema**.

`relationship_detection.py` hiện:

1. Xét source key có suffix `_id` hoặc `_code`, kiểu TEXT/BIGINT.
2. Target table label được normalize Unicode/dấu, separator, tiền tố số và
   plural English đơn giản.
3. Prefix key phải khớp **exact normalized entity name** của target, không match
   mọi mô tả dài bắt đầu tương tự.
4. Target key phải đúng tên source key hoặc `id`/`code` cùng kiểu.
5. Candidate phải duy nhất; không đoán giữa nhiều keys/directions cùng cặp bảng.
6. Chỉ candidate liên quan bảng vừa upload; không backfill toàn database cũ.
7. Gọi full-data verification qua PostgreSQL: hai bảng có dữ liệu, type giống hệt,
   không NULL keys, target unique, zero orphans, cardinality kiểm thật.
8. Auto chỉ kích hoạt many-to-one. One-to-one không đủ chứng minh fact direction
   tự động, phải manual theo contract.

Automatic record có `origin="automatic"`, `confirmed=false`, valid statistics và
revision; **không giả thành người dùng đã bấm xác nhận**. Approved backend có thể
bao gồm quan hệ automatic đã kiểm chứng hoặc manual còn valid/revision đúng.

Manual UI: Quản lý dữ liệu -> Liên kết bảng -> chọn fact/key/dimension/key ->
preview statistics/reasons -> xác nhận rõ -> lưu revision. Manual verification
chấp nhận một số key types rộng hơn automatic nhưng không tự cast/normalize giá trị.

Ví dụ synthetic logistics:

- `03_don_giao_hang.tai_xe_id -> 02_tai_xe.tai_xe_id` auto khớp sau bỏ số thứ tự.
- `02_tai_xe.kho_id -> 01_kho_dieu_phoi.kho_id` không exact entity name `kho`;
  sau hardening naming conservative cần manual.
- User từng duyệt thêm đúng hai quan hệ đã kiểm chứng cho workspace lịch sử ID
  12 ở đợt riêng; không lấy quyền đó để sửa các workspace khác.

Full key overlap không đủ chứng minh cùng miền nghiệp vụ. Tránh match
`student_archive` như `students` chỉ do prefix; đã có regression để chặn.

## 13. Schema context thực sự được dựng như thế nào

Authenticated route authorize workspace -> `build_workspace_context()` trong
`dependencies.py` -> lấy approved relationships theo owner/dataset khi flag ON ->
`build_dataset_sql_context()` trong `datasets/context.py`.

Context immutable request-local chứa:

- `schema_context`: schema/types/source headers/row counts/categorical values/rules.
- `routing_context`: source capability descriptions, không phải mọi SQL-specific rules.
- `table_columns`, `allowed_schemas`, `column_types`.
- `dataset_id`, `owner_user_id`, `has_documents`, `approved_joins`.

Generator nhận SQL context; router nhận routing context. Backend tạo SQL validator
max_tables 1 nếu không edge, 2 nếu một edge, 3 nếu >=2 edges (actual SQL vẫn phải
đúng shape/tree). Document count thực được đưa vào context; SQL schema không chứa
document text **không có nghĩa** workspace không có policy.

Context ghi rõ:

- Display label/file name không phải identifier; copy exact schema.physical_table.
- Approved equality, fact/dimension direction và physical FROM/JOIN fragment.
- Aggregate example dùng numeric source measure, không áp business metric tự đoán.
- Safe three-table root fact fragment cho graph hợp lệ (bounded examples).
- COUNT aliases, NULL/zero semantics, group ID và unsupported cases.
- Cell/headers/observed categorical values là untrusted data, không instruction.

Trong Gate D mới nhất, safe diagnostics cả tám request xác nhận **3 allowed
tables và 2 approved edges**. Do đó không có bằng chứng context thiếu relationship
cho workspace synthetic 13. Tuy vậy chưa đo quality/token attention hoặc lưu raw
rejected draft để giải thích mọi quyết định của model.

Không thêm schema agent/relevance selector hoặc tự bỏ hết guard chỉ từ giả thuyết
context dài. Cần fake gateway capture prompt synthetic/offline để chứng minh trước.

## 14. RAG, Hybrid và lỗi DOCX mới phát hiện

### 14.1 Ingestion/retrieval

PDF có text layer, DOCX, TXT, MD được parse thành text; không OCR PDF scan.
Tài liệu có caps kích thước/trang/chars/archive/extraction; binary gốc không lưu.
Chunking heading-aware, target khoảng 300 words, overlap 30 words khi cần chia.
Hash giúp dedup/không embedding lại nguồn không đổi. RAG truy hồi dataset-scoped,
default top_k=3; không lấy private chunks của workspace khác.

AnswerDraft chỉ được cite chunk IDs thực retrieved; citation ngoài tập hoặc không
có citation cần thiết bị từ chối. Citation hợp lệ không tự chứng minh conclusion
đúng; vẫn phải đọc evidence và so điều kiện.

### 14.2 Hybrid implementation hiện hành

`HybridPipeline.run()` gọi SQL pipeline **trước**, sau đó retrieve và synthesize.
SQL pipeline hiện tự ground answer trước, dù Hybrid cuối còn một synthesis riêng.
Bởi vậy đường full success dự kiến gồm router + SQL draft + SQL grounding +
Hybrid grounding = 4 logical generation calls; thêm một query embedding.

Nếu SQL generation/guard dừng, Hybrid không retrieve và không dùng query embedding.
Không thay kiến trúc để “tiết kiệm một call” trong một lượt sửa reliability hẹp.

### 14.3 DOCX table evidence bug

Audit phát hiện parser trước đây chỉ đọc paragraphs nên mất policy nằm trong Word
tables. Đã sửa duyệt paragraph/table theo thứ tự, giữ giới hạn và từ chối nested
tables không hỗ trợ một cách rõ ràng.

Ba DOCX synthetic gốc từng cho 6/6/7 chunks, sau sửa 7/7/7; rule KPI thiếu trước
sửa đã xuất hiện. Offline fake-generation/RAG + real PostgreSQL cases đạt.

**Fix parser chỉ tác động ingestion mới.** Các DOCX đã ingest trước fix có thể
vẫn thiếu table chunks trong DB. Không tự sửa/re-embed dữ liệu cũ; duplicate hash
có thể chặn upload y hệt. Cần duyệt riêng nguồn/recovery/history/embedding budget,
không bypass dedup bằng sửa file cho khác hash chỉ để làm test xanh.

Không nhầm KPI trong DOCX cũ (ít nhất 8 đơn “Đã giao”) với policy Gate D mới
(tổng phí tất cả trạng thái >=500000.00); đây là hai fixtures khác nhau.

## 15. Dòng thời gian phát triển — điều đã làm và tại sao đổi phạm vi

Đây là tóm tắt theo mốc sản phẩm, không gán mọi số test lịch sử cho source hiện tại.

| Chặng | Đã làm / bài học |
| --- | --- |
| Phase 2 | Backend, PostgreSQL, SQL/RAG/Hybrid; Gemini smoke và embeddings; từng có router503 cần phân biệt upstream/config/schema/retry |
| Model selection | Người dùng chốt Gemini `gemini-3.5-flash-lite`; không còn dùng các tên model được nhắc thử trước đó |
| Git/secret hygiene | Tạo .env private, bỏ key khỏi example; người dùng đã thu hồi/thay key; GitHub CI dần bổ sung integration |
| Phase 3 | React/TypeScript, Nginx/Docker, responsive chat UI, deployment readiness local |
| UI refinements | Sidebar/composer/Markdown, compact evidence toolbar, model selector/history, không redesign framework |
| Dev environment | Đưa requirements runtime về root, venv backend/.venv, sửa Antigravity interpreter/activation |
| Dataset workspace | Nhiều CSV/XLSX/tài liệu trong cùng workspace, schema/context dynamic, SQL/RAG/Hybrid scope đúng |
| Hai provider | Knowledge mặc định + Gemini manual; provenance/fallback explicit; embedding tách riêng |
| Timezone | Fix transaction business timezone và tháng VN cho cả hai providers; tests biên tháng |
| CI PostgreSQL | Test DB độc lập không API key; không dùng main cho integration |
| Multi-domain | Bỏ sales assumptions cho upload datasets, test học phí/HR/logistics/energy |
| CRUD deletion | Xóa file/bảng/tài liệu/workspace + explicit consent xóa history; transaction/rollback |
| Auth multi-user | Google OIDC invite-only, opaque sessions, CSRF, repositories theo owner; clean main volume được duyệt riêng |
| Guest | Optional login, upload tạm RAM/TEMP/TTL, giới hạn session/system, private namespace tách biệt |
| Regression stabilization | Nginx upload cap, preview quotas, same-session focus không mất upload, input editable, gates rõ ràng, trusted proxy IP |
| Correctness hardening | DATE/TIMESTAMP/TIMESTAMPTZ, Decimal/BIGINT lossless, alias validation, tests PG thật |
| JOIN v1 hai bảng | Metadata additive migration/backup restore rehearsal, manual approved keys, SELECT-only/grain guard |
| JOIN direction | Canonicalize safe INNER order, không sửa sai khóa; nhiều UNSUPPORTED cũ chỉ có aggregate code chung |
| Auto relationships | Naming candidate + full data verification, origin automatic/manual, không LLM đoán |
| JOIN ba bảng | Tree/root fact, hai edges, safe normalization, guards cả hai revisions, golden tests |
| Logistics fix | Numbered labels và relationship metadata thiếu ở workspace12; đã kiểm rows SQL thật, chưa đủ chứng minh live model đúng |
| Root audit | Duplicate-name grain, numeric key measures, reserved count aliases, subtotal grouping và DOCX table evidence bugs |
| Gate D mới nhất | Authenticated UI tám synthetic probes: 3PASS/5FAIL; xác định count alias refusals và generator unsupported |

### Vì sao phần JOIN sửa nhiều lần mà người dùng vẫn thấy không chạy?

Các lần sửa giải quyết các failure modes khác nhau, không phải một bug duy nhất:

1. Workspace thật từng thiếu relation, nên JOIN bị cấm đúng theo context.
2. Khi có relation, model có thể đảo FROM/JOIN; cần safe equivalence proof.
3. Khi keys/order hợp lệ, aggregate expression/alias vẫn có thể sai contract.
4. Dữ liệu tên duy nhất làm golden tests cũ không thấy gộp sai entity trùng tên.
5. Guest fixture English/simple không đại diện authenticated physical identifiers,
   tiếng Việt, dataset logistics hoặc nhu cầu thêm documents/Hybrid.
6. Old log chỉ có `join_aggregate`/generic frontend text, chưa đủ phân biệt subtype.
7. Test fake gateway chứng minh guard/pipeline hoạt động với draft được định trước,
   không chứng minh provider sẽ sinh đúng draft trên UI.
8. Một câu PASS lịch sử có thể dùng source/guard khác hoặc chưa test cùng grain.

Vì vậy không nên tiếp tục patch validator theo ảnh “chưa thể trả lời”. Phải lấy
safe stage/reason, source/runtime version và cùng metadata path, rồi tái hiện offline.

## 16. Audit root causes mới nhất và các bản sửa đã deploy

| ID | Vấn đề có bằng chứng | Sửa đã triển khai |
| --- | --- | --- |
| J01 | GROUP BY chỉ name gộp sai entity khác ID | Yêu cầu approved target key, fail-closed thiếu ID |
| J02 | SUM/AVG numeric fact JOIN key bị coi là measure | Chặn verified identifier measure |
| J03 | Prefix labels dễ auto-link entity không đúng nghĩa | Exact normalized entity name; mô tả/dịch cần manual |
| J04 | Generic refusal không xác định stage | Bounded safe diagnostics/correlation/stage/reason |
| J05 | Workspace logistics thiếu metadata | Sửa numbered naming và thêm đúng hai edges được duyệt ở đợt riêng |
| J06 | SUM AS fact_row_count làm grounding hiểu sai | Reserved count aliases không dùng cho SUM/AVG |
| J07 | GROUP BY có ID nhưng ROLLUP tạo subtotal | Chặn ROLLUP/CUBE/GROUPING SETS modifiers |
| J08 | DOCX tables mất rule KPI | Parse blocks paragraph/table đúng thứ tự, giới hạn giữ nguyên |

J01/J02/J06/J07 là hardening correctness; không được bỏ để model dễ pass hơn.
J04 không bật raw production trace hoặc external observability framework.

## 17. Gate D: bằng chứng live mới nhất đầy đủ

### 17.1 Quyền đã duyệt và cách giữ budget

Chủ dự án duyệt tối đa 8 synthetic questions, 26 logical generation calls,
3 embedding calls; SDK retries có thể tăng HTTP requests.

Đã chạy 21/10/2026, khoảng 09:32–09:43 giờ Việt Nam, hoàn tất evidence 09:44:51.
Google session do chính người dùng đăng nhập bình thường, không auth mock.
Chỉ workspace synthetic **ID13**, tên `Root audit synthetic · 21-10-2026`.

Order có chủ đích: sáu SQL trước khi workspace có documents -> thêm đúng một
policy chunk -> hai Hybrid. Mỗi câu chỉ gửi một lần bằng UI, không retry chat.
Không Knowledge/Gemini calls nào khác để “kiểm tra lại cho chắc”.

Đã dùng: **8 chats, 19 logical generation stages, 1 document embedding**.
Query embeddings: **0** vì cả hai Hybrid fail ở SQL trước retrieval. Phần trần
chưa dùng không cho phép thêm probe thứ chín hoặc tự lặp một câu đã fail.

### 17.2 Fixture và oracle chốt trước provider calls

| Synthetic table label | Rows | Vai trò |
| --- | --- | --- |
| `01_kho_dieu_phoi` | 5 | Warehouse dimension |
| `02_tai_xe` | 15 | Driver dimension, dẫn đến warehouse |
| `03_don_giao_hang` | 50 | Root delivery fact |

Hai keys: orders.tai_xe_id -> drivers.tai_xe_id, drivers.kho_id -> warehouses.kho_id.
Source/target nulls, target duplicates, orphans đều 0. One automatic/one manual
edge ở fixture13; không sửa source rows của workspace người dùng.

Independent oracle là SELECT PostgreSQL tự viết trước khi model sinh SQL,
không lấy generated SQL làm oracle. 50 fact rows, 15 driver groups, 5 warehouse
groups, tổng `2472500.00`, 4 NULL phí và 3 zero phí.

| Warehouse ID | SUM tất cả trạng thái | COUNT(*) | KPI policy mới |
| --- | --- | --- | --- |
| KHO01 | 393500.00 | 10 | Chưa đạt |
| KHO02 | 598000.00 | 10 | Đạt |
| KHO03 | 502000.00 | 10 | Đạt |
| KHO04 | 439000.00 | 10 | Chưa đạt |
| KHO05 | 540000.00 | 10 | Đạt |

Policy `live_gate_d_kpi.md`: tổng phí >=500000.00, tất cả trạng thái, xác định kho
qua tài xế/kho_id, không group theo tên đơn thuần; SUM bỏ NULL, giữ zero hợp lệ.
Policy ngắn parse/chunk thành đúng một chunk trước ingestion; UI xác nhận một
document, một chunk; vector PostgreSQL 768 dimensions.

### 17.3 Bốn câu hỏi, mỗi model dùng một lần

Q1 — một bảng:

> Liệt kê don_id, phi_giao_vnd và trang_thai của toàn bộ đơn giao hàng, tính tất
> cả trạng thái; sắp xếp don_id tăng dần. Giữ nguyên giá trị 0 và NULL, không
> thay NULL bằng 0.

Q2 — hai bảng:

> Theo từng tài xế, cho biết mã tai_xe_id, tên ten_tai_xe, tổng phi_giao_vnd và
> số dòng đơn giao hàng, tính tất cả trạng thái. Phân biệt tài xế theo mã ID;
> đếm dòng đơn, không đếm tài xế.

Q3 — ba bảng:

> Theo từng kho, cho biết mã kho_id, tên ten_kho, tổng phi_giao_vnd và số dòng
> đơn giao hàng, tính tất cả trạng thái. Dùng liên kết đơn giao hàng → tài xế
> → kho; phân biệt kho theo mã ID.

QH — Hybrid:

> Theo tài liệu live_gate_d_kpi.md, những kho nào đạt KPI tổng phí? Với từng
> kho, cho biết mã kho_id, tên ten_kho, tổng phi_giao_vnd của tất cả trạng thái,
> số dòng đơn và kết luận đạt/chưa đạt. Kết hợp dữ liệu đơn giao hàng → tài xế
> → kho với điều kiện trong tài liệu, phân biệt kho theo mã ID.

### 17.4 Kết quả từng probe

| Probe | Router | Final | Rows/answer hoặc failure stage | Logical generation |
| --- | --- | --- | --- | ---: |
| K1 | SQL | SQL | PASS 50 rows, answer giữ Decimal/zero/NULL | 3 |
| K2 | SQL | UNSUPPORTED | join_aggregate / count_star_alias | 2 |
| K3 | SQL | UNSUPPORTED | join_aggregate / count_star_alias | 2 |
| G1 | SQL | SQL | PASS 50 rows, answer giữ Decimal/zero/NULL | 3 |
| G2 | SQL | SQL | PASS 15 driver groups, exact IDs/name/SUM/COUNT + answer | 3 |
| G3 | SQL | UNSUPPORTED | join_aggregate / count_column_alias | 2 |
| KH | HYBRID | UNSUPPORTED | join_aggregate / count_star_alias | 2 |
| GH | HYBRID | UNSUPPORTED | generator_unsupported | 2 |

K = Knowledge, G = Gemini. Cả tám used model đúng requested selection,
fallback_used=false. Ba SQL success chỉ chứa đúng synthetic tables cần thiết,
validator/execution_guard/SQL_execution PASS; rows so exact oracle, không chỉ tổng.

Năm FAIL đều chưa tới executor, không rows/sources giả; response có error=null
và HTTP nghiệp vụ thành công không có nghĩa acceptance PASS. Generic UI refusal
là UX có chủ đích, không lộ internal SQL/error cho người dùng cuối.

### 17.5 Những kết luận được và không được phép rút ra

Đã chứng minh:

- Context13 có đủ 3tables/2edges, owner binding/approval/schema stages thành công.
- K2/K3/KH sinh draft rồi bị COUNT(*) alias guard chặn.
- G3 sinh draft rồi bị COUNT(column) alias/semantics guard chặn.
- GH generator chủ động trả unsupported trước validator/executor.
- Không quan sát provider-outage 503 làm nguyên nhân các lỗi trên.
- Guard fail-closed hiệu quả, nhưng user-facing reliability JOIN chưa đạt.

Chưa chứng minh:

- Tên raw alias/cột bị lỗi trong rejected draft; production không lưu raw SQL đó.
- Grain hoặc các bước sau chắc chắn đúng nếu chỉ sửa alias đầu tiên.
- Nguyên nhân nội bộ model GH quyết định unsupported; safe code không giữ raw reason.
- Retrieval quality/citations/conclusion Hybrid mới nhất, vì chưa gọi retrieval.
- Mọi câu SQL một bảng/two-table đều đúng chỉ từ Q1/G2.
- Accuracy tổng thể là 37,5%; 3/8 chỉ của matrix cố định rất nhỏ này.
- Không có SDK retry; HTTP request count không instrument.

### 17.6 History và integrity

Tạo 4 conversations / 16 messages cho đúng synthetic 13. Reload thật trang và mở lại
cả bốn conversations; giữ tám answers/refusals, model labels, rows 50/50/15.
Mở evidence table Gemini15 rows sau reload; đối chiếu DB content/response_metadata
với evidence lúc nhận kết quả, không gọi AI mới để kiểm tra history.

26 bảng nghiệp vụ cũ giữ counts/hashes giống baseline, aggregate SHA-256:
`f73b828698b29380b28b5ae89a654df52115bef858ed7a4c246a2b11c84fa736`.

Phép so này loại đúng synthetic13 (gồm messages thuộc conversations13), ba bảng
auth thay đổi do Google login bình thường, counters/leases vận hành. Không gọi
đây là toàn database byte-for-byte không đổi. Auth identity/session không reset.

## 18. Docker local, volumes, backup và recovery

### 18.1 Đúng runtime đang phục vụ 8080

| Service | Container | ID ngắn | Host mapping |
| --- | --- | --- | --- |
| web | `shopquery-ai-web-1` | `2af67d527f2e` | 127.0.0.1:8080 ->80 |
| api | `shopquery-ai-api-1` | `ea2a3f3688ea` | 127.0.0.1:8001 ->8000 |
| db | `shopquery-ai-db-1` | `511c4f5aaccc` | 127.0.0.1:15432 ->5432 |

Lúc viết handoff cả ba healthy. Health gần nhất trả
`{"status":"ok","service":"ShopQuery AI"}`.

Actual Compose files trên máy này:

1. `compose.yaml`
2. `.env.compose-ui.yaml` (local ignored override)
3. `.env.join-v1.yaml` (local ignored override)

Main DB tên `shopquery`, volume **`shopquery-ai_postgres_auth_20261019`**.
Volume **`shopquery-ai_postgres_data`** là archived/legacy, vẫn phải giữ.

**Không chạy base Compose một mình trên máy nghiệm thu này**: defaults trong
repository là API8000/DB54321 và volume cũ, khác actual overrides. Trong container
app kết nối `db:5432`, không dùng host15432 cho giao tiếp container-to-container.

Read-only status command:

```powershell
Set-Location 'C:\Work\ShopQuery AI'
docker compose -p shopquery-ai -f compose.yaml -f .env.compose-ui.yaml -f .env.join-v1.yaml ps
Invoke-RestMethod 'http://127.0.0.1:8080/api/health'
```

Không dump resolved Compose/env ra báo cáo vì có secrets. Lượt Gate D đã so
runtime với resolved Compose, 0 khác biệt môi trường; không rebuild/recreate.

API image digest:
`09fb41dc043ee14bf52de6baf9d0a611f28287c87e599632e03b2f7aeaabf9d7`.
Web image digest:
`5ca6e17125f12574cf8cdf4d030b6a0a209007e9469b264e94e6d98056090146`.
71 app Python modules local/runtime đã khớp, map hash:
`715c5b01327e970c67930c304529c6bce5f44a38be82231512885f22c770c167`.

### 18.2 Migration lịch sử, không chạy lại

JOIN metadata migration version `002_confirmed_relationships` là additive:
dataset_relationships + scoped unique index/version marker/revoke reader metadata;
advisory lock, transaction, lock/statement timeouts, idempotency. Không startup
migration tự động; không DROP/TRUNCATE business tables hoặc đổi legacy timestamps.

Quy trình trước main đã được yêu cầu backup mới ngoài repo, restore clone cô lập,
schema/owner/count/fingerprint comparisons, repeat/rollback tests. Lúc restore
từng có hai CHECK definitions khác cách biểu diễn; chỉ cho phép ngoại lệ đúng
hai fully-qualified constraints/cặp expressions đã chứng minh tương đương, không
so sánh tổng quát xóa mọi cast. Các chi tiết exact phải đọc evidence deployment
trước mọi migration tương lai; handoff không cấp quyền bypass constraint checks.

Không lặp lại backup/restore/migration chỉ để sửa prompt/COUNT offline.

Một backup JOIN lịch sử đã ghi nhận (không khẳng định là backup mới nhất hiện tại):
`C:\Work\ShopQuery-Backups\join-v1-20261020-0047\main.dump`, 114902 bytes,
SHA-256 `A9B458A5EE1C21966F9407E659075D2EADF6E071B4E244B9E07A2C9F18078138`.
Nếu cần recovery phải xác minh lại file/target/freshness; không restore đè main
khi có các ghi mới chưa được xử lý theo kế hoạch.

### 18.3 Rollback ứng dụng và tắt JOIN

Recovery image tags đã giữ từ đợt audit:

- `shopquery-ai-api:rollback-root-audit-20261021`
- `shopquery-ai-web:rollback-root-audit-20261021`

Tắt JOIN khẩn cấp là đặt `SQL_JOIN_V1_ENABLED=false` trong override đúng và
recreate **chỉ API** bằng cùng ba Compose files sau khi được phép vận hành.
**Flag OFF không rollback schema/database**. Không dùng `git reset --hard`,
restore main, xóa metadata hoặc down -v như một “rollback nhanh”.

Không cần recreate PostgreSQL/web để sửa riêng Python API khi không có lý do.
API restart làm Guest RAM mất theo lifecycle; phải báo tác động này trước deploy.

Docker host có project khác. “Dọn Docker cho gọn” không cho phép xóa mọi stopped
container/image/volume. Chỉ exact disposable test resources đã xác minh label,
mounts và quyền xóa; giữ main/archived volumes, backups và recovery images.

## 19. UI, upload và các regression đã gặp

UI light/responsive, sidebar off-canvas trên màn nhỏ, composer đa dòng, model
selector; response có route/model, Markdown và compact evidence toolbar:
“Bảng dữ liệu”, “Xem SQL”, “Nguồn tham khảo”. Mỗi lần chỉ mở panel cần thiết.

Những lỗi lịch sử quan trọng đã sửa/đối chiếu:

- Nginx mặc định upload1MB làm mọi file có vẻ lỗi: proxy cap11MB để đủ multipart,
  backend account file cap10MB, Guest cap5MiB vẫn tách riêng.
- Gate tắt làm document ingest403 là privacy behavior, không phải parser lỗi.
- Preview và import đều tính quota trước đây gây cạn lượt: tách preview budget,
  UI đọc actual upload limits từ backend.
- Auth focus revalidation unmount làm mất upload draft cùng session: giữ state
  đúng phiên, epoch/abort ngăn stale private response khi đổi phiên.
- Input bị disable vì chưa dữ liệu/gate off/hết quota: giờ vẫn nhập/giữ draft,
  send giải thích lý do; không tạo conversation/answer giả.
- Forwarded IP không tin client tùy ý; chỉ trust đúng web proxy, Nginx overwrite.
- XLSX worksheet bounds/dates: calculate_dimension(force=True), validate ranges,
  XML lỗi thành422; không coi mọi read-only worksheet thiếu dimensions là hỏng.
- Same-file reselect sau import/delete cần reset file input để phát change.
- SQL context nhầm không có docs nếu chỉ nhìn schema: document count/capability
  rõ và RAG retrieval riêng.

Browser automation từng bị Work permissions tắt dù tab mở/Google login thành công.
Không đánh đồng ảnh người dùng đang đăng nhập với công cụ đã được cấp quyền đọc UI.
Sau khi quyền khả dụng, lượt Gate D đã điều khiển tab8080 thật thành công. Cửa sổ
Chromium automation riêng từng bị Google chặn “không an toàn”; không bypass
browser warning hoặc tự lấy session secrets để né. Hiện không cần mở OAuth mới
chỉ để đọc handoff.

Các screenshots báo lỗi cũ là evidence lịch sử, không phải trạng thái runtime mới.
History refusal cũ cũng không tự được tính lại sau deploy, phải phân biệt với
câu hỏi mới được gửi trong một budget riêng.

## 20. CI, tests và cách diễn giải kết quả

### 20.1 Kết quả đúng source đã deploy

Code source `50d7bac4e1f6af8adffeb8f317a458f637de7bb0` đã có CI xanh được xác minh
trong lượt trước:
https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39530792010

Docs HEAD `e2151a3d6b37f3a11e83f68553e5985bbe087deb` cũng đã được xác minh xanh:
https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39532429820

| Suite | Snapshot PASS |
| --- | ---: |
| Ruff backend | PASS |
| Backend unit | 594 |
| PostgreSQL integration | 513 |
| Backend tổng không-live | 1.107 |
| Golden PostgreSQL subset | 144, nằm trong513, không cộng thêm |
| Frontend Vitest | 66 |
| Frontend Playwright mock | 105 |
| FE ESLint/typecheck/build | PASS |

Các số này thuộc snapshot/source đã ghi, không phải test mới chạy lại trong lượt
viết handoff. CI không gọi Knowledge/Gemini/Google OAuth thật và không cần keys.

Trước đây commit2962fe2 từng có GitHub Actions state/timeout/rerun issue; người
dùng xác nhận xanh sau đó. Đó không phải source baseline hiện tại; không rerun
workflow cũ khi xử lý lỗi mới này. Không biến historical incident thành bằng
chứng outage gây mọi timeout hiện tại.

### 20.2 CI workflow hiện tại

`.github/workflows/ci.yml` có ba jobs:

1. Backend quality: Python3.11, uv sync locked, Ruff, unit không integration/live.
2. PostgreSQL integration: pgvector PG17 service độc lập, DB `shopquery_ci`,
   disposable setup/reader roles, provider keys/base URL rỗng, fallbackfalse,
   RUN_DATABASE_TESTS1; timeout job10phút.
3. Frontend quality: Node24/npmci, lint/typecheck/Vitest/build, Chromium và
   105 offline mock UI tests; artifact diagnostics chỉ khi fail, retention2ngày.

Không hạ/bỏ owner/CSRF/SQL-security tests để CI xanh. Kiểm tra run đúng SHA mới
sau push, không lấy pass local hoặc SHA cũ thay kết luận CI.

### 20.3 Local test safety

Integration fixtures có thể tạo/drop/seed/delete tables. **Tuyệt đối không chạy
integration trên `shopquery` main**. Guard yêu cầu explicit test URL, tên DB
`shopquery_ci` hoặc `shopquery_test_<suffix>`, đúng setup/testURL và không trùng
application DB cấu hình local. Dùng PostgreSQL container riêng.

Unit nên đặt flag JOIN OFF chỉ trong tiến trình pytest để giống CI mặc định;
tests JOIN tự bật flag với metadata đúng. Đã từng có test kế thừa local `.env`
JOINON làm fake fixture thiếu owner/repository fail, không được sửa security
chỉ để chấp nhận fixture sai environment.

Ví dụ offline unit, không sửa `.env`:

```powershell
Set-Location 'C:\Work\ShopQuery AI\backend'
$env:SQL_JOIN_V1_ENABLED = 'false'
uv run ruff check app scripts tests
uv run pytest -m 'not integration and not live'
```

Nếu chưa muốn dùng `uv`, interpreter thật nằm ở
`C:\Work\ShopQuery AI\backend\.venv\Scripts\python.exe`.

Trước integration phải cấu hình private URLs **chỉ DB test cô lập**, không copy
main URLs. Không đưa ví dụ chứa password vào handoff. Live suites là opt-in riêng;
không chạy `npm run test:e2e:*-live` hoặc live pytest chỉ vì muốn kiểm nhanh.

FE offline từ `frontend`: `npm run lint`, `npm run typecheck`, `npm test`,
`npm run build`; mockE2E dùng SHOPQUERY_E2E_START_SERVER1/BASE_URL5173 trong shell
test riêng, không tự chuyển nó sang thao tác main live UI.

## 21. Bản đồ source để tiếp tục có trọng tâm

Mọi path dưới đây tương đối với **`C:\Work\ShopQuery AI`**. Khi chỉ upload
handoff lên ChatGPT web, web không tự đọc được các file local này; cần đính kèm
source có chọn lọc nếu muốn review code thực tế.

### 21.1 Backend xử lý request và AI

| File | Vai trò |
| --- | --- |
| `backend/app/main.py` | App/middleware/routes lifecycle |
| `backend/app/api/routes.py` | Chat/conversations/upload/CRUD datasets/limits/health |
| `backend/app/api/models.py` | HTTP request/response contracts |
| `backend/app/dependencies.py` | Dựng pipelines request-local/context/owner guards |
| `backend/app/ai/chat.py` | Model service/attribution/whole-turn fallback |
| `backend/app/ai/providers.py` | Fixed registry, lazy provider/embedding builders |
| `backend/app/ai/gemini.py` | Google adapter/SDKretry/structured/text/embed |
| `backend/app/ai/inetcloud.py` | Knowledge ChatOpenAI adapter/schema retry |
| `backend/app/routing/router.py` | Structured RouteDecision/capability |
| `backend/app/routing/service.py` | SQL/RAG/Hybrid dispatch + safe refusals |
| `backend/app/routing/hybrid.py` | SQL then retrieve then evidence synthesis |
| `backend/app/core/config.py` | Settings/defaults/gates/quotas |
| `backend/app/core/errors.py` | Typed failures/internal codes |
| `backend/app/core/diagnostics.py` | Bounded safe stage diagnostics |

### 21.2 SQL/schema/relationships

| File | Vai trò |
| --- | --- |
| `backend/app/datasets/parser.py` | CSV/XLSX types/headers/Decimal/timestamps/limits |
| `backend/app/datasets/repository.py` | Owner CRUD/physical tables/categorical scans |
| `backend/app/datasets/context.py` | SQL/routing context từ metadata đúng workspace |
| `backend/app/datasets/relationship_detection.py` | Conservative naming candidates |
| `backend/app/datasets/relationships.py` | Full-data verification/stats/revision models |
| `backend/app/datasets/relationship_repository.py` | Persist/approve/execution_guard |
| `backend/app/api/relationship_routes.py` | Auth relationship list/preview/confirm/delete |
| `backend/app/text_to_sql/generator.py` | Prompt/SqlDraft/unsupported_reason |
| `backend/app/text_to_sql/validator.py` | AST/column/scope/shape validation |
| `backend/app/text_to_sql/join_policy.py` | Keys/order/tree/COUNT/aggregate/grain |
| `backend/app/text_to_sql/executor.py` | READONLY/timezone/timeout/cap/JSON lossless |
| `backend/app/text_to_sql/pipeline.py` | Draft->validate->guard->execute->ground |
| `backend/app/text_to_sql/schema_context.py` | Demo context/business timezone |

### 21.3 Auth/Guest/RAG/database

| Nhóm path | Vai trò |
| --- | --- |
| `backend/app/auth/` | OIDC/session/CSRF/limits/dependencies/routes |
| `backend/app/guest/` | Capability store/worker/limits/pipeline/routes/relationships |
| `backend/app/database/guest_access.py` | PostgreSQL Guest least-privilege setup |
| `backend/app/database/models.py` | SQLAlchemy metadata models |
| `backend/app/database/join_migration.py` | Additive migration002, không tự chạy |
| `backend/app/database/test_safety.py` | Guard integration target |
| `backend/app/conversations/repository.py` | Owner history/evidence persistence |
| `backend/app/rag/upload_parser.py` | PDF/DOCX/TXT/MD bounded extraction |
| `backend/app/rag/chunking.py` | Heading-aware chunking/hash |
| `backend/app/rag/repository.py` | Dataset-scope chunk/vector persistence/retrieval |
| `backend/app/rag/pipeline.py` | Query embed/retrieve/answer/citation validation |
| `backend/scripts/` | Setup/migration/ingest/rehearsal; không chạy bừa trên main |

### 21.4 Frontend và browser tests

| File / nhóm | Vai trò |
| --- | --- |
| `frontend/src/App.tsx` | Chat/history/workspace/model UI state |
| `frontend/src/api.ts` | Auth requests/CSRF/abort/errors |
| `frontend/src/guest.ts` | Guest client/lifecycle |
| `components/AuthBoundary.tsx`, `AccountMenu.tsx` | Session state/login/logout |
| `components/DatasetUploadDialog.tsx`, `GuestUploadDialog.tsx` | Upload/management flows |
| `components/RelationshipPanel.tsx` | Auto/manual/preview/confirm/delete relations |
| `components/ChatMessage.tsx`, `AssistantContent.tsx`, `ResponseEvidence.tsx` | Markdown/evidence/rendering |
| `components/ChatInput.tsx`, `ModelSelector.tsx`, `Sidebar.tsx` | Composer/model/history |
| `frontend/e2e/*-mock.spec.ts` | CI offline intercepted API tests |
| `frontend/e2e/join-providers-live.spec.ts` | Opt-in synthetic provider UI harness |
| `frontend/e2e/relationships-live.spec.ts` | Real upload/relationship UI lifecycle |
| `frontend/e2e/sql-correctness-live.spec.ts` | Real parser/preview SQL correctness UI |

Các paths `components/...` ở bảng này nằm dưới `frontend/src/`.

## 22. Regression tests cần giữ/mở rộng cho blocker COUNT

Các file liên quan có sẵn:

- `test_join_policy.py`, `test_join_order.py`, `test_three_table_join.py`.
- `test_join_audit.py`, `test_diagnostics.py`, `test_workspace_prompts.py`.
- `test_relationship_detection.py`, `test_relationships.py`.
- `test_join_order_integration.py`, `test_three_table_join_integration.py`.
- `test_join_golden_integration.py`, `test_join_counterexamples_integration.py`.
- `test_join_domains_integration.py`, `test_logistics_relationships_integration.py`.
- `test_relationship_api_integration.py`, `test_auto_relationships_integration.py`.
- `test_domain_pipelines_integration.py`, `test_routing_and_hybrid.py`.
- `test_timestamp_contract.py`, `test_decimal_contract.py`.
- `test_sql_alias_validation.py`, `test_sql_correctness_integration.py`.
- `test_auth_integration.py`, `test_guest_integration.py` và Guest relationship tests.
- `test_document_upload_parser.py` cho DOCX blocks/tables/caps.

Chúng nằm dưới `backend/tests/`. Không cần chạy mọi bộ lớn trước khi chưa thay code;
ưu tiên targeted tái hiện lỗi, sau fix mới chạy affected regressions/fullCI cần thiết.

Những assertions không được mất:

- Wrong owner/workspace rejected trước provider/executor.
- SELECT-only và forbidden AST/function/table/schema.
- Exact approved ON; wrong key không auto-repair.
- Stale/revoked revision bất kỳ cạnh nào của ba-table đều chặn.
- Dimension SUM/AVG, identifier SUM/AVG, COUNT nullable sai semantics bị chặn.
- Duplicate names không gộp entity khác ID; thiếu ID fail-closed.
- NULL/zero/Decimal/BIGINT/timezone và count row/value distinction.
- Fan-out/twofacts/cycle/ambiguous graph/4+tables rejected.
- Knowledge/Gemini selection/fallback attribution/history đúng, không fake answer.
- Single-table/RAG/Hybrid capability không regression do sửa JOIN context.
- Parser/ingest/document retrieval đúng scope, không invent citations.

## 23. Safe diagnostics và thu evidence đúng cách

`pipeline_diagnostic` có correlation_id/stage/status/reason/duration và các facts
bounded như model, route, table/edge counts, sql_validated, execution_reached,
result_rows. Không chứa question, SQL, raw rows, email, cookies hoặc tokens.
Tối đa64 events/request; logger failure không được làm hỏng request.

Các stages quan trọng:

```text
workspace_binding -> relationship_approval -> schema_metadata
 -> router_unsupported -> generator_unsupported -> sql_parse_error
 -> column_resolution -> join_graph / join_relationship / join_key
 -> join_aggregate -> join_grain -> execution_guard -> sql_execution
 -> answer_grounding / document_retrieval -> request
```

Tên `router_unsupported`/`generator_unsupported` là tên stage, status success có
thể là router/draft thành công; phải đọc status/reason/route, không suy từ tên.
`frontend_rendering` có tên dành cho test diagnostics, chưa là production browser
telemetry pipeline. Không có Langfuse dashboard ở hệ thống hiện tại.

UI refusal “chưa thể tính” không tự xác định aggregate cause; phải đọc safe
internal code. Không bật raw SQL logging production để tìm rejected draft. Nếu
cần draft evidence, tái hiện fake gateway/offline hoặc live synthetic private
capture riêng được duyệt, không log real customer data.

## 24. Private evidence và tài liệu nên đọc theo thứ tự

### 24.1 Tài liệu repository

Ưu tiên newest append-only sections thay vì chỉ đọc kết luận cũ đầu file:

1. `AGENTS.md` — quy tắc bắt buộc.
2. `handoff.md` — snapshot tổng hợp này.
3. `docs/sql_join_root_cause_audit.md` — báo cáo mới nhất, gồm GateD 3/8PASS.
4. `docs/sql_join_reliability_acceptance.md` — lịch sử N..X: order, aggregation,
   auto detection, three-table, logistics; đầu file có kết luận cũ theo thời điểm.
5. `docs/join_v1_final_acceptance.md` — migration/deployment/recovery lịch sử.
6. `docs/sql_correctness_hardening.md` — timestamp/Decimal/validator, có caveats.
7. `docs/regression_stabilization.md` — Guest/auth/upload/proxy/gates.
8. `docs/authentication.md`, `docs/main_auth_upgrade.md`, `docs/guest_mode.md`.
9. `docs/multi_model_integration.md`, `docs/multidomain_evaluation.md`.
10. `docs/dataset_deletion.md`, `docs/system_reliability_audit.md`.
11. `README.md`, `docs/technical_references.md`, các audit/evaluation cũ.

Một số tài liệu cũ có dòng “chưa authentication”, “max_tables1”, “chưa JOIN”,
“Guest login screen” hoặc số tests/gates cũ. Đó là checkpoint lịch sử, **không
ghi đè source/current report**. README chưa được đồng bộ mọi giới hạn/liveGateD
mới nhất, ví dụ câu PASS Guest ba-table lịch sử không có nghĩa auth13 mới PASS.

### 24.2 Evidence local ngoài Git

GateD private folder:
`C:\Work\ShopQuery-Backups\live-gate-d-20261021`

Có ledger/oracle, eight synthetic response JSONs, safe-diagnostics JSON, policy
MD và screenshot `gemini-history-result.jpg`. Không có cookie/token trong bộ
response synthetic được thu; không tự upload mọi backup folder lên ChatGPT web.
Backups khác có thể chứa dữ liệu/auth, chỉ review local và redact có chọn lọc.

Oracle SHA-256:
`bda5e5aac8a08af94713c66778b1357ac5831a306db36aa999ea834c15f587ee`.

Helper private `C:\Work\ShopQuery-Backups\live_gate_d.py` quản lý ledger/reserve/
capture/oracle/diagnostics/finalize, không gọi provider. **Không reset ledger,
không chạy prepare lại, không reserve/send lại các case đã hoàn thành.**

Helper `C:\Work\ShopQuery-Backups\root_audit_runtime.py` verify/hash/final chỉ
đọc runtime/DB và lưu private hashes; không là migration. Bản final loại đúng
synthetic13 messages qua conversationdataset13, vẫn kiểm mọi history cũ khác.

Source fixture synthetic gốc từng ở Downloads: `01_kho_dieu_phoi.csv`,
`02_tai_xe.csv`, `03_don_giao_hang.csv`, cùng ba DOCX policy. Không coi toàn bộ
Downloads là synthetic hoặc được phép gửi; chỉ những file định danh rõ này.

## 25. Những việc chưa làm và rủi ro còn tồn tại

### Blocker nghiệm thu hiện tại

1. Model không tuân thủ COUNT alias/semantics ổn định qua authenticated UI.
2. Gemini Hybrid QH generator unsupported chưa có nguyên nhân raw reason.
3. Chưa có live Hybrid/citation/conclusion PASS dưới contract hiện tại ở matrix13.
4. Sửa offline tiếp theo và budget live mới chưa được thực hiện/phê duyệt.

### Hạn chế sản phẩm không được giấu

- JOIN subset tối đa3tables/2edges, không arbitrary relational SQL.
- Grouping shared attributes thiếu ID có thể bị từ chối theo quyết định grain.
- Automatic discovery cần naming đủ bằng chứng, không hiểu mọi ngôn ngữ/domain.
- Không metric/units/locale catalog bảo đảm mọi business formula đúng.
- Legacy timestamps/precision sai từ dữ liệu trước đây không tự phục hồi.
- DOCX cũ có thể còn missing chunks cho đến re-ingestion có kế hoạch riêng.
- PDF scan/OCR chưa hỗ trợ; file original binary không được persist.
- Full request deadlines/production capacity/upstream uptime chưa được chứng minh.
- Guest RAM store một worker, refresh mất chat theo thiết kế.
- Application-level owner enforcement, không phải database RLS.
- Runtime app DB connection local vẫn dùng setup role quyền cao; tách least-
  privilege runtime còn backlog trước public deployment.
- Chưa nghiệm thu load, antivirus/object storage, scheduled/offsite backup+
  restore operations, production observability/redaction/log rotation.
- Không VPS/TLS public/reverse-proxy production hoàn chỉnh được nghiệm thu.
- Nginx/Uvicorn raw access logs được hạn chế để không lộ OAuth callback secrets;
  không bật lại thiếu redaction chỉ để debug thuận tiện.
- Provider privacy permission cần theo dataset cụ thể, gateON không là consent
  tự động cho mọi loại dữ liệu cá nhân/công ty.

## 26. Kế hoạch tiếp tục đề xuất — ưu tiên offline, chưa phải lệnh thực thi

### Bước 1: chốt đúng baseline

- Đọc AGENTS/reportdiff; giữ docs chưa commit, không gom source khác.
- Xác minh source/runtime/gates/metadata, không restart/migrate DB chỉ để audit.
- Không gọi provider; budget8 của GateD đã dùng xong.

### Bước 2: offline capture context và SqlDraft synthetic

- Dùng đúng authenticated-style random physical identifiers/columns/owner path
  như13, nhưng trên PostgreSQL test cô lập.
- Fake generation gateway capture schema/context contract, không ghi production prompt.
- Reproduce COUNT(*) missing/wrong alias, COUNT(nullable/nonnullable/key) với row
  alias/value alias, direct vs wrapped aggregates, nested/alias/group resolution.
- Two-table và chain three-table, cả thứ tự FROM tương đương.
- Independent oracle phải phân biệt rows vs nonNULL vs entity count, không chỉ
  kiểm totals; thêm duplicate display labels/zero/NULL/largeDecimal.

### Bước 3: xác định sửa nhỏ có bằng chứng

- Đọc prompt/context thật đã capture: count rules/examples có mâu thuẫn, bị
  examples dimension/intermediate grain làm lẫn hay không? Đừng mặc định có.
- Không tự sửa missing/wrong alias trong mọi SQL, không map arbitrary COUNT
  thành row count, không tự chèn GROUPBYID.
- Nếu chọn thay prompt/structured contract, giữ framework/model và test old/new
  output behavior, Knowledge không regression; schema mới cần được review.
- Generator unsupported với Hybrid: test SQL context documentcount/capability
  và instruction rằng document criteria được giải quyết ở retrieval sauSQL;
  chỉ fix nếu tái hiện/chứng minh, không suy đoán model reason không có evidence.
- Chỉ mở validator normalization nếu có proof hẹp semantics tương đương và
  negative tests; không lấy mong muốn giảm false refusals làm lý do nới security.

### Bước 4: verify code trước deployment/live

- Targeted tests -> affected SQL/RAG/Hybrid/auth/Guest regressions -> Ruff/CI
  trong phạm vi thay đổi. Không bớt assertions.
- Báo SQL/AST synthetic trước/sau, stage đã sửa, phần vẫn không biết.
- Nếu cần deploymentAPI, xin phép thao tác main scoped, giữ exact overrides/
  env/model/quotas, không recreate DB; image/module hashes và health.
- Đề xuất số probes/calls mới tối thiểu bằng synthetic, xin ngân sách mới trước
  provider, không làm live loop cho tới khi tình cờ xanh.

### Bước 5: nghiệm thu đúng nghĩa

- Auth UI cùng fixture metadata path, exact question predeclared, no extra retries.
- Router/SqlDraft/tables/keys/grain/validation/execution/rows/answer/citations nếu
  Hybrid, actualmodel/no fallback, reload history, protected data hashes.
- Báo PASS/FAIL/NOTRUN riêng; không reuse old successful screenshot.
- Commit/push chỉ khi người dùng yêu cầu/quyền đúngscope, kiểm CI đúngSHA.

## 27. Hướng dẫn cho ChatGPT web tiếp nhận tài liệu này

ChatGPT web chỉ nhận file này không mặc nhiên có quyền đọc `C:\Work\...`, Docker,
Git private evidence hoặc tab8080 trên máy. Không tuyên bố đã chạy test, mở log,
đọc source đầy đủ hay xác nhận CI mới nếu chỉ đọc handoff.

Nếu cần code review cụ thể, yêu cầu người dùng gửi source text/diff có chọn lọc:
`datasets/context.py`, `text_to_sql/generator.py`, `join_policy.py`, `validator.py`,
`pipeline.py`, `dependencies.py`, `routing/service.py`, `routing/hybrid.py`,
relevant tests và phần mới nhất của root-cause report. Không xin `.env`, cookie,
token, DB dump, OAuth secrets, internal endpoint hoặc production raw prompts.

Yêu cầu hữu ích để người dùng gửi kèm handoff:

> Hãy đọc toàn bộ handoff này. Trước tiên tóm tắt đúng kiến trúc và blocker hiện
> tại, tách kết quả offline/CI khỏi live UI. Đề xuất kế hoạch sửa COUNT contract
> tối thiểu dựa bằng chứng, bảo toàn fail-closed, entity grain và owner isolation.
> Chỉ rõ source/diff nào còn cần xem. Không tự cho rằng đã đọc file local, không
> gọi provider live, không đổi model/framework hoặc nới SQL validator để làm xanh.
> Nếu thiếu bằng chứng raw rejected draft, hãy nói chưa biết thay vì suy đoán.

Tài liệu này là ngữ cảnh, không tự cấp quyền thao tác mới. Các kế hoạch đề xuất
chưa có nghĩa mọi bước đã được chủ dự án duyệt hay đã thực hiện.

## 28. Checklist cuối cho người tiếp quản

- [ ] Hiểu source `50d7bac`, docs HEAD `e2151a3`, local 8080 và report chưa commit.
- [ ] Biết Gate D đã hoàn thành: 8 probes, 3 PASS / 5 FAIL, 19 generation / 1 embedding.
- [ ] Không gọi lại probes hoặc coi phần trần chưa dùng là quyền gọi tiếp.
- [ ] Không nhầm count-alias failures với thiếu relationship ở synthetic 13.
- [ ] Không cho rằng generic UI text cung cấp raw rejected SQL.
- [ ] Giữ GROUP BY ID, exact ON, fact root, revision/owner guards và SELECT-only.
- [ ] Hiểu Knowledge generation khác Gemini embedding và fallback đang OFF.
- [ ] Không reset/re-ingest/migrate dữ liệu main hay xóa volumes.
- [ ] Dùng đúng ba Compose files, API 8001 / PG 15432 / web 8080 và main volume auth.
- [ ] Chỉ dùng DB cô lập cho integration, fake gateways cho tái hiện offline.
- [ ] Giữ report chưa commit; không tự commit/push hoặc deploy khi chỉ được hỏi tư vấn.
- [ ] Chưa tuyên bố production-ready hoặc JOIN/Hybrid live ổn định.

---

**Tóm tắt một câu:** ShopQuery AI có full-stack local đa nguồn/đa model và guardrails
đã kiểm thử rộng, nhưng authenticated live JOIN/Hybrid vẫn có false refusals ở
COUNT contract và generator; ưu tiên tiếp theo là tái hiện/sửa nhỏ offline có
bằng chứng, không làm yếu bảo mật hoặc gọi thêm AI trước ngân sách mới.
