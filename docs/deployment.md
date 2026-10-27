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

Current API source `a67242d1e6a1e267c440eeb6547c7ddbd961fb9a`.
API digest `069e7f67fb409ac3a587c6327104f509bf3182ca2d410e281f2f3cf90818c599`.
Web source `02d5cbb445901f7eb63f82bee87e2e8785d35663`.
Web digest `ae181335b61aa738f6b0b1c2c1c450fe46a5ba26b4688d5c294d541975696a58`.
Docs-only commits sau đó không yêu cầu rebuild. Kiểm digest, OCI revision và bytes,
không chỉ tin tên tag. Các nhãn candidate/development cũ không xác định runtime.

27/10/2026 10:00:55–10:01:11 API-only cutover cho Knowledge predicate wire constraints
và approved identity grouping completion. CI40441018076 exact main/testa67242d PASS
1365backend/857isolated PostgreSQL; Web không thay nên frontend job SKIPPED, không build.
API3ce1af0d/Webc6f1f591/DB511c4f5a, strict87modules/no drift/health8080/Nginx PASS.
Web/DB image/container/start time, protected main volume giữ nguyên; không migrate/BGE.
Final schema/40table fingerprints và old-history prefix PASS; chỉ quota/login metadata
và2conversations/4messages UI mới. Google login/workspace/history/reload PASS.
Knowledge SQL15PASS/1UNKNOWN(recorder lỗi), Gemini compatibility1PASS, RAG/Hybrid smoke
mỗi nhánh1PASS/citation23. Không loại UNKNOWN để promote: Gemini default/fallbackOFF,
gateON/GuestOFF, embedding2/768/vector-only giữ nguyên. Final status
`KNOWLEDGE_NOT_ACCEPTED — GEMINI_PRODUCTION_READY`, không tuyên bố model failure từ
instrumentation failure. Agent budget đã đóng36Knowledge(debit gồm2unknown)/2Gemini/
2query/0document; không retry hoặc dùng phần dư. Không tiếp tục cải tiến sau bàn giao.
Immediate rollback API67a891b0/sourcef6f44ae + `.env.release.before` tại private
backups/shopquery-ai/knowledge-final-20261027. Không xóa images/volumes/prune trong lượt
này. Xem [acceptance hiện hành](v2_final_acceptance.md) trước các đoạn lịch sử bên dưới.

## Langfuse localhost — đã thử một lần và dừng an toàn, 27/10/2026

**BLOCKED_RUNTIME_RESOURCES.** Chỉ thị mới cho phép đúng một lần trên Docker7.415GiB.
Pull6pinned images thành công; `up -d`12:09:41 Asia/Saigon tạo đủ6containers/5volumes
riêng project `shopquery-observability`. Bốn datastores healthy, Web/Worker còn
starting. Windows available RAM472MiB xuống254/184MiB ở2mẫu cách khoảng5giây;
ngưỡng bảo thủ256MiB kích hoạt graceful stop riêng Langfuse, xong12:10:41. Không OOM,
crash/restart hoặc ShopQuery failure; không khẳng định eventual OOM từ các mẫu này.
Sau dừng available1469MiB. Không đổi WSL/pagefile, đóng app, tuning RAM hoặc thử lại.

Giữ6stopped containers,6current images,5named volumes, network riêng và private secrets;
không cleanup/prune/dùng main DB. Web exit143 doSIGTERM, Worker/4datastores exit0,
mọi OOMKilledfalse/RestartCount0. Xem [runbook và bằng chứng](../ops/langfuse/README.md).
Không SDK/instrumentation/project keys, không Dashboard/trace ingestion/usage/cost/
privacy/fail-open acceptance; không READY, không merge như integration đã hoàn tất.

8080HTTP200 xuyên suốt mẫu đo; API3ce1af0d/Webc6f1f591/DB511c4f5a với images và start
times giữ nguyên. Main volume `shopquery-ai_postgres_auth_20261019` không đổi; Gemini
default/fallbackOFF/gateON/GuestOFF/embedding2/768/vector-only giữ nguyên. Không build,
recreate/migrate ShopQuery hoặc gọi provider. Phần dưới là lịch sử trước chỉ thị mới.
Kiểm sau stop:9Compose tests PASS, strict87modules PASS/no source hoặc environment
drift/3services healthy. Google login/history UI không nghiệm thu lại trong lượt này.

