# Langfuse trên Docker Desktop

**LANGFUSE_READY_WITH_LIMITATIONS — 27/10/2026.** Dashboard tại
[localhost:3000](http://127.0.0.1:3000). Sáu service healthy, Web/Worker ready,
project/keys thật đã tạo; API8080 đã gửi trace. Không có provider call trả phí trong
đợt tích hợp. Reload8080 xác nhận session, workspace và lịch sử cũ vẫn tải được;
không thử lại luồng Google sign-in mới.

## Runtime và bằng chứng

Một project `shopquery-observability`, sáu images pin trong `compose.yaml`, năm
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
| ShopQuery API | source8a2c6aa / image52701da8a2d0fb40f5825647ef955936148271cad47c0838dcbaeaca41983285 |

Startup14:11:50 Asia/Saigon bằng containers/images có sẵn. Operator đã tự đăng ký
và đăng nhập, project ShopQuery AI đã tạo qua UI, SDK auth_check=True. Organization
AI-powered features OFF; không cấu hình model provider trong Langfuse. Keys thật
nằm trong ignored `ops/langfuse/.env` và private `.env.release`; không in resolved
Compose environment hoặc SDK responses chứa credentials ra console/Git.

Operator duyệt cutover API và recreate LF Web. Runtime cuối14:59:26: main Web/DB
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
Failed call thiếu usage giữ UNKNOWN. Cost chưa có bảng giá được cấu hình/kiểm chứng
cho exact models; không coi null/UNKNOWN là miễn phí hoặc bịa giá Knowledge.

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
docker compose -p shopquery-observability --env-file ops/langfuse/.env -f ops/langfuse/compose.yaml config --quiet
docker compose -p shopquery-observability --env-file ops/langfuse/.env -f ops/langfuse/compose.yaml ps
./scripts/release.ps1 -Observability
Invoke-RestMethod http://127.0.0.1:8080/api/health
```

Khởi động lại containers có sẵn khi cần, không tự pull/rebuild/recreate:

```powershell
docker compose -p shopquery-observability --env-file ops/langfuse/.env -f ops/langfuse/compose.yaml up -d --no-build --no-recreate --pull never
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

Rollback image API069e7f67/sourcea67242d và `.env.release.before` được giữ tại private
`C:\Users\admin\.codex\backups\shopquery-ai\langfuse-20261027-1450`. Khôi phục config
và API-only deploy trong maintenance window được duyệt; không main Web/DB recreate.
Không ghi đè secrets LF nếu volumes đã tồn tại. Không xóa năm volumes datastore.

## Kiểm thử và giới hạn

123 targeted backend tests và10 Compose tests PASS trên CI main; observability.py
có17 parametrized test cases với SDK thật/InMemorySpanExporter, không provider/network.
Phủ correlation/nesting/single-dispatch, usage/cache/reasoning/missing, privacy/raw
exception, OFF, SDK errors, bounded queue overflow. Compose resolver thật kiểm pins,
loopback ports, credentials required, storage/network isolation, probes và queue512.
CI application source8a2c6aa cũng PASS3jobs. Không tự chạy lại full regression/golden.

Lệnh targeted khi source liên quan thay đổi:

```powershell
./scripts/test.ps1 -Tests tests/test_observability.py
./scripts/invoke-python.ps1 -PythonArguments @('ops/langfuse/test_compose.py', '-v')
```

**Chưa kiểm:** telemetry của generation/embedding trả phí thực, cost với giá exact
models, persistence qua restart toàn bộ datastore, retention và backup/restore drill.
Không dùng synthetic token test làm live SQL/RAG/Hybrid acceptance. Không có ngân sách
provider mới cho nhiệm vụ này; generation/query/document embeddings thực đều0.

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

Lịch sử preflight/lần stop đầu được giữ trong docs/deployment.md và Git; chỉ thị
khởi động mới đã thay các hạn chế cũ. Không mở lại RAM audit hoặc nghiên cứu VM.
