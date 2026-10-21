# Hybrid COUNT — root-cause investigation and offline fix

Ngày kiểm tra: 21/10/2026, local Windows; PostgreSQL test 17.8; SQLGlot 29.0.1.

Trạng thái: **PATCHED OFFLINE — REGRESSION PASSED**, **NOT DEPLOYED**.
Sẵn sàng bước **PATCH READY — DEPLOYMENT APPROVAL REQUIRED**. KH lịch sử: **ROOT CAUSE
PARTIALLY IDENTIFIED**. Không có live provider request trong lượt này.

## A. Executive findings

1. Xác nhận một false refusal riêng biệt: SELECT và ORDER BY dùng hai cách đếm
   tương đương `COUNT(*)` / `COUNT(root_fact.approved_inner_key)`, nhưng normalizer
   cũ chỉ nhận AST giống hệt nhau. Hai phía không khớp nên COUNT ở ORDER BY bị
   áp luật alias của SELECT, gây `count_star_alias` hoặc `count_column_alias`.
   **24/24 PostgreSQL counterexamples fail-before/pass-after**, sáu domain,
   hai/ba bảng, cả hai chiều chuyển đổi.
2. Xác nhận khoảng trống diagnostics: cùng `count_star_alias` có thể thuộc SELECT,
   ORDER BY hoặc HAVING. Error code cũ không thể phân biệt. Đã thêm metadata AST
   hữu hạn, không ghi SQL/names/values.
3. Khi stress diagnostics, danh sách trace dừng ở 64 nhưng logger vẫn phát thêm:
   test 80 ORDER terms tạo **85 log events**. Đã áp cùng ngưỡng 64 cho việc phát
   events của trace, không chỉ lưu trong RAM. Không thay quyết định validation.
4. **Chưa biết raw KH SqlDraft lịch sử.** Không có bằng chứng nó thuộc false
   refusal vừa sửa, sai alias SELECT hay COUNT trong HAVING. Không tái dựng SQL
   lịch sử từ error code; không thể tuyên bố đã sửa hoàn toàn Hybrid/live KH.
5. Không thay prompt thêm trong lượt này: hợp đồng SQL-evidence/document-policy
   và COUNT alias đã có ở working tree/runtime trước lượt này. Không có evidence
   cho thấy một prompt edit khác sẽ sửa đúng draft KH đã bị mất.

### Call-flow KH và điểm dừng đã quan sát

```text
authenticated workspace/schema/approved relationships
  -> router HYBRID -> SqlGenerator -> structured SqlDraft
  -> parse -> allowed objects/functions -> column resolution
  -> exact JOIN graph/keys -> aggregate policy
  X join_aggregate / count_star_alias
  -- execution_guard / SQL execution / SQL grounding: NOT REACHED
  -- RAG retrieval / query embedding / Hybrid synthesis: NOT REACHED
```

KH không chứng minh lỗi thiếu relationship, schema binding hoặc RAG. Nó chứng
minh draft đã vượt các gate đó đến aggregate validation. Relationship revision
và execution guard chưa được thực thi ở request KH đó.

### K3 Knowledge SQL PASS so với KH Knowledge Hybrid FAIL

| Thành phần | Giống nhau | Khác biệt / giới hạn evidence |
|---|---|---|
| Metadata | Cùng cấu trúc root fact → driver → warehouse, 3 tables/2 edges | Không có raw rejected KH để đối chiếu expression |
| SQL generator | Cùng class, schema contract, `SqlDraft` schema, reference-date rules | Question KH nhắc tài liệu KPI và kết luận đạt/chưa đạt |
| Router | Nhận routing metadata, không nhận các SQL syntax examples | Quyết định SQL ở K3, HYBRID ở KH |
| Dispatch | Cùng SQL pipeline/generator/validator | Hybrid gọi SQL trước, sau đó mới retrieve/synthesize |
| Provider | Cùng Knowledge adapter và structured schema contract | Output model có thể khác theo question; chưa biết SQL cụ thể |
| Grounding | COUNT/SUM root fact, group theo entity ID | KH cần thêm document evidence, nhưng chưa tới bước đó |