## Langfuse sau restart — lịch sử cấu hình VM trước chỉ thị localhost, 27/10/2026

**BLOCKED_INSUFFICIENT_RESOURCES — CONFIG_ONLY — LIVE_PENDING.** Windows boot11:45:57,
đo11:52:57 Asia/Saigon: RAM15.31GiB, khả dụng1.47GiB, commit20.65GiB/pagefile1199MiB,
CPU4%, disk135.52GiB. Docker vẫn7.415GiB/12CPU, Linux available6.29GiB gồm cache có
thể thu hồi. Không có bằng chứng peak/headroom đủ cho sáu service; không thay WSL,
swap hoặc dừng ứng dụng operator. Cổng3000/3030/9000/9090 chưa có listener; chưa start
Langfuse, không pull layers, tạo volumes hay mua/triển khai VM.

Nhánh `codex/langfuse-observability` từ maina6d337d chuẩn bị
[Compose/runbook VM](../ops/langfuse/README.md): đúng6service/5volumes riêng,
digest pins được registry xác nhận, template secrets trống bắt buộc, loopback3000/9090,
datastores không publish, Docker log rotation.9offline config tests PASS; không thay
backend/app/dependencies hoặc Compose ShopQuery. Không merge main hay deploy
instrumentation khi chưa nghiệm thu hạ tầng. Chi tiết images/sizing, kết nối private
TLS, retention/backup/restore và các gates còn lại nằm trong runbook đó.

Strict87modules PASS sau restart, API069e7f67/sourcea67242d và Webae181335/source02d5cbb
vẫn đúng immutable images;3ShopQuery container IDs/protected volume giữ nguyên,
chỉ start times thay do Windows reboot.8080/API/main PostgreSQL healthy. Giữ default
Gemini/fallbackOFF/gateON/GuestOFF/embedding2/768/vector-only. Không gọi provider, chưa
có trace/token/cost/fail-open/live acceptance mới. UI Google reload sau reboot chưa
được kiểm trong lượt cấu hình; không dùng kết quả lịch sử thay verification hiện tại.

## Langfuse trước restart: preflight dừng do thiếu tài nguyên — 27/10/2026

**BLOCKED_INSUFFICIENT_RESOURCES**. Chưa pull/start Langfuse, chưa tạo Compose project,
network, volumes, credentials, SDK dependency hoặc instrumentation. Không sửa/rebuild/
recreate API/Web/DB8080 và không gọi provider. Đây là dừng tại gate tài nguyên, không
phải integration đã được thử rồi thất bại. Mục17 của yêu cầu operator bắt buộc dừng
nếu máy không đáp ứng; không tự nới Docker/WSL memory hoặc đóng ứng dụng của operator.

Phần quy tắc đã hoàn tất trước preflight: `AGENTS.md` commit
`ac4111e53a18c64979746cd75c3fc32ff172be6e`, push origin/main và đối chiếu remote SHA
khớp. Giữ quy tắc cũ, bổ sung chất lượng/tên/source/Git/Docker/kiểm thử/telemetry,
ngoại lệ đủ sáu service Langfuse vận hành và bảo vệ dữ liệu. Không có AGENTS.md con.
Không mở branch tích hợp khi gate đã chặn; thay đổi bàn giao này chỉ là docs.

### Bằng chứng tài nguyên

Đo bằng CIM Windows, `/proc/meminfo` của Docker Desktop, `docker info/stats/system df`,
volume C và listener inventory, khoảng10:46 Asia/Saigon. Không tạo test containers.

