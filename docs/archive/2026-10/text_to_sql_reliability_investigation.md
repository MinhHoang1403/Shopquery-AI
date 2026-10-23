> HISTORICAL snapshot. Current architecture/status: [Stage 1 report](../../stage1_implementation_report.md).

# Điều tra độ tin cậy Text-to-SQL / JOIN

Ngày: 21/10/2026. Workspace: `C:\Work\ShopQuery AI`.

Trạng thái: **OFFLINE/POSTGRESQL VERIFIED; LIVE NOT RUN; CHƯA DEPLOY 8080**.

## A. Executive findings

### A1. Kết luận quan trọng nhất

Có một lỗi false refusal tái hiện được trong validator: một COUNT hợp lệ ở SELECT,
đã có alias đúng, vẫn bị từ chối khi lặp lại chính COUNT đó trong ORDER BY.

```sql
-- Tất cả tên và dữ liệu trong ví dụ này là synthetic.
SELECT s.student_id, s.name, COUNT(*) AS fact_row_count
FROM uploaded_data.payments AS p
INNER JOIN uploaded_data.students AS s ON p.student_id = s.student_id
GROUP BY s.student_id, s.name
ORDER BY COUNT(*) DESC NULLS LAST;
```

PostgreSQL chấp nhận; kết quả giống `ORDER BY fact_row_count DESC NULLS LAST`.
Validator baseline lại báo `join_aggregate/count_star_alias` cho COUNT ở ORDER BY:
parent AST của COUNT này là `Ordered`, không phải `Alias`. COUNT(column) gặp lỗi
tương tự, với `count_column_alias`, dù SELECT dùng `fact_value_count` đúng.

Do đó **mã lỗi Gate D không chứng minh alias sai nằm ở SELECT**. Nó cũng chưa chứng minh
provider sinh sai yêu cầu nghiệp vụ. Không có rejected SqlDraft của Gate D để khẳng định
năm lỗi live là trường hợp ORDER BY này. Đây là lỗi ứng dụng độc lập đã chứng minh,
không phải việc khôi phục lại raw SQL lịch sử bằng suy đoán.

### A2. Những phát hiện khác

- CONFIRMED: routing context chứa cả chỉ dẫn dựng SQL, pair examples và FROM/JOIN fragments.
  Ranh giới router/generator đã bị trộn khi thêm relationships. Đã tách lại, giữ nguyên
  schema, source headers, document capability, approved equalities và root fact.
- CONFIRMED: description của `SqlDraft.sql` chỉ nói phải là SELECT, trong khi refusal
  contract yêu cầu chuỗi rỗng. Đã đồng bộ description và prompt success/refusal.
- CONFIRMED về thiếu instruction: SQL generator nhận câu hỏi Hybrid trước retrieval nhưng
  chưa giải thích rõ việc xử lý điều kiện tài liệu ở giai đoạn synthesis. Đã làm rõ ranh giới.
  **Chưa chứng minh** thiếu instruction này gây `generator_unsupported` của Gemini Gate D.
- REFUTED đối với Gate D: không thể mặc định lỗi do thiếu bảng/relationships; diagnostics
  đã ghi đủ ba bảng/hai edges cho cả tám lượt. Router chọn đúng nhánh trước các lỗi.
- UNKNOWN: chính xác SQL/alias/ý định nội bộ của provider trong năm lượt thất bại;
  độ cải thiện generation của hai model sau thay đổi prompt.

### A3. Những gì không thay đổi

Không gọi provider/embedding live; không dùng lại ngân sách Gate D. Không kết nối database
main để chạy test. Không build/restart/deploy main, migration, seed main, restore, re-ingest,
đổi model/key/gates/quota, OAuth, volume, VPS hoặc tracing. Không commit/push.

Working tree ban đầu có `docs/archive/2026-10/sql_join_root_cause_audit.md` đang sửa và `handoff.md`
chưa tracked. Giữ nguyên hai file đó. HEAD vẫn là
`e2151a3d6b37f3a11e83f68553e5985bbe087deb`; code baseline là
`50d7bac4e1f6af8adffeb8f317a458f637de7bb0`.

### A4. Vì sao những lần sửa trước chưa đủ?

Các bản sửa trước xử lý những lỗi khác nhau: hướng INNER JOIN, COUNT row/value aliases,
auto relationships, graph ba bảng, entity ID grain và DOCX evidence. Không phải tất cả
refusals cùng một nguyên nhân. Guard entity-ID được siết về sau cũng làm các live cases
cũ trước hardening không còn là bằng chứng nghiệm thu runtime mới.

Blind spot cụ thể vừa tìm được là tests có COUNT ở SELECT và ORDER BY output alias, nhưng
chưa có cùng COUNT lặp trong ORDER BY. Mã lỗi alias không chỉ rõ clause nên rất dễ quy
nhầm thành model đặt sai SELECT alias. Fake model tests chỉ trả drafts đã định trước;
chúng không chứng minh mọi cách sinh SQL của Knowledge/Gemini tuân thủ contract. Patch này
bổ sung đúng biến thể còn thiếu, không tuyên bố giải thích toàn bộ lịch sử lỗi hoặc hoàn
tất live acceptance chỉ nhờ tests xanh.

## B. End-to-end audit

### B1. Call flow và trách nhiệm

