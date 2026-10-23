> HISTORICAL snapshot. Current status: [V2 acceptance](../../v2_final_acceptance.md).

# Nghiệm thu ổn định Guest/Auth và dọn môi trường

Ngày kiểm tra: 19-10-2026 (giờ Việt Nam). Đây là báo cáo thực nghiệm, không phải cam kết không còn mọi lỗi có thể xảy ra.

## A. Git và runtime

- Bắt đầu từ main `527a3d9ca2946a5e53288d9ea3d8b795118f42d2`, working tree sạch trước đợt sửa. Các thay đổi trong báo cáo là của đợt ổn định này.
- Main dùng `compose.yaml` **cùng** override riêng `.env.compose-ui.yaml`: web 8080, API 8001, PostgreSQL 15432, chỉ bind loopback.
- Volume main: `shopquery-ai_postgres_auth_20261019`; volume cũ `shopquery-ai_postgres_data` được giữ nguyên. Không reset/re-seed/migrate schema main.
- Người dùng đã chủ động bật provider gate và sau đó yêu cầu bật cả Guest. Runtime cuối phải có `BETA_PROVIDER_DATA_ENABLED=true`, `GUEST_AI_ENABLED=true`; `.env.example` vẫn để false để cài mới không tự gửi dữ liệu.
- Không đổi generation/embedding model, không tự bật fallback. Gemini generation: `gemini-3.5-flash-lite`; embedding: `gemini-embedding-2`, 768 chiều.
- Thêm `restart: unless-stopped` cho 3 dịch vụ: tự khởi động lại sau lỗi/restart Docker, không ghi đè thao tác dừng chủ động.
- Images đã kiểm tra cuối: API `sha256:ca52b03b514d0cc19ec59f0160ae6f3e7983bcec69e50f97b795e5c2cb25250f`; web `sha256:6d693ce379961b04509c7e1421c12f83dac398169f1234d6517549f877f3053f`; PostgreSQL `sha256:137f044b0efe3d57f39b972b9b53641b1f2045b99d879e298bbf514a25787dcf`. API/web/db đều healthy, `/api/health` qua 8080 trả 200. Container DB gốc `511c4f5aaccc` không bị recreate.

## B. Nguyên nhân đã xác minh

| Lỗi | Tái hiện/bằng chứng | Nguyên nhân và vị trí |
|---|---|---|
| Không gõ được chat | Test trước sửa thất bại vì textarea disabled khi thiếu dataset; Guest gate-off cũng khóa input | `App.tsx` dùng chung gate/quota/thiếu nguồn cho `ChatInput.disabled` |
| Guest hết upload budget sớm | Với budget thêm tệp = 1, lần preview thứ hai trả 429 dù chưa commit; test đỏ trước sửa | `guest/routes.py:process_file` dùng cùng action upload cho preview và commit |
| Mọi Guest bị tính theo proxy | Counter cũ khớp hash IP Nginx, upload=10/session=20; Uvicorn không tin peer Nginx hiện tại | `peer_ip` lấy socket peer, chưa có trusted proxy xử lý |
| Auth upload mất file/draft | Test focus cùng session làm mất draft/file trước sửa; thực tế file picker có thể phát focus | `AuthBoundary` unmount App khi focus; hủy cả upload đang chạy |
| Tài liệu không được lưu | Khi provider gate false, PDF/DOCX/TXT/MD hợp lệ trả 403 trước khởi tạo gateway, không tạo tài liệu | Đây là privacy gate của embedding, không phải parser hỏng |
| Router nhầm tài liệu không tồn tại | Diagnostic Gemini thật trả UNSUPPORTED với lý do chỉ có fees.csv, không có policy, dù có tài liệu | SQL source context không nói số tài liệu có thật; bổ sung metadata, không ép route |
| Popup không cân đối | Upload Guest nhận width 820px chung; link Google không có căn nút/không bỏ underline | CSS chung và modal chưa quản lý focus |

Trên main, khung giờ quota đã đổi lúc audit nên probe tạo phiên trả 200; không tuyên bố đã ép main tái hiện 429 bằng cách làm cạn quota. Test quota dùng môi trường riêng; counters main không bị xóa.

## C. Các sửa đổi có mục đích

