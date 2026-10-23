> HISTORICAL snapshot. Current architecture/status: [Stage 1 report](../../stage1_implementation_report.md).

# Batch A live acceptance và khả năng tổng quát hóa Text-to-SQL

Ngày kiểm tra: **21/10/2026**, múi giờ Việt Nam UTC+07:00.

## Kết luận

- **BATCH A LIVE PASSED FOR LOGISTICS TEST MATRIX**: K2, K3, G3 đều PASS trên UI
  8080 với Google session thật, PostgreSQL thật, đúng workspace synthetic 13.
- **CROSS-DOMAIN OFFLINE VERIFIED** trong ma trận dưới đây: **400 test khác nhau
  PASS** (281 PostgreSQL integration + 119 unit); Ruff PASS.
- **CROSS-DOMAIN PROVIDER LIVE NOT VERIFIED** / **CROSS-DOMAIN LIVE PROVIDER
  ACCURACY NOT MEASURED** đối với các domain ngoài logistics.
- Không có production patch/deploy mới, migration, thay config, commit hoặc push.
  Không thể kết luận mọi dataset/cách diễn đạt đều đúng từ ba lần sinh SQL thành công.

## A. Preflight và phạm vi quyền

Đã đọc AGENTS.md, handoff.md, các báo cáo investigation/verification, root-cause audit,
JOIN acceptance và implementation/context/tests liên quan. Giữ nguyên các thay đổi có
trước trong working tree, bao gồm Hybrid; không dùng HEAD đơn thuần để suy ra runtime.

### Source/runtime

| Thành phần | Giá trị đã xác minh trước và sau |
|---|---|
| Git HEAD | `e2151a3d6b37f3a11e83f68553e5985bbe087deb`, có thay đổi chưa commit |
| API | `fd62fc397a91153f36bf9a3bc378283d0664e1754b2993a86d2b6433b664e67f` |
| Web | `2af67d527f2e6b63386c7371c4970bc8c21431e063c9db990040d8f271fe211d` |
| DB | `511c4f5aacccd1ac42261aaa2a7173ae40c5c5e3aa673bb4898d988a8206a3c8` |
| API image | `sha256:1a96e048886281ff5d7742e21cb1374e2e88571556c769bcdad3b29990b36417` |
| 71/71 Python app modules | Runtime = local, LF-normalized manifest `bd500b4c2a56631f91751a086c5e092178f4fc9c6a642b7d5acada2e66a1e238` |
| Active DB volume | `shopquery-ai_postgres_auth_20261019` |
| Compose | `compose.yaml` + `.env.compose-ui.yaml` + `.env.join-v1.yaml` |
| Environment digest | `ddcd7de55005f7fb5dcf88cbdf7614354867ba0e58a864c9e618ae4e28dd60c7`, không đổi |
| Health | API/web/DB healthy; `/api/health` trên 8001 và 8080 trả HTTP 200 |

JOIN bật; Knowledge = `knowledge`, Gemini = `gemini-3.5-flash-lite`; fallback false.
Embedding config giữ `gemini-embedding-2`, 768 dimensions. Không đổi provider gates,
OAuth, quotas, retries hoặc timeouts. Merged Compose environment khớp runtime.
Gemini SDK 1.75.0: timeout 30 giây, attempts 3 cho transient errors theo cấu hình cũ;
Knowledge timeout 60 giây, transport attempts 1, giữ nguyên xử lý structured format.
Không reset quotas hay tận dụng ngân sách Gate D cũ.

### Dữ liệu, quyền và oracle

- Tab 8080 có Google session hợp lệ do người dùng tự đăng nhập; reload vẫn hợp lệ.
  Owner của workspace 13 khớp tài khoản hiển thị. Không đọc/xuất cookies hoặc tokens.
- Workspace **Root audit synthetic · 21-10-2026**, 50 orders / 15 drivers / 5 warehouses.
  Physical identifiers khớp saved oracle; registry/columns/types đã đối chiếu catalog.
- Đúng hai verified edges: orders.tai_xe_id → drivers.tai_xe_id và drivers.kho_id →
  warehouses.kho_id. Revision, direction, statistics hợp lệ, không NULL keys,
  duplicate target keys hoặc orphans. Không thêm/xóa/xác nhận lại relationship.