```text
App.submitQuestion(question, captured model, dataset)
  -> authenticated chat/conversation API hoặc Guest worker
  -> authentication + CSRF + owner/dataset binding
  -> registry metadata + approved revisioned relationships
  -> DatasetSqlContext
  -> ModelChatService: selected gateway, bounded whole-turn fallback contract
  -> QueryRouter: route + available capabilities, không dựng SQL
     SQL: SqlGenerator -> SqlDraft -> parse/table/column checks
          -> approved JOIN/tree + aggregate + entity-grain validation
          -> narrow equivalent normalization + object/function/column revalidation
          -> owner/revision execution guard -> read-only PostgreSQL -> grounding
     RAG: scoped retrieval -> grounded answer + validated chunk IDs
     HYBRID: SQL pipeline trước -> retrieval sau -> synthesis trên cả hai evidence sets
  -> response/model attribution -> owner-scoped history -> UI/evidence rendering
```

Không có query intent IR riêng hoặc agent: natural language được router phân tuyến, sau đó
LLM sinh SqlDraft từ câu hỏi và request-local metadata. Backend xác định allowed objects,
approved edges, root fact và các invariants; không suy diễn metric thay người dùng.

### B2. Mười lăm câu hỏi audit

| Câu hỏi | Bằng chứng source và kết luận |
|---|---|
| 1. Hiểu yêu cầu tự nhiên? | `text_to_sql/generator.py:31` nhận câu hỏi hiện tại + schema + ngày tham chiếu. Các fake drafts kiểm chứng contract, không đo khả năng hiểu ngôn ngữ của model. UNKNOWN với các rejected drafts lịch sử. |
| 2. Router SQL/RAG/Hybrid? | `routing/router.py:28`, `routing/service.py:100`: enum + available routes, không keyword routing. Gate D chọn đúng 8/8 trước refusal. Các tests scripted không phải accuracy router live. Context boundary bug đã sửa. |
| 3. Dataset/owner? | `dependencies.py:69`, `RelationshipRepository.approved/execution_guard`, API/auth dependencies: context của dataset đã owner-bound; không tự chọn workspace khác. Wrong-owner/foreign-workspace tests giữ fail-closed. |
| 4. Headers/identifiers? | Parser giữ `ColumnSpec(source_name,name,data_type)`; registry lưu random physical table name. Context phân biệt display/file name với identifier. Auth và Guest cùng builder, không SQL bằng display label. |
| 5. Types/NULL/Decimal/time? | `datasets/parser.py`, `text_to_sql/executor.py:21/53`, schema/generator date rules: NULL khác zero, NUMERIC và BIGINT lớn serialize losslessly; executor đặt Asia/Ho_Chi_Minh. Không đổi inference hoặc timestamp dữ liệu. |
| 6. Quan hệ? | `relationship_detection.py:69`, `relationships.py:113`, `relationship_repository.py:72/122/210`: auto candidate theo metadata + kiểm chứng types/cardinality/keys; ambiguous/manual vẫn cần xác nhận. Không phải mọi cặp cùng tên cột được auto-approve. |
| 7. Fact root/graph? | `join_policy.py:56/90`: đúng hai edges, ba bindings, một root; chain/star, không hai facts qua dimension. Two-table root là approved source, không vị trí FROM do model chọn. |
| 8. Prompt mâu thuẫn/dài? | Context trộn nhiệm vụ router là CONFIRMED. Pair fragments của intermediate dimension có thể gây chú ý sai nhưng đã có root-tree instruction; ảnh hưởng model là SUSPECTED. Không pruning schema khi chưa có bằng chứng. |
| 9. Hai structured adapters? | Cùng Pydantic SqlDraft và generator. Knowledge dùng strict JSON schema; Gemini dùng response_schema. JSON wire format khác nhau nhưng cả success/refusal được mock HTTP test qua adapter thật. Không chứng minh upstream tuân thủ schema live. |
| 10. False syntax refusal? | COUNT trong ORDER BY là CONFIRMED, đã có PostgreSQL differential proof. Parent-Alias check áp cho tất cả AggFunc làm nhầm projection alias với aggregate ở clause khác. |
| 11. Cú pháp đúng nhưng nghiệp vụ sai? | Label-only grouping gộp distinct IDs, COUNT(nullable) khác COUNT(*), dimension SUM gây nhân grain. Existing counterexample/oracle tests tái kiểm tra; không nới các guard này. Validator không thể chứng minh mọi SQL hiểu đúng câu hỏi. |
| 12. Hybrid thiếu policy? | `routing/hybrid.py:42`: retrieval sau SQL; generator chưa được đọc policy. Đã bổ sung instruction SQL-evidence-only, không bịa threshold; causal explanation cho refusal Gemini vẫn UNKNOWN. |
| 13. unsupported_reason? | Nonempty reason trong SqlDraft làm generator ném `generator_unsupported`; frontend nhận refusal ngắn, không raw reason. Empty SQL không reason vẫn bị SQL-empty validator, không sinh kết quả giả. |
| 14. Grounding/count aliases? | `text_to_sql/pipeline.py:58`, `routing/hybrid.py:42` giải thích fact rows/non-NULL values/không phải dimension entities. SQL rows giữ Decimal/null/zero. Fake gateway xác nhận evidence, không bảo đảm diễn đạt model thật. |
| 15. Auth/Guest/provider differences? | Auth registry random names + bounded categorical hints + DB owner guard + persistent conversation; Guest TEMP tables, file/session scope và memory chunks, không cùng durable history. Provider/model attribution/fallback là lớp độc lập, không sửa. |

### B3. Các ranh giới đã đối chiếu thêm

- `frontend/src/App.tsx:247` chụp model của request, không dùng model đổi giữa lúc chờ response;
  đổi dataset bắt đầu conversation mới; response rendering không tự chế SQL results.
