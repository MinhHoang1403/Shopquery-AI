# Langfuse trên Docker Desktop

**BLOCKED_RUNTIME_RESOURCES — một lần khởi động đã dùng, không thử lại.**

## Kết quả lần thử localhost, 27/10/2026

- Pull thành công cả6immutable images trong `compose.yaml`. Chỉ một lệnh `up -d`
  lúc12:09:41 Asia/Saigon, Docker vẫn7.415GiB; không đổi WSL/Windows hoặc dừng app khác.
- Cả6containers đã chạy; PostgreSQL/ClickHouse/Redis/MinIO healthy. Web/Worker còn
  `starting`; **chưa** chứng minh app readiness, Dashboard/login hoặc ingestion.
- Giám sát host thấy available RAM472→449→371→344→311→254→184MiB. Hai mẫu cuối cách
  khoảng5giây dưới256MiB (ngưỡng dừng bảo thủ của lần thử, không phải minimum do
  Langfuse công bố). Tín hiệu thực tế này kích hoạt stop, không phải sizing16GiB.
  Mẫu độc lập trong lúc dừng170MiB; sau dừng1469MiB. Không có OOMKilled/restart hoặc
  bằng chứng ShopQuery failure; không suy ra Langfuse chắc chắn sẽ OOM nếu chờ thêm.
- Graceful stop **riêng** project, exit CLI0; hoàn tất12:10:41. Web exit143 doSIGTERM,
  Worker và4datastores exit0; mọi RestartCount0/OOMKilledfalse. Không SIGKILL, không
  điều chỉnh RAM/thử lại. Container/images,5volumes và private `.env` được giữ nguyên.
- API8080HTTP200 trong toàn bộ các mẫu; API/Web/DB IDs/images/start times không đổi.
  Không recreate API/Web/DB, không migrate hoặc ghi main dữ liệu, không paid calls.
- Kiểm sau dừng:9Compose tests PASS; strict verifier87modules PASS, không source/
  environment drift,3ShopQuery services healthy và đúng main volume. Google login/
  history UI không kiểm lại trong lần thử này; không dùng kết quả lịch sử làm PASS mới.
- SDK chưa cài, không project/API keys hoặc trace thật. Token/cost/privacy/fail-open
  integration và Dashboard đều **NOT_VERIFIED**; không báo READY từ4healthchecks.
  Không nối network ShopQuery hoặc bật flag instrumentation. Không merge nhánh chỉ
  có cấu hình này vào main như một integration hoàn tất.

Chỉ thị mới ngày27/10 cho phép **một lần khởi động có kiểm soát** trên Docker Desktop
hiện tại, thay điều kiện dừng theo sizing khuyến nghị trước đó. Dùng lại cấu hình này,
không đổi giới hạn7.415GiB, Windows/WSL hoặc dừng ShopQuery/ứng dụng khác. Kết quả
runtime phải ghi riêng sau lần thử; Compose config PASS chưa chứng minh ingestion.
Chưa có SDK/instrumentation hoặc endpoint ShopQuery→Langfuse đang chạy.

## Preflight sau restart, trước chỉ thị thử localhost

Đã đọc AGENTS.md/README/deployment/audit/acceptance và báo cáo maintenance ngoài repo.
Không cập nhật lại AGENTS.md: main đã có quy tắc tại ac4111e. Baseline branch từ
origin/main `a6d337d4ff94108c9ac93be410ef60d99559821c`; giữ ba script untracked của operator.

Windows boot11:45:57.5; đo11:52:57 Asia/Saigon, uptime khoảng7phút. RAM15.31GiB,
khả dụng1.47GiB; committed20.65GiB, pagefile1199MiB, CPU4%, C trống135.52GiB.
Docker Desktop/WSL2 có12CPU,7.415GiB tổng; Linux MemAvailable6.29GiB gồm reclaimable
cache, không phải thêm6.29GiB RAM vật lý độc lập với Windows. Paging mẫu3pages/s,
không suy ra overload liên tục. ShopQuery idle: API200.1MiB/Web13.79MiB/DB52.07MiB;
chưa đo peak ingestion/chat. Không đóng ứng dụng để tăng số đo, không đổi WSL/swap.

Chỉ3containers ShopQuery đang chạy;18containers/41images/27volumes, Docker images50.03GB,
cache44.37GB và volumes1.816GB. Không có Langfuse;3000/3030/9000/9090 chưa có listener.
Restart không recreate container: API3ce1af0d/image069e7f67/sourcea67242d,
Webc6f1f591/imageae181335/source02d5cbb, DB511c4f5a/protected volume giữ nguyên.
Strict87modules PASS/no source/config drift;8080/API/DB healthy. Không gọi AI.
Session/history được bảo vệ trong DB; UI Google reload sau restart chưa nghiệm thu
trong lượt chuẩn bị cấu hình này, không coi dữ liệu tồn tại là login UI PASS mới.

