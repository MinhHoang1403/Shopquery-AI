# Sửa correctness và trình bày kết quả sau bàn giao

Baseline: main `1f7871a16c16f9b840703e50199ec81f41269a9c`, API application
`3fe4cc2`/image `d8ad8aa5`, Web `02d5cbb`/image `ae181335`. Một deployment 8080;
không đổi DB/schema, model, gate, fallback, Guest policy, embedding hoặc Langfuse.
Đây là hồ sơ của bản sửa; CI/live/image cuối phải được cập nhật bằng kết quả thực tế.
Chưa có kết quả live của bản sửa tại thời điểm lập hồ sơ.

## Nguyên nhân và mức chắc chắn

| Scenario | Provider | Route/boundary | Bằng chứng | Kết luận và sửa |
| --- | --- | --- | --- | --- |
| COUNT + SUM bị từ chối | Gemini | SQL → compilation/join_graph | `16228c7c4d5f49aea095124980194fe5`, `acb411b2b5234d26b717181a55dfccd4`; 2 calls, chưa execution, `dimension_group_key` | Xác nhận không phải router hoặc JSON conversion. Không có raw plan lịch sử nên grouping/projection chính xác còn UNKNOWN. Regression tái hiện bug riêng: scalar aggregate với grouping=category bị bắt có category key dù không có dimension projection. Chỉ sửa scalar direct aggregates; giữ fact/N:1/COUNT/type guards. |
| JOIN theo entity bị lỗi | Knowledge | sql_plan_generation/request | `2ebd4e13cafa48b2b52d2123b5ee388d`, timeout attempt 1 | Timeout upstream, không có bằng chứng binder/compiler sai ở lượt này. Không tăng timeout/retry hoặc dùng fallback để che lỗi. |
| Hybrid scope incomplete | Gemini | policy_verification | `f34fdb7c2f184b3cb0f61c6d6b968e54`, 8 SQL rows, `policy_sql_scope_incomplete` | Verifier cũ chỉ nhận all-row rule trong single chunk; tài liệu nhiều chunk có kỳ/trạng thái không nhận thành policy. Model fallback plan có scope qualifiers nên guard từ chối đúng. Bổ sung complete-document grammar và full-column scope proof; không xóa filters để vượt guard. |
| Hybrid unknown reference | Knowledge | plan_binding | `92279dd317c448399b48fd31afcb3856`, `unknown_reference`, chưa SQL execution | Xác nhận reference không thuộc catalog/graph hợp lệ; raw token/reference cụ thể không được lưu nên UNKNOWN. Gửi issued-ID enums request-local trong wire schema Knowledge; local binder vẫn là authority, không remap ID đoán mò. |
| Follow-up thiếu kiểu literal | Knowledge | domain_conversion | `d8f1f7a971ed45e58d39a0fdff115b4d`, expressions[0].value_type, `literal_type_missing` | Literal đã dùng sentinel none; schema cũ cho phép tổ hợp này dù conversion từ chối. Chia wire anyOf thành literal/nonliteral với enum rời nhau, giữ local conversion. Không đoán kiểu từ giá trị. |
| Ngày xuất hiện ở metric | Gemini | SQL projection → stored rows → UI | Stored response có literal DATE được SELECT với alias giống tổng; registry/CSV date và numeric đúng | Không phải formatter đổi tiền thành ngày. Unverified draft chỉ kiểm metric alias tồn tại, chưa bắt source lineage. Chặn metric constant cả khi unverified; result metadata lấy kiểu/provenance/header thực từ compiler, không lấy ngữ nghĩa từ alias. |
| Văn trả lời SQL | Cả hai | deterministic presenter | Trước đây ghép raw alias vào câu | Dùng verified aggregate metadata/COUNT provenance để soạn summary; nhóm lớn chỉ nêu số nhóm, ranking chỉ từ verified sort/limit. Không thêm generation call hoặc tự thêm đơn vị. |
| Bảng lặp/thiếu phân cấp | Cả hai | ResponseEvidence | Inline table mặc định và cùng bảng ở detail panel | Summary riêng; bảng/SQL/citation mặc định thu gọn. Một bảng structured với pagination; subset chỉ khi verified metadata, luôn có cách xem toàn bộ SQL evidence. |

