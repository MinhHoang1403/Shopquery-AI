# ShopQuery AI V2 — current acceptance

**MAIN CONSOLIDATED — 8080 ACTIVE — ACCEPTANCE PARTIAL — PAID GATE CLOSED**

Updated 2026-10-23 (Asia/Saigon). No release tag or full Stage 2 acceptance.
Operator authorized consolidation before completion of AI/BGE acceptance.

## A. Consolidation and data safety

- PR #1 merged at `a55acb25162529b1b6b7d44d6b0bde5d4fcc8c96`.
- Application source on main: `5ba7669535e05d3779a0f2b5832be781405f9000`.
  Later documentation commits do not require rebuilding this image.
- API: `shopquery-ai-api@sha256:1a57c0d151944309951bd32a2e9f21baca79ad3b82caf05683a81c3c2f7659a9`,
  OCI source revision `5ba7669535e05d3779a0f2b5832be781405f9000`.
- Web: `shopquery-ai-web@sha256:e4a8c96c742bfaf2e6ff834fb320f457dc443ad4df4fedcf797094461e99bfb1`,
  OCI source revision `e76dfed2ebcfaebcf37e36485d3041eda68f4209`.
- Strict release verifier PASS: all 80 API module hashes match main, no effective
  environment drift, one worker, no reload/source bind/GPU requests. One release
  API8001/Web8080/main PostgreSQL15432. Direct Web/API8080 both HTTP200.
- Main container `511c4f5aacccd1ac42261aaa2a7173ae40c5c5e3aa673bb4898d988a8206a3c8`
  and Web container unchanged. Main volume `shopquery-ai_postgres_auth_20261019`
  was never recreated, restored, reset, migrated or re-ingested by this work.
- Backup restore rehearsal previously matched 34/34 full-table fingerprints;
  backup SHA256 `42d8c6a181d2844ab2b5db6b4fa98156feef9460e2e641c06d67a198272a8160`.
  Backup/private evidence remain outside Git at
  `C:\Users\admin\.codex\backups\shopquery-ai\stage2-20261023T025413Z`.
- Current audit: all 34 existing tables retained, 27 unchanged table fingerprints,
  all three KPI upload tables unchanged, all 86 original historical messages
  byte-for-byte equal to backup. Live activity added one upload table plus reader
  SELECT grant; existing schema matches backup. Metadata/session/rate/chat tables
  changed during UI activity. Do not claim the complete database is unchanged.
- API-only deployment now waits for health then validates and gracefully reloads
  existing Nginx to refresh the upstream address. This fixes stale-IP 8080 API
  failures after API recreation, without recreating Web or DB. Actual deploy and
  paid-gate closure exercised this path successfully.

## B. Cleanup

Archived with SHA256 verification outside repo, then removed exact root files:

```text
.env.stage1-baseline.json       .env.stage1-cleanup.json
.env.stage1-inventory.json      .env.stage1-reload.json
.env.stage1-runtime.json        .env.v2-baseline.json
.env.v2-candidate.compose.yaml  .env.v2-candidate.json
.env.v2-candidate.runtime       .env.v2-http-check.py
.env.v2-http-state.json         .env.v2-integration-retry.log
.env.v2-integration.log         .env.v2-integrity.json
.env.v2-persistence.json        .env.v2-runtime-baseline.json
.env.v2-schema-check.json       .env.runtime-safe.yaml
requirements.txt (unused generated uv export; backend/uv.lock remains canonical)
```

Private `cleanup-manifest.json` records exact absolute paths/hashes/container IDs.
Active `.env`, `.env.release`, `.env.compose-ui.yaml`, `.env.join-v1.yaml` kept.
Dependencies/virtualenv/node_modules, model artifact, backups, rollback images and
all volumes kept. Historical Stage1 report, preparation handoff and root handoff
moved to existing `docs/archive/2026-10/`; current pointers updated.

Removed exact project-owned candidate API/Web/DB containers:
`shopquery-ai-release-check-api-1`, `shopquery-ai-release-check-web-1`,
`shopquery-ai-release-check-db-1`; removed empty candidate backend network.
DevDB has no active work and is stopped, container/volume retained for tests.
Only serving API/Web/main DB remain running for ShopQuery.8080 health/runtime
verification PASS after cleanup; no serving container restart for cleanup.

Recursive cache removal was blocked by automatic approval review (`blocked by
policy`); cache directories remain. No bypass, broad clean/prune or volume delete.

## C. Functionality and fixes

