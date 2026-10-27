# Chuẩn bị Langfuse trên VM riêng

**BLOCKED_INSUFFICIENT_RESOURCES — CONFIG_ONLY — NOT_DEPLOYED — LIVE_PENDING.**
Không chạy `up`/`pull` trên máy Windows hiện tại. Nhánh này chỉ chứa cấu hình đã kiểm
tra offline, không có SDK/instrumentation hoặc endpoint ShopQuery→Langfuse đang chạy.
Không dùng Compose config PASS để công nhận health, login, ingestion hay fail-open.

## Preflight sau restart, 27/10/2026

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
tổng RAM Docker hiện hành; không có headroom Windows/ShopQuery/peak phù hợp. Không
dùng swap hoặc bỏ service bắt buộc để vượt resource gate.

Đề xuất VM **4vCPU tối thiểu, ưu tiên8vCPU/32GiB RAM/100GiB SSD hoặc hơn**, Linux
Ubuntu được Docker hỗ trợ.32GiB là đề xuất headroom cho các service cộng OS, không
capacity/SLA đã đo. Trace storage theo events/ngày×bytes/event×retention, cộng index,
blob, logs, backup và dung lượng trống; chỉ đo được sau ingestion thực. Không tự mua
VM. Cần operator cung cấp host/quyền SSH, mạng riêng/VPN, DNS/TLS và nơi backup.

## Nguồn và pin images

Nền tảng là [Compose release4.70.1](https://github.com/langfuse/langfuse/blob/v4.70.1/docker-compose.yml).
Không clone source Langfuse, không dùng Kubernetes hoặc stack khác.
Registry manifests được tra bằng `docker buildx imagetools inspect` ngày27/10;
không pull image layers, tạo container/network/volume. Digest trong compose.yaml là
multi-platform index đã kiểm có Linux amd64; không phải build/runtime đã nghiệm thu.

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
thấp khi chưa đo VM và workload.

Không có credentials thật. Sau khi host được duyệt, copy `.env.example` thành `.env`
trên VM, `chmod600`; tạo riêng mỗi secret bằng `openssl rand -hex32` (lệnh thật bên
dưới có khoảng trắng). Encryption key đúng32random bytes/64hex. PostgreSQL dùng hex
để không gây ambiguity URL encoding. Không in secrets hoặc resolved Compose JSON
vào logs; `config --quiet` là kiểm tra cấu hình phù hợp. Thiếu bất kỳ secret nào
Compose phải từ chối; template trống không được dùng để tuyên bố integration PASS.

## Thực hiện trên host đã được duyệt, chưa chạy trong lượt này

1. Xác minh CPU/RAM/disk/ports/architecture/quyền và backup destination; giữ VM riêng.
   Dùng checkout cùng repository/commit, không tạo source ShopQuery thứ hai trên máy
   hiện tại; chỉ chuyển thư mục cấu hình này tới VM bằng quy trình operator cho phép.
2. Trong thư mục cấu hình trên VM (Linux shell):

   ```bash
   umask 077
   cp .env.example .env
   chmod 600 .env
   # Mỗi lần sinh một secret riêng; nhập vào .env bằng editor an toàn, không ghi log:
   # openssl rand -hex 32
   docker compose --env-file .env -f compose.yaml config --quiet
   # Chỉ khi resource/security gates và thời điểm triển khai đã duyệt:
   docker compose --env-file .env -f compose.yaml pull
   docker compose --env-file .env -f compose.yaml up -d
   docker compose --env-file .env -f compose.yaml ps
   ```

3. Truy cập UI/media bằng SSH forwarding cổng3000/9090. Không có default admin;
   operator tạo user/org/project và API keys thật. Không tạo email/account giả.
   Không public DB/Redis/ClickHouse hoặc gửi telemetry qua Internet HTTP.
4. Với API trên máy Windows: cần endpoint HTTPS qua VPN/private network có DNS và
   certificate tin cậy. Dùng reverse proxy được quản trị trên VM chuyển HTTPS tới
   loopback3000, hạn chế ingress từ ShopQuery/VPN; xác minh từ API container. Docker
   bridge không nối hai máy. Chưa có host nên không đặt hostname/endpoint giả trong
   ShopQuery, không thay Compose/API mạng đang chạy. Public/media URL phải theo luồng
   SSH hoặc TLS thực, không dùng localhost3000 bên trong API container.
5. Xác minh4datastores health/auth, Web login và worker readiness theo
   [hướng dẫn health](https://langfuse.com/self-hosting/configuration/health-readiness-endpoints).
   Đã thêm healthcheck wget theo tài liệu cho Web/Worker; Web kiểm cả database.
   Kiểm riêng `/api/public/ready`; health PASS/`up --wait` đơn lẻ không đủ để chấm
   ingestion. Kiểm ingestion synthetic được gắn nhãn, worker queue drains,
   persistence qua restart chỉ service Langfuse. Không tạo test containers/stack.

## Retention, backup và restore

Chốt retention ban đầu nhỏ (đề xuất7ngày) trước production ingestion, theo khả năng
edition và cơ chế retention được phiên bản thực hỗ trợ; kiểm deletion ở cả ClickHouse
và blob storage. Chưa xác minh edition/license/UI trên instance thật. Nếu chưa có
retention được kiểm thì không mở telemetry production vô hạn; giám sát disk, tạm dừng
agent ingestion trước khi thiếu chỗ. Không đặt TTL/lifecycle xóa blob tùy ý vì late
events có thể sai/deduplicate không đúng. Không tự kích hoạt deletion ở lượt chuẩn bị.

Theo [backup chính thức](https://langfuse.com/self-hosting/configuration/backups),
bảo vệ PostgreSQL(project/users/keys), ClickHouse(observations), MinIO(raw events/blobs),
Redis(queue) và private secrets, đặc biệt SALT/ENCRYPTION_KEY. VM/storage snapshots
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
