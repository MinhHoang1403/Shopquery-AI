# ShopQuery AI V2 — current acceptance

**MAIN CONSOLIDATED — 8080 ACTIVE — FUNCTIONAL ACCEPTANCE PARTIAL**

Updated2026-10-23 (Asia/Saigon). Operator explicitly authorized consolidation and
safe cleanup before resolving the remaining AI issues. This supersedes the old
rule that blocked merge/cleanup on BGE. No v2.0.0 tag or full acceptance claim.

## Source and runtime

- PR#1 merged; consolidation main SHA `a55acb25162529b1b6b7d44d6b0bde5d4fcc8c96`.
- [Main CI:3/3 PASS](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39899490078).
- Workspace now tracks `main`; feature branch retained as historical reference.
- API source `5c98c967b78767bd388c5b1202eeb21ec8322171`,
  API `shopquery-ai-api@sha256:e581ffd9699a982526be035075f1c2ecb1515d111ae85bbc82f4bb6379008825`;
  Web source `e76dfed2ebcfaebcf37e36485d3041eda68f4209`,
  Web `shopquery-ai-web@sha256:e4a8c96c742bfaf2e6ff834fb320f457dc443ad4df4fedcf797094461e99bfb1`.
- Application Git blobs/80 Python module hashes match the serving image; repo HEAD
  also contains host scripts/config/docs. No image rebuild for consolidation;
  API rebuilt only after the minimal planner/provider patch.
- Windows checkout introduced CRLF-only hash drift; `*.py text eol=lf` now preserves
  canonical Git/image bytes. Strict runtime verifier passes without relaxing hashes.
- One release API8001/Web8080/main PostgreSQL15432, no reload/source bind. Existing
  vector-only retrieval via private `RELEASE_RERANKER_PATH=`. Provider/Guest AI/fallback
  OFF, SDK attempts1. Main container/volume not recreated or migrated.

## Functionality

| Function | Status | Actual evidence/limits |
| --- | --- | --- |
| Google login/logout/relogin | PASS,1 invited account | Operator UI confirmation plus session creation/revocation in DB |
| History/reload | PASS observed scope | Existing history and RAG citations survive API recreation/reload |
| CSV/XLSX | PASS smoke | Guest CSV upload/preview and XLSX preview through8080; authenticated upload not repeated |
| Knowledge SQL | BLOCKED | Two generated plans refused before execution; details below |
| RAG/citations | PASS bounded scope | Knowledge and Gemini live, correct persisted Markdown policy/citation, vector-only |
| Hybrid | BLOCKED | Gemini retrieval passed; QueryPlan generation rejected upstream |
| Knowledge/Gemini overall | PARTIAL | RAG works; SQL/Hybrid acceptance incomplete; paid gate closed after window |
| Guest | PASS bounded scope | RAM upload/reset and private-data denial; Guest AI OFF |
| Owner security | PARTIAL live | Existing offline tests PASS; full two-account live check not performed |
| BGE GPU | DEFERRED/BLOCKED | Prior cold-load memory guard stop; no new load/benchmark, no FP32/model/driver change |

Previously verified suites:1049 backend,804 PostgreSQL,68 frontend,105 mock browser,
60 scripted golden/adversarial replay cases (10/10 per six groups). These are not
natural-language model accuracy or a150-question benchmark. No local full rerun
for this consolidation. Relevant verifier tests7/7, PowerShell parse and actual
Compose default/empty-path/runtime checks PASS. Main CI ran once after merge.

## Data safety

Protected volume `shopquery-ai_postgres_auth_20261019`, archived volume
`shopquery-ai_postgres_data`, development/candidate volumes all retained.
Main container `511c4f5aacccd1ac42261aaa2a7173ae40c5c5e3aa673bb4898d988a8206a3c8` preserved.

Private PostgreSQL17 custom backup/restore rehearsal:178232bytes,34/34 full-row
hashes match; two CHECK cast-deparse differences independently verified equivalent.
SHA256 `42d8c6a181d2844ab2b5db6b4fa98156feef9460e2e641c06d67a198272a8160`.
Evidence/backup root: `C:\Users\admin\.codex\backups\shopquery-ai\stage2-20261023T025413Z`,
operator/SYSTEM ACL; no dumps/config secrets committed. Temporary restored DB was
removed only after proof. No restore/reset/re-ingest of main.

