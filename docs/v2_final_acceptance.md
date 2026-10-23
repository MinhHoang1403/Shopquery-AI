# ShopQuery AI V2 — nghiệm thu Stage 2

**STAGE 2 PARTIAL — ACCEPTANCE BLOCKED**

Ngày kiểm tra: 2026-10-23, Asia/Saigon. Đây là báo cáo hiện hành; các kết quả
preparation trong handoff không thay thế nghiệm thu live. Không merge, tag,
cutover8080 hoặc cleanup phá hủy khi còn gate bắt buộc chưa đạt.

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
- 8080 vẫn là Web development; API development8001 đã dừng có kiểm soát để
  giải phóng BGE. Vì vậy API phía sau8080 đang unavailable; chưa phải release.
  Main DB15432 và DevDB15433 giữ nguyên container/volume, không recreate.

## Gates và functional acceptance

| Gate | Kết quả hiện tại |
| --- | --- |
| A — preflight/backup/restore | PASS; 34 tables, schema và protected identities được đối chiếu |
| B — offline regression/gold | PASS; backend1049, PostgreSQL804, frontend68, browser105, gold60 |
| C — BGE release/memory | BLOCKED: model load bị guard-stop khi Windows thiếu RAM; chưa hoàn tất inference |
| D — Google thật | PENDING controlled8080 window và thao tác người dùng |
| E — Knowledge/Gemini thật | PENDING ngân sách mới; không dùng quyền các đợt trước |
| F — UI/business live | PENDING; mock không thay thế Google/provider thật |
| G — merge/tag/deploy | BLOCKED bởi các gate trên; PR vẫn draft |
| H — cleanup | DEFERRED theo yêu cầu, chỉ sau stable accepted V2 |

| Chức năng | Offline | Live | Final |
| --- | --- | --- | --- |
| Google Login | OIDC/cookie/CSRF mocks trong backend suite | Chưa chạy | PENDING |
| Auth/history | Backend/PostgreSQL PASS | Chưa chạy | PENDING |
| CSV/XLSX | Backend/PostgreSQL PASS | Chưa chạy | PENDING |
| SQL single table | Backend/PostgreSQL/gold PASS | Chưa chạy | PENDING |
| SQL 2–3 table JOIN | Backend/PostgreSQL/gold PASS | Chưa chạy | PENDING |
| PDF/DOCX/TXT/Markdown, RAG/citations | Parser/contracts/PostgreSQL/gold PASS | Chưa chạy | PENDING |
| BGE GPU release | Load bị guard-stop; chưa có inference result | Chưa chạy | BLOCKED |
| Hybrid | Backend/PostgreSQL/gold PASS | Chưa chạy | PENDING |
| Knowledge | Mock contracts PASS | 0 calls | PENDING |
| Gemini | Mock contracts PASS | 0 calls | PENDING |
| Guest | Backend contracts PASS; AI gates OFF | Chưa chạy | PENDING |
| Security/owner isolation | Backend/PostgreSQL PASS | Chưa chạy | PENDING |
| Persistence | Main unchanged; PostgreSQL PASS | Chưa Google/reload live | PENDING |

## Offline regression và benchmark MVP

- Backend: **1049 PASS**, 820 deselected, 55.29s; HTTP transport thật bị chặn.
- Ruff: PASS. PowerShell parse `dev.ps1`/`release.ps1`: PASS.
- Runtime verifier: 7 cases PASS; actual development positive exit0; actual release
  expectation trên development image/environment exit nonzero đúng như yêu cầu.
  Deploy branch của release script chưa được chạy.
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

Chưa có bằng chứng FP32 không tương thích phần cứng. Biện pháp nhỏ nhất: giữ một
model/worker, đóng thêm workload ngoài ShopQuery để có thêm khoảng2–3GiB Windows
headroom (mục tiêu đo mới khoảng5–6GiB Available trước cold start, không phải cam
kết PASS), rồi mới thực hiện một lần đo mới. Không tự giảm FP32, thêm inference
server hoặc đổi WSL/driver. Không retry để che bằng chứng cold-load bị chặn.

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
- Sau reboot: **34/34 tables và schema unchanged**; mainDB/DevDB/Web container IDs,
  images và mounts giống baseline. Authorized main operational writes: **0**.
- Baseline rollback API/Web digests tồn tại; private active config copies đã lưu.
  Chỉ rollback application theo [runbook](deployment.md), không restore main DB
  để xóa writes. Release candidate chưa kết nối main.

## Live scope và ngân sách

Approved: **chưa có**. Used: chats0, logical generation stages0, query embeddings0,
document embeddings0, manual retries0. Không reuse historic budget.

Presence-only preflight: Google client/secret, invited accounts và provider config
có sẵn; không thử credentials upstream. Existing origin `http://127.0.0.1:8080`,
callback `/api/auth/callback`; không đổi Google Console/client. Model IDs cấu hình:
Knowledge `knowledge`, Gemini `gemini-3.5-flash-lite`, embeddings
`gemini-embedding-2`; fallback OFF, release/Guest AI gates OFF.

Có một persisted document khớp SHA fixture KPI tổng hợp gốc; owner/source IDs giữ
private. Chưa gửi nội dung lên provider. Sau offline/GPU gates mới xin **một lần**
phê duyệt live budget, Google browser steps và thời điểm controlled8080 cutover,
thông báo session/Guest interruption. Không tạo fake authenticated live session.

## Cleanup và bước tiếp theo

Chưa xóa temporary workspace files, containers, networks, volumes hoặc images.
Chỉ temporary restore DB được thu hồi sau proof theo vòng đời đã duyệt.
Development API đã stop để giải phóng GPU; candidate API/Web chỉ chạy trong các
cửa sổ test rồi stop. Giữ toàn bộ volumes, local BGE artifact, rollback images,
feature branch và private evidence. `.env.release` là active config cần giữ.

Tiếp theo: giải phóng thêm host RAM → BGE release inference/lifecycle → xin quyền
live/cutover → Google/SQL/RAG/Hybrid acceptance. Offline suites/gold đã hoàn tất.
Merge, tag, promote và cleanup chỉ khi mọi gate bắt buộc PASS. Hướng dẫn vận hành,
start/stop/logs/health/version/config/promotion/rollback ở [deployment](deployment.md).
