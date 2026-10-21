# SQL/JOIN root-cause audit — 20–21/10/2026

Kết luận hiện tại: **PARTIALLY VERIFIED — chưa nghiệm thu JOIN/Hybrid live**.
Gate A/B PASS trong deterministic contract; source CI và local deployment đạt.
Gate D được duyệt và chạy ngày 21/10: **3/8 PASS, 5/8 FAIL** trên bộ synthetic
cố định, không thử lại. Single-table cả hai model và Gemini hai-table đạt;
Knowledge JOIN, Gemini ba-table và cả hai Hybrid chưa đạt. Chi tiết cuối báo cáo.
Trạng thái lúc bắt đầu là NOT READY do các counterexamples entity aggregation.

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
| Học phí | 24 PASS / 0 FAIL | TEXT keys, tên có dấu, duplicate labels, Decimal/zero/NULL |
| Giao vận synthetic | 24 PASS / 0 FAIL | 50 facts, 15 drivers, 5 warehouses; từng nhóm, không chỉ totals; DOCX table KPI |
| Bán hàng | 24 PASS / 0 FAIL | Đếm order lines, không giả đó là distinct orders |
| Nhân sự | 24 PASS / 0 FAIL | Hours SUM/AVG và entity identity |
| Năng lượng | 24 PASS / 0 FAIL | NUMERIC, TIMESTAMPTZ hai biên tháng theo Việt Nam |
| Bảo trì holdout | 24 PASS / 0 FAIL | Star graph fact → hai dimensions; không thêm prompt theo domain |

Seeds 0/7/19 đổi row order, upload order, CSV/XLSX và random physical identifiers.
Mỗi domain có 2 Unsupported đúng, 0 Unsupported sai trong fake-gateway harness.
Không dùng các số này để tuyên bố tỷ lệ refusal thực tế của Knowledge/Gemini.
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

C: source commit `50d7bac4e1f6af8adffeb8f317a458f637de7bb0` đã push main;
[CI run 39530792010](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39530792010)
SUCCESS tại đúng SHA, ba jobs success. Logs xác nhận Ruff + 594 unit,
513 PostgreSQL integration (tổng backend 1,107), FE 66 unit + 105 browser mock,
lint/typecheck/build PASS. Golden 144 là tập con trong 513, không cộng lần nữa.
47 targeted cases trong bốn file audit/diagnostics/counterexamples/logistics
cũng là tập con. Không loại hay giảm security assertions.
D tại thời điểm chốt CI: NOT RUN. Kết quả live sau phê duyệt được ghi riêng ở cuối;
không dùng CI offline để thay thế nghiệm thu provider thật.

## Local deployment và bảo toàn dữ liệu

Triển khai ngày 21/10 sau CI source xanh, đúng Compose `compose.yaml` +
`.env.compose-ui.yaml` + `.env.join-v1.yaml`. So môi trường container trước/sau
với resolved Compose: **0 khác biệt**. Chỉ build/recreate API/web, không recreate
DB. DB đã dừng qua đêm, chỉ start lại container hiện có, không migration/reset.

| Thành phần | Container / image digest | Trạng thái |
| --- | --- | --- |
| API | `ea2a3f3688ea` / `09fb41dc043ee14bf52de6baf9d0a611f28287c87e599632e03b2f7aeaabf9d7` | healthy |
| Web | `2af67d527f2e` / `5ca6e17125f12574cf8cdf4d030b6a0a209007e9469b264e94e6d98056090146` | healthy, HTTP 200 |
| DB | `511c4f5aaccc` (không đổi) | healthy |

71 Python app modules khớp từng file với source local đã commit. SHA-256 map
module paths/hashes: `715c5b01327e970c67930c304529c6bce5f44a38be82231512885f22c770c167`.
JOIN ON, provider-data ON, Guest AI ON, Gemini `gemini-3.5-flash-lite`, fallback
OFF: giữ nguyên giá trị trước deploy, không sửa .env/OAuth/quota/model.
`/api/health` trả OK. Main volume `shopquery-ai_postgres_auth_20261019` và archived
`shopquery-ai_postgres_data` nguyên vẹn; không prune/xóa volume.