- `frontend/src/api.ts`, `ChatMessage.tsx`, `ResponseEvidence.tsx`: hiển thị route, actual model,
  bảng/SQL/citations từ response. Không thay API shape/UI trong patch này.
- `api/routes.py:205/226`, `conversations/repository.py:159/189`: lưu user turn và structured
  response, gồm refusal/model/evidence. Persistence không đồng nghĩa gửi toàn bộ history cho
  generator: hiện mỗi lượt AI vẫn dựa câu hỏi hiện tại; câu hỏi đại từ/tiếp nối có giới hạn.
- Relationship revisions và shared workspace lock được giữ trong cửa sổ guard/execution.
  Không có việc sửa COUNT làm bỏ qua lock hoặc kiểm tra owner/revision.
- RAG retrieval owner/dataset-scoped; IDs phải thuộc chunks thực nhận. Hybrid không chạy
  retrieval khi SQL bị từ chối, giải thích vì sao Gate D Hybrid có 0 query embedding.
- Lịch sử DOCX parser bỏ table đã được sửa ở baseline; không re-ingest tài liệu cũ trong lượt này.

## C. Root-cause evidence matrix

| Issue | Evidence / reproduction | Root cause / affected code | Status |
|---|---|---|---|
| COUNT(*) ở ORDER BY bị từ chối | Test 2/3 bảng; SELECT có fact_row_count/matched_row_count; SQL PostgreSQL chạy đúng | `_validate_join_aggregates` duyệt mọi AggFunc và đòi parent Alias, kể cả Ordered | CONFIRMED, fixed offline |
| COUNT(nullable measure) ở ORDER BY bị từ chối | SELECT fact_value_count đúng; ORDER BY cùng COUNT; exact oracle giữ NULL vs count rows | Cùng lỗi clause/parent; không phải COUNT(column) tự nhiên luôn sai | CONFIRMED, fixed offline |
| Router nhận SQL instructions | Capture prompt qua builder thật với 1/2 approved edges | `build_dataset_sql_context` trả source_context đã append examples làm routing_context | CONFIRMED, fixed boundary; live effect UNKNOWN |
| Schema description của refusal không nhất quán | JSON schema description yêu cầu SELECT, refusal prompt yêu cầu sql rỗng | `SqlDraft` field metadata và generate prompt | CONFIRMED, aligned; live effect UNKNOWN |
| Hybrid missing-policy refusal | Fake draft reason không rỗng tái hiện đúng failure trước execution/retrieval; inspect SQL-first pipeline | Chưa có instruction rõ giữa SQL evidence và unretrieved policy | Instruction gap CONFIRMED; nguyên nhân Gemini Gate D UNKNOWN |
| Thiếu metadata ở Gate D | Bằng chứng Gate D đủ 3 bảng/2 edges cả 8 lượt | Không phù hợp dữ kiện mới nhất | REFUTED trong Gate D, không loại trừ schema lỗi ở workspace khác |
| Sai router là nguyên nhân 5 lỗi Gate D | 6 SQL và 2 Hybrid đã chọn đúng nhánh | Refusal ở generator/validator, trước executor | REFUTED trong Gate D |
| Provider/model/fallback sai | Actual model đúng, fallback false trong Gate D; adapter/attribution regression | Không có bằng chứng provider bị tráo | REFUTED trong Gate D |
| Quá nhiều schema khiến model sai | 3 bảng/2 edges, context measured nhưng không có ablation live | Attention/relevance có thể ảnh hưởng; physical random names khó hơn readable names | SUSPECTED; không pruning/đổi model |
| matched_row_count làm model lẫn grouped count | Scalar contract khác fact_row_count; validator chấp nhận row-count aliases có cùng nghĩa đếm dòng | Không thu được rejected draft để truy nhân quả | SUSPECTED, không đổi tên API/semantics |
| Label-only entity grouping | PostgreSQL counterexample distinct IDs trùng tên; existing tests | Group key phải chứa verified entity ID | CONFIRMED trước patch, guard giữ nguyên |

Các line chính của bản sửa: `datasets/context.py:87/107/167/241`,
`text_to_sql/generator.py:10/31`, `join_policy.py:216/348`, `validator.py:111`.
Line có thể đổi nếu chỉnh source tiếp; function name là anchor ổn định.

### C1. Phân biệt các COUNT

| SQL | Nghĩa và điều kiện |
|---|---|
| COUNT(*) AS fact_row_count | Đếm mọi matched root fact row, kể cả measure NULL/zero. |
| COUNT(*) AS matched_row_count | Cùng phép đếm dòng, dùng chẩn đoán scalar SUM/AVG rỗng/all-NULL; không tự thay metric. |
| COUNT(f.measure) AS fact_value_count | Đếm giá trị fact không NULL, không phải số giao dịch. |
| COUNT(f.approved_join_key) AS fact_row_count | Baseline đã chứng minh INNER equality loại NULL key; chuẩn hóa sao chỉ cho verified key. Patch này không mở rộng quy tắc đó. |
| COUNT(f.non_key) AS fact_row_count | Vẫn từ chối, kể cả sample nhìn như không NULL. |
| COUNT(dimension.column), SUM/AVG(dimension) | Vẫn ngoài root-fact aggregation contract. |

Zero không phải NULL. SUM/AVG của nhóm all-NULL vẫn NULL. Group ID không được suy từ tên.
Không tự thêm ID vào GROUP BY hoặc đổi COUNT(nullable column) thành COUNT(*).

