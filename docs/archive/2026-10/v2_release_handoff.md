> HISTORICAL snapshot; current status: [V2 acceptance](../../v2_final_acceptance.md).

# ShopQuery AI V2 — bàn giao chuẩn bị release

**V2 CONSOLIDATION PREPARED — MERGE/DEPLOY PENDING ACCEPTANCE**

Ngày kiểm tra: 2026-10-23, Asia/Saigon. Chưa có Stage 2 acceptance; chưa merge,
tag release hoặc thay runtime 8080. Không gọi generation/embedding provider thật,
không đăng nhập Google thật, không thay credentials hoặc dữ liệu chính.

## Git và một codebase

- Main lịch sử/remote: `0062e47d75cc51646bf9b45409a12aa49288552e`.
- Branch: `codex/shopquery-mvp-v2-stage1`; [draft PR #1](https://github.com/MinhHoang1403/Shopquery-AI/pull/1).
- Stage 1 đã nghiệm thu bounded gates tại `54594d4cafba571bff1677a3c1b90d428465758f`.
- Candidate source commit: `e76dfed2ebcfaebcf37e36485d3041eda68f4209`.
  Commit bàn giao sau đó chỉ sửa documentation; không đổi ứng dụng hoặc candidate.
  Xác minh HEAD bàn giao bằng `git rev-parse HEAD` và head của PR, không suy từ tên tag.

| Thành phần V2 được giữ | Source chính |
| --- | --- |
| Typed QueryPlanner → QueryCompiler → SQLAlchemy Core → guards → bound executor | `backend/app/text_to_sql/`, `backend/app/dependencies.py` |
| SQLGlot, COUNT/JOIN, owner và relationship revision guards | `text_to_sql/validator.py`, `count_contract.py`, `join_policy.py`, `datasets/relationship_repository.py` |
| RAG owner-scoped retrieval, citations và shared BGE | `backend/app/rag/` |
| Hybrid evidence binding, Decimal/metric/source identity | `backend/app/routing/` |
| React dataset/upload/model/SQL/citation UI | `frontend/src/` |
| Google OIDC, CSRF, DB sessions, owner-scoped history | `backend/app/auth/`, `conversations/`, `datasets/` |
| PostgreSQL/pgvector persistence | `backend/app/database/`, protected main volume |

Legacy SQL generator không còn trong application. Không mở rộng SQL/RAG/Hybrid,
đổi models/schema hoặc tạo codebase/service inference thứ hai trong đợt này.

## Candidate và khác biệt môi trường

| | Development đang chạy | Release candidate đã build |
| --- | --- | --- |
| Compose | base + dev + gpu | base + release + release.gpu |
| API | source bind, reload | source trong image, một worker, không reload |
| Web | Vite, banner Development | Nginx, compiled React, không banner Development/DevDB |
| DB | `shopquery_dev` trên DevDB | sandbox `shopquery_test_release_v2`; chưa nối main |
| Cổng | API8001/Web8080 | Kiểm tại API8002/Web8081, DB15434; dừng sandbox sau kiểm tra |
| AI | paid gates tắt | release gates mặc định tắt, test credentials rỗng |
| Model | pinned local read-only snapshot | cùng snapshot, offline, local-files-only, không download |

API: `shopquery-ai-api@sha256:e3989166a219acc914e009e66fb245d3c586b9cd01ce639c0a017324b02e49a7`.

Web: `shopquery-ai-web@sha256:e4a8c96c742bfaf2e6ff834fb320f457dc443ad4df4fedcf797094461e99bfb1`.

Đây là RepoDigests trong local Docker image store, chưa publish registry. Khi deploy
local phải dùng `--pull never --no-build`. OCI revision labels khớp candidate source
commit; 80 Python application modules khớp source. API có Torch `2.14.1+cu130`,
CUDA build13.0 và Sentence Transformers `5.7.0`. Không lấy development image làm
bằng chứng release; candidate được build riêng từ hai Dockerfiles với revision label.

## OAuth, provider và database readiness

Private config có Google client ID/secret, hai invited emails và cấu hình Knowledge/
Gemini; chỉ kiểm tra sự hiện diện, không xuất giá trị hoặc đổi credentials.
Origin/callback hiện hữu: `http://127.0.0.1:8080` và `/api/auth/callback`.
Google Console redirect allowlist/credential validity chưa được kiểm chứng online.
Candidate không có Google credentials; synthetic DB sessions chỉ kiểm thử application
authentication, không chứng minh Google Sign-In. Callback8081 cho account test cần
operator duyệt/configure trước live acceptance. Cookie/CSRF/OIDC tests dùng mocks.

Release gates dùng `RELEASE_PROVIDER_DATA_ENABLED` và `RELEASE_GUEST_AI_ENABLED`,
default false, độc lập legacy `.env` gates đang bật. Chưa gửi prompt/document/query
embedding nào tới provider. CSV/XLSX không cần AI; document ingestion có embedding
và phải tiếp tục bị chặn khi gate tắt. Không coi model configured hoặc health200
là live AI readiness. UI vẫn phân biệt API liveness và provider denial.

Fresh baseline main: 34 public/uploaded tables với full-row logical hashes và schema
fingerprint, lưu private ignored files. Có 2 users, 8 datasets, 14 chunks,
19 conversations, 86 messages; active resource leases bằng0 ở thời điểm chụp.
16 ORM tables có đủ columns/types/required NOT NULL sau chuẩn hóa tên type PostgreSQL;
ORM/setup/migration source không đổi so với stable main. Chưa thấy cần migration.
Nếu schema drift xuất hiện ở cửa sổ triển khai, dừng và lập kế hoạch riêng.

Main container/volume `shopquery-ai_postgres_auth_20261019` và archived
`shopquery-ai_postgres_data` được giữ. Không chạy setup/migration/reset/re-ingest main.
Candidate dùng volume mới `shopquery-ai_release_candidate_v2`, không dùng DevDB/main.
Baseline không thay thế backup/restore rehearsal trước actual deployment.

## Kiểm chứng và giới hạn

| Kiểm chứng | Kết quả và giới hạn |
| --- | --- |
| Candidate image, Compose CPU/GPU merge, provider defaults, revision/source, no reload/bind | PASS; CPU configuration checked, CPU release image chưa build |
| API8002/Nginx8081 và CUDA tensor thật | PASS, RTX3050 Laptop6GiB, CUDA available=true, tensor sum2.0; chưa load BGE |
| SQL production factory trong image candidate → PlanDecision → compiler/guards/executor | PASS COUNT8 bằng independent PostgreSQL oracle; gateway/grounding offline, legacy generator absent |
| PostgreSQL sandbox regression | 803 PASS + 1 connection-timeout khi network sandbox ban đầu chưa expose host ports; case đó rerun riêng PASS sau sửa sandbox |
| Release HTTP thật qua Nginx | PASS DB sessions, CSV/XLSX import, CSRF/Origin negatives, A/B owner isolation, model selection, history và SQL/RAG/Hybrid evidence snapshots; đây là synthetic history, không phải live AI results |
| Gate/OAuth negative checks | PASS models/limits report AI off, chat/document embedding denied403, unconfigured login503, incomplete callback400; không Google network calls |
| Browser trên compiled release frontend | 21 desktop mock tests PASS; actual candidate UI không có Development banner, hiện AI off và không phát chat request khi submit |
| Restart isolated DB/API/Web | PASS, logical fingerprints cả26 tables không đổi; DB sessions/CSV/XLSX/model/history/evidence và A/B negatives tiếp tục PASS sau restart |
| Main data/schema và original runtime integrity | PASS cả34 main tables/schema; existing API/Web/mainDB/DevDB container IDs/images/env/mounts không đổi |
| [CI candidate source e76dfed](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39888244818) | PASS 1042 backend,804 PostgreSQL,68 frontend,105 browser; không live provider |

CI của documentation HEAD bàn giao phải được đối chiếu trong PR/lúc bàn giao;
không dùng source CI để nói rằng một commit mới đã được CI kiểm tra.

**GPU release inference/headroom còn pending.** Development đang giữ model (~2287MiB
VRAM); host chỉ còn khoảng316MiB free physical RAM ở preflight. Không nạp thêm model
resident vào candidate. Stage1 đã chứng minh BGE cuda:0/FP32, CPU/GPU agreement và
~2.32GiB observed VRAM peak; không chuyển chứng cứ đó thành release model/load PASS.
Cần cửa sổ operator duyệt để giải phóng development GPU, chạy candidate BGE smoke,
đo RAM/VRAM/cold start/restart và concurrent requests trên đúng image này.

## Acceptance trước merge/deploy

1. Duyệt Stage2 budget, providers/models, dữ liệu test và consent; live
   Provider → Plan → SQL → Rows, RAG retrieval/citations và Hybrid evidence đúng.
2. Google login thật trên sandbox đã được duyệt: callback/cookies/CSRF, account A/B,
   logout/replay và owner/history isolation. Không tạo identity giả trên main.
3. Candidate GPU model inference, memory headroom và concurrency/cold-start/restart;
   benchmark/holdout theo kế hoạch Stage2, không suy chất lượng từ smoke.
4. Fresh private main backup + restore rehearsal, baseline/config/schema/permissions
   không drift; xác nhận account/dataset/history compatibility và rollback images.
5. Review diff/secrets, exact final CI và PR head; ký acceptance cho merge/tag/deploy.

## Quy trình merge, deploy, rollback — CHƯA CHẠY

Chỉ operator chạy sau acceptance; không chạy các lệnh này để hoàn tất preparation.

1. Fetch; kiểm remote main vẫn bằng baseline và branch/PR head bằng SHA trong biên bản
   được duyệt. Nếu head đổi, review/test lại. `gh pr checks 1 --required` phải PASS
   (nếu chưa cấu hình required checks, kiểm toàn bộ CI, không coi empty list là PASS).
   Review `git diff origin/main...origin/codex/shopquery-mvp-v2-stage1`, secrets và
   xác nhận candidate app/Docker/lock/Compose không đổi từ source SHA nêu trên.
2. Đóng cửa sổ writers/Guest work có kiểm soát, kiểm leases/worker activity; Guest RAM
   mất khi recreate. Chụp baseline/config mới và backup custom bằng pg_dump vào vùng
   private ngoài repo; restore và đối chiếu trước khi chuyển. Không tự migrate main.
3. Giữ SHA đã được duyệt trong `$taskApprovedHead`; chỉ khi user đã duyệt merge:
   `gh pr ready 1`; `gh pr merge 1 --merge --match-head-commit $taskApprovedHead`.
   Fetch và kiểm PR merge commit bằng remote main SHA. Không force/squash/delete branch.
4. Kiểm tag `v2.0.0` chưa tồn tại; tạo annotated tag trên verified main merge SHA,
   push tag sau khi được duyệt release. Ghi source SHA/digests vào release evidence:
   image label giữ approved source SHA, tag trỏ merge SHA; không rebuild ngầm image.
5. Trong PowerShell tại workspace, nạp reviewed private `.env`, đặt `BGE_MODEL_PATH`,
   `POSTGRES_VOLUME_NAME=shopquery-ai_postgres_auth_20261019` và hai image refs ở trên.
   Hai release provider gates giữ false cho tới khi consent/budget cho phép bật.
   Cấu hình local dùng các file, đúng thứ tự:

   ```powershell
   $taskRelease = @('compose', '-p', 'shopquery-ai', '--env-file', '.env',
       '-f', 'compose.yaml', '-f', '.env.compose-ui.yaml', '-f', '.env.join-v1.yaml',
       '-f', 'compose.release.yaml', '-f', 'compose.release.gpu.yaml')
   docker @taskRelease config --quiet
   docker @taskRelease up -d --no-deps --no-build --pull never --wait api
   docker @taskRelease up -d --no-deps --no-build --pull never --wait web
   ```

   Trước up phải kiểm private effective config: chỉ3 services, đúng volume/DB main,
   ports8001/8080 không tranh chấp, image digests/labels, no reload/source bind, đúng
   credentials/origin/callback và explicit provider gates. Không up/recreate `db`.
6. Kiểm API/Web8080 health, actual container image digests/labels/source, main DB mount
   và schema/config drift. Đối chiếu users/datasets/history/all uploaded tables với
   baseline; phân loại riêng session/login/quota/history writes hợp lệ. Chạy account
   và live business acceptance đã được duyệt. Lưu evidence private, không log tokens.
   Chỉ khi tất cả PASS mới công bố deployed V2. Giữ feature branch và baseline images.
7. Sau khi không còn dev/test work, dừng `devdb` bằng exact service, giữ volume;
   dừng sandbox candidate để không có product deployment thứ hai.

Rollback application nếu acceptance sau chuyển thất bại: không khôi phục/drop DB
để xóa operational writes. Dùng cùng base + local overrides + release, bỏ GPU
overlay; set API digest
`shopquery-ai-api@sha256:e48449814155713a9724dd1d816ec58baebd81738640cba2fe79d820b3b38132`,
Web digest
`shopquery-ai-web@sha256:5ca6e17125f12574cf8cdf4d030b6a0a209007e9469b264e94e6d98056090146`.
Hai baseline images đã có trong local store. Chỉ up API/Web `--no-deps --no-build
--pull never --wait`, cùng main volume/origin và reviewed original environment;
verify image IDs, auth/history và baseline lần nữa. Model mount không khiến baseline
CPU image có reranker; rollback khôi phục baseline capability, không chứng nhận V2.
Nếu có DB drift/incompatibility ngoài operational writes, dừng riêng để điều tra;
không tự restore backup hoặc downgrade schema.

Các quyền còn cần: Stage2 live budget/consent, Google test flow/callback, cửa sổ GPU
và maintenance, ký acceptance, sau đó merge/tag/deploy. Không cần quyền thêm để lưu
preparation này. Technical sources: [Docker GPU](https://docs.docker.com/compose/how-tos/gpu-support/),
[Compose merge](https://docs.docker.com/reference/compose-file/merge/),
[Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect).
