# Runtime và deployment

Một source chính `C:\Work\ShopQuery AI` trên `main`, một Compose project
`shopquery-ai`, API8001/Web8080/main PostgreSQL15432 trên loopback. Active volume
`shopquery-ai_postgres_auth_20261019`; không recreate hoặc xóa volume này.
Archived/test volumes được giữ, không dùng làm main. Exact release order:
`compose.yaml`, `.env.compose-ui.yaml`, `.env.join-v1.yaml`, `compose.release.yaml`;
env files `.env` trước, `.env.release` sau. Local overrides bị Git ignore.

| File | Vai trò hiện hành |
| --- | --- |
| `.env` | Credentials và cấu hình nền private; không commit |
| `.env.release` | Pin API/Web digest, main volume và release gates private |
| `.env.compose-ui.yaml` | Override cổng loopback của deployment này |
| `.env.join-v1.yaml` | Bật approved JOIN; tên v1 là tên cấu hình, không phải app cũ |
| `.env.example` | Template không có credentials cho người phát triển |
| `compose.yaml`, `compose.release.yaml` | Base và override của deployment chính |
| `compose.dev.yaml`, `compose.gpu.yaml`, `compose.release.gpu.yaml` | Công cụ test/maintenance hoặc GPU opt-in; không phải stack đang chạy |

Không xóa/đổi tên hai local YAML overrides khi scripts và Compose labels còn
tham chiếu chúng. Không in resolved environment hoặc đưa file private vào Git.

API source `ac369738f152ad2f685fbbd86fb71cdfa51fad8d`, digest `f161d7f5a441e7d036e4ecf97c3e4bd864edeefaf00820c577bb3c8cf31a2fa9`.
Web source `e76dfed2ebcfaebcf37e36485d3041eda68f4209`, digest `e4a8c96c742bfaf2e6ff834fb320f457dc443ad4df4fedcf797094461e99bfb1`.
Docs-only commits sau đó không yêu cầu rebuild. Kiểm digest, OCI revision và bytes,
không chỉ tin tên tag. Các nhãn candidate/development cũ không xác định runtime.

Trước switch kiểm mounts, health, active leases và in-flight workers. Auth sessions
lưu DB được giữ; Guest RAM không sống qua API recreate. Exec process mới không đọc
được GuestStore của process đang chạy. Không coi worker count là số idle sessions.
Không recreate main `db`, đổi main key/schema/data hoặc xóa volumes để chuyển modes.

Development tools và isolated test DB vẫn thuộc source. Không chạy dev API/Web
song song hoặc chuyển8080 sang DevDB khi chỉ cần targeted tests. Test DB
`shopquery_test_stage1` dùng volume `shopquery-ai_postgres_dev_stage1`, chỉ cần chạy
lúc integration test; container có thể tái tạo từ Compose với volume còn nguyên.
Không seed/ingest/fake Google user trên main.

## Rollback đã giữ

Rollback API gần nhất là `shopquery-ai-api@sha256:1a57c0d151944309951bd32a2e9f21baca79ad3b82caf05683a81c3c2f7659a9`,
source `5ba7669535e05d3779a0f2b5832be781405f9000`, đã từng phục vụ cùng Web hiện hành.
Web không đổi trong các patch API; giữ thêm Web legacy `5ca6e17125f12574cf8cdf4d030b6a0a209007e9469b264e94e6d98056090146`
làm bản dự phòng cuối. Private rollback/environment evidence được giữ ngoài Git.
Không giữ mọi image patch cũ; không dùng tag `latest` để chọn bản chạy.

Rollback phải kiểm active work, pin đúng digest/private config và kiểm source drift.
Nếu source khác image rollback, strict verifier phải báo đúng khác biệt; dùng
reviewed manual Compose API-only sequence, không bỏ guard để tạo PASS giả. Không
restore/drop main DB để xóa operational writes. Environment/credentials thay đổi
không được coi là exact rollback dù image giống nhau.

## Release

Trạng thái nghiệm thu hiện hành nằm trong [nghiệm thu V2](v2_final_acceptance.md);
Image rollback hiện hành được ghi ở đầu hướng dẫn này; báo cáo lịch sử có trong Git tại `87cdf40`.
Operator đã duyệt controlled acceptance cutover8080 ở chế độ vector-only để dùng
Google/history/upload trong khi Gate C tạm hoãn. Đây chưa phải Stage2/full release
acceptance. PR#1 đã merge theo chỉ đạo consolidation riêng; chưa tag V2. Không lặp GPU benchmark.

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

