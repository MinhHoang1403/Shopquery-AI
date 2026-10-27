# Nghiệm thu Langfuse và 8080 — 27/10/2026

Baseline `00415fb`, API `52701da8`, Web `ae181335`, Langfuse4.70.1/SDK5.0.4.
Một deployment8080, project observability riêng. Báo cáo này phân biệt coverage
trong source/tests với quan sát live; bảng live bên dưới sẽ ghi kết quả thực tế.

## Coverage từ source

Duration lấy từ thời điểm bắt đầu/kết thúc span SDK. Model/usage chỉ thuộc provider
observation; các stage backend deterministic không được gán token hoặc model giả.
Mọi metadata qua allowlist và export masking; không raw content/identity.

| Nhóm | Span / metadata | Model/token | Coverage source |
| --- | --- | --- | --- |
| Request/response | request, correlation, final_status, route, verified status, duration | measured subtotal metadata; không root usage_details trùng child | PASS |
| Authentication | authentication, status, HTTP401/403 category; chỉ request được theo dõi | NOT_APPLICABLE | Bổ sung |
| Context/follow-up | conversation_context, context_used; không nội dung tiền đề | NOT_APPLICABLE | Bổ sung flag |
| Router | routing + generation_contract + generation; explicit route không model call | provider thực khi có dispatch | PASS |
| SQL planner | sql_plan_generation; coverage plan dùng plan_construction deterministic | generation chỉ khi thực gọi | PASS |
| Generation contract | generation_contract, status, phase/error_category | child generation giữ usage dù parsing/conversion lỗi | Bổ sung |
| Binding | plan_binding, status/error; chỉ khi bind_approved_grain chạy | NOT_APPLICABLE | Bổ sung |
| JOIN | relationship_approval, approved_edges, join_graph; không export IDs/keys/SQL | NOT_APPLICABLE | PASS |
| Compiler | plan_compilation, status/error | NOT_APPLICABLE | PASS |
| AST/guards | sql_validation, sql_parse_error, schema_metadata, column_resolution, join_graph | NOT_APPLICABLE | Bổ sung outer span |
| Executor | execution_guard, sql_execution, result_rows, execution_reached | NOT_APPLICABLE | PASS |
| Embedding | query_embedding/document_embedding, actual model, latency, calls | SDK1.75 không có token field; UNKNOWN; billable characters riêng nếu có | Bổ sung characters |
| Retrieval | document_retrieval, retrieved_chunks/selected_chunks | child embedding, không vectors/chunk contents | Bổ sung counts |
| RAG answer | answer_grounding, citation_count | child generation | Bổ sung count |
| Hybrid | hybrid_pipeline, policy_requirements, plan_coverage_validation, policy_verification, verified status/citation_count | không generation giả khi backend tự phân loại | Bổ sung citation count |
| Persistence | response_persistence, status/error/duration | NOT_APPLICABLE | PASS |
| Provider/fallback | requested_model/used_model, fallback_used, fallback_error_category | mỗi dispatch đúng một observation | Bổ sung attribution khi failure |
| Errors/refusals | fixed category/phase/origin_stage/verification reason, root failure/unsupported | failed consumption nếu SDK cung cấp; khác UNKNOWN | PASS với giới hạn provider |
| UI render/reload | API không thể đo browser render bằng backend span | NOT_APPLICABLE; kiểm UI riêng | NOT_APPLICABLE |

### Kiểm trực tiếp các cột telemetry

Mọi stage backend có duration từ SDK start/end và safe error metadata khi exception;
error path được kiểm bằng tests, không tạo lỗi provider trả phí. Success span không cần
error_category giả. Tất cả input/output content của234observations live đều null.

