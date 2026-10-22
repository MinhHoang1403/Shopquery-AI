> HISTORICAL snapshot. Current architecture/status: [Stage 1 report](../../stage1_implementation_report.md).

# Semantic COUNT contract — offline redesign and conformance

Ngày 21/10/2026. Workspace `C:\Work\ShopQuery AI`.

> Cập nhật deployment sau lượt offline: source đúng manifest72 đã được triển khai
> API-only lên8080. Xem `text_to_sql_count_deployment_git_delivery.md` cho runtime/
> Git delivery hiện tại. Các phần dưới giữ evidence của lượt offline; không có
> KH/GH live acceptance mới trong lượt deployment.

**PATCHED OFFLINE — REGRESSION PASSED — NOT DEPLOYED.** Không provider/embedding live, main writes,
migration, restart/recreate main, commit hoặc push. Historical KH draft vẫn UNKNOWN.

## 1. Root architectural cause — đã chứng minh trong source

JOIN policy trước lượt này dùng `aggregate.parent is Alias` và ba tên output
`fact_row_count`, `matched_row_count`, `fact_value_count` để quyết định COUNT được
chấp nhận. ORDER normalizer cũng chỉ tìm SELECT COUNT có một trong các tên đó.
Vì thế alias nội bộ đồng thời đóng vai trò chứng minh phép đếm, tên hiển thị và
gợi ý grounding. Những patch exact-AST/INNER-key equivalence trước chỉ giải quyết
một phần: `COUNT(*) AS delivery_count` vẫn bị chặn dù đúng phép đếm và graph.

Tách rõ năm vấn đề:

| Concern | Nguồn quyết định mới |
|---|---|
| Syntax validity | SQLGlot PostgreSQL parse, SELECT-only/prohibited nodes, PostgreSQL execution |
| COUNT semantics | Argument AST, authorized root fact, exact active INNER edges |
| Business intent correctness | Model phải chọn đúng phép tính theo câu hỏi; analyzer không chứng minh NL intent |
| Backend contract | Typed `CountMetric`/`CountKind` và provenance, không suy từ business alias |
| Display/history label | Giữ output alias PostgreSQL thực sự trả về; không đổi trường thành canonical chỉ để validation PASS |

Đây là nguyên nhân kiến trúc của **các false refusals được tái hiện offline**.
Không có raw KH live SqlDraft; không được kết luận KH lịch sử chắc chắn do SELECT
alias hoặc ORDER BY. Batch A K2/K3/G3 PASS, Batch B KH FAIL trước SQL execution,
GH NOT RUN giữ nguyên kết quả lịch sử. Handoff cũ không phải runtime snapshot mới.

### Inventory mọi đường phụ thuộc canonical count names

| Component | Trước | Sau / compatibility |
|---|---|---|
| Generator / dataset context | Bắt alias canonical, ORDER theo alias | Canonical names là lựa chọn ưu tiên; business aliases duy nhất được phép; SqlDraft schema không đổi |
| JOIN policy | Alias whitelist xác định COUNT validity, rewrite selected key → star | COUNT analyzer riêng; không sửa selected COUNT arguments; SUM/AVG và reserved-role guards còn nguyên |
| SqlValidator | Không có metric provenance | Resolve outputs, typed metrics, revalidation normalized AST và provenance invariance |
| Executor / serialization | Generic row mappings, Decimal/BIGINT lossless | Không đổi executor; output-field names không bị rename |
| SQL answer grounding | Chỉ mô tả tên canonical | Nhận field → kind/source/proof/scope JSON từ backend; label là data |
| Hybrid synthesis | Canonical labels trong grain text | Cùng typed provenance; policy cần rows không được dùng nullable-value count để thay |
| Frontend | Generic `Object.keys(rows)` | Không đổi production UI/API schema; test business labels + history wire roundtrip |
| History persistence | Generic response snapshot, SQL/rows/answer/model | Không đổi DB/API; labels, values, SQL và answer đã ground được lưu/reload nguyên vẹn |
| Diagnostics | Finite AST categories, old alias reasons | Giữ privacy/event cap, bổ sung semantic/clause/ambiguity reasons hữu hạn |