After prior live window:34 schemas/table identities preserved; data/document/chunk
and uploaded tables unchanged. All86 historical messages match baseline. All19 old
conversations and2 users retained; only updated_at of one synthetic conversation
and operator user changed. Other writes are authorized sessions/rate/synthetic
turns. Before/after cleanup, all34 table hashes and schema match exactly.

## Cleanup manifest

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

## Live evidence and outstanding fixes

Previous window cap6 chats/24 generation stages/8 query embeddings/0 document
embeddings/no manual retry. Used5/10/3/0/0; both SDKs1 attempt, fallback OFF.
No budget carries over to a new paid diagnostic/natural-language window.

Verified synthetic workspace: Root audit synthetic ·21-10-2026,3 tables with
5/15/50 rows, full-row match to fixture; original KPI policy chunk and existing768D
embedding match; current authenticated owner verified. Independent PostgreSQL
oracles stay separate from planner prompts. Single policy chunk limits relevance
claims. No customer data transmitted.

| Prior probe | Actual provider/route | Result |
| --- | --- | --- |
| Aggregate/filter | Knowledge/SQL | Invalid nested aggregate; no execution |
| Three-table join | Knowledge/SQL (intended Gemini) | Row count does not take a value column; no execution |
| Policy | Gemini/RAG | PASS correct source/citation,3.64s |
| Policy | Knowledge/RAG | PASS correct source/citation,6.09s |
| KPI | Gemini/HYBRID | Retrieval PASS, generation request rejected before execution,2.26s |

Previous exact failing plans/upstream error bodies were not retained. Do not infer compiler,
quota/key or schema root cause from generic errors alone. Guards remain intact.
New-chat selection resets to default Knowledge by existing design; later requested/
used model attribution verified. UI mismatch is not yet proven.

Fresh approved diagnostic window: maximum2 structured diagnostics plus12 natural
language chats,38 generation stages,8 query embeddings,0 document embeddings;
single SDK/schema attempt, no manual retry, fallback/Guest AI OFF. Old budget closed.
Two diagnostics used2 generation stages, no embeddings or SQL execution:

- Knowledge reproduced the failure: an expression already performs SUM/row_count,
  but its output field repeats the aggregate. Compiler correctly rejects this.
  Planner and typed schema now explain the two mutually exclusive encodings and
  null-reference row_count contract. COUNT/JOIN/compiler guards unchanged.
- Gemini returned HTTP400, schema rejection at QueryPlan generation. The retained
  diagnostic does not identify the offending schema constraint; no speculative
  model/request-format change. Safe status/category logging added, without raw
  upstream messages, prompts, identities or credentials.
- Knowledge no longer makes a second application-level schema request after invalid
  output. SDK retry configuration remains explicit and separately tested.
- Targeted provider/planner/compiler tests111/111 PASS, including captured failure
  shapes and request privacy. [Patch CI3/3 PASS](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39900966187).
  This is not live accuracy acceptance.
- Operator approved API-only cutover and paid gate closure at window end/blocker.
  New API deployed; strict verifier PASS, all34 schema/table fingerprints and118
  installed package versions unchanged. Main DB/Web containers unchanged.
- Direct8080 verification found Nginx retaining the previous API address after
  recreation: API8001 healthy while8080 API failed. Graceful Nginx reload restored
  Web/API8080 HTTP200 without recreating Web. API-only release now validates/reloads
  Nginx after API health. No Web image change or new deployment stack.
- 12 ordinary Vietnamese cases and independent read-only PG oracles prepared.
  First window stopped after5 UI questions:3 PASS,2 FAIL. Paid gate closed through
  API-only deploy; Nginx refresh branch and direct8080 Web/API verification PASS.