Fingerprint private trước deploy bao phủ **29 bảng**, bao gồm owner IDs,
accounts/sessions/OIDC, relationships, toàn bộ legacy + uploaded rows; không dùng
helper migration cũ vốn bỏ owner. Chỉ loại resource counters/leases vận hành.
Full hash trước: `88845e877f215a7f7034f79788c7f9e7bbc71f9a0320004475afee5dbabedf93`.
Sau deploy: `76e41b7f17b0614f7281f5b8c7197bd217f8e6a1250af1fdbc52504181f57cc0`.
Hai hash **không bằng nhau**, không báo pass giả: đã dừng điều tra và xác định
28 bảng không đổi, riêng `oidc_flows` từ 0 → 1 khi đăng nhập mới bắt đầu; tiếp
tục quan sát có flow mới và Google account chooser bình thường. Không có flow
cũ bị mất vì baseline bằng 0. Không khôi phục đè main.

Sau đó chủ dự án hoàn tất Google login qua UI, có thể cập nhật user.updated_at,
thêm/revoke session và consume flow đúng auth code hiện hành. Không tự tạo session
giả hoặc xuất auth secrets. UI synthetic chỉ thêm workspace **13** và ba bảng,
một auto edge/một manual edge. Đối chiếu lại **26 bảng nghiệp vụ cũ** với baseline
(lọc đúng workspace 13 mới và loại ba bảng auth có login hợp lệ): tất cả counts
và hashes khớp, aggregate hash `f73b828698b29380b28b5ae89a654df52115bef858ed7a4c246a2b11c84fa736`.
Không diễn đạt kiểm tra này thành toàn bộ DB byte-for-byte bất biến sau login.

### UI và API trên 8080

- Google UI thật: tạo `Root audit synthetic · 21-10-2026`, ID 13; upload ba CSV
  gốc synthetic 5/15/50 rows. UI hiển thị auto edge đơn → tài xế; preview cạnh
  tài xế → kho là many-to-one, NULL/duplicates/orphans đều 0; confirm manual.
  Reload, mở lại workspace: đủ ba tables và cả auto/manual relationships.
- Context trên API runtime của synthetic 13: 3 allowed tables, 2 approved edges,
  có safe three-table example, flag ON. Không ghi prompts/SQL/values vào log.
- Google history reload giữ hai kết quả Knowledge cũ: 15 và 5 result rows,
  model attribution còn đúng. **Không phải generation mới** trên guard mới,
  không chứng minh Gemini live hoặc mọi JOIN đã ổn định.
- Desktop 1280×900 và mobile 390×844: xem/confirm relationships được, mobile
  page/panel không overflow; reset viewport sau test. Screenshot private chỉ
  vùng synthetic relationship, không commit screenshot/logs/PII.
- Guest UI thật: CSV preview kho hiển thị đúng, chưa hoàn tất file-commit trong
  tab đó vì tab bị đóng rồi Google session được người dùng đăng nhập; không tự
  logout để ép kiểm thử. **Không tuyên bố full Guest UI lifecycle mới đã PASS**.
- Bù bằng Guest API thật trên 8080, không dùng Google cookie: ba CSV nhận đủ,
  một auto edge + một manual edge; invalid CSRF/Origin 403, foreign Guest
  preview 404, private datasets 401, phiên khác không thấy relationships.
  Không gọi `/api/guest/chat`; files chỉ ở RAM/TEMP theo TTL sẵn có.
- SQL/RAG/Hybrid/new conversation/history flows qua mock UI PASS; actual new
  SQL/RAG/Hybrid answers trên cả hai providers ở current runtime còn Gate D.

### Rollback và dữ liệu DOCX cũ