- `ChatInput`/`App`: input chỉ khóa khi đang thực hiện tác vụ; khả năng gửi tách khỏi gate. Nút gửi có lý do `aria-disabled`/tooltip, vẫn cho thao tác để giải thích vì sao chưa gửi; không gọi API chat khi điều kiện chưa đạt. Giữ draft, không tạo answer giả.
- `AuthBoundary`/`api.ts`: giữ component khi xác minh lại **cùng user và CSRF**, ẩn/inert trong lúc kiểm tra; request mới và response riêng tư phải đợi xác minh. Đổi session/tài khoản hoặc xác minh thất bại thì hủy epoch, xóa state riêng tư; logout vẫn unmount ngay. Không hủy upload hợp lệ chỉ vì focus cùng session. Session check timeout 15 giây; request thông thường có timeout hữu hạn 240 giây, không tự retry mutation.
- Guest: budget xử lý/preview riêng với budget thêm tệp; parse lỗi không tốn lượt thêm tệp, vẫn tốn budget xử lý chống abuse. Commit hợp lệ qua bước kiểm quota rồi mới thêm RAM; thất bại do tài nguyên có thể vẫn tốn lượt commit, không hứa chỉ tính thành công trong mọi lỗi.
- Auth: preview có budget riêng; create/import/document vẫn dùng upload budget. Endpoint authenticated `/api/uploads/limits` trả hạn mức thực tế, model registry có `ai_enabled`; UI giải thích embedding gate.
- `client_ip.py`/Nginx/Dockerfile: socket peer phải khớp IP/DNS trusted host `web` mới nhận một IP forwarded hợp lệ. Nginx ghi đè X-Forwarded-For bằng remote_addr; direct API/multi-IP/invalid header không được tin. Tắt Uvicorn tự sửa peer để kiểm tra trust trên raw socket peer.
- Kiểm tra thêm cùng họ lỗi: Google login/callback cũng tính quota theo Nginx. Hai test đỏ trước sửa; dùng lại `client_ip` đã kiểm trust cho cả hai endpoint, không sửa giao thức OIDC.
- `datasets/context.py`: nêu document count thực tế, nhắc RAG truy hồi riêng; không suy ra tài liệu vắng mặt từ schema bảng. Test có 0/1 tài liệu đỏ trước, xanh sau.
- Modal: Google CTA chính cùng kích thước với nút phụ, bỏ underline; width riêng, compact privacy disclosure; Escape/outside/Tab trap/focus restore.

## D. Hạn mức và upload

| Hạn mức mặc định | Guest | Đăng nhập |
|---|---|---|
| Định dạng | CSV/XLSX/PDF/DOCX/TXT/MD | CSV/XLSX/PDF/DOCX/TXT/MD |
| Dung lượng/tệp | 5 MiB | 10 MiB |
| Bảng | 5.000 dòng/30 cột | 5.000 dòng/30 cột |
| Số tệp | 8/phiên | Không áp cap 2 tệp; nhiều bảng/tài liệu/workspace |
| Xử lý/preview | 180/IP/giờ và 40/phiên, gồm cả parse khi commit | 180/người/giờ, tách khỏi ghi |
| Thêm tệp/ghi | 60/IP/giờ | 60/người/giờ, gồm tạo workspace |
| Lưu trữ | RAM ước tính 32 MiB/phiên, 128 MiB toàn hệ thống; 32 chunks/phiên | 20 workspace, 100 MiB/người |
| PDF | 20 trang có text | 100 trang có text |
| Vòng đời | 10 phút kể từ tạo phiên; refresh mất UI | PostgreSQL, owner scope |

Guest vẫn có 5 câu hỏi/phiên, 10 câu hỏi/IP/giờ, 2 tác vụ toàn hệ thống; parser worker 768 MiB, timeout parse 10 giây, chat 120 giây. Không upload/RAM vô hạn. Nginx cap 11 MiB, không tăng parser auth vượt thiết kế hiện tại. 8 tệp lớn có thể không vừa RAM và phải bị từ chối rõ ràng.

Fixed-hour rate limit trả Retry-After tới đầu giờ kế tiếp, không phải TTL giữ row counter 2 giờ. UI hiển thị thời gian thử lại nếu có. Upload/preview/busy không tự đánh dấu hết quota chat.

Docker Desktop/NAT có thể gom nhiều trình duyệt vào cùng IP client thực; đã bỏ nhầm IP Nginx, không hứa mỗi browser có IP riêng. Session và user là ranh giới nội dung/quyền, IP chỉ là budget bổ sung.

## E. Chat và live AI