| Hạng mục | Kết quả |
| --- | --- |
| RAM vật lý Windows |15.31GiB tổng;1.51–1.58GiB khả dụng; ba mẫu1549/1547/1555MiB |
| Commit/pagefile |27.8GiB committed; pagefile đang dùng3156MiB, allocated26624MiB |
| Paging tại ba mẫu |Pages/sec0/31/99, PageReads/sec0/3/15; không gọi đây là benchmark hoặc chứng minh paging nghiêm trọng liên tục |
| Docker Desktop/WSL2 |7.415GiB tổng,12logical CPUs; WSL MemAvailable khoảng6.25GiB bao gồm phần có thể thu hồi; không coi đây là RAM vật lý mới ngoài Windows |
| ShopQuery khi nhàn rỗi |API183.9MiB, Web18.37MiB, DB65.25MiB; không đại diện peak khi chat/ingest |
| Ổ C |475.91GiB tổng,135.03GiB trống; chưa dành/reserve dung lượng cho traces |
| Docker storage hiện có |41images/50.03GB;27volumes/1.816GB; build cache53.59GB; có layer dùng chung, không cộng thành số dung lượng có thể thu hồi |
| Cổng |3000/3030/5432/6379/8123/9000/9001/9090 không thấy TCP listener tại thời điểm đo;8080/8001/15432 vẫn loopback |