Giữ image tags `shopquery-ai-api:rollback-root-audit-20261021` và
`shopquery-ai-web:rollback-root-audit-20261021`. API image cũ config digest
`9253bfdbcf852c1da486824f0dbf20db7cf6fee5478dd7f9f5f40f42af57855b`, web cũ
`f5e708802bd3c79a992c17f0c5f068b31e3760d20b327fa6217a334a1a222354`.
Rollback ứng dụng cần tag lại hai images rồi Compose recreate **chỉ API/web**;
không restore DB và không dùng git reset làm mất work. Có thể tắt JOIN bằng
override riêng `SQL_JOIN_V1_ENABLED=false` và recreate API nếu cần; không đổi
provider gates/models. Tắt flag không phải database rollback. Không tự thực hiện
rollback trong lượt audit khi runtime đang healthy.

Parser mới chỉ sửa lần ingest mới. Tài liệu DOCX đã ingest trước sửa có thể vẫn
thiếu table chunks; file-content duplicate protection chặn re-upload y hệt.
Chưa xóa/re-ingest tài liệu hay embeddings main. Muốn cập nhật các tài liệu cũ
phải duyệt riêng đúng nguồn, phương án giữ lịch sử và embedding budget; không
gợi ý bypass dedup hoặc sửa file chỉ để vượt kiểm tra. Workspace 13 được để lại
cho kiểm thử tiếp, không tự xóa dữ liệu/lịch sử. Không VPS/Langfuse/framework mới.

## Kế hoạch Gate D (đã được duyệt và thực hiện 21/10)

Chỉ synthetic dataset: một fact, hai dimensions, một policy chunk. Knowledge
hiện cấu hình và Gemini `gemini-3.5-flash-lite`, fallback hiện hành giữ nguyên.
Mỗi model: single-table, two-table, three-table SQL, một Hybrid = 8 logical chat
probes. Trần được duyệt: 26 logical generation calls (6 SQL × 3 + 2 Hybrid × 4), 3 logical
embedding calls (một policy chunk ingest + hai Hybrid queries), nếu chưa có vector
fixture phù hợp. SDK retries giữ cấu hình, HTTP requests có thể cao hơn logical
calls. Chủ dự án đã phê duyệt trước khi gọi. So từng row với PostgreSQL oracle,
stable IDs/Decimal/NULL/zero, actual model/no silent fallback, citations và history
reload. Một pass/probe không chứng minh độ ổn định mọi câu hỏi; báo pass rate
đúng số lượt được duyệt, không tự retry/probe thêm.

## Gate D — kết quả live authenticated UI 21/10/2026

### Phạm vi và ngân sách thực tế

Chạy 09:32–09:43 giờ Việt Nam trên tab Google đã đăng nhập tại 8080, chỉ workspace
**13 — Root audit synthetic · 21-10-2026**. Không đọc/gửi dữ liệu workspace khác
vào provider. Source ứng dụng `50d7bac4e1f6af8adffeb8f317a458f637de7bb0`, HEAD báo
cáo trước lượt này `e2151a3d6b37f3a11e83f68553e5985bbe087deb`. Không sửa code,
validator, prompt, model, gates, fallback, quotas hoặc runtime trong lượt live.

Đúng **8/8 logical chat probes**, mỗi câu chỉ gửi một lần, **19/26 logical
generation method calls**, **1/3 logical embedding calls**. Sáu SQL chạy khi
workspace chưa có tài liệu, sau đó mới ingest `live_gate_d_kpi.md` thành đúng một
chunk/vector 768 dimensions. Cả hai Hybrid dừng trong nhánh SQL trước
`document_retrieval`, nên **0 query embedding**, không gọi synthesis/grounding
Hybrid. Không dùng phần ngân sách còn dư để thử lại hoặc thêm câu hỏi.

