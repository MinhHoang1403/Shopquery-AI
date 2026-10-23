# Authentication & multi-user isolation

## Phạm vi hướng dẫn

Tài liệu này mô tả authentication và migration hiện hữu. Trạng thái MVP/runtime hiện tại nằm trong [báo cáo Giai đoạn 1](stage1_implementation_report.md), [architecture](architecture.md) và [deployment](deployment.md). Các mốc triển khai/nghiệm thu cũ không chứng nhận runtime development mới.

Google OIDC invite-only, PostgreSQL opaque sessions, CSRF, owner-scoped repositories, optional login và quota beta được giữ. Logout thành công về Guest trống. Không suy ra callback/logout live PASS từ browser mock. Lịch sử main upgrade/Guest nằm trong [archive](archive/README.md).

## Google OIDC

Authlib 1.9.1 thực hiện Authorization Code Flow, PKCE S256, signature/JWKS và claim validation. Identity unique theo `(issuer, subject)`, không theo email. Chỉ Google issuer được chấp nhận. Email phải verified và nằm trong allowlist backend; empty allowlist từ chối mọi tài khoản. Không có admin đọc dữ liệu của người khác.

Backend tự tạo state, nonce, verifier và browser-binding cookie ngẫu nhiên. Flow record tồn tại 10 phút trong PostgreSQL; browser binding chỉ lưu hash. Callback lấy và xoá flow atomically trước token exchange để chặn replay. Redirect URI lấy từ cấu hình, không từ Host/query/return URL do client cung cấp. OAuth access/refresh/ID tokens không lưu lâu dài.

