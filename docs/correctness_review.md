# Sửa correctness và trình bày kết quả sau bàn giao

Baseline: main `1f7871a16c16f9b840703e50199ec81f41269a9c`, API application
`3fe4cc2`/image `d8ad8aa5`, Web `02d5cbb`/image `ae181335`. Một deployment 8080;
không đổi DB/schema, model, gate, fallback, Guest policy, embedding hoặc Langfuse.
Application hiện hành: API `29bb788`/image `5675513a`, Web `b75a844`/image `9b735b38`.
**Kết luận nghiệm thu toàn bộ: RELEASE_BLOCKED.** Các sửa đổi đã triển khai và có các
bounded live PASS bên dưới; không tuyên bố tất cả gate đều đạt. Không có release tag.

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
Không coi mocks là provider acceptance. Correction `29bb788314b965d63b218a50898ab91d74faf0a3`
đã có [CI40554366778](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/40554366778)
4/4 PASS: 1.424 backend,875 PostgreSQL,87 frontend,125 mock E2E,10 maintenance và10 Compose.
Chỉ API build lại thành `sha256:5675513a90921b713413b8dda5391a9c0dfb2b24acbdb60edf4b9f96446f14b0`;
Web không build lại. Operator duyệt API-only cutover và cửa sổ live mới; strict88 modules,
source/image/env và health PASS, Web/main DB/Langfuse giữ container hiện tại.

### Scorecard trên API29bb788 — cửa sổ mới đã đóng

Mỗi câu được gửi một lần qua UI8080, không retry/fallback/paid diagnostics. Không đổi
nguồn dữ liệu hoặc hỏi lại bằng cách diễn đạt khác. Có8 câu thực gửi; hai ca Knowledge
còn lại không gửi sau403, follow-up Knowledge không có premise verified.

| Scenario | Provider | Kết quả | Bằng chứng/đối chiếu |
| --- | --- | --- | --- |
| Giao nhận COUNT+SUM | Gemini | BLOCKED | `e4f156165f844fffb229817f1abd3c27`, router504/transient_unavailable/29,786s,1 generation, chưa plan/execution; không gán lỗi scalar grain cho lượt này |
| Giao nhận JOIN kho | Knowledge | BLOCKED | `1ce319b88cb84e79b65e63bc393bb00c`, router403/authentication_or_permission/1,934s,1 generation, chưa plan/execution |
| Giao nhận KPI | Gemini | PASS | `789dfd9a50154500b891a1050c332597`,10,169s;8 entities/tổng từng entity đúng independent PG oracle;K04–K08 đạt,K01–K03 chưa; K04/K05 bằng ngưỡng vẫn đạt; citations50,51; verified_classification |
| Follow-up chưa đạt | Gemini | PASS | `c1fca8d1d2df4545b67be611a7072750`,2,909s; cùng conversation với premise message374; context_used=true; SQL giữ8 rows, backend subset[1,4,6] đúng K01–K03; citations50,51/verified persistence |
| Chính sách trạng thái Xe điện | Gemini | FAIL false refusal | `0029c4817bae4798b03ee83ece0ea832`,5,112s; câu chỉ hỏi quy tắc nhưng route HYBRID, planner model_unsupported; có2 generation/1 query embedding, chưa execution. Chunk23 ghi rõ “Tính mọi trạng thái” |
| Khách sạn có trên100 phòng | Gemini | PASS | `78d6aef6992b41808e53d851328d0d6f`,47,203s;16 IDs/names khớp independent SELECT từ main PG;2 generation, không embedding |
| Ba mã/ngày/phí đầu tiên | Gemini | PASS | `5964c832099b480eb010bad3b371332e`,10,120s;3 rows khớp independent PG oracle; DATE numeric=false, BIGINT exact integers, TEXT giữ DG0001..DG0003 |
| Nhân viên giao trễ nhiều nhất | Gemini | PASS safe refusal | `43d3a1c8189140cc81290897db55118c`,6,268s; registry không có employee/late-delivery evidence; route UNSUPPORTED,1 generation, không SQL/rows/embedding |
| KPI và follow-up | Knowledge | NOT_RUN | Không gọi thêm sau403; không dùng Gemini fallback hoặc thừa nhận premise chưa được xác minh |

