# ShopQuery AI V2 — current acceptance

**MAIN CONSOLIDATED — 8080 ACTIVE — ACCEPTANCE PARTIAL — PAID GATE CLOSED**

Updated 2026-10-23 (Asia/Saigon). No release tag or full Stage 2 acceptance.
Operator authorized consolidation before completion of AI/BGE acceptance.

## A. Consolidation and data safety

- PR #1 merged at `a55acb25162529b1b6b7d44d6b0bde5d4fcc8c96`.
- Application source on main: `ac369738f152ad2f685fbbd86fb71cdfa51fad8d`.
  Later documentation commits do not require rebuilding this image.
- API: `shopquery-ai-api@sha256:f161d7f5a441e7d036e4ecf97c3e4bd864edeefaf00820c577bb3c8cf31a2fa9`,
  OCI source revision `ac369738f152ad2f685fbbd86fb71cdfa51fad8d`.
- Web: `shopquery-ai-web@sha256:e4a8c96c742bfaf2e6ff834fb320f457dc443ad4df4fedcf797094461e99bfb1`,
  OCI source revision `e76dfed2ebcfaebcf37e36485d3041eda68f4209`.
- Strict release verifier PASS: all 83 API module hashes match main, no effective
  environment drift, one worker, no reload/source bind/GPU requests. One release
  API8001/Web8080/main PostgreSQL15432. Direct Web/API8080 both HTTP200.
- Main container `511c4f5aacccd1ac42261aaa2a7173ae40c5c5e3aa673bb4898d988a8206a3c8`
  and Web container unchanged. Main volume `shopquery-ai_postgres_auth_20261019`
  was never recreated, restored, reset, migrated or re-ingested by this work.
- Backup restore rehearsal previously matched 34/34 full-table fingerprints;
  backup SHA256 `42d8c6a181d2844ab2b5db6b4fa98156feef9460e2e641c06d67a198272a8160`.
  Backup/private evidence remain outside Git at
  `C:\Users\admin\.codex\backups\shopquery-ai\stage2-20261023T025413Z`.
- Prior consolidation audit: all 34 existing tables retained, 27 unchanged fingerprints,
  all three KPI upload tables unchanged, all 86 original historical messages
  byte-for-byte equal to backup. Live activity added one upload table plus reader
  SELECT grant; existing schema matches backup. Metadata/session/rate/chat tables
  changed during UI activity. Do not claim the complete database is unchanged.
- Root-correction audit: all 35 current tables and schema retained. Only chat
  conversations/messages and resource limits changed during the four-question
  window; data/documents/relationships/uploads stayed unchanged. All messages
  preceding this window remain byte-for-byte equal to the pre-correction snapshot.
  The image retains the same 118 installed package versions as the previous API.
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

An earlier cache removal was blocked by automatic approval review. Subsequent
explicitly authorized deep cleanup removed reviewed project caches and unused
images/build records; its private manifest is under `deep-cleanup-20261023` beside
the other backup evidence. No broad prune or volume deletion was used.

## C. Functionality and fixes

| Function | Status | Verified scope and remaining limit |
| --- | --- | --- |
| Google login/logout/relogin | PASS bounded | One invited account; operator confirmed real flow; current authenticated UI reload works |
| History/citations | PASS bounded | Persist across API recreation/reload; original 86 messages unchanged |
| CSV/XLSX upload | PASS smoke | Prior Guest CSV upload/preview and XLSX preview; no new authenticated upload acceptance |
| Knowledge SQL | PASS bounded | Natural warehouse fee/count question returns five exact PostgreSQL oracle rows with COUNT(*) and stable warehouse IDs |
| Gemini SQL | PASS bounded | Native compact QueryPlan request accepted live; highest-fee warehouse KHO02/598000.00 matches oracle |
| RAG | PASS bounded | Knowledge/Gemini policy answers with real persisted citation22, existing vector-only retrieval |
| Hybrid/context | PASS bounded | Gemini KPI classification and Knowledge follow-up in the same conversation match all five rows/statuses and citation22; follow-up still shows the full table |
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
  catalog. The backend now completes only a unique approved path/fact/key; there
  are no invented keys, free-form SQL fallbacks or weaker compiler/COUNT guards.
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
Offline success is not live accuracy acceptance. Historical interactive logs on
the previous `5ba7669` image show Gemini HTTP400 rejections and Hybrid failures;
their more precise upstream cause remains unknown. New bounded live proof is in E.

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

At the end of that previous window: Knowledge emitted a plan rejected at join_grain;
the exact plan is not retained, so the specific source/group-key error cannot be
asserted from the stage code alone. Gemini returned generic HTTP400 at the
QueryPlan boundary; no more precise upstream cause is established. No speculative
new patch, weakened guard, paid retry or extra diagnostic was made in this window.

## E. Root-cause correction and bounded live proof (23 October)

Source `ac36973` was pushed to main, built and deployed API-only with operator
approval. A NEW independent window was approved for four synthetic UI questions,
at most12 generation stages/4 query embeddings/0 document embeddings. Historical
failures above remain failures; the results below are new acceptance evidence.