Theo [Compose chính thức](https://langfuse.com/self-hosting/deployment/docker-compose),
VM khởi điểm4vCPU/16GiB/100GiB. [Sizing từng service](https://langfuse.com/self-hosting/configuration/scaling)
nêu ClickHouse8GiB, Web/Worker mỗi4GiB, PostgreSQL4GiB, Redis1.5GiB, MinIO4GiB.
Đây là hướng dẫn sizing khác nhau, không bảo đảm mọi tải. Riêng ClickHouse đã lớn hơn
tổng RAM Docker hiện hành theo sizing, nhưng operator đã cho phép thử tải thực tế.
Không dùng sizing này làm điều kiện tự động từ chối lần thử. Trace storage vẫn cần
đo sau ingestion; cộng index/blob/logs/backup và dung lượng trống khi đặt retention.

## Nguồn và pin images

Nền tảng là [Compose release4.70.1](https://github.com/langfuse/langfuse/blob/v4.70.1/docker-compose.yml).
Không clone source Langfuse, không dùng Kubernetes hoặc stack khác.
Registry manifests được tra bằng `docker buildx imagetools inspect` ngày27/10;
trước khi pull. Digest trong compose.yaml là multi-platform index đã kiểm có Linux
amd64; pull thành công đơn lẻ chưa chứng minh runtime đã nghiệm thu.

| Service | Nguồn pin |
| --- | --- |
| Web/Worker | docker.langfuse.com, release4.70.1, index71b04842/3976a73d |
| ClickHouse | upstream25.12, index8a790dd3, đáp ứng v4 minimum25.12 |
| PostgreSQL | official17, indexb8faeff7, manifest amd64 version17.11 |
| Redis | official7, indexbd28fff4, manifest amd64 version7.4.12 |
| MinIO | cgr.dev/chainguard/minio từ upstream Compose, indexa1d2b351, build26/10; chỉ digest, không tag latest chạy động |

[SDK hiện hành](https://langfuse.com/docs/observability/sdk/overview): Python5.0.4
(PyPI JSON kiểm trực tiếp, Python>=3.11), cần server>=4.59.0. Chưa cài/lock SDK vào
ShopQuery hoặc chứng minh dependency compatibility. Không dùng legacy trace()/span().

## Cấu hình được chuẩn bị

`compose.yaml`: đúng6service,5named volumes project riêng, một mạng default riêng;
không nối ShopQuery hoặc dùng main PostgreSQL. Chỉ publish UI127.0.0.1:3000 và
MinIO media127.0.0.1:9090; worker3030, DB5432, Redis6379, ClickHouse8123/9000,
MinIO console9001 không publish. Redis auth healthcheck, AOF/noeviction; Docker
json-file rotation10m×3 mỗi service. ClickHouse system-table logs cần giám sát riêng;
Docker log rotation không giới hạn database growth. Chưa ép per-service RAM limits
thấp để thử may rủi trên máy này.

Credentials thật nằm trong `ops/langfuse/.env`, bị Git ignore. Mỗi secret riêng được
sinh bằng bộ tạo số ngẫu nhiên mật mã,32bytes/64hex; không dùng giá trị template.
Encryption key đúng32random bytes/64hex. PostgreSQL dùng hex
để không gây ambiguity URL encoding. Không in secrets hoặc resolved Compose JSON
vào logs; `config --quiet` là kiểm tra cấu hình phù hợp. Thiếu bất kỳ secret nào
Compose phải từ chối; template trống không được dùng để tuyên bố integration PASS.

## Vận hành localhost theo chỉ thị hiện hành

Tại repository gốc, kiểm Docker hoạt động,8080healthy,3000/9090không xung đột và
còn dung lượng. Không audit máy lại hoặc thay memory limits. Secrets phải đã có
trước `config --quiet`; không ghi đè `.env` nếu volumes đã tồn tại.

```powershell
docker compose -p shopquery-observability --env-file ops/langfuse/.env -f ops/langfuse/compose.yaml config --quiet
docker compose -p shopquery-observability --env-file ops/langfuse/.env -f ops/langfuse/compose.yaml pull --quiet
# Chỉ một lần khởi động trong cửa sổ đã duyệt, kèm giám sát bên dưới:
docker compose -p shopquery-observability --env-file ops/langfuse/.env -f ops/langfuse/compose.yaml up -d
```

Trong startup và sau đó kiểm API8080, DB/API health/start time/restart/OOM, trạng
thái Langfuse và Windows available memory cơ bản. Có OOM, crash loop, daemon restart,
Windows thiếu RAM nghiêm trọng hoặc ShopQuery bị ảnh hưởng: **dừng riêng Langfuse**,
giữ5volumes/.env/images; không `down -v`, không thử cấu hình RAM khác hoặc restart
vòng lặp. Dùng `docker compose ... stop --timeout -1` với đúng project/file/env ở
trên để chờ graceful stop; kiểm ShopQuery lại và báo `BLOCKED_RUNTIME_RESOURCES`.

Dashboard `http://127.0.0.1:3000`, media `http://127.0.0.1:9090`. Không có default
admin; tạo user/org/project và API keys bằng luồng chính thức, không bịa email/keys.
Nếu ổn định và có credentials thật, chỉ nối API và Langfuse Web bằng mạng ingestion
cần thiết; DB ShopQuery không nối mạng Langfuse. Endpoint bên trong API phải là
Docker hostname, không dùng `127.0.0.1:3000`. Hiện chưa thêm mạng này vào ShopQuery.

Xác minh4datastores health/auth, Web login và worker readiness theo
   [hướng dẫn health](https://langfuse.com/self-hosting/configuration/health-readiness-endpoints).
Đã thêm healthcheck wget theo tài liệu cho Web/Worker; Web kiểm cả database.
Kiểm riêng `/api/public/ready`; health PASS/`up --wait` đơn lẻ không đủ để chấm
ingestion. Kiểm ingestion synthetic được gắn nhãn, worker queue drains,
persistence qua restart chỉ service Langfuse. Các bước này chưa được thực hiện;
không tạo test containers/stack.

## Retention, backup và restore

Chốt retention ban đầu nhỏ (đề xuất7ngày) trước production ingestion, theo khả năng
edition và cơ chế retention được phiên bản thực hỗ trợ; kiểm deletion ở cả ClickHouse
và blob storage. Chưa xác minh edition/license/UI trên instance thật. Nếu chưa có
retention được kiểm thì không mở telemetry production vô hạn; giám sát disk, tạm dừng
agent ingestion trước khi thiếu chỗ. Không đặt TTL/lifecycle xóa blob tùy ý vì late
events có thể sai/deduplicate không đúng. Không tự kích hoạt deletion ở lượt chuẩn bị.

Theo [backup chính thức](https://langfuse.com/self-hosting/configuration/backups),
bảo vệ PostgreSQL(project/users/keys), ClickHouse(observations), MinIO(raw events/blobs),
Redis(queue) và private secrets, đặc biệt SALT/ENCRYPTION_KEY. Storage snapshots
có thể dùng sau khi ngừng ingestion và gracefully stop **riêng project này** trong
maintenance window; chụp đồng bộ tất cả5volumes, giữ manifest image digests và mã
kiểm tra. `docker volume inspect` tìm exact mountpoints, không đoán data-root.
Không dùng helper containers, không sao chép live data directory khi DB đang ghi.

Lưu snapshot/secret backup mã hóa, ngoài source/host chính, hạn chế quyền và xác minh
checksum. Restore khi có operator approval: dừng Langfuse, phục hồi bộ volume nhất
quán và đúng secrets/digests trên chính host đã duyệt, khởi động datastores trước rồi
Web/Worker; kiểm auth/trace counts/queue/blob identity trước nối lại API. Không đổi/xóa
main ShopQuery volume, không `down -v`. Backup/restore drill chưa được chạy, là gate
trước khi coi dữ liệu monitoring có khả năng phục hồi.

## Phần tích hợp tiếp theo — chưa triển khai

Chỉ sau hạ tầng và endpoint/auth PASS: thêm layer nhỏ từ diagnostics, mặc định OFF;
`LANGFUSE_BASE_URL/PUBLIC_KEY/SECRET_KEY` theo SDK, feature flag `LANGFUSE_ENABLED`
là cấu hình ứng dụng cần triển khai, **hiện chưa có hiệu lực trong ShopQuery**.
Manual spans metadata-only, một root/correlation request, nesting SQL trong Hybrid,
mỗi call một observation. Không auto callbacks/raw contents/duplicate counts.
Pseudonymous owner/conversation, SDK measured vs UNKNOWN/cached/reasoning usage, không
tự tính token bằng độ dài hoặc bịa Knowledge price. Gemini cost cần đối chiếu pricing
chính thức đúng model tại lúc tích hợp; hiện chưa đặt bảng giá/cost.

Trước API deploy cần tests fail-open OFF/missing keys/SDK exception/timeout/restart/
queue bounded; outputs/taxonomy giữ nguyên, không sync export/flush mỗi request.
Sau đó CI, API-only controlled cutover, main-data/strict/UI verification. Không rebuild
Web. Synthetic traces chỉ kiểm telemetry, phải gắn nhãn mô phỏng; chưa có ngân sách
mới nên live Gemini/Knowledge/RAG/Hybrid/embedding đều **LIVE_PENDING**,0paid requests.

## Kiểm chứng cấu hình

```powershell
./scripts/invoke-python.ps1 -PythonArguments @('ops/langfuse/test_compose.py', '-v')
```

9unittest với Compose resolver thực:6services/digestpins/loopbackports/storage/network/
dependency và health endpoints/logrotation/8missing-secret cases/template không credentials.
Chỉ `docker compose config`, không daemon mutation hoặc generation. Workflow
`Observability configuration` chạy đúng test này, không service/testcontainers hoặc
backend/frontend full regression. Runtime/fail-open/trace usage chưa kiểm, không ghi PASS.