Không lấy log branch/error category làm bằng chứng raw plan đã được chụp. Private logs,
history, SQL và registry chỉ lưu ngoài Git. Không thay masking production để chẩn đoán.
Ba CSV local khớp ZIP gốc và toàn bộ values khớp PostgreSQL; independent read-only oracle
đã xác nhận các tổng, grouping, ranking và boundary operator được operator nêu.

## Phân chia trách nhiệm và lựa chọn

Kết hợp ba thay đổi độc lập: A — wire contract và scalar grouping tối thiểu;
B — complete policy evidence/typed classification intent/scope proof;
C — typed result provenance/deterministic summary và collapsed evidence UI.
Không thêm SQL generator, provider, queue/service hoặc answer-rewrite model call.

- `generation_contract.py::generation_catalog`, `_expression_schema`: ContextVar request-local,
  source/column/relationship IDs được cấp; expression IDs vẫn kiểm DAG/depth local.
  `planner.py` chỉ scope schema trong lời gọi hiện hữu. Hai SDK có tests wire serialization.
  Gemini giữ wire grammar đã nghiệm thu; enrichment enum/conditional chỉ gửi Knowledge.
- `join_policy.py::_validate_entity_groups`: aggregate vô hướng không có dimension key;
  chỉ direct aggregate projections và không GROUP BY mới đi nhánh này. Không thay fanout guards.
- `natural_policy.py::_parse_regulation`: thêm một ngữ pháp đóng cho quy định tổng tiền có
  kỳ/trạng thái, không dùng model-extracted rule làm authority. Entity, field/key, ngày,
  status, threshold và currency lấy từ tài liệu; mọi câu được consume. Chỉ hỗ trợ cấu trúc
  điều khoản đã kiểm; ngoại lệ/quy tắc thứ hai/unknown text bị từ chối.
  `regulation_title_supported` kiểm cả section headings và kỳ trong tiêu đề: không bỏ
  điều kiện chỉ dành tập con hoặc mâu thuẫn tháng/năm. Hai negative tests mới từng chứng
  minh SQL chạy trước khi nhận thiếu bằng chứng, nay phải dừng trước execution. Positive
  fixtures dùng tiêu đề thuộc vocabulary được công bố; tên/heading tùy ý chưa được hỗ trợ.
- `DocumentRepository.retrieve`/`complete_policy_evidence`/`policy_content`: lấy sibling chunks
  đã đăng ký của các tài liệu được truy xuất, giữ ID/title/hash/owner/workspace; bỏ đúng
  overlap tối đa 30 từ của chunker. Tối đa 20 chunks/60.000 ký tự, không embedding lần hai.
- `DatasetRepository.column_profiles`: read-only COUNT(*), COUNT(column), MIN/MAX toàn cột
  TEXT/temporal, không sample; registry owner kiểm lại, timeout 3 giây, một query/table.
  Scope chỉ được chứng minh tương đương toàn bảng nếu đủ non-NULL, mọi ngày trong kỳ,
  duy nhất status đúng tài liệu và cột DATE/status không mơ hồ. Nếu có dòng ngoài scope
  thì từ chối; chưa mở rộng sang arbitrary filtered policy plans.
- `hybrid_coverage.py` nhận typed classification intent từ route hiện hữu. Intent không phải
  policy authority. `verified_policies`, cả hai lớp coverage, Decimal evaluate và answer composer
  tiếp tục kiểm độc lập trước/ sau SQL. Unsupported policy dừng sớm khi đã biết intent classification.
- `hybrid_evidence.py::compose_answer`: unverified metric cũng cần column/aggregate lineage;
  COUNT(*) vẫn hợp lệ. `verified_classification` giữ mọi citation cần cho tài liệu đầy đủ.
- `compiler.py::_result_column`: data_type/provenance/aggregate/source_label theo expression
  thực; labels không suy từ alias. Identifier có số 0 đầu giữ nguyên. DATE/TIMESTAMP không
  opt-in numeric. Metadata đi qua API/history cùng schema ResultColumn hiện hữu, defaults
  giữ tương thích lịch sử.