Native Gemini wire compatibility đã có bằng chứng live mới: planner ở ca Xe điện trả
unsupported đúng wire/domain contract (semantics của route vẫn FAIL), và hai ca SQL
Khách sạn/DATE đã parse/compile/execute, rows đúng oracle. Không suy từ đó rằng COUNT+SUM
hoặc Knowledge wire đã live PASS. Literal/catalog constraints Knowledge mới chưa được
nghiệm thu live vì403 xảy ra trước schema generation.

Knowledge403 còn được xác nhận bởi một GET models không generation từ chính API
container: HTTP403/JSON105bytes, không WWW-Authenticate hoặc request-ID header. Cấu hình
provider không đổi giữa candidate/rollback/API cuối. Lý do chi tiết và quyền phía server
còn UNKNOWN; không suy đoán cần API key cụ thể, không đổi endpoint/credentials/model.

False refusal Xe điện nằm ở `QueryRouter.route`: classifier chọn HYBRID cho yêu cầu chỉ
tra điều kiện áp dụng trạng thái. `HybridPipeline` sau đó đi tới planner; planner trả
unsupported nên service trả safe refusal. Không phải thiếu tài liệu23 hoặc SQL executor.
Không có raw reason/plan để xác định vì sao model chọn HYBRID. Chưa có bản sửa tổng quát
được chứng minh; không vá prompt theo nguyên câu hỏi hoặc thêm RAG retry/fallback để
biến mẫu này thành PASS. Đây là blocker correctness còn thực sự tồn tại.

UI live: Hybrid không có inline table; bảng/SQL/citation thu gọn độc lập. Follow-up mở
đúng3 entities của câu trả lời, nút xem toàn bộ8 SQL rows vẫn hoạt động. History table32
rows pagination1–20→21–32 và thu gọn lại PASS; chỉ có một table khi mở,0 khi thu gọn.
DATE hiển thị ISO và TEXT IDs giữ số0 đầu; BIGINT trực tiếp hiển thị nguyên digits vì
formatting opt-in không đồng nghĩa với SQL numeric type. Private oracle check ban đầu
đòi numeric=true cho direct BIGINT là sai contract; đã sửa assertion ngoài source để
kiểm BIGINT/provenance/exact integer values, không sửa application để làm check PASS.

Langfuse:9 traces/9 roots/246 observations,13 generation observations và3 query embeddings,
0 document embeddings; observation IDs duy nhất, số call khớp diagnostics cho từng root.
26.356 generation tokens có SDK usage khớp root totals;3 failed calls không có usage,
không coi là0. Embedding tokens UNKNOWN. Live kiểm full metadata của246 observations:
raw input/output absent; không có question/SQL, owner/conversation UUID thật, Gemini key,
Langfuse secret hoặc private Knowledge URL. SDK public key không phải secret. Gemini cost
inferred/estimated, Knowledge cost UNKNOWN. Dashboard đã mở trace schema400 và verified KPI;
không chỉ dựa mocks hoặc một trang UI truy cập được.

Sau acceptance đã kiểm cuối: fingerprints36 data objects và292 old messages≤366 không đổi,
thêm đúng18 messages của9 requests trong hai cửa sổ (310 messages, max384). Không upload/re-embed/migrate/delete
hoặc sửa history cũ. Các raw evidence/oracle/screenshots/configs/DB archive nằm private,
không commit. DB archive đã kiểm229 entries nhưng chưa làm restore drill.

## Ngân sách và triển khai

Cửa sổ mới được yêu cầu cho phép: tối đa 36 generation stages (hai providers cộng dồn),
12 query embeddings, 0 document embeddings; một attempt/stage, không retry/fallback.
Cửa sổ đầu đã dừng ở2 generation/0 embeddings sau schema400. Operator duyệt cửa sổ mới
tối đa10 câu/24 generation/8 query/0 document, tổng nhiệm vụ không vượt36/12/0.
Cửa sổ mới kết thúc:8 câu,11 generation/3 query/0 document. Tổng thực tế13/36 generation,
3/12 query,0 document; không reset theo batch hoặc dùng phần dư sau khi đóng. Normal
operation gate ON giữ nguyên, Gemini default/fallback OFF/Guest OFF; không gọi thêm provider.
PostgreSQL/Langfuse/volumes không recreate. Rollback d8ad8aa5/ae181335 và configs được giữ;
API candidates d7f2d822/6a632447 bị loại, không dùng phục vụ sau correction cuối.

