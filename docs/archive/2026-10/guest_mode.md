> HISTORICAL snapshot. Current architecture/status: [Stage 1 report](../../stage1_implementation_report.md).

# Guest Mode, optional Google login và kiểm tra upload — 19/10/2026

Trạng thái: đã triển khai local 8080, đạt kiểm thử offline/isolated và smoke upload thật; **chưa nghiệm thu live AI hoặc production/VPS**. Các kết quả mock được ghi rõ, không thay thế provider/Google live acceptance.

## A. Git

Baseline `f48aa32e49f252e01cb49f890440ebb1f4d0ece2`, branch `main`. Working tree đầu đợt có phần nâng cấp main auth chưa commit; thay đổi đó được giữ cùng phần Guest, không có reset/revert dữ liệu người dùng. Không thêm dependencies.

SHA và link GitHub Actions đúng commit được trả ở phần bàn giao sau push; không ghi SHA tự tham chiếu vào chính commit. CI vẫn chạy backend, PostgreSQL cô lập và frontend/browser mock, không cần API key và không gọi AI/Google login thật.

CI đầu của `c3ac630` pass backend/PostgreSQL nhưng browser đạt 78/80: hai case mobile Linux timeout trong đoạn test tab thứ hai/đọc lại trang cũ. Bộ test được sửa để kiểm tra DOM trang đầu trước khi mở tab thứ hai và giao việc đóng tabs cho test runner; vẫn giữ đầy đủ kiểm tra upload, gate-off và tab mới trống, không skip/retry để che lỗi. Vite trong chế độ mock cũng tắt proxy API để unload keepalive không rơi sang backend thật khi interceptor đang teardown. Lần CI sau phải được xác minh riêng trước khi kết luận xanh.

## B. UX

- `/api/auth/me` được kiểm tra trước khi mount private App. 401 vào ngay chatbot Guest, không redirect Google, không đọc private datasets/conversations/models.
- Tái sử dụng App, Sidebar, ChatHeader, ChatInput, selector, Markdown và evidence toolbar. Guest có nhãn chat tạm, upload và nút Đăng nhập góc phải/sidebar. Chat, danh sách chat và credentials Guest chỉ nằm trong memory; không localStorage/sessionStorage/IndexedDB.
- Nút Đăng nhập mở xác nhận nhỏ, rồi link Google OIDC cũ. Không tự chuyển file/chat Guest sang tài khoản. Unmount/login/pagehide giải phóng context best-effort, abort requests và chặn late responses.
- Google user vẫn dùng private persistent workspace/history/account menu. Logout chỉ về Guest trống sau xác nhận backend; lỗi giữ màn hình retry, không giả vờ revoke thành công. Session expiry cũng bỏ toàn bộ private state.
- Authenticated focus revalidates session; Guest focus không làm mất draft/file. Trang phục hồi từ bfcache bắt đầu lại Guest, không khôi phục tệp cũ.

## C. Kiến trúc dữ liệu tạm

1. Browser gửi raw bytes tới `/api/guest/files/preview` hoặc `/files`, kèm capability token và CSRF trong header. Filename/sheet là query đã validate, không nhận owner/dataset/conversation ID.
2. Backend giới hạn stream trước parse; không dùng multipart spool cho Guest. Nginx riêng `/api/guest/` tắt request buffering, dùng proxy HTTP/1.1. Original bytes được bỏ sau request; không lưu original file lâu dài.
3. CSV/XLSX đi qua parser sẵn có, PDF/DOCX/TXT/MD qua document parser/chunker sẵn có. Parsed rows/chunks được giữ trong `GuestStore` RAM, token server chỉ giữ SHA-256. Không fake user hoặc persistent dataset/chunks/chat.
4. SQL tạo `TEMPORARY table_n` trên connection riêng `StaticPool`, `SET ROLE shopquery_guest` trước tạo/nạp bảng. Role NOLOGIN, không quyền đọc/ghi bảng persistent hoặc tạo bảng public; SQLGlot chỉ cho bảng `pg_temp` của request. Executor giữ SELECT/read-only, timeout và timezone Việt Nam. Giữ chính sách **mỗi truy vấn một bảng, không JOIN khi chưa có quan hệ tin cậy**.
5. RAG chỉ cosine-retrieve chunks/vectors trong RAM của phiên; giữ citation validation. Hybrid dùng cùng file scope SQL + RAG. Không retrieve corpus demo hoặc uploaded_data của tài khoản.
6. Worker là child process dùng spawn, wall deadline và Linux CPU/address-space limits. Parent đóng/kết thúc worker trong finally. Connection TEMP không thuộc auth connection pool; đóng bình thường hoặc process exit làm kết thúc SQL session. Process parse không được truyền provider/DB credentials qua Settings và bỏ credential environment trước parse; đây không phải OS sandbox chống RCE.
7. Reset/TTL/shutdown đặt cancellation và bỏ references RAM. TTL cố định 600 giây, cleanup mỗi 15 giây. Refresh xoá ngay UI; server reset qua unload chỉ best-effort, TTL/deadline mới là bảo đảm dọn khi tab biến mất. Disconnect đơn thuần không bảo đảm huỷ tức thời; worker vẫn bị timeout/reset/TTL chặn.