| Nhóm | Trace/duration live | Model/token live | Error metadata | Privacy | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| Request/response | Có/6root | Subtotal metadata, không usage_details | Category/phase khi lỗi; tests | PASS | PASS |
| Authentication | Có/6success | NOT_APPLICABLE |401/403 testPASS | PASS | PASS; failure liveNOT_RUN |
| Context/follow-up | Có/context_used | NOT_APPLICABLE | Tests | PASS | PASS |
| Router | Có | Đúng actual provider/generation | Tests | PASS | PASS |
| Planner/contract/binder | Có | Generation khi model; deterministic không token | Tests và error contract regression | PASS | PASS |
| JOIN/compiler/AST/guards/executor | Có | NOT_APPLICABLE | Tests | PASS | PASS |
| Query embedding | Có/3calls | Model đúng, token UNKNOWN upstream | Tests | PASS | PARTIAL: token không được cung cấp |
| Document embedding | Không dispatch | Offline SDK test | Tests | Offline PASS | NOT_RUN live, quota0 |
| Retrieval/RAG answer | Có/counts/citation_count | Embedding + generation phân biệt | Tests | PASS | PASS |
| Hybrid/coverage/policy | Có/đủ phases | Router generation; backend deterministic | Tests | PASS | PASS |
| Persistence | Có/6saved responses + reload | NOT_APPLICABLE | Tests | PASS | PASS |
| Provider attribution | Có/requested/used/actual model |10generation đúng usage | Tests | PASS | PASS |
| Fallback | OFF; không span/call giả | NOT_APPLICABLE live | Category được test | Offline PASS | NOT_RUN live |
| Refusal/failure | Không xảy ra trong6câu | Không consumption giả | Negative CI PASS, runtime timeout trước đó | Tests PASS | PARTIAL: không gây lỗi live mới |
| Browser render duration | Không phải backend stage | NOT_APPLICABLE | NOT_APPLICABLE | Không export browser data | NOT_APPLICABLE |

approved_edges là số quan hệ được phê duyệt trong workspace, không phải số JOIN của
mỗi query. Các stage AST lặp phản ánh revalidation thực; không cộng chúng vào LLM calls.

Không mở rộng authentication trace sang Google callbacks/GET hoặc tạo root mới cho
mỗi dependency. Stage không có diagnostic request không export orphan span. Không
thêm conversation/user IDs thô; chỉ correlation ngẫu nhiên nối diagnostics với trace.

## Sửa và kiểm thử

- Authentication/binding/contract/validation spans và counts/flags ở các điểm dữ liệu
  thực có sẵn. Không sửa prompts, QueryPlan/compiler/SQL/RAG/Hybrid decisions.
- Root tổng hợp phần usage đã đo; nếu một dispatch không có usage, trạng thái partial
  hoặc unknown. Không gán0, không tính cached/reasoning lần hai, không root usage_details.
- CI lần đầu bắt16 failures error_contract: decorator mới gán origin_stage trước
  caller, làm đổi taxonomy. Chưa triển khai image đó. Thêm annotate_error=False cho
  telemetry-only stages, giữ error contract cũ và regression riêng. Không sửa assertions
  để che lỗi. Image candidate cũ không được nghiệm thu.
- Final targeted CI132 provider/pipeline cases PASS, local70 auth/context/binding PASS; thêm kiểm thử
  missing credentials, partial root consumption, SDK embedding schema và preservation
  của error origin. Các lượt sau có overlap; không cộng thành số test độc lập giả.
- OFF/missing keys/SDK exceptions/blocked exporter/queue overflow/privacy kiểm bằng
  SDK thật với exporter memory và mocks, không provider calls.
- CI application3fe4cc2:1391backend unit,857isolated PostgreSQL,85frontend và125mockE2E
  PASS tự động; không chạy lại toàn bộ suite trên máy hoặc gọi provider trong CI. Bằng chứng runtime
  export timeout từ đợt trước: API401/health200 vẫn trả, trace đó bị mất.

## Usage và cost

Google GenAI1.75 EmbedContentResponse chỉ có embeddings/metadata; EmbedContentMetadata
có billable_character_count. Không có usage_metadata token, không đổi ký tự thành token.
Gemini generation và Knowledge dùng SDK usage; thiếu một trường vẫn partial/unknown.
Failed generation có usage chỉ khi SDK thực trả; timeout không tự suy ra consumption.