Trong cửa sổ operator tạm hoãn BGE, đặt dòng **`RELEASE_RERANKER_PATH=`** rỗng trong
private `.env.release`. `compose.release.yaml` dùng default `/models/bge` khi biến
không được đặt; explicit empty chọn đường vector retrieval đã có và không tạo model.
Không thêm GPU overlay khi chạy vector-only; không âm thầm chuyển BGE sang CPU.
Đổi cấu hình này cần recreate riêng API rồi kiểm trực tiếp8080; không sửa dữ liệu
hoặc build image. Giữ model artifact read-only để có thể nghiệm thu BGE sau này.
Gate C vẫn BLOCKED/DEFERRED; RAG/Hybrid vector-only không phải BGE GPU PASS.

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
# Hiện hành: vector-only, RELEASE_RERANKER_PATH= trong private .env.release.
# Read-only: source/image/environment drift phải làm lệnh FAIL.
./scripts/release.ps1

# Start/promote API/Web; không build, pull hoặc recreate main DB.
./scripts/release.ps1 -Deploy
./scripts/release.ps1 -Deploy -Service api
./scripts/release.ps1 -Deploy -Service web

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
Deploy branch đã thực hiện thành công cho controlled vector-only cutover: đúng
API/Web digests, main container không recreate, source/image/environment verifier
PASS và health8080 PASS. GPU mode chưa được nghiệm thu.

API-only recreate có thể đổi địa chỉ nội bộ của API. Script chờ API healthy rồi
chạy `nginx -t` và graceful reload trong Web hiện có để refresh upstream address.
Web không recreate; thiếu/fail proxy reload làm deployment báo lỗi. Luôn kiểm
`http://127.0.0.1:8080/api/health`, không chỉ health8001 hoặc trang HTML8080.

Sửa `.env`/`.env.release` trong vùng private, kiểm diff tên biến mà không lộ giá trị,
rồi recreate service chịu ảnh hưởng trong cửa sổ đã duyệt. Bật
`RELEASE_PROVIDER_DATA_ENABLED=true` chỉ sau phê duyệt dữ liệu/ngân sách; Guest cần
phê duyệt riêng trước `RELEASE_GUEST_AI_ENABLED=true`. Fallback giữ OFF.
Không thử key bằng request ngoài ngân sách. Sau thay đổi chạy verification và
kiểm chức năng tương ứng; health200 không thay thế Google/provider acceptance.
Trong các bounded live window, SDK retry attempts đặt1 cho cả Gemini và
Knowledge; không manual retry. Chỉ dùng verified synthetic fixture; hết cửa sổ
hoặc gặp blocker thì tắt `RELEASE_PROVIDER_DATA_ENABLED` và recreate riêng API.
Điều đó giữ Google/history/tabular upload, chặn paid chats/document embeddings.
Sau nghiệm thu, operator đã yêu cầu bật lại để sử dụng bình thường: provider gate
hiện ON cho tài khoản đăng nhập, Guest AI/fallback OFF, vector-only/no BGE. Đây
không phải cửa sổ test phải tự đóng; xem mục F trong [acceptance](v2_final_acceptance.md).

Một sửa đổi nhỏ: targeted tests → push/CI đúng SHA → build image service bị đổi
hoặc reuse digest nếu build inputs không đổi → cập nhật private image ref →
verify identity → deploy API-only/Web-only → postdeploy health/auth/data smoke.
Chạy `./scripts/test.ps1` theo [testing](testing.md), integration chỉ dùng
`shopquery_test_stage1` trên DevDB. Không chạy test destructive trên main.

Ví dụ cập nhật riêng API từ root, giữ nguyên bộ dependency CUDA của image hiện hành;
vector-only vẫn do `RELEASE_RERANKER_PATH=` quyết định, không tải BGE khi build:

```powershell
git switch main
git pull --ff-only
# Sửa source, chọn đúng test liên quan; không chạy toàn bộ suite mỗi lần.
Push-Location backend
./.venv/Scripts/python.exe -m pytest tests/test_plan_providers.py tests/test_providers.py tests/test_gemini.py -q
Pop-Location
git add -p
git commit -m "Describe the verified fix"
git push origin main
$taskRevision = git rev-parse HEAD
docker build -f backend/Dockerfile --build-arg SOURCE_REVISION=$taskRevision --build-arg INSTALL_RERANKER=true --build-arg RERANKER_EXTRA=reranker-cuda -t shopquery-ai-api:main-$taskRevision .
docker image inspect --format '{{json .RepoDigests}}' shopquery-ai-api:main-$taskRevision
# Pin digest vừa build vào SHOPQUERY_API_IMAGE trong private .env.release.
# Chỉ sau khi operator duyệt thời điểm gián đoạn API:
./scripts/release.ps1 -Deploy -Service api
Invoke-RestMethod http://127.0.0.1:8080/api/health
```

Kiểm cả UI8080, session/history và hành vi đã sửa sau deploy; health không chứng
minh AI đúng. Khi chỉ sửa Web, build frontend/Dockerfile rồi pin/deploy riêng web.
Không đổi dependency extra, key, volume hoặc bật paid gates trong ví dụ này.

Nếu postdeploy FAIL, dùng rollback pin digest ở đầu runbook, cùng protected main
volume và reviewed environment; kiểm image IDs, main identity, Google session/history
và schema/data. Source drift của rollback phải được báo trung thực.