[Hướng dẫn Compose chính thức](https://langfuse.com/self-hosting/deployment/docker-compose)
khuyến nghị VM ít nhất4cores/16GiB RAM và khoảng100GiB storage cho tracing.
Đây là khuyến nghị VM, không phải bằng chứng rằng mọi workload đều cần chính xác16GiB.
[Sizing chính thức](https://langfuse.com/self-hosting/configuration/scaling) nêu
ClickHouse8GiB, Web/Worker mỗi4GiB, PostgreSQL4GiB, Redis1.5GiB, blob storage4GiB.
Riêng ClickHouse theo sizing này đã vượt toàn bộ RAM Docker hiện có. Windows gần hết
headroom, nên chưa có cơ sở an toàn để nhận thêm sáu service vận hành. Không thử giới
hạn RAM thấp, swap hoặc cắt service bắt buộc để tìm một lần startup may mắn.

### Phiên bản đã tra và phương án triển khai tiếp

- Stable server được tra là
  [Langfuse v4.70.1](https://github.com/langfuse/langfuse/releases/tag/v4.70.1).
  [Compose tại release đó](https://github.com/langfuse/langfuse/blob/v4.70.1/docker-compose.yml)
  có Web/Worker/PostgreSQL/ClickHouse/Redis/MinIO. Chỉ đọc upstream, không clone repo
  thứ hai hay áp dụng mặc định secrets/tag major trong file mẫu.
- PyPI JSON thực lúc preflight trả Python SDK5.0.4, Python>=3.11; search cache còn
  hiển thị SDK4 nên không dùng cache chọn major. [SDK overview/compatibility](https://langfuse.com/docs/observability/sdk/overview)
  yêu cầu SDK5 với server>=4.59.0. Chưa cài SDK, kiểm dependency compatibility dự án,
  chọn/pin image digest hoặc xác nhận ingestion runtime; không coi tra version là PASS.
- Dùng máy/VM riêng cho `shopquery-observability`, cấu hình vẫn quản lý trong
  `ops/langfuse/` của repository này. Khởi điểm Compose theo khuyến nghị16GiB/4vCPU/
  100GiB; ưu tiên32GiB nếu cấp đủ các mức RAM theo từng service cộng headroom OS.
  Chốt kích thước/retention theo tải thực, không hứa capacity chưa đo.
- Trên VM riêng: sáu service chính thức, volumes/DB riêng, secret ngẫu nhiên, image
  stable pin digest. UI bind127.0.0.1:3000, có thể dùng SSH forwarding để truy cập;
  endpoint telemetry từ API phải qua kết nối riêng có TLS/auth phù hợp. Docker bridge
  cục bộ không tự nối qua hai máy. Không expose main DB hoặc dùng localhost container
  sai nghĩa; không tự mở LAN/Internet trong lượt này.
- Khi có tài nguyên phù hợp mới tiếp tục branch ngắn hạn, instrumentation tối thiểu
  từ diagnostics, metadata-only/privacy, measured/UNKNOWN token usage, cost có nguồn,
  bounded async export/fail-open, targeted tests/CI rồi triển khai và live smoke mới.
  Không reuse ngân sách đã đóng hoặc đổi SQL/RAG/Hybrid/default/fallback để giám sát.

### Trạng thái ShopQuery và bàn giao

Strict verifier87modules PASS, source/image/environment không drift;8080 và API health
trả200. Runtime vẫn API069e7f67/sourcea67242d, Webae181335/source02d5cbb, mainDB511c4f5a
và protected volume giữ nguyên. Không thực hiện database writes/migrations/data cleanup;
không chạy lại full regression hoặc fingerprint toàn corpus khi chỉ sửa quy tắc/docs.
Gemini default/fallbackOFF/gateON/GuestOFF, embedding2/768/vector-only giữ nguyên.
Không phát sinh generation/query/document embeddings. Không có Langfuse login URL đang
vận hành, project keys, traces, pricing configuration, fail-open tests hoặc live smoke
được nghiệm thu. Không báo LANGFUSE_READY. CI application không chạy lại cho docs-only;
`git diff --check` PASS. Ba script bảo trì untracked của operator được giữ nguyên.
Không tạo/xóa container/image/volume/cache nào, không thay settings Windows/WSL.

## Lịch sử triển khai trước preflight Langfuse

26/10/2026 17:03 cutover theo quyền triển khai có điều kiện trong master audit:
exact-main/test `272cbf81`, CI40303628357 PASS1349backend/833PG/85frontend/125mockE2E.
Application inputs khớp hai OCI revisions trên; chỉ tests khác API sourcef6f44ae.
API8569f0b1/Webc6f1f591, strict87modules/health/Nginx PASS. Main DB511c4f5a/volume
không recreate trong cutover. Final fingerprints40tables: chỉ thêm2conversations,
8messages và resource counters; toàn bộ dữ liệu/docs/vectors/relationships/history
cũ giữ nguyên. DB từng interruption/recovery09:11UTC trước cutover, nguyên nhân chưa
rõ; không tuyên bố uptime liên tục. Xem [audit](architecture_audit.md).
Gemini SQL5/5, RAG3/3; Knowledge RAG3/3; hai provider Hybrid/follow-up UI2/2 mỗi bên
đúng Decimal oracle/citation23. Knowledge SQL JOIN vẫn chặn wire predicate_reference,
không execute; các mẫu SQL Knowledge còn lại dừng. Gemini default, fallbackOFF,
gateON/GuestOFF, embedding2/768/vector-only giữ nguyên; không BGE/migrate/paid retry.
Audit thực dùng29generation/10query/0document embeddings; conservative debit65/16/0
trong ngân sách mới200/100/30. Đã kết thúc agent tests, normal gate tiếp tục ON.
Immediate rollback API2be89452/Web03f83efc và private `.env.release.before-audit-cutover`
trong backups/shopquery-ai/architecture-audit-20261026. Không FULL_PASS/Stage2/tag.

Các đoạn triển khai dưới đây là lịch sử; không dùng image refs lịch sử làm cấu hình hiện hành.

26/10/2026 15:22–15:23 operator-approved API/Web cutover: bounded conversion
diagnostics và typed inline result presentation. CI40291179613(main/testad087dcd)
PASS561backend/119PG/85frontend/125mockE2E, application bytes khớp08d71b9.
Strict87modules/health/Nginx syntax+graceful reload PASS. APIdbea3568/Web7a028386;
DB511c4f5a/protected volume/image/start time không đổi. Google session/history giữ.
Live Gemini hotel filter16rows và category12groups/2400/638885507.75 PASS oracle;
Knowledge COUNT+SUM360/33066538.03 PASS. Knowledge JOIN blocked trước execution tại
plan_compilation/sql_validation f93ddf2487a14353a848acfbba5bd457; RAG/Hybrid/follow-up
NOT_RUN, acceptance window đóng theo điều kiện. Không đổi Gemini default,
fallbackOFF/gateON/GuestOFF/embedding2/768/noBGE. Budget agent9generation, conservative
13/18 gồm2lượt song song trước cutover;0query/document embeddings, không retry.
Immediate rollback: API6994abd7/source0656765 và Web127da3e8/sourcefd1f510, private
contract-repair-20261026/.env.release.before giữ nguyên. Không FULL_PASS/tag.

26/10/2026 14:29 operator-approved API/Web cutover: category grouping repair,
explicit Knowledge planning wire contract, natural neutral SQL summaries and compact
error details. CI40285627334 PASS508backend/118PostgreSQL/80frontend/110mockE2E;
strict87modules/Nginx syntax+graceful reload/Web+API8080PASS. DB511c4f5a và protected
volume/start time không đổi. Q1Gemini hotel category livePASS12rows/oracle; Q2Gemini
filter failed atcontract_conversion before binding/execution. Paid window stopped:
2questions/4generation/0embeddings; Knowledge/RAG/Hybrid NOT_RUN. Gemini default,
fallbackOFF/gateON/GuestOFF/embedding2/768/noBGE retained, no migrations/re-embed.
Rollback APIe49f838/fbfeb03f and Web881bfe1/5f4ab329 retained with private config
snapshot sql-repair-20261026/.env.release.before. See current acceptance for limits.

26/10 planning/fallback correction deployed API-only after operator approval and
exact-main CI497unit/116PostgreSQL PASS. Strict86modules and Nginx reload PASS.
Knowledge live SQL failed binding with outcomequery, then a separately approved
diagnostic failed root PlanDecision wire validation. No speculative prompt/schema/
guard change or activation followed; Gemini default/fallbackOFF/gateON/GuestOFF
retained. Current acceptance details the blockers and two closed paid windows.
Web/DB identities unchanged. Immediate API rollback sourceb48cfc2/digest626a8704
retained with private .env.release.before under knowledge-root-cause-20261026.

26/10 PDF correction: operator-approved API-only cutover, Nginx syntax/graceful
reload and strict verifier86 modules PASS. Original PDF uploaded once via8080,
3 chunks/vectors persisted and visible after reload. Web/DB not recreated;
schema, business data, old documents/vectors, relationships and history unchanged.
Gemini/provider gateON retained, no BGE/migration. Immediate API rollback source
`df10688740f945b9b68f240673b74248b260081d`, digest
`df8dff610cd912e048964ba8350fa1dfc240c2fe948cec013184b97750465741` retained with
private pre-cutover config snapshot. See current acceptance for budget/evidence.

26/10 Knowledge endpoint recheck: running API already has the administrator-updated
URL from private .env; resolved Compose/runtime match, so no recreate was needed.
Connectivity and two bounded text/strict-schema probes PASS. First live SQL UI
question failed planning sql_validation before execution; acceptance stopped.
The prior plan=None inference is unproven because the old stage also wrapped binding.
Knowledge default/fallback switch was NOT performed. Gemini/default, fallbackOFF,
gateON, GuestOFF, current images/containers and data remain unchanged. A tested
fallback candidate is held privately, not applied or deployed; see current acceptance
for the specific activation blockers and actual4-stage/0-embedding usage.

### Vận hành hiện tại — Gemini mặc định, 25/10/2026

Operator yêu cầu dùng Gemini cho tài khoản đăng nhập. Private `.env.release`, nạp
sau `.env`, đặt `AI_DEFAULT_MODEL=gemini`, generation `gemini-3.5-flash-lite`,
embedding `gemini-embedding-2`, `GEMINI_RETRY_ATTEMPTS=1`, fallback OFF,
`RELEASE_PROVIDER_DATA_ENABLED=true`, Guest AI OFF; reranker path vẫn rỗng.
Embedding model cũng được cố định trong base Compose. Key khớp cấu hình hiệu lực;
`models.get` xác nhận cả hai model và loại tác vụ, không gọi generation/embedding.

Không sửa source/build inputs hoặc rebuild. API-only recreate và Nginx syntax check/
graceful reload PASS; Web/DB/images giữ nguyên. Strict verifier PASS: 84 modules,
không source/image/environment drift. `/api/models` authenticated trả default Gemini,
AI enabled và fallback false. Chat mới mặc định Gemini; chat cũ đổi được bằng selector,
không bulk rewrite history. Knowledge adapter/config được giữ; chọn Knowledge vẫn có
thể nhận503 từ upstream.

Smoke có điều kiện đã duyệt: SQL tổng360/33066538.03 PASS; JOIN12trạm, mỗi trạm30phiên
và toàn bộ phí khớp PostgreSQL oracle PASS; Hybrid từ chối tại policy_verification /
insufficient_evidence sau retrieval/planning/SQL12rows thành công; follow-up NOT_RUN.
Dùng3chats/4generation/1query embedding/0document embeddings, không retry/fallback.
Không tự reuse budget dư để dò lỗi. Normal-operation gate vẫn ON sau smoke; Guest AI
OFF, quotas/concurrency/owner scope giữ nguyên. Xem acceptance để biết giới hạn.

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

Knowledge investigation25/10:effective provider config khớp Compose,local DNS/TCP/TLS
PASS,no proxy env/mounts. Non-generation GET models/health và direct TLS GET models
đều503 với HAProxy-default107byte HTML fingerprint. Chưa có upstream admin logs để
phân biệt route mismatch/backendDOWN/maintenance;không đổi base URL,timeout,model,
retry hoặc serving theo suy đoán. Operator không có server admin access;private
handoff ở existing ev-acceptance-20261024/knowledge-503-admin-handoff.md. Endpoint
identity lưu riêng ngoàiGit. Không gửi probe generation thật hoặc tự bật gate.
Sau provider recovery cần xác nhận model-list/API support rồi xin ngân sách mới
tối đa1text+1structured synthetic probe trước khi tiếp tục functional acceptance.

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

Rollback hiện hành là cặp đã chạy trước architecture audit:

- API `shopquery-ai-api@sha256:2be8945280dbb710f287209ecead2731a9b81b96050c5ed65ef5a3b9ecbceb5d`.
- Web `shopquery-ai-web@sha256:03f83efc5f4b46452f20baa7a82a16c7289662cbdffa701b8396ac4733dd0fb3`.
- Cả hai source `08d71b9020bafd76a131d48733a6ba8fb466e7bd`; đã kiểm image tồn tại local.
- Private config `.env.release.before-audit-cutover` dưới
  backups/shopquery-ai/architecture-audit-20261026; không in credentials.

API6994abd7/Web127da3e8 còn giữ thêm. Các refs fec296b4/5db99157 trong lịch sử
đã được cleanup sau inventory, không còn là rollback vận hành. Không dùng snapshot
cũ để deploy mù hoặc nhầm source revision của image hiện hành với main test/docs HEAD.
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
Sau khi đóng cửa sổ24/10,operator yêu cầu25/10 dùngGemini làmdefault và bật lại
normal operation. Trạng thái mới nhất:provider gateON,GuestAI/fallbackOFF,
vector-only/noBGE. Không auto-close normal gate khi agent smoke kết thúc;không reuse
unused paid test budget. Normal gate chỉ đổi theo phê duyệt mới nhất của operator.

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

### Upload-to-chat UX validation

Approved26/10 cutovers deployed API/Webdf10688 then Web-only881bfe1. Strict86modules,
image/source/config identities, health8080, Google session/history and3table previews
against independent PostgreSQL cell hashes PASS. Final Web-only switch retained
API/DB container/start identities. No paid calls, main migrations or data resets.
Protected volume and all business/document/relationship/history fingerprints held.
Rollback refs/config are retained privately under backups/shopquery-ai/ux-20261026-e7ef020.

Workflow hiện có hỗ trợ `workflow_dispatch scope=ux, services=all`: preview/owner/
resource/relationship unit checks, PostgreSQL integration trên service CI cô lập,
frontend lint/typecheck/unit/build và mock browser routing. Không tạo local DB mới
hoặc ghi fixture lên main để chạy các test này. Preview mới dùng registered table
ID, reader READ ONLY, timeout5s và giới hạn1–50rows; UI tải25rows khi mở từng bảng.
Không gọi provider để mở manager, đọc liên kết hoặc xem dữ liệu đã nhập.
`scope=layout, services=frontend` chỉ chạy frontend quality và10 relationship/preview
browser cases, gồm17cột và modal-scroll boundary. Dùng khi chỉ thay CSS/Web; không
chạy lại backend/PostgreSQL/golden đã đạt nếu inputs không đổi.

Nếu postdeploy FAIL, dùng rollback pin digest ở đầu runbook, cùng protected main
volume và reviewed environment; kiểm image IDs, main identity, Google session/history
và schema/data. Source drift của rollback phải được báo trung thực.