Langfuse Model Definitions đã có managed definition exact gemini-3.5-flash-lite:
input0.30USD/1M, output2.50USD/1M, cached input0.03USD/1M; khớp
[Google pricing](https://ai.google.dev/gemini-api/docs/pricing), kiểm27/10/2026.
Đây là Standard paid list price, không chứng minh tài khoản dùng tier nào/hóa đơn.
Embedding2 text0.20USD/1M theo cùng nguồn, nhưng không tính được nếu thiếu token.
Knowledge không có giá được xác minh. Không tạo model definitions trùng hoặc giá tự đặt.

Application không gửi cost_details vì chưa biết billing tier/discounts. cost_status=unknown
là giới hạn có chủ ý của cost do ứng dụng cung cấp. Langfuse có thể auto-infer estimate
cho model khớp definition; không coi đó là measured billed cost. Nếu cached/reasoning
chỉ được lưu descriptive metadata thì inferred cost không được khẳng định chính xác
đến hóa đơn. Không bật tokenizer ước lượng hoặc trả free-form SQL để tạo metric.

## Retention, storage và backup

Project Settings bản hiện hành không có Data Retention trong menu. Theo
[Langfuse retention](https://langfuse.com/docs/administration/data-retention), tính năng
self-hosted này thuộc Enterprise; mặc định không tự xóa. Không có license được cấu hình,
không chỉnh TTL database/lifecycle blob để vượt edition và không xóa trace kiểm thử.
Đề xuất7ngày khi có tính năng chính thức được cấp phép; hiện giữ dữ liệu, theo dõi disk
và làm maintenance có duyệt trước khi storage đầy. Không có scheduled cleanup mới.

Mẫu trước live: PostgreSQL15439539bytes, ClickHouse256720KiB, MinIO208KiB; đây là
storage thực ở thời điểm kiểm, không dự báo tốc độ tăng từ hai synthetic traces.
Docker logs rotation10m×3/service. Worker xử lý được ingestion; không OOM/restarts.
**BACKUP_RESTORE_NOT_VERIFIED**: runbook bảo vệ cả năm volumes và secrets đã có,
chưa snapshot/restore drill; không sao chép data directory khi database đang ghi.

## Ba script chưa commit

| File | Nội dung / quyết định |
| --- | --- |
| scripts/generate_maintenance_demo.py | Sinh synthetic CSV/DOCX/PDF; không network/credentials. Có default output cố định và có thể ghi đè file; dependencies/fonts riêng, chưa workflow chính thức. Giữ untracked. |
| scripts/maintenance_documents.py | Nội dung tài liệu fixture synthetic, không dữ liệu riêng/secrets phát hiện; chỉ hai scripts kia import. Giữ untracked cùng bộ chưa nghiệm thu. |
| scripts/maintenance_oracle.py | Oracle Decimal từ CSV bảo trì; fixture demo/bao_tri_thiet_bi không tồn tại, entrypoint ghi oracle.json; chưa đủ điều kiện chạy/commit như tool được hỗ trợ. Giữ untracked. |

AST syntax cả ba PASS, đã đọc source và tìm references; không tạo fixture để mở rộng
scope, không execute generator/oracle, không xóa hoặc sửa ba file của operator.

## Live và release

**LANGFUSE_READY_WITH_LIMITATIONS.** Cửa sổ nghiệm thu mới đã đóng sau đúng6câu,
10/20generation,3/8query,0/0document embeddings; SDK attempts1, không retry/fallback
hoặc paid diagnostics. Gate vận hành vẫnON. Source main3fe4cc2, API image
`sha256:d8ad8aa5e3425b803bcec9c61a5e84dd5e950a2e07dc978d70c64d7c33dcbbb2`.
CI40474177836 cả3jobs PASS, workflow40474178023 PASS. Candidate bị CI loại
ffa4ef39 chưa deploy, đã xóa sau khi chứng minh không container/config/rollback dùng.

Operator duyệt cutover có điều kiện CI PASS; sau khi báo image cũ bị loại và sửa,
đã áp dụng cửa sổ duyệt cho bản corrected3fe4cc2.15:37:51–15:38:07 Asia/Saigon chỉ
recreate API, Nginx syntax/graceful reload PASS. Guard preflight lần đầu chặn do
candidate private còn pin image cũ (sai tên key khi chuẩn bị); sửa đúng SHOPQUERY_API_IMAGE
rồi mới recreate, không bỏ guard. Strict88modules PASS/no source hoặc env drift.
API containerbb40a2e7; Webc6f1f591/DB511c4f5a không recreate hoặc đổi image/start time.

### Sáu request qua UI đăng nhập

| Q | Câu hỏi nguyên văn | Model / route | Oracle / kết quả | Input / output / total đã đo | End-to-end |
| --- | --- | --- | --- | --- | --- |
| 1 | Tổng cộng có bao nhiêu phiên sạc và tổng phí của tất cả phiên là bao nhiêu? | Gemini / SQL |360phiên,33066538.03; PostgreSQL PASS|7171 /285 /7456|4.591s|
| 2 | Cho tôi số phiên sạc và tổng phí theo từng trạm sạc. | Knowledge / SQL JOIN |12trạm, mỗi trạm30phiên; mọi tên/mã/phí khớp oracle|7177 /1673 /8850|13.908s|
| 3 | Chỉ dựa trên tài liệu KPI đã lưu, điều kiện để một trạm sạc đạt KPI là gì? | Gemini / RAG |threshold2800000, mọi trạng thái, ma_tram; citation23|4213 /101 /4314|3.900s|
| 4 | Theo tài liệu KPI, trạm nào đạt và trạm nào chưa đạt? | Gemini / HYBRID |TS07–TS12 đạt;TS01–TS06 chưa đạt; đủ12metric/citation23/verified_classification|3291 /43 /3334|2.607s|
| 5 | Vậy còn những trạm chưa đạt KPI? | Gemini / HYBRID follow-up |cùng conversationQ4;12evidence rows,6presentation indices đúngTS01–TS06, verified/citation23|3613 /48 /3661|2.756s|
| 6 | Những khách sạn nào có số phòng lớn hơn 100? | Gemini / SQL |16mã/tên khách sạn khớp PostgreSQL WHERE so_phong>100|4717 /269 /4986|3.722s|

Oracle được viết độc lập, không thực thi SQL do model tạo để chấm chính nó. SQL
persisted rows so với oracle sau chuẩn hóa thứ tự/aliases; Decimal so chính xác,
không float tolerance. Q5 chỉ gửi sau Q4 metrics/verdict/citation/persistence PASS.
Q6 chuyển workspace qua dialog bắt đầu chat mới; không đưa context Xe điện sang Khách sạn.

| Q | Correlation = trace ID | Spans | Generation / query embedding | Usage status toàn request |
| --- | --- | --- | --- | --- |
|1|b567bb2ef95f4e6a80d4edb5a73ad2c0|34|2 /0|measured|
|2|c9ebd80f61b1457fb7cab384a5f4debc|34|2 /0|measured|
|3|fdc52d81ebf7463ea11930fe46deae1c|16|2 /1|partial: embedding UNKNOWN|
|4|365e680d297e4ed7b016bb141a4c1cfb|58|1 /1|partial: embedding UNKNOWN|
|5|023d32f9301149018f70877c73b437b0|58|1 /1|partial: embedding UNKNOWN|
|6|476c869d29794ee1ba422f1ec1cc6ec4|34|2 /0|measured|

Cả6trace được đọc lại qua API Langfuse và mở từng cây trên Dashboard. Mỗi cây đúng
một root, tất cả parent/child hiện diện (root AS_ROOT được SDK đánh dấu dù có remote
parent placeholder). Generation dưới generation_contract, embedding dưới retrieval,
SQL/Hybrid/persistence nesting đúng. Không có orphan, duplicate provider observations
hoặc input/output nội dung.3/6lần SQL validation và nhiều coverage/policy spans trong
Hybrid phản ánh các lần validate thực ở compiler/executor/policy verifier, không phải
nhiều LLM dispatch. Hybrid deterministic chỉ có1generation Router, không planner/answer
model call giả. Metadata root không có usage_details để tránh cộng token hai lần.

### Chấm điểm từng request

| Q | BUSINESS_CORRECTNESS | TRACE_COMPLETENESS | TOKEN_ACCURACY | MODEL_ATTRIBUTION | PRIVACY | ERROR_HANDLING | PERSISTENCE |
| --- | --- | --- | --- | --- | --- | --- | --- |
|1|PASS|PASS|PASS|PASS|PASS|NOT_APPLICABLE: success|PASS|
|2|PASS|PASS|PASS|PASS|PASS|NOT_APPLICABLE: success|PASS|
|3|PASS|PASS|PARTIAL: embedding UNKNOWN|PASS|PASS|NOT_APPLICABLE: success|PASS|
|4|PASS|PASS|PARTIAL: embedding UNKNOWN|PASS|PASS|NOT_APPLICABLE: success|PASS|
|5|PASS|PASS|PARTIAL: embedding UNKNOWN|PASS|PASS|NOT_APPLICABLE: success|PASS|
|6|PASS|PASS|PASS|PASS|PASS|NOT_APPLICABLE: success|PASS|

Các error/refusal paths được kiểm offline/CI, không chủ động gây lỗi provider có tính
phí. Không gán PASS runtime error handling chỉ vì sáu success requests. Coverage source
ở bảng đầu đã có hiệu lực trong image này; document embedding, provider fallback,
explicit-route/no-model và unsupported/failure paths không dispatch live trong cửa sổ,
nghiệm thu bằng tests/các bằng chứng runtime trước đó, không thêm câu thứ7.

### Đối chiếu token/cost thực

Generation Gemini8calls: input23005/output746/total23751. Knowledge2calls:
input7177/output1673/total8850. Cộng10calls: input30182/output2419/total32601.
Từng call và tổng theo request khớp diagnostics; root tổng hợp chỉ là metadata subtotal.
Ba query embedding observations đúng model/duration/calls; API không trả token hoặc
billable characters trong ba responses này nên usage/cost UNKNOWN, không giả0.
Knowledge báo cached_input_tokens=0 thật trong SDK; Gemini cached/thought fields
không có trong responses đã đo, không suy ra một chỉ số mới từ đó.

Langfuse tự suy giá Gemini generation khoảng0.0087665USD theo managed Standard list
price; đây là **estimated**, không hóa đơn, không gồm Knowledge/embeddings UNKNOWN.
Số tự suy có sai số floating point khoảng1e-12USD ở một call, không phải token lệch.
Application cost_status=unknown nói về cost_details ứng dụng không cung cấp; khác với
Langfuse server-inferred cost. Không đủ căn cứ để báo tổng chi phí tất cả provider.

### Integrity và cấu hình

Fingerprint33objects dữ liệu (23uploaded tables và10public data/metadata tables) cùng
prefix238messages cũ đến message_id312 không đổi trước/sau. Chỉ thêm12messages của
6questions; Q4/Q5 cùng conversation và verified metadata/citation persist. Không upload,
re-embed, migrate, sửa datasets/documents/relationships/users/history cũ. Reload8080
vẫn đăng nhập, workspace Khách sạn và16row answer tải lại; không chạy lại OAuth sign-in.

UI đã hiện3tables/3documents mỗi workspace, PDF/DOCX/MD/chunks, approved N:1 links.
Runtime Gemini default, Knowledge manual, gateON/fallbackOFF/GuestOFF, embedding2/768,
JOIN ON/read-only guards, vector-only/BGEOFF; không feature vô tình bị tắt. Upload parser
không upload live vì quota0document embeddings; không dùng visibility làm upload PASS mới.
Không OOM/restart/crash, cả6LFservices và main8080healthy sau window.

### Docker và Git

Giữ active API d8ad8aa5, Webae181335/source02d5cbb, main DB137f044b và volume
shopquery-ai_postgres_auth_20261019. Sáu LF digests/pins trong ops/langfuse/compose.yaml
khớp runtime; năm LFvolumes riêng giữ nguyên. Rollback tức thời API52701da8/source8a2c6aa,
private .env.release.before tại backups/shopquery-ai/langfuse-acceptance-20261027;
069e7f67 và các rollback cũ đang được lịch sử runbook tham chiếu cũng được giữ.

Inventory sau cleanup:9ACTIVE,14REQUIRED_FOR_DEPLOYMENT (stopped containers còn
references),7ROLLBACK/historical runbook,19UNKNOWN thuộc projects khác. UNKNOWN
không có nghĩa rác. Inventory toàn máy:50unique images trước cleanup; chỉ xóa candidateffa4ef39 chưa từng
triển khai, không container/effective config/rollback/model references, exact tag, không
force. Sau49images. Docker report image size55.9GB cả trước/sau do làm tròn/shared/cache;
**dung lượng byte thực thu hồi UNKNOWN**, không báo đã giải phóng525MB theo virtual size.
Không prune/cache cleanup hoặc xóa images của projects khác. Tất cả volumes giữ nguyên.

Source commits:3d3087c instrumentation, bead097 tests,3fe4cc2 giữ error contract.
Bản sửa3fe4cc2 đã push/main và CI PASS trước deploy. Báo cáo/docs commits sau không
đổi application bytes hoặc yêu cầu rebuild. Ba scripts operator vẫn untracked có lý do
ở bảng trên; không còn source thay đổi chưa commit của nhiệm vụ sau bàn giao.

Giới hạn còn lại: embedding tokens không có upstream, Knowledge price UNKNOWN,
retention yêu cầu Enterprise và BACKUP_RESTORE_NOT_VERIFIED. Không full Stage2/tag,
không khẳng định một cửa sổ sáu câu bảo đảm mọi dữ liệu hoặc mọi tải dài hạn.
