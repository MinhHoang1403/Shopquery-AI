> HISTORICAL snapshot. Current architecture/status: [Stage 1 report](../../stage1_implementation_report.md).

# Main authentication upgrade — 19/10/2026

Trạng thái của checkpoint ban đầu: **READY FOR GOOGLE LIVE LOGIN ON MAIN 8080**. Các mục NOT RUN bên dưới ghi nhận thời điểm checkpoint này, không phải trạng thái runtime mới nhất. Sau đó người dùng đã xác nhận Google login thành công; main có một tài khoản thật. Đợt Guest giữ nguyên tài khoản/session và thay login wall bằng optional login; xem [báo cáo Guest và upload 8080](guest_mode.md). Không coi CI, mock browser hoặc HTTP 302 là Google login thật.

## A. Git

- Baseline/HEAD `f48aa32e49f252e01cb49f890440ebb1f4d0ece2`, branch `main`, working tree ban đầu sạch.
- Có thay đổi source/test/docs local phục vụ nâng cấp này. Chưa commit/push: chờ login/logout và nghiệm thu main theo thứ tự được yêu cầu.
- Chưa có CI cho diff mới. [CI baseline](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39211593668) không được tính là CI của đợt này.

## B. UI/UX

- Guest screen trắng/xám, logo nhất quán, một Google Sign-In chính; loading không mount private App trước session.
- Account footer lấy display name/email từ `/api/auth/me`, initials không cần thêm OAuth scope. Menu hỗ trợ outside click, Escape, Arrow keys, Tab, focus visible, collapsed sidebar và mobile.
- Logout unmount private UI/huỷ requests ngay; chỉ xác nhận xong sau backend response. Timeout 15 giây; lỗi hiện retry, xác minh lại session/CSRF trước thử logout tiếp. Không tự mount lại private App khi focus trong lúc logout pending/failed.
- Empty state không quảng cáo corpus demo rỗng; hướng dẫn tạo workspace/upload, chặn composer khi chưa có nguồn. API cũng chặn default chat khi demo rỗng trước provider/generation hoặc ghi message.
- 65 browser mock cases pass trên 1440×900, 1280×800, 768×1024, 390×844, 320×700. Đã mở xem screenshots desktop, tablet/mobile, guest, empty welcome, account menu và collapsed sidebar; dữ liệu danh tính hoàn toàn giả lập. Screenshots ở `frontend/test-results/`, bị Git ignore.
- Chưa kiểm tra authenticated UI của Google session thật trên main. Không dùng screenshot mock để nhận live pass.

## C. Database sạch và backup

- Main target xác minh bằng TCP connection metadata: database `shopquery`, service `shopquery-ai-db-1`, host port loopback 15432, network `shopquery-ai_backend`.
- Trước chuyển: 8 categories, 150 products, 2000 orders, 4019 order_items; 7 datasets/7 uploaded tables/1 document/28 chunks; 12 conversations/72 messages. Fingerprints cả 17 bảng khớp clone audit trước đó, không phát hiện dữ liệu mới khác snapshot.
- Backup mới ngoài repository: `<private-backups>/shopquery_before_clean_main_20261019T075819Z.dump`, 231102 bytes. Đã đọc TOC, restore vào database cô lập `shopquery_test_backup_f21cd670b750`; fingerprints cả 17 bảng khớp. So sánh lại main sau dừng writers vẫn khớp backup trước chuyển volume.
- **Không DROP/TRUNCATE database cũ.** Volume cũ `shopquery-ai_postgres_data` được giữ nguyên, không còn gắn main DB đang chạy. Backup cũ ngoài repository không bị xoá.
- Main mới dùng volume `shopquery-ai_postgres_auth_20261019`, schema version `001_fresh_install`. Không copy test identities/sessions/synthetic owner. Các bảng commerce giữ rỗng để tương thích; không seed/import/ingest.
- Trước login initiation: toàn bộ 15 bảng application/auth đều 0 dòng (users, sessions, OIDC flows, quotas/leases, datasets/sources/chunks, conversations/messages và commerce); `schema_migrations` có 1 marker. Preflight sau đó tạo một OIDC flow và login-rate counter hợp lệ, không tạo user/session.
- Fresh install CLI trong Docker image mới pass lần đầu và re-run trên database cô lập; integration kiểm tra owner NOT NULL, FK/unique, từ chối cross-owner conversation và từ chối database đã có bảng mà chưa có fresh marker.

## D. Google OAuth

- Runtime main: `APP_ENVIRONMENT=development`, `APP_ORIGIN=http://127.0.0.1:8080`.
- Callback đúng `http://127.0.0.1:8080/api/auth/callback`, không về 18080; Host giả cũng không đổi callback.
- Client ID/Secret: configured; allowlist khớp `.env` private. Không sửa `.env`, không in credentials/state/nonce/verifier/code/cookies/CSRF.
- Login initiation 302 Google, scope đúng `openid email profile`, PKCE S256, state/nonce; browser-binding cookie HttpOnly/SameSite=Lax và flow hash trong main PostgreSQL đã đối chiếu.
- Google Console redirect configuration chưa được kiểm tra trực tiếp. Google callback/token validation/session creation và logout thật: **NOT RUN — chờ người dùng tự đăng nhập**.

