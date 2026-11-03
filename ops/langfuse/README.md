# Langfuse trên Docker Desktop

**Đổi tên nhóm dùng chung — 04/11/2026: hoàn tất và kiểm chứng.** Tên Compose project
chuyển từ `shopquery-observability` sang `langfuse` theo yêu cầu operator; giữ nguyên
images, credentials, endpoint3000/media9090 và dữ liệu. Năm volumes cùng hai mạng
được khai báo external với tên cũ để không tạo datastore rỗng hoặc đổi clients.

**Nghiệm thu ingestion lịch sử — 27/10/2026: LANGFUSE_READY_WITH_LIMITATIONS.** Dashboard tại
[localhost:3000](http://127.0.0.1:3000). Sáu service healthy, Web/Worker ready,
project/keys thật đã tạo; API8080 đã gửi trace. Đợt nghiệm thu tiếp theo chạy6câu UI
trong ngân sách mới:10generation/3query/0document embeddings; tất cả đúng oracle.
[Ma trận và báo cáo đầy đủ](../../docs/observability_acceptance.md). Reload8080 xác nhận
session, workspace và lịch sử cũ vẫn tải được;
không thử lại luồng Google sign-in mới.

## Runtime và bằng chứng

Một project `langfuse`, sáu images pin trong `compose.yaml`, năm
volumes riêng. ShopQuery vẫn một project `shopquery-ai`, một deployment8080 và main
PostgreSQL riêng. Không tạo sandbox, test containers hoặc clone source.

| Thành phần | Phiên bản / digest prefix |
| --- | --- |
| Langfuse Web / Worker | 4.70.1 / 71b04842 / 3976a73d |
| PostgreSQL | 17 / b8faeff7 |
| ClickHouse | 25.12 / 8a790dd3 |
| Redis | 7 / bd28fff4 |
| MinIO | Chainguard / a1d2b351, digest-only |
| Python SDK | langfuse==5.0.4, uv.lock |
| ShopQuery API | source3fe4cc2 / imaged8ad8aa5e3425b803bcec9c61a5e84dd5e950a2e07dc978d70c64d7c33dcbbb2 |

Startup14:11:50 Asia/Saigon bằng containers/images có sẵn. Operator đã tự đăng ký
và đăng nhập, project ShopQuery AI đã tạo qua UI, SDK auth_check=True. Organization
AI-powered features OFF; không cấu hình model provider trong Langfuse. Keys thật
nằm trong ignored `ops/langfuse/.env` và private `.env.release`; không in resolved
Compose environment hoặc SDK responses chứa credentials ra console/Git.

Operator duyệt cutover API và recreate LF Web. Runtime instrumentation đầu14:59:26: main Web/DB
không recreate, Nginx graceful reload; strict88modules PASS/no source hoặc env drift.
Gemini default/fallbackOFF/gateON/GuestOFF/embedding2/768/vector-only giữ nguyên.
Main volume `shopquery-ai_postgres_auth_20261019` không đổi; không migrate/ghi fixture.
Không OOMKilled hoặc container tự restart trong cửa sổ kiểm; không kết luận máy đáp
ứng mọi tải từ thời gian idle này. Không thay Windows/WSL/pagefile/security policy.

Hai lỗi cấu hình đã được chứng minh bằng kết nối thực:
- Loopback health probes refused vì Web/Worker bind IP container. Đổi probes sang
  service hostname; Web health kiểm database, Worker health và Web ready trả200.
- Web thêm mạng ingestion nhưng vẫn chỉ listen IP mạng cũ. Đặt HOSTNAME=0.0.0.0 bên
  trong container; API→Web health/ready200. Host UI vẫn bind loopback. Override API
  giữ mạng backend, chỉ thêm observability; bridge default dư đã xóa khi rỗng.

Bằng chứng ingestion được đọc lại bằng Langfuse API và Dashboard:
- Trace `b618a9aeeb6c41cb9f949bd02a8cbd2f`: synthetic host root + generation,
  usage7input/3output/10total, synthetic=true, không model/provider attribution,
  nội dung input/output null, cost null. Token này là mô phỏng.
- Trace `239f68d5a87948a99e879f83f60960b7`: request thật qua8080 lúc15:02:17,
  HTTP401 do không đăng nhập, đúng một root/correlation, final_status=failure,
  nội dung input/output null; không provider dispatch. Dashboard đã thấy trace.
- Trước sửa binding, export timeout thật đã xảy ra nhưng request401 và health200
  vẫn trả bình thường. Trace đó không lưu; đây là fail-open evidence, không phải
  ingestion PASS. Không dừng/restart Langfuse để thử thêm lỗi tương tự.

## Instrumentation và quyền riêng tư

`backend/app/core/observability.py` tích hợp nhỏ từ diagnostics hiện hữu. Không đổi
SQL/RAG/Hybrid/QueryPlan/owner guards, không auto-instrumentation ghi raw content.
Một root trace mỗi correlation request; stages chỉ xuất hiện khi thực chạy, mỗi SDK
provider dispatch một generation/embedding observation. Không tạo model calls để đo.

Manual allowlist và export masking bỏ prompts, questions, documents, rows, SQL,
parameters, vectors, email, tokens/keys và private provider URL. Không export owner/
conversation identifiers thô. SDK có thể thêm project public-key định tuyến trong
metadata nội bộ; không dump toàn bộ response hoặc ảnh cột metadata vào báo cáo.

Usage lấy trực tiếp từ SDK, phân biệt measured/partial/unknown. Cached input và
reasoning là chi tiết, không cộng hai lần vào totals. Không tự suy token từ độ dài.
Failed call thiếu usage giữ UNKNOWN. Application không cung cấp billed cost; server
đã có managed Gemini3.5 Flash-Lite pricing khớp nguồn Google, auto-inferred estimate
được kiểm trong nghiệm thu. Embedding token/Knowledge price UNKNOWN, không miễn phí.

Feature flag mặc định OFF trong source; runtime8080 hiện ON theo cutover đã duyệt.
Export bất đồng bộ: queue512, batch64, interval5s, timeout1s. Queue đầy bỏ telemetry,
không chờ exporter trong request. SDK init/update/exit errors không đổi output hoặc
exception nghiệp vụ. Chỉ shutdown/short-lived synthetic script mới flush; không
flush từng request. Queue overflow và exporter bị chặn đã kiểm bằng SDK thật offline.

## Mạng và vận hành

Chỉ publish UI127.0.0.1:3000 và media127.0.0.1:9090. Không publish LF PostgreSQL,
Redis, ClickHouse hoặc Worker. Ingestion network `shopquery-observability_ingestion`
chỉ chứa LF Web/main API; main DB/Web không nối vào. API dùng
`http://langfuse-web:3000`, không dùng localhost container. LF datastore dùng mạng
riêng default. Docker logs rotation10m×3; không có nghĩa database storage bị giới hạn.

Kiểm không thay runtime:

```powershell
docker compose -p langfuse --env-file ops/langfuse/.env -f ops/langfuse/compose.yaml config --quiet
docker compose -p langfuse --env-file ops/langfuse/.env -f ops/langfuse/compose.yaml ps
./scripts/release.ps1 -Observability
Invoke-RestMethod http://127.0.0.1:8080/api/health
```

Khởi động lại containers có sẵn khi cần, không tự pull/rebuild/recreate:

```powershell
docker compose -p langfuse --env-file ops/langfuse/.env -f ops/langfuse/compose.yaml up -d --no-build --no-recreate --pull never
```

Theo chỉ thị operator hiện hành, không dừng chỉ theo ngưỡng availableRAM256MiB.
Nếu có OOM/crash loop/daemon failure hoặc ShopQuery bị ảnh hưởng, dừng graceful đúng
project bằng `docker compose ... stop --timeout -1` với file/env/project ở trên;
giữ volumes/secrets/images. Không down-v, prune hoặc chạm projects khác.

Release API sau này phải giữ `-Observability` nếu muốn giữ cấu hình này. Chỉ chạy
lệnh có mutation sau khi có immutable image/config, rollback và cutover được duyệt:

```powershell
./scripts/release.ps1 -Deploy -Service api -Observability
```

Rollback hiện hành API52701da8/source8a2c6aa và `.env.release.before` tại private
`C:\Users\admin\.codex\backups\shopquery-ai\langfuse-acceptance-20261027`;
rollback069e7f67/sourcea67242d trước instrumentation cũng được giữ. Khôi phục config
và API-only deploy trong maintenance window được duyệt; không main Web/DB recreate.
Không ghi đè secrets LF nếu volumes đã tồn tại. Không xóa năm volumes datastore.

## Chuyển tên nhóm Docker ngày04/11/2026

Đổi tên project cần recreate sáu containers vì Docker Desktop nhóm theo Compose
labels; `docker rename` riêng một container không đổi nhóm. Không chạy hai nhóm
đồng thời. Trước chuyển, kiểm inventory/mounts/immutable images/private config và
clients; dừng Web/Worker graceful, chụp hash metadata PostgreSQL/ClickHouse và object
bytes MinIO khi ingestion dừng. Dừng các datastore graceful, sao lưu cả năm volumes
qua containers đã dừng và giữ secrets riêng ngoài Git trước khi xóa containers cũ.
Không xóa volumes hoặc networks. Chỉ bỏ sáu container IDs đã xác minh thuộc nhóm cũ,
không `-v`/force; khởi động bốn datastore dưới project mới rồi so lại dữ liệu trước
khi bật Web/Worker. Sau chuyển kiểm sáu services, health/ready, ports, mounts,
credentials hash và các dự án khác. Không pull/build hoặc nâng version cho đổi tên.

Các resources `shopquery-observability_postgres-data`, `clickhouse-data`,
`clickhouse-logs`, `redis-data`, `minio-data` đều dùng đầy đủ prefix lịch sử ở Compose;
mạng `shopquery-observability_default`/`shopquery-observability_ingestion` giữ nguyên.
Nếu resource thiếu thì Compose phải từ chối thay vì tạo mới. Khi cần rollback tên,
dừng/xóa đúng containers mới sau khi giữ backup rồi dùng `-p shopquery-observability`
với cùng cấu hình external/images/secrets để khởi động lại; không restore đè hoặc
chạy hai nhóm trên cùng datastores. Main ShopQuery API/Web/DB không recreate.

Preflight phát hiện worker đã có timeout Redis trước đổi tên:540lượt khớp cụm
`Socket timeout`/360dòng cóerror trong10phút, Web0error; Redis PING từ workerPONG
(211ms). Healthcheck6/6xanh không chứng minh mọi queue hoạt động. Đổi tên không được
gọi là đã sửa nguyên nhân queue hoặc nghiệm thu ingestion mới. Không gọi model để
thử đổi tên.

Kết quả chuyển tên thực tế:

- Source/config `820f3d8beab317622c84db2a67554c82f16dbad7` đã vào main/origin;
  [PR7](https://github.com/MinhHoang1403/Shopquery-AI/pull/7) được tích hợp bằng
  fast-forward. [CI đúng commit](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/41700215289)
  đạt 4/4 jobs (Observability/Backend/Frontend/PostgreSQL); 10/10 Compose tests local PASS.
- Đã dừng graceful sáu container cũ, sao lưu năm volumes khi tất cả datastore dừng.
  Archive tổng 2.888.998.307 bytes, kiểm gzip/tar đọc hết, SHA256 và số files; private
  `.env`/config được giữ cùng backup ngoài Git tại
  `C:/Users/admin/.codex/backups/langfuse/rename-20261104/`. Không coi đây là restore
  drill hoặc bản off-host. Bản trước và volumes gốc không bị ghi đè/xóa.
- Đã xóa đúng sáu containerIDs cũ bằng `docker container rm`, không force/`-v`;
  tạo lại đúng sáu trong project `langfuse`, không pull/build/upgrade images. Không
  còn container của project `shopquery-observability`. Tên mới gồm
  `langfuse-langfuse-web-1`, `langfuse-langfuse-worker-1` và bốn datastore.
- Trước bật lại Web/Worker, so mọi row có hash canonical của 84 bảng PostgreSQL và
  14 bảng ClickHouse (dùng FINAL khi engine cần), cùng tên/size/SHA256 của 949 tệp MinIO:
  khớp hoàn toàn. Redis dùng đúng volume AOF đã sao lưu, không reset queue; không
  nhận là đã so logical Redis keys bất biến sau khi worker hoạt động.
- Runtime sáu services healthy, 0 restart/OOM; images/environment digests, mounts,
  networks và ports không đổi. UI/title Langfuse/health/ready HTTP 200, 0 browser pageerrors;
  đã xem ảnh trang đăng nhập sạch, không giả đăng nhập hoặc tạo tài khoản mới.
  Dùng credentials project đã cấu hình để đọc 1 observation cũ qua API v2 HTTP 200.
  Probe đầu dùng endpoint traces cũ trả 404 đúng hành vi v4; chuyển sang v2, không đổi
  server/data để làm probe PASS. Không có inference hoặc write trace mới.
- Inventory trước/sau cutover: 50 images/36 volumes/31 containers, không thêm image/volume;
  sáu IDs cũ được thay bằng sáu IDs mới. 25 container ngoài Langfuse giữ nguyên IDs/image
  refs/mounts/restart counts/trạng thái. Main ShopQuery đang dừng từ trước cutover,
  không tự khởi động/recreate API/Web/DB chỉ để đổi tên dịch vụ dùng chung.
- Sau restart Web/Worker, cửa sổ kiểm khoảng 3 phút chưa tái hiện socket timeout/error
  (0 matches), khác với baseline có lỗi. Đây là quan sát ngắn, không chứng minh đã
  sửa nguyên nhân upstream hoặc ổn định lâu dài. Retention, restore drill, tải dài
  hạn và các giới hạn nghiệm thu trước vẫn còn; không dùng tên mới để che lỗi cũ.

Đã dọn sạch containers dư trong phạm vi chuyển tên. Không có image Langfuse cũ không
được tham chiếu: sáu image pins đều dùng thật, giữ nguyên. Studio đã có báo cáo riêng
về tám images cũ bị xóa và rollback DAC giữ lại; không global prune hoặc xóa stopped
containers của các ứng dụng khác vì trạng thái Stopped không đồng nghĩa tài nguyên bỏ.

## Kiểm thử và giới hạn

Targeted telemetry/provider/error/auth/context/binding và10 Compose tests PASS trên CI main; observability.py
có26 parametrized test cases với SDK thật/InMemorySpanExporter, không provider/network.
Phủ correlation/nesting/single-dispatch, usage/cache/reasoning/missing, privacy/raw
exception, OFF, SDK errors, bounded queue overflow. Compose resolver thật kiểm pins,
loopback ports, credentials required, storage/network isolation, probes và queue512.
CI application source3fe4cc2 PASS3jobs. Không tự chạy lại full regression/golden.

Lệnh targeted khi source liên quan thay đổi:

```powershell
./scripts/test.ps1 -Tests tests/test_observability.py
./scripts/invoke-python.ps1 -PythonArguments @('ops/langfuse/test_compose.py', '-v')
```

**Còn giới hạn:** embedding token usage upstream không có, Knowledge price UNKNOWN,
persistence qua restart toàn bộ datastore, retention và backup/restore drill.
Generation Gemini/Knowledge và query embeddings đã nghiệm thu live trong6câu UI;
SDK totals khớp32601generation tokens. Gemini managed pricing auto-infers estimate,
không phải hóa đơn hoặc tổng chi phí mọi provider.
Không dùng synthetic token test làm live SQL/RAG/Hybrid acceptance. Cửa sổ ngân sách agent mới đã đóng10generation/3query/0document; không dùng dư.

Retention chưa được cấu hình hoặc nghiệm thu. Theo dõi dung lượng trace/storage;
không tự đặt TTL/xóa blobs vì có thể phá ingestion. Backup phải bảo vệ PostgreSQL
(users/projects/keys), ClickHouse, Redis queue, MinIO và SALT/ENCRYPTION_KEY/private
secrets. Snapshot đồng bộ năm volumes chỉ sau maintenance window dừng ingestion và
graceful stop đúng project; không sao chép live DB directory hoặc main volume.
Backup mã hóa ngoài source/host, kiểm checksum; restore drill cần operator duyệt.
Đây là các giới hạn vận hành dài hạn, không blocker của ingestion đã chứng minh.

## Nguồn

- [Compose chính thức4.70.1](https://github.com/langfuse/langfuse/blob/v4.70.1/docker-compose.yml).
- [Health/readiness](https://langfuse.com/self-hosting/configuration/health-readiness-endpoints).
- [SDK](https://langfuse.com/docs/observability/sdk/overview).
- [Backup](https://langfuse.com/self-hosting/configuration/backups).
- [Docker Compose project name](https://docs.docker.com/reference/compose-file/version-and-name/),
  [external volumes](https://docs.docker.com/reference/compose-file/volumes/) và
  [external networks](https://docs.docker.com/reference/compose-file/networks/): giữ
  resource names độc lập project, thiếu thì fail closed; đã kiểm 04/11/2026.
- [Langfuse Public API](https://langfuse.com/docs/api-and-data-platform/features/public-api)
  và [migration API cũ](https://langfuse.com/faq/all/deprecated-api-migration): v4 dùng
  Observations API v2, endpoint traces cũ 404; đã kiểm 04/11/2026 cùng runtime thật.

Lịch sử preflight/lần stop đầu được giữ trong docs/deployment.md và Git; chỉ thị
khởi động mới đã thay các hạn chế cũ. Không mở lại RAM audit hoặc nghiên cứu VM.