### C2. Chứng minh normalization hẹp

Gọi E là COUNT trực tiếp trong SELECT, alias a duy nhất trong output. Theo PostgreSQL,
`ORDER BY E` và `ORDER BY a` tham chiếu cùng giá trị của từng output row khi a được định nghĩa
chính bằng E. AST matcher yêu cầu `projection.this == ordered.this`, không đoán theo tên.

Patch chỉ thay `Ordered.this` bằng copy của alias Identifier của projection. Giữ nguyên
DESC/ASC, NULLS, các sort keys khác, LIMIT, SELECT, GROUP BY, WHERE, ON và bindings.
Duplicate alias bị chặn (kể cả alias trùng tên cột không có AS). Quoting giữ nguyên;
quoted uppercase identifiers vẫn bị contract hiện có từ chối. Không bật optimizer tổng quát.

Sau rewrite, SELECT aggregate còn nguyên và phải qua đầy đủ fact/key/type/count/grain guards;
tables/functions/columns còn được kiểm tra lại cho cả hai và ba bảng. Execution guard vẫn chạy.

Không normalize COUNT trong HAVING, aggregate không có projection tương ứng, DISTINCT,
COUNT trong arithmetic, alias sai hoặc COUNT khác projection. Những trường hợp đó tiếp tục
fail-closed. Không diễn giải lại câu hỏi để ép SQL thành công.

## D. Research review — nguồn gốc và quyết định

Đọc methodology/implementation/evaluation gốc, không lấy benchmark accuracy làm ShopQuery
accuracy. Nội dung dưới đây là tổng hợp ngắn; cột áp dụng là đánh giá cho repository này,
không phải kết luận của tác giả paper về ShopQuery.

