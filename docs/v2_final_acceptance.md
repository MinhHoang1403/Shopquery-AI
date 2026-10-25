# ShopQuery AI V2 — current acceptance

**MAIN CONSOLIDATED — 8080 ACTIVE — GEMINI DEFAULT — ACCEPTANCE PARTIAL — PROVIDER GATE ON**

Updated 2026-10-26 (Asia/Saigon). No release tag or full Stage 2 acceptance.
Operator authorized consolidation before completion of AI/BGE acceptance.

## SQL evidence coverage and verified conversation — FULL PASS (bounded scope)

The actual SQL244/correlation79abb63129e34b1caa1561e8502253d8 established a
planning semantic failure: document-threshold HAVING removed the unqualified
entities. A reconstructed typed equivalent (not the original serialized model
response) reached the executor before this patch. It now fails with
`planning_scope_violation`, origin `plan_coverage_validation`, before compilation
or execution. A separate compiled-AST check prevents evidence/parameterized SQL
drift before execution. Normal SQL WHERE/date filters keep their existing path.

`EvidenceCoverageRequirement` describes one all-row entity aggregate using issued
source/column/relationship references. The Hybrid resolver requires a fully
consumed classification request, a unique closed-grammar policy, authorized
identity/measure/aggregate, unique approved path and the existing whole-document
hash/scope/title/unit verifier. Entity wording is checked against policy subject
and registry; it is not a KPI keyword trigger. Explicit time/status qualifiers or
unknown wording do not enter this path. Ambiguous metadata cannot authorize it.

For this bounded simple-policy case, QueryPlanner constructs a fresh typed plan
from that evidence, using SchemaReferences/bind_approved_grain/QueryCompiler.
It never deletes filters from a model plan, invents SQL text, calls a repair model
or changes user filters. Coverage validates source, grouping, direct aggregate,
relationships and absence of evidence-removing predicates/limits. The independent
SQLGlot check verifies emitted lineage and exact executed AST; compiler SQL/JOIN/
COUNT/read-only guards still run separately. Registry dimension row counts also
prevent claiming full classification when an INNER JOIN omits an entity with no
fact rows; this does not replace AST/provenance/cardinality checks.

Policy verification and Decimal evaluation/composition still independently run
after execution. For requests for only qualified/not-qualified entities, SQL
evidence remains complete; the composer verifies all decisions first, then
selects presentation. NULL retains insufficient-evidence semantics and cannot
be marked fully verified. No model decides a policy verdict in this path.

Backend `verification_status` distinguishes verified_classification, unverified,
explanation and refused. It flows through HybridResult → ChatResult → ChatResponse
→ existing JSON persistence → reload. Only a coverage-checked, source-bound,
fully evaluated/cited classification receives verified_classification. No database
migration or history rewrite. Old Hybrid messages without this field remain
readable but cannot supply a KPI premise. `contextual_question()` requires this
trusted status and retains owner/dataset/conversation/bounds/reset guards; a
later unverified/error turn invalidates older premises. SQL/RAG context remains
compatible. The exact current question travels separately from untrusted bounded
history so history cannot hide a filter from request interpretation. Fresh SQL/RAG
evidence is still retrieved for each follow-up.

537 targeted backend tests PASS, including HAVING/WHERE/LIMIT/group/metric/source
violations before execution, AST drift, aliases, approved/ambiguous paths,
Decimal/NULL/zero, omitted dimension entities, staffing headers, scope/hash,
security/COUNT/JOIN guards and verified metadata persistence/context. Ruff and
diff checks PASS. Frontend TypeScript and21 App tests PASS without Web source
changes; its response parser accepts the added optional metadata. No configured
backend static type checker was added.

Read-only PostgreSQL integration using production planner/compiler/executor and
Hybrid verifier returns all12 exact fees, total33066538.03, correct6/6 statuses
and citation23. The follow-up presentation contains exactly TS01–TS06 while SQL
retains12 rows. The reconstructed old HAVING plan is rejected. No provider calls,
test writes to main, new stack/database/workspace or document embeddings. Existing
private evidence folder uses coverage prefixes; actual live acceptance is pending.