- Catalog check bổ sung ban đầu của helper coi registry `TEXT` là PostgreSQL `text`.
  Đây là giả định sai của helper, không phải schema drift: `datasets/repository.py`
  ánh xạ `TEXT` → SQLAlchemy `String` → PostgreSQL `character varying`. Sau khi đối
  chiếu đúng mapping hiện hữu, toàn bộ catalog khớp. Không ALTER/cast dữ liệu.
- Oracle được xây dựng bằng SQL độc lập từ dữ liệu synthetic **trước live**, không lấy
  generated SQL làm expected. So sánh từng ID/name/SUM/COUNT, không chỉ grand total.
  Saved Gate D oracle SHA-256:
  `bda5e5aac8a08af94713c66778b1357ac5831a306db36aa999ea834c15f587ee`, oracle mới khớp.
- Fixture có 4 NULL fees và 3 zero fees: SUM bỏ NULL đúng PostgreSQL, COUNT(*) vẫn
  tính đủ 50 fact rows; không đổi COUNT(column) thành COUNT(*) để làm đẹp số liệu.

Các truy vấn audit main dùng transaction REPEATABLE READ / READ ONLY, statement timeout
30 giây và lock timeout 3 giây, rollback cuối phiên. Fingerprints tính server-side,
không xuất raw business rows. Không chạy helper snapshot cũ vốn có phạm vi rộng hơn.

## B. Batch A live trên authenticated UI 8080

Chạy theo thứ tự, mỗi lượt chỉ sau lượt trước đã đạt rows/answer/history. Không retry chat.

| Case | Model requested = used | Route | Validator/guard | Execution | Oracle | Answer/history | Kết quả |
|---|---|---|---|---|---|---|---|
| K2 | inetcloud-knowledge | SQL | PASS | PostgreSQL, 15 rows | Exact PASS | Exact PASS / reload PASS | PASS |
| K3 | inetcloud-knowledge | SQL | PASS | PostgreSQL, 5 rows | Exact PASS | Exact PASS / reload PASS | PASS |
| G3 | gemini | SQL | PASS | PostgreSQL, 5 rows | Exact PASS | Exact PASS / reload PASS | PASS |

Tất cả response: error=null, fallback=false, sources=[]; đúng owner/workspace.
Model attribution dựa trên response metadata, gateway selection/config runtime và safe
diagnostics, không chỉ nhãn frontend; không có independent provider-side billing trace.

### Câu hỏi đã gửi nguyên văn

**K2**:

> Theo từng tài xế, cho biết mã tai_xe_id, tên ten_tai_xe, tổng phi_giao_vnd và số dòng đơn giao hàng, tính tất cả trạng thái. Phân biệt tài xế theo mã ID; đếm dòng đơn, không đếm tài xế.

**K3 và G3**:

> Theo từng kho, cho biết mã kho_id, tên ten_kho, tổng phi_giao_vnd và số dòng đơn giao hàng, tính tất cả trạng thái. Dùng liên kết đơn giao hàng → tài xế → kho; phân biệt kho theo mã ID.

### Kết quả và bằng chứng

- K2: 15 driver identities, tổng COUNT = **50**, tổng SUM = **2472500.00**. Hai bảng
  được phép, root orders, một INNER JOIN, grouping driver ID, COUNT(*) AS fact_row_count.
  Cả 15 rows và bảng Markdown trong answer khớp independent oracle (Decimal exact).
- K3/G3: root orders, đúng ba bảng/hai approved edges, grouping warehouse ID,
  SUM trên fact fee, COUNT(*) AS fact_row_count. Không tự thêm status/date filter.
  Tổng 50 facts / 2472500.00. K3 và G3 tình cờ có cùng final SQL hash; không coi đó
  là bằng chứng một provider dùng kết quả của provider kia.

| Synthetic warehouse ID | SUM fee | COUNT fact rows |
|---|---:|---:|
| KHO01 | 393500.00 | 10 |
| KHO02 | 598000.00 | 10 |
| KHO03 | 502000.00 | 10 |
| KHO04 | 439000.00 | 10 |
| KHO05 | 540000.00 | 10 |

Không yêu cầu ORDER BY nên so sánh exact multiset theo ID, không áp đặt thứ tự ngoài câu hỏi.
K2/K3 answer dạng bảng, G3 dạng danh sách; kiểm từng ID, label, amount và count, không
đánh FAIL chỉ vì khác hình thức trình bày. Reload từng conversation giữ đúng model,
answer, rows và evidence controls; bảng rows sau reload khớp oracle.