## Căn cứ và giới hạn

### Bổ sung điều tra provider28/10/2026

Yêu cầu bổ sung giữ nguyên công việc và dữ liệu; không mở lại audit kiến trúc. Các
thay đổi provider dưới đây chưa được coi là đã triển khai cho tới cutover/strict riêng.
Runtime trong lượt điều tra vẫn API29bb788/Webb75a844. Working tree chứa sửa errors,
Gemini response handling, tests và tài liệu của chính nhiệm vụ; không reset/gộp file ngoài scope.

#### A. Nguồn chính thức và SDK thực

Đã đọc [Google troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting),
[API errors](https://ai.google.dev/gemini-api/docs/api-errors),
[structured output](https://ai.google.dev/gemini-api/docs/structured-output),
[API keys](https://ai.google.dev/gemini-api/docs/api-key),
[rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) và
[Python SDK](https://github.com/googleapis/python-genai). Trang API errors hiện mô tả
Interactions API; ứng dụng này dùng GenerateContent/v1beta, không sao chép giao thức
`error.code` dạng snake_case của Interactions vào parser SDK GenerateContent.

SDK được kiểm từ container/source cài đặt: google-genai1.75.0, OpenAI3.35.1,
langchain-openai1.7.2/langchain-core1.6.12, Pydantic2.14.1, httpx0.28.1/httpx2.13.1.
Không nâng dependency. Container có Gemini key, client truyền key tường minh, endpoint
public generativelanguage.googleapis.com/v1beta, không Vertex hoặc custom-base/proxy env.
Models đúng gemini-3.5-flash-lite/gemini-embedding-2; gateON/defaultGemini/fallbackOFF/
GuestOFF. Knowledge key không lấy từ Gemini. Runtime env không đổi trong các cutover
ngoài image refs; quyền bên trong Google project/key restrictions không thể suy từ Settings.
Các generation live PASS chứng minh quyền với requests đã chạy; không chứng minh mọi
model/resource hoặc quyền không bao giờ thay đổi. Không tạo/đổi key hay gửi key qua chat.

Google chỉ hỗ trợ JSON Schema subset; anyOf/enum/type/required không xác minh semantics.
Native Schema của SDK pinned có projection khác raw JSON Schema; response_mime_type vẫn
application/json, response_schema lấy từ Pydantic rồi transform đã kiểm. Keywords local
bounds bị lược khỏi wire để giữ grammar đã chạy; Pydantic vẫn kiểm nguyên bounds và
domain/binder kiểm DAG/types/references. Không tự bỏ filters/fields của output. Bản sửa
Gemini wire trước đó đã có planner/SQL live PASS, không suy raw400 do enum nào cụ thể.

Retry đối chiếu chính
[google-genai v1.75.0](https://github.com/googleapis/python-genai/blob/v1.75.0/google/genai/_api_client.py):
options attempts là tổng số attempts, gồm initial; retry mặc định của SDK có5 attempts
nhưng runtime đã ghi đè1. Với policy cho phép, SDK retry APIError408/429/500/502/503/504,
httpx Timeout/ConnectError bằng exponential jitter; không có xử lý Retry-After trong
`retry_args` phiên bản này. Không tăng attempts hoặc viết retry layer. OpenAI
[v3.35.1](https://github.com/openai/openai-python/blob/v3.35.1/src/openai/_base_client.py)
dùng max_retries (không gồm initial), Knowledge đặt attempts−1=0; có bounded retry/backoff
và Retry-After khi được bật. Tests kiểm cả attempts1 và policy3:401/403/402/404/400 không
retry trong responses thông thường. Không bật retry/fallback trả phí để che lỗi.

Google rate limits áp dụng theo project, gồm RPM/TPM/RPD và tùy tier/model;429 không tự
phân biệt daily quota/rate limit nếu không có code bằng chứng.402 ở API có hỗ trợ biểu
thị payment/prepay; không suy billing issue chỉ vì403.404 không chứng minh model ID sai
thay vì resource/path khác.504 biểu thị deadline timeout, không chứng minh lỗi SQL hoặc
thiếu key. Trang key mô tả quyền/project restrictions và các key types; việc key có mặt
không chứng minh quyền. Không áp dụng tài liệu Google để chẩn đoán Knowledge authentication.

#### B. Knowledge transport và phép kiểm lại được operator duyệt

`InetCloudGateway.__init__` dùng ChatOpenAI, configured HTTPS base có suffix/v1,
model knowledge, Chat Completions không Responses, Bearer placeholder `not-required`,
temperature0, timeout60s, max_retries0. Không proxy env trong container. Tests qua đúng SDK
chứng minh path /v1/chat/completions, response_format=json_schema/strict=true/include_raw,
không tools/max_tokens hoặc Gemini key. `ModelChatService` fallbackOFF không phát call
thứ hai; LazyGeminiEmbedder độc lập không thay generation provider.

Trace1ce319b8 được xác nhận provider knowledge/model knowledge/HTTP403/phase request,
origin routing, requested=used=inetcloud-knowledge,attempt1. Generation khoảng0,42s,
root1,934s, chưa route result/plan/execution; tokens/cost không có upstream là UNKNOWN.
Không có hợp đồng auth chính thức hoặc server logs nên **ROOT_CAUSE_UNKNOWN** về lý do
403: chưa xác nhận missing key, IP allowlist, project/model restriction hay gateway policy.
Placeholder đã từng đi cùng bounded live passes; không tự xóa Bearer, gửi key khác hoặc
đổi endpoint. HTTP401/403 gộp trong nhãn cũ không đủ để khẳng định sai authentication.

Một GET models không generation trước đó trả403; phép kiểm đọc bổ sung28/10 trả200
cùng endpoint/config/Bearer, không redirect. Điều này chỉ chứng minh endpoint đọc trả lời
tại thời điểm đó. Operator yêu cầu “Thử gọi lại knowledge… không cần tắt”; đã gửi một
câu SQL mới trên dataset17 qua UI, không retry stage. Trace
`4b3bdf15f45c40b1bc54aad328f9c66d`,message386: SDK timeout ở routing sau61,273s,
không có HTTP response/status,1 generation/0 embeddings/không SQL. **UPSTREAM_BLOCKED**;
không gán timeout thành403 hoặc tuyên bố generation access phục hồi. Giữ Knowledge manual
và config như operator yêu cầu; không gọi thêm cho đến khi có trạng thái mới.

Phía quản trị iNetCloud cần xác nhận auth/ACL/model-access convention của configured
gateway, đối chiếu request403 và timeout theo thời điểm/trace tương ứng, gateway upstream
health/queue/deadline và access logs. Chưa có request-ID header upstream để liên kết chắc
chắn với nội bộ server; correlation ID của ShopQuery là định danh phía ứng dụng, không
giả định provider đã nhận cùng ID. Không gửi raw logs/private URL tới bên ngoài tự động.

#### C. Bản sửa có failing regression trong lần bổ sung

`core/errors.py::provider_category` trước gộp401/403,402/404 vào generic request_rejected
và504 vào unavailable. Mock cả hai SDK chứng minh việc gộp làm mất lớp lỗi cần phân biệt.
Sửa status→category, giữ raw HTTP/provider/operation/phase/correlation; category legacy
authentication_or_permission giữ cho app auth/history tương thích. Không suy nguyên nhân
sâu hơn status. `error_message` thêm lời giải thích an toàn, không raw exception.

| HTTP/signal | Category sau sửa | Retry/runtime | Mức nguyên nhân |
| --- | --- | --- | --- |
|400 thông thường/schema/complexity|request_rejected/schema_rejected/schema_complexity|Không retry|Boundary xác nhận; keyword schema/complexity chỉ dùng nội bộ để chọn fixed enum|
|401|authentication_failed|Không retry|Xác thực bị từ chối; lý do key hết hạn/sai còn cần provider|
|402 nếu endpoint trả|payment_required|Không retry|HTTP payment boundary, không suy số dư cụ thể|
|403|permission_denied|Không retry|Quyền truy cập bị từ chối; ACL/project/model/auth convention UNKNOWN nếu thiếu bằng chứng|
|404|resource_not_found|Không retry|Model hoặc resource/path không tìm thấy, không tự đổi model|
|408/504 hoặc SDK timeout|timeout|Runtime1 attempt|HTTP deadline khác SDK timeout không có status|
|429|quota_or_rate_limit|Runtime1 attempt|Không tự đoán loại quota|
|500/502/503|transient_unavailable|Runtime1 attempt|Server/gateway unavailable, nội bộ UNKNOWN|
|Network exception|connection_failure|Runtime1 attempt|Khác HTTP denial hoặc schema|
|Prompt/candidate safety block|model_refusal,phase=response|Không repair|Không gọi JSON decode cho response đã blocked|
|Không text|invalid_response,phase=response|Không repair|Khác nonempty invalid JSON|
|Nonempty JSON lỗi|invalid_json,phase=json_decode|Không repair|Không chạy domain conversion/SQL|
|Pydantic/schema/domain lỗi|wire_validation/contract_conversion|Không repair|Local validation không bị bỏ|
|SDK preparation|sdk_preparation|Không dispatch bổ sung|Không đổ lỗi model JSON|
|Thiếu credentials/unknown local model|configuration|Không khởi tạo client|Không gửi key giả để thử|

`GeminiGateway._response_text` kiểm prompt_feedback.block_reason và candidate finish_reason
cho cả generate_structured/generate_text trước lấy text/parse. Trước sửa: prompt block
bị báo invalid_json, candidate block trong text path bị báo invalid_response, structured
empty bị báo invalid_json. Regression qua MockTransport FAIL trước sửa. Giữ nonempty
JSON parsing/wire/domain boundaries; không thêm network/model call hoặc đổi business output.

Tests mới test_provider_failures44 cases (HTTP11×2, blocked/empty6,invalidJSON1,
nontransient no-retry10,network4,missing config1), cùng8 Langfuse ERROR status tests.
Lượt targeted provider/observability212 PASS; sau đổi kiểm no-execution qua chính
DatasetChatService,44 provider tests PASS. Missing usage vẫn UNKNOWN, một observation
mỗi SDK dispatch, không duplicate generation/SQL execution sau failure; privacy assertion
kiểm metadata/history/log không chứa test secrets. Các regression SQL/policy/grain/
cross-owner/follow-up còn giữ, không sửa các oracle assertions để thích nghi model.
Lượt liên quan contract/conversion/coverage/context/COUNT/three-table JOIN/policy-scope:
247 PASS; các suite overlap không cộng. Ruff và git diff --check PASS.

#### D. Ma trận nguyên nhân theo boundary đã xác minh

| Scenario | Provider | HTTP | Stage | Reason | Root cause/mức chắc chắn | Fix | Verification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| COUNT+SUM lịch sử | Gemini | Không lỗi transport được ghi | compilation/join_graph | dimension_group_key | CONFIRMED boundary; raw grouping/projection UNKNOWN; regression xác nhận lỗi scalar/category | scalar direct aggregate exemption, giữ grain guards | Regression/PG oracle PASS; đúng câu live sau sửa bị504, chưa chấm PASS |
| JOIN kho lịch sử | Knowledge | Không response | sql_plan_generation/request | timeout | CONFIRMED SDK timeout; model server reason UNKNOWN | Không sửa JOIN dựa timeout | Upstream chưa nghiệm thu lại |
| Hybrid scope | Gemini | Không lỗi transport | policy_verification | policy_sql_scope_incomplete | CONFIRMED complete document chưa được parser nhận/scope chưa chứng minh | complete chunks/title/hash + full-column scope proof | Offline/CI và8entities live đúng oracle |
| Hybrid reference | Knowledge | Không lỗi transport | plan_binding | unknown_reference | CONFIRMED invalid reference boundary; token cụ thể UNKNOWN | request-local issued enums Knowledge; binder giữ | SDK/local guards PASS; Knowledge generation mới bị chặn upstream |
| Literal follow-up | Knowledge | Không lỗi transport | domain_conversion | literal_type_missing | CONFIRMED wire cho literal sentinel none nhưng domain từ chối | disjoint literal/nonliteral wire Knowledge; local conversion | Before/after regression PASS; không nhận failed premise |
| Ngày giả metric | Gemini | Không lỗi transport | SELECT→stored rows | metric constant | CONFIRMED literal DATE đã có trong SQL, không phải formatter | require source lineage + compiled type/provenance | Negative/PG PASS; DATE/IDs live đúng3rows |
| API schema mới | Gemini |400|sql_plan_generation/request|schema_rejected|CONFIRMED request boundary; enum/anyOf nguyên nhân server cụ thể UNKNOWN|restore accepted Gemini wire only|Exact SDK schema fixture + SQL16rows/DATE3rows live PASS|
| COUNT mới | Gemini |504|routing/request|transient_unavailable lịch sử; timeout sau mappingfix|CONFIRMED deadline HTTP; nội bộ UNKNOWN|Không đổi model/timeout/retry|Mock504 mapping PASS; không retry câu này|
| Provider403 | Knowledge |403|routing/request|authentication_or_permission lịch sử; permission_denied saufix|CONFIRMED denial; auth/ACL/model/root reason UNKNOWN|Specific mapping; giữ auth/config|Exactstatus/phase/attempt/ERROR span mock PASS; models GET lúc khác200 không đủ |
| Recheck operator | Knowledge |Không response|routing/request|timeout|CONFIRMED SDK timeout60s; UPSTREAM_BLOCKED|Không đổi access hoặc tắt lựa chọn|1attempt,0SQL; chờ operator cập nhật upstream|
| Policy-only question | Gemini |Không lỗi transport|routing→planner|HYBRID→model_unsupported|CONFIRMED false-refusal boundary; vì sao classifier chọn sai UNKNOWN|NOT_FIXED, không thêm prompt workaround/retry|Live FAIL được giữ, không cherry-pick|
| Block/empty response | Gemini |200 synthetic|response|safety/empty bị parse nhầm|CONFIRMED adapter order trước sửa sai|shared response guard trước parse|Failing regression trước sửa, targeted PASS|

Trạng thái phần bổ sung: mapping/safety fixes **FIXED_OFFLINE**; Knowledge access/service
**UPSTREAM_BLOCKED/ROOT_CAUSE_UNKNOWN**; root cause cụ thể của historical raw plans và
Gemini504 **UNKNOWN**; false refusal policy-only **NOT_FIXED** (đúng boundary routing→
planner unsupported đã có bằng chứng, chưa có deterministic semantic proof để sửa).
Không nâng SDK, đổi auth/key, SQL/JOIN/RAG algorithms hoặc tăng timeout/retries.

Sau lượt Knowledge bổ sung: tổng nhiệm vụ14 generation/3 query/0 document,10 requests,
thêm20 messages (max386),không reset13 stages trước. File yêu cầu mới cho phép dùng phần
ngân sách còn lại nhưng chưa phát thêm calls; không nghiệm thu Knowledge tiếp sau timeout.

Wire JSON Schema là ràng buộc cấu trúc, không tự chứng minh đúng ngữ nghĩa. Đối chiếu
[tài liệu Google](https://ai.google.dev/gemini-api/docs/structured-output?hl=en) với
serialization thực của SDK pinned trong tests. anyOf/enum vẫn phải qua conversion/binder.
Scope proof dùng COUNT khác COUNT(column) để phát hiện NULL, rồi MIN/MAX; semantics theo
[PostgreSQL 17](https://www.postgresql.org/docs/17/functions-aggregate.html).

Không hỗ trợ mọi văn bản chính sách, mọi kỳ có dữ liệu ngoài phạm vi, nhiều quy tắc hoặc
ngoại lệ. Không giả tạo filtered-policy support bằng cách bỏ WHERE/HAVING/LIMIT.
Timeout Knowledge vẫn phụ thuộc upstream; không đổi retry/fallback. BGE/public hosting,
retention/backup Langfuse ngoài phạm vi. Không báo CORRECTNESS_FIX_ACCEPTED trước live.
