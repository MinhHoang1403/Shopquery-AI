# ShopQuery AI V2 — nghiệm thu Stage 2

**STAGE 2 PARTIAL — ACCEPTANCE BLOCKED**

Ngày kiểm tra: 2026-10-23, Asia/Saigon. Đây là báo cáo hiện hành; các kết quả
preparation trong handoff không thay thế nghiệm thu live. Theo chỉ đạo operator
mới, tạm hoãn Gate C và ưu tiên khôi phục8080; không chạy lại GPU benchmark hoặc
offline suites đã PASS. Controlled acceptance cutover đã được duyệt và thực hiện;
không merge/tag, cleanup phá hủy hoặc tuyên bố Stage2 hoàn tất.

## Version và runtime

- Branch/HEAD bắt đầu: `codex/shopquery-mvp-v2-stage1`,
  `9b35540ee949ba83dff892ec75242c9e908be33b`.
- Remote main chưa merge: `0062e47d75cc51646bf9b45409a12aa49288552e`.
- [Draft PR #1](https://github.com/MinhHoang1403/Shopquery-AI/pull/1).
- Image source: `e76dfed2ebcfaebcf37e36485d3041eda68f4209`.
- API: `shopquery-ai-api@sha256:e3989166a219acc914e009e66fb245d3c586b9cd01ce639c0a017324b02e49a7`.
- Web: `shopquery-ai-web@sha256:e4a8c96c742bfaf2e6ff834fb320f457dc443ad4df4fedcf797094461e99bfb1`.
- Không rebuild; serving application, entrypoint, dependencies và Dockerfiles không
  đổi. Stage2 sửa host verification/release scripts, test fixtures và documentation.
  `verify_runtime.py` được chạy từ host ở HEAD hiện hành; bản copy của script này
  trong immutable candidate vẫn cũ và không được serving runtime gọi. Không tuyên
  bố toàn bộ bytes/source scripts trong image bằng HEAD mới.
- Merge SHA/tag: chưa có. [CI handoff HEAD](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39889897340)
  PASS. CI Stage2 phải đối chiếu exact HEAD tại [checks PR #1](https://github.com/MinhHoang1403/Shopquery-AI/pull/1/checks);
  SHA/run hiện hành được ghi trong PR body khi bàn giao, không suy từ run handoff.
- CUDA image: Torch `2.14.1+cu130`, Sentence Transformers `5.7.0`;
  BGE revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, FP32 dự kiến.
- Stage2 host verification/tests/report commit `f66feb2023939aae1eee5c67b5d436660560fa2b`:
  [CI 3/3 PASS](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39896418747).
- **8080 hiện chạy release API/Web images nêu trên, main DB**, API8001 và Nginx8080
  healthy; no reload/source bind, một worker. Google config hiện hữu đã khôi phục.
  `RELEASE_RERANKER_PATH=` trong private `.env.release` chọn vector-only có sẵn,
  không nạp BGE trên CPU hoặc GPU. Gate C vẫn chưa đạt.
- Main DB15432 giữ container `511c4f5aacccd1ac42261aaa2a7173ae40c5c5e3aa673bb4898d988a8206a3c8`
  và protected volume; không recreate/migrate/re-ingest. DevDB vẫn được giữ riêng.

## Gates và functional acceptance

| Gate | Kết quả hiện tại |
| --- | --- |
| A — preflight/backup/restore | PASS; 34 tables, schema và protected identities được đối chiếu |
| B — offline regression/gold | PASS; backend1049, PostgreSQL804, frontend68, browser105, gold60 |
| C — BGE release/memory | DEFERRED/BLOCKED theo operator; giữ nguyên memory guard, không benchmark lại |
| D — Google thật | Login/reload/logout/relogin/history PASS theo operator và DB session/revocation; A-B live chưa đủ |
| E — Knowledge/Gemini thật | RAG/citations cả hai providers PASS; Knowledge SQL FAIL; Gemini Hybrid provider rejection |
| F — UI/business live | Release8080/Google/history/Guest CSV-XLSX/RAG smoke hoạt động; SQL/Hybrid còn blocker |
| G — merge/tag/deploy | Controlled release8080 vector-only đã duyệt; merge/tag/full acceptance vẫn BLOCKED |
| H — cleanup | DEFERRED theo yêu cầu, chỉ sau stable accepted V2 |

| Chức năng | Offline | Live | Final |
| --- | --- | --- | --- |
| Google Login | OIDC/cookie/CSRF mocks trong backend suite | Login/reload/logout/relogin PASS, fresh session và revocation đúng owner | PASS phạm vi1 account; A-B live chưa đủ |
| Auth/history | Backend/PostgreSQL PASS | Operator thấy workspace/history cũ sau reload | PARTIAL |
| CSV/XLSX | Backend/PostgreSQL PASS | Guest CSV upload/preview, XLSX preview PASS qua8080 | PASS phạm vi smoke; auth upload chưa live |
| SQL single table | Backend/PostgreSQL/gold PASS | Knowledge plan bị guard từ chối trước execution | FAIL live probe |
| SQL 2–3 table JOIN | Backend/PostgreSQL/gold PASS | Knowledge plan bị guard từ chối trước execution | FAIL live probe |
| PDF/DOCX/TXT/Markdown, RAG/citations | Parser/contracts/PostgreSQL/gold PASS | Persisted Markdown RAG/citations cả hai providers PASS, vector-only | PASS phạm vi1 policy chunk; formats khác chưa live |
| BGE GPU release | Load bị guard-stop; chưa có inference result | Chưa chạy | BLOCKED |
| Hybrid | Backend/PostgreSQL/gold PASS | Gemini retrieval PASS, generation QueryPlan bị provider từ chối | FAIL live probe; chưa có SQL/decisions |
| Knowledge | Mock contracts PASS | RAG PASS; SQL plan bị từ chối trước execution | PARTIAL |
| Gemini | Mock contracts PASS | RAG PASS; Hybrid generation bị provider từ chối | PARTIAL |
| Guest | Backend contracts PASS; Guest AI OFF | Session/upload/preview/reset PASS, private datasets401 | PASS phạm vi smoke |
| Security/owner isolation | Backend/PostgreSQL PASS | Chưa chạy | PENDING |
| Persistence | Main protected data giữ nguyên; PostgreSQL PASS | Google reload/history cũ hiển thị, live turns đã persist | PASS phạm vi đã quan sát |

## Offline regression và benchmark MVP

- Backend: **1049 PASS**, 820 deselected, 55.29s; HTTP transport thật bị chặn.
- Ruff: PASS. PowerShell parse `dev.ps1`/`release.ps1`: PASS.
- Runtime verifier: 7 cases PASS; actual development positive exit0; actual release
  expectation trên development image/environment exit nonzero đúng như yêu cầu.
  Deploy branch sau đó đã chạy controlled vector-only cutover và API-only gate
  recreation thành công; verifier đều PASS. Không chạy lại regression đã PASS.
- Frontend lint/typecheck/build: PASS; Vitest **68/68 PASS**, 32.32s.
- PostgreSQL lần đầu: **798 PASS, 6 FAIL** do management fixture dùng tên cố định
  trùng dữ liệu test tồn tại từ đợt trước. Sửa fixture tạo owner riêng mỗi test và
  chỉ thu hồi dữ liệu chính test đó tạo. Không sửa oracle, không xóa existing rows.
  Affected suite chạy hai lần liên tiếp **7/7 PASS** trên cùng test DB.
- Full PostgreSQL rerun và Playwright105 bị ngắt bởi Windows reboot lúc10:22.
  Không có final JUnit/result; không tính là PASS. Sau reboot chạy lại tuần tự trên
  existing test DB/candidate, không tạo deployment mới.
  Log PostgreSQL trước reboot có một `F` ở case263
  `test_guest_relationship_worker_ram_scope_and_expiry`; traceback chưa được flush
  nên chưa xác định nguyên nhân, không tự quy thành lỗi timeout hoặc logic.
- Fresh full PostgreSQL sau reboot: **804/804 PASS**, 1065 deselected, **352.97s**,
  gồm case Guest trên, security, owner isolation và provider mock contracts.
  Playwright sau reboot: **105/105 PASS**, **137.44s**, 5 viewports trên existing
  candidate Nginx compiled frontend; mock HTTP không chứng minh provider thật.
- Compose release CPU/GPU validation PASS: existing protected external volume,
  chỉ api/web/db, no build/source bind, provider/Guest gates OFF, fallback OFF.

Đã cố định trước regression **60 offline replay cases**, 6 nhóm ×10: SQL1/2/3 bảng,
RAG, Hybrid, unsupported/owner/security. Sử dụng existing independent PostgreSQL
oracles, Decimal và holdout `maintenance_holdout`; không đưa expected answers vào
planner prompts. Provider plans và query embeddings được script/mock sẵn. Đây là
60 golden/adversarial replay cases, **không phải 60 câu tự nhiên độc lập, không phải
benchmark150, không đo accuracy của provider thật hoặc semantic retrieval thật**.
Final JUnit xác nhận từng nhóm dưới đây. Latency là tổng thời gian test gồm
fixtures/setup/teardown, **không phải API/provider latency**. Không dùng LLM judge.

| Nhóm | PASS/total | p50 test (ms) | p95 test (ms) |
| --- | --- | --- | --- |
| SQL một bảng | 10/10 | 306.0 | 685.0 |
| SQL hai bảng | 10/10 | 321.5 | 443.0 |
| SQL ba bảng | 10/10 | 337.5 | 393.0 |
| RAG | 10/10 | 367.0 | 638.0 |
| Hybrid | 10/10 | 443.5 | 855.0 |
| Unsupported/owner/security | 10/10 | 338.0 | 775.0 |

## Performance và memory

Development BGE đã được unload bằng stop exact API sau khi xác minh leases0 và
không có Guest worker in-flight. NVIDIA báo VRAM0MiB sau stop; không có hai model
resident. Trước stop, Windows Available85MiB, commit87.56%, paging546 reads/s;
sau stop vẫn232MiB/83.19% và paging cao. Người dùng đang giải phóng RAM.

Windows reboot lúc10:22 đã ngắt test; mẫu ngay sau reboot Available202MiB,
commit52.72%, paging3606 reads/s. Không coi giảm commit là đủ RAM để kết luận ổn
định. Không thay driver/WSL, precision, worker count hoặc inference architecture
để né gate.

Sau khi offline hoàn tất, Available có lúc1940MiB rồi giảm753MiB; người dùng đóng
thêm ứng dụng, mẫu kế tiếp899MiB/commit55.73%/paging0.99 reads/s, WSL Available
khoảng6GiB, VRAM0/6144MiB. Smoke bị chặn **ở preflight**, trước khi tạo model process,
bởi local diagnostic guard yêu cầu ít nhất1500MiB Windows Available. Đây là mức
dự phòng bảo thủ cho phép đo, không phải memory limit hoặc yêu cầu cứng của BGE.
Đây là lần preflight trước khi người dùng giải phóng thêm RAM.

Sau đó Windows Available đạt **3315MiB**, commit49.36%, paging23.65 reads/s,
VRAM0. Đã chạy existing `scripts.reranker_smoke --device cuda:0 --repeats2`
trong đúng API candidate image, local model mount read-only, HF/Transformers offline,
credentials rỗng và paid gates OFF. API vẫn một worker không reload, lazy model
chưa nạp; chỉ một diagnostic process đang load BGE, không có model thứ hai.

**Kết quả: guard-stop vì memory pressure, không phải inference PASS.**

- Sau46.91s: Windows Available **408MiB**, paging2285.92 reads/s.
- Sau51.02s: Available436MiB, paging2160.98 reads/s; commit peak62.02%.
- Guard chấm dứt đúng diagnostic PID bằng SIGTERM sau54.05s, exit143 chủ động.
  Peak observed GPU **1687MiB** trong lúc load; sau stop **0MiB**.
- Candidate API vẫn healthy, Docker OOMKilled=false, restart count0→0.
  Không có CUDA OOM trong log; chưa hoàn tất forward/six scenarios nên chưa có
  precision/inference/ranking/concurrency result hoặc latency percentile.
- Artifact hash checks và local weight loading đã đi qua; không suy từ đó rằng
  FP32 inference hoặc serving-worker model lifecycle đã đạt. Worker/restart smoke
  tiếp theo chưa chạy vì memory gate đã chặn.

Chưa có bằng chứng FP32 không tương thích phần cứng. **Operator yêu cầu tạm hoãn
GPU, không tiếp tục yêu cầu giải phóng RAM hoặc lặp benchmark.** Giữ nguyên guard,
FP32/model artifact và kiến trúc; vận hành vector-only đã có. Không tự giảm FP32,
thêm inference server hoặc đổi WSL/driver. Chứng cứ cold-load ở trên được bảo tồn.

## Database, backup và rollback

- Protected main volume `shopquery-ai_postgres_auth_20261019`; archived
  `shopquery-ai_postgres_data` được giữ nguyên. Không migration/reset/re-ingest.
- Fresh baseline full-row logical hashes của **34 public/uploaded tables** và
  schema; backup PostgreSQL17 custom-format `main.dump`, **178232 bytes**,
  SHA256 `42d8c6a181d2844ab2b5db6b4fa98156feef9460e2e641c06d67a198272a8160`.
- Private location: `C:\Users\admin\.codex\backups\shopquery-ai\stage2-20261023T025413Z`;
  ACL chỉ operator và SYSTEM. Không commit dump, raw rows hoặc active env copies.
- `pg_restore --list` PASS; restore vào temporary DB trên existing candidate
  PostgreSQL, 34/34 full-row hashes bằng baseline. Chỉ hai CHECK expressions có
  PostgreSQL deparse khác cách đặt VARCHAR→TEXT cast; đã kiểm7 giá trị/constraint
  (valid/invalid/NULL) cho kết quả giống nhau. Schema/ACL còn lại giống nhau.
  Temporary restored DB đã drop sau khi giữ đầy đủ evidence; không drop volume.
- Trước/sau controlled cutover: **34/34 tables và schema unchanged**. MainDB và
  DevDB giữ IDs/images/mounts. Chỉ API/Web được recreate bằng release digests.
  Sau Google/Guest/live đã có operational writes được duyệt: OIDC/session,
  rate counters, synthetic conversation/messages; phân loại riêng với dữ liệu cũ.
- Sau live: schema và đủ34 table names giữ nguyên; chỉ5 bảng thay hash:
  `chat_conversations`, `chat_messages`, `resource_limits`, `user_sessions`, `users`.
  Dataset/table/document/chunk/uploaded rows không đổi. **86 historical messages
  khớp toàn bộ baseline**; đối chiếu metadata từ private backup xác nhận đủ19
  conversation và2 user cũ, chỉ `updated_at` của1 conversation synthetic và1 user
  operator thay đổi. Không có thay đổi owner/dataset/title hoặc mất lịch sử cũ.
- Baseline rollback API/Web digests tồn tại; private active config copies đã lưu.
  Chỉ rollback application theo [runbook](deployment.md), không restore main DB
  để xóa writes. Release V2 vector-only hiện đã kết nối main trong acceptance window.

## Live scope và ngân sách

Approved mới bởi operator: **6 chats,24 generation stages,8 query embeddings,
0 document embeddings,0 manual retries**, mỗi SDK1 attempt. Chỉ verified synthetic
KPI fixture, Knowledge/Gemini đúng model IDs, fallback OFF, Guest AI OFF.
Used cuối cửa sổ: **5/6 chats,10/24 generation stages,3/8 query embeddings,
0 document embeddings,0 manual retries**; SDK attempts1. Dừng sau provider rejection,
không dùng slot6 để debug hoặc retry. Paid provider gate được tắt lại bằng API-only
recreation; Google/history/tabular upload vẫn chạy, AI requests mới bị chặn.

Presence-only preflight: Google client/secret, invited accounts và provider config
có sẵn; không thử credentials upstream. Existing origin `http://127.0.0.1:8080`,
callback `/api/auth/callback`; không đổi Google Console/client. Model IDs cấu hình:
Knowledge `knowledge`, Gemini `gemini-3.5-flash-lite`, embeddings
`gemini-embedding-2`; fallback OFF, Guest AI OFF. Authenticated provider gate chỉ bật
trong cửa sổ nghiệm thu đã duyệt rồi tắt; không coi configured models là full PASS.

Workspace `Root audit synthetic · 21-10-2026`: full-row comparison3 bảng (5/15/50)
khớp source fixture, original KPI chunk khớp và embedding768D đã persist; owner
khớp fresh Google session. Một policy chunk nên không có rerank-quality claim.
Independent PostgreSQL oracles giữ riêng, không đưa expected results vào prompts.

Browser automation bị Work settings chặn (`Local browser use is disabled`). Operator
đăng nhập/gửi câu hỏi trên UI8080; agent chỉ đọc evidence runtime/DB, không lấy cookie,
token hoặc tạo authenticated session giả. Operator xác nhận login/reload thấy data cũ.
Cuối cửa sổ operator xác nhận reload thấy RAG/citation đã lưu, logout về màn chào và
login lại giữ history/workspace. DB xác nhận session cũ revoked và một fresh active
session đúng owner. Không giả lập account B; A-B live đầy đủ vẫn chưa được chứng minh.

Knowledge SQL probe1: router chọn SQL, hai generation stages đã phản hồi, compiler
từ chối `Invalid nested aggregate`; execution_reached=false, không fallback/retry.
Plan gốc không được log nên không suy đoán chính xác nested shape hoặc tự sửa guard.
Đây là planner/compiler refusal, chưa chứng minh backend SQL execution sai và không
phải bằng chứng provider HTTP outage. Không tính là SQL PASS.

| Probe | Actual model/route | Kết quả | Generation/query embeddings | Request time |
| --- | --- | --- | --- | --- |
| 1 — aggregate/filter | Knowledge/SQL | FAIL `Invalid nested aggregate`, chưa execution | 2/0 | 11.62s |
| 2 — JOIN3 | Knowledge/SQL | FAIL `Row count does not take a value column`, chưa execution | 2/0 | 9.69s |
| 3 — policy RAG | Gemini/RAG | PASS đúng policy, citation/source identity và provider | 2/1 | 3.64s |
| 4 — policy RAG | Knowledge/RAG | PASS đúng policy, citation/source identity và provider | 2/1 | 6.09s |
| 5 — KPI Hybrid | Gemini/HYBRID | Retrieval PASS; QueryPlan generation bị provider từ chối, chưa execution | 2/1 | 2.26s |
| 6 | Không gọi | Chưa dùng; không retry provider | 0/0 | — |

Probe2 được định chạy Gemini nhưng actual persisted metadata/diagnostics là
Knowledge, nên không ghi Gemini SQL FAIL hoặc PASS. UI đổi model đã được xác minh
persist sau đó; thao tác tạo chat mới đưa lựa chọn về default Knowledge theo source.
Probe3/4/5 dùng model đúng qua requested/used attribution, không fallback. Chưa có
browser observation để quy model selection trước probe2 là UI bug hay thao tác.

Gemini Hybrid lỗi `Gemini generation request was rejected; verify API configuration`.
Wrapper không persist upstream body/status chi tiết; chưa đủ chứng cứ kết luận quota,
key hoặc response-schema root cause. Không chuyển lỗi provider này thành SQL/Hybrid
logic failure. Không thay model, prompt, compiler guard hoặc gọi thêm để debug.
Chưa có live SQL rows để chấm với independent oracle; chưa có Hybrid decisions để
chấm accuracy. RAG chỉ1 policy chunk, không chứng minh ranking trên corpus lớn.

## Cleanup và bước tiếp theo

Chưa xóa temporary workspace files, containers, networks, volumes hoặc images.
Chỉ temporary restore DB được thu hồi sau proof theo vòng đời đã duyệt.
Candidate API/Web vẫn stop; production8080 dùng release images ngay trên project
`shopquery-ai`. Giữ toàn bộ volumes, local BGE artifact, rollback images, feature
branch và private evidence. `.env.release` là active vector-only config cần giữ;
`.env.runtime-safe.yaml` là recovery config DevDB, không được release hiện hành dùng.

Tiếp theo: chốt Google/live evidence trong budget, sửa defect chỉ khi đủ bằng chứng,
giữ8080 hoạt động. Không chạy lại offline/gold hoặc BGE benchmark nếu chưa có chỉ đạo
mới. Merge, tag và cleanup chỉ khi mọi gate bắt buộc PASS. Hướng dẫn vận hành,
start/stop/logs/health/version/config/promotion/rollback ở [deployment](deployment.md).

Thay đổi lượt operator này chỉ gồm Compose configuration và canonical docs; đã kiểm
hai trường hợp unset/explicit-empty reranker path bằng effective Compose, thực hiện
deploy/gate recreation và smoke trực tiếp8080. Không đổi application/entrypoint/model,
không rebuild. Không rerun offline/golden hoặc tự kích hoạt full CI cho config/docs
commit (`[skip ci]`); bằng chứng CI application source hiện hành vẫn là run f66feb2
đã dẫn ở trên. Không tuyên bố CI exact HEAD mới PASS hoặc merge-ready từ kết quả cũ.