Canonical aliases vẫn được kiểm như **semantic assertions có sẵn** sau khi derive
kind: nullable COUNT không được giả làm `fact_row_count`/`matched_row_count`;
COUNT(*) không được giả là `fact_value_count`. SUM/AVG không dùng reserved count
aliases. Không xóa ràng buộc này khi downstream/history cũ vẫn dùng các tên đó.
Nhưng một tên khác không còn là lý do từ chối COUNT hợp lệ.

## 2. Formal semantic COUNT contract

Nội bộ `CountMetric` lưu kind, root fact, source column nếu có, source aggregate
AST snapshot, selected projection snapshot/index, output field, GROUP BY AST
snapshot, approved relationship IDs/revisions, nonnull proof và normalization
evidence. AST/names/relationship details bị loại khỏi dataclass repr và không log.
Đây là IR **backend-derived**, không phải một contract mới cho model tự cấp quyền.

| Expression | Kind / proof | Semantics và giới hạn |
|---|---|---|
| COUNT(*) | ROW_COUNT / star_rows | Số source rows hoặc matched fact rows sau JOIN/WHERE; không phải DISTINCT dimension entities |
| COUNT(root fact key thật sự tham gia approved INNER ON) | ROW_COUNT / verified_inner_equality | Exact equality loại NULL trên matched key; root fact grain được bảo vệ bởi relationship guards |
| COUNT(root fact other column) | NON_NULL_VALUE_COUNT / nullable_or_unknown | Đếm non-NULL values; zero là present value. Không suy NOT NULL từ tên ID, observed samples hoặc type |
| COUNT(key) trong query một bảng, không JOIN | NON_NULL_VALUE_COUNT / nullable_or_unknown | Có relationship trong workspace thôi chưa đủ; phải xuất hiện đúng INNER equality trong SQL |
| COUNT(dimension column) trong JOIN | Unsupported | Không tự gọi nó là row count/entity count hoặc đổi sang fact column |
| COUNT DISTINCT/FILTER, COUNT(1), nested/arithmetic, COUNT HAVING | Unsupported trong contract COUNT này | Cần proof/contract riêng; không repair expressions, filters hoặc clauses |