## E. Security

- Giữ session/CSRF/request epoch, owner-derived scope và SQL/RAG/Hybrid authorization. Backend regression dùng providers giả, A/B trên PostgreSQL cô lập, không giả identity trên main.
- `BETA_PROVIDER_DATA_ENABLED=false`, `AI_GEMINI_FALLBACK_ENABLED=false`. Không gọi Knowledge/Gemini generation hoặc embedding thật trong đợt này. OAuth discovery không phải AI call.
- Reader read-only, không đọc bảng auth/history/migration. Bootstrap không còn default SELECT cho mọi bảng public tương lai.
- Nginx access/error request logs và Uvicorn access log tắt trong images mới để tránh lưu OAuth callback query. Production redaction/monitoring chưa triển khai.
- Chưa tách runtime DB khỏi setup superuser; chưa public/VPS/HTTPS. Không nhận production-ready.

## F. Main Docker

| Container | Host port (127.0.0.1) | Trạng thái |
| --- | --- | --- |
| `shopquery-ai-web-1` | 8080 → 80 | Healthy, image mới |
| `shopquery-ai-api-1` | 8001 → 8000 | Healthy, image mới |
| `shopquery-ai-db-1` | 15432 → 5432 | Healthy, pgvector PostgreSQL 17 |

- Đúng Compose project `shopquery-ai`; cả ba chỉ gắn `shopquery-ai_backend`, không gắn auth-test network/volume. Nginx proxy `api:8000`, không proxy tới 18001. Runtime DB URL dùng `db:5432/shopquery`, không dùng 15433.
- Override local `.env.compose-ui.yaml` giữ cổng 8001/15432 và chọn volume sạch; file ignored, không chứa secrets. **Phải dùng cả hai Compose files khi vận hành máy này.** Base Compose một mình mặc định chọn volume cũ.
- HTTP frontend/health 200; guest me/datasets/conversations/models 401; OpenAPI 404; next/open redirect bị từ chối 400. Không lấy Running thay cho smoke test.
- Giữ rollback web image tag `shopquery-ai-web:pre-auth-20261019`. Image API cũ của container không còn trong image store nên không tag được; rollback cần build lại source phiên bản trước auth (`c022a9b`) cùng volume/backup cũ, không hứa rollback một lệnh.

## G. Test cleanup

**Chưa thực hiện, đúng điều kiện chờ main Google login/logout nghiệm thu.** Ba container test vẫn nguyên IDs/start times sau deploy:

- `shopquery-auth-web-smoke-20261019`: 18080.
- `shopquery-auth-api-smoke-20261019`: 18001.
- `shopquery-auth-test-20261019`: 15433.

Network `shopquery-auth-smoke-20261019` và test PG volume `297689ce12d035d22344d99f9c90307c4d98ec5f791a268014ff8240373f54d3` chưa xoá. Không global prune hoặc xoá volume. Sau main acceptance mới remove đúng containers/network; volume test cần kiểm tra và phê duyệt riêng nếu muốn xoá hẳn.

## H. Tests

| Kiểm tra | Kết quả |
| --- | --- |
| Ruff | Pass |
| Backend unit/API | 225 passed |
| PostgreSQL integration | 98 passed, database riêng tại 15433 |
| Backend không-live tổng | 323 passed; 8 live không chạy |
| ESLint / TypeScript | Pass |
| Vitest | 42 passed |
| Frontend production build | Pass |
| Playwright mock, 5 viewports | 65 passed |
| API/web Docker build | Pass |
| Fresh CLI image, first/repeat | Pass |
| Main HTTP/OIDC initiation | Pass |
| Main Google login/logout / live upload / history | NOT RUN — user interaction checkpoint |
| CI của diff mới | Chưa có commit/push |

## I. Checkpoint và giới hạn

Người dùng mở `http://127.0.0.1:8080` bằng browser thường, chọn **Tiếp tục với Google** và tự đăng nhập Gmail được mời. Báo đã vào được chat, account menu hiển thị đúng tên/email, reload giữ phiên hay lỗi ngắn gọn. Không gửi callback URL/code/token/cookies.

Sau xác nhận: kiểm tra session phía DB chỉ bằng metadata an toàn; nghiệm thu empty state, tạo/import nguồn synthetic và logout/revocation. Không tự tạo fake Google user trên main. Chat/embedding thật cần cấp phép riêng để bật provider gate. Chỉ sau main acceptance mới dọn auth-test, commit/push và xác minh CI đúng commit mới.

Cơ sở kỹ thuật: [PostgreSQL composite foreign keys](https://www.postgresql.org/docs/17/ddl-constraints.html), [Docker Compose named volumes](https://docs.docker.com/reference/compose-file/volumes/), [Nginx log configuration](https://nginx.org/en/docs/http/ngx_http_log_module.html), [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect).
