# Core acceptance checkpoint — 29/10/2026

**CORE_REBUILD_BLOCKED**. Candidate application `ec877ca`; main/runtime unchanged.
Không phải release acceptance. Không merge/build/deploy/source cleanup/image cleanup.

## Confirmed blocker

Knowledge p17 generated district TEXT `3` for gold `quận 3`; typed conversion accepted it.
No trusted mapping or observed district values were supplied by the locked synthetic catalog.
Read-only main PostgreSQL metadata inspection of approved datasets15/16/17 found9tables,
no district column. This does not inspect unrelated/private datasets and does not establish
a source mapping. PostgreSQL exact TEXT comparison returned false. A VALUES counterexample
is a test-only witness, not existing source data. Do not normalize or change gold.

Boundary: model interpretation/literal grounding, before coverage. Coverage preserves an
already represented predicate; it cannot prove the literal entails natural language.
No scoped deterministic repair is proven; no model verifier, prompt-specific patch, retry
or mapping was added. No automatic-release claim or silent fallback.

## Locked 28-case dispatch ledger

`PROPOSAL_ONLY` means conversion/route observation, not end-to-end correctness.
Old-contract proposals are not current-candidate native acceptance. Every execution remains
NOT_EVALUATED here unless the separate replay oracle below explicitly passes.

| Case | Knowledge latest source / observation | Gemini observation |
|---|---|---|
| p01 | bc1e360 / PROPOSAL_ONLY explain | ec877ca / PROPOSAL_ONLY explain |
| p02 | bc1e360 / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p03 | bc1e360 / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p04 | bc1e360 / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p05 | c6c7483 / PROPOSAL_ONLY query | NOT_RUN |
| p06 | 5dcb98c / PROPOSAL_ONLY explain | NOT_RUN |
| p07 | 5dcb98c / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p08 | 5dcb98c / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p09 | 5dcb98c / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p10 | 5dcb98c / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p11 | 5dcb98c / PROPOSAL_ONLY explain | NOT_RUN |
| p12 | 5dcb98c / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p13 | 5dcb98c / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p14 | ec877ca / PROPOSAL_ONLY query | ec877ca / PROPOSAL_ONLY query |
| p15 | ec877ca / PROPOSAL_ONLY explain | NOT_RUN |
| p16 | ec877ca / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p17 | ec877ca / PROPOSAL_ONLY apply_policy; FAIL literal vs gold | NOT_RUN |
| p18 | ec877ca / PROPOSAL_ONLY query | NOT_RUN |
| p19 | ec877ca / PROPOSAL_ONLY explain | NOT_RUN |
| p20 | ec877ca / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p21 | ec877ca / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p22 | ec877ca / PROPOSAL_ONLY explain | NOT_RUN |
| p23 | ec877ca / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p24 | ec877ca / PROPOSAL_ONLY apply_policy | NOT_RUN |
| p25 | NOT_RUN | NOT_RUN |
| p26 | NOT_RUN | NOT_RUN |
| p27 | NOT_RUN | NOT_RUN |
| p28 | NOT_RUN | NOT_RUN |

## Per-field inspection of current SQL captures

| Case/provider | Source / operator / literal | Aggregation / grouping | Output | Execution |
|---|---|---|---|---|
| p14 / both | hotels.room_count / gt / BIGINT120 correct; name+room_count projected | no aggregate | no policy selection or limit | compile PASS; captured replay PG oracle pending |
| p17 / Knowledge | branches.district / eq correct; literal3 differs from goldquận3 | policy binding not run | qualified requested | BLOCKED; no semantic PASS |
| p18 / Knowledge | loans.loan_date >=2025-01-01 AND <2026-01-01 preserved | row_count + branch name; existing approved grain binder/compiler PASS | no order/limit | no execution yet |

Other predicate, policy applicability, grouping and answerability dimensions are not
declared PASS solely from the automatic route/selection checks. p25–p28 were not dispatched:
the current native task harness does not yet construct the locked history/capability states.
Existing scoped conversation regressions do not replace native follow-up acceptance.

## Verification and usage

- Exact candidate CI40826128833:4/4PASS; backend1733PASS, PostgreSQL885PASS.
- Two new Gemini calls: p01 explain and p14 numeric filter; native generation/conversion PASS,
  not RAG answer or SQL execution PASS. Latency1684/1847ms; total2962tokens.
- Agent ledger31/120generation,0/24query,0/0document; do not reset or silently retry.
- New local focused tests33PASS;10PostgreSQL oracle tests collected.
- Added captured synthetic proposals only, no secrets/raw customer logs. The two p14
  providers will be replayed through QueryRouter/SQL pipeline/compiler/executor on isolated
  CI temp tables, compared with manual SQL and boundary119/120/121/200/NULL rows.
  This is captured-output execution, not a fresh live end-to-end generation call.
- Added negative district witness; a passing witness test records a product semantic
  limitation, it does not make p17 an accepted answer.

## Release and cleanup

API/Web8080 retain baseline images2d27fba1/b2188879, health200. ProtectedDB untouched.
Gemini default, Knowledge manual, fallbackOFF, gateON/GuestOFF, Langfuse unchanged.
No production code changes for this closeout checkpoint; no framework/schema redesign.
Source cleanup categories and per-image deletion decisions are deliberately NOT_EXECUTED
until correctness gates pass. Existing image inventory alone is insufficient to delete.
Remaining gates: trusted literal grounding outcome, native history/capability cases, full
per-field held-out grading, supported SQL/RAG/Hybrid actual E2E for both providers, release
security/concurrency acceptance, cleanup regression, main sync/build/cutover/strict verifier.
Keep PR5 draft and all current/rollback images. No unsafe release to satisfy cleanup.
