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

`compose.release.yaml` yêu cầu reviewed image refs `SHOPQUERY_API_IMAGE`,
`SHOPQUERY_WEB_IMAGE` và existing external `POSTGRES_VOLUME_NAME`. Dùng digest hoặc
tag đã xác minh digest, `--no-build`; chọn host ports/flags theo overrides đã review.
Không deploy release/merge main trong Giai đoạn 1.

verify-runtime chỉ xuất tên biến drift, source hashes/differences, health/IDs/mounts;
không resolved env/key/token. Health là liveness, không chứng minh DB/AI readiness.
