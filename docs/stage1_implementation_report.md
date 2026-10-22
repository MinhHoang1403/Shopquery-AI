# MVP V2 — Stage 1 implementation report

**STAGE 1 PARTIAL — BLOCKED**

Ngày thực hiện: 22–23/10/2026, Asia/Saigon. Không chuyển sang Giai đoạn 2.
Continuation từ `946ff82`: production SQL đã chuyển sang QueryPlanner/QueryCompiler
cho default/authenticated/Guest/Hybrid; generator SQL tự do đã được gỡ.
CUDA model/serving/reload đã được kiểm chứng; đang chờ exact final pushed CI.
Các checkpoints 22–23/10 phía dưới là lịch sử, không chứng nhận source mới.

## A. Source/runtime baseline

- Đọc AGENTS.md trước mọi chỉnh sửa; giữ nguyên nội dung instructions.
- Baseline local/remote main: `0062e47d75cc51646bf9b45409a12aa49288552e`.
- Feature branch: `codex/shopquery-mvp-v2-stage1`; main không được merge/force-push.
- Trước khi làm: chỉ có untracked `docs/hybrid_live_acceptance_20261022.md`.
  Tệp này được giữ nguyên ngoài commits, SHA256 `0a13a5e7c41b0c2003cedc1c7475da8a7f726b1580b1da930b0900c01161e283`.
- Backend/infrastructure checkpoint: `cf5ca602e3ff485d2b710fced92860f6d4264b21`. Frontend development notice/runtime verification được hoàn thiện tại `8d9d83885b3d46a730503459a88946d35a1166d6`; regression fixtures/test runner tại3915485.
  Các commit tài liệu tiếp theo không thay source runtime; final metadata SHA đọc từ Git log.
- Baseline smoke: 135 PASS. Historical counts 974/778/68/105 chỉ là tham chiếu.
- Baseline Compose project `shopquery-ai`, exact order `compose.yaml`,
  `.env.compose-ui.yaml`, `.env.join-v1.yaml`; API8001/web8080/DB15432.
- Baseline API `75086624f3f2`, image `sha256:e48449814155713a9724dd1d816ec58baebd81738640cba2fe79d820b3b38132`;
  web `2af67d527f2e`, image `sha256:5ca6e17125f12574cf8cdf4d030b6a0a209007e9469b264e94e6d98056090146`.
  Cả hai được giữ bằng baseline image tags, không overwrite image contents.
- Main DB container `511c4f5aaccc`, active volume `shopquery-ai_postgres_auth_20261019`,
  archived volume `shopquery-ai_postgres_data`, không recreate/reset/migrate/re-ingest.
- Main baseline: 2 users, 1 unexpired login session, 8 datasets, 14 chunks, 19 conversations;
  active resource leases=0 và không có spawned Guest worker trước switch.
  Idle GuestStore của process cũ không thể enumerate qua một docker exec mới;
  Guest RAM theo thiết kế không sống qua API recreate. Không coi worker count là session count.
- Main read-only fingerprints cho users/datasets/chunks/conversations/messages không đổi
  sau switch và các tests. Đây là kiểm năm nhóm dữ liệu, không phải bytewise full DB proof.
- Drift baseline chỉ ở tên biến `GEMINI_API_KEY` giữa merged host config và API cũ;
  không in/lưu giá trị key, không thử key với provider. Dev cố ý không nhận key/gates.
- Other projects/containers, archived volumes và private backups không bị sửa.

## B. Architecture and scope

Giữ modular monolith, Google auth/CSRF/owner isolation, Guest workers/TTL/quota,
PostgreSQL + pgvector, SQLAlchemy/Psycopg, SQLGlot, React/Vite và provider/model contracts.
Canonical [architecture](architecture.md), [capabilities](capabilities.md),
[security](security.md) thay các snapshot cũ làm hướng dẫn chính.

Production SQL có một path: authorized catalog → PlanDecision → QueryCompiler →
SQLGlot/JOIN/COUNT → guarded reader execution với parameters. Không có legacy fallback.
Không xây authentication/frontend/database mới.

## C. Text-to-SQL

### Continuation baseline and capability matrix (23/10/2026)

Continuation starts at clean `946ff82b28d84b88c2dcebb522e0af5242ba546f`.
API `264ba70159c3`, web `07893ff84717`, protected main DB `511c4f5aaccc`
and DevDB `337bd37c8ef8` were healthy; development source hashes matched.
Compose project inventory reports base, dev, UI override; service verification
against base+dev reports no API/web environment drift. Main/archived volumes remain protected.

This matrix was recorded before extending the plan implementation. A validator
acceptance test proves syntax coverage only; new compilation requires PostgreSQL oracles.

| Capability | Existing evidence | Verified scope / migration requirement |
| --- | --- | --- |
| Projection, comparisons, NULL, IN, sort/limit | compiler tests; SQL correctness, alias and import integration | One authorized table; exact typed values and output labels |
| SUM/AVG/MIN/MAX, Decimal and NULL | SQL correctness integration | Single table; preserve zero versus NULL and lossless decimals |
| COUNT rows/non-NULL values | count conformance and key/order PostgreSQL suites | Preserve direct metric provenance, aliases and verified INNER-key proof |
| Arithmetic on multiple columns | generator prompt; default revenue validator tests and database revenue oracle | Bounded numeric expressions; no invented formulas |
| Aggregate division | domain integration uses SUM(price)/COUNT(price) as independent AVG oracle | Legacy production emits AVG, not division. Raw wrapped COUNT is rejected by current count contract; equivalent typed average must preserve NULL/zero semantics |
| quantity × unit_price | default validator cases and database revenue oracle | Default store fact expression; uploaded JOIN aggregate expressions remain explicitly unsupported |
| AND/OR, HAVING | SQL validator permits operators and ordinary SUM HAVING; no dedicated semantic oracle | Add bounded typed boolean/HAVING oracle; COUNT HAVING stays unsupported |
| Date/time boundaries | timezone and correctness PostgreSQL suites | DATE/TIMESTAMP/TIMESTAMPTZ, explicit offsets, half-open local ranges |
| Date grouping/formatting | validator function allowlist, no dedicated grouping oracle | Bound day/month/year operations and add timezone/year-boundary oracles |
| Two/three table chain/star | join golden/order/tree PostgreSQL suites | Verified N:1 keys, fact root, dimension grouping identity, revision guard |
| JOIN aggregate arithmetic/MIN/MAX/dimension measures | join order/tree negative tests | Unsupported intentionally; retain these security assertions |
| Default four-table revenue/category joins | default validator cases | Backend-declared default FK tree only; never extend uploaded three-table scope |
| Hybrid metric/filter/source binding | gate D, original prose, count/policy integration | Preserve literal evidence SQL separately from parameterized execution |
| Structured provider plan and factories | absent at baseline | Must exercise real mocked Knowledge/Gemini serializers and all factories before removing legacy |