`HybridPipeline.run()` truyền nguyên câu hỏi vào `TextToSqlPipeline.run()`;
không truyền route hoặc policy text vào `SqlGenerator.generate()`. Generator
không có document threshold trước retrieval. Prompt hiện đã yêu cầu SQL evidence
only, không bịa threshold, không dịch unretrieved policy thành SQL filter, giữ
filters người dùng nêu; context yêu cầu canonical COUNT alias và ORDER BY alias.
Knowledge thêm system instruction final-answer/schema chung; Gemini nhận prompt
qua structured generation. Các adapter khác serializer, không có nhánh SQL
contract riêng theo route. Mock-transport tests kiểm tra schema cả hai adapter.

Do đó, "nhắc tài liệu làm model sinh HAVING/sai alias" vẫn là **hypothesis**;
khác biệt câu hỏi không đủ chứng minh causal mechanism. Không ép HYBRID thành
SQL-only và không thêm provider call để thử giả thuyết.

## B. Failure anatomy và PostgreSQL proof

`f` là root fact, `d` là dimension; `f.key = d.key` là đúng approved INNER edge.
`m` là nullable fact measure, không phải JOIN key. Tất cả SQL bên dưới là
**synthetic test shapes**, không phải SQL KH được khôi phục.

| SQL/AST shape | Clause | PostgreSQL | Before lượt này | After | Classification |
|---|---|---|---|---|---|
| `COUNT(*) AS fact_row_count`, ORDER BY alias | SELECT/ORDER | Row count | PASS | PASS | Supported |
| `COUNT(*) AS matched_row_count` | SELECT | Row count | PASS | PASS | Supported scalar diagnostic alias |
| Selected COUNT và ORDER COUNT cùng AST | ORDER BY | Cùng selected metric | PASS | PASS | Existing normalizer, không phải fix mới |
| SELECT `COUNT(*) AS fact_row_count`, ORDER `COUNT(f.key)` | ORDER BY | Equivalent on verified INNER rows | `count_column_alias` | PASS | **False refusal fixed** |
| SELECT `COUNT(f.key) AS fact_row_count`, ORDER `COUNT(*)` | ORDER BY | Equivalent on verified INNER rows | `count_star_alias` | PASS | **False refusal fixed** |
| `COUNT(f.m) AS fact_value_count`, ORDER cùng COUNT/alias | SELECT/ORDER | Non-NULL values | PASS | PASS | Supported; NULL semantics không đổi |
| `COUNT(f.key) AS fact_value_count` | SELECT | Non-NULL key values | PASS | PASS | Không ép value-count alias thành row-count alias |
| `COUNT(*) AS delivery_count` hoặc thiếu alias | SELECT | SQL hợp lệ | Refuse | Refuse | Đúng contract refusal; không rename tùy ý |
| SUM được SELECT, ORDER BY COUNT không được SELECT | ORDER BY | SQL hợp lệ | `count_star_alias` | Refuse | Không invent projection/metric |
| Selected COUNT, `HAVING COUNT(*) > 0` | HAVING | SQL hợp lệ | `count_star_alias` | Refuse | Không mở rộng COUNT HAVING |
| `COUNT(*)+1`, `COALESCE(COUNT(*),0)` | SELECT expression | Hợp lệ nhưng khác shape/metric | `projection_expression` | Refuse | Không repair arithmetic/nesting |
| `COUNT(f.m) AS fact_row_count` | SELECT | Có thể ít hơn số dòng | `count_column_alias` | Refuse | NULL row/value distinction |
| COUNT DISTINCT, COUNT FILTER | SELECT | Distinct/subset count | Refuse | Refuse | Vẫn ngoài contract |
| COUNT dimension, SUM/AVG dimension | SELECT | Có thể SQL hợp lệ, sai grain contract | Refuse | Refuse | Root fact only |
| Duplicate output labels / alias trùng selected source output | ORDER | Ambiguous/shadowing | Refuse | Refuse | Không chọn alias mơ hồ |
| Alias canonical quoted lowercase / unquoted uppercase | ORDER | PostgreSQL name resolution | PASS | PASS | Giữ quoting/direction/nulls/top-N |
| Quoted mixed/uppercase identifier | Binding | PostgreSQL case-sensitive | Refuse | Refuse | Metadata normalized exact-name contract |
| Unqualified source column dù PG resolve được | JOIN columns | Có thể SQL hợp lệ | Refuse | Refuse | Qualified-source rule giữ nguyên |
| ORDER bằng alias trùng **unselected** source name | ORDER | Output name ưu tiên | PASS | PASS | Không rewrite WHERE/GROUP source references |