- JOIN/grain: all four original rejection branches now identify `fact_source`,
  `dimension_measure`, `subtotal_group` or `dimension_group_key` in sanitized
  diagnostics. The last live plan was not retained, so its exact branch remains
  unknown. Captured older synthetic plans separately demonstrate invalid COUNT
  references, SUM on a text order ID and missing warehouse identity grouping.
  `plan_binding.py` binds the sole direct measure source, unique approved N:1
  path and referenced dimension identity keys before the unchanged compiler.
  Missing/ambiguous paths, mixed fact measures, wrong COUNT provenance and fanout
  still refuse; no table, relationship or measure is invented.
- Gemini: the original native SDK PlanDecision schema has seven nullable nodes
  and nine array constraints; Router/RAG have neither. SDK transformation already
  removes `anyOf`/references, so their presence in Pydantic alone does not prove
  the HTTP400 cause. The earlier explicit `additionalProperties` rejection is
  confirmed; the later generic HTTP400 does not establish a more precise cause.
  The new flat typed generation contract uses the same native `response_schema`
  request format, no nullable nodes or provider-side bounds, and deterministic
  conversion into the original validated QueryPlan. Actual installed SDK wire
  serialization passes offline transport tests. The same native request was also
  accepted live for Gemini SQL and Hybrid below. No free-form SQL, repair call or
  fallback is introduced. The old generic400's exact rejected constraint remains
  unproven; live success establishes this contract's bounded compatibility.
- Hybrid: the verified simple policy previously still required a model verdict
  and could fail final evidence consistency. A uniquely source-bound policy now
  uses existing Decimal evaluation and the same authoritative answer composer.
  Multiple/exception rules, unknown scope, filtered/top-N SQL and ambiguous
  bindings retain refusal/unverified behavior. Citation identity, NULL/zero,
  owner/workspace scope and read-only SQL guards are preserved.
- Context: `_persist_chat_turn` previously sent only the current message into
  `service.chat`, leaving QueryRouter without the preceding successful KPI turn.
  It now supplies at most two bounded successful pairs from the same server-owned
  conversation/dataset. Failed or oversized intervening turns clear the premise;
  context is untrusted reference data and current evidence must be retrieved and
  verified again. Stored user messages remain the original question.

Changed modules: `text_to_sql/plan_binding.py`, `generation_contract.py`, planner,
QueryPlan, compiler/JOIN policy/pipeline; `ai/gemini.py`; routing Hybrid evidence
and composer integration; conversation context/repository and `api/routes.py`;
bounded core error/diagnostics fields. Related tests cover these boundaries.

Validation: 386 targeted unit checks PASS, 37 scoped PostgreSQL integration
checks PASS, a related 34-check PostgreSQL run PASS, and the final 134-check
diagnostics/schema/context delta PASS. These groups overlap and are not an
additive unique-test count. Integration uses the existing isolated test DB,
including the five-warehouse independent oracle, omitted identity/path binding,
same-conversation follow-up, cross-owner denial and unsafe policy cases. Ruff
and diff whitespace checks PASS. No full regression/golden or GPU benchmark was
rerun. Full CI is intentionally skipped for this bounded patch; targeted checks
are not exact-head full CI evidence.

All four questions were sent exactly once through Computer Use on8080, in one
new dataset13 conversation. The fourth was sent only after the third supplied a
valid KPI premise. Persisted SQL, rows, answers, provider attribution and citation
were checked against the independent PostgreSQL oracle and the original policy:

| Provider / natural question | Actual evidence |
| --- | --- |
| Knowledge: Cho tôi tổng phí và số đơn của từng kho. | PASS SQL: five exact warehouse totals, ten orders each, COUNT(*), warehouse ID grouping |
| Gemini: Kho nào thu tổng phí cao nhất? | PASS SQL: KHO02/Hải Phòng/598000.00; native structured request accepted |
| Gemini: Theo tài liệu, kho nào đang đạt và kho nào chưa đạt KPI? | PASS Hybrid: exact five fees and statuses; qualified KHO02/KHO03/KHO05, not qualified KHO01/KHO04; citation22 |
| Knowledge: Vậy còn những kho chưa đạt KPI? | PASS bounded context/Hybrid: same conversation, fresh retrieval/SQL, correct KHO01/KHO04 and citation22; answer also includes the complete five-row classification table |

Actual use:4 chats,10 generation stages (4 routers,4 planners,2 SQL answer calls),
2 query embeddings,0 document embeddings. Two Hybrid policy-verification stages
are backend work and are excluded from provider usage. No additional diagnostics,
retry, fallback or question was used. Guest AI stayed OFF and the gate is CLOSED.
There were no source changes or broader test runs during the live window.

Initial browser permission failure was resolved before any paid call. After gate
closure and API-only recreation, strict verifier PASS, Web/API8080 HTTP200, real
Google session/history reload PASS, and saved citation content opens correctly.
Web/main DB identities, uploads, relationships, data/document tables and schema
remain intact. All pre-window messages are byte-for-byte unchanged. The current
API image and its rollback image remain local; no new stack was created.

This proves the four requested natural questions in the verified synthetic
workspace, not all possible SQL/policy shapes. Gate C/BGE and two-account live
owner acceptance remain open; no release tag or Stage2 completion is claimed.

## F. Future workflow

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