| Natural question / Knowledge | Result |
| --- | --- |
| Tổng phí giao hàng là bao nhiêu? | PASS SQL:2472500.00, independent PG oracle match |
| Chỉ tính những đơn đã giao xong, tổng phí và số đơn là bao nhiêu? | PASS SQL:1879500.00/38 rows, exact Đã giao filter and COUNT(*) |
| Mỗi kho có bao nhiêu đơn và thu tổng phí bao nhiêu? | FAIL row_count with column reference; no execution |
| Khi đánh giá KPI, có bỏ những đơn đã hủy không? | PASS RAG:all statuses, real citation22 |
| Theo chính sách KPI, những kho nào đang đạt? | FAIL at answer verification after retrieval and5 SQL rows |

Operator approved4 additional structured diagnostic calls and1 query embedding,
within the original38/8/0 total cap; no automatic/manual retry outside these explicit
diagnostics. Global paid gate remained OFF. Used totals:5 UI chats,19 generation
stages (including6 diagnostic calls),3 query embeddings,0 document embeddings.

Captured boundaries now establish:

- Knowledge JOIN plan puts a fact ID reference on row_count. Typed PlanField now
  exposes separate JSON-schema branches for row count (null reference) versus
  other fields and validates the same rule before compilation. Compiler guard stays.
- Knowledge Hybrid SQL returns all5 correct warehouse totals and the backend policy
  is verified, but the model assigns unverified to every row despite choosing that
  policy. Prompt/schema descriptions now distinguish an already bound policy from
  the final independent verdict check. No verdict override or weakened validation.
- Gemini HTTP400 explicitly names unknown `additional_properties` in response_schema.
  Switch to SDK-supported standard response_json_schema; retain original Pydantic
  extra-field/bounds validation. No model change or unstructured JSON fallback.
- Targeted provider/plan/count/JOIN/Hybrid tests340/340 and Ruff PASS. New source is
  pending API build/deploy/live verification; these checks do not prove live accuracy.
  Six new UI questions prepared (11 unique questions total); stay within original cap.

Subsequent UI checks failed before execution: Gemini average-fee QueryPlan HTTP400
(router SQL succeeded); Knowledge warehouse comparison used SUM on a TEXT order ID.
Global paid gate closed again. Standard response_json_schema did not resolve the
QueryPlan request; it is not retained as an automatic request fallback.

Operator approved2 further one-shot diagnostics within the same38/8/0 cap. Gemini
returned only a generic invalid-argument detail. Knowledge captured the SUM(ID)
plan. Generation now uses one existing representation: aggregates are expression
nodes, fields project their IDs. Direct aggregate fields remain internal compiler
DTO compatibility, not part of the generation schema. No plan repair or relaxed
compiler guard. Gemini now sends native Schema dictionaries with the specifically
rejected additionalProperties keyword omitted; original Pydantic validation still
forbids extra output fields and enforces bounds. Targeted tests341/341 and Ruff PASS;
pending build/deploy/live validation. Totals25 stages/3 query embeddings/0 document
embeddings,7 UI chats plus8 diagnostics. Four new UI cases remain authorized.
Computer Use became available after operator restart; real existing Google session
and synthetic history visible. DevDB restarted with the machine and was stopped
again only after verifying no clients; its container/volume remain preserved.

The planner catalog additionally lists grouping key IDs taken only from approved
relationship targets, so warehouse names are accompanied by their actual identity.
No name-based key inference;49 focused workspace/provider checks PASS after this
metadata-only adjustment. Four final UI cases will exercise Knowledge JOIN/count,
Gemini SQL/Hybrid and an ambiguous follow-up; no extra diagnostic calls remain.

Schema descriptions and backend validation follow the official
[Gemini structured-output guidance](https://ai.google.dev/gemini-api/docs/structured-output).
Standard JSON-schema request configuration follows the
[Google GenAI SDK documentation](https://googleapis.github.io/python-genai/).

Browser automation was disabled by Work settings. Operator used real UI8080;
no cookie extraction or fake auth. Next: investigate provider/schema boundaries,
minimal targeted patch when justified, then a separately approved live window
with10–15 ordinary Vietnamese questions. No GPU benchmark or large test framework.

## Operations

Current instructions: [deployment/rollback runbook](deployment.md). Historical
preparation/rollback reference: [archived handoff](archive/2026-10/v2_release_handoff.md).
Work on main → targeted test → commit/push → build only changed service → approved
API-only/Web-only deploy → direct8080 smoke. No second application stack.
