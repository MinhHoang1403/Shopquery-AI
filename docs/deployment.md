# Runtime và deployment

Runbook hiện hành cho một source `C:/Work/ShopQuery AI`, branch `main`, một ứng dụng
[8080](http://127.0.0.1:8080), Compose project `shopquery-ai`.
[Langfuse](http://127.0.0.1:3000) chạy riêng project `shopquery-observability`.
Không dùng các image refs lịch sử làm cấu hình hiện hành.

## Runtime đã xác minh

| Service | Immutable image | Application revision |
| --- | --- | --- |
| API | sha256:4a80e003aeb9ea008afcc5b557084db105ad4507130695a5b7fa1d378bc586e7 |e2722da8973883bdeb5cb837e9614001f9be490a|
| Web | sha256:9b735b38e62a19f9e1f8426b10c1774bedc30ae07d23cbda6cae75db1237a23f |b75a844b959ccd0d268a11ac10f99ab0326813d4|
| Main PostgreSQL/pgvector | sha256:137f044b0efe3d57f39b972b9b53641b1f2045b99d879e298bbf514a25787dcf |upstream image|

API 127.0.0.1:8001, Web 127.0.0.1:8080, main DB 127.0.0.1:15432. Main volume
`shopquery-ai_postgres_auth_20261019` là external/protected; không recreate/reset/xóa.
Application inputs khớp main dù các commit docs/scripts về sau có SHA khác OCI revision.
Strict verifier đối chiếu bytes/manifests, image IDs, Compose/env; không chỉ so tên tag.

Cutover được operator duyệt ngày 28/10/2026; API/Web healthy, strict 88 modules PASS.
Hybrid/follow-up Giao nhận, SQL Khách sạn, DATE/ID và unsupported safety đã kiểm live.
Provider error mapping/safety response correction e2722da đã được duyệt API-only cutover;
SQL ranking và explicit RAG trên image hiện hành PASS, không dùng để chấm auto-routing PASS.
Nghiệm thu toàn bộ correction còn **RELEASE_BLOCKED**: Knowledge403, COUNT+SUM gặp
Gemini504, một policy-only question chọn sai route/false refusal. Không đổi model/gate
hoặc retry để che failure. Chi tiết và ngân sách: [correctness review](correctness_review.md).

Gemini default, Knowledge manual, fallback OFF, gate ON, Guest AI OFF, embedding2/768,
approved JOIN ON, vector-only/BGE OFF, Langfuse ON. Không tự đổi model/provider/gates.
Một Uvicorn worker, không source bind/reload trong release. Guest RAM mất khi recreate API.

## Cấu hình và thứ tự Compose

Đọc `.env` trước, `.env.release` sau; file order cố định:

1. `compose.yaml`: service definitions/công cụ base, không chạy riêng trên máy này.
2. `.env.compose-ui.yaml`: private loopback port override.
3. `.env.join-v1.yaml`: private approved JOIN override; tên giữ tương thích.
4. `compose.release.yaml`: immutable images, protected volume, one worker.
5. `ops/langfuse/shopquery.compose.yaml`: instrumentation và ingestion network.

`.env`, `.env.release`, hai YAML local và `ops/langfuse/.env` phải giữ private.
`.env.example`/`ops/langfuse/.env.example` chỉ là templates không chứa secrets.
`compose.dev.yaml`, `compose.gpu.yaml`, `compose.release.gpu.yaml` có scripts/tests
tham chiếu; giữ làm maintenance opt-in. Không xóa chỉ vì tên dev/gpu/v1.

Ingestion network `shopquery-observability_ingestion` chỉ có API và Langfuse Web;
main Web/DB không nối datastore network Langfuse. API còn nối `shopquery-ai_backend`.
Langfuse Web listen 0.0.0.0 bên trong container để nhận cả hai interfaces, host port
vẫn 127.0.0.1:3000. Sáu pins/five volumes/backup limits ở [runbook Langfuse](../ops/langfuse/README.md).

## Kiểm tra chỉ đọc

```powershell
./scripts/release.ps1 -Observability
Invoke-RestMethod http://127.0.0.1:8080/api/health
docker ps --format '{{.Names}} {{.Status}}'
docker compose -p shopquery-observability --env-file ops/langfuse/.env -f ops/langfuse/compose.yaml ps
```

`release.ps1` không có `-Deploy` chỉ kiểm; fail khi source/image/config drift.
Không đưa resolved Compose/env, raw logs, callback URL hoặc secrets lên Git/chat.
Theo dõi OOM/restart/readiness và tải thực tế; không tự đổi Windows/WSL/security policy.

## Cập nhật API hoặc Web

1. Đọc AGENTS, kiểm Git/working tree và baseline runtime. Không gộp thay đổi người khác.
2. Tests đúng phạm vi, commit/push và exact-head CI PASS. Cấm paid calls nếu chưa có ngân sách mới.
3. Chỉ build service có application/build inputs đổi; docs/maintenance scripts không build image.
4. Ghi source revision, pin immutable digest trong private release config, giữ config/image rollback.
5. Kiểm active leases/Guest work. Operator duyệt thời điểm gián đoạn; không deploy đang có work.
6. Chỉ recreate API hoặc Web, không PostgreSQL. Sau API switch, script kiểm/reload Nginx graceful.
7. Strict verifier,8080/session/history và integrity theo phạm vi; không coi health200 là SQL correctness.

Ví dụ build API khi source thực sự đổi, từ repository root:

```powershell
$revision = git rev-parse HEAD
docker build --pull=false --build-arg "SOURCE_REVISION=$revision" --build-arg INSTALL_RERANKER=false -f backend/Dockerfile -t "shopquery-ai-api:main-$revision" .
docker image inspect "shopquery-ai-api:main-$revision" --format '{{.Id}}'
# Pin digest thật vừa kiểm vào SHOPQUERY_API_IMAGE của private .env.release.
# Chỉ sau CI/image/config/rollback và thời điểm cutover được duyệt:
./scripts/release.ps1 -Deploy -Service api -Observability
```

Build Web khi frontend inputs đổi bằng `frontend/Dockerfile`, cùng SOURCE_REVISION;
pin `SHOPQUERY_WEB_IMAGE`, dùng `-Deploy -Service web -Observability`. Không build Web
cho backend-only change. Không mở BGE hoặc đổi dependency extras để làm xanh verifier.

## Restart và khôi phục

Chỉ thao tác trong maintenance window được operator duyệt. Trước restart, kiểm
`resource_leases WHERE expires_at>now()` theo guard trong release.ps1 và Guest worker
processes; dừng nếu có work hoặc không xác minh được. Không hủy work bằng cleanup.

Khi thật sự cần restart cùng image/config, dùng đúng services và đủ overrides:

```powershell
$releaseCompose = @('compose','-p','shopquery-ai','--env-file','.env','--env-file','.env.release',
  '-f','compose.yaml','-f','.env.compose-ui.yaml','-f','.env.join-v1.yaml',
  '-f','compose.release.yaml','-f','ops/langfuse/shopquery.compose.yaml')
docker @releaseCompose restart api
./scripts/release.ps1 -Observability
```

Không restart/recreate DB để cập nhật API/Web. Sau Docker/Windows startup, nếu chỉ cần
bật containers đã có, dùng chính file/env/project và `up -d --no-build --no-recreate
--pull never`; không dùng `down -v`. Runtime/image thay đổi phải dùng controlled release,
không coi một restart là triển khai source mới.

Rollback trước đợt correction: API `sha256:d8ad8aa5e3425b803bcec9c61a5e84dd5e950a2e07dc978d70c64d7c33dcbbb2`,
source `3fe4cc2`; rollback Web `sha256:ae181335b61aa738f6b0b1c2c1c450fe46a5ba26b4688d5c294d541975696a58`,
source `02d5cbb`. Private configs nằm trong
`C:/Users/admin/.codex/backups/shopquery-ai/correctness-20261027`; `.env.release.before`
giữ cả hai image trước cutover, `.env.release.rollback-api-new-web` giữ API trước/Web mới.
Không promote hai candidates đã bị loại `d7f2d822` và `6a632447`.

Trước rollback kiểm exact image/config, active leases/Guest work và thời điểm được duyệt.
Rollback application source khác main cần đối chiếu với chính Git revision của image;
strict verifier so main sẽ báo source drift có chủ đích, không được đổi guard để báo PASS.
Chỉ recreate service cần rollback và refresh Nginx sau API; không undo main data. Lượt
rollback API sau schema400 đã kiểm identity/config, leases, Guest và 88 modules với Git
revision cũ (chỉ chuẩn hóa CRLF/LF khi so Git blobs), rồi phục hồi bản sửa sau CI/duyệt mới.
Các rollback cũ52701da8/069e7f67 vẫn giữ; GitHub không thay backup volumes/secrets.

Rollback tức thời sau provider fix: API `sha256:5675513a90921b713413b8dda5391a9c0dfb2b24acbdb60edf4b9f96446f14b0`,
source29bb788, private `.env.release.before-provider-fix` trong cùng thư mục nêu trên.
Không dọn images/cache/volumes trong đợt điều tra provider.

## Dữ liệu và backups

Không chạy seed/re-ingest/re-embed/fresh setup/migration vào main trong maintenance thường.
Migrations và role scripts ở backend/scripts vẫn cần cho fresh install/recovery đã duyệt;
không phải dead code. Dữ liệu application và monitoring có backup/restore riêng.

Trước thao tác data/schema có rủi ro cần backup mới và restore verification ở target
được duyệt. Không copy live database directories hoặc tạo clone/test stack theo thói quen.
Langfuse backup/restore drill và retention còn giới hạn đã công bố; xem runbook riêng.
Không prune volumes, models hoặc private config khi cleanup.

## Bằng chứng và trạng thái bàn giao

- [System acceptance](v2_final_acceptance.md): phạm vi SQL/RAG/Hybrid, guards và giới hạn Knowledge/BGE.
- [Observability acceptance](observability_acceptance.md):6 câu UI, oracle/citation 23,
  234 observations,10 generation/3 query/0 document,32601 generation tokens; cửa sổ đã đóng.
- [Operational handoff](operational_handoff.md): inventory, cleanup, scripts, branches và exact-head CI cuối.

Nhật ký deployment/preflight/cutover cũ được giữ nguyên tại
[Git baseline 24ab3c8](https://github.com/MinhHoang1403/Shopquery-AI/blob/24ab3c8d89d63c2d6b80ec3932c45c3c82edd1b8/docs/deployment.md).
Không dùng các marker BLOCKED hoặc source/image lịch sử ở đó làm trạng thái hiện hành.