| Function | Status | Verified scope and remaining limit |
| --- | --- | --- |
| Google login/logout/relogin | PASS bounded | One invited account; operator confirmed real flow; current authenticated UI reload works |
| History/citations | PASS bounded | Persist across API recreation/reload; original 86 messages unchanged |
| CSV/XLSX upload | PASS smoke | Prior Guest CSV upload/preview and XLSX preview; no new authenticated upload acceptance |
| Knowledge SQL | PARTIAL | Basic SUM/filter/count matched PostgreSQL oracle; latest warehouse JOIN/count falsely refused at join_grain before execution |
| Gemini SQL | BLOCKED acceptance | Latest highest-fee warehouse question rejected HTTP400 at QueryPlan; router succeeds |
| RAG | PASS bounded | Knowledge/Gemini policy answers with real persisted citation22, existing vector-only retrieval |
| Hybrid | BLOCKED | Latest Gemini retrieval succeeds but QueryPlan HTTP400; Knowledge follow-up routed UNSUPPORTED |
| Model selection | PASS observed | Actual requested/used attribution checked; new chat defaults to Knowledge by existing design |
| Guest | PASS bounded | RAM upload/reset and private-data denial; Guest AI remains OFF |
| Owner security | PARTIAL live | Existing offline checks PASS; two-account live acceptance not performed |
| BGE GPU / Gate C | DEFERRED/BLOCKED | Memory guard retained, no new load/benchmark, no BGE PASS claim |

Paid data gate, Guest AI and fallback are OFF. Google/history/tabular operations
remain available; new paid AI requests/document embeddings are disabled.

Minimal fixes already on main and in the current API image:

- Generation uses existing expression nodes for every aggregate; fields project
  expression IDs. This removes the duplicate field/expression aggregate contract
  from the provider schema. Row-count reference validation remains strict.
- Approved relationship target IDs are explicit grouping keys in the planner
  catalog. No inferred keys, plan repair, free-form SQL fallback or weaker guards.
- Knowledge makes one structured attempt instead of a hidden second schema call.
- Gemini native Schema dictionaries omit the specifically rejected
  `additionalProperties` keyword; original Pydantic extra-field/bounds validation
  remains. The abandoned raw `response_json_schema` attempt is not a fallback.
- Hybrid instructions distinguish a backend-bound policy from final verification;
  authoritative decisions, numeric/source binding and refusal guards remain.

Validation: 341 targeted core checks and Ruff PASS at `acd6639`; its
[CI has 3/3 PASS](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39904863246).
The subsequent grouping-key metadata delta at `5ba7669` passed 49 focused checks;
full CI was intentionally not rerun for that delta. Do not call it exact-head CI.
Existing large regression/golden suites were not rerun locally for small patches.
Offline success is not live accuracy acceptance. Later interactive logs on the
current image still show two Gemini HTTP400 request rejections and Hybrid failures;
no more precise upstream cause is established by those logs.

