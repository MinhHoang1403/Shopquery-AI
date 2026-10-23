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

Trạng thái nghiệm thu hiện hành nằm trong [nghiệm thu V2](v2_final_acceptance.md);
baseline và image rollback được bảo tồn trong [bàn giao V2](v2_release_handoff.md).
Chưa merge hoặc chuyển release vào 8080 khi các gate bắt buộc còn BLOCKED.

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
không resolved env/key/token. Mismatch source, image, environment hoặc service
thiếu/unhealthy làm lệnh exit khác0. Health là liveness, không chứng minh DB/AI readiness.

## Runbook vận hành và promotion

Hot reload chỉ thuộc development. Production/release cần triển khai image đã kiểm tra.
Giữ một repository, một deployment chính8080 và test DB riêng. Không tạo stack mới
cho mỗi sửa đổi. `.env` và `.env.release` là active private config, không commit.

`.env.release` giữ hai image refs pin `@sha256:…`, `BGE_MODEL_PATH`,
`POSTGRES_VOLUME_NAME=shopquery-ai_postgres_auth_20261019` và hai release provider
gates. Compose nhận `.env` trước, `.env.release` sau; không in resolved config ra log.
GPU dùng đúng existing local snapshot read-only và image CUDA đã được nghiệm thu.

Các lệnh sau tại root chỉ dùng cho release sau khi được duyệt cutover:

```powershell
# Read-only: source/image/environment drift phải làm lệnh FAIL.
./scripts/release.ps1 -Gpu

# Start/promote API/Web; không build, pull hoặc recreate main DB.
./scripts/release.ps1 -Gpu -Deploy
./scripts/release.ps1 -Gpu -Deploy -Service api
./scripts/release.ps1 -Gpu -Deploy -Service web

# Liveness, process và logs; không đưa logs chứa nội dung riêng tư lên Git.
Invoke-RestMethod http://127.0.0.1:8001/api/health
docker top shopquery-ai-api-1 -eo pid,ppid,args
docker logs --tail 50 shopquery-ai-api-1
docker logs --tail 50 shopquery-ai-web-1
git rev-parse HEAD
docker inspect --format '{{.Image}} {{index .Config.Labels "org.opencontainers.image.revision"}}' shopquery-ai-api-1
docker inspect --format '{{.Image}} {{index .Config.Labels "org.opencontainers.image.revision"}}' shopquery-ai-web-1
```

Trước stop/recreate phải kiểm active leases, Guest workers và thông báo gián đoạn;
Guest RAM mất khi API dừng. Sau đó chỉ stop exact API/Web bằng `docker stop
shopquery-ai-api-1 shopquery-ai-web-1`; giữ main DB chạy. Script promotion kiểm
active work, main identity, image revision, một worker, no reload/source bind và
ports loopback; chỉ thực hiện `up` API/Web `--no-deps --no-build --pull never`.
Phần deploy của script chưa được nghiệm thu khi controlled cutover còn pending.

Sửa `.env`/`.env.release` trong vùng private, kiểm diff tên biến mà không lộ giá trị,
rồi recreate service chịu ảnh hưởng trong cửa sổ đã duyệt. Bật
`RELEASE_PROVIDER_DATA_ENABLED=true` chỉ sau phê duyệt dữ liệu/ngân sách; Guest cần
phê duyệt riêng trước `RELEASE_GUEST_AI_ENABLED=true`. Fallback giữ OFF.
Không thử key bằng request ngoài ngân sách. Sau thay đổi chạy verification và
kiểm chức năng tương ứng; health200 không thay thế Google/provider acceptance.

Một sửa đổi nhỏ: targeted tests → push/CI đúng SHA → build image service bị đổi
hoặc reuse digest nếu build inputs không đổi → cập nhật private image ref →
verify identity → deploy API-only/Web-only → postdeploy health/auth/data smoke.
Chạy `./scripts/test.ps1` theo [testing](testing.md), integration chỉ dùng
`shopquery_test_stage1` trên DevDB. Không chạy test destructive trên main.

Nếu postdeploy FAIL, dùng rollback API/Web pin digest theo bàn giao, cùng protected
main volume và reviewed original environment; không restore/drop main DB để xóa
operational writes. Baseline images cũ không có OCI revision label nên không dùng
`release.ps1` để triển khai chúng. Chạy reviewed manual Compose sequence, rồi kiểm
image IDs, main identity, Google session/history và schema/data. Source verifier
sẽ báo drift khi baseline image khác source V2 hiện tại; đó là kết quả dự kiến
cho rollback capability, không phải bằng chứng V2 đạt nghiệm thu.