| Case | Conversation ID synthetic | Correlation ID của chat | Request duration server |
|---|---|---|---:|
| K2 | b2287e27-aebc-449a-89c1-3e1e086813f3 | ff4b475146fe46fb92228a91d6701f83 | 13.906s |
| K3 | 3c41c4c5-74da-4669-90f4-3ac3fd1351cd | 8f353547a59644fa9f116fa9f87dfb5b | 9.016s |
| G3 | 5108dc16-54f4-487a-ab4d-b5281cf9a970 | 5718b1c2dc1c42b285f0e4fa2d3a4bfe | 6.890s |

Safe diagnostic stages đều success: workspace_binding, relationship_approval,
schema_metadata, router, generator, parse, column_resolution, join_graph,
execution_guard, sql_execution, answer_grounding. Một số stage có tên kết thúc
`_unsupported`/`_error` nhưng **status=success, reason=ok**, không phải refusal.

Final SQL SHA-256:

- K2: `09fd34b50db5c0a2b6766df00873bb06e901214027753d206e742b0234d1263e`.
- K3/G3: `6b605e3435da5c6852be4d1717ce3a42e0b6ce14817bc7554b9c29c4e28c9292`.

Ngân sách thực hiện: **3 chats, 9 logical generation stages (router/draft/answer),
0 embedding calls**, không upload document, không Batch B hoặc extra chat retry.
Đây không phải số HTTP requests: instrumentation hiện tại không xác định chính xác
SDK transport/structured-format attempts hay billing tokens; không khẳng định 9 HTTP
requests. Không thay retry settings để tăng xác suất PASS. Không capture raw rejected
SqlDraft, không bật prompt/SQL logging production. Accepted synthetic evidence lưu private.

## C. Root-cause closure so với Gate D

Gate D cũ có K2/K3/KH `count_star_alias`, G3 `count_column_alias`, GH
`generator_unsupported`. Không có raw rejected drafts để chứng minh biểu thức SQL cũ.

Bản deploy trước Batch A đã sửa COUNT-order bằng exact AST matching: khi COUNT đã được
SELECT với alias hợp lệ, ORDER BY cùng aggregate được tham chiếu qua alias; không sửa
SELECT metric, JOIN keys, WHERE, GROUP BY, NULL semantics hoặc grain.

Batch A chứng minh **K2/K3/G3 hiện tại chạy được end-to-end trên câu hỏi đã chốt**, và
regression độc lập chứng minh COUNT-order equivalent cases chạy đúng PostgreSQL.
Không chứng minh mọi lỗi cũ do ORDER BY; không thể xác định normalization đã kích hoạt
trong mỗi raw live draft vì không có instrumentation/capture được duyệt. Final SQL
không đủ để tái dựng raw draft trước normalization. KH/GH chưa được live kiểm lại.

## D. Cross-domain offline evaluation

Fake gateways chỉ trả scripted draft/decision/answer; DB/executor/context/guards thật.
Không dùng API keys/provider network. Oracles lấy từ fixture business facts qua PostgreSQL
VALUES aggregation độc lập, không lấy generated SQL làm expected.

| Domain | 1 bảng | 2 bảng | 3 bảng | Security | Oracle | Live provider |
|---|---|---|---|---|---|---|
| Giao vận | PASS | PASS | Chain PASS | PASS scoped negatives + common suite | Exact PASS | K2/K3 Knowledge, G3 Gemini PASS |
| Học phí | PASS | PASS | Chain PASS | PASS scoped negatives + common suite | Exact PASS | NOT RUN |
| Bán hàng | PASS | PASS | Chain PASS | PASS scoped negatives + common suite | Exact PASS | NOT RUN |
| Nhân sự | PASS | PASS | Chain PASS | PASS scoped negatives + common suite | Exact PASS | NOT RUN |
| Năng lượng | PASS | PASS | Chain PASS | PASS scoped negatives + common suite | Exact PASS | NOT RUN |
| Bảo trì holdout | PASS | PASS | Star PASS | PASS scoped negatives + common suite | Exact PASS | NOT RUN |

Mỗi domain có 6 golden positives cho mỗi mức 1/2/3 bảng (3 seeds × 2 fake model IDs),
4 context-permutation positives cho 3 bảng, cùng RAG/Hybrid/unsupported cases. Không
khẳng định chain lẫn star đã chạy riêng trên mọi domain: star golden là maintenance;
common PostgreSQL suite có thêm star và equivalent reverse-order cases.