- `answer.py::compose_sql_answer`: cùng một presenter cho hai providers; COUNT row/value
  phân biệt, Decimal exact, NULL không thành 0, không suy money/unit từ tên cột.
- `ChatMessage`/`ResponseEvidence`: verification label rõ; một detail table thu gọn,
  keyboard/aria-controls/expanded, pagination, SQL đầy đủ và citation panel độc lập.
  Không đọc số từ câu văn, không tự tính KPI.

Ví dụ synthetic: trước `Anything: 0.00` → sau `Tổng Số tiền đã đóng là 0,00`.
Trước bảng 32 dòng mặc định → sau summary số nhóm và nút `Xem bảng dữ liệu · 32 dòng`.
Đơn vị chỉ hiện khi nguồn xác minh hỗ trợ; summary không tự gắn “đồng” cho một NUMERIC.

## Kiểm thử và kết quả

- Before fix: 5/7 structural regression FAIL (scalar/category, literal schema và 3 metric
  constant cases); cả 2 UI regression mới FAIL (bảng chưa thu gọn, thiếu verification label).
- Targeted backend đã chạy: 213 PASS; lượt contract/API cập nhật: 60 PASS; lượt sửa tương thích
  fixture/Decimal/COUNT/diagnostics/presenter/Guest: 180 PASS. Các suite có overlap, không cộng.
- Whole-document/scope unit: 17 PASS trên ba entity/schema/threshold biến đổi và 14 negatives,
  gồm hai ca điều kiện/kỳ chỉ xuất hiện trong section title. Lượt targeted sau sửa: 163 PASS
  (có overlap với các suite trên, không cộng).
- Frontend local: 87 PASS, lint/typecheck/build PASS. E2E assertions cập nhật theo hành vi
  được yêu cầu; không bỏ các assertions về giá trị, pagination, privacy hoặc accessibility.
- Full backend local ban đầu 1.404 PASS/17 FAIL: 11 fixture contracts dùng string thay typed plan,
  5 wording assertions cũ và 1 Guest process timing failure. Đã tách presentation flags vào
  CompiledQuery, cập nhật assertions đúng metadata/ngữ nghĩa; Guest timing giữ nguyên và
  targeted chạy lại PASS. CI sạch là kết quả full authoritative tiếp theo.
- PostgreSQL tests mới: scalar COUNT/SUM/AVG so independent fact SQL trên 6 domains ×2 grouping;
  scoped regulation/whole-document/owner proof trên 3 schema × positive/out-of-period.
  Chỉ chạy ở isolated CI, không tạo local test containers.
- Deterministic source check trên workspace hiện hữu: source mới, guarded read-only SQL,
  đủ 8 entities/tổng đúng oracle/citations 50,51/verified_classification. Reuse document vector
  đã lưu và mock router; 0 paid calls. Không gọi đây là live model acceptance.