File đối chiếu: fees.csv có 100 và 200; policy.md quy định miễn phí vận chuyển từ 500.000 đồng.

- Trước sửa metadata: Knowledge SQL/RAG đạt; một cách hỏi Hybrid bị UNSUPPORTED. Gemini cũng từ chối một cách hỏi RAG; diagnostic ghi nhận nhầm tài liệu vắng mặt. Câu hỏi rõ nghĩa khác đã chạy được. Không giấu các kết quả này.
- Sau sửa metadata, authenticated HTTP thật qua Nginx 18080/database test riêng: Knowledge và Gemini đều SQL/RAG/Hybrid HTTP 200, route đúng, không error/fallback; SQL=300, matched_row_count=2; RAG/Hybrid có policy.md đúng nội dung. Lịch sử mỗi model 6 messages đọc lại được từ server.
- 18080 tạo embedding thật cho MD/PDF/DOCX/TXT (mỗi file 201, 1 chunk); đọc lại 2 tables/4 documents; import CSV trùng trả 409. Workspace/chat giả lập được xóa đúng owner và session giả lập đã revoke. Không tạo giả session trên main.
- Main 8080: Guest HTTP live **6/6** (SQL/RAG/Hybrid × Knowledge/Gemini) đều 200, đúng route, tổng 300/2 dòng và nguồn policy.md, không fallback/error. Đã reset đúng các RAM session giả lập của probe, không reset counter IP.
- Main 8080 bằng **Google session thật trên giao diện**: CSV/XLSX và PDF/DOCX/TXT/MD đều thêm thành công; Knowledge/Gemini đều SQL/RAG/Hybrid đúng kết quả. Refresh khôi phục 6 assistant messages/12 tin nhắn, đúng workspace và model Gemini. Bảng/trích dẫn được mở để đối chiếu; không suy ra pass chỉ từ văn bản answer.
- Duplicate CSV và duplicate MD trên giao diện bị từ chối rõ ràng, vẫn giữ 2 bảng/4 tài liệu. Logout thật thành công, về Guest trống, không còn tên/email/dataset/history riêng tư.
- Sau bản runtime cuối, Guest giao diện main chọn Gemini, nạp CSV + MD, Hybrid trả 300/2 dòng và so sánh đúng ngưỡng 500.000; input được mở lại. Refresh xóa chat/tệp Guest. Một timeout/định vị file chooser của công cụ đã được khắc phục bằng click label hiển thị; không tính đó là lỗi ứng dụng hay kết quả pass khi chưa nhìn thấy phản hồi.

## F. UI/UX và browser

- Đã kiểm tra trên Nginx 8080: Guest gõ được dù gate tắt, giữ draft và báo lý do; CSV rồi XLSX import liên tiếp; refresh về Guest không nguồn.
- HTTP main khi gate tắt: xem trước nhiều lần và thêm 8 tệp/6 định dạng đều 200; tệp thứ 9 trả 429; Guest thứ hai không thấy tệp Guest thứ nhất. Probe chat đầu thiếu Content-Type JSON trả 422 do harness; đã sửa harness và kiểm lại 403 đúng gate. Không coi 422 đó là bug ứng dụng.
- Browser mock gồm 1440/1280/768/390/320; kiểm tra login CTA 44px/không underline/Tab/Escape, Guest gate/quota editable, refresh isolation, Auth focus giữ preview và PDF/DOCX gate false.
- Harness ban đầu coi hai response 403 có chủ đích là console failure; đã assert đúng **chính xác** hai endpoint document 403, vẫn fail các lỗi khác. Không tắt kiểm lỗi browser toàn cục.
- Ảnh nghiệm thu thật lưu riêng ngoài Git, không công khai email/tài khoản. Ảnh mock không phải live AI evidence.

## G. Bảo mật

Giữ OIDC invite-only, Origin/CSRF, session revocation, owner filtering và read-only SQL validator. Không bypass auth để nghiệm thu main; test giả lập chỉ trên test DB. Secret không in/commit. `.env` riêng chỉ thay hạn mức upload và bật Guest AI theo chỉ đạo người dùng; không đưa vào Git. External AI có thể nhận câu hỏi, kết quả SQL và nội dung tài liệu liên quan; chỉ gửi dữ liệu được phép. Không đặt API public/VPS trong đợt này.

