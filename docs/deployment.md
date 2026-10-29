# Runtime và deployment

Runbook hiện hành cho một source `C:/Work/ShopQuery AI`, branch `main`, một ứng dụng
[8080](http://127.0.0.1:8080), Compose project `shopquery-ai`.
[Langfuse](http://127.0.0.1:3000) chạy riêng project `shopquery-observability`.
Không dùng các image refs lịch sử làm cấu hình hiện hành.

## Runtime đã xác minh

| Service | Immutable image | Application revision |
| --- | --- | --- |
| API | sha256:2d27fba187bb8703ebefbb214931933576767a52d7a32855b05d4a25c3bf5d98 |4ab2c5a1cc115b95cbc9854d6dc65f75a95ae473|
| Web | sha256:b2188879d84d6069f66dd73a13210bb810d269a23366aa77d6d4fd6eb307a7b3 |de0572ebf7e946c3396c5693a9c5a3f27ab6a4ef|
| Main PostgreSQL/pgvector | sha256:137f044b0efe3d57f39b972b9b53641b1f2045b99d879e298bbf514a25787dcf |upstream image|

API 127.0.0.1:8001, Web 127.0.0.1:8080, main DB 127.0.0.1:15432. Main volume
`shopquery-ai_postgres_auth_20261019` là external/protected; không recreate/reset/xóa.
Application inputs khớp main dù các commit docs/scripts về sau có SHA khác OCI revision.
Strict verifier đối chiếu bytes/manifests, image IDs, Compose/env; không chỉ so tên tag.

Cutover ngày28/10 theo chỉ thị tự hoàn tất triển khai của operator; API/Web healthy,
strict88 modules/source/config PASS. Policy-only AutoRAG/citation23, exact COUNT+SUM
192/24360000 và SQL Khách sạn16entities PASS trên de0572e. Sau một Hybrid failure đã
rollback API rồi sửa contract bắt buộc intent/scope, CI4/4 và triển khai4ab2c5a: Hybrid8kho/
5đạt/3chưa,follow-up3kho và policy-only follow-up AutoRAG đều PASS đúng oracle/citations.
Trạng thái: **APPLICATION_ACCEPTED_WITH_UPSTREAM_LIMITATIONS** trong phạm vi đã kiểm,
không full Stage2/tag hoặc bảo đảm mọi câu hỏi/schema. Knowledge generation còn chưa
nghiệm thu lại sau403/timeout; GET/models200 không chứng minh inference phục hồi. Giữmanual.
Chi tiết nguồn, root-cause certainty và7requests/13generation/5query/0document đã đóng:
[correctness review](correctness_review.md). Không gọi lại provider để kiểm docs/cleanup.

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

Rollback giữ sau closeout29/10: API
`sha256:4a80e003aeb9ea008afcc5b557084db105ad4507130695a5b7fa1d378bc586e7`
(source `e2722da8973883bdeb5cb837e9614001f9be490a`) và Web
`sha256:9b735b38e62a19f9e1f8426b10c1774bedc30ae07d23cbda6cae75db1237a23f`
(source `b75a844b959ccd0d268a11ac10f99ab0326813d4`). Đây là cặp rollback đã ghi trong
bàn giao28/10 và đã kiểm identity/tồn tại, không phải một lượt smoke rollback mới.
Private config ở `C:/Users/admin/.codex/backups/shopquery-ai/evidence-routing-20261028/`.
Chỉ dùng `.env.release.rollback` sau khi xác minh đúng hai digests trên và effective
Compose; các private configs/images trước đó chỉ là lịch sử, không còn cam kết tồn tại.

Không restart/rollback khi có active leases hoặc Guest work; cần thời điểm gián đoạn
được operator duyệt. Không undo main data. Các API/Web cũ khác đã xóa theo exactID
trong closeout; danh sách ở [PROJECT_CLOSEOUT](PROJECT_CLOSEOUT.md). Không dùng configs
lịch sử để pull/build/promote candidate. Git history không phải backup dữ liệu/secrets.

Closeout không rebuild/redeploy. Strict verifier byte-exact hiện báo ba file Python
khác CRLF/LF so với image; nội dung chuẩn hóa LF của đủ88modules bằng nhau, OCI revision
và effective config đều đúng. Không sửa verifier/guard hoặc runtime để làm xanh kết quả.
Chi tiết hạn chế, fingerprint và known Windows test failure ở [bàn giao cuối](PROJECT_CLOSEOUT.md).

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
- [Operational handoff](PROJECT_CLOSEOUT.md): inventory, cleanup, scripts, branches và exact-head CI cuối.

Nhật ký deployment/preflight/cutover cũ được giữ nguyên tại
[Git baseline 24ab3c8](https://github.com/MinhHoang1403/Shopquery-AI/blob/24ab3c8d89d63c2d6b80ec3932c45c3c82edd1b8/docs/deployment.md).
Không dùng các marker BLOCKED hoặc source/image lịch sử ở đó làm trạng thái hiện hành.