PR [#2](https://github.com/MinhHoang1403/Shopquery-AI/pull/2) đã squash merge main
`b75a844b959ccd0d268a11ac10f99ab0326813d4`; CI PR và main đều PASS. Guard bổ sung
section title ở main `937a828662c68516ba008ce1d5b6f459749bc498` có
[exact-head CI 40550706754](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/40550706754)
4/4 jobs PASS: 1.423 backend, 875 PostgreSQL, 87 frontend, 125 mock E2E,
10 maintenance checks và 10 Compose checks. Các tests mock/CI không thay live model acceptance.

Image ứng viên API `sha256:6a63244725d904b3866e34298a46a4289a77b0a5144b45735123a1e141ee8116`
được build từ `937a828`; Web `sha256:9b735b38e62a19f9e1f8426b10c1774bedc30ae07d23cbda6cae75db1237a23f`
từ `b75a844` có inputs không đổi. API ứng viên trước `d7f2d822` bị loại trước triển khai
do hai negative tests mới; chưa dùng image đó phục vụ người dùng. Effective candidate
Compose chỉ đổi hai image refs; cấu hình rollback và DB archive đã được kiểm.

### Cửa sổ live 28/10/2026 — BLOCKED

Operator đã duyệt và cutover hai images trên. Strict verifier PASS 88 modules, không
source/image/env drift; API/Web healthy, main DB container giữ nguyên. Fingerprints 36 data
objects và 292 messages lịch sử (đến message366) khớp baseline trước khi gửi câu đầu.

Câu Gemini COUNT+SUM duy nhất được gửi một lần. Router SQL PASS; QueryPlan generation
bị Gemini từ chối HTTP400/schema_rejected/phase=request, trước binding/compile/execution.
Correlation `43dc10ac9cf14ec4b47d7133c4e8cdc4`, lúc 00:42:45 28/10 giờ Việt Nam.
Messages367/368 được persist; không có SQL rows. Langfuse có 14 observations, đúng một
root và hai generation observations; mọi raw input/output absent. Router trả 1.867 input,
39 output, 1.906 total tokens; rejected planner call không trả usage, phần đó UNKNOWN.
Request 5.253ms, planner failure 140ms; không embedding/retry/fallback. Cửa sổ đã dừng
ở 2/36 generation, 0/12 query, 0 document; không dùng phần dư để thử lại.

API đã rollback về `d8ad8aa5`/source `3fe4cc2`; giữ Web mới `9b735b38` và toàn bộ config
model/gates/Langfuse. Nginx validate/reload,8080 health PASS. Đây là rollback có chủ đích:
API đang chạy chưa khớp source main của bản sửa, không tuyên bố strict/current-main PASS.

New failure boundary được xác nhận là request schema tại Gemini, không phải SQL/JOIN/RAG.
Không có error body chi tiết nên không kết luận chính xác enum hay anyOf gây HTTP400.
Google công bố schema branching/enum complexity có thể bị từ chối400; đây chỉ là giả thuyết
về lý do bên trong server, không phải bằng chứng cho request cụ thể.

Correction offline: Gemini tắt riêng wire enrichment khi dựng schema, giữ contract native
đã chạy trước cutover; local validation/conversion/catalog/binder/SQL guards không đổi.
Fixture `gemini_plan_schema.json` được chụp từ SDK pinned trong API baseline bằng
MockTransport, không network/provider. Regression từng FAIL trước sửa, sau sửa so toàn bộ
serialized responseSchema bằng fixture (kể cả khi request có nhiều issued IDs). Knowledge
vẫn giữ constraints và không bị ContextVar của Gemini làm thay đổi. Targeted 85 PASS;
CI/image/live của correction này còn phải hoàn tất, không coi mocks là provider acceptance.

## Ngân sách và triển khai

Cửa sổ mới được yêu cầu cho phép: tối đa 36 generation stages (hai providers cộng dồn),
12 query embeddings, 0 document embeddings; một attempt/stage, không retry/fallback.
Trước cutover/live: 0/0/0. Normal operation gate ON giữ nguyên, không dùng dư ngân sách cũ.
Chỉ build API/Web đã đổi inputs sau CI; PostgreSQL/Langfuse/volumes không recreate.
Pin immutable images và rollback trước khi xin duyệt thời điểm cutover theo runbook.

## Căn cứ và giới hạn

Wire JSON Schema là ràng buộc cấu trúc, không tự chứng minh đúng ngữ nghĩa. Đối chiếu
[tài liệu Google](https://ai.google.dev/gemini-api/docs/structured-output?hl=en) với
serialization thực của SDK pinned trong tests. anyOf/enum vẫn phải qua conversion/binder.
Scope proof dùng COUNT khác COUNT(column) để phát hiện NULL, rồi MIN/MAX; semantics theo
[PostgreSQL 17](https://www.postgresql.org/docs/17/functions-aggregate.html).

Không hỗ trợ mọi văn bản chính sách, mọi kỳ có dữ liệu ngoài phạm vi, nhiều quy tắc hoặc
ngoại lệ. Không giả tạo filtered-policy support bằng cách bỏ WHERE/HAVING/LIMIT.
Timeout Knowledge vẫn phụ thuộc upstream; không đổi retry/fallback. BGE/public hosting,
retention/backup Langfuse ngoài phạm vi. Không báo CORRECTNESS_FIX_ACCEPTED trước live.
