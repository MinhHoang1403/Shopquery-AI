# Runtime và deployment

Main baseline `0062e47d75cc51646bf9b45409a12aa49288552e`; active volume
`shopquery-ai_postgres_auth_20261019`, archived volume `shopquery-ai_postgres_data`.
Exact main order trên máy này: `compose.yaml`, `.env.compose-ui.yaml`,
`.env.join-v1.yaml`, project `shopquery-ai`. API8001/web8080/PostgreSQL15432.
Local overrides bị Git ignore, không phải template cho máy mới.

Main images giữ bằng `shopquery-ai-api:baseline-0062e47` và
`shopquery-ai-web:baseline-0062e47`. Actual IDs/hashes/fingerprints nằm trong báo cáo
và ignored private baseline. Kiểm image IDs, không chỉ tin tên tag.

Trước switch kiểm mounts, health, active leases và in-flight workers. Auth sessions
lưu DB được giữ; Guest RAM không sống qua API recreate. Exec process mới không đọc
được GuestStore của process đang chạy. Không coi worker count là số idle sessions.
Không recreate main `db`, đổi main key/schema/data hoặc xóa volumes để chuyển modes.

Development chỉ vận hành devdb/api/web qua base+dev override, database
`shopquery_dev`, test `shopquery_test_stage1`, volume `shopquery-ai_postgres_dev_stage1`.
`--fresh` chỉ áp dụng dev DB mới, không seed/ingest/fake Google user.

## Khôi phục main image đã giữ

Kiểm không có in-flight work trước khi chuyển; cần baseline local overrides còn nguyên.

```powershell
docker image tag shopquery-ai-api:baseline-0062e47 shopquery-ai-api:latest
docker image tag shopquery-ai-web:baseline-0062e47 shopquery-ai-web:latest
docker compose -p shopquery-ai -f compose.yaml -f .env.compose-ui.yaml -f .env.join-v1.yaml up -d --no-deps --no-build --wait api web
./scripts/verify-runtime.ps1 -Main
```

Recreate dùng environment host hiện tại: host key đã đổi nghĩa là không exact env
rollback. Kiểm drift trước, không gọi provider để thử key. Local source khác image
baseline sẽ được verify-runtime báo rõ. Không down -v/prune hoặc tráo main/dev volume.

## Release

Trạng thái candidate, acceptance gates và lệnh merge/deploy/rollback nằm trong
[bàn giao V2](v2_release_handoff.md). Chưa merge hoặc chuyển release vào 8080.

`compose.release.yaml` dùng cùng Dockerfiles/source với development nhưng chỉ nhận
`SHOPQUERY_API_IMAGE`, `SHOPQUERY_WEB_IMAGE` đã pin digest; không build khi deploy.
`POSTGRES_VOLUME_NAME` phải là existing external volume đã đối chiếu. API chỉ mount
BGE read-only qua `BGE_MODEL_PATH`, không bind source hoặc bật hot reload. Web là
Nginx static, không dùng Vite development server. Dockerfiles nhận build argument
`SOURCE_REVISION` và ghi OCI revision label để đối chiếu image với source commit.

Build CPU với `INSTALL_RERANKER=true`, `RERANKER_EXTRA=reranker`; build CUDA với
`INSTALL_RERANKER=true`, `RERANKER_EXTRA=reranker-cuda`. Dùng `--frozen` lockfile sẵn
có. Thêm `compose.release.gpu.yaml` chỉ cho image CUDA đã được kiểm chứng; không dùng
`compose.dev.yaml` hoặc `compose.gpu.yaml` trong release. Không thêm model service.

Release provider gates mặc định tắt kể cả private `.env` đang bật legacy gates.
Chỉ operator được duyệt ngân sách/consent mới đặt `RELEASE_PROVIDER_DATA_ENABLED=true`
và, riêng Guest, `RELEASE_GUEST_AI_ENABLED=true`. Không tự đổi credentials/fallback.
Nếu gate tắt, UI giữ thông báo từ chối AI; health200 chỉ chứng minh API còn hoạt động.

Local release tại HTTP 127.0.0.1:8080 giữ security environment `development` để dùng
cookie local như bản trước; đây là release artifact, không phải public production.
`APP_ENVIRONMENT=production` vẫn bắt buộc HTTPS và Secure cookies. Không bỏ kiểm tra
HTTPS để chạy localhost; public TLS/VPS không thuộc đợt chuẩn bị này. Development
banner do Vite development build tạo và không xuất hiện trong Nginx release build.

Cấu hình GPU/Compose theo [Docker GPU reservations](https://docs.docker.com/compose/how-tos/gpu-support/)
và [Compose merge](https://docs.docker.com/reference/compose-file/merge/).

verify-runtime chỉ xuất tên biến drift, source hashes/differences, health/IDs/mounts;
không resolved env/key/token. Health là liveness, không chứng minh DB/AI readiness.