Nguồn thiết kế: [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect), [Authlib web clients](https://docs.authlib.org/en/stable/oauth2/client/web/index.html).

## Cấu hình thủ công

Không chia sẻ secret qua chat. Người quản trị tạo Google Cloud OAuth Client loại Web application, cấu hình consent/test users phù hợp và lưu các giá trị chỉ trong `.env` private:

```dotenv
APP_ENVIRONMENT=development
APP_ORIGIN=http://127.0.0.1:8080
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
AUTH_INVITED_EMAILS=[]
AUTH_SESSION_HOURS=12
API_DOCS_ENABLED=false
BETA_PROVIDER_DATA_ENABLED=false
```

Điền client ID/secret và JSON list email được mời tại máy, không commit. Redirect URI chính xác là `${APP_ORIGIN}/api/auth/callback`; ví dụ local `http://127.0.0.1:8080/api/auth/callback`. Nếu dùng Vite, APP_ORIGIN và Google redirect phải cùng origin Vite, không trộn localhost với 127.0.0.1. Không tạo OAuth Client tự động trong repository.

### Tạo OAuth Client lần đầu

1. Mở Google Cloud Console bằng browser thông thường, chọn/tạo project riêng cho development.
2. Vào Google Auth Platform → Get started/Branding, đặt tên ShopQuery AI và support/contact email.
3. Audience: chọn External nếu dùng Gmail cá nhân, giữ Testing. Có thể thêm tài khoản kiểm thử trong Test users; ứng dụng vẫn bắt buộc allowlist backend, không dựa vào Google test-user list để cấp quyền. Với chỉ openid/email/profile, Google có ngoại lệ đối với hạn chế testing, nên allowlist backend là lớp bắt buộc.
4. Clients → Create client → Web application. Không chọn Desktop app hoặc service account.
5. Authorized redirect URIs phải khớp chính xác `${APP_ORIGIN}/api/auth/callback`, không thêm dấu `/` cuối. Chỉ thêm origin thực sự được dùng; development Giai đoạn 1 hiện tắt Google credentials. Không cần Google Drive/Gmail scopes; chỉ openid/email/profile.
6. Lưu Client ID và Client secret vào file private .env, điền AUTH_INVITED_EMAILS bằng JSON list email được phép. Secret không phải Gemini API key. Không gửi secret hoặc file download OAuth vào chat/Git.
7. Báo đã cấu hình để operator đưa các giá trị vào backend test và restart đúng test container. Không tự restart stack chính, không trỏ test backend vào database chính. Cấu hình .env không tự cập nhật environment của container đang chạy.
8. Đăng nhập Google bằng browser thông thường trên bản test. Kiểm tra /auth/me, logout và tài khoản ngoài allowlist, xác nhận issuer/sub của owner thật. Chỉ sau đó mới xin phép migration chính.

Google Console reference: [Get started](https://support.google.com/cloud/answer/15544987?hl=en), [Web server credentials](https://developers.google.com/identity/protocols/oauth2/web-server), [Audience/testing exceptions](https://support.google.com/cloud/answer/15549945?hl=en).

Production environment bắt buộc HTTPS. Cookies production dùng `__Host-`, HttpOnly, Secure, SameSite=Lax, Path=/ và không có Domain. Chỉ localhost development cho phép HTTP/non-Secure. Không có AUTH_DISABLED hoặc header giả danh user trong runtime.

## Sessions và CSRF

Session token có 256 bit randomness, browser giữ opaque token HttpOnly; `user_sessions` chỉ lưu SHA-256 token, user FK, created/expiry/revocation. Login tạo token mới và revoke token hiện tại; logout revoke server-side. Session expiry mặc định 12 giờ. Tài khoản inactive hoặc email không còn trong allowlist không sử dụng được phiên.

`GET /api/auth/me` trả current user và CSRF token gắn với session. Frontend giữ token trong memory, không localStorage. Mọi POST/PATCH/DELETE/upload phải có `Origin` khớp APP_ORIGIN và `X-CSRF-Token`; OAuth callback dùng state/nonce riêng. SameSite không phải lớp CSRF duy nhất. API responses đặt `Cache-Control: no-store`.

Endpoints: GET `/api/auth/login`, GET `/api/auth/callback`, GET `/api/auth/me`, POST `/api/auth/logout`. Login không nhận redirect tùy ý. Models và tất cả API dữ liệu cũ yêu cầu session; health public chỉ liveness. `/api/guest/*` là public capability API riêng, không bỏ auth của API cũ. Docs/OpenAPI mặc định tắt, chỉ bật rõ cho development. Lỗi chat nghiệp vụ vẫn HTTP 200 có error; unauthenticated 401, sai owner/missing resource 404, CSRF/policy 403, quota 429.

Nguồn: [OWASP Sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

## Ownership và demo

`datasets.owner_user_id` và `chat_conversations.owner_user_id` là boundary. Tables/documents/chunks/messages kế thừa parent; mỗi repository đọc/ghi theo owner của session. Client không được chọn owner. Dataset name unique case-insensitive theo owner. Conversation chỉ gắn dataset cùng owner; migration thêm composite FK. Không đổi physical table names.

Authorize trước schema/categorical scan, parser công việc ứng dụng, embedding, generation và SQL execution. SQL allowlist chỉ chứa bảng authorized workspace; RAG lọc dataset trong DB và kiểm tra owner; fallback vẫn dùng cùng authorized context. Reader role không được đọc session/OIDC/limit tables. Đây là application authorization, không phải RLS hoặc database riêng từng user.

Demo commerce và chunks `dataset_id IS NULL` dùng chung read-only cho authenticated users. Không API sửa/xoá/upload vào demo. Chat trên demo vẫn thuộc từng user. Chunks workspace không trộn corpus demo.

## Frontend

AuthBoundary kiểm tra `/auth/me` trước khi mount App. Guest chỉ thấy login screen. Account/logout ở sidebar. 401 hoặc session-policy-invalid unmount private UI, xoá CSRF, abort requests; request epoch loại bỏ response cũ kể cả transport bỏ qua abort. Focus tab revalidates session, ngăn tiếp tục hiển thị state tài khoản trước sau đổi phiên. Đổi user remount App, xoá messages/evidence/datasets/history/dialogs/model context. Không persist private data/token trong browser storage.

## Giới hạn beta và privacy

PostgreSQL lưu counters/leases để dùng chung giữa workers; không Redis. Defaults cấu hình được:

| Setting | Default |
|---|---:|
| BETA_LOGIN_PER_IP_HOUR | 20, login và callback cùng budget |
| BETA_CHAT_PER_USER_HOUR | 30 |
| BETA_UPLOAD_PER_USER_HOUR | 10, gồm preview/import/create |
| BETA_USER_CONCURRENCY | 1 |
| BETA_SYSTEM_CONCURRENCY | 4 |
| BETA_MAX_DATASETS | 20 |
| BETA_MAX_USER_BYTES | 104857600 |

Counters theo fixed hour, lease hết hạn sau 30 phút nếu process chết. Quota storage đo kích thước bảng vật lý và text/vector chunks, không phải tổng dung lượng PostgreSQL hoặc billing. Repository dùng owner lock và kiểm tra budget trước commit; vượt budget rollback bảng/metadata. Không tính history vào quota storage hiện tại. Toàn request deadline và tải production chưa nghiệm thu. Per-IP dùng peer address, không tin X-Forwarded-For từ client; proxy trust chỉ dùng các peers được cấu hình; public deployment chưa nghiệm thu.

`BETA_PROVIDER_DATA_ENABLED=false` mặc định chặn chat và document embeddings trước provider call. Chỉ bật sau khi quản trị xác nhận dữ liệu beta được phép gửi providers. Knowledge generation nhận câu hỏi/schema/rows/evidence; Gemini generation nhận tương tự nếu chọn hoặc fallback được phép. Query embedding và document ingestion vẫn gửi text tới Google kể cả chọn Knowledge. Không hứa xử lý hoàn toàn nội bộ. Không tự bật Gemini fallback; model preference/attribution giữ nguyên. Đây là gate vận hành, không thay thế policy pháp lý/consent theo loại dữ liệu.

## Migration an toàn — không tự áp dụng DB chính

### Fresh installation (database sạch)

`python scripts/setup_database.py --confirm-database <target> --fresh` chỉ dùng cho database chưa có bảng ứng dụng. Lệnh tạo pgvector, các bảng rỗng, owner NOT NULL/FKs, unique tên theo owner và composite FK `(dataset_id, owner_user_id)` giữa conversation/dataset. Ghi version `001_fresh_install` không có owner; không tạo identity/sessions/seed/chunks và không gọi providers. Re-run sau cài thành công không sửa dữ liệu. Database có bảng nhưng chưa có fresh marker bị từ chối, kể cả khi bảng rỗng; không dùng flag này như lệnh reset.

Nếu cài bị gián đoạn trước marker, dừng để kiểm tra schema và target; không tự DROP hoặc seed để vượt lỗi. Schema legacy tiếp tục dùng quy trình dưới đây, không đổi thành fresh install tự động.

Reader chỉ được SELECT trên nguồn SQL/RAG cho phép; không được đọc users, sessions, OIDC, quota, history hoặc migration marker. Role runtime hiện vẫn là setup superuser trong Compose local; tách runtime least-privilege còn là công việc trước public/VPS, không coi đợt này đã xử lý xong.

### Legacy ownership (chỉ khi cần giữ dữ liệu)

Không chạy down -v, seed, re-ingest hoặc re-embed để nâng cấp. Stop writers trong cửa sổ migration được duyệt, xác minh target và tạo backup mới trước khi áp dụng thật.

1. Backup riêng bằng pg_dump custom ra ngoài repository.
2. Restore vào PostgreSQL cô lập. So sánh fingerprints 10 bảng legacy + mọi physical uploaded table; hàm fingerprint bao gồm IDs, JSON evidence/model metadata và vector values, chỉ loại owner column mới.
3. Expand schema bằng thao tác quản trị có target confirmation, không trên GET/startup:
   `uv run python scripts/setup_database.py --confirm-database <database-name>`.
4. Xác định đúng identity thật: Google issuer/sub được verify qua flow trên môi trường clone có OAuth cấu hình. Không gán dữ liệu cho user đầu tiên. Khi cần chuẩn bị user trên DB đích, người quản trị phải đối chiếu issuer/sub đã verify; không dùng email làm subject và không sao chép subject test.
5. Trên clone, chạy `scripts/migrate_ownership.py --owner-user-id <uuid> --confirm-database <clone-name> --backup-restored`.
6. Migration version `001_user_ownership`: session advisory lock serialize toàn thao tác, owner-null backfill explicit, validate relationship, uniqueness theo owner, NOT NULL/FKs, record version và owner. Constraint/backfill transaction rollback nếu lỗi; expand là bước riêng idempotent và có thể còn lại sau thất bại. Không hứa downgrade tự động.
7. Kiểm tra fingerprints, FK, unowned count và repeat migration. Different owner trên version đã áp dụng phải bị từ chối.
8. Chỉ sau khi người dùng xác nhận owner và cấp phép riêng mới lặp lại quy trình trên database chính. Sau đó rebuild/start backend/frontend và nghiệm thu Google sign-in cùng A/B live trên dữ liệu test được phép.

`scripts/rehearse_ownership.py` chỉ chấp nhận test target explicit, tự dùng synthetic owner trên clone để so sánh trước/sau/repeat. Không dùng synthetic owner đó cho dữ liệu chính. `--backup-restored` là xác nhận của operator, không tự chứng minh backup đã kiểm tra.

Không tự đổi physical tables, IDs, embeddings 768 chiều, source relationships hoặc history. Dữ liệu chưa gán owner không được hiển thị cho tài khoản bất kỳ. Xoá source giữ history evidence cũ; xoá workspace/history theo consent hiện hữu.

## Test safety và CI

Integration chỉ chạy khi RUN_DATABASE_TESTS=1, target có tên `shopquery_ci` hoặc `shopquery_test_<suffix>`, và SHOPQUERY_TEST_DATABASE_URL bằng setup URL; target trùng application DB trong .env bị từ chối. Default/dev/production names bị chặn. Dùng container PostgreSQL test riêng và disposable credentials; không trỏ tests vào DB chính. Fixture cũ vẫn có seed/delete, nên đây là guard bắt buộc trước fixtures.

```powershell
# Chỉ trong shell test, URL trỏ DB/container cô lập do bạn tạo.
$env:RUN_DATABASE_TESTS = '1'
$env:DATABASE_SETUP_URL = '<isolated-test-setup-url>'
$env:DATABASE_READONLY_URL = '<isolated-test-reader-url>'
$env:SHOPQUERY_TEST_DATABASE_URL = $env:DATABASE_SETUP_URL
uv run pytest -m 'not live'
```

Backend auth tests dùng token ký RSA/JWKS offline và real sessions PostgreSQL, không bypass toàn dependency. A/B negatives fail nếu provider/parser/schema bị gọi. Owned SQL/RAG/Hybrid chạy DB thật với fake generation/embedding, không gọi AI có phí. Migration tests tạo DB clone tạm và kiểm tra fingerprints/repeat/failure. CI không cần Google/AI secrets.

Browser mocks chặn API bằng Playwright và test 5 viewport, không gọi AI. Có thể chạy Vite riêng:

```powershell
$env:SHOPQUERY_E2E_START_SERVER = '1'
$env:SHOPQUERY_E2E_BASE_URL = 'http://127.0.0.1:5173'
npm run test:e2e
```

Mọi live browser suite yêu cầu opt-in riêng và SHOPQUERY_LIVE_STORAGE_STATE trỏ file phiên của tài khoản test trong DB cô lập. File đó là secret: lưu ngoài repo hoặc .auth/ bị ignore. Backend live tests cũng yêu cầu explicit test DB và BETA_PROVIDER_DATA_ENABLED=true. Không chạy live cho tới khi người dùng cho phép; test mặc định không gọi upstream.

## Bằng chứng lịch sử

Xem [main authentication upgrade](archive/2026-10/main_auth_upgrade.md) cho rehearsal, fingerprints và test counts tháng 10/2026. Đây không phải trạng thái current runtime.

## Chưa sẵn sàng public VPS

Public-deployment backlog riêng (không phải tuyên bố Giai đoạn 2 đã bắt đầu): runtime DB least privilege thay superuser; HTTPS và proxy trust; production Compose/resource/restart/log limits; Nginx upload-size alignment; scheduled/offsite backups và restore; monitoring/alerting; whole-request deadlines, blocking parser/embedding workload và capacity tests; provider privacy policy. Nhiệm vụ MVP V2 hiện tại không triển khai public TLS/VPS/RLS mới.

Image mới tắt Uvicorn access log và Nginx access log; Nginx error output cũng bị tắt để không lưu callback query chứa code. Không bật lại log request thô khi thử OAuth. Đây là lựa chọn local; redaction có kiểm chứng, log rotation và observability production cần được nghiệm thu trước public deployment. Không chia sẻ logs hoặc callback URL thô.