Schema compatibility follows official
[Gemini structured-output guidance](https://ai.google.dev/gemini-api/docs/structured-output)
and [Google GenAI SDK documentation](https://googleapis.github.io/python-genai/).

## D. Natural-language acceptance and budget

Only verified synthetic KPI dataset13 was authorized for agent provider calls.
Independent PostgreSQL oracles were computed read-only, separately from prompts.
All-status fees total2472500.00; delivered1879500.00/38 orders. Warehouse totals:
KHO01=393500.00, KHO02=598000.00, KHO03=502000.00, KHO04=439000.00,
KHO05=540000.00; each10 orders. Policy threshold500000.00 inclusive, all statuses;
NULL ignored and zero valid. Qualified KHO02/KHO03/KHO05, citation22.

Seven actual controlled UI questions, each sent once before the latest image:

| Provider / question | Actual result |
| --- | --- |
| Knowledge: Tổng phí giao hàng là bao nhiêu? | PASS SQL2472500.00 |
| Knowledge: Chỉ tính những đơn đã giao xong, tổng phí và số đơn là bao nhiêu? | PASS SQL1879500.00/38, exact status, COUNT(*) |
| Knowledge: Mỗi kho có bao nhiêu đơn và thu tổng phí bao nhiêu? | FAIL row_count column reference; no execution |
| Knowledge: Khi đánh giá KPI, có bỏ những đơn đã hủy không? | PASS RAG all statuses, citation22 |
| Knowledge: Theo chính sách KPI, những kho nào đang đạt? | FAIL final verification after retrieval and five SQL rows |
| Gemini: Trung bình một đơn có phí giao hàng bao nhiêu? | FAIL QueryPlan HTTP400, no execution |
| Knowledge: So sánh tổng phí và số đơn giữa các kho. | FAIL numeric measure validation, no execution |

Current-window approved cap was38 generation stages/8 query embeddings/0 document
embeddings, with explicit amendments for8 one-shot diagnostic calls and12 UI chats.
Before the last approved cutover:7 controlled UI chats plus8 diagnostics used
25 generation stages and3 query embeddings, zero document embeddings. No automatic
or unapproved manual retry; SDK/schema attempts1, fallback OFF.

The final image was deployed with operator approval. On resuming work, the real
browser was in another workspace, with8 additional user UI turns after watermark184.
Sanitized runtime diagnostics record19 more generation-stage events and5 query
retrievals. Combined observations are at least44 stages and8 query embeddings;
these are stage-event counts, not an exact billing statement. Those additional
interactive turns are outside the approved synthetic acceptance corpus, are not
agent acceptance PASS evidence, and document-embedding usage there is unestablished.
No private question/result content from that workspace is included here.

The agent closed the paid gate immediately after detecting this discrepancy;
API-only deploy, Nginx reload, strict verifier and direct8080 health all PASS.
Operator then approved a NEW independent window:4 UI chats,12 generation calls,
4 query embeddings,0 document embeddings, the same verified KPI dataset13, one
attempt per call, no retry/fallback/Guest AI. All four questions were sent directly
through the real UI8080 with Computer Use, exactly once, on source `5ba7669`:

| Provider / question | Actual route / outcome |
| --- | --- |
| Knowledge: Cho tôi tổng phí và số đơn của từng kho. | SQL → UNSUPPORTED at join_grain; false refusal; no SQL execution |
| Gemini: Kho nào thu tổng phí cao nhất? | SQL router PASS; QueryPlan HTTP400 request_rejected; no execution |
| Gemini: Theo tài liệu, kho nào đang đạt và kho nào chưa đạt KPI? | HYBRID retrieval PASS; QueryPlan HTTP400 request_rejected; no execution |
| Knowledge: Vậy còn những kho chưa đạt KPI? | Router UNSUPPORTED; generic insufficient-information refusal; context/Hybrid acceptance unproven |

No result rows were produced in this four-question window, so none can be claimed
as a SQL/oracle or Hybrid PASS. The last refusal avoids invented results but does
not demonstrate conversational-context support. All requested model selections
match the runtime trace, with fallback false. Error metadata leaves used_model null
for the failed Gemini requests; the trace independently identifies Gemini.

Actual new-window usage:4 chats,7 generation calls (4 routers,3 planners),1 query
embedding,0 document embeddings. Eight generation-stage events include one
zero-duration refusal marker, which is excluded from provider-call accounting.
No additional diagnostic call or question retry. Eleven controlled unique natural
questions have now been exercised across the patches; historical failures remain
failures, not overwritten by offline checks.

The gate was closed prematurely after the first refusal, then reopened to complete
the three independent questions within the same approved budget; the failed
question was not resent. The paid gate is now CLOSED after all four, and Guest AI
and fallback remain OFF. All API-only deploys refreshed Nginx without Web/DB
recreation. Final strict verifier PASS, Web/API8080 HTTP200. Across this final
window the full schema and all table identities are unchanged; only
chat_conversations, chat_messages and resource_limits fingerprints changed.
Data/document/upload tables stayed unchanged. The real authenticated history was
reloaded after closure, without fake auth or cookie extraction.

Remaining factual blockers: Knowledge emitted a plan rejected at join_grain;
the exact plan is not retained, so the specific source/group-key error cannot be
asserted from the stage code alone. Gemini still returns generic HTTP400 at the
QueryPlan boundary; no more precise upstream cause is established. No speculative
new patch, weakened guard, paid retry or extra diagnostic was made in this window.

## E. Future workflow

Use the existing [PowerShell deployment runbook](deployment.md#runbook-vận-hành-và-promotion):
main → minimal fix → related tests → commit/push → build only changed service →
pin immutable digest privately → approved API/Web cutover → verify8080 behavior.
No second Docker application stack, no test writes to main, no rebuild for docs.

```powershell
git switch main
git pull --ff-only
# Edit source; run relevant tests listed in docs/deployment.md.
git add -p
git commit -m "Describe the verified fix"
git push origin main
# Build changed service and pin its digest in private .env.release as documented.
# Only after approval for the interruption:
./scripts/release.ps1 -Deploy -Service api
./scripts/release.ps1
Invoke-RestMethod http://127.0.0.1:8080/api/health
```

Historical preparation: [archived handoff](archive/2026-10/v2_release_handoff.md).
No tag or complete Stage2 acceptance until mandatory live and BGE gates pass.