COUNT(*) đếm dòng còn COUNT(column) bỏ NULL theo
[PostgreSQL 17 aggregate semantics](https://www.postgresql.org/docs/17/functions-aggregate.html).
Row-equivalence của verified key là suy luận từ exact equality và
[INNER JOIN semantics](https://www.postgresql.org/docs/17/queries-table-expressions.html),
không từ alias. Metadata đúng nhưng ON sai vẫn bị chặn **trước** analyzer.

COUNT key dùng alias `fact_value_count` tiếp tục được hỗ trợ cho compatibility:
source column và INNER nonnull proof được giữ; trong tập matched rows số non-NULL
key values bằng số rows. Kind canonical là ROW_COUNT theo proof, không theo alias.
Selected expression vẫn là COUNT(key), không bị đổi thành COUNT(*).

Không có general NOT NULL solver cho WHERE/constraint inference. Ví dụ một
non-key column được lọc IS NOT NULL vẫn không tự được nâng thành ROW_COUNT.
Không thể suy mọi yêu cầu nghiệp vụ đúng chỉ từ SQL semantics.

## 3. Logical pipeline và trust boundary

```text
parse -> SELECT/prohibited constructs -> exact allowed tables/functions/columns
  -> approved JOIN bindings/graph/exact ON/root fact
  -> entity ID grouping grain
  -> derive COUNT meanings from AST + active edges
  -> build unique projection/output/sort-reference map
  -> normalize only proved references/default label
  -> revalidate objects/functions/columns + graph/grain/COUNT without rewriting
  -> verify unchanged metric provenance
  -> owner/workspace/revision guard -> readonly execution
  -> SQL grounding -> scoped retrieval -> Hybrid grounding if requested
```

Two-table reverse binding normalization và three-table chain/star normalization
vẫn là behavior đã được duyệt: chỉ exact approved INNER predicates được reorder.
COUNT không cấp quyền cho graph mới, không thêm table/edge, không xác định root
bằng vị trí FROM. Analyzer không gọi DB/provider hoặc biến SQL fragments thành quyền.

Revalidation là hai pass deterministic trên AST, **không phải** LLM repair/retry
loop. Pass hai tắt COUNT normalization, kiểm graph/grain và metric provenance còn
giống pass một. Single-table COUNT cũng revalidate table/function/column bindings.
Read-only role, execution timeout/row cap và relationship locking giữ nguyên.

## 4. Alias decoupling và AST normalization proof

### Selected fields

- Business alias duy nhất, không mơ hồ: **giữ nguyên**, không đổi thành tên canonical.
- COUNT không alias: chỉ thêm `AS count` nếu field identity duy nhất, vì đó chính
  là default PostgreSQL output label; vị trí cột và giá trị không đổi.
- Không tự thêm COUNT, không thay COUNT argument, SUM/AVG, metric, WHERE, GROUP BY,
  HAVING hoặc LIMIT. Không tự chèn entity ID hoặc sửa JOIN key.
- Duplicate labels, implicit duplicate `count`, wildcard output không thể chứng
  minh field identity, hoặc name quá 63 UTF-8 bytes: fail-closed bằng code riêng.
- Output fields được resolve theo PostgreSQL UTF8 identifier behavior: unquoted
  ASCII A–Z được fold; Unicode bytes khác không tự dùng Python Unicode `lower()`.
  Quoted lowercase labels được giữ; quoted mixed-case JOIN identifiers vẫn ngoài
  normalized-identifier subset cũ, không mở rộng trong lượt này.

Field-length guard tránh PostgreSQL truncate labels, gây collision hoặc mismatch
với grounding metadata. Giới hạn default được kiểm `SHOW max_identifier_length=63`.
[PostgreSQL identifier rules](https://www.postgresql.org/docs/17/sql-syntax-lexical.html).
Test DB UTF8 trả `Đếm` và `dem` cho unquoted aliases `Đếm`/`DEM`; hai output labels
`Đếm` và `đếm` có thể là hai fields khác nghĩa và được map riêng.

### ORDER BY

Signature của row count là `(ROW_COUNT, verified_root)`; signature của value
count là `(NON_NULL_VALUE_COUNT, verified_root, exact_source_column)`. Star và
verified INNER-key count match cùng row signature; arbitrary nullable/non-key
column không match row signature.

Direct ORDER COUNT chỉ đổi thành **một selected output identifier đã xác minh**
cùng signature. Nhiều selected row counts tương đương có labels khác nhau là an
toàn: chọn projection đầu tiên theo thứ tự SELECT, vì các giá trị bằng nhau;
không nhầm chúng với duplicate field names. ORDER alias có sẵn được giữ.
Count không được SELECT hoặc khác metric tiếp tục bị từ chối, không thêm projection.

Chỉ thay `Ordered.this`: ASC/DESC, NULLS FIRST/LAST, sort ưu tiên tiếp theo và
LIMIT được giữ. Không chuyển reference ở WHERE/HAVING/GROUP BY. Source references
phải qualified trong JOIN; ORDER output label ưu tiên hơn unselected source name,
còn GROUP input priority giữ nguyên.
[PostgreSQL ORDER BY resolution](https://www.postgresql.org/docs/17/queries-order.html).

SQLGlot 29.0.1 AST/parent traversal và selected projection map được dùng trực tiếp.
Đã đối chiếu [scope source](https://github.com/tobymao/sqlglot/blob/v29.0.1/sqlglot/optimizer/scope.py)
và [qualification source](https://github.com/tobymao/sqlglot/blob/v29.0.1/sqlglot/optimizer/qualify_columns.py).
Vì CTE/subquery/window bị cấm, chỉ có một root SELECT; không bật general-purpose
optimizer/qualifier để tự đổi column references hoặc mở SQL subset.

## 5. Grounding, API, display và history

`ValidatedSql.count_metrics` được chuyển vào `SqlResult`, SQL answer và Hybrid
prompt qua `count_evidence()`: field, kind, source column, nonnull proof và scope.
Nó là dữ liệu authorized của cùng workspace, không phải instruction từ tên alias.
Không serialize raw AST/relationships vào response và không ghi provenance vào
generic logs. API response fields/DB schema/executor serialization **không đổi**.

SQL/Hybrid instructions phải dùng kind thay vì đoán từ `delivery_count` hoặc
`total_orders`. Row count zero giúp xác định không matches; row count positive
với SUM/AVG null là all-NULL measurements. Value count zero một mình không đủ
phân biệt zero matches và all-NULL. Nếu câu hỏi/policy cần rows nhưng chỉ có
nullable value count, yêu cầu nêu thiếu evidence, không invent row count.

Đó vẫn là instruction cho model grounding, không phải theorem prover về natural
language answers. Fake gateway kiểm frame/contract, không chứng minh provider sẽ
luôn tuân thủ. Typed analyzer không tự sửa sai business metric do model chọn.

Rows giữ display keys/order và numbers như PostgreSQL. Authenticated test API
kiểm business alias cho Knowledge/Gemini selections ở SQL hai/ba bảng và Hybrid,
reload giữ exact response, model, rows và SQL; owner khác nhận404. History GET
không gọi generation mới. Provenance là nội bộ khi generation, không thêm history
API fields; stored SQL/rows/answer không bị reinterpret/rename lúc reload.
Frontend test kiểm labels Unicode, hai loại count, zero/Decimal và JSON roundtrip.

## 6. Clause-aware refusal và privacy

COUNT SELECT trực tiếp được analyze; ORDER được map riêng. Không dùng một luật
"parent phải Alias" cho SELECT, ORDER và HAVING nữa. GROUP BY metric alias/ordinal
hoặc COUNT trực tiếp không được sửa thành phép grouping khác.

| Stable reason | Phân loại |
|---|---|
| count_wrong_argument_semantics | Reserved row/value role mâu thuẫn expression/proof |
| count_projection_alias_ambiguous | Duplicate/default/wildcard/overlength output identity không an toàn |
| count_order_unprojected | Không có selected COUNT để reuse |
| count_order_non_equivalent | ORDER COUNT không cùng signature với selected metrics |
| count_having_unsupported | COUNT ở HAVING ngoài contract |
| count_clause_unsupported | COUNT ở vị trí/expression clause khác chưa được hỗ trợ |
| count_group_reference | GROUP BY đang trỏ tới aggregate metric |
| argument_expression / filter / dimension_column / projection_expression | Các aggregate subset guards đã có |

API code vẫn `join_aggregate` với frontend refusal ngắn; internal subreason không
được expose/persist vào user response/history. Old reason enum entries còn để
compatibility, không tiếp tục phát generic count_star_alias cho các case mới trên.
Finite AST metadata/correlation/event cap64 vẫn giữ; arbitrary names/SQL/headers/
rows/policy/question/credentials không vào logs. Telemetry failure không đổi kết
quả validation. Rejected draft không tới executor, SQL grounding, retrieval hoặc
Hybrid synthesis. Không fallback qua provider khác để bypass validation.

## 7. Conformance matrix thống nhất và independent oracle

Registry duy nhất: `backend/tests/count_conformance.py`. Unit và PostgreSQL dùng
cùng positive/negative cases, không thêm một normalizer riêng cho từng tên COUNT.
Giữ các historical regressions, cập nhật expectation khi contract đã đổi rõ ràng;
không giảm owner/key/grain/revision/no-executor/security assertions.

### Supported-positive matrix

| Case | Before redesign | Expected / normalized behavior |
|---|---|---|
| Canonical row/value aliases | PASS | PASS, typed provenance thêm |
| Business row/value labels | Alias refusal | PASS, label giữ nguyên, kind từ argument |
| Bare COUNT(*) | Alias refusal trong JOIN | PASS khi unique default label, AS count |
| Approved key COUNT | Chỉ một số alias | PASS theo INNER proof, selected argument giữ nguyên |
| Same COUNT ORDER expression | Chỉ canonical alias | PASS theo signature, không cần label whitelist |
| COUNT star ↔ approved key ORDER | Chỉ canonical row alias | PASS theo row-equivalence proof |
| Multiple row/value metrics | Chỉ canonical tên | PASS, signatures khác nhau không interchange |
| Equivalent projections / nhiều sorts | Alias whitelist | PASS unique field labels, stable selected-map |
| Quoted lower / unquoted ASCII case / UTF8 distinct fields | Chưa có semantic map đầy đủ | PASS, PostgreSQL output names và reference priority đúng |
| Source-name shadowing | Existing canonical case | PASS business label, WHERE/GROUP không đổi |

16 positive templates; fixture chạy single-table và JOIN hai/ba bảng chain/star,
chỉ bật key-row-equivalence templates khi có actual JOIN. **540 supported-positive
scenarios** trong **36 parameterized PostgreSQL tests** (không gọi chúng là 540
pytest tests distinct). Mỗi scenario chạy test-authored raw SQL, normalized SQL,
guarded execution, so exact independent oracle và field/provenance semantics.

| Domain | Fixture variants | Topologies | Positive scenarios | Expected |
|---|---|---|---:|---|
| Logistics | CSV/XLSX, source headers tiếng Việt | Single/pair/chain | 90 | PASS90/90, exact oracle |
| Tuition | CSV/XLSX, duplicate labels/NULL/zero | Single/pair/chain | 90 | PASS90/90, exact oracle |
| Sales | CSV/XLSX, random physical names | Single/pair/chain | 90 | PASS90/90, exact oracle |
| Staffing | CSV/XLSX, all-NULL groups | Single/pair/chain | 90 | PASS90/90, exact oracle |
| Energy | CSV/XLSX, VN calendar boundary filter | Single/pair/chain | 90 | PASS90/90, exact oracle |
| Maintenance holdout | CSV/XLSX, unseen field mappings | Single/pair/star | 90 | PASS90/90, exact oracle |

Oracle dùng flattened known fact/entity mapping trong PostgreSQL VALUES, không
lấy normalized/generated SQL làm expected. Có SUM/AVG/COUNT, nullable measure,
non-unique fact key values, exact entity IDs dù trùng display names, zero/all-NULL,
date filter và top-N. Uploaded physical names UUID ngẫu nhiên; đảo table/column
metadata order và thêm unrelated table. Chỉ original approved edges được dùng.
Selected Count AST trước/sau phải giống hệt; ON predicate multiset, WHERE, GROUP,
LIMIT và sort flags được kiểm, validate idempotent. Existing suites kiểm reversed
bindings, automatic/manual approvals, Decimal/BIGINT, owner và Guest TEMP.

### Unsafe-negative matrix

20 negative templates × 24 JOIN fixture variants = **480 validator-negative
scenarios**, thêm24 missing-approved-edge checks và18 actual owner/workspace/stale
guard cases trong sáu parameterized PG tests. Mọi unsafe negative assert không
tới executor/answer; validator failures còn assert không gọi execution guard.

- Nullable/non-key COUNT giả làm rows; dimension count; DISTINCT/FILTER/nesting/
  arithmetic; unprojected/non-equivalent ORDER; HAVING/GROUP metric; ambiguous/
  duplicate/default labels; wrong key/grain; DML/catalog/window/unsafe functions.
- Thiếu approved edge và two-fact/fanout graph bị chặn; COUNT metadata không cấp
  quyền mới. Existing real full-data relationship tests kiểm target uniqueness,
  orphans/NULL/cardinality trước approval; không giả provenance thành approval.
- Cross-owner/workspace và stale revision giữ real repository guards/locks.
- Alias >63 bytes bị từ chối thay vì để PG truncate; Unicode folding/collision,
  wildcard output và telemetry privacy có thêm unit/adversarial tests.

Không coi SQL PostgreSQL hợp lệ nhưng DISTINCT/HAVING/nesting ngoài subset là
false refusal. Business question hợp lệ vẫn có thể unsupported theo grammar đã
công bố; không repair sang metric/câu hỏi khác.

### SQL/RAG/Hybrid / two non-logistics policies

Existing six-domain SQL/RAG/Hybrid scripted flows được chạy lại. Hai policy
tuition >=30.00 tổng thanh toán và staffing >=12.50 tổng giờ, document oracle đọc
fixture policy riêng; SQL oracle độc lập. Hai model selections fake × explicit
VN time filter có/không × canonical/business aliases = **16 Hybrid tests**.
Kiểm row/value field provenance trong synthesis, real scoped PG retrieval, citation
ID/content, NULL/zero và giữ filter. Threshold chỉ trong fixture/document, không
hardcode vào product analyzer/compiler.

## 8. Regression-first evidence và kết quả

| Check | Before | After / final |
|---|---|---|
| Initial 39 unit conformance cases (sau sửa alias fixture f/p) | 30 alias-based refusals +9 thiếu typed metadata | PASS; positive matrix nay48 cases |
| PG tuition baseline, CSV/XLSX single/pair/chain | 4 JOIN alias failures sau raw/oracle PASS; 2 single thiếu metadata | PASS trong matrix36 PG tests |
| Output byte/case/GROUP edge tests | 4 FAIL trong implementation mới | PASS sau output identity correction |
| Distinct UTF8 fields Đếm/đếm | False ambiguous output refusal | PASS sau PG-compatible projection map |
| Final COUNT unit conformance | — | 92 PASS, thuộc full unit |
| Targeted PG contracts + four privacy cases | — | 46 PASS, 59.16s |
| Targeted replay/two-policy fixtures | — | 79 PASS, 58.51s ở snapshot trước Unicode pair assertion cuối |
| Full backend unit | Baseline678 | **770 PASS**, 19.39s |
| Full PostgreSQL integration | Baseline626 | **682 PASS**, 276.76s, fresh final DB |
| Frontend unit | Baseline66 | **67 PASS**, 9 files |
| Frontend mock UI | Baseline105 | **105 PASS**, 3.4 phút, isolated15173 |
| Ruff / FE lint / typecheck / build / diff check | BaselinePASS | PASS, kiểm lại cuối |
| Knowledge/Gemini/embedding live | Không được duyệt | **NOT RUN: 0 / 0 / 0** |

Các lần targeted rerun là subsets, không cộng lại vào distinct totals. Current
distinct backend là **1452 =770 unit +682 PostgreSQL**, tăng148 so baseline1304.
92 COUNT unit và42 COUNT PG tests nằm trong tổng trên, không cộng lại. 16 opt-in
live tests không chạy. Không còn failing tests ở snapshot bàn giao.

Full PG lần đầu: **678 PASS /4 FAIL**, 348.29s. Bốn privacy regression fixtures
vẫn gửi `COUNT(*) AS payment_count` với mock grounding/retrieval cố tình chưa
được cấu hình vì trước đây query đó bị refuse. Theo contract mới nó hợp lệ,
nên test đi tiếp và mocks fail. Đã đổi fixture sang sai nghĩa thật sự
`COUNT(*) AS fact_value_count`, giữ toàn bộ assertions no execution/retrieval,
no internal code leak/persistence, model/fallback/history. Không sửa production
để phục hồi alias whitelist hoặc làm mock lỗi trở thành successful answer.
Rerun full dùng database test mới; không drop/restore database đầu.

## 9. Environment, integrity và exact changes

Test container mới duy nhất: `shopquery-ai-count-semantic-test`, full ID
`d9c49d74cbda137fb09966cd95597a5f8a5d48f90bace72aeca593a782e20804`.
Existing image pgvector PG17; loopback15441; Mounts=[], tmpfs data, không main/
archived volumes. DBs `shopquery_test_count_semantic` (targeted),
`shopquery_test_count_semantic_full` (first full),
`shopquery_test_count_semantic_final` (fresh final).
Test safety guard không tắt; setup/reader URLs đúng DB/port; provider env rỗng,
fallback false, provider gates tắt chỉ trong process test. Reader default readonly.
Fake embeddings/mocked transports không phải live provider requests.

Đã dọn đúng container test trên sau full regression: kiểm tra full ID/name,
label `shopquery.test=count-semantic-20261021`, Mounts=[] và tmpfs trước khi
stop graceful; xác minh exited/exit0 rồi `docker rm` đúng ID, không force/volume
removal. Ba database synthetic tmpfs bị loại bỏ cùng container, có thể tạo lại
từ fixtures; runner/JUnit/report và image được giữ. Postflight: ba services
ShopQuery API/web/DB vẫn healthy, IDs/StartedAt không đổi, health8080 status ok;
không đụng containers của project khác.

Private runner/JUnit ngoài repo:
`C:\Work\ShopQuery-Backups\count_semantic_offline.py` và
`shopquery_test_count_semantic*.xml`. Fixtures/tests trong repo để reproduce.
Không đọc/export cookies/tokens/main credentials, không đổi `.env`/models/gates/
quotas/retries/OAuth, không main SQL/fingerprints mới. Không lấy fingerprint cũ
làm phép đo mới; kết luận integrity giới hạn ở isolation/no main mutations và
runtime identities/health, không tuyên bố DB bất biến trước concurrent user writes.

Production delta của **lượt này**, giữ dirty changes cũ:

| File | Change |
|---|---|
| text_to_sql/count_contract.py (new) | Typed semantic analyzer/provenance, output/reference map, finite diagnostics helper |
| text_to_sql/join_policy.py | Graph/grain trước COUNT; bỏ alias whitelist + per-shape order helper; giữ SUM/AVG/key restrictions |
| text_to_sql/validator.py | Count metrics, PG output alias resolution, two-pass validation/provenance invariant |
| text_to_sql/pipeline.py | Pass typed evidence to SQL grounding; no executor/serializer/API schema change |
| routing/hybrid.py | Same semantic evidence cho policy synthesis |
| datasets/context.py | Đồng bộ mô tả preferred aliases thay mandatory display whitelist |
| core/errors.py, core/diagnostics.py | Seven bounded semantic reason codes; giữ short API mapping/event privacy |

Generator source trước đó vẫn dirty nhưng **không sửa thêm trong lượt này**.
Executor, history repository, API schema, migrations, settings và FE production
không sửa. Một FE ResultTable unit test mới; centralized conformance registry/
unit/integration files mới, và updates các regressions cũ cho explicit new contract.
Giữ historical reports/handoff và mọi unrelated changes; không reset/checkout/stage.

## 10. Runtime vs working tree / deployment plan

Main tiếp tục API image
`sha256:1a96e048886281ff5d7742e21cb1374e2e88571556c769bcdad3b29990b36417`.
API `fd62fc397a91`, web `2af67d527f2e`, DB `511c4f5aaccc` giữ nguyên IDs và StartedAt
07:10:06 /07:10:22 /07:10:06 UTC, healthy; GET8080 `/api/health` status ok.
Runtime **chưa có** `app/text_to_sql/count_contract.py`. Bản này chưa phục vụ8080.
Volume main `shopquery-ai_postgres_auth_20261019` không bị đụng.

Git HEAD `e2151a3d6b37f3a11e83f68553e5985bbe087deb`, working tree uncommitted;
không có SHA/CI mới, không push hoặc trigger CI.
Local source có72 modules. Manifest LF-normalized SHA-256:
`47b9d4083e13bf32d79c441681d344dcf3f88ea1e5c679604a8f0db1d7f59586`.
Format dùng ở đây: sorted `relative_to_app/path.py SPACE sha256(LF text) LF`,
rồi SHA-256 toàn UTF8 listing; empty files hash như empty bytes. Không so trực
tiếp với historical manifest khác format. Count module byte SHA-256:
`8a8b46f77862da95334f84afd93cbe95b953321dd22d89704eb38eaaa89f5c9c`.

Deployment API-only cần phê duyệt riêng:

1. Review/freeze đúng source sau tests, chốt manifest và current rollback image.
2. Kiểm exact main DB/volume/Compose, approve read-only integrity/synthetic preflight
   riêng nếu cần. Dùng đủ `compose.yaml + .env.compose-ui.yaml + .env.join-v1.yaml`.
3. Báo trước API recreate sẽ mất **Guest RAM state/files/history/in-flight work**;
   drain theo cửa sổ được duyệt, không reset persistent Google/history data.
4. Build/recreate API only, no-deps, không DB/web restart, migration hoặc restore;
   giữ models/provider gates/fallback/retries/quotas hiện hành.
5. Verify72 modules, health, JOIN flag và đúng ba ShopQuery services healthy.
6. Nếu lỗi, dừng trước live; rollback API về pinned current image với cùng overrides
   khi có quyền rollback, không restore/overwrite DB hoặc xóa volume.

## 11. Typed-plan research và quyết định không mở rộng LLM interface

[IRNet](https://arxiv.org/abs/1905.08205) tách schema linking, intermediate query
và deterministic SQL inference. [NatSQL](https://arxiv.org/abs/2109.05153) nghiên
cứu IR đơn giản hơn SQL để giảm khoảng cách NL/SQL. Hai hướng là cơ sở để đánh
giá compiler sau này, không phải bằng chứng tự động chọn đúng business metric
trên ShopQuery hoặc cấp quyền bỏ validator.

[PICARD](https://aclanthology.org/2021.emnlp-main.779/) ràng buộc decoding bằng
incremental parsing. Backend này không kiểm soát decoder của Knowledge/Gemini;
không giả vờ đã triển khai PICARD bằng post-hoc validation. Parse-valid SQL vẫn
có thể sai metric, grain hoặc policy; không lấy benchmark papers làm accuracy ở đây.

Đã chọn backend semantic COUNT normalization trước. Typed provenance giải quyết
alias/sort dependence mà không đổi SqlDraft schema hoặc tăng calls/dependencies.
Không thêm feature flag/LLM typed-plan compiler khi conformance subset đã có
deterministic proof; chưa có live benchmark chứng minh cần migration lớn hơn.

Nếu sau live holdout còn nhiều generation mistakes: đề xuất riêng typed aggregate
intent dưới flag, model chỉ trả registry references/measures/count_rows/count_non_null,
backend authorize và compile AST rồi vẫn validate/guard. Cần benchmark intent
accuracy, filters/grain completeness, adapter structured-schema compatibility,
fallback/rollback/versioning và privacy. Không được tin model-supplied table names,
JOIN permissions hoặc arbitrary SQL fragments. Không triển khai phương án đó ở lượt này.

## 12. A/B/C classification và giới hạn

- **A — false refusal:** đúng expression/graph/grain, chỉ khác display alias hoặc
  proved sort syntax. Đã loại bỏ trong conformance subset bằng semantic signatures.
- **B — generation mistake:** chọn nullable count thay row count, wrong key/grain,
  metric không được yêu cầu. Không đổi column/argument để làm PASS. Reserved role
  contradictions bị chặn; business-intent mismatch còn cần model/oracle kiểm.
- **C — legitimate unsupported:** DISTINCT/FILTER/nesting/HAVING, grouping chưa
  được hỗ trợ, missing/unapproved graph, ambiguity, 4+tables hoặc forbidden access.
  Giữ refusal; không gọi chúng là lỗi alias cần bypass.

Không có guarantee mọi phrasing/dataset/model answer sẽ đúng. Query semantics
valid không chứng minh user intent, tài liệu retrieved đúng không chứng minh
mọi natural-language conclusion. Fake generation PASS chỉ chứng minh application
contract, real PG execution/guards và evidence plumbing, không live model accuracy.

## 13. KH/GH live plan — CHƯA ĐƯỢC PHÉP CHẠY

Sau khi có quyền deploy và separate live budget: đúng workspace synthetic13,
Google session do user tự đăng nhập; fresh read-only independent SQL/document
oracle và protected fingerprints được duyệt. Chỉ safe bounded diagnostics,
không raw production logging/cookies hoặc reuse unused Batch-B quota.

1. KH Knowledge HYBRID: một câu đã chốt về kho đạt KPI, cần rows, exact policy
   retrieval, threshold conclusion/citations, used-model/fallback và history.
2. Chỉ KH PASS và còn budget mới GH Gemini cùng fixture/oracle.

Đề xuất tối đa **2 chats /8 logical generation stages /2 query embeddings /
0 document embeddings** nếu policy vector hiện tại còn hợp lệ. SDK/structured
retry có thể tăng HTTP requests/cost. Không tự retry chat hoặc đổi model.
Dừng ngay nếu sai oracle/metric/relationship/scope, refusal, provider error,
citations/history/fingerprint mismatch. Không thêm probe thứ ba để thử may.

Nếu cần raw synthetic draft, xin quyền single-use/private capture riêng đúng
workspace/user/request và budget, không bật trong lượt này. New live draft dù
cùng câu hỏi không thể khôi phục chính xác SQL KH cũ đã không được lưu.

## 14. Final gate

Full regression đã PASS: 770 unit, 682 PostgreSQL, 67 frontend unit, 105 UI mock;
Ruff/lint/typecheck/build/diff checks PASS. 540/540 supported-positive scenarios
khớp independent oracle;480/480 validator-negative scenarios bị chặn trước
execution,24 missing-edge và18 owner/workspace/stale guard cases không tới executor.
Các con số scenarios là coverage bên trong tests, không cộng thành test totals.

Trạng thái **PATCH READY — DEPLOYMENT APPROVAL REQUIRED**. Chưa gọi bất kỳ provider
nào, chưa deploy. Không tuyên bố LIVE FIX VERIFIED hoặc mọi COUNT/JOIN/Hybrid đều
đúng trên8080 từ các kết quả offline. Exact test-container cleanup ghi sau kiểm tra
identity/mounts và stop graceful đã hoàn tất như mục9; không cleanup tài nguyên
project khác. Không commit/push và không có CI run cho source mới này.