SQLAlchemy bound operators and Pydantic validation are based on official references:
[SQLAlchemy operators](https://docs.sqlalchemy.org/en/20/core/operators.html),
[Pydantic models](https://docs.pydantic.dev/latest/concepts/models/).

- `QueryPlan`: backend-issued source/column/relation IDs, selected fields/metrics,
  aggregate kinds, AND filters, grouping, sort/null ordering, row limit.
- `SchemaReferences`: deterministic IDs từ chính authorized DatasetSqlContext;
  không nhận raw SQL identifiers, JOIN ON expressions hoặc provider-generated paths.
- SQLAlchemy Core compile; exact ON/root từ approved graph; reject unknown IDs,
  duplicate relations/aliases và columns ngoài selected graph. Existing validator vẫn
  là authority cho grain, approved edges, dimension group keys và COUNT semantics.
- Filter values được parse theo registered types, Decimal giữ exact digits,
  date/timestamps giữ offset; bind database parameters. SQLGlot kiểm cả literal preview
  và bound statement, provenance phải khớp, reject AST cần normalization không chứng minh.
- Executor thêm optional parameters vào cùng reader/read-only/timeout/rollback path.
- Targeted unit: 14 PASS (compiler/executor tại checkpoint ban đầu); PostgreSQL:
  6 PASS với independent VALUES oracle, một/hai/ba bảng và half-open timestamp filters.
  Integration phát hiện `:parameter::TIMESTAMP` không được SQLAlchemy text bind nhận;
  đã sửa bằng dialect BindTyping.NONE và chạy lại toàn bộ sáu cases PASS.
- Continuation: bounded expression DAG (80 nodes/depth8), +/−/×/÷, aggregate
  expressions một bảng, AND/OR, SUM HAVING, day/month/year và date/month labels.
  SUM(x)/COUNT(x) compile thành AVG(x); PostgreSQL oracle giữ empty/all-NULL/zero.
  Mẫu số động zero trả NULL bằng NULLIF; literal zero bị từ chối. Type/group checks
  chạy trước SQL. Uploaded JOIN aggregate restrictions không đổi.
- Hardening `cde9151` preserves COUNT(nullable BOOLEAN), including false values;
  WHERE rejects formatted/bucketed timestamp comparisons and requires unchanged source
  columns for temporal ranges. `b661c19` bounds expanded DAG size512/expression to prevent
  repeated references from expanding SQL exponentially. Related security/PG oracles PASS.
- Default catalog lấy từ đúng bốn SQLAlchemy models và declared FKs. Default revenue
  bốn bảng qua actual Knowledge mock → Plan → SQL → PostgreSQL khớp independent
  seed oracle tổng `151687001000`. Không đưa công thức commerce vào uploaded compiler.
- Knowledge/Gemini serializers đi qua HTTP mock với PlanDecision; valid/invalid JSON,
  missing/extra fields, unsupported output, unknown IDs, bad operators/depth và schema
  rejection đều được kiểm. Actual-adapter factory integration gồm authenticated và Guest.
- Schema prompting dùng toàn bộ authorized catalog IDs/types/headers/observed values/
  approved relationships; không heuristic pruning làm mất field/path. Một logical plan
  generation thay một logical SQL generation. Existing adapter retry policies giữ nguyên.
  SQL vẫn route/plan/answer; Hybrid retrieval → route/plan/final decision không thêm repair call.
- Pipeline execute chỉ bound SQL; safe rendered/validated evidence SQL giữ public API
  và Hybrid filter/metric binding. Count provenance từ AST và approved keys/revisions.
  Guard chạy trước executor; COUNT aliases không biến SUM/AVG thành row evidence.
- `generator.py` đã gỡ. Fixed hostile SQL tests dùng test-only validation harness;
  static oracle SQL có helper chuyển sang mocked PlanDecision, không import từ app.
  Các tests đó không được tính thay actual serializer/factory proof ở trên.
- COUNT/alias/JOIN validator hiện hữu được giữ nguyên; không domain-hardcode trong compiler.

Nguồn semantic: [PostgreSQL aggregates](https://www.postgresql.org/docs/17/functions-aggregate.html),
[NULLIF](https://www.postgresql.org/docs/17/functions-conditional.html).

| Path | Changed/Removed | Why safe | Test evidence |
| --- | --- | --- | --- |
| `backend/app/text_to_sql/generator.py` | Removed | All production factories use typed planner/compiler; no fallback | Real mocked adapters + PostgreSQL factory tests |
| `backend/app/text_to_sql/planner.py`, `expressions.py`, `compiler.py` | Added/extended | Catalog IDs, bounded operators and bind values; existing guards remain | Type/security, arithmetic/calendar/COUNT/JOIN oracles |
| `backend/app/dependencies.py`, `guest/pipeline.py`, `text_to_sql/pipeline.py` | Migrated | Same reader/timeout/guard/grounding stages and public rows | Auth/Guest/Hybrid/history regressions |
| `backend/tests/plan_fixtures.py`, `sql_validation_fixtures.py` | Test-only adapters | Preserve static oracle rows and adversarial SQL assertions; never imported by app | Existing security and independent domain suites |

Continuation SQL checkpoint: Ruff PASS, backend unit **1037 PASS**, isolated PostgreSQL
**803 PASS** (one complete sequential run, 325.03s), frontend unit **68 PASS**.
16 live cases excluded; no provider/embedding call or Stage2 benchmark.
Runtime still healthy with the original development API/web containers; **80 app modules**
and31 frontend sources match bind mounts, no environment drift, DevDB identity unchanged.
API source manifest: `db6cf69e7a095de94a8b1fe406eb29846602de85404b32f38e23723dd0794a5e`.

Docker GPU preflight succeeded using the existing development image with `--network none`,
one GPU, no extra host mounts: RTX3050 6GB, driver617.42, compute8.6. This is visibility
proof only; CUDA-enabled Torch/model inference remains a separate gate below.

## D. RAG/local BGE

- Tìm đúng HF cache chuẩn, không quét toàn ổ đĩa hoặc đọc dữ liệu project khác.
- Artifact: `C:/Users/admin/.cache/huggingface/hub/models--BAAI--bge-reranker-v2-m3/snapshots/953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`.
- Identity: BAAI/bge-reranker-v2-m3, pinned revision trên, Apache-2.0 trong local model card
  và [official model card](https://huggingface.co/BAAI/bge-reranker-v2-m3).
  Config có inherited base `_name_or_path=BAAI/bge-m3`; sequence-classification
  architecture + pinned weight hash xác minh reranker artifact, không chỉ tin tên config.
- Weights 2,271,071,852 bytes, SHA256
  `d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286`.
  Tokenizer JSON SHA256 `69564b696052886ed0ac63fa393e928384e0f8caada38c1f4864a9bfbf379c15`.
  Runtime kiểm hai hashes trước load; không tải/move/overwrite model.
- Host Ryzen 5 7535HS, RAM khoảng15.31 GiB, RTX3050 6GiB, driver617.42/CUDA13.4;
  WSL2 có Docker Desktop running, Ubuntu stopped. Docker memory khoảng7.41GiB.
  Checkpoint946ff82 chọn CPU; CUDA continuation được ghi ngay dưới đây.
- Sentence Transformers5.7.0/PyTorch2.14.1+cpu khóa trong optional extra/uv.lock.
  Offline local CrossEncoder, remote code=false, max_length512, batch2, K12/N3.
- Shared instance per process/config, load/predict serialized; bounded scores và sanitized
  diagnostics. Failure dùng original vector order, không retry/load mỗi chat;
  cần process restart sau khi sửa model/device. N chỉ chọn original immutable chunk objects.
- Auth/default RAG tích hợp rerank sau scoped retrieval, trước composition. Guest
  giữ vector retrieval vì disposable worker768MiB; không nới isolation để chứa weights2.27GB.
- Native CPU load/scoring PASS; API container CPU load/scoring/reused instance PASS,
  relevant synthetic chunk đứng trước distractor. Đây là docker-exec smoke, không live chat.
- Model mount read-only `/models/bge`; không weights trong image/Git; không re-embed main.
- Chưa khẳng định tăng accuracy; Recall/MRR/nDCG/latency là Giai đoạn 2.

### CUDA continuation — 23/10/2026

- Official Torch `2.14.1+cu130`, CUDA build13.0, Sentence Transformers5.7.0,
  Transformers5.20.2; Python3.11.9, glibc2.36, Linux x86_64. Driver617.42 supports
  CUDA13.x; actual Torch reports available=true, device_count=1, RTX3050/compute8.6,
  and compiled arch list includes sm_86. A CUDA tensor sum returned4.0 inside Docker.
- Separate optional `reranker-cuda` and `compose.gpu.yaml` only affect API development.
  All113 previously locked package/version pairs remain;20 CUDA dependency variants added.
  Default export contains no CUDA/Torch; CPU extra still uses2.14.1+cpu. No global host
  Python/CUDA/driver/WSL/Docker setting changed. NVIDIA runtime packages live in the image.
- Official wheel SHA256: `9023b6a538714e370fe9e027fc20c5c600bbe3759b79d9a1a6f07e73c40db8d0`.
  Model identity/revision/two hashes above were checked by the real loader on each smoke;
  model mount read-only, trust_remote_code=false/local_files_only=true, network disabled.
  No model download, provider generation or embedding calls.
- CPU/GPU comparison used the **same CUDA wheel**, same local weights and three synthetic
  bilingual query sets, K12/N3, batch2, max_length512. Short and padded512-token inputs,
  two repetitions per scenario; two-CPU quota and6GiB RAM limit per temporary diagnostic
  container. These are tiny empirical p50/p95 (p95 is the maximum of two samples), not
  production latency estimates or a retrieval-quality benchmark.

| Case/input | CPU p50/p95 ms | GPU p50/p95 ms |
| --- | --- | --- |
| Delivery/short | 2806.56 /2940.69 | 172.67 /190.97 |
| Warranty/short | 2443.11 /2535.36 | 175.13 /192.87 |
| Tuition/short | 2438.73 /2503.88 | 165.34 /172.85 |
| Delivery/512 | 26811.00 /28503.36 | 1499.99 /1513.22 |
| Warranty/512 | 25402.07 /25625.53 | 1902.57 /1935.77 |
| Tuition/512 | 24720.72 /25034.27 | 2169.24 /2213.41 |

- Both ran **torch.float32**, no FP16/AMP/quantization/torch.compile changes. All six
  top-3 orders matched exactly; positive chunk ranked first throughout; maximum score
  difference `4.172325134277344e-7`, all scores finite, original object identities retained.
- Observer recorded72 CPU and84 CUDA forward calls, actual input device cpu/cuda:0,
  max batch2/max token512. CUDA event spans were positive. Two concurrent CUDA rerank
  requests used the same model, max_active_predict=1; singleton cache identity remained true.
- Peak Torch allocated **2218.10 MiB**, reserved **2254 MiB**; NVIDIA sampler observed
  **2373 MiB**, utilization100%. Process peak RSS: CPU2491.53 MiB, GPU2788.92 MiB.
  Process load/hash/first-inference timers after Torch import: CPU62.88s, GPU84.43s.
  No CUDA inference error/OOM. Initial CPU instrumentation trial failed because library5.7
  invokes a bound forward method directly and bypasses PyTorch hooks; observer was corrected
  in the diagnostic only, and that incomplete trial is excluded from PASS/timing results.
- Host15.31GiB/Docker7.415GiB remained unchanged. The initial WMI sampler reported a zero
  minimum (not treated as a reliable whole-host peak); after diagnostic exit Available
  Memory was600MiB. Valid Available Memory counters later reached284MiB on API cold start
  and166MiB on reload. This is limited
  headroom, not evidence for production concurrency/load safety; no host limit was raised.
  Diagnostics ended and released GPU memory to0 before the serving worker was started.
- Missing CUDA/OOM unit cases preserve original sources/vector fallback, attempt once and
  log only safe device/failure categories. Guest remains vector-only in its768MiB worker.

Sources: [official Torch release](https://github.com/pytorch/pytorch/releases/tag/v2.14.1),
[official CUDA wheel index](https://download.pytorch.org/whl/cu130/torch/),
[NVIDIA driver compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html),
[Docker GPU reservations](https://docs.docker.com/compose/how-tos/gpu-support/),
[CrossEncoder API](https://www.sbert.net/docs/package_reference/cross_encoder/model.html).

### GPU serving runtime and reload

- Applied only API with `compose.yaml`, `compose.dev.yaml`, `compose.gpu.yaml`,
  `up -d --no-deps --wait api`. Before restart DevDB had0 active leases; the three API
  processes were exactly Uvicorn reloader, resource tracker and serving worker. Guest RAM
  is not durable across restart; no claim to enumerate another process's idle RAM sessions.
  No DB setup/migration/seed/ingestion command was run for this GPU switch.
- API container `ea8f89d55fb836f28537c658049be22077ab4747e202c514bcea57fa9b821a1c`;
  image `sha256:4b56f80c57f6cb4ebf46a6bdd140927863308ca254a7b7697cbf77c8370155e5`.
  Driver nvidia/count1/capabilities gpu; no GPU given to DB/web, no privileged/socket/root mounts.
- In the actual Uvicorn serving worker, warmup logged pid8, cuda:0, torch.float32,
  shared=True, selected synthetic chunk1; allocated2174.1/reserved2184.0MiB.
  Initial warmup109.36s. API stayed on DevDB with paid gates OFF/credentials empty.
- Touching only planner.py mtime triggered one hot reload without content/hash changes.
  New worker pid244 logged the same cuda:0/dtype/shared/model memory and successful inference;
  warmup105.01s, recovery about119s. NVIDIA memory dropped to0 between workers and returned
  to2287MiB (also observed peak2287), without accumulation/two resident model copies.
  Both API8001 and proxy8080 `/api/health` returned200 after reload. This development pause
  and cold-load RAM headroom are documented limits, not production readiness claims.
- Runtime verification: 80 app modules and31 frontend source files match; env drift lists
  empty, CUDA available/device_count1. App manifest
  `cbc5e37a8e33eeaec658b98226a92067e36f732037fc14b3a992fef4172bba10`;
  GPU entrypoint hash `3562269fc4a1a9b4be329d0a16f77e88314b8d025b21dc1ba64c1fbb0cac5c55`.
- Web remains `07893ff84717`, main DB `511c4f5aaccc` on protected
  `shopquery-ai_postgres_auth_20261019`, DevDB `337bd37c8ef8` on
  `shopquery-ai_postgres_dev_stage1`; archived `shopquery-ai_postgres_data` untouched.
- Final read-only checks confirm the five main logical fingerprints unchanged
  (users/datasets/chunks/conversations/messages). DevDB still has0 users/datasets/chunks/
  conversations. This is logical table proof, not bytewise proof of every DB/volume file.

| GPU path | Change | Why bounded | Evidence |
| --- | --- | --- | --- |
| `backend/pyproject.toml`, `uv.lock`, `Dockerfile` | Separate CUDA extra/build argument | Existing113 versions retained; default/CPU independent | Frozen image build, export checks, real CUDA tensor/model |
| `compose.gpu.yaml`, `scripts/dev.ps1`, `verify-runtime.ps1` | Explicit GPU development override | API only, one GPU, same DevDB/model mounts | Container config/source/CUDA verification |
| `backend/scripts/gpu_api.py` | Warm same app/shared model in serving worker | Two synthetic chunks, no new endpoint/provider | pid8→pid244 reload, stable VRAM, health200 |
| `backend/scripts/reranker_smoke.py` | Bounded diagnostic CLI | Three synthetic queries, K12/N3, batch2/512, network none | CPU/CUDA forward, scores, identity, concurrency and resources |
| `backend/app/rag/reranker.py` | Device check/safe failure categories | Same retrieval/ranking/fallback; no retries or CPU model duplication | CUDA-unavailable/OOM units and actual model smoke |

## E. Hybrid

Retrieval/rerank → parse candidate policy requirements → bounded untrusted planning
context → SQL → source/metric/identity verification → one authoritative decision set.
Candidate policy trước SQL chưa có quyền verified; binding vẫn kiểm source hash,
single-chunk completeness, workspace/owner và registry sau execution.

Bỏ lượt free-form SQL answer generation bị composer bỏ đi. SQL-only vẫn độc lập
RAG; RAG-only không SQL. Missing/malformed evidence dừng trước SQL; unsupported SQL
dừng trước execution/answer. Không repair loop hoặc thêm model calls để chọn metrics.

Giữ closed numeric policy scope, Decimal, entity coverage, citations và summary/detail
consistency. Multiple/ambiguous/exception policies không tự mở rộng thành rules engine.
260 targeted tests PASS sau refactor; PostgreSQL selected suites đã được chỉnh assertions
về thứ tự/call count mới, không bỏ assertions về unsafe SQL/rows/identity/verdict.

## F. Cleanup manifest

| Path | Action | Reason | Replacement/History | Verification |
| --- | --- | --- | --- | --- |
| `AGENTS.md` | KEEP | Repository instructions | Original bytes preserved | Git diff empty |
| `README.md` | REWRITE | Dated runtime/acceptance snapshots conflicted | Canonical docs + baseline Git | Local link check |
| `handoff.md` | REWRITE | Multiple contradictory latest states | Current report pointer; full old text in baseline Git | Link/reference review |
| `docs/authentication.md` | KEEP | Required migration/security interface | Link updates to archived evidence | Source/repository auth tests |
| `docs/technical_references.md` | REWRITE | Old references claimed auth/JOIN absent | Current primary sources | Source/API documentation review |
| `routing/hybrid.py`, `text_to_sql/pipeline.py` | REWRITE | SQL-before-policy, discarded SQL narrative | Evidence-first flow, optional grounding | Sequence + decision/SQL tests |
| `ai/gemini.py`, `ai/inetcloud.py` | REFACTOR | Duplicate transient status values | `core/errors.py` shared authoritative tuple | Existing adapter status/error tests |
| Production route/worker/CLI functions with no direct callers | KEEP | Decorator/startup/subprocess registration | Existing registrations | AST + main include_router + worker targets checked |
| Direct existing dependencies | KEEP | All have source/CLI/runtime responsibilities | pyproject/uv.lock | Import graph + Ruff; no evidence justifying removal |
| `docs/hybrid_live_acceptance_20261022.md` | KEEP untracked | User evidence newer than historical handoff | Original file outside commits | SHA256 recorded above |
| `docs/dataset_deletion.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/dataset_deletion.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/evaluation_report.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/evaluation_report.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/final_audit_report.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/final_audit_report.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/guest_mode.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/guest_mode.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/hybrid_answer_consistency_root_cause_fix.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/hybrid_answer_consistency_root_cause_fix.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/hybrid_natural_policy_final_delivery.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/hybrid_natural_policy_final_delivery.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/join_v1_final_acceptance.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/join_v1_final_acceptance.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/main_auth_upgrade.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/main_auth_upgrade.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/multi_model_integration.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/multi_model_integration.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/multidomain_evaluation.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/multidomain_evaluation.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/regression_stabilization.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/regression_stabilization.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/sql_correctness_hardening.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/sql_correctness_hardening.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/sql_join_reliability_acceptance.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/sql_join_reliability_acceptance.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/sql_join_root_cause_audit.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/sql_join_root_cause_audit.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/system_reliability_audit.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/system_reliability_audit.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/text_to_sql_batch_a_live_and_generalization.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/text_to_sql_batch_a_live_and_generalization.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/text_to_sql_batch_b_hybrid_live_acceptance.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/text_to_sql_batch_b_hybrid_live_acceptance.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/text_to_sql_count_deployment_git_delivery.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/text_to_sql_count_deployment_git_delivery.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/text_to_sql_count_semantic_contract_redesign.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/text_to_sql_count_semantic_contract_redesign.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/text_to_sql_hybrid_count_root_cause_fix.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/text_to_sql_hybrid_count_root_cause_fix.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/text_to_sql_reliability_investigation.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/text_to_sql_reliability_investigation.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/text_to_sql_semantic_count_hybrid_live_final_acceptance.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/text_to_sql_semantic_count_hybrid_live_final_acceptance.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |
| `docs/text_to_sql_verification_and_acceptance.md` | MOVE | Dated historical evidence | `docs/archive/2026-10/text_to_sql_verification_and_acceptance.md` | Full content preserved except historical banner/link repair; canonical extraction + link scan |

No production module was deleted merely for low static reference count. No dependencies
were removed without proof. Deleted current-working-tree content is limited to superseded
README/handoff snapshots; their full originals remain in Git. Twenty-three reports moved
by an explicit reviewed path list, not a deletion filename glob. No private backups removed.

## G. Docker/dev verification

Effective dev: `compose.yaml` → `compose.dev.yaml`, project shopquery-ai. API/web use
read-only source bind mounts, Uvicorn reload/Vite HMR (polling on Windows). New devdb
contains shopquery_dev and isolated shopquery_test_stage1; main db service remains untouched.
Paid credentials/gates/fallback disabled; dev UI clearly labels the database as development.
Release override removes build definitions and requires reviewed image refs/existing external
volume. Release config sanity PASS; no release deployment performed.

Python proof: temporarily changed health service label, observed `ShopQuery AI reload-probe`
through8080, restored original bytes/label. API and main DB container IDs unchanged during
probe. Frontend proof: temporarily changed development banner, observed browser HMR, restored
original. Browser loaded Guest UI with zero page errors. No probe remains in source/data.
Dependency changes rebuilt web; environment changes require controlled recreate, not reload.

Current runtime snapshot (source bind hashes match all79 Python modules and31 frontend source files; API/web env drift names empty):

| Service | Container | Image | Health |
| --- | --- | --- | --- |
| api | `264ba70159c3` | `sha256:63719ee2ce736651128beb64fd24b7d17b431b017eead0db19df1a02b082c4ed` | healthy |
| web | `07893ff84717` | `sha256:2a46891e5488e91df8b84e93ba7e8b7093c507b34aa1e077a7662ec078faf44d` | healthy |
| db | `511c4f5aaccc` | `sha256:137f044b0efe3d57f39b972b9b53641b1f2045b99d879e298bbf514a25787dcf` | healthy |
| devdb | `337bd37c8ef8` | `sha256:137f044b0efe3d57f39b972b9b53641b1f2045b99d879e298bbf514a25787dcf` | healthy |

Main/archived volumes remain present; dev volume is shopquery-ai_postgres_dev_stage1.
Source/config verification: `scripts/verify-runtime.ps1`; no resolved secrets printed.

## H. Tests/GitHub

| Check | Result/evidence |
| --- | --- |
| Initial SQL/Hybrid/RAG smoke | 135 PASS |
| Backend unit broad smoke | 998 PASS on CI3915485; local997 + targeted follow-up67 PASS |
| Compiler bound PostgreSQL | 6 PASS locally; included in CI784 PASS on isolated DB |
| PostgreSQL regression | 784 PASS on CI3915485, no live tests |
| Hybrid evidence/original prose selected integration | 125 PASS in intermediate run; remaining51 PASS after call-order assertion updates;49 PASS sequential affected negative/API/Guest cases after final fixture alignment |
| Frontend unit | 68 PASS |
| Frontend lint/typecheck/build | PASS; Node types added for typed Vite proxy hook |
| UI mock five viewports | 105 PASS |
| Compose dev/release config | PASS |
| API/web health, Python reload, React HMR | PASS |
| Native and container BGE CPU smoke | PASS, synthetic text, no providers |
| Main protected fingerprints | Unchanged for five groups named above |
| Provider live / embeddings / re-ingestion | NOT RUN: budget zero |
| Full final benchmark / Stage 2 acceptance | NOT RUN |

Commits pushed after scoped tests:

- `6e98a97`: offline bounded reranking.
- `d03b213`: evidence-first Hybrid.
- `1260914`: typed compiler and bound execution.
- `ac3d1e0`: offline HTTP boundary, model hashes, independent PostgreSQL compiler proof,
  transient-status consolidation and affected regression assertions.
- `cf5ca60`: isolated Docker development, source sync and runtime/test scripts.
- `3915485`: complete affected Hybrid call-order fixtures, sequential test DB mutex.
- `8d9d838`: frontend source hash verification and mobile development banner fit (320px viewport/page width both320).

Draft PR: [#1](https://github.com/MinhHoang1403/Shopquery-AI/pull/1).
CI run at infrastructure checkpoint:
[39817362150](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39817362150).
Run39817362150 phát hiện25 assertions/fixtures integration còn giả định SQL-before-retrieval; đã sửa expectations và synthetic embedding. Một lần chạy local chồng test DB gây deadlock, kết quả đó không dùng làm PASS; test.ps1 đã thêm named mutex và chạy lại tuần tự. Final CI/remote verification được ghi ở phần delivery cuối.

New run [39818625553](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39818625553) at3915485 completed SUCCESS for all three jobs: Backend quality998, PostgreSQL integration784 and Frontend quality.
No merge/force push; no secrets/env/weights/log/private evidence in commits.

## I. Remaining mandatory work and Stage 2 boundary

1. QueryPlan và CUDA image/inference/resource/reload gates đã PASS offline/local;
   exact final GPU commit CI còn chờ trước khi kết luận hoàn tất.
2. Guest giữ vector-only theo phạm vi được chấp nhận; không load BGE vào worker768 MiB.
3. Final Stage 2 comprehensive regression, independent holdout/150-question benchmark,
   retrieval quality/latency, live Knowledge/Gemini and final release remain unperformed.
   Historical user report says KH PASS/GH FAIL on the old runtime; no new live verdict.

**Không đủ điều kiện ghi STAGE 1 COMPLETED — READY FOR STAGE 2.**

## Historical inventory evidence at 946ff82 (superseded by continuation above)

AST inventory covers every app Python module, local import adjacency, entrypoint scripts
and HTTP decorator registrations. Zero direct callers are not treated as dead code. Main
startup includes API/auth/relationship/Guest routers; Guest subprocess targets and CLI
`__main__` entrypoints are retained. New compiler is test-only preparation, explicitly DEFER
for production activation; there is no second live query engine.

### Production/source modules

| Path | Classification | Local app dependencies |
| --- | --- | --- |
| `backend/app/__init__.py` | KEEP |  |
| `backend/app/ai/__init__.py` | KEEP |  |
| `backend/app/ai/chat.py` | KEEP | `ai.gemini`, `ai.providers`, `core.config`, `core.diagnostics`, `core.errors`, `routing.service` |
| `backend/app/ai/gemini.py` | REFACTOR | `core.config`, `core.errors` |
| `backend/app/ai/inetcloud.py` | REFACTOR | `ai.gemini`, `core.config`, `core.errors` |
| `backend/app/ai/providers.py` | KEEP | `ai.gemini`, `ai.inetcloud`, `core.config`, `core.errors` |
| `backend/app/api/__init__.py` | KEEP |  |
| `backend/app/api/models.py` | KEEP | `ai.providers`, `routing.router` |
| `backend/app/api/relationship_routes.py` | KEEP | `auth.dependencies`, `auth.limits`, `core.config`, `core.errors`, `database.session`, `datasets.relationship_repository`, `datasets.relationships` |
| `backend/app/api/routes.py` | KEEP | `ai.gemini`, `ai.providers`, `api.models`, `auth.dependencies`, `auth.limits`, `conversations.repository`, `core.config`, `core.diagnostics`, `core.errors`, `datasets.parser`, `datasets.repository`, `dependencies`, `rag.repository`, `rag.upload_parser`, `routing.service` |
| `backend/app/auth/__init__.py` | KEEP |  |
| `backend/app/auth/dependencies.py` | KEEP | `auth.repository`, `core.config`, `database.session` |
| `backend/app/auth/limits.py` | KEEP | `core.config`, `database.models`, `database.quotas`, `database.session` |
| `backend/app/auth/oidc.py` | KEEP | `auth.repository`, `core.config` |
| `backend/app/auth/repository.py` | KEEP | `database.models` |
| `backend/app/auth/routes.py` | KEEP | `auth.dependencies`, `auth.limits`, `auth.oidc`, `core.client_ip`, `core.config` |
| `backend/app/conversations/__init__.py` | KEEP |  |
| `backend/app/conversations/repository.py` | KEEP | `ai.providers`, `core.errors`, `database.models` |
| `backend/app/core/__init__.py` | KEEP |  |
| `backend/app/core/client_ip.py` | KEEP | `core.config` |
| `backend/app/core/config.py` | REFACTOR |  |
| `backend/app/core/diagnostics.py` | KEEP |  |
| `backend/app/core/errors.py` | REFACTOR |  |
| `backend/app/core/logging.py` | KEEP |  |
| `backend/app/database/__init__.py` | KEEP |  |
| `backend/app/database/fresh.py` | KEEP | `database.setup` |
| `backend/app/database/guest_access.py` | KEEP |  |
| `backend/app/database/integrity.py` | KEEP |  |
| `backend/app/database/join_migration.py` | KEEP | `database.models` |
| `backend/app/database/loader.py` | KEEP | `database.models` |
| `backend/app/database/migrations.py` | KEEP | `database.setup` |
| `backend/app/database/models.py` | KEEP |  |
| `backend/app/database/quotas.py` | KEEP | `core.config`, `database.models` |
| `backend/app/database/seed_data.py` | KEEP |  |
| `backend/app/database/session.py` | KEEP | `core.config` |
| `backend/app/database/setup.py` | KEEP | `database.models` |
| `backend/app/database/test_safety.py` | KEEP |  |
| `backend/app/datasets/__init__.py` | KEEP |  |
| `backend/app/datasets/context.py` | KEEP | `core.diagnostics`, `core.errors`, `datasets.repository`, `text_to_sql.join_policy` |
| `backend/app/datasets/parser.py` | KEEP | `core.diagnostics`, `core.errors` |
| `backend/app/datasets/relationship_detection.py` | KEEP | `core.diagnostics`, `datasets.relationships` |
| `backend/app/datasets/relationship_repository.py` | KEEP | `core.errors`, `database.models`, `datasets.parser`, `datasets.relationship_detection`, `datasets.relationships`, `text_to_sql.join_policy`, `text_to_sql.validator` |
| `backend/app/datasets/relationships.py` | KEEP | `core.errors`, `datasets.parser` |
| `backend/app/datasets/repository.py` | KEEP | `core.errors`, `database.models`, `database.quotas`, `datasets.parser`, `datasets.relationship_repository`, `text_to_sql.executor` |
| `backend/app/dependencies.py` | REFACTOR | `ai.chat`, `ai.gemini`, `ai.providers`, `conversations.repository`, `core.config`, `core.diagnostics`, `database.session`, `datasets.context`, `datasets.relationship_repository`, `datasets.repository`, `rag.pipeline`, `rag.repository`, `rag.reranker`, `routing.hybrid`, `routing.router`, `routing.service`, `text_to_sql.executor`, `text_to_sql.generator`, `text_to_sql.pipeline`, `text_to_sql.validator` |
| `backend/app/guest/__init__.py` | KEEP |  |
| `backend/app/guest/limits.py` | KEEP | `auth.limits`, `core.config`, `database.models` |
| `backend/app/guest/middleware.py` | KEEP | `core.config` |
| `backend/app/guest/pipeline.py` | KEEP | `ai.chat`, `ai.gemini`, `ai.providers`, `core.config`, `core.diagnostics`, `core.errors`, `datasets.context`, `datasets.relationships`, `datasets.repository`, `guest.store`, `rag.pipeline`, `rag.repository`, `routing.hybrid`, `routing.router`, `routing.service`, `text_to_sql.executor`, `text_to_sql.generator`, `text_to_sql.join_policy`, `text_to_sql.pipeline`, `text_to_sql.validator` |
| `backend/app/guest/relationship_routes.py` | KEEP | `api.relationship_routes`, `core.config`, `datasets.relationships`, `guest.routes`, `guest.store`, `guest.worker` |
| `backend/app/guest/routes.py` | KEEP | `ai.providers`, `api.models`, `auth.repository`, `core.client_ip`, `core.config`, `core.diagnostics`, `database.session`, `datasets.relationships`, `guest.limits`, `guest.store`, `guest.worker` |
| `backend/app/guest/store.py` | KEEP | `core.config`, `datasets.parser`, `datasets.relationships`, `rag.chunking` |
| `backend/app/guest/worker.py` | KEEP | `core.config`, `core.diagnostics`, `core.errors`, `datasets.parser`, `datasets.relationship_detection`, `datasets.relationships`, `guest.pipeline`, `guest.store`, `rag.chunking`, `rag.upload_parser` |
| `backend/app/main.py` | KEEP | `api.relationship_routes`, `api.routes`, `auth.routes`, `core.config`, `core.diagnostics`, `core.logging`, `guest.middleware`, `guest.relationship_routes`, `guest.routes`, `guest.store` |
| `backend/app/rag/__init__.py` | KEEP |  |
| `backend/app/rag/chunking.py` | KEEP | `rag.documents` |
| `backend/app/rag/documents.py` | KEEP |  |
| `backend/app/rag/pipeline.py` | REFACTOR | `ai.gemini`, `core.diagnostics`, `core.errors`, `rag.repository` |
| `backend/app/rag/repository.py` | KEEP | `ai.gemini`, `core.errors`, `database.models`, `database.quotas`, `rag.chunking`, `rag.upload_parser` |
| `backend/app/rag/reranker.py` | REFACTOR | `core.config`, `rag.repository` |
| `backend/app/rag/upload_parser.py` | KEEP | `core.errors`, `rag.documents` |
| `backend/app/routing/__init__.py` | KEEP |  |
| `backend/app/routing/hybrid.py` | REFACTOR | `ai.gemini`, `core.diagnostics`, `core.errors`, `datasets.context`, `rag.pipeline`, `routing.hybrid_evidence`, `routing.hybrid_policy`, `routing.hybrid_policy_binding`, `text_to_sql.count_contract`, `text_to_sql.pipeline` |
| `backend/app/routing/hybrid_evidence.py` | KEEP | `core.errors`, `datasets.context`, `rag.repository`, `routing.hybrid_policy`, `routing.hybrid_policy_binding`, `text_to_sql.pipeline` |
| `backend/app/routing/hybrid_policy.py` | KEEP | `core.errors`, `rag.repository`, `routing.natural_policy` |
| `backend/app/routing/hybrid_policy_binding.py` | KEEP | `core.errors`, `datasets.context`, `rag.repository`, `routing.hybrid_policy`, `routing.natural_policy`, `text_to_sql.count_contract`, `text_to_sql.pipeline` |
| `backend/app/routing/natural_policy.py` | KEEP |  |
| `backend/app/routing/router.py` | KEEP | `ai.gemini`, `core.diagnostics` |
| `backend/app/routing/service.py` | KEEP | `core.diagnostics`, `core.errors`, `rag.pipeline`, `routing.hybrid`, `routing.router`, `text_to_sql.pipeline` |
| `backend/app/text_to_sql/__init__.py` | KEEP |  |
| `backend/app/text_to_sql/compiler.py` | DEFER production activation | `core.errors`, `datasets.context`, `datasets.repository`, `text_to_sql.join_policy`, `text_to_sql.query_plan`, `text_to_sql.validator` |
| `backend/app/text_to_sql/count_contract.py` | KEEP | `core.diagnostics`, `core.errors`, `text_to_sql.join_policy` |
| `backend/app/text_to_sql/executor.py` | REFACTOR | `core.errors`, `text_to_sql.schema_context`, `text_to_sql.validator` |
| `backend/app/text_to_sql/generator.py` | REFACTOR | `ai.gemini`, `core.errors`, `text_to_sql.schema_context` |
| `backend/app/text_to_sql/join_policy.py` | KEEP | `core.errors`, `text_to_sql.count_contract` |
| `backend/app/text_to_sql/pipeline.py` | REFACTOR | `ai.gemini`, `core.diagnostics`, `text_to_sql.count_contract`, `text_to_sql.executor`, `text_to_sql.generator`, `text_to_sql.validator` |
| `backend/app/text_to_sql/query_plan.py` | DEFER production activation |  |
| `backend/app/text_to_sql/schema_context.py` | KEEP |  |
| `backend/app/text_to_sql/validator.py` | KEEP | `core.diagnostics`, `core.errors`, `text_to_sql.count_contract`, `text_to_sql.join_policy`, `text_to_sql.schema_context` |

### Package import graph

- `ai` → `ai`, `core`, `routing`.
- `api` → `ai`, `api`, `auth`, `conversations`, `core`, `database`, `datasets`, `dependencies`, `rag`, `routing`.
- `auth` → `auth`, `core`, `database`.
- `conversations` → `ai`, `core`, `database`.
- `core` → `core`.
- `database` → `core`, `database`.
- `datasets` → `core`, `database`, `datasets`, `text_to_sql`.
- `dependencies` → `ai`, `conversations`, `core`, `database`, `datasets`, `rag`, `routing`, `text_to_sql`.
- `guest` → `ai`, `api`, `auth`, `core`, `database`, `datasets`, `guest`, `rag`, `routing`, `text_to_sql`.
- `main` → `api`, `auth`, `core`, `guest`.
- `rag` → `ai`, `core`, `database`, `rag`.
- `routing` → `ai`, `core`, `datasets`, `rag`, `routing`, `text_to_sql`.
- `text_to_sql` → `ai`, `core`, `datasets`, `text_to_sql`.

### CLI/entrypoints and tests

FastAPI entrypoint `backend/app/main.py:app`; Uvicorn single worker/reloader. Frontend `src/main.tsx`; Vite dev or Nginx static release.

- `backend/scripts/generate_synthetic_data.py`: KEEP (setup/seed/ingestion/migration/verification CLI, not automatically invoked against main).
- `backend/scripts/ingest_documents.py`: KEEP (setup/seed/ingestion/migration/verification CLI, not automatically invoked against main).
- `backend/scripts/load_seed_data.py`: KEEP (setup/seed/ingestion/migration/verification CLI, not automatically invoked against main).
- `backend/scripts/migrate_ownership.py`: KEEP (setup/seed/ingestion/migration/verification CLI, not automatically invoked against main).
- `backend/scripts/migrate_relationships.py`: KEEP (setup/seed/ingestion/migration/verification CLI, not automatically invoked against main).
- `backend/scripts/rehearse_ownership.py`: KEEP (setup/seed/ingestion/migration/verification CLI, not automatically invoked against main).
- `backend/scripts/setup_database.py`: KEEP (setup/seed/ingestion/migration/verification CLI, not automatically invoked against main).
- `backend/scripts/setup_guest_access.py`: KEEP (setup/seed/ingestion/migration/verification CLI, not automatically invoked against main).
- `backend/scripts/verify_runtime.py`: KEEP (setup/seed/ingestion/migration/verification CLI, not automatically invoked against main).

Inventory: 76 backend test modules, plus fixture/helper modules; frontend unit/E2E fixtures and lockfiles retained.

### API registrations

| Method | Path | Module |
| --- | --- | --- |
| GET | `/api/datasets/{dataset_id}/relationships` | `backend/app/api/relationship_routes.py` |
| POST | `/api/datasets/{dataset_id}/relationships/preview` | `backend/app/api/relationship_routes.py` |
| POST | `/api/datasets/{dataset_id}/relationships` | `backend/app/api/relationship_routes.py` |
| DELETE | `/api/datasets/{dataset_id}/relationships/{relationship_id}` | `backend/app/api/relationship_routes.py` |
| GET | `/api/models` | `backend/app/api/routes.py` |
| GET | `/api/health` | `backend/app/api/routes.py` |
| GET | `/api/uploads/limits` | `backend/app/api/routes.py` |
| POST | `/api/chat` | `backend/app/api/routes.py` |
| GET | `/api/conversations` | `backend/app/api/routes.py` |
| POST | `/api/conversations` | `backend/app/api/routes.py` |
| GET | `/api/conversations/{conversation_id}` | `backend/app/api/routes.py` |
| PATCH | `/api/conversations/{conversation_id}` | `backend/app/api/routes.py` |
| DELETE | `/api/conversations/{conversation_id}` | `backend/app/api/routes.py` |
| POST | `/api/conversations/{conversation_id}/messages` | `backend/app/api/routes.py` |
| GET | `/api/datasets` | `backend/app/api/routes.py` |
| POST | `/api/datasets` | `backend/app/api/routes.py` |
| GET | `/api/datasets/{dataset_id}` | `backend/app/api/routes.py` |
| GET | `/api/datasets/{dataset_id}/preview` | `backend/app/api/routes.py` |
| DELETE | `/api/datasets/{dataset_id}` | `backend/app/api/routes.py` |
| DELETE | `/api/datasets/{dataset_id}/tables/{table_id}` | `backend/app/api/routes.py` |
| POST | `/api/datasets/preview` | `backend/app/api/routes.py` |
| POST | `/api/datasets/import` | `backend/app/api/routes.py` |
| GET | `/api/datasets/{dataset_id}/tables` | `backend/app/api/routes.py` |
| POST | `/api/datasets/{dataset_id}/tables/preview` | `backend/app/api/routes.py` |
| POST | `/api/datasets/{dataset_id}/tables/import` | `backend/app/api/routes.py` |
| GET | `/api/datasets/{dataset_id}/documents` | `backend/app/api/routes.py` |
| POST | `/api/datasets/{dataset_id}/documents` | `backend/app/api/routes.py` |
| GET | `/api/datasets/{dataset_id}/documents/{document_id}` | `backend/app/api/routes.py` |
| DELETE | `/api/datasets/{dataset_id}/documents/{document_id}` | `backend/app/api/routes.py` |
| GET | `/api/auth/login` | `backend/app/auth/routes.py` |
| GET | `/api/auth/callback` | `backend/app/auth/routes.py` |
| GET | `/api/auth/me` | `backend/app/auth/routes.py` |
| POST | `/api/auth/logout` | `backend/app/auth/routes.py` |
| GET | `/api/guest/relationships` | `backend/app/guest/relationship_routes.py` |
| POST | `/api/guest/relationships/preview` | `backend/app/guest/relationship_routes.py` |
| POST | `/api/guest/relationships` | `backend/app/guest/relationship_routes.py` |
| DELETE | `/api/guest/relationships/{relationship_id}` | `backend/app/guest/relationship_routes.py` |
| POST | `/api/guest/session` | `backend/app/guest/routes.py` |
| GET | `/api/guest/limits` | `backend/app/guest/routes.py` |
| POST | `/api/guest/reset` | `backend/app/guest/routes.py` |
| POST | `/api/guest/files/preview` | `backend/app/guest/routes.py` |
| POST | `/api/guest/files` | `backend/app/guest/routes.py` |
| POST | `/api/guest/chat` | `backend/app/guest/routes.py` |

## Historical delivery verification before continuation

- GitHub run39818625553 at3915485 completed SUCCESS for all three jobs: Backend quality998 PASS, PostgreSQL integration784 PASS, Frontend quality PASS.
  Frontend lint/typecheck/build/68 Vitest/105 mock UI are also PASS locally.
- All79 Python modules and31 frontend source files match running development bind mounts;
  API/web env drift list is empty and both services healthy. Main DB container/volume unchanged.
- High-signal Google/GitHub/private-key pattern scan and local Markdown link check PASS;
  this is not a comprehensive historical secret audit. No secrets/env/weights/log/private
  evidence included. Only the pre-existing user report is intentionally left untracked.
- Final documentation commit does not change app source. Its exact local/remote SHA and
  current PR check results are verified at handoff; use PR checks rather than reusing an
  older run as certification of a later commit.
- At historical checkpoint946ff82, QueryPlan production migration was incomplete.
  No Stage 2 benchmark/provider acceptance/release was performed.