Twelve PostgreSQL-legal unsupported shapes được thực thi riêng trong test,
đối chiếu COUNT/SUM/NULL bằng oracle, rồi xác nhận validator vẫn từ chối. Một
statement PostgreSQL chấp nhận **không tự động thuộc subset JOIN được hỗ trợ**.
HAVING SUM và các aggregate khác không được blanket mở rộng hay blanket cấm
trong lượt này; bảng trên chỉ kết luận các COUNT HAVING đã kiểm tra.

### Proof normalization hẹp

PostgreSQL phân biệt COUNT số dòng với COUNT số giá trị khác NULL.
[Tài liệu aggregate PostgreSQL 17](https://www.postgresql.org/docs/17/functions-aggregate.html).
INNER JOIN chỉ giữ cặp thỏa ON, nên đối với equality trên key, matched fact key
không thể NULL. Đây là suy luận từ
[INNER JOIN semantics](https://www.postgresql.org/docs/17/queries-table-expressions.html),
không phải suy đoán NOT NULL từ tên `id` hoặc sample.

Kiểm chứng độc lập trên test DB, không dùng uploaded tables:

```sql
SELECT count(*) AS rows, count(f.key) AS key_values,
       count(f.measure) AS measure_values, sum(f.measure) AS total
FROM (VALUES (1,0::numeric), (1,NULL::numeric),
             (NULL::integer,99::numeric), (9,88::numeric)) f(key,measure)
INNER JOIN (VALUES (1)) d(key) ON f.key=d.key;
-- rows=2, key_values=2, measure_values=1, total=0
```

NULL-key và orphan không match; NULL measure vẫn thuộc row count nhưng không
thuộc value count; zero không biến thành NULL. Vì vậy equivalence chỉ áp dụng
cho đúng approved root fact key, không áp dụng `COUNT(nullable_measure)` hoặc
non-key ID. Không thay value-count metric.

Normalizer chỉ thay `Ordered.this` bằng identifier của projection COUNT hợp lệ,
duy nhất; không thay cả Ordered node. Vì thế ASC/DESC và NULLS FIRST/LAST không
đổi. ORDER BY standalone output alias có nghĩa theo
[PostgreSQL ORDER BY](https://www.postgresql.org/docs/17/queries-order.html).
Hai cách SELECT COUNT key → star đã được validator hỗ trợ từ trước; thay đổi mới
cho phép chúng match khi chọn ORDER alias. Không có đổi metric mới ngoài proof đó.

Raw SQL, canonical SQL và independent `VALUES` oracle khớp trên 24 ca; AST asserts
giữ nguyên ON, WHERE, GROUP BY, LIMIT, direction và null-ordering; validate lần
hai idempotent. Numeric totals/AVG đi qua Decimal serialization như trước.

## C. Safe diagnostics

| Field | Giá trị được chấp nhận |
|---|---|
| `aggregate_function` | count / sum / avg / other |
| `aggregate_clause` | select / order_by / having / other |
| `aggregate_parent_type` | Finite allowlist: Alias, Select, Ordered, comparator, arithmetic, Paren, Filter, Coalesce, Distinct; còn lại Other |
| `count_argument_shape` | star / column / expression / not_applicable |
| `projection_alias_contract` | valid / missing / invalid / not_applicable |
| `matching_selected_aggregate` | boolean |
| `normalization_candidate` | boolean |
| `normalization_applied` | boolean |
| `reason` | Stable allowlisted `aggregate_reason` hiện có; không xuất exception text |

Clause nhận bằng parent/ancestor AST thuộc đúng root SELECT, không regex.
`projection_alias_contract` mô tả alias COUNT tại SELECT, không thay thế full
argument/type/key validation; DISTINCT có alias đúng vẫn có thể bị reject.
`matching_selected_aggregate/candidate/applied` nói về ORDER-to-selected matching
ở event đang xét, không phải tổng kết tất cả COUNT trong request.

Event `aggregate_normalization` success lưu metadata trước rewrite, applied=true
khi ORDER được thay. Các aggregate validation tiếp theo cập nhật facts của
aggregate đang xét; request-summary cuối có thể applied=false. Cần đọc event
normalization hoặc **failure event**, không suy toàn bộ request từ field cuối.
Không có rewrite khi không match, sai clause, metric khác hoặc alias mơ hồ.

Tên field cố định, values enum/boolean. Arbitrary strings bị bỏ. AST class name
không có trong allowlist trở thành Other; không log table/column/alias name,
question, policy text, result values, SQL, headers, email, credentials hoặc raw
provider response. Diagnostics lỗi không làm query PASS thành FAIL hoặc ngược lại.
Giới hạn trace và phát event nội bộ: 64; một request AST quá dài có thể cạn budget
và không có final summary. Không tăng số provider calls, không thêm retry.

Tests kiểm tra SELECT wrong/missing alias, unselected ORDER COUNT, HAVING, nested,
arithmetic, DISTINCT, FILTER, dimension COUNT, nullable row alias, successful
normalization, rejected normalization, injected telemetry failure, arbitrary-string
redaction và 80 ORDER terms. Không mở raw synthetic capture trên main: chưa cần,
chưa được duyệt. Future safe metadata không phục hồi draft đã mất của KH lịch sử.

## D. Implementation và decision matrix

| Root cause | Evidence | Candidate / safety | Cross-domain impact | Decision |
|---|---|---|---|---|
| Exact-AST COUNT mismatch | 24 failing PostgreSQL reproductions | Match star/verified fact-key row-count only, unique selected alias; all other validation retained | Six domain dynamic metadata | Implement narrow deterministic normalization |
| Clause không được quan sát | 10 refusal shapes, cùng code có nhiều clause | Bounded AST facts, no names/values | Domain-independent | Implement diagnostics, giữ exception/frontend message |
| Event logger không cap cùng trace | 85 events cho trace cap64 | Publish only retained events | Telemetry only | Fix bound |
| KH live selected alias/HAVING/unselected ORDER | Không có raw draft/AST metadata | Không đủ evidence | Unknown | Không repair theo phỏng đoán |
| Generator nhận trách nhiệm policy sai | Current prompt đã tách SQL/document; fake contracts PASS | Không chứng minh generator-output cause | Live holdout cần riêng | Không sửa prompt thêm |
| Typed intent/SQL Agent/repair loop | Chưa có benchmark cần thiết | Scope/architecture lớn hơn | Chưa chứng minh | Không triển khai |

Production files sửa **trong lượt này**:

- `backend/app/text_to_sql/join_policy.py`: metadata-aware COUNT matching,
  `_is_inner_row_count`, `_record_aggregate_shape`, call sites trước các refusal.
- `backend/app/core/diagnostics.py`: finite aggregate facts/stage và cap logger.

Không sửa thêm generator/context/validator trong lượt này. Chúng **đã dirty từ
trước** và được giữ nguyên, cũng như report cũ và các tests/handoff chưa commit.
Không có dependencies, framework, model, quotas, fallback hoặc API schema mới.

Tests mới của lượt này:

- `test_aggregate_diagnostics.py`: AST refusal matrix, normalization positives,
  privacy/bounds/telemetry failure và fake Hybrid fail-before-execution.
- `test_count_key_order_integration.py`: 24 differential positives + 12 SQL-legal
  contract negatives với PostgreSQL thật và independent oracle.
- `test_hybrid_policy_domains_integration.py`: 8 Hybrid cases, hai policies độc lập,
  hai model IDs fake, explicit time-filter được giữ nguyên.

Giữ exact approved ON, hai/ba bảng cùng scope, graph root duy nhất, relationship
revision/execution guard, owner/workspace checks, entity ID grouping, SELECT-only,
function/object/column allowlists và revalidation sau AST normalization. COUNT
nullable/non-key không được chuyển thành row count. Refusal không gọi executor,
SQL answer generation, retrieval hoặc Hybrid synthesis, không tạo evidence giả.

## E. Verification

### Regression-first evidence

| Test group | Before production patch | After | Ý nghĩa |
|---|---|---|---|
| Initial new diagnostic/COUNT unit file | 19 FAIL / 4 PASS | PASS | 4 SQL false-refusal variants; các FAIL còn lại là diagnostics chưa có, không phải 19 query bugs |
| Six-domain COUNT-key PostgreSQL | 24 FAIL, đều sau raw/oracle assertions | 24 PASS | Fail-before/pass-after đúng validator |
| Log-cap + alias diagnostic follow-up | 2 FAIL / 13 PASS trong selection | PASS | 85→64 events; key value-count alias diagnostic corrected |
| Targeted cross-domain SQL/RAG/Hybrid + security suite | Không rerun toàn baseline | 285 PASS, 122.80s | Trước thêm 12 legal-negative matrix cases và 5 diagnostic follow-up cases |
| COUNT PostgreSQL + two policy suite sau thêm matrix | — | 44 PASS, 26.77s | 36 PG COUNT + 8 Hybrid policy |
| Diagnostics focused final | — | 60 PASS, 5.52s | 43 new + 17 existing diagnostics |
| Full backend unit final | — | **678 PASS**, 17.62s | `not integration and not live` |
| Full PostgreSQL integration rerun | 625 PASS / 1 new-test assertion FAIL | **626 PASS**, 216.04s | Fresh isolated DB; exact ON/multiplicity assertions retained |
| Frontend Vitest | — | **66 PASS**, 9 files | No API shape change |
| Frontend ESLint / TypeScript / build | — | PASS | Existing dependencies; build local only |
| Frontend mock UI | — | **105 PASS**, 3.2 phút | Isolated Vite15173; not 8080/live |
| Ruff `app scripts tests` / diff check | — | PASS | Check lại cuối trước bàn giao |
| Live Knowledge/Gemini/embeddings | NOT RUN | NOT RUN | **0 / 0 / 0**, cần duyệt riêng |

### Cross-domain / Hybrid evidence

Sáu domain: logistics, tuition, sales, staffing, energy, maintenance_holdout.
Existing golden fixture có 1/2/3 bảng, chain/star, COUNT row/value, SUM/AVG,
multiple aggregates, random physical names, shuffled upload rows, CSV/XLSX,
Vietnamese questions, duplicate labels, NULL/all-NULL/zero và timezone boundaries.
Context permutation tests thêm table/column order + unrelated table + adapter
contract; không cho unrelated tables trở thành approved edges.

Hybrid mới dùng hai tài liệu synthetic riêng: khóa học đạt tổng thanh toán >=30.00;
phòng ban đạt tổng giờ >=12.50. Document oracle đọc threshold từ fixture policy;
SQL oracle dùng independent flattened facts/VALUES, không lấy model SQL làm expected.
Có/không filter tháng 9/2025 theo giờ Việt Nam × hai model IDs. Mỗi fake gateway
đi đủ router → draft → real validator/guard/PostgreSQL → SQL grounding → fake
embedding + real scoped retrieval → Hybrid synthesis/citation validation.
Không có policy threshold trong SQL prompt; không bỏ explicit date filter;
all-NULL không bị coi là đạt, zero/Decimal giữ nguyên, citation content/file đúng.

Gate-D replay fixture còn kiểm tra đúng 50 facts/15 drivers/5 warehouses, hai
approved edges, source headers tiếng Việt/random physical identifiers, exact
five-group totals và document KPI; authenticated test clients lưu/reload history,
account khác không đọc được. Đây là isolated fixture sessions, không đọc session
Google thật và **không phải nghiệm thu authenticated UI 8080**.

Security negatives chạy lại gồm wrong ON/graph, thiếu/stale relation, revision
drift, owner/workspace, entity-label-only grain, dimension measures, COUNT nullable
gắn row alias, nested/window/DML/DDL/catalog, no-executor-on-refusal, Guest/auth
separation, precision/BIGINT và citations. Không xóa/giảm assertion để làm xanh.

Full PostgreSQL lần đầu: **625 PASS / 1 FAIL**, 265.81s. Failure ở test mới
`test_count_key_order_differential[True-3-maintenance_holdout]`: assertion so ON
theo vị trí, trong khi verified star có thể reorder hai INNER edges theo metadata
random table names. Raw rows đã khớp oracle. Đã sửa test so **sorted predicate
multiset** (giữ đủ từng ON và multiplicity), thêm assert FROM fact không đổi;
không đổi product behavior, không bỏ exact-key assertion. Rerun full dùng fresh
DB khác, không xóa/restore DB trước. Case này giải thích tại sao targeted trước
có thể PASS còn full gặp physical-name ordering khác.

Frontend mock lần đầu không khởi chạy vì port5173 đang dùng. Không kill/reuse
server hoặc đọc phiên của nó; chuyển test server sang port15173 free và đủ 105
tests PASS. Storage-state override bị bỏ riêng trong process mock test, không
đọc/xuất cookies và không dùng Google session thật.

### Database test safety / reproduction

Container riêng: `shopquery-ai-count-clause-test`, ID
`144e63496b55c3f134a80cebbc0fb9c0fe29efa61e92598953c0c310a5ac5db9`.
Existing image `pgvector/pgvector:0.8.1-pg17-trixie`; private bind
`127.0.0.1:15440`; `Mounts=[]`, data tmpfs, không main/archived volumes.
DB targeted `shopquery_test_count_clause`; full suite dùng database mới riêng
`shopquery_test_count_full`, rồi rerun dùng fresh `shopquery_test_count_final`
trong chính container đó. Các names qua
`require_test_database`, URL setup/readonly trỏ đúng port15440; reader role
default read-only. Providers env rỗng, fallback false, beta/Guest provider gates
tắt riêng test process; không đọc/ghi `.env` và không đổi main gates.

Private runner/evidence ngoài Git:
`C:\Work\ShopQuery-Backups\count_clause_offline.py`,
`count-clause-targeted.xml`, `count-clause-full.xml`.
Runner chỉ dùng disposable credentials của test DB, không production credentials.
Các fixtures trong repo tạo/delete đúng workspace test, không trỏ DB `shopquery`.
Reproduce: tạo disposable pgvector DB + setup/reader roles, cấu hình guarded
test URLs/disabled provider env như CI, chạy các test files trên hoặc hai marker
selections. Không chạy helper khi container đã cleanup hoặc URL chưa xác minh.

Cleanup đã hoàn tất: kiểm tra đúng full ID/name/label, Mounts rỗng và data tmpfs;
stop graceful trả exit0 rồi mới `docker rm` đúng ID đó, không force, không xóa
image/volume và không global prune. Dữ liệu synthetic tmpfs của ba DB test không
được giữ, có thể tái tạo từ fixtures. XML/runner/report vẫn giữ ngoài Git/theo
đường dẫn nêu trên. Không dọn container của project khác; ba services ShopQuery
vẫn đúng IDs/healthy và GET8080 `/api/health` vẫn ok sau cleanup.

## F. Historical comparison — không sửa lại kết quả cũ

- Batch A: K2 Knowledge SQL hai bảng PASS; K3 Knowledge SQL ba bảng PASS;
  G3 Gemini SQL ba bảng PASS. 3 chats/9 logical generation/0 embeddings.
- Batch B KH: HYBRID, `join_aggregate/count_star_alias`; 1 chat/2 generation/0
  embeddings, fail-closed, không tới SQL execution hoặc retrieval.
- GH: NOT RUN theo stop condition. Chưa tiêu phần budget cũ không tạo quyền mới.
- KH raw SqlDraft không được lưu. AST shapes ở B là synthetic reproductions,
  không gán thành historical output. New live question dù giống hệt không bảo đảm
  model tái sinh đúng draft cũ.

## G. Runtime, Git và deployment/live readiness

Main không thay đổi trong lượt này; health GET 8080 trả status=ok. Container
identities, images và StartedAt không đổi; đúng ba main services healthy:

| Service | Container | StartedAt UTC |
|---|---|---|
| API | `fd62fc397a91` | `2026-10-21T07:10:06.209810085Z` |
| Web | `2af67d527f2e` | `2026-10-21T07:10:22.522078834Z` |
| PostgreSQL | `511c4f5aaccc` | `2026-10-21T07:10:06.256952072Z` |

API image giữ `sha256:1a96e048886281ff5d7742e21cb1374e2e88571556c769bcdad3b29990b36417`.
Volume DB giữ `shopquery-ai_postgres_auth_20261019`. Compose labels xác nhận
`compose.yaml + .env.compose-ui.yaml + .env.join-v1.yaml`; không dùng base đơn lẻ.
Manifest runtime baseline đã ghi ở Batch B:
`bd500b4c2a56631f91751a086c5e092178f4fc9c6a642b7d5acada2e66a1e238`.
Lượt này không tái hash toàn runtime; kiểm tra trực tiếp hai module sửa chứng minh
working-tree patch **chưa deploy**:

| File | Runtime SHA-256 | New local SHA-256 |
|---|---|---|
| `core/diagnostics.py` | `6807c02b97112a0ae01055c9ac2efe2e3a3815114c5746943da6418dd24312fd` | `c4108b94f180b815915c5612eeed5e9d09be713aabadbd0272f1139299d2c012` |
| `text_to_sql/join_policy.py` | `9233dd57c3d1dbbee2851b680075a8c703b9b8b92d0efb5034de8a3e74651237` | `ead596538b9663799b2ccf40f749e03a9a19d9890805208ef1bba7050074715c` |

Không chạy main fingerprints/SQL dump mới và không đọc OAuth sessions/secrets.
Vì vậy không tự gán kết quả fingerprint Batch B thành phép đo mới; bằng chứng
lượt này là mọi write chỉ qua test URLs/container, main không bị recreate, và
source/runtime diff rõ ràng. Data integrity live acceptance vẫn cần đo riêng
trong cửa sổ được duyệt.

Git HEAD vẫn `e2151a3d6b37f3a11e83f68553e5985bbe087deb`. Không stage/commit/push,
không trigger/check CI cho SHA mới vì chưa có SHA mới. Dirty context/generator/
validator, report cũ, Gate-D/count/context/adapter tests và handoff giữ nguyên.
Tổng Git diff từ HEAD bao gồm cả công việc cũ; không nhầm với delta hai production
files của lượt này. Không secrets/cache/venv/log được stage hoặc commit.

Prompt/context size không tăng bởi lượt này vì generator/context không sửa thêm.
Normalizer chỉ duyệt selected projections cho direct ORDER COUNT, như helper cũ;
phần mới thêm kiểm tra metadata hằng số, AST ancestry ngắn và facts hữu hạn.
Không benchmark p95 production và không suy latency/cost live từ thời gian pytest.

### Deployment plan — CHƯA THỰC HIỆN, cần quyền riêng

1. Review toàn working tree (kể cả dirty Hybrid cũ), chốt source manifest và rollback
   image; kiểm tra exact Compose/DB volume/config không đổi.
2. Khi được duyệt, build/recreate **API only**, đủ ba Compose files; không DB/web,
   migration/seed/restore. Không đổi models/gates/fallback/quotas/OAuth.
3. Cảnh báo: API recreation làm mất **Guest RAM state**. Authenticated history ở
   PostgreSQL không bị reset; cần thông báo trước maintenance window.
4. Kiểm tra API health, module hashes, JOIN flag và ba services healthy trước live.
5. Nếu application regression: chỉ rollback API về image trên với đúng overrides,
   không restore database/volume; giữ nguyên mọi writes mới. Không thực hiện trong
   lượt này.

### Live acceptance đề xuất — CẦN DUYỆT MỚI, không phải quyền thực thi

- Một KH-style Knowledge Hybrid probe synthetic, đúng workspace13 và user Google
  qua UI bình thường. Chỉ safe clause/AST metadata + correlation, không raw capture.
- Nếu KH PASS mới chạy một GH Gemini Hybrid probe cùng synthetic oracle.
- Trần đề xuất chung: **2 chats / 8 logical generation stages / 2 query embeddings /
  0 document embeddings** nếu persisted policy vẫn hợp lệ. SDK retries có thể làm
  HTTP requests/cost cao hơn, không thay retry cấu hình. Không reuse Batch-B quota.
- Budget trên bao gồm diagnostic KH probe; không cộng thêm "diagnostic thứ ba".
- Nếu fail bất kỳ stage, dừng, không retry/chuyển model/đổi validator theo phỏng đoán.
- PASS phải gồm rows/oracle, actual scoped policy retrieval, conclusions/citations,
  used-model/fallback=false, history reload và protected fingerprints không đổi.
- Nếu finite metadata chưa đủ, dừng và xin phép synthetic-scoped, single-use private
  draft capture riêng, binding workspace13/owner/request. Không bật raw logging.

## H. Generalization và kết luận

Root-key equivalence dựa approved metadata, không tên nghiệp vụ; diagnostics dùng
AST classes, không keyword/domain threshold. Hai chính sách khác lĩnh vực chỉ nằm
trong test fixtures. Không làm mọi SQL hợp lệ thành supported SQL, không mở rộng
JOIN graph/aggregate subset và không bảo đảm model sẽ tuân thủ prompt trong mọi
question/schema mới.

Fake gateway PASS chứng minh contract, validation, guard, execution, retrieval và
grounding wiring; không chứng minh live LLM generation accuracy hay toàn bộ nội dung
natural-language answer luôn đúng. Cần live holdout riêng sau deployment được duyệt.

Kết luận hiện tại: lỗi validator tương đương COUNT và khoảng trống diagnostics đã
có evidence offline; exact historical KH cause vẫn chưa đủ evidence. Không tuyên
bố **LIVE FIX VERIFIED** hoặc "Hybrid hoàn toàn hết lỗi" từ kết quả offline.