Technical basis: installed SQLGlot29.0.1/Pydantic2.14.1 behavior is reproduced in
tests; [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html)
defines HAVING group elimination, [SQLGlot AST](https://sqlglot.com/sqlglot/expressions/query.html)
provides structural clause/column nodes, and [Decimal](https://docs.python.org/3/library/decimal.html)
supports exact numeric comparisons. No dependency/provider/model/compiler changes.

New live budget explicitly approved:2 questions/6 generation/2 query embeddings/
0 document embeddings, one attempt, no retry/fallback/Knowledge/extra paid
diagnostics; Q2 only after Q1 PASS. Gate stays ON for authenticated normal use,
Guest/fallback OFF, vector-only. API-only build and approved cutover follow the
deployment runbook; no Web rebuild or PostgreSQL recreation.

### Controlled deployment and live acceptance — 26/10/2026

Operator explicitly approved cutover and restored Computer Use. API-only promotion
deployed application source `3364da43bc0c2828fe0bd2b2ec3504a59955b7f9`, immutable
API digest `sha256:de4bf4c27fab2025ef59f6ae37e6ba2ce9175997f501be147a4ca64e33df123a`.
No active leases/Guest workers before recreate; Nginx configuration/graceful reload
PASS. Existing Web/main PostgreSQL containers and protected volume are unchanged;
rollback image retained. No source modification or rebuild during live acceptance.

Both approved natural questions were sent once through Computer Use on8080 in one
dataset15 conversation. Q1 selected Gemini + Hybrid. Q2 was sent only after Q1
passed full SQL/policy/oracle verification, keeping Gemini and selecting Auto.

| Question | Actual live result |
| --- | --- |
| Theo tài liệu KPI, trạm nào đạt và trạm nào chưa đạt? | PASS: message246,12 exact station IDs/fees, all-status scope, threshold2800000, TS01–TS06 not qualified and TS07–TS12 qualified; citation23; backend verified_classification |
| Vậy những trạm chưa đạt KPI là trạm nào? | PASS: message248, same conversation, Auto routes HYBRID; verified Q1 premise, fresh retrieval/SQL; complete12-row SQL evidence, presentation exactly TS01–TS06, citation23; backend verified_classification |

Q1 correlation `9e5b0a2ca8a74d26ab077e27cbd77b81`, Q2
`f5ad272356774f118f8f869b1c6b56e4`. Both record
coverage_requirement=full_entity_classification and successful pre-execution
coverage validation, compilation, relationship guard, SQL execution and policy
verification. Actual persisted SQL has the approved N:1 JOIN, grouping on the
dimension key, correct fact SUM and no WHERE/HAVING/LIMIT/OFFSET. Independent
read-only PostgreSQL oracle checks all12 fees (total33066538.03;30 fact rows per
station), then production policy binding/Decimal/composer verifies every status
and exact summary/table consistency. Scope/hash and the actual cited MD content
match. The Q2 six-row display is selected after complete classification; its
12-row SQL evidence is intentionally retained. The final presentation verification
diagnostic reports6 rows, while sql_execution/result_rows remains12.

The backend-generated verification metadata is persisted for both responses and
survives reload. Google session, workspace, previous history and both new answers
remain visible on8080. A read-only context check confirms the verified premise is
eligible while the prior unverified message244 is rejected. Source-path and unit
contract checks verify fresh evidence rather than treating history as authority.

Actual paid use:2 user questions,1 generation stage (Auto router only),2 query
embeddings,0 document embeddings. The source-bound deterministic plan/evaluator
needs no planner or verdict generation. No retries, fallback, Knowledge requests
or additional paid diagnostics. This agent test window is finished; normal
authenticated provider gate remains ON, Gemini default, Guest/fallback OFF.

Postdeploy strict verifier PASS:86 source modules, exact API identity and no
source/environment drift. Web/API8080 health PASS. All37 table/schema fingerprints
checked; only chat_conversations/chat_messages/resource_limits changed. Every
pre-window message<=244 is hash-identical. Uploaded data, documents/chunks/vectors,
relationships, users and Google sessions remain unchanged. Main is pushed clean;
only acceptance documentation is committed after application source3364da4.

FULL PASS applies to the two corrected failure classes and this bounded Q1/Q2
acceptance. Deterministic coverage supports one complete, unconditional closed-
grammar SUM/AVG policy with uniquely bound sources and supported classification
wording. Unknown wording/extra filters, exceptions, multiple rules, ambiguous
paths or incomplete entity coverage do not gain verified classification. No
claim of universal natural-language support, full historical CI/golden coverage,
Knowledge503 recovery, BGE/Gate C or Stage2/release completion. No tag is created.

## Hybrid policy correction — 25/10/2026 — PARTIAL / LIVE FAILED

The historical Gemini correlation `2532bcfc7ff0471786da83ed06dd385d` proves
successful retrieval, planning, compilation and execution (12 rows), followed by
a parsed answer draft and a verification refusal. Its SQL, retrieved chunk IDs,
candidate count and draft remain UNKNOWN. Reconstructed fixtures do not recover
that missing payload and cannot prove its exact rejection branch.

A corresponding false-refusal class is reproduced independently: grouping a fact
by its approved N:1 foreign key produces the same 12 identities and exact amounts
as the successful dimension JOIN, but `_bind_prose()` previously accepted only
the relationship target key. `_identities()` imposed the same restriction.
The fact-side key was rejected before classification; conventional `*_id` names
could instead fail the subject check against the fact label. Regression fixtures
also reproduce this outside the EV domain with arbitrary `ref_unit` keys/aliases.

`identity_source()` now resolves a source key to exactly one approved entity key
for subject verification. It does not create a JOIN, infer keys from `ma_`, or
alter the registry/compiler. Missing targets or ambiguous mappings refuse.
AST source/aggregate/group checks and uniqueness remain mandatory. The real
single-chunk KPI parses correctly without parser or title-guard changes. Both
JOIN and fact-key reconstructions run the production candidate/binding/Decimal/
classification/composer chain, matching all12 PostgreSQL oracle IDs/statuses,
threshold2800000, all statuses and citation23. These are offline checks, not live
Gemini acceptance.

Typed, bounded `ErrorContext.reason_code` and policy counts distinguish document
scope/hash/parser/multiple-rule, identity/metric/aggregate/coverage/unit/path,
classification, exact numeric and citation refusals. Pipeline wrappers retain
the reason; discarded policy candidates record sanitized verification metadata.
No raw SQL, cells, prompts, documents or model drafts enter diagnostics. Existing
UI refusal text, provider errors, one-attempt behavior and no-retry contract remain.

Targeted tests cover the corrected equivalent-key shapes, arbitrary aliases,
Decimal/NULL/zero, missing/ambiguous relationships, scope/hash, qualifiers,
multiple candidates, SQL coverage, identity/decision/citation consistency,
injection, COUNT/JOIN security and successful/failed/cross-owner context.
The reconstructed complete answer fits the existing bounded context contract;
conversation code is unchanged. Ruff and read-only PostgreSQL oracle checks PASS.
No full historical/golden/BGE suite, second stack, database or workspace is created.

Only backend core errors/diagnostics and the three Hybrid modules change; tests
and this current acceptance document supply the evidence. No SQL compiler,
registry, schema, policy contents/thresholds, provider, model or Web changes.
Application source `f90592dae6810dff3a45b2fbc19a46c52c99010a` was pushed to main
and deployed API-only after explicit timing approval. API digest:
`sha256:5bc66e195142d838204b3ea4b81f43068193b034c13a8f107f2b84526dfa26e4`.
369 targeted cases pass across the bounded run and corrected test-only assertion
rerun (368 passed initially; its JSON-escaped premise assertion was corrected,
then the19-case delta passed). Ruff/diff checks pass. Full CI/golden/BGE were
intentionally skipped; no unchanged Web build.

Budget:2 questions/6 generation/2 query embeddings/0 document embeddings, one
attempt, no retry/fallback/extra diagnostics; Q2 only after actual Q1 PASS.
Gemini default/provider gate remain ON for normal operation; Guest/fallback OFF.
Historical exact root cause remains unresolved; FULL PASS requires both live
questions plus strict runtime/data verification.

Q1 was sent once through Computer Use on8080 with Gemini + Hybrid. Message244,
correlation `79abb63129e34b1caa1561e8502253d8`: SQL validation/execution succeeded,
but returned only6 rows. The actual persisted SQL groups on the approved fact-side
key and adds `HAVING SUM(q0.phi_sac_vnd) >= 2800000`. Independent read-only
PostgreSQL comparison confirms those six fees are correct, while TS01–TS06 are
omitted. Citation23 is the correct MD policy. This is a new, precisely observed
coverage failure, not proof of the missing historical SQL's shape.

`verified_policies()` correctly refuses the HAVING branch before candidate parsing:
`policy_sql_scope_incomplete`, origin policy_verification, phase verification,
category insufficient_evidence. The early metadata candidate_count=0 means not
computed at that branch, not proof that the document parser found no candidate;
independent offline parsing finds exactly1. `verified_classification()` returns
None; one structured answer draft is then composed as explicitly UNVERIFIED,
with no qualified verdict asserted. Consequently HTTP200/request-success is not
business acceptance. The UI shows six unverified stations, not the required12
classifications. The existing coverage guard must not be removed or HAVING
silently stripped to relabel this as PASS.

Confirmed remaining boundaries:

- `QueryPlanner.generate()` accepts a typed plan containing the document-threshold
  HAVING despite its existing prompt prohibition. The SQL compiler accepts it as
  valid read-only SQL; it is the Hybrid evidence requirement that is violated.
  A further fix needs deterministic coverage enforcement at the planning/execution
  boundary, not another prompt patch or a paid repair call.
- `_persist_chat_turn()` persists this unverified result with route HYBRID and
  error=null. A read-only offline call with that actual conversation proves
  `contextual_question()` accepts it as a successful premise. Valid verified
  classification must be distinguishable in the context contract; no follow-up
  was sent using this premise. No conversation source patch is included here.

The user-required stop-on-Q1-failure rule was followed: Q2 NOT_RUN /
BLOCKED_PRECONDITION, no source repair followed by another paid request. Actual
usage:1 question,2 generation stages (planner + draft),1 query embedding,
0 document embeddings; one attempt, no retry/fallback/Knowledge request.
Normal-operation gate stays ON. Evidence remains private in the existing folder,
with hybrid-correction prefixes and a screenshot. This task is PARTIAL; Hybrid
and conversational business acceptance are not complete.

Post-window strict verifier PASS (84 source modules, immutable API identity, no
source/environment drift); Web/API8080 health PASS. Google login and persisted Q1
history survive reload. All37 tables and schema retain integrity: only chat
conversations/messages/resource_limits changed; every earlier message<=242 is
hash-identical. Uploaded tables, documents/chunks/vectors, relationships, users
and sessions are unchanged. Web/main DB containers and protected main volume
were not recreated. Application image source remains f90592d; subsequent commits
only update this acceptance record. Main is pushed without release tag.

## Current operation: Gemini default — 25/10/2026

Operator explicitly selected Gemini for normal authenticated operation. Private
`.env.release` overrides `AI_DEFAULT_MODEL=gemini`, generation `gemini-3.5-flash-lite`,
embedding `gemini-embedding-2`, attempts1, fallback OFF, provider gate ON and Guest AI
OFF. This supersedes earlier bounded-window gate-closure instructions. Do not
turn this normal-operation gate OFF when an agent smoke window ends. Application
quotas, concurrency and owner isolation remain unchanged. Knowledge remains configured;
its upstream503 has not been fixed.

Configuration-only API recreate and Nginx graceful reload; no source/image rebuild.
Web/DB containers and application source5d4c595/image digests below are unchanged.
Strict verifier PASS: 84modules, no source/image/environment drift; Web/API8080HTTP200,
all healthy. Google session/history reload PASS. Authenticated `/api/models` shows
Gemini default, AI enabled, both integrations configured and fallback false. New chat
selects Gemini. One old chat switched through the existing selector and persisted on
reload; its historical Knowledge message attribution stayed unchanged. No bulk history
edits. UI retains3tables/3docs/2approved N:1 relationships.

Key presence/equality to Compose verified without disclosing key. Two non-generation
`models.get` calls confirm both IDs and supported actions. Three targeted provider
selection/empty-workspace offline tests PASS. No regression/golden/BGE reruns or guard
changes.

New approved smoke budget:4chats/8generation stages/2query embeddings/0documents,
explicit SQL/Hybrid source choices, one attempt, no retry/fallback, conditional progression:

| Check | Live outcome |
| --- | --- |
| Total sessions/fee | PASS:360 /33066538.03; fact COUNT(*) and SUM, no filters; PostgreSQL oracle matches |
| Per-station JOIN | PASS:12stations,30sessions each; all exact fee rows match independent PostgreSQL oracle; group station ID+name |
| KPI Hybrid | NOT ACCEPTED: retrieval/planner/compiler/execution succeed with12rows; answer draft parses, then policy_verification refuses insufficient_evidence |
| KPI follow-up | BLOCKED_PRECONDITION / NOT_RUN: no successful KPI premise; no fourth question |

All requests selected Gemini; successful SQL requested/used Gemini, without Knowledge
or fallback. KPI correlation `2532bcfc7ff0471786da83ed06dd385d`: phase verification,
origin policy_verification, category insufficient_evidence. No HTTP503 or invalid
structured output in this window. Intermediate Hybrid SQL/rows/chunk IDs/draft were
not retained in the error response; exact binding/refusal cause remains unresolved.
This is not proof of incorrect SQL. No extra paid diagnostics or unrelated patch.
PDF/DOCX RAG not separately tested here.

Used3chats/4generation/1query embedding/0documents. Agent smoke window ended; normal
gate remains ON. All37tables/schema retained; only conversations/messages/resource_limits
changed; old messages<=236 hash-preserved; uploads/docs/vectors/relationships/accounts/
sessions unchanged. Private evidence reuses ev-acceptance-20261024 with gemini prefix.
This is bounded SQL/JOIN acceptance, not full Hybrid/RAG/Stage2 acceptance.

## Knowledge connectivity investigation — 25/10/2026

No generation or embedding requests; gate stayed OFF. Effective URL/model/timeout/
attempt config matches Compose. DNS/TCP/verified TLS from serving API container PASS,
no proxy environment or HTTP-client proxy mounts. GET model-list and health return
503 text/html,107bytes,about75–80ms. A credential-free GET models over direct TLS
without SDK returns the same body/hash. Readiness/model listing not confirmed.

Response exactly matches HAProxy's default503 template; reverse-proxy/load-balancer
origin is strongly inferred, not instance/backend identity proof. Backend DOWN,
unmatched Host/path/default_backend,maintenance or other serving cause cannot be
distinguished without upstream logs/health-check state. User has no server admin
access. No Retry-After/upstream request ID received. Original24/10 correlation
2424518bb21940e2b878641eae2e0609 was local, not forwarded as a request header;
original503 body/headers were not captured. Do not claim new GET fingerprint proves
the historical response body or exact model-worker failure.

Offline real-SDK serializers send the configured prefix +chat/completions,model
knowledge,and strict json_schema correctly; real server support remains UNVERIFIED.
No source/config/serving change justified, no repeat EV tests. Administrator must
check vhost/path routing,selected backend/server,termination state and LastChk,
then restore the confirmed failing service. Private handoff and endpoint identity:
existing ev-acceptance-20261024 backup folder,knowledge-503-admin-handoff.md and
knowledge-admin-endpoint-private-20261025.json. Internal host/URL is not published.
Knowledge remains BLOCKED_PROVIDER;503 not fixed. Main8080 Web/API HTTP200.

## Latest reliability deployment and bounded live window — 24/10/2026

Application source `5d4c595965ad379b85627dac227034446e673ef7` deployed on8080,
API digest26877f4176df1dc17924cee02491df349f8d0b548252d547e7294d9775df72df,
Web digestbd7601be72e6d60aae704ff3f857a8f91162a89a9f0f54a534f7a15656210467.
Targeted CI460backend+131PostgreSQL tests PASS; unchanged frontend inputs at
fcf230b passed73unit+105mock browser checks. First CI found2 obsolete LLM-grounding
assumptions; assertions now verify deterministic behavior/provenance. No broad/golden
or BGE benchmark reruns. These tests do not prove live AI correctness.

Operator reported Python/DLL permission resolved. Same project .venv imports
select/subprocess successfully. Strict verifier after deploy and gate-close PASS:
84module hashes, immutable image identity/source revision, no environment/source drift.
No interpreter bypass/security policy changes. Main DB container/volume unchanged.
Google session/history reload and UI3tables/3docs/2approved N:1 PASS after cutover.

New budget approved10UI questions/14generation stages/4query embeddings/0documents,
attempts1/no retry/fallback/Guest AI. Q1 sent once, original Vietnamese wording,
Knowledge with explicit SQL selection. Router skipped; planner call HTTP503;
error phase=request, category=transient_unavailable, attempt=1, attempted_route=SQL,
correlation2424518bb21940e2b878641eae2e0609. Messages235/236 persisted correctly.
SQL compilation/execution not reached. Status BLOCKED_PROVIDER, not SQL logic failure.

Stop-on-blocker condition applied: no Q2–Q10, no retry/provider swap/paid diagnostics.
Q10 additionally lacks successful KPI premise. Used1generation,0query embeddings,
0document embeddings. Gate closed via API-only recreate+graceful Nginx reload;
Web and main DB not recreated during gate closure. Web/API8080 HTTP200, all healthy.

37tables/schema retained. Only conversations/messages/resource_limits changed;
uploaded physical tables, docs/chunks/vectors, relationships, accounts/sessions
unchanged; all pre-window messages<=234 preserve exact hash. Oracle remains
360rows/33066538.03, not a successful application SQL answer.

Reliability error path PASS live in this bounded failure case; SQL/RAG/Hybrid on
this new image NOT ACCEPTED live. Q9 old exact invalid field remains unknown.
Old EV window had Q8RAG PASS; Q1–Q7 BLOCKED_PROVIDER;Q9FAIL_INTERNAL;Q10blocked.
That historical success does not prove this deployment's complete acceptance.

Private evidence stays in existing ev-acceptance-20261024 folder with reliability
prefix; current detailed error report is updated there. No release tag/full Stage2.

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

The authenticated provider data gate is ON after the operator's later approval
for normal use (section F). Document embeddings and Knowledge/Gemini chat are
enabled. Guest AI and fallback remain OFF; Google/history/tabular operations work.

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

## F. Provider operation and latest gate

Document ingestion immediately calls Gemini Embedding before persistence; the
existing allow_provider_data guard therefore blocks PDF/DOCX/TXT/MD when the gate
is OFF. CSV/XLSX ingestion does not require a provider. This is an operational
consent gate, not an upload parser failure. Legacy DOC and scanned PDF/OCR remain
unsupported.

The operator closed the24/10bounded window,then explicitly reopened normal operation
with Gemini default on25/10. Current RELEASE_PROVIDER_DATA_ENABLED=true;
GuestAI/fallbackOFF,vector-only,noBGE. Normal operation is separate from agent test
budgets;do not reuse unused calls or auto-close the normal gate after smoke tests.

Google session/history and tabular data remain available. No source fix or parser
change should silently alter this consent boundary.

## G. Future workflow

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

Historical preparation reports remain available in Git at commit `87cdf40`;
they were removed from the current checkout during the operator-requested cleanup.
No tag or complete Stage2 acceptance until mandatory live and BGE gates pass.