19 calls là số lần gọi gateway ở router/draft/answer được đối chiếu diagnostics,
không phải số HTTP requests. Gemini SDK attempts=3, timeout=30 giây; Knowledge
HTTP attempts=1, timeout=60 giây và vòng structured-schema tối đa hai lần sẵn có
đều giữ nguyên. Không có HTTP attempt instrumentation cho lượt này; **không xác
định chính xác số HTTP requests hoặc khẳng định không retry**. Không bật logging
raw prompt/SQL/credentials để đo requests.

### Oracle độc lập và kết quả

Oracle được chốt bằng SELECT PostgreSQL tự viết **trước** khi gọi model, không
lấy SQL do model sinh làm đáp án chuẩn: 50 orders, 15 tài xế, 5 kho; tổng phí
`2472500.00`. Bốn phí NULL và ba phí zero được kiểm tra riêng. Hai approved edges
đủ trong schema context của cả tám requests: 3 allowed tables, 2 approved edges.

| Probe | Model | Yêu cầu | Kết quả thực tế | Generation / query embedding |
| --- | --- | --- | --- | --- |
| K1 | Knowledge | Một bảng: 50 đơn, phí, trạng thái | PASS: từng row và answer đúng, giữ NULL/0/Decimal | 3 / 0 |
| K2 | Knowledge | Hai bảng: từng tài xế, SUM phí, đếm dòng | FAIL: `join_aggregate/count_star_alias`, chưa executor | 2 / 0 |
| K3 | Knowledge | Ba bảng: từng kho, SUM phí, đếm dòng | FAIL: `join_aggregate/count_star_alias`, chưa executor | 2 / 0 |
| G1 | Gemini | Cùng yêu cầu một bảng | PASS: từng row và answer đúng, giữ NULL/0/Decimal | 3 / 0 |
| G2 | Gemini | Cùng yêu cầu hai bảng | PASS: 15 groups đúng ID/name/SUM/COUNT trong rows và answer | 3 / 0 |
| G3 | Gemini | Cùng yêu cầu ba bảng | FAIL: `join_aggregate/count_column_alias`, chưa executor | 2 / 0 |
| KH | Knowledge | Ba bảng + policy KPI | FAIL: router HYBRID, `join_aggregate/count_star_alias`; chưa retrieval | 2 / 0 |
| GH | Gemini | Cùng yêu cầu Hybrid | FAIL: router HYBRID, `generator_unsupported`; chưa validator/executor/retrieval | 2 / 0 |

Sáu câu SQL được router chọn SQL; hai câu Hybrid được chọn HYBRID. Năm câu bị
chặn trả route cuối UNSUPPORTED, rows rỗng và thông báo ngắn; `error=null`
**không có nghĩa là nghiệm thu PASS**. Không tạo số liệu/citation giả thay kết quả.
Cả tám response lưu requested/used model đúng lựa chọn, `fallback_used=false`;
config runtime là Knowledge `knowledge` và Gemini `gemini-3.5-flash-lite`.
Ba câu thành công chỉ tham chiếu đúng tập bảng synthetic cần thiết; validator,
execution guard và PostgreSQL execution đều thành công.

Policy mới cố ý dùng KPI đơn giản **tổng phí tất cả trạng thái >= 500000.00**,
không phải KPI 8 đơn Đã giao trong DOCX cũ. Oracle từng kho là `393500.00`,
`598000.00`, `502000.00`, `439000.00`, `540000.00`, mỗi kho 10 dòng; KHO02,
KHO03, KHO05 đạt. Vì hai Hybrid đều bị chặn, chưa có câu trả lời live/citation
để đối chiếu với oracle này. Ingest một chunk PASS không chứng minh retrieval
hoặc Hybrid live PASS. Không re-ingest hay sửa tài liệu DOCX đã có trước.

### Nguyên nhân được xác minh và phần chưa biết

- K2/K3/KH đi qua workspace binding, relationship approval, schema metadata,
  router và structured draft; column resolution thành công rồi bị guard COUNT
  từ chối. Đây **không phải thiếu approved relationship** ở workspace 13 hoặc
  lỗi kết nối upstream quan sát được trong các câu này.