### Test results mới của lượt này

| Test module | PASS |
|---|---:|
| test_join_domains_integration.py | 144 |
| test_count_order_integration.py | 24 |
| test_count_order_edges_integration.py | 6 |
| test_join_counterexamples_integration.py | 8 |
| test_three_table_join_integration.py | 35 |
| test_sql_timezone_integration.py | 40 |
| test_sql_generation_contract.py | 37 |
| test_sql_draft_adapters.py | 4 |
| test_relationship_detection.py | 21 |
| test_join_policy.py | 57 |
| **Lượt regression đầu** | **376 / 376, 69.88s** |
| test_context_permutations_integration.py (mới) | **24 / 24, 8.78s** |
| **Tổng distinct tests** | **400 PASS; 0 FAIL; 0 skipped** |

24 tests mới đã chạy lại sau chỉnh format/import fixture; không cộng trùng lần chạy trước.
Ruff `check backend/app backend/scripts backend/tests`: PASS.
Không chạy lại toàn bộ 635 unit/558 integration hoặc frontend 66 unit/105 mock UI;
đó là baseline trước deploy, không gộp vào 400 tests mới. Không chạy CI trong lượt này.

### Coverage và giới hạn phép đo

- CSV/XLSX, upload/row order seeds 0/7/19, random physical IDs, display/source labels khác
  SQL identifiers; Vietnamese accented headers và English headers giữ trong context.
- Test mới: sáu domain × hai fake model IDs × hai column orders; đảo table order và
  thêm **hai** unrelated tables. Context giữ đủ columns/edges; từng unrelated target
  vẫn bị `join_relationship` chặn. Không thêm edge dựa trên columns giống nhau.
- SUM/AVG/COUNT(*)/COUNT(column), non-NULL count khác row count, numeric FK không phải
  measure, repeated COUNT ORDER BY/quoted aliases/ASC/DESC/LIMIT, requested filters.
- Verified manual và automatic relations; thiếu/ambiguous keys, mismatched types,
  NULL keys, duplicate target keys/orphans không tự kích hoạt quan hệ.
- Duplicate entity names nhưng khác ID, exact Decimal/zero/all-NULL/empty aggregates,
  BIGINT vượt JS-safe range, timestamp và biên tháng Việt Nam.
- Sai key, dimension SUM/AVG, label-only grain, cross-workspace/owner, stale/deleted
  relation, fanout/two-fact graph, DML/multi-statement/catalog/function abuse bị chặn.
  Common adversarial pipeline suite assert executor và answer gateway không được gọi.
- SQL/RAG/Hybrid fake-provider contracts, Guest isolation, authenticated API history,
  CSRF 403 và wrong-owner 404 được chạy trên DB test. **Không dùng fake auth đó trên main**.
- Domain fixtures dùng câu hỏi tiếng Việt; fake gateway không tự hiểu câu hỏi. Chưa đo
  live paraphrase accuracy hay tỷ lệ provider tự chọn đúng schema ở domain khác.
- SQL SUBSET unsupported cases PASS nghĩa là từ chối đúng, không phải hỗ trợ tính năng đó.

### PostgreSQL test và cleanup

Trước tạo đã kiểm inventory: không có PostgreSQL test phù hợp, hai container 15437/15438
cũ không còn. Tạo duy nhất `shopquery-ai-batch-a-crossdomain-test`, full ID:

`9749252b1c632f0810c952e94ab862e26a0e3f6d4d69b8005a21d62294242fea`.

DB `shopquery_test_batch_a_crossdomain`, loopback port **15439**, pgvector image có sẵn,
Mounts=[], tmpfs `/var/lib/postgresql/data`; không main volume/bind/network dependency.
Test safety xác minh explicit setup URL/DB name khác main trước fixtures; keys/endpoints
rỗng, provider gates trong **test process** tắt, reader role read-only. Không sửa `.env`.

Sau tests kiểm lại full ID/name/test label/mounts, stop bình thường (exit 0), rồi `docker rm`
đúng full ID, không force/prune/volume flags. Chỉ dữ liệu synthetic disposable trong
container mới bị loại bỏ; không thể khôi phục cùng container ID, có thể tái tạo fixtures.
JUnit/output nằm ngoài Docker và được giữ. Không tác động tài nguyên dự án khác.

## E. Source generalization findings

