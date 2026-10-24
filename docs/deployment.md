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

API source `5d4c595965ad379b85627dac227034446e673ef7`, digest `26877f4176df1dc17924cee02491df349f8d0b548252d547e7294d9775df72df`.
Web source `5d4c595965ad379b85627dac227034446e673ef7`, digest `bd7601be72e6d60aae704ff3f857a8f91162a89a9f0f54a534f7a15656210467`.
Docs-only commits sau đó không yêu cầu rebuild. Kiểm digest, OCI revision và bytes,
không chỉ tin tên tag. Các nhãn candidate/development cũ không xác định runtime.

### Reliability artifacts — deployed 24/10/2026

Application source `5d4c595965ad379b85627dac227034446e673ef7` đã push main;
backend targeted CI460 tests + PostgreSQL131 tests PASS tại
[CI40101327066](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/40101327066).
Frontend inputs không đổi sau `fcf230b`:73 unit +105 mock browser checks PASS tại
[CI40100969466](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/40100969466).

- API: `shopquery-ai-api@sha256:26877f4176df1dc17924cee02491df349f8d0b548252d547e7294d9775df72df`.
- Web: `shopquery-ai-web@sha256:bd7601be72e6d60aae704ff3f857a8f91162a89a9f0f54a534f7a15656210467`.
- Cả hai OCI revision khớp đủ40 ký tự; source build inputs khớp commit này.
- Đã pin private config, deploy API/Web trên8080; main DB không recreate.
- Operator đã xử lý quyền Python/DLL; cùng .venv import select/subprocess được.
  Strict verifier sau deploy và sau gate-close PASS:84 modules khớp source,
  image/revision/environment khớp, không source drift. Không đổi security policy.
- UI Google session/history reload PASS; Xe điện còn3tables/3docs/2approved N:1.
- Cửa sổ MỚI được duyệt10chats/14generation/4query embeddings/0document embeddings.
  Chỉ Q1 được gửi một lần, explicit SQL/Knowledge:HTTP503 tại planner, không Router.
  Error context giữ status503/category transient_unavailable/phase request/attempt1,
  attempted_route SQL/correlation2424518bb21940e2b878641eae2e0609. Không thực thi SQL.
- BLOCKED_PROVIDER; dừng ngay theo điều kiện cửa sổ, không retry/fallback/provider swap.
  Q2–Q10 NOT_RUN, follow-up chưa có tiền đề KPI. Used1generation/0embeddings.
- Provider gate OFF sau API-only recreate+Nginx graceful reload; Web giữ container.
-37tables/schema/business data/docs/vectors/relationships/auth rows giữ nguyên,
  chỉ chat_conversations/chat_messages/resource_limits thay đổi; old messages giữ hash.

Q9 cũ vẫn unresolved ở exact invalid field, chưa có live confirmation Gemini/Hybrid
trên image mới. Không coi error-path verification hoặc HTTP200 là SQL/Hybrid PASS.

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

Rollback ngay trước reliability cutover giữ local: API
`shopquery-ai-api@sha256:5db99157ab742e200a9ab5e24c757d7ac7fa16ddf05db12a8078451837c70bf6`, Web
`shopquery-ai-web@sha256:e888860e87a1baff7149fbe5d7b354dedba7b9e0888bca9c1c9f654e108ab744`,
cùng source `a49d4ebb7dd8d132103a17f1b798ef40c102ac3b`. Private config/baseline và
live trace dưới existing backup folder `ev-acceptance-20261024`, prefix reliability.
Rollback không xóa metadata liên kết/history. Không dùng tag latest hoặc xóa rollback duy nhất.

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
Sau yêu cầu bật normal operation trước đó, operator đã duyệt cửa sổ Xe điện mới
ngày24/10 và yêu cầu đóng gate cuối lượt. Trạng thái mới nhất: provider gate OFF,
Guest AI/fallback OFF, vector-only/no BGE. Không tự reuse budget hoặc tự bật gate.
Normal operation gate chỉ đổi theo phê duyệt rõ ràng mới nhất của operator.

Windows scripts dùng invoke-python.ps1 với đúng .venv executable hiện hành,
redirect stdout/stderr trước khi đặt encoding và đọc cả hai stream bất đồng bộ.
Không dùng shell thứ hai hoặc interpreter fallback. Deploy preflight import các
verifier dependencies trước khi cutover; Application Control chặn DLL/executable
phải báo BLOCKED, không chỉnh security policy hoặc coi manual checks là strict PASS.

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
