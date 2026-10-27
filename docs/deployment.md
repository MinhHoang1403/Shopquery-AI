# Runtime và deployment

Runbook hiện hành cho một source `C:/Work/ShopQuery AI`, branch `main`, một ứng dụng
[8080](http://127.0.0.1:8080), Compose project `shopquery-ai`.
[Langfuse](http://127.0.0.1:3000) chạy riêng project `shopquery-observability`.
Không dùng các image refs lịch sử làm cấu hình hiện hành.

## Runtime đã xác minh

| Service | Immutable image | Application revision |
| --- | --- | --- |
| API | sha256:d8ad8aa5e3425b803bcec9c61a5e84dd5e950a2e07dc978d70c64d7c33dcbbb2 |3fe4cc22bc4769dfa6318541bf26bd50109ffb29|
| Web | sha256:ae181335b61aa738f6b0b1c2c1c450fe46a5ba26b4688d5c294d541975696a58 |02d5cbb445901f7eb63f82bee87e2e8785d35663|
| Main PostgreSQL/pgvector | sha256:137f044b0efe3d57f39b972b9b53641b1f2045b99d879e298bbf514a25787dcf |upstream image|

API 127.0.0.1:8001, Web 127.0.0.1:8080, main DB 127.0.0.1:15432. Main volume
`shopquery-ai_postgres_auth_20261019` là external/protected; không recreate/reset/xóa.
Application inputs khớp main dù các commit docs/scripts về sau có SHA khác OCI revision.
Strict verifier đối chiếu bytes/manifests, image IDs, Compose/env; không chỉ so tên tag.

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

Rollback API hiện hành: `sha256:52701da8a2d0fb40f5825647ef955936148271cad47c0838dcbaeaca41983285`,
source 8a2c6aa. Private `.env.release.before` ở
`C:/Users/admin/.codex/backups/shopquery-ai/langfuse-acceptance-20261027`.
Trước rollback xem lại image/config tương thích và current work, xin duyệt thời điểm;
khôi phục release env rồi API-only deploy với `-Observability`. Không undo main data.
Image069e7f67 trước instrumentation cũng được giữ cho lịch sử phục hồi, không dùng tự động.
Web hiện hành không đổi trong các đợt Langfuse; các image cũ chưa chứng minh không cần
vẫn được giữ. GitHub không thay backup volumes/secrets.

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