| Câu hỏi audit | Phân loại | Kết luận có bằng chứng |
|---|---|---|
| Có hardcode logistics trong product logic? | REFUTED trong modules đã review | tai_xe_id/kho_id/fee chỉ thuộc fixtures; dynamic context dùng registry/verified metadata. Demo store default riêng, không thay upload context. |
| Prompt examples gây bias domain? | SUSPECTED / UNKNOWN về mức ảnh hưởng | Router có nhiều domain examples; context chọn numeric measure đầu tiên làm syntax example, có disclaimer. Chưa đo độ lệch provider bằng live holdout, không patch theo phỏng đoán. |
| Root từ metadata hay vị trí FROM? | CONFIRMED | resolve_join_tree và ApprovedJoin xác định fact; reverse INNER JOIN chỉ canonicalize khi graph/key/subset đúng, không coi tên bảng là bằng chứng grain. |
| COUNT aliases thống nhất? | CONFIRMED | fact_row_count/matched_row_count cho fact rows, fact_value_count cho non-NULL fact values; dùng chung mọi domain, có exact COUNT-order tests. |
| Autolink naming có giới hạn? | CONFIRMED | Cần explicit *_id/*_code TEXT/BIGINT, normalized target entity label khớp prefix; descriptive labels không khớp phải manual. Không fuzzy-map hoặc suy ra từ trùng values; ambiguous/1:1 không tự chọn fact direction. |
| Guard nào phải giữ? | CONFIRMED | Owner/workspace/schema allowlist, verified revision/cardinality, exact ON equality, SELECT-only, max ba bảng/hai edges, root fact measure, GROUP BY dimension ID, execution-time recheck/timeout/row cap. |
| SQLGlot normalization phụ thuộc tên logistics? | REFUTED | AST/metadata/alias rules chung; six-domain PostgreSQL COUNT-sort regressions PASS. |
| Unrelated tables làm cấp edge mới? | REFUTED trong cases đã test | Metadata vẫn có mặt để generation chọn nguồn; approved_joins không tăng, unauthorized edge bị chặn trước executor. Có regression nhiều bảng phụ/cột đảo. |
| Answer có thể sai entity grain? | CONFIRMED đã có counterexample SQL; guard hiện chặn | Label-only GROUP BY gộp entity trùng tên được tái hiện PostgreSQL; join_grain guard bắt thiếu ID. Narrative của model vẫn có rủi ro ngoài kiểm soát SQL; ba live answers lần này đúng, không phải bảo đảm mọi answer. |
| Dataset mới không có domain SQL template hoạt động? | CONFIRMED offline subset; UNKNOWN live accuracy | Schema/header/types/approved edges truyền động, sáu schemas chạy được pipeline. Không suy rộng fake drafts thành năng lực Knowledge/Gemini tự sinh SQL cho mọi upload. |

Giới hạn cần giải thích cho người dùng: không arbitrary JOIN/many-to-many/fanout/cycle,
không >3 bảng, không chọn path mơ hồ, không aggregate dimension hay aggregate arithmetic,
không nhóm thuộc tính chung bỏ entity ID khi chưa có grain contract riêng. Thiếu quan hệ
được verified phải fail closed; upload không bảo đảm luôn tự gán quan hệ cho mọi naming.
Không phát hiện bug production mới đủ bằng chứng cần thay đổi trong task này.

## F. Post-test integrity và Git

Protected scope lấy **đúng 26 bảng** từ Gate D evidence, loại auth/session/oidc tables;
không suy đoán danh sách mới. Scoped dataset/registry/docs/history loại workspace 13
theo đúng baseline trước; operational counters/leases và Google session lifecycle không
thuộc immutable business fingerprint. Không đọc private conversation contents để hash.

Aggregate SHA-256 của map 26 bảng (count + server-side row SHA-256):

```text
Trước: f73b828698b29380b28b5ae89a654df52115bef858ed7a4c246a2b11c84fa736
Sau:   f73b828698b29380b28b5ae89a654df52115bef858ed7a4c246a2b11c84fa736
```

26/26 count và hash khớp fresh baseline lẫn historical evidence; không ngoại lệ drift.
Ba synthetic tables giữ nguyên row hashes/counts; hai relationships giữ nguyên revisions,
verification statistics và mapping. Có đúng **3 user + 3 assistant messages mới**, không
error messages, owner đúng. Giữ nguyên ba conversations và quota effects; không cleanup
history/reset quota/restore. Không fingerprint auth/session tables hoặc tuyên bố toàn DB
byte-for-byte bất biến từ row hashes có scope.

API/web/DB full IDs/images không đổi, RestartCount=0; source 71 modules và environment
digest không đổi sau tests; vẫn ba services main healthy, không còn container test mới.

**File mới trong repository do lượt này tạo**:

- `backend/tests/test_context_permutations_integration.py`: regression context order/
  unrelated schemas cho sáu domain, chỉ test, không ảnh hưởng production modules.
- `docs/archive/2026-10/text_to_sql_batch_a_live_and_generalization.md`: báo cáo này.

Không sửa thêm bốn production files đang dirty từ task trước: datasets/context.py,
text_to_sql/generator.py, join_policy.py, validator.py. Giữ nguyên docs/tests/handoff và
Hybrid changes chưa commit khác. Không stage, commit, push; không có SHA/CI mới để báo PASS.
`git diff --check` PASS. Thay đổi mới chỉ test/docs, không có production patch NOT DEPLOYED.

Private evidence (không đưa raw synthetic rows/SQL/prompts vào report/Git):
`C:\Work\ShopQuery-Backups\batch-a-20261021\` chứa protected-before/after,
preflight/oracle/synthetic-after/runtime-after, budget ledger, per-case response/
verification/safe diagnostics/screenshots và hai JUnit reports. Helpers private chỉ
read-only main hoặc chạy synthetic fixtures trên DB test, không gọi provider.

## G. Trạng thái cuối

**BATCH A LIVE PASSED** — cụ thể **FOR LOGISTICS TEST MATRIX**.

**CROSS-DOMAIN OFFLINE VERIFIED** trong supported subset đã kiểm thử.

**CROSS-DOMAIN PROVIDER LIVE NOT VERIFIED** ở các lĩnh vực còn lại.

Ba live successes không đo được repeatability, paraphrase coverage, larger schemas,
provider variance hoặc độ chính xác mọi dataset. Không tuyên bố “ổn định hoàn toàn”.

## H. Bước tiếp theo — CHƯA THỰC HIỆN, cần phê duyệt mới

### Batch B Hybrid riêng

KH/GH trên synthetic 13 và policy synthetic hiện có, Knowledge + Gemini: tối đa **2
chats / 8 logical generation stages / 2 query embeddings**, không document ingestion.
Chốt lại nguyên văn câu hỏi/document oracle trước khi gửi; SQL rows phải so oracle và
kết luận/citations phải khớp rule. Dừng lỗi đầu tiên, không retry. Đây chỉ là đề xuất,
không tận dụng phần ngân sách Batch A đã dùng hết.

### Cross-Domain Live Holdout Acceptance riêng

Đề xuất hai schemas không phải logistics từ `tests/join_domains.py`, seed 19:

1. Học phí: courses → students → payments theo chiều quan hệ payments → students → courses.
   Câu hỏi: **“Theo từng khóa học, cho biết course_id, course_title, tổng amount_paid và
   số dòng payments. Phân biệt khóa học theo ID; giữ kết quả NULL và 0 đúng dữ liệu.”**
2. Nhân sự: departments/employees/work_logs, root work_logs.
   Câu hỏi: **“Theo từng phòng ban, cho biết department_id, department_name, tổng hours,
   trung bình hours và số dòng work_logs. Phân biệt phòng ban theo ID; không coi khóa
   ngoại là giờ làm.”**

Mỗi câu chạy Knowledge và Gemini: tổng **4 chats / tối đa 12 logical generation stages /
0 embeddings**; SDK requests có thể nhiều hơn. Provider tự sinh SQL, không scripted draft.
Xin quyền riêng tạo hai synthetic workspaces/upload CSV-XLSX và verified relations trên
main; hiện chưa tạo. Trước live tạo independent PostgreSQL VALUES oracle và hashes theo
fixture, kiểm đúng IDs/SUM/AVG/COUNT/all-NULL/zero. Dùng real Google session, không fake auth.

Chạy tuần tự, dừng ở lỗi đầu tiên (owner/relationship/provider/validator/rows/answer/history/
integrity/fallback), không extra probes/retry. Giữ guards và fingerprint scope được duyệt;
không template domain trong product, không tự đổi model hoặc deploy. Chỉ sau nghiệm thu
này mới có thêm bằng chứng provider hiểu schema ngoài logistics, chưa đủ bảo đảm mọi lĩnh vực.