- `count_star_alias` chứng minh COUNT(*) không có alias được contract chấp nhận
  (`fact_row_count`/`matched_row_count`). G3 bị `count_column_alias`: COUNT(column)
  không đáp ứng alias/semantics đang cho phép. Không suy ra cột/alias cụ thể của
  draft bị chặn vì production không lưu raw rejected SQL. Cũng không suy ra
  grain/những bước sau đó chắc chắn đúng chỉ từ lỗi đầu tiên này.
- GH bị generator chủ động trả unsupported; không có raw unsupported_reason
  trong safe diagnostics. **Chưa biết** vì sao provider từ chối tạo SQL cho
  câu này; không quy cho guard COUNT khi chưa có bằng chứng.
- Kết quả xác nhận generation contract chưa được model tuân thủ ổn định dù
  offline golden/guard tests xanh. G2 PASS không chứng minh JOIN ba bảng hay
  mọi câu hỏi đã ổn định. Pass-rate 3/8 (37,5%) chỉ của tám probes cố định này,
  không phải ước lượng accuracy toàn hệ thống.

Không nới alias/COUNT semantics, không tự sửa cột/grain và không thêm repair loop
trong lượt nghiệm thu. Bước tiếp theo đề xuất là offline counterexamples cho
COUNT contract và cách đưa schema/examples cho từng gateway, bảo toàn COUNT(*)
khác COUNT(nullable), identifier grain và security assertions; mọi probe live
mới cần ngân sách/phê duyệt riêng.

### History, runtime và dữ liệu bảo vệ

Reload thật tab 8080, mở lại bốn conversations synthetic bằng UI: đủ tám câu trả
lời, model attribution, ba kết quả SQL 50/50/15 dòng và năm lời từ chối còn đúng.
Mở bảng Gemini 15 dòng sau reload và đối chiếu IDs/tên/Decimal/count. Đọc lại tám
assistant messages chỉ trong workspace 13: content và response_metadata (SQL,
rows, model/fallback) bằng chính bản evidence chụp lúc nhận kết quả; không gửi
generation mới để kiểm tra history. Không xuất cookie/token/session secrets.

Đối chiếu lại **26 bảng nghiệp vụ cũ**: counts và SHA-256 không đổi, aggregate
`f73b828698b29380b28b5ae89a654df52115bef858ed7a4c246a2b11c84fa736`.
Chỉ loại đúng workspace synthetic 13 và chat messages gắn với conversation của
13, ba bảng auth có login bình thường, cùng counters vận hành như baseline;
không loại lịch sử/nghiệp vụ của workspace khác. Không tuyên bố toàn DB bất biến:
lượt test cố ý thêm 4 conversations/16 messages và 1 document/chunk cho 13.

API/web/DB vẫn đúng ba services healthy, `/api/health` OK, DB container/volume
không đổi; resolved Compose so env runtime có **0 khác biệt**. Không rebuild,
migration, reset, restore, Docker cleanup, VPS hoặc Langfuse trong lượt này.
Giữ nguyên synthetic workspace/lịch sử để tái kiểm tra, không tự xóa.

Private evidence ngoài repository:
`C:\Work\ShopQuery-Backups\live-gate-d-20261021` gồm ledger, oracle, tám response
synthetic, safe stage diagnostics và ảnh UI sau reload. Oracle SHA-256:
`bda5e5aac8a08af94713c66778b1357ac5831a306db36aa999ea834c15f587ee`.
Không commit raw responses, logs, screenshots hay synthetic source files.

Lượt này chỉ cập nhật báo cáo; không sửa source nên không chạy lại test suite lớn.
Kết quả Ruff/1,107 backend/66 FE unit/105 browser mock và CI xanh đã ghi ở trên
thuộc source đã triển khai, **không biến năm live failures thành PASS**. Không
commit/push mới trong lượt phê duyệt ngân sách này. Kết luận Gate D: **FAIL**;
hệ thống chưa sẵn sàng để cam kết JOIN/Hybrid live ổn định trên cả hai providers.
