# SQL/JOIN root-cause audit — 20–21/10/2026

Trạng thái ban đầu: **NOT READY** cho hợp đồng entity aggregation; đang xử lý
counterexamples, chưa có nghiệm thu live cho thay đổi của audit này.

## Baseline và ranh giới

- HEAD đã kiểm tra: `08bfbf09ab7402fc89628730b61bbf69f677d2f1`, không giả là
  working tree sạch. Giữ và review các thay đổi logistics từ lượt X: detector,
  unit/integration tests, README và acceptance report. Không có hunk Hybrid khác.
- Runtime lúc bắt đầu: API `4f28dddb243a`, web `a27d03924b65`, DB `511c4f5aaccc`,
  đều healthy. API được build từ dirty logistics source, không phải nguyên HEAD.
- Main và archived volumes, accounts/sessions, dữ liệu, embeddings, lịch sử và
  quan hệ hiện có được bảo vệ. Không migration, reset, backfill hay provider calls.
- Chỉ deployment sau Gate A/B/C. Không thêm optimizer/agent/framework/model,
  không 4+ bảng. Live Gate D cần phê duyệt ngân sách mới.

## Research evidence (đọc trực tiếp 20/10/2026 trước sửa lớn)

| Vấn đề ShopQuery | Bằng chứng source | Nguồn kỹ thuật | Kết luận áp dụng | Cần sửa |
| --- | --- | --- | --- | --- |
| INNER equality/reorder/fan-out | join_policy kiểm tra exact key rồi canonicalize | [PG table expressions](https://www.postgresql.org/docs/17/queries-table-expressions.html) | Đối chiếu row multisets, không dựa vào SQL string; giữ equality và predicates | Giữ guard, mở coverage |
| COUNT, NULL, Decimal | COUNT aliases; SUM/AVG chỉ kiểm tra numeric type | [PG aggregates](https://www.postgresql.org/docs/17/functions-aggregate.html) | COUNT(*) khác COUNT(nullable); numeric identifier không tự thành measure | Có |
| Group label không unique | Không hậu kiểm dimension identity trong GROUP BY | [PG grouping](https://www.postgresql.org/docs/17/queries-table-expressions.html#QUERIES-GROUP) | SQL hợp lệ có thể gộp nhiều entity; cần declared key | Có, P1 |
| EXPLAIN không chứng minh nghiệp vụ | executor read-only/timeout | [PG EXPLAIN](https://www.postgresql.org/docs/17/using-explain.html) | Plan chỉ hỗ trợ kiểm tra execution/cardinality; oracle riêng vẫn bắt buộc | Test, không thêm production EXPLAIN |
| AST qualification có rewrite | validator tự resolve aliases, không dùng optimizer | [SQLGlot](https://sqlglot.com/), [repo](https://github.com/tobymao/sqlglot), [qualify source](https://github.com/tobymao/sqlglot/blob/main/sqlglot/optimizer/qualify.py) | qualify có expand aliases/stars/normalize; không bật toàn bộ optimizer trên model SQL | Không tích hợp mới |
| Context/model accuracy thiếu holdout | Fixtures lịch sử tập trung English tuition | [Spider 2.0](https://spider2-sql.github.io/), [CHESS](https://arxiv.org/abs/2405.16755), [DIN-SQL](https://arxiv.org/abs/2304.11015) | Tách schema linking, generation, execution và đánh giá holdout; không lấy benchmark accuracy làm độ tin cậy app | Golden đa lĩnh vực |
| Tests khớp tổng nhưng có thể sai nhóm | Lượt X chỉ main aggregate conservation | [Defog sql-eval](https://github.com/defog-ai/sql-eval) | Exact execution results và dữ liệu phân biệt sai query; không chỉ totals/empty result | Có |
| Trusted DDL/terminology vs LLM inference | Backend metadata allowlist | [Vanna](https://github.com/vanna-ai/vanna), [legacy DDL/examples source](https://github.com/vanna-ai/vanna/blob/main/src/vanna/legacy/base/base.py) | Chỉ học cách đưa schema/docs/examples; legacy API khác framework hiện tại, không tích hợp Vanna | Giữ kiến trúc |

SQLGlot qualify documentation endpoint trả lỗi khi truy cập; đã đọc source chính
chủ trực tiếp thay thế. Không suy diễn rằng qualification chứng minh entity grain.

## Root causes trước sửa lớn

| Bug ID | Scenario / severity | Failure stage | Evidence trước sửa | Root cause / impact | Recommended fix | Regression |
| --- | --- | --- | --- | --- | --- | --- |
| J01 | Entity trùng tên, P1 | join grain | Hai unit cases 2/3 bảng không raise khi GROUP BY s.name | Prompt yêu cầu ID nhưng validator không thực thi; có thể gộp sai người/kho | Fail closed nếu nhóm dimension thiếu approved target key, không tự sửa SQL | Duplicate labels + PG per-ID oracle |
| J02 | SUM/AVG foreign BIGINT identifier, P1 | join aggregate | Hai unit cases SUM/AVG(f.entity_id) không raise | Kiểu số bị coi là measure, trái vai trò khóa đã biết | Chặn aggregate identifier đã kiểm chứng, vẫn cho COUNT đúng semantics | Numeric key vs real measure |
| J03 | student_archive giống prefix, P1/P2 | relationship discovery | Candidate hiện được chọn dù không có semantic equivalence với students | Descriptive prefix + dữ liệu đầy đủ không chứng minh ý nghĩa nghiệp vụ | Chỉ exact normalized entity tự kích hoạt; tên mô tả/dịch khác nghĩa cần manual preview/confirm | Matching incidental domains, numbered exact names |
| J04 | Không xác định stage của UNSUPPORTED, P2 | diagnostics | generator có unsupported_reason nhưng error code unspecified; router UNSUPPORTED không trace | Frontend message chung không đủ phân biệt nguồn lỗi | Safe stage/correlation diagnostics; không log prompts/SQL/values | Stage failures + telemetry failure isolation |
| J05 | Logistics thiếu metadata, P2 (lịch sử X) | relationship discovery/context | Workspace 12 từng có 0 edges; numbering/name mismatch | Test English không đại diện mọi upload; context thực sự cấm JOIN | Giữ xử lý numbered exact label, không backfill hàng loạt | Logistics chain/manual semantic approval |
| J06 | SUM AS fact_row_count, P1 | join aggregate | Ba aliases đếm đều nhận SUM trước sửa | Grounding có thể hiểu nhầm số tiền thành số dòng | Chặn reserved count aliases trên SUM/AVG | Ba FAIL trước sửa, PASS sau sửa |
| J07 | WITH ROLLUP, P1 | join grain | Có ID trong GROUP BY nhưng subtotal vẫn được nhận | Kiểm tra chỉ nhìn expressions, bỏ qua modifiers của Group AST | Fail closed mọi subtotal grouping modifiers; kiểm tra cả dimension bên trong group expression | WITH ROLLUP FAIL trước sửa; ROLLUP/CUBE/GROUPING SETS đều REJECT sau sửa |
| J08 | Mất quy tắc trong bảng DOCX, P1/P2 | schema/document metadata | Tài liệu KPI gốc mất dòng ngưỡng 8; parser chỉ duyệt document.paragraphs | Upload thành công nhưng context thiếu bảng Word; fixture cũ chỉ có paragraph/Markdown nên bỏ sót | Duyệt paragraph/table theo thứ tự tài liệu; giữ extraction/archive limits; từ chối nested table rõ ràng | Hai FAIL trước sửa; kiểm tra thứ tự, giới hạn, nested-table rejection và RAG/Hybrid PostgreSQL |

Reproduce hiện tại: `test_join_audit.py` **5 FAIL** trước sửa, không gọi provider.
Đây là baseline counterexamples, không phải kết quả nghiệm thu cuối.

### Phê duyệt thay đổi phạm vi grouping

Chủ dự án đã duyệt siết fail-closed: aggregate JOIN có thuộc tính dimension phải
GROUP BY approved target identifier. Không tự chèn ID, không sửa WHERE/key/metric.
Nhóm theo thuộc tính chung không kèm ID (ví dụ thành phố) có thể bị từ chối;
đây là giới hạn công bố, không ghi nhận thành case hỗ trợ rồi làm test xanh giả.

### Không được suy rộng từ evidence

- count_star_alias là một log có thật nhưng không có correlation để gắn nó với
  từng câu hỏi production cũ. Chưa chứng minh mọi model refusal là validator bug.
- Tree example cap/context relevance là hypothesis; tất cả approved edges vẫn
  có trong context. Không tự lọc schema hoặc thêm schema retrieval agent.
- Two facts/shared dimension, wrong keys, outer/cartesian/composite, 4+ tables,
  absent/ambiguous relation là intended unsupported; không nới để tăng pass rate.
- Đếm business entity ở fact có nhiều dòng/ID cần hợp đồng grain riêng; không
  tuyên bố COUNT(*) luôn là số đơn. Không tự thêm DISTINCT hoặc LEFT JOIN.

## Thay đổi và lý do các lần trước bỏ sót

- `join_policy.py`: hậu kiểm entity ID và subtotal, chặn SUM/AVG khóa đã biết và
  alias đếm sai. Không chèn ID, đổi ON/WHERE, thêm DISTINCT hay sửa grain.
- `datasets/context.py`: đồng bộ chỉ dẫn với validator. Khóa fact lấy từ backend
  relationships, không lấy từ vị trí FROM hay quyết định của model.
- `relationship_detection.py`: giữ numbered exact-name fix; không kích hoạt
  descriptive-prefix matches. Các quan hệ đang lưu không bị sửa/backfill.
- `rag/upload_parser.py`: đọc bảng Word đúng thứ tự. Dùng API chính thức
  [python-docx Document](https://python-docx.readthedocs.io/en/latest/api/document.html)
  và [Table](https://python-docx.readthedocs.io/en/latest/api/table.html), phiên bản
  1.2.0 đã cài; không đổi dependency. Nested tables chưa hỗ trợ, fail closed.
  Không tự re-ingest tài liệu cũ hoặc tạo embedding mới trên main.
- `core/diagnostics.py` và các điểm gọi: correlation ID, safe stage/reason,
  duration, bảng/cạnh, route/model, validated/executed/row count/status. Bounded
  64 events; không question, SQL, values, docs, email, cookie/token. ContextVar
  tách request; Guest relay safe events từ child; logger failure không làm fail
  chat. API POST không phải OAuth có `X-Request-ID`. Không external telemetry.
- UI chỉ giải thích rõ giới hạn auto-discovery, không redesign. Mock/live
  relationship assertions cập nhật theo wording, không giảm owner/CSRF tests.

Lịch sử review: `2a8c113` sửa equivalent INNER order; `be93d5a` thống nhất
aggregate/count contract; `08bfbf0` thêm auto-detection và ba-table trees.
Các bản trước tập trung examples và happy paths; chưa có adversarial duplicate
labels, BIGINT foreign-key measures, reserved alias counterexamples, subtotal
AST và DOCX table rules. Nhiều refusal production cũ không có correlation nên
không thể gắn nguyên nhân chắc chắn từ screenshot/message UI. Audit không nhận
J01/J08 là lời giải thích cho mọi câu hỏi bị từ chối trước đó.

## Golden, metamorphic và oracle

`test_join_domains_integration.py`: 144 cases, PostgreSQL thật, fake gateways
cho cả hai lựa chọn model. 108 SQL cases (1/2/3 bảng × 6 domains × 3 seeds ×
2 models), 36 RAG/Hybrid/Unsupported. Mỗi domain 24 cases: 22 expected-safe,
2 intended Unsupported. Không phải phép đo độ chính xác sinh SQL/routing của LLM.

| Domain | Cases | Oracle / phạm vi |
| --- | ---: | --- |
| Học phí | 24 | TEXT keys, tên có dấu, duplicate labels, Decimal/zero/NULL |
| Giao vận synthetic | 24 | 50 facts, 15 drivers, 5 warehouses; từng nhóm, không chỉ totals; DOCX table KPI |
| Bán hàng | 24 | Đếm order lines, không giả đó là distinct orders |
| Nhân sự | 24 | Hours SUM/AVG và entity identity |
| Năng lượng | 24 | NUMERIC, TIMESTAMPTZ hai biên tháng theo Việt Nam |
| Bảo trì holdout | 24 | Star graph fact → hai dimensions; không thêm prompt theo domain |

Seeds 0/7/19 đổi row order, upload order, CSV/XLSX và random physical identifiers.
Có duplicate names khác ID, zero, NULL measure, nhóm toàn NULL và dimension không
có fact (INNER intentionally không trả unmatched dimensions). Oracle dùng mapping
business fixture độc lập rồi PostgreSQL VALUES aggregation, không dùng lại JOIN
model/SQL string làm expected. SUM/AVG/COUNT rows và non-NULL values so exact,
không float tolerance. Các permutations JOIN/ON/alias/filter, stale deletion,
cross-workspace và execution guard tiếp tục nằm trong regression suites cũ.

`test_join_counterexamples_integration.py`: 8 cases bổ sung. PostgreSQL chứng minh
label-only trả một nhóm 50 thay vì hai ID 20/30; EXPLAIN ANALYZE chỉ hỗ trợ execution
evidence, không thay business oracle. Duplicate target, orphan, NULL source/target,
type mismatch, một-một và ambiguous semantic targets không được tự kích hoạt.

### Đối chiếu file giao vận gốc (private local evidence)

Đã tìm và đọc ba CSV cùng ba DOCX gốc trong Downloads, không commit các file hay
raw rows. SHA-256 ba CSV lần lượt:

- `5954987c33c512191ad9b797052fa9eb6815dcb86649c50fb5984da8d94e322e`
- `921f7166441685e05c82b860e672bcb8ec907810406d2f03453dfd831f50aacd`
- `e82a4a961089ef5e20085980e614441dbbe1f4fb009bb0ff83b0a0a6dad4c8ba`

Python stdlib CSV/Decimal oracle dựng mapping bằng IDs độc lập; import trên DB test
riêng, manual preview/confirm cạnh kho mô tả, validator + execution guard + reader
execution. Hai-table 15 groups và ba-table 5 groups khớp từng dòng, 50 orders,
2,472,500.00 VND, mỗi kho 10 orders. Hash hai tập grouped oracle:
`aced6996b539e28b0215241cd52bfab8ade8982ed4261f427aac96b19e8ed583`.

Ba DOCX parse/chunk sau sửa: 7/7/7 chunks, 2,155/2,103/2,221 characters.
Trước sửa: 6/6/7 chunks, 1,828/1,660/1,836 characters, thiếu dòng KPI trong bảng.
Bốn RAG/Hybrid fake-model cases trên đúng bộ gốc đạt: ngưỡng ít nhất 8 đơn
"Đã giao", SQL lọc trạng thái trước GROUP BY ID, 5 nhóm, 4 kho đạt; citations
trỏ chunk thật chứa ngưỡng. Embedding stub cố ý ưu tiên chunk ngưỡng để kiểm tra
pipeline/citation, **không đo chất lượng semantic retrieval của Gemini**.
Không có provider call. Đây là parser/content acceptance, không phải kiểm tra
layout/render của DOCX và không thay đổi các file nguồn.

## Security và giới hạn còn lại

Giữ SELECT-only, reader role/transaction, exact approved ON, tối đa ba bảng,
hai edges, một root fact, owner/workspace allowlists, revision locks, timeout,
row cap, CSRF/Origin, Guest RAM/TEMP/TTL và no-fallback-leak. Tests unsafe vẫn
phải REJECT trước executor; không loại assertion để làm xanh.

- Group theo shared category không có ID, outer JOIN, distinct dimension count,
  hai facts/fan-out và 4+ bảng vẫn ngoài contract. ID là khóa JOIN đã biết mới
  được nhận diện chắc là identifier; app chưa có business-metric catalog để
  chứng minh mọi cột số khác là measure đúng ý nghĩa.
- Tên khác nghĩa/ngôn ngữ cần xác nhận thủ công. Full value match không chứng
  minh cùng miền nghiệp vụ; auto mode không cam kết suy luận mọi schema.
- Context tree-example cap/relevance chưa có bằng chứng là root cause; không
  thêm schema agent/selection tự đoán. LLM vẫn có thể từ chối hoặc sinh sai draft.
- Frontend rendering kiểm tra qua unit/mock/browser assertions; không thêm
  endpoint telemetry từ browser. `frontend_rendering` chỉ là tên stage dành
  cho test diagnostics, chưa có production browser event pipeline.
- Google session quan sát hợp lệ ngày 20/10; sau dừng máy qua đêm phải kiểm tra
  lại. Không xuất credentials/session hoặc coi ảnh cũ là current acceptance.

## Test và gates

Baseline sau các sửa JOIN/diagnostics đầu: 1,104 backend offline tests PASS
(16 live deselected). Parser DOCX và golden DOCX bổ sung sau đó phải chạy targeted
và CI đúng snapshot mới. Ruff PASS; FE lint/typecheck/build PASS, 66 unit và
105 browser mock PASS trên 5 viewports (Guest/auth, history, model attribution,
Decimal/zero/NULL, upload, relationships, deletion, CSRF/state).

Một lần unit không đặt JOIN flag OFF kế thừa `.env` ON nên fake-owner fixture
đụng real relationship builder và FAIL; không sửa security để vượt. Lần chạy
chuẩn offline đặt flag OFF, cùng điều kiện CI; JOIN-specific suites tự bật flag
với authenticated metadata thật trên test DB. Kết quả cuối cập nhật bên dưới.

A/B PASS trong deterministic contract: 594 backend unit PASS trên source cuối,
144 golden PostgreSQL PASS sau bổ sung DOCX; toàn suite trước DOCX là 1,104 PASS
(591 unit + 513 integration). Ba unit mới nâng tổng dự kiến lên 1,107; CI sẽ
xác minh exact snapshot, không cộng targeted runs thành số test độc lập mới.
Security negative cases và Guest/auth/CSRF nằm trong unit/integration totals,
không có pass-rate LLM suy ra từ hai nhãn fake model.

C: source/test/docs chuẩn bị commit; CI và runtime evidence cập nhật sau khi
xác minh đúng SHA. D NOT RUN: 0 live generation và 0 live embedding calls.

## Kế hoạch Gate D (chưa được duyệt, không thực hiện)

Chỉ synthetic dataset: một fact, hai dimensions, một policy chunk. Knowledge
hiện cấu hình và Gemini `gemini-3.5-flash-lite`, fallback hiện hành giữ nguyên.
Mỗi model: single-table, two-table, three-table SQL, một Hybrid = 8 logical chat
probes. Dự kiến 26 logical generation calls (6 SQL × 3 + 2 Hybrid × 4), 3 logical
embedding calls (một policy chunk ingest + hai Hybrid queries), nếu chưa có vector
fixture phù hợp. SDK retries giữ cấu hình, HTTP requests có thể cao hơn logical
calls. Cần chủ dự án phê duyệt trước khi gọi. So từng row với PostgreSQL oracle,
stable IDs/Decimal/NULL/zero, actual model/no silent fallback, citations và history
reload. Một pass/probe không chứng minh độ ổn định mọi câu hỏi; báo pass rate
đúng số lượt được duyệt, không tự retry/probe thêm.