PostgreSQL TEMP có thể dùng disk nội bộ; không phải all-RAM hoặc forensic secure erase. Logical `pg_dump` không giữ bảng TEMP; physical disk snapshots/swap/provider retention không thuộc cam kết này. Không đưa Guest content vào user records/backups logic. Chỉ hashes/counters/leases chống lạm dụng được persist, không nội dung file/prompt. Theo [PostgreSQL TEMP lifetime](https://www.postgresql.org/docs/17/sql-createtable.html), [pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html), [Nginx request buffering](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_request_buffering).

## D. Guest features và limits

| Cấu hình | Mặc định |
| --- | ---: |
| `GUEST_ENABLED` / `GUEST_AI_ENABLED` | true / false |
| `GUEST_QUESTIONS_PER_SESSION` | 5 |
| `GUEST_CHAT_PER_IP_HOUR` / `GUEST_SESSIONS_PER_IP_HOUR` | 10 / 20 |
| `GUEST_UPLOADS_PER_IP_HOUR` | 10, gồm preview và commit |
| Concurrent mỗi Guest / toàn Guest | 1 / 2 |
| Tệp / bytes mỗi tệp | 2 / 2.097.152 |
| Rows / columns / PDF pages | 1.000 / 20 / 20 |
| Characters / chunks tổng / prompt characters | 100.000 / 12 / 2.000 |
| Parsed RAM budget phiên / toàn hệ thống | 10 MiB / 64 MiB, ước lượng bảo thủ |
| Parse deadline / chat deadline | 10s / 120s |
| Linux worker address space / CPU | 768 MiB / 15s |

Tất cả knobs có trong Settings, `.env.example` và Compose; giữ một API worker vì context RAM không phân tán. ZIP expansion có cap riêng 10 MiB. Quá mức trả lỗi thay vì ingest không giới hạn/OCR. Native Windows không có Linux rlimit; môi trường nghiệm thu runtime là Docker Linux.

Không có file: general handler nhỏ chỉ giải thích SQL/phân tích dữ liệu hoặc hướng dẫn upload nếu cần số liệu. Không tạo SQL/rows/sources giả. Có file: SQL/RAG/Hybrid tái sử dụng pipeline đã kiểm chứng. Chưa thêm di chuyển Guest history sang tài khoản.

## E. Security và privacy

- Origin unsafe request phải khớp APP_ORIGIN; capability ngẫu nhiên 256 bit và CSRF HMAC; token không chuyển thành Google session. API responses no-store. Không tin resource IDs từ frontend.
- Backend quyết định quota trước worker/provider. Gate tắt không tiêu thụ câu hỏi. Khi đã bắt đầu AI, cả thất bại cũng tính một lượt; response lỗi trả remaining chính xác, không tạo câu trả lời. Hết ngân sách giữ chat hiển thị; busy/upload rate không bị hiểu nhầm là hết quota chat vĩnh viễn.
- IP counter persist theo fixed hour, refresh/process restart không reset ngân sách. Peer IP dùng trực tiếp, không tin X-Forwarded-For. Với Nginx local, nhiều khách chia sẻ proxy IP và cùng budget; chưa có trusted-proxy policy cho VPS. Không coi IP là identity.
- Quota Guest tách quota authenticated. Global Guest leases chỉ là metadata, được release finally hoặc expire sau deadline + 30s nếu API chết.
- Không ghi nội dung prompt/upload vào application/access logs; không commit secrets, .env, cookies, dumps hoặc screenshots danh tính thật.
- Notice trước upload nêu rõ PII và provider sharing; RAG vẫn dùng Google embedding kể cả chọn Knowledge. Gate/fallback không được tự bật.

Runtime cuối đợt: Gemini key có cấu hình; **Knowledge base URL chưa cấu hình trong main container**. `BETA_PROVIDER_DATA_ENABLED=false`, `GUEST_AI_ENABLED=false`, `AI_GEMINI_FALLBACK_ENABLED=false`. Có key không đồng nghĩa được phép gọi provider. Không có live AI call trong đợt này.

## F. Authenticated mode

OIDC state/nonce/PKCE, Google verified identity/allowlist, session revocation/cookie security, CSRF, owner isolation, lịch sử và datasets persistent giữ nguyên. User đã xác nhận Google login trước đợt Guest. Trước và sau lượt smoke đầu: 1 user, 7 session records, fingerprints khớp. Khi kiểm tra cuối có thêm một session và users.updated_at thay đổi trong lúc hệ thống đang được sử dụng; không hoàn nguyên hoạt động đăng nhập đó. Đối chiếu với backup trong memory xác nhận cùng identity và toàn bộ 7 session cũ còn nguyên trường bất biến, hiện có 8 sessions. Không tạo giả user/session để thử private API trên main.

Private persistence, account switching/logout về Guest và reload history được kiểm tra bằng PostgreSQL tests + browser mock. **Chưa chạy lại Google callback/logout bằng tài khoản thật sau bản Guest**; không thay mock thành live pass.

## G. Kiểm thử

| Kiểm tra | Kết quả |
| --- | --- |
| Ruff | Pass |
| Backend unit/API, không live | 246 passed |
| PostgreSQL integration, DB riêng cổng 15433 | 104 passed |
| Backend không-live tổng | 350 passed; 8 live không chạy |
| ESLint / TypeScript / production build | Pass |
| Vitest | 49 passed |
| Playwright offline, 5 viewports | 80 passed |
| Docker API + web build | Pass |
| HTTP main 8080, 6 định dạng parse | CSV/XLSX/PDF/DOCX/TXT/MD đều 200 |
| Import tạm main CSV + MD, Guest A/B, reset | Pass; không ghi user data |
| Browser main thật | Guest home, CSV preview 100/200, commit 2 dòng, refresh về trống, optional-login mở đúng link Google |
| Gate false / private API | Chat 403 và quota giữ 5; private datasets/conversations/models 401 |
| Google flow, Knowledge/Gemini live sau Guest | NOT RUN |

Tests bao phủ direct-API quota bypass, resource-ID injection, Origin/CSRF, hai Guest, TTL/background/shutdown, parser crash/timeout và process exit đóng connection TEMP thật. Fake gateway kiểm tra tổng học phí 100+200=300, RAG nguồn rules.md ngưỡng 250, Hybrid kết hợp đúng rows + nguồn, từ chối public.users/cross-guest TEMP. Tests lỗi không tạo answer/evidence. Main user/content fingerprints không đổi.

Fingerprints content vẫn không đổi ở lần kiểm tra cuối; user/session có hoạt động đăng nhập đồng thời như mục F. Không coi thay đổi updated_at/session mới là mất dữ liệu và không rollback hoạt động đó.

Kiểm tra thủ công riêng trên database test: khi connection TEMP còn sống, `pg_dump` không chứa bảng TEMP hoặc sentinel 9917283627463; đóng connection xong không còn TEMP table. Dọn đúng 1 counter upload do 10 request synthetic của đợt smoke tạo (kiểm tra key theo proxy IP và count=10), không xoá counters session/login/người dùng hoặc tắt rate limit.

Lần chạy integration đầu trên DB test đã dùng lại bị trùng fixtures; chuyển sang DB cô lập mới cho mỗi full run, không sửa dữ liệu chính. Mock embedder thiếu embed_query đã được sửa; kết quả pass ở bảng là lần chạy sau sửa, không bỏ qua test lỗi.

## H. Main runtime và lỗi upload

API/web mới chạy cùng project `shopquery-ai`; DB container ID/start time/volume không đổi. Chỉ recreate API/web; không restart/drop/reset DB, không cleanup test containers/volumes. `shopquery-ai_postgres_auth_20261019` vẫn là volume chính, volume legacy giữ nguyên.

- Web 127.0.0.1:8080 → 80, API 8001 → 8000, DB 15432 → 5432; health pass.
- Vận hành máy này dùng **cả** `compose.yaml` và `.env.compose-ui.yaml`; base Compose đơn lẻ có thể chọn volume cũ. `.env` không bị sửa.
- Guest SQL role được thiết lập idempotent bằng `scripts/setup_guest_access.py --confirm-database shopquery`; không có content migration. Cài mới: sau schema setup/fresh install cũng cần chạy CLI này trên đúng database trước khi cho phép Guest SQL.
- Backup trước Guest ngoài Git: `<private-backups>/shopquery_before_guest_20261019T092319Z.dump`, 51.048 bytes, TOC đọc được. Không tuyên bố đã restore nghiệm thu backup mới này. Backup cũ đã restore kiểm tra ở đợt trước vẫn giữ.
- Không tag lại được image API cũ từ container vì image SHA không còn trong local image store. Không hứa rollback một lệnh; database/backup không bị xoá.

**Upload cổng 8080:** Nginx trước đó không khai báo client_max_body_size, nên dùng mặc định 1 MB; request synthetic khoảng 1,1 MB trả 413 HTML trước backend. Đã sửa `11m`, vẫn giữ backend cap 10 MB/tệp tài khoản, 2 MB/tệp Guest; frontend hiển thị 413 rõ cả khi proxy trả HTML. Cùng probe sau sửa tới được backend, trả 401 JSON do cố ý không có session; đây chứng minh proxy đã thông, không phải claim authenticated import pass. [Cấu hình chính thức Nginx](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size).

Sau cấu hình Nginx Guest streaming cuối cùng, file CSV synthetic **1.141.904 bytes / 950 dòng / 2 cột** được preview thật qua 8080: HTTP 200, đúng 950 dòng, không cần AI. Reset phiên ngay sau thử.

PDF/DOCX/TXT/MD **lưu vào tài khoản** cần embedding nên gate false chặn theo thiết kế. Guest chỉ parse và giữ chunks RAM nên vẫn upload/xem trước được. CSV/XLSX nhỏ không cần AI; chưa tái hiện được lỗi cụ thể của file nhỏ người dùng vì không có thông báo lỗi/session browser đó. Không kết luận mọi lần upload thất bại đều do 1 MB hoặc AI gate. PDF scan không text layer, file hỏng/mã hoá, vượt cap hoặc quota vẫn bị từ chối có chủ đích.

## I. Giới hạn và nghiệm thu còn lại

1. Chưa bật hoặc nghiệm thu provider live. Cần người quản trị cho phép riêng trước khi thay flags; Knowledge cần URL đúng hoặc chủ động chọn Gemini. Không tự đổi model/fallback.
2. Chưa chạy lại login/logout thực tế sau bản Guest; user cần tự thao tác Google. Không deploy VPS/HTTPS/public.
3. RAM contexts chỉ hỗ trợ một API worker; không scale nhiều replica. Resource estimates không thay memory cgroup/container limits; parser process không phải full security sandbox.
4. RAG re-embed tối đa 12 chunks mỗi lượt, vectors chỉ cache trong request, chưa cache qua nhiều lượt; provider cost có thể gồm nhiều API calls trong một câu hỏi. Quota không phải giới hạn billing tuyệt đối.
5. Cleanup không hứa tức thời khi mất mạng/đóng tab; reset best-effort + TTL + worker deadline. TEMP có thể chạm disk; không cam kết secure erase vật lý hoặc third-party retention.
6. Runtime setup account còn quyền cao như bản trước; SQL Guest đã hạ role và validator, nhưng chưa tách runtime DB credentials theo production hardening.

## J. Screenshots

`frontend/test-results/` bị Git ignore, chỉ chứa danh tính/dữ liệu giả của browser offline tests. Mỗi viewport có guest-home.png, guest-upload.png, guest-chat.png, guest-limit.png; auth tests có account-menu.png và logged-out-guest.png. Đã xem ảnh desktop và mobile 320; không tràn ngang. Đây là mock screenshots, không phải bằng chứng live AI.

Giao diện main thật được kiểm tra riêng bằng browser: CSV 100/200 đã được preview và thêm thành công trong phiên Guest; screenshot hiển thị trong cuộc trao đổi. Không chụp hoặc commit danh tính Google thật.