| Method / nguồn gốc | Vấn đề / bằng chứng paper hoặc implementation | Phù hợp ShopQuery? | Chi phí/rủi ro | Quyết định |
|---|---|---|---|---|
| [CHESS, §3.1](https://arxiv.org/html/2405.16755v3) | Tách retrieval, schema selection, candidate generation, verification; selector phải cân bằng precision/recall ở schema lớn | Hữu ích về boundary và verification, chưa chứng minh cần prune context 3 bảng | Nhiều calls, privacy/cost, bỏ nhầm edge; framework mới ngoài phạm vi | Chỉ áp dụng nguyên tắc stage ownership + test oracle; không multi-agent/pruning/candidate loop |
| [RESDSQL](https://ojs.aaai.org/index.php/AAAI/article/view/26535), [implementation](https://github.com/RUCKBReasoning/RESDSQL/blob/main/text2sql_data_generator.py) | Ranking schema tách khỏi skeleton/SQL decoding; code giữ original identifiers, có tùy chọn FK và schema noise | Registry và typed metadata hiện có làm phần deterministic linking; IR mới chưa có benchmark lợi ích | Training/ranker/IR thêm lỗi và bảo trì | Giữ metadata đầy đủ, test rename/order; không thêm IR/LLM call |
| [DIN-SQL, §4](https://arxiv.org/html/2304.11015v3) | Schema linking, classification/decomposition, generation, self-correction; nested và non-nested khác nhau | Tách routing facts khỏi generation rules; sửa đúng stage | NatSQL/new pipeline và self-correction nhiều calls; có thể đổi ý nghĩa | Không copy repair loop; chỉ canonicalize equivalence có proof |
| [PICARD, §2](https://aclanthology.org/2021.emnlp-main.779.pdf) | Incremental parsing/guards lọc token hypotheses khi decode | Tư tưởng syntax/scope guard phù hợp; API hiện tại không cung cấp vòng token logits để gắn PICARD trực tiếp | Đổi decoding/model ngoài scope; syntax valid chưa chứng minh business grain | Giữ post-generation AST + independent semantic oracle |
| [Spider 2.0, §2–3 và Appendix A](https://arxiv.org/html/2411.07763v1) | Enterprise workflow, metadata/documents/dialects, evaluation execution-focused; agentic và SQL-only là hai setting khác | Nhắc phải kiểm chứng actual execution và metadata mapping, không chỉ generated string | Benchmark lớn không cùng subset/quyền của ứng dụng | Dùng local scoped oracle; không triển khai Spider-Agent hoặc DDL workflows |
| [BIRD, §3, §5](https://arxiv.org/html/2305.03111v3) | Values, noisy data, external knowledge; EX so kết quả thực thi; VES chỉ có nghĩa trên SQL trả đúng | Kiểm chứng values/NULL/types/filtered results và policy evidence | Một DB có thể che sai semantics; EX không là proof tổng quát | So exact IDs/rows/Decimal/counts và thêm counterexamples, không tối ưu VES trước correctness |
| [Dr.Spider, §3](https://arxiv.org/html/2301.08881v1), [code](https://github.com/awslabs/diagnostic-robustness-text-to-sql) | Perturbations DB/NL/SQL; paraphrase cần kiểm tra không đổi nghĩa | Schema/row/upload/alias/JOIN-order metamorphic fixtures phù hợp | Fake paraphrases không đo được hiểu tiếng Việt của model thật | Kiểm chứng application invariants offline; live robustness vẫn NOT RUN |
| [Distilled test suites](https://aclanthology.org/2020.emnlp-main.29.pdf) | Một DB denotation có false positives; nhiều fixtures phân biệt neighboring wrong queries tốt hơn exact SQL string | Independent fact-only VALUES oracle, NULL/duplicate-name/key mutations | Finite suite vẫn là approximation, không proof mọi dữ liệu | Dùng differential + counterexamples; không tự nâng sample size bằng đếm trùng |
| [PostgreSQL 17 aggregates](https://www.postgresql.org/docs/17/functions-aggregate.html), [table expressions](https://www.postgresql.org/docs/17/queries-table-expressions.html), [ORDER BY](https://www.postgresql.org/docs/17/queries-order.html) | COUNT rows vs non-NULL; GROUP BY identity; sort biểu thức hoặc output label và output-name precedence | Nền tảng proof COUNT ORDER rewrite và guard giữ NULL/grain | Hiểu sai alias scope sẽ đổi nghĩa | Chỉ exact projection match + unique output alias; PG differential tests |
| [SQLGlot 29.0.1 qualify source](https://github.com/tobymao/sqlglot/blob/v29.0.1/sqlglot/optimizer/qualify.py) | Qualify thực hiện nhiều rewrites: alias/star expansion, identifiers/table qualification | AST copy/equality phù hợp normalizer hẹp | Bật qualify/optimizer tổng quát có thể đổi scope/casing | Không gọi optimizer; chỉ mutate Ordered.this và revalidate |

Không thêm dependency từ research. Không gửi dữ liệu hoặc prompt workspace vào dịch vụ nghiên cứu.
Các số liệu benchmark trong paper không được sao chép thành kết quả ứng dụng.

## E. Design decision

| Option | Correctness / false refusal / unsafe acceptance | Complexity, size, calls, latency/quota | Maintenance / domain / adapters | Quyết định |
|---|---|---|---|---|
| A. Contract alignment | Sửa mâu thuẫn schema và phân công Hybrid; chưa có live false-refusal measurement; không thay guard | Nhỏ, prompt tăng một đoạn; 0 call mới, latency chưa đo | Chung hai providers, không domain-specific | Chọn mô tả success/refusal và SQL evidence boundary |
| B. Typed semantic intent/IR mới | Có thể tách COUNT rows/value/grain nhưng chưa có evidence model dùng đúng IR | Thêm schema/stage hoặc training; call/maintenance có thể tăng | Cần benchmark riêng trên hai adapters và holdout | Chưa triển khai; cần quyết định kiến trúc riêng |
| C. Deterministic SQL construction | ON metadata đúng nhưng không được backend đoán metric/group/filter thay NL | Thêm compiler/intent contract; rủi ro silently repair | Backend metadata đã có, chưa có đủ typed intent | Không dựng lại query/khóa/GROUP BY |
| D. Narrow AST normalization | Giảm false refusal đã tái hiện; exact expression/unique label giữ semantics; negatives không mở rộng | 27 dòng helper + common revalidation; 0 LLM call | Ít, dùng SQLGlot hiện có; không domain/provider-specific | Chọn riêng COUNT ORDER BY khớp SELECT |
| E. Context presentation | Trả router về facts đúng nhiệm vụ; không thay schema set hoặc authorized edges | Router context giảm đo được; SQL context không prune | Chung auth/Guest builder; model accuracy chưa đo | Chọn tách rules/examples khỏi router; không schema retrieval/pruning |

Narrow normalization không phải repair loop. Không thử SQL mới sau execution failure; không
đổi câu hỏi, cột, khóa, filter hay grain. Không retry generation vì refusal.

### E1. Kích thước context đo được

So cùng metadata synthetic, ba physical UUID identifiers cố định, hai approved edges,
document_count=1; builder cũ lấy trực tiếp từ HEAD bằng `git show`, builder mới từ working tree.
Đơn vị là Python character count, **không phải token estimate**; chưa tính wrapper prompt.

| Domain | Router trước → sau | SQL schema trước → sau |
|---|---:|---:|
| Học phí | 3855 → 1931 | 7259 → 7352 |
| Giao vận | 3839 → 1933 | 7243 → 7336 |
| Bán hàng | 3889 → 1957 | 7293 → 7386 |
| Nhân sự | 3905 → 1969 | 7309 → 7402 |
| Năng lượng | 3831 → 1923 | 7235 → 7328 |
| Bảo trì holdout, star | 4573 → 1967 | 7977 → 8070 |

SQL schema tăng 93 ký tự do hướng dẫn ORDER BY. Generator wrapper cũng tăng vì làm rõ
contract; không tuyên bố tổng prompt giảm hoặc latency/accuracy đã cải thiện. Router vẫn
có tất cả tables/columns/source headers/edges/root fact, không lọc theo keyword câu hỏi.

## F. Implementation

### F1. Production diff — đúng bốn files

1. `backend/app/text_to_sql/join_policy.py`: `_normalize_selected_count_order`;
   gọi trước aggregate checks; mọi aggregate ở SELECT vẫn phải qua guard cũ.
2. `backend/app/text_to_sql/validator.py`: revalidate tables/functions/columns sau JOIN
   policy cho cả hai/ba bảng, không chỉ three-table branch như trước.
3. `backend/app/datasets/context.py`: routing facts riêng, relation facts tái sử dụng;
   examples/SQL commands chỉ vào schema_context; gợi ý ORDER BY selected COUNT alias.
4. `backend/app/text_to_sql/generator.py`: description/prompt nhất quán success/refusal;
   SQL-evidence-only khi so với quy định tài liệu, không invent threshold/filter.

Không sửa relationship detection, executor, provider adapters, database models/schema,
API shape hoặc frontend. Không tăng supported table/edge count hoặc thêm IR.

### F2. Tests mới

- `backend/tests/test_sql_generation_contract.py`: 32 cases; prompt boundaries, schema,
  refusal, 8 equivalent COUNT-order variants, 12 negative ordering/semantics cases,
  quoted/unquoted aliases, LIMIT/null ordering, HAVING vẫn fail-closed, Vietnamese source
  headers + unrelated table + đảo thứ tự registry.
- `backend/tests/test_sql_draft_adapters.py`: 4 cases qua adapter thật nhưng mock HTTP;
  Gemini/Knowledge × success/refusal. Kiểm tra schema descriptions gửi đi và parse kết quả.
- `backend/tests/test_count_order_integration.py`: 24 cases, sáu domain × 2/3 tables ×
  row/value COUNT sorting; PG raw/canonical/pipeline so với oracle độc lập.

Tổng bổ sung 60 tests, không cộng các lần rerun thành test cases mới.

### F3. Invariants giữ nguyên

SELECT-only, một scope/statement, allowlisted objects/functions, không DDL/DML/catalog,
không nested/window/unsafe joins, đúng một relationship mỗi pair, tối đa ba tables/hai edges,
root fact từ metadata, exact approved ON, entity ID grain, fact numeric measure contract,
owner/workspace isolation, current revision/lock guard, read-only timeout/row cap, lossless
Decimal/BIGINT/NULL/zero, CSRF/authentication/provider gates/fallback attribution.

## G. Before/after evaluation

### G1. Môi trường và an toàn

- Python 3.11.9; google-genai 1.75.0; SQLGlot 29.0.1; Pydantic 2.14.1;
  SQLAlchemy 2.1.4; langchain-openai 1.7.2; pytest 9.1.1; Ruff 0.17.0.
- PostgreSQL **17.8**, image có sẵn `pgvector/pgvector:0.8.1-pg17-trixie`.
- Container mới: `shopquery-ai-reliability-research`, ID prefix `9eaf77a22e7d`;
  label `shopquery.test=reliability-investigation-20261021`.
- Bind chỉ `127.0.0.1:15438`; data **tmpfs**, inspect `.Mounts=[]`, không bind/named volume main.
- Targeted DB: `shopquery_test_reliability_investigation`.
- Full integration DB mới riêng: `shopquery_test_reliability_full`.
- `current_database()` được xác minh trước khi tests; test safety guard vẫn hoạt động.
  Setup/reader là roles chỉ dành cho container test; không ghi credentials vào báo cáo.
- Test process đặt `SQL_JOIN_V1_ENABLED=false`; JOIN fixture bật request-local flag.
  `GEMINI_API_KEY=''`, `INETCLOUD_BASE_URL=''`; live opt-in suites không chạy.
  Gateways của evaluation scripted; provider-adapter tests dùng mock transports.

Không chạy test trên cổng 15432/database `shopquery`. Không sử dụng volume
`shopquery-ai_postgres_auth_20261019`. Ba main container IDs vẫn là web `2af67d527f2e`,
API `ea2a3f3688ea`, DB `511c4f5aaccc`, observed healthy; đây **không phải deployment
hoặc nghiệm thu source mới**. Không đọc raw rows/prompt/secrets main để làm audit.

### G2. Trước sửa — fail đúng tầng

1. Bộ regression đầu tiên: **13 FAIL / 11 PASS** (24 cases lúc tạo đầu).
   Trong 13 failures: 8 COUNT-order validator, 2 routing-boundary, 1 schema description,
   2 missing Hybrid/generator-instruction assertions. Năm prompt/schema failures là
   contract assertions, **không phải năm lỗi model live**.
2. 24 PG cases đều chạy raw SQL và canonical SQL khớp independent oracle trước khi đến
   validation. Validator baseline sau đó từ chối **24/24** ở COUNT alias check.
3. Lần chạy PG đầu tiên có lỗi test-only diagnostic `response.error` không tồn tại;
   đã sửa test sang gọi validator trực tiếp trước service để hiển thị đúng cause.
   Kết quả baseline 24/24 nói ở mục 2 là lần chạy lại đã sửa assertion, trước sửa production.

### G3. Oracle và metamorphic coverage

`tests.test_join_domains_integration.oracle` dựng PG VALUES từ facts/business IDs đã biết,
không dùng generated JOIN SQL làm expected. Test mới gọi oracle **trước** dựng draft.
Raw COUNT-order và alias-order chạy trên cùng synthetic PostgreSQL; pipeline sau sửa
đi qua registry context, approved guard, real read-only executor và grounded evidence.

Sáu domain: học phí, giao vận, bán hàng, nhân sự, năng lượng và bảo trì holdout (star).
Existing 144 domain golden cases được chạy lại, là **subset** của full integration count,
không cộng thêm. Bao gồm seed 0/7/19, row/upload reorder, CSV/XLSX, random physical names,
single/two/three tables, duplicate display names/distinct IDs, chain/star, SUM/AVG/counts,
zero/NULL/Decimal, temporal filter, SQL/RAG/Hybrid/unsupported với fake providers.

Test mới dùng COUNT row/value sorting có tie-break entity ID; exact ordered rows so PG
oracle. New metadata cases giữ source headers có dấu và extra unapproved `_id` table;
không prune hoặc tự authorize extra relationship. Paraphrase được gửi qua pipeline nhưng
gateway đã scripted SQL: chỉ đo boundary propagation, **không đo NL understanding**.

Các regressions khác tái kiểm tra JOIN order permutations, stale/revoked relations,
concurrent guard, owner/workspace/CSRF, NULL keys/orphans/duplicate targets/ambiguous
directions, wrong ON, unsafe fan-out/two facts, BIGINT, TIMESTAMP/TIMESTAMPTZ/VN month edges,
document citations, provider errors/retries, history/model attribution và Guest TEMP scope.

### G4. Kết quả test cuối

| Lệnh / suite | Kết quả thực tế |
|---|---|
| Targeted `test_sql_generation_contract`, `test_join_audit`, `test_join_order`, `test_three_table_join`, `test_workspace_prompts` ở thời điểm patch đầu | 183 PASS / 0 FAIL, 2.79 giây; các test bổ sung sau đó được full suite chạy lại |
| `test_sql_generation_contract.py` sau bổ sung alias/security/metadata cases | 32 PASS / 0 FAIL, 2.29 giây |
| `test_count_order_integration.py` trên DB targeted | 24 PASS / 0 FAIL, 8.82 giây |
| `test_sql_draft_adapters.py` | 4 PASS / 0 FAIL, 3.50 giây |
| Full unit, `pytest -m 'not integration and not live' -q --tb=short` | **630 PASS / 0 FAIL**, 553 deselected, 17.21 giây |
| Full PostgreSQL, `pytest -m integration -q --tb=short` | **537 PASS / 0 FAIL**, 642 deselected, 160.47 giây |
| `ruff check backend/app backend/tests` | PASS |
| `git diff --check` | PASS; chỉ cảnh báo Git LF/CRLF, không whitespace errors |
| Frontend Vitest/Playwright, Google browser UI live | NOT RUN trong task này; không đổi UI/API shape |
| Live Knowledge/Gemini/embedding | NOT RUN: 0 external generation, 0 external embedding |
| CI trên patch này | NOT RUN; không commit/push |

Hai full suites cộng lại là **1167 distinct offline tests**, tăng 60 so với baseline
1107. Không cộng targeted reruns hoặc 144 domain subset một lần nữa. PostgreSQL suite
được collect trước lúc thêm bốn adapter unit tests; vì vậy deselected là 642 thay vì 646,
không thiếu integration case. Unit full cuối đã chứa cả bốn adapter tests.

Điều kiện chạy lại: cấp hai database URLs và `SHOPQUERY_TEST_DATABASE_URL` cùng trỏ đúng
database test cô lập, `RUN_DATABASE_TESTS=1` cho integration; không lấy main URL từ `.env`.
Đặt `SQL_JOIN_V1_ENABLED=false`, không bật live flags. Cần setup role/reader test và image
pgvector hiện có; `require_test_database` vẫn kiểm tra tên/target, không tắt safety guard.

Sau tests, container tmpfs riêng được dừng để không chạy dư. Không xóa container, image
hoặc volume; tmpfs data là dữ liệu giả dùng một lần, không dùng làm nơi lưu evidence lâu dài.
Fixtures và tests là nguồn tái tạo. Không dừng/recreate ba main services.

### G5. Metrics và cách đọc đúng

| Metric | Kết quả trên tập mới / giới hạn |
|---|---|
| Supported COUNT-order false refusal | Baseline 24/24; sau sửa 0/24 trong matrix PostgreSQL, không phải live refusal rate |
| SQL execution / exact oracle | 24/24 raw và canonical PG trước sửa; 24/24 guarded pipeline sau sửa; không cộng thành 72 independent questions |
| Synthetic semantic correctness | 24/24 exact IDs, rows/order/counts/SUM/AVG/NULL/Decimal của các drafts định trước; không chứng minh mọi query hoặc mọi dữ liệu |
| Unsafe acceptance | 0/12 new negative ordering/semantics cases; executor/grounding không được gọi. Các security suites cũ giữ assertions riêng |
| Structured adapter contract | 4/4 mock-HTTP cases; cùng success/refusal semantics, không live upstream conformance |
| Grounded answer match | 24/24 fake gateway nhận exact JSON oracle và trả JSON; không đánh giá văn phong/ảo giác của model thật |
| Linking correctness | Unit kiểm tra exact registry/header/type/edge set; PG guards và old golden tests thật. Provider linking accuracy UNKNOWN |
| Route / Hybrid / citations / history | Existing integration API/scripted routes và real test DB; không phải live router/UI evaluation mới |
| Knowledge/Gemini model accuracy | NOT RUN; không có request provider live trong lượt này |

Samples không ngẫu nhiên/độc lập thống kê: các cases chia sẻ fixtures và deterministic drafts.
Không suy confidence interval model hoặc population reliability từ 24/24. Single-fixture
agreement không là formal proof tổng quát; finite metamorphic/counterexample suite chỉ giảm
một số blind spots đã xác định.

### G6. Provider retry/timeout — không thay đổi

Knowledge: temperature=0; strict JSON schema + Pydantic; tối đa hai structured-format
attempts trong adapter khi JSON/schema không hợp lệ. Transport retry mặc định một attempt,
timeout mặc định 60 giây. Không retry SQL refusal/validation để sửa SQL.

Gemini: generation structured temperature=0; text grounding=0.1; timeout mặc định 30 giây;
SDK attempts=3 cho status 408/429/500/502/503/504, có backoff SDK. Không retry auth/config
hoặc SQL validation bằng vòng app. [SDK source đúng version](https://github.com/googleapis/python-genai/blob/v1.75.0/google/genai/_api_client.py).

Actual runtime overrides không được thay trong lượt này. Logical stages khác HTTP attempts;
ngân sách live tương lai phải tính SDK/structured-format retries. Các retry/error tests đều
mock transport. Fallback cả turn chỉ khi ProviderError cho phép và cấu hình bật; không dùng
fallback để vượt semantic refusal. Model attribution giữ nguyên.

## H. Known limitations / chưa được phép tuyên bố

1. Chưa có rejected drafts của Gate D: không khẳng định COUNT-order bug giải thích tất cả
   Knowledge/Gemini failures. `generator_unsupported` có nhiều lý do nội bộ chưa quan sát.
2. Nếu model dùng alias như `delivery_count` thay canonical row/value alias, vẫn bị từ chối.
   Không đoán alias nghiệp vụ để biến COUNT(nullable) thành row count.
3. COUNT trong HAVING hoặc ORDER BY aggregate không selected vẫn fail-closed. Không mở
   thêm HAVING contract vì chưa có proof/authorization cho behavior rộng hơn.
4. Grouping city/category attributes chung thiếu dimension ID vẫn ngoài entity-grain contract.
   Không tự thêm ID. Trên ba bảng chỉ chấp nhận rooted chain/star N:1/1:1 đã kiểm chứng;
   không nhiều-fact fan-out, composite joins, arbitrary paths, >3 tables hoặc nested SQL.
5. Validator bảo vệ supported SQL subset, không phải bộ chứng minh NL-to-business semantics;
   một query safe/cú pháp đúng vẫn có thể không trả lời đúng câu hỏi nếu model hiểu nhầm metric.
6. Context còn pair và tree examples; không có bằng chứng live về mức ảnh hưởng attention.
   Không thêm schema pruning/ranker/IR hoặc deterministic SQL compiler chỉ vì paper đề xuất.
7. Grounded text và Hybrid policy application vẫn do model sinh; citation-ID validation không
   chứng minh mọi câu diễn đạt đều đúng. Fake gateway không thay thế live acceptance.
8. Frontend tests/live UI không chạy lại vì không đổi UI/API contract; account/history
   regressions được kiểm bằng test API/DB, không tuyên bố Google browser live mới PASS.
9. Main vẫn dùng code trước patch; unit pass không tự triển khai bản sửa lên 8080.
10. Test DB tmpfs là disposable, không backup dữ liệu người dùng; fixtures/tests trong Git
    là tài liệu tái tạo. Không có cam kết project “không còn lỗi”.

## I. Đề xuất live acceptance — CHỜ DUYỆT RIÊNG

Không thực hiện trong task này. Không tái sử dụng Gate D budget. Trước live cần duyệt riêng
triển khai đúng source mới lên API 8080; kiểm tra module hashes, DB identity và giữ nguyên main
volume/models/gates. Google login do người dùng thực hiện bình thường; không export session.

### I1. Fixture / câu hỏi cố định

Dùng duy nhất synthetic logistics workspace 13 đã được kiểm chứng: 50 delivery facts,
15 drivers, 5 warehouses, hai approved edges, tài liệu KPI đã có. Không upload/re-ingest
tài liệu mới nếu chưa được duyệt; không gửi dữ liệu workspace khác.

Chạy ba câu sau với Knowledge, rồi đúng ba câu với Gemini:

1. “Cho biết mã và tên từng tài xế, tổng phí, phí trung bình, số dòng đơn và số giá trị phí
   không rỗng, tính tất cả trạng thái; sắp theo số dòng đơn giảm dần rồi mã tài xế tăng dần.”
2. “Cho biết mã và tên từng kho điều phối, tổng phí, phí trung bình, số dòng đơn và số giá trị
   phí không rỗng, tính tất cả trạng thái; sắp theo số dòng đơn giảm dần rồi mã kho tăng dần.”
3. “Theo quy định KPI trong tài liệu, kho nào đạt ngưỡng tổng phí? Cho biết mã, tên, tổng phí
   và số dòng đơn theo từng kho, tính tất cả trạng thái, rồi đối chiếu điều kiện và dẫn nguồn.”

Oracle mới đọc từ PostgreSQL trước gọi model; exact entity IDs, counts/null/zero/decimal,
ordering và policy content/IDs. Đối chiếu cả answer và evidence, actual model/fallback=false,
history reload. Không hardcode kết quả Gate D vào response.

### I2. Trần ngân sách đề nghị

- **6 logical chat probes**: bốn SQL × 3 generation stages + hai Hybrid × 4 stages =
  **20 logical generation calls** theo pipeline hiện tại.
- **2 query embedding calls**, không document embedding nếu dùng đúng policy/chunks đã có.
- SDK transient retries và Knowledge structured-format attempts có thể tăng HTTP requests;
  phải ghi nhận số thực nếu quan sát được, không coi logical calls là HTTP hard cap.
- Không tự gửi câu hỏi thứ bảy, retry chat hay repair SQL ngoài kế hoạch.

### I3. Stop conditions và integrity

Nếu model sai, validator refuse, fallback ngầm, actual model khác, schema/module mismatch,
owner/session không đúng hoặc quota/upstream lỗi: dừng, không thử lại để “may rủi”.
Giữ fail-closed. Chỉ lưu raw draft trong private synthetic evidence nếu có quyền cụ thể;
không bật raw logging production. Ghi stage/refusal code an toàn và causal uncertainty.

Kiểm tra owner/scope/approved revisions trước probe; schema/data fingerprints business
trước/sau nếu được phép đọc main; chỉ conversations/rate counters/session bình thường có thể
thay đổi. Không xóa synthetic/history tự động. Chỉ báo live PASS cho đúng probes đã thực hiện,
không suy thành mọi loại JOIN hoạt động đúng.