Nguồn thiết kế trust: [FastAPI behind a proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/), [Nginx proxy_set_header](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header), [Uvicorn settings](https://uvicorn.dev/settings/). Không tin `*` hoặc header Internet tùy ý.

Restart policy theo [Docker restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/); không dùng restart policy để che lỗi ứng dụng hoặc hứa không gián đoạn.

## H. Kiểm thử tự động

| Hạng mục | Kết quả gần nhất |
|---|---|
| Ruff | Pass |
| Backend unit/API không live | 258 pass |
| PostgreSQL integration riêng, không API key | 109 pass |
| Vitest | 57 pass |
| ESLint / TypeScript / production build | Pass |
| Playwright mock / 5 viewports | 85 pass |
| Docker API/web build | Pass |
| npm audit production dependencies | 0 vulnerabilities được báo tại thời điểm chạy |

Tổng backend không live = 367; 8 live pytest không được gọi tự động. Live provider đã chạy bằng các yêu cầu kiểm soát riêng nêu trên, không nhập nhằng với fake gateway tests. Npm audit chỉ phản ánh advisories hiện biết, không thay thế security review/pentest.

## I. GitHub

Code, tests và báo cáo được giao trong commit ổn định trên `main`; SHA và kết quả CI đúng HEAD được cung cấp trong thông báo giao việc cuối. Có thể đối chiếu bằng `git log -1` và [GitHub Actions](https://github.com/MinhHoang1403/Shopquery-AI/actions/workflows/ci.yml). Chỉ xác nhận CI pass sau khi kiểm tra run của chính commit được push, không suy từ test local. Không force push; không commit secret/cache/backup/browser artifacts.

## J. Cleanup, nghiệm thu cuối và giới hạn

- Có backup main ngoài repository trước triển khai và trước cleanup. Backup gần nhất `shopquery_final_stabilization_20261019T131728Z.dump`, kiểm TOC; chưa diễn tập restore backup này.
- Đã dọn đúng 5 container test: `shopquery-auth-api-smoke-20261019`, `shopquery-auth-web-smoke-20261019`, hai bản trước ổn định có suffix `before-stabilization-4b59c8`, và `shopquery-auth-test-20261019`. Network `shopquery-auth-smoke-20261019` chỉ xóa sau khi không còn container kết nối.
- ShopQuery AI còn đúng 3 container main API/web/db đang healthy. Không xóa container dự án khác, không prune toàn máy, không xóa volume/image. Volume PostgreSQL test `297689ce12d035d22344d99f9c90307c4d98ec5f791a268014ff8240373f54d3` giữ lại; môi trường test có thể dựng lại nhưng cổng 18080/18001/15433 không còn chạy sau cleanup.
- Di chuyển 6 thư mục cache/build/test artifacts và 13 thư mục `__pycache__` khỏi workspace vào `C:\Users\admin\.codex\backups\shopquery-generated-20261019-final`. Đây là cleanup có thể phục hồi; không xóa source. Giữ `.venv`, `node_modules` để không làm hỏng môi trường phát triển. Caches sẽ tự sinh lại khi chạy test.
- Giữ workspace giả lập `Nghiệm thu ổn định · 19-10-2026` (2 bảng, 4 tài liệu, chat nghiệm thu) để chủ hệ thống kiểm tra lại; không xóa các workspace/history đã có trước đó. Dữ liệu thay đổi do thao tác thử nghiệm này và thao tác người dùng, không tuyên bố fingerprint toàn database không đổi sau nghiệm thu.
- Source/test/fixtures/migration đang được dùng không bị xóa chỉ để giảm số file. Tài liệu cũ là lịch sử, không thay bằng cam kết mới sai sự thật.
- Chưa phải pentest/fuzz/load test toàn diện; một API worker vì Guest RAM. SQL chỉ tập con an toàn, không JOIN bảng upload khi chưa có quan hệ; PDF scan không OCR. Provider có thể quota/timeout/503, câu hỏi mơ hồ vẫn có thể cần diễn đạt lại.
- Không có bảo đảm “không còn bất kỳ lỗi nào”. Chỉ nghiệm thu các tình huống có bằng chứng, không đánh đồng local beta với sẵn sàng VPS/public.

Kết luận: đủ điều kiện **sử dụng/test local trong các luồng đã nghiệm thu**, AI đã bật theo yêu cầu, vẫn giữ quota và kiểm soát quyền. Chưa nghiệm thu chịu tải công khai, VPS/HTTPS, mọi loại file/câu hỏi đối kháng hoặc độ khả dụng tương lai của upstream.
