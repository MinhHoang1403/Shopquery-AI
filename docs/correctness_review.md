# Sửa correctness và trình bày kết quả sau bàn giao

## Quyết định thiết kế thử nghiệm — 28/10/2026

Benchmark độc lập khóa trước thiết kế tại commit `95a6b0d`, SHA-256 chuẩn LF
`d5c6403e32984fce1825b26482f4b70b266551ce40e4c1dbe8587c020e44a69c`: 36 câu,
8 development/8 regression/20 held-out, 5 lĩnh vực; nông nghiệp là schema mới.
Nhãn task/evidence/route/intent/scope/execution đặt trước; held-out không đưa vào prompt.
Đây là bộ đánh giá synthetic, không phải kết quả live hay điểm Spider/BIRD.

| Phương án | Bằng chứng và rủi ro | Quyết định thử |
| --- | --- | --- |
| A: PR5 fields độc lập | Chặn một mâu thuẫn nhưng Knowledge chọn intent none dù route đúng; một classifier call | Baseline so sánh; chưa đạt |
| B: một task typed và scope | Bỏ route/evidence/intent trùng lặp; backend ánh xạ tất định. Compact trước có prompt/schema không khớp nên chưa đánh giá công bằng; vẫn có thể false RAG/Hybrid | Candidate một: prompt và wire phải cùng contract; một call |
| C: consistency/capability guard | Chặn mâu thuẫn rõ, scope chưa biết và nguồn thiếu; không xác minh ngữ nghĩa khi model sai nhất quán | Kết hợp vào B bằng kiểm tra deterministic, không thêm call |

Chỉ chọn B+C để thử sau khóa benchmark. Các giá trị scope chưa rõ không được tự biến
thành all_entities, owner và policy/coverage/SQL guards vẫn là authority; no keyword
override, không thêm classifier. Nếu semantic test thất bại, không promote, không sửa
prompt hàng loạt. Chi phí mục tiêu một generation như baseline; latency/tokens phải đo
được, không giả định. Chưa quyết định production cho đến khi both-provider held-out,
known contrasts, independent PostgreSQL oracle và live E2E đạt.

Gap hội thoại độc lập: RAG có thể persist câu thiếu bằng chứng kèm citation và error=null;
`contextual_question` hiện nhận là lượt thành công. Citation ID hợp lệ không chứng minh
câu trả lời đầy đủ. Không dùng regex và không coi model tự gắn nhãn là factual verification;
cần negative regression và xử lý legacy không ghi đè history trước khi cân nhắc sửa.

### Kết quả đánh giá độc lập và quyết định phát hành

`RELEASE_BLOCKED`: thử nghiệm B+C bị bác bỏ sau khi chạy tuần tự trên hai provider,
không merge, deploy hoặc dọn image. Candidate dùng một task enum và một scope do model
sinh; backend ánh xạ task sang route/evidence/intent và từ chối scope không rõ. Prompt
và wire cùng hợp đồng. Không có fallback hoặc retry; mã candidate đã được gỡ khỏi source.
Phép đo chỉ gọi Router trong API container với dữ liệu synthetic, không chạy SQL, không
phải UI acceptance hay kết quả PostgreSQL oracle.

| Kịch bản | Boundary/bằng chứng | Kết luận và trạng thái |
| --- | --- | --- |
| Áp dụng policy sau giải thích | Baseline Knowledge `267eda943194497d9bed0e125d2020ac`: RAG/documents thay vì HYBRID/both; candidate cùng mẫu đúng | Sai định tuyến baseline **CONFIRMED**; một mẫu cải thiện không chứng minh sửa tổng quát |
| Chỉ giải thích policy sau Hybrid | Baseline và candidate đúng RAG trên mẫu đối chứng Knowledge; candidate cũng đúng trên Gemini | Mẫu kiểm đúng; không đủ chứng minh không false Hybrid |
| Scope của tập đối tượng | Held-out `h07`, Knowledge `73dce125974943dbb91d4646bcf3bd7f`: HYBRID/both/not_qualified đúng, nhưng `filtered_entities` thay vì `all_entities` | **CONFIRMED semantic failure** ở Router; model có thể nhầm lựa chọn kết quả với giới hạn tập đầu vào. Không có SQL execution; nguyên nhân nội bộ của model UNKNOWN |
| RAG refusal/history | Negative regression trong `test_conversation_context.py`: answer thiếu bằng chứng, citation hợp lệ, error=null vẫn vào history được gọi là successful | **APPLICATION_DEFECT**; test xfail strict để theo dõi, không tính là PASS. Không chứng minh đây là nguyên nhân trace routing lịch sử |
| Knowledge timeout | Trace `21efd96c67cb41d69dd7e4fd6e71e5de`: timeout tại Router trước QueryPlan | **UPSTREAM_EVIDENCE_REQUIRED**; không có log server để phân biệt connect/read/pool/queue/inference |
| Coverage, binder, typed literal, SQL safety và provenance | Bằng chứng lịch sử và các regression tương ứng ở các bảng bên dưới | Giữ guard; không suy lỗi ứng dụng hiện tại từ trace cũ nếu chưa tái hiện |

Với output scope sai nói trên, `DatasetChatService.chat` và `ChatService.chat` trước sửa chỉ
truyền `classification` khi scope là `all_entities`. Sai scope có thể làm Hybrid không yêu
cầu coverage classification; `HybridPipeline.run` có nhánh draft model với trạng thái
`unverified`. Bốn negative regressions tái hiện ở cả hai service và hai scope thiếu chứng minh
đã FAIL trước sửa. Guard chung hiện trả lời không hỗ trợ trước khi chạy pipeline khi có
classification nhưng scope không phải `all_entities`; không xóa hoặc nới SQL/coverage guard.
Đây là **safe refusal**, có thể từ chối câu hợp lệ khi model phân loại sai scope; chưa sửa
được semantic routing và không chứng minh câu trả lời hay SQL của `h07` đã sai vì thử nghiệm
chỉ dừng ở Router. Fix guard hiện chỉ có bằng chứng offline, chưa triển khai.

Candidate khớp tất cả nhãn ở 6/7 mẫu Knowledge held-out đã chạy trước khi dừng;
13 mẫu held-out Knowledge và toàn bộ held-out Gemini chưa chạy. Không tính đây là
accuracy đầy đủ hoặc ước lượng ổn định dài hạn. Mẫu phát triển/hồi quy và baseline
nhỏ, không được dùng làm oracle hay thay cho nghiệm thu. Một ý tưởng dùng model thứ
hai để kiểm scope chỉ là giả thuyết: chưa có bằng chứng so sánh độ chính xác, chi phí,
độ trễ và tác động privacy, nên chưa đưa vào production. Nếu sửa sau khi xem held-out,
cần khóa một tập held-out mới độc lập, giữ lại mẫu đã xem như regression và không
điều chỉnh nhãn chuẩn theo kết quả.

Ngân sách cửa sổ đã đóng: **22 generation, 0 query embeddings, 0 document embeddings**,
không có fallback/retry. Trong đó Knowledge 16 calls (9.815 input/4.643 output tokens),
Gemini 6 calls (3.694 input/343 output tokens), theo metadata SDK; chi phí tiền tệ
UNKNOWN. Thời gian quan sát Router: Knowledge baseline 2.970–4.290 ms/candidate
1.986–4.333 ms; Gemini baseline 1.464 ms/candidate 1.062–1.742 ms. Các mẫu quá nhỏ
để kết luận phân phối latency hoặc năng lực provider.

## Điều tra Knowledge routing tiếp theo — chưa promote

Baseline b09ec4e/API4ab2c5a/Webde0572e. Nghiệm thu trên mạng công ty có9requests,
17generation/4query:7PASS,1false refusal,1timeout. Đây là cửa sổ đã đóng, không reuse.
Lượt mới giới hạn24generation/6query/0document, serial,attempts1,fallbackOFF; dừng nếu
timeout/permission lặp. Runtime giữ nguyên cho đến khi đủ release gates.

| Hiện tượng | Failure boundary | Bằng chứng | Giả thuyết | Cách xác minh | Mức chắc chắn |
| --- | --- | --- | --- | --- | --- |
| Hybrid bị chọnRAG | Semantic classification | dfe0c869582c45e5ac9ad09df7f57c09,evidence=documents,0SQL | Current request xuất hiện trước rồi lặp trong khốiQuestion kết thúc bằng history; mô tả field chưa tách requested output khỏi nguồn quy định | Regression prompt táchhistory/current; gold labels cố định trước live; before/after cùng mẫu vàheld-out | Boundary CONFIRMED; causal history bias UNKNOWN trước paired live |
| Intent mâu thuẫn evidence bị xóa | Backend normalization | router.py xóa intent khi nonHYBRID; test hiện có cấpqualified+documents vẫnRAG | Mất tín hiệu mâu thuẫn có thể dẫn dispatch khi cần làm rõ | Failing negative cả hai SDK; phảirefuse trước mọi pipeline,không épHYBRID | Contract gap CONFIRMED; chưa chứng minh trace dfe0 chứa contradiction |
| Router timeout | Provider request |21efd96c67cb41d69dd7e4fd6e71e5de,61.419s,noHTTPstatus,noPlan | Connect/read/pool hoặc upstreamqueue; chưa cóserverlogs | Đọc SDK pin,timeout/client lifecycle; capture bounded exception class nếu live lặp; không tăngtimeout/retry | Boundary CONFIRMED; nguyên nhân server UNKNOWN |

RAT-SQL/Spider hướng dẫn schema grounding và tách schema đánh giá; BIRD yêu cầu chấm
result bằng dữ liệu độc lập; PICARD minh họa constrained output không thay semantic
correctness. Không cài mô hình/framework hoặc tuyên bố điểm benchmark. Đã đối chiếu
HTTPX [timeout phases](https://www.python-httpx.org/advanced/timeouts/) và local pinned
OpenAI3.35.1/LangChain1.7.2/google-genai1.75.0/Pydantic2.14.1. SDK nhậnfloat60 thành
connect/read/write/pool60,không phải tổng deadline60; OpenAI timeout wrapper giữ cause,
max_retries=attempts−1=0. MỗiModelChatService._attempt tạo/đóngclient trongfinally;
Router/SQL cùng turn reuseclient. Chưa có bằng chứng pool leak hoặc cần đổi lifecycle.

### Kết quả candidate — KNOWLEDGE_ROUTING_NOT_ACCEPTED

Không promote/merge/build/deploy/cleanup. API4ab2c5a/Webde0572e vẫn phục vụ8080;
candidate nằm trên branch`codex/routing-context-contract` để review. Không thay provider
config,defaultGemini/fallbackOFF/gateON/GuestOFF hoặc documents/vectors/history.

8regressions mới FAIL trước sửa:4ca metadata contradiction qua2SDK và4ca current/history
placement. Candidate đặt context thànhJSON data, current request duy nhất ở cuối prompt,
và trả clarification trước mọi pipeline nếu intentclassification mâu thuẫn evidence chỉ
tables/documents. Không suyHYBRID từintent,không nớiSQLguards. Tên/properties/enums/required
và nativeGemini serialization giữ nguyên; chỉ diễn đạt rõ hơn policy_intent là requested
operation,không phải verdict đã tính. Hai sửa contract có bằng chứng offline; **chưa phải
bằng chứng sửa xong semantic routing**. Trace lịch sửdfe0 không có rawenum trước normalize,
không tự nhận contradiction chắc chắn xảy ra ở trace đó.

Một bộ gold được khóaSHA trước dispatch tại`backend/tests/fixtures/routing_evaluation.json`.
Không đổi labels sau xem kết quả. Development/regression gồm logistics/energy/hotel;
3ca hotel/library dành held-out cho lượt candidate đầu, không chèn câu held-out vào prompt.
Sau khi đã quan sát, các ca chạy lại là regression/ablation, không còn fresh held-out.
Không dùng số liệu model tạo làm oracle. Đây là classification-only từ APIcontainer bằng
sourcecandidate truyền qua stdin,không deployment/teststack/SQLexecution/upload/embedding.

| Phase/provider | Số generation | Route đúng | Metadata classification đúng | Kết luận |
| --- | --- | --- | --- | --- |
|Before/Knowledge|4|3/4|0/2Hybrid|Library rawrouteHYBRID nhưngevidence=tables/intentnot_qualified;backend thànhSQL. DeliveryHybridintentnone. |
|Candidate prompt+guard/Knowledge|8|8/8|0/4Hybrid|3RAG/1SQL/4Hybrid;nhãn route đúng chưa đủ để dùng full coverage. Held-out3/3route nhưng0/2Hybrid metadata. |
|Clarified field description/Knowledge|4|4/4|1/4Hybrid|Libraryall/all_entities đúng;Deliverynone/all_entities;Energynone/unspecified;Hotelnone/unspecified. Dừng sửa,không thử đến khiPASS. |
|Clarified contract/Gemini|2|2/2|0/1full metadata theo gold|RAGswitch đúng;HotelHybridintentqualified nhưngscopefiltered_entities thay vìall_entities. Không có pairedGemini-before nên không quy thành regression do candidate. |

Paired4questions Before→candidate đầu:route3/4→4/4,Hybridmetadata0/2→0/2.
Không tuyên bố causal fix/modelreliability từ những mẫu nhỏ. Hợp đồng/schema parse đủ
fields nhưng vẫn chọnsai/thiếu ngữ nghĩa; lý do nội bộ Knowledge **UNKNOWN**. Không tạo
failing mock rồi gọi đó là bằng chứng mô hình hiểu sai đã được sửa. Chưa sửa SQL/JOIN/
Hybridengine hoặc thêm classifier/repair/retry. Đã dừng sau một contract clarification
có giả thuyết cụ thể; không tiếp tục prompt churn. Các câu unsupported/missingcapability/
negativecontext có offline coverage, chưa có liveaccuracy trong cửa sổ này.

Lượt full backend local đầu:1522PASS/9FAIL;9assertions đòi raw multiline workspace/Question
heading cũ. Sửa để JSON-decode rồi so exact workspace và current request, không bỏ assertion
owner/SQL/security. Targeted sau cùng186PASS, RuffPASS; không cộng overlap với173PASS
trước đó. Full backend/PostgreSQL/frontend/mockE2E/Compose regression chạy qua PRCI;
exact-head URL/counts trả trong bàn giao. Không có liveUI candidate vì semantic gate FAIL.
Independent PG oracle và guard tests hiện có được giữ, không chạySQL do classifier tạo.

Cửa sổ mới **CLOSED18/24generation,0/6query,0document**,SDKattempts1,nofallback,serial.
Knowledge16calls:15/16route đúng khi gộp cảBefore (không dùng tỷ lệ gộp này chấm candidate),
0transporterrors,mean4719.465ms/median4802.922ms. Gemini2calls:2/2route,
mean/median1693.226ms. Không suySLA hoặc timeout đã khỏi; lỗi61.419s lịch sử vẫn chưa có
serverlogs để phân biệtnetwork/read/queue. Không có căn cứ nângtimeout hoặc thaypooling.
GET/models từAPI200/243.67ms,cóknowledge,auth/model/timeout60/attempts1 không đổi.

18calls cóSDKusage:40147input+6076output=46223tokens (Knowledge41501,Gemini4722).
KnowledgecostUNKNOWN; không coi làfree. Không phát sinhquery/documentembeddings.
Langfuse18roots/72observations,18generation,no duplicate/no fallback/rawIOabsent,
fullmetadata privacyPASS kể cả synthetic evalquestions. Không logreason/chain-of-thought.
Các classifier calls chỉ chạy classification; không tạoSQL/policyverification spans giả.
Private evidence:`C:/Users/admin/.codex/backups/shopquery-ai/routing-reliability-20261028/`.

Runtime chưa bị thay, không tạo candidateimage hay dọnimage. Không thể gọi nhiệm vụ là
KNOWLEDGE_ROUTING_ACCEPTED chỉ nhờ regression/route accuracy; current app vẫn giữ
Knowledge manual để operator sử dụng với giới hạn đã công bố.

### Tiếp tục theo operator — kiểm contract nhỏ và chốt giới hạn

Job PostgreSQL đầu của PR40649825723:870PASS/8FAIL. Tất cả8failure nằm ở hai assertions
`context.routing_context in prompt` trong`test_join_order_integration.py`, còn tìm raw
multiline sau khi context đã encodeJSON. Đã đổi sangdecodeJSON/soexactworkspace; giữ
toàn bộ owner-isolation/SQL/oracle assertions. Không sửa compiler hoặc bỏ testcase.

Operator yêu cầu tiếp tục sửa kỹ; mở cửa sổ mới tối đa6generation trong cùng trần24,
không reuse cửa sổ18calls đã đóng. Không thêmUI/embeddings. Đã thử một contract nhỏ
classification-only có mộtoperationenum vàscope, mapdeterministic vàoRouteDecision:
không các trườngroute/evidence/intent độc lập để model trả mâu thuẫn. Cùng schema/prompt
context và3câuHybrid+1policy-only đã khóa trước,1call/case,khôngrepair/retry.

| Case | Operation/scope Knowledge | Kết quả |
| --- | --- | --- |
|delivery_apply|classify_every_entity_using_document/whole_entity_set|HYBRID/all/all_entities đúng;5996.038ms;0758543f660a45988fba2cf5ebc1af15|
|energy_apply|classify_every_entity_using_document/whole_entity_set|HYBRID/all/all_entities đúng;4619.043ms;158e20b174874f088a089634522ddbd6|
|library_apply|classify_every_entity_using_document/whole_entity_set|HYBRID/all/all_entities đúng;4167.028ms;45b33c6ad9e24a5393ac6b9c90b7e833|
|delivery_rule|classify_every_entity_using_document/whole_entity_set|**FAIL_FALSE_HYBRID**:chỉ hỏiquyđịnh phảiRAG;2463.475ms;8bf21385274048bbae2ad23ba6bb7380|

Contract nhỏ không được tích hợp vàoadapter hoặc giữ thànhproductionmodule chết.
Schema/kết quả thử được lưuprivateevidence; bỏhai experimental source/test files của
phương án chưađạt. Không đổi Knowledge/Gemini wire đang dùng. Không suy vì3HybridPASS
mà bỏpolicy-onlyFAIL, không chạythêm để kiếmcaPASS. Những ca đã quan sát không cònheld-out.

Lượt nối tiếp **CLOSED4/6generation**, cộng dồn nhiệm vụ **22/24generation,0query,0document**;
2stagescònlại khôngtựdùng sau đóng. Kết luận giữ **KNOWLEDGE_ROUTING_NOT_ACCEPTED**.
KhôngcandidateUI,merge/build/deploy/cleanup;main và runtime hiện hành được bảo toàn.

## Kết luận hiện hành — 28/10/2026

**APPLICATION_ACCEPTED_WITH_UPSTREAM_LIMITATIONS**, chỉ trong phạm vi hỗ trợ và mẫu
nghiệm thu dưới đây. API application `4ab2c5a1cc115b95cbc9854d6dc65f75a95ae473`, image
`sha256:2d27fba187bb8703ebefbb214931933576767a52d7a32855b05d4a25c3bf5d98`;
Web application `de0572ebf7e946c3396c5693a9c5a3f27ab6a4ef`, image
`sha256:b2188879d84d6069f66dd73a13210bb810d269a23366aa77d6d4fd6eb307a7b3`.
Các commit bàn giao chỉ sửa tài liệu sau hai application revisions này không đòi rebuild.
Không release tag/full Stage2, không tuyên bố mọi câu hỏi/schema đều đúng.

| Lỗi | Root cause và mức chắc chắn | Sửa ở đâu | Regression | Live / trạng thái |
| --- | --- | --- | --- | --- |
| Policy-only bị chọn HYBRID | CONFIRMED: Router contract chỉ biểu diễn route, không biểu diễn loại bằng chứng cần dùng; history/current request chưa tách rõ trách nhiệm. Lý do suy luận nội bộ của model lịch sử UNKNOWN. | `routing/router.py::RouteDecision`, `QueryRouter.route`; `routing/service.py`; dataset/chat services truyền current question riêng | Evidence/route contradiction, capability unavailable, ambiguity, explicit route, current/history switch; cả hai SDK wire | Auto RAG citation23 và policy-only follow-up citation50 PASS; FIXED trong mẫu đã kiểm |
| COUNT+SUM gặp 504 | CONFIRMED failure boundary trước đây là provider deadline/transport, không có bằng chứng compiler lỗi ở trace504 | Không tăng timeout/retry, không sửa SQL để che transport; scalar guards đã sửa ở đợt trước giữ nguyên | Independent PostgreSQL COUNT/SUM/AVG, NULL, Decimal, scalar và grouping | Exact question trả192 và24360000 đúng oracle,3.328s; NOT_REPRODUCED ở lượt mới, không tuyên bố hết504 vĩnh viễn |
| Hybrid mới scope incomplete | CONFIRMED contract gap: evidence/intent/scope có defaults, schema/SDK cho bỏ fields; service chỉ dùng full classification khi intent khácnone và scopeall_entities. Raw intent/scope của trace lỗi UNKNOWN, chưa chứng minh là nguyên nhân duy nhất | `routing/router.py::RouteDecision` yêu cầu cả ba fields; local dispatch validation; descriptions chung; safe enum metadata ở diagnostics/observability | 3 tests FAIL trước sửa;45 SDK/routing checks PASS;240 related targeted PASS có overlap, không cộng. Complete intent qua real Hybrid verification6cases/2SDK/3selections | PR4 Hybrid8entities/5đạt/3chưa và follow-up3entities PASS đúng oracle; FIXED trong mẫu, giới hạn paraphrase còn công bố |
| Alias/thuật ngữ/error summary khó hiểu | CONFIRMED fallback thiếu metadata dùng alias làm nhãn; UI error chung không phân biệt boundary | `text_to_sql/answer.py::compose_sql_answer`, `routing/hybrid_evidence.py::compose_answer`, `ErrorDetails.tsx`, `ChatMessage.tsx` | Neutral metadata fallback, Decimal/NULL/DATE/ID, category-specific safe errors, collapsed evidence/accessibility | Summary và evidence live đúng số/citation; friendly provider errors chỉ kiểm offline, không cố tạo paid failure |
| Knowledge403/timeout | CONFIRMED các lượt lịch sử dừng ở upstream trước plan/SQL; quyền gateway/model inference hiện tại UNKNOWN | Không đổi auth/key/model/endpoint; giữ manual và fallbackOFF | Hai SDK contract/mapping offline PASS không thay provider acceptance | GET/models200,334ms,cóknowledge; không đủ chứng minh generation/structured support; UPSTREAM_BLOCKED/chưa nghiệm thu lại |

PR[#4](https://github.com/MinhHoang1403/Shopquery-AI/pull/4) đã squash merge.
[Exact application-main CI40631282398](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/40631282398)
**4/4 jobs PASS:1523 backend,878 PostgreSQL,88 frontend,125 mock E2E,10 maintenance,
10 Compose**. Local targeted và full CI được phân biệt; không cộng overlap thành test count.
Giữ QueryPlan/Pydantic/binder/compiler, approvedN:1/fact/grouping/COUNT provenance,
WHERE/HAVING/LIMIT coverage trước execution, AST/read-only/timeout/rowcap, Decimal/NULL,
owner/workspace scope, citation identity và verified conversation guards. Không đổi dependency.

### Cửa sổ live cuối và đối chiếu độc lập

Sau failure của cửa sổ đầu, operator cho phép tiếp tục tự kiểm an toàn trong hạn mức;
cửa sổ mới giữ trần3câu/6generation/3query/0document, không reuse cửa sổ đã đóng.
Chỉ Gemini, attempts1, không retry/fallback hoặc Knowledge generation. Cả ba dùng cùng
hội thoại dataset17, tài liệu synthetic đã xác minh; follow-up chỉ gửi sau Hybrid PASS thật.

| Câu | Correlation | Kết quả được đối chiếu | Usage / thời gian |
| --- | --- | --- | --- |
| Theo chính sách KPI đã lưu, những kho nào đạt và những kho nào chưa đạt? |c3dcc160229e4e788b05b27acadbb2c2|HYBRID,verified_classification;8kho,5đạt/3chưa; mọi tổng/sốđơn đúng independent fact oracle,citations50/51;intentall/scopeall_entities|1generation/1query;2.932s |
| Vậy còn những kho chưa đạt KPI? |5585fe2882df491ab3b147e62f6c8081|Cùng hội thoại/context;K01,K02,K03 đúng oracle,fullSQL evidence vẫn8kho;verified,citations50/51|1generation/1query;2.669s |
| Vậy quy định đó yêu cầu tính những trạng thái đơn nào? |03cb3b972bd54bc08ae44cf56c646fca|RAG/evidence=documents;contexttrue,citation50 khớp nội dung;chỉHoàn tất trong kỳ,khôngSQL|2generation/1query;3.829s |

Lưu ý nhánh follow-up: classifier trả intentnot_qualified nhưng **scopefiltered_entities**.
Kết quả đúng nhờ resolver `classification_selection` hiện có nhận câu tham chiếu trong
grammar hỗ trợ, dựng full coverage rồi chọn subset. Không dùng PASS này để tuyên bố mọi
paraphrase đi qua typed-intent branch, hoặc contract bắt buộc sẽ bảo đảm semantic accuracy.
Không thêm regex ngành/dataset hoặc nới guard để ép câu này PASS.

Oracle:192facts/8kho,24dòng mỗi kho; tổng24360000. K01/K02/K03 lần lượt2400000/
2640000/2880000;K04/K053000000;K063240000;K073480000;K083720000.
Ngưỡng tài liệu>=3000000 nênK04–K08đạt. Chính sách/kỳ/trạng thái/citation50/51 kiểm riêng
với tài liệu, không lấy câu trả lời hoặc SQL do model tạo làm oracle.

Toàn nhiệm vụ có **7UI requests:6PASS/1FAIL trước correction**. Loại câu:2policy-onlyRAG,
2SQL,2Hybrid (1FAIL,1PASS),1follow-up classification;2câu cuối có context. Route đúng7/7
trong mẫu nhỏ, business false refusal1/7 trước correction,0/3 sau correction; không có
unsupported/ambiguous live samples nên không báo accuracy cho hai nhóm đó. Provider
transport failures0/7 không suy SLA. SQLCOUNT+SUM/hotel PASS trên de0572e; sau PR4 chỉ đổi
classifier contract, SQL offline/PG regressions PASS, không gọi lại hai câu để tăng score.

**Usage cộng dồn13/16generation,5/5query,0document,7/8UI; cả hai cửa sổ đã đóng.**
Langfuse có7roots/258observations,13generation/5query observations, IDs không trùng;
SDK usage đủ13generation:30162input+2105output=32267tokens. Embedding tokens/cost
UNKNOWN; cost estimate trên dashboard không phải hóa đơn. Raw input/output null và
metadata privacy checks PASS trên cả258observations; không ghi câu hỏi/SQL/rows/email/
owner/conversation IDs thô/keys/private Knowledge URL. Dashboard trace mới hiển thị2.93s
và pipeline thực. Không generation/embedding call nào chỉ để tạo telemetry.

### Trình bày, tổng quát hóa và vận hành cuối

Ví dụ có căn cứ, không tạo thêm lời trả lời trả phí để minh họa:

| Trường hợp | Trước / sau và phạm vi bằng chứng |
| --- | --- |
| COUNT/SUM | Raw alias fallback → nhãn từ result provenance đã kiểm; live192bản ghi/tổng24360000 đúng oracle, không tự thêm đơn vị tiền |
| Numeric filter/GROUP BY | Chi tiết16rows ở giao diện → summary16nhóm, mở bảng khi cần; live IDs/names đúng16khách sạn có>100phòng |
| Ranking | Ranking chỉ diễn đạt từ sort/limit metadata được xác minh; ordinal/date/ID không suy từ alias; regression/PG/E2E, không có lượt ranking trả phí mới |
| RAG policy | False refusal doHYBRID → câu trả lời tài liệu và citation23; follow-up tài liệu citation50,khôngSQL |
| Hybrid verified | Summary chung →5đạt/3chưa từ chính vector decisions đã Decimal-verify; subset3 có thể mở toàn8SQL rows |
| Insufficient evidence | Chi tiết validation/đề nghị đổi câu hỏi dù yêu cầu rõ → thông báo không đủ căn cứ xác nhận; guard/error details giữ thu gọn, negative tests |
| Provider unavailable | Thông báo chung hoặc lẫn thiếu dữ liệu → summary timeout/quyền truy cập/quota theo safe category; technical details thu gọn, offline regression |

Frontend không đổi số liệu, không tính KPI ở client, một bảng evidence mặc định thu gọn;
pagination/mobile/keyboard/citation/SQL detail còn nguyên. Live reload giữ Google existing
session, ba câu/history và citation; không gọi đó là fresh OAuth acceptance.

Phạm vi tổng quát:4domains trong routing fixtures (logistics/energy/hotel/library),
library held-out không dùng làm prompt examples;16phrases script metadata như bảng bên
dưới. Metamorphic3schema variants/12executions+3threshold checks bằng oracle độc lập,
không đo model accuracy. Negative tests gồm unavailable/unclear/contradiction/missing
metadata, unverified/cross-owner context, metric/coverage/grain/refusal;45 và240targeted
checks có overlap nên không bịa tổng số negative độc lập. Không hardcode giá trị nghiệp vụ.

Strict verifier88modules/source manifest/config/image/health PASS; manifest
`3054d4cad4f1d1a3e03746f67fa4fde1f88895f468ace4f923106b2d9e4bc123`.
MainPG giữ container511c4f5a và volume`shopquery-ai_postgres_auth_20261019`;36data objects
và316messages cũ≤390 có fingerprint không đổi. Chỉ thêm14messages nghiệm thu, tổng330,
maxID404. Sáu Langfuse containers/datastores giữ nguyên. Không migrate/re-embed/BGE.
Gemini default/gateON/GuestOFF/fallbackOFF/embedding2-768/Knowledge manual giữ nguyên.

Cleanup sau promote: xóa exacttags của3API images07045862/d7f2d822/6a632447 đã xác minh
không container tham chiếu và không cần rollback. Giữ active2d27/b218,rollback4a80/9b,
các model/PG/Langfuse images và toàn34volumes. Images64→61; Docker báo57.44→57.42GB
(làm tròn/shared layers). Hostfree138423947264→138423463936bytes trong hoạt động đồng thời;
**dung lượng vật lý thu hồi UNKNOWN/chưa chứng minh**, không nhân virtual image sizes.
Buildcache401/47.24GB giữ nguyên, không prune/force hoặc tác động project khác.

Evidence riêng ngoài Git:`C:/Users/admin/.codex/backups/shopquery-ai/evidence-routing-20261028/`,
gồm oracle/fingerprints, strict reports, usage, sanitized trace checks và screenshots;
không commit raw logs/history/config secrets. Runbook ghi đầy đủ active/rollback digests.

## Nhật ký lịch sử trước nghiệm thu cuối

Các trạng thái LIVE_PENDING/RELEASE_BLOCKED dưới đây giữ lịch sử đúng thời điểm,
được thay thế bởi kết luận hiện hành ở đầu tài liệu; không dùng làm trạng thái runtime mới.

## Quyết định bổ sung 28/10/2026 — evidence routing và UX

Baseline b576ab8/API e2722da/4a80e003 được kiểm lại bằng strict verifier:88 modules,
không source/config drift; PostgreSQL và sáu Langfuse services healthy. Cửa sổ cũ đã đóng.
Yêu cầu mới cho phép tối đa8 câu UI/16 generation/5 query/0 document, attempts1,
không retry/fallback. Chưa dispatch trong bước chẩn đoán offline.

| Vấn đề | Bằng chứng | Nguồn nghiên cứu | Phương án | Rủi ro | Test chứng minh |
| --- | --- | --- | --- | --- | --- |
| Policy-only chọn HYBRID | Trace0029c481; QueryRouter chỉ nhận route/reason, không có hợp đồng về bằng chứng cần dùng | RAT-SQL: liên kết schema; PICARD: hợp lệ cấu trúc không đồng nghĩa đúng ngữ nghĩa | Cùng classifier trả evidence requirement; backend suy route, kiểm capability; không thêm call/regex ngành | Model vẫn có thể phân loại sai evidence; cần live, mocks không đo accuracy | Cặp policy/data/application nhiều domain; contradiction/missing metadata; unavailable capability |
| Context làm lẫn intent | Prompt hiện ghép current question với các lượt trước | Spider: tách schema/queries; nguyên tắc scope hiện có | Nêu rõ current request và context chỉ để giải tham chiếu; không dùng route trước làm authority | Không tự chứng minh semantic accuracy | Topic switch/rule-only follow-up; failed/unverified/cross-owner context |
| Lời trả lời lộ labels/thiếu thông báo phù hợp | Presenter fallback dùng raw alias; ErrorDetails luôn hiển thị một câu chung, message backend có SDK/SQL | ToTTo: trung thành dữ kiện; metadata compiler là authority | Summary trung tính khi thiếu metadata; error summary theo category an toàn, details vẫn thu gọn | Không đoán nhãn/đơn vị từ alias | Unknown alias/date/ID/Decimal; provider khác validation/insufficient; history/accessibility |
| Tổng quát hóa | Các mocks cũ cung cấp route mong muốn, không thể chứng minh model hiểu câu hỏi | Spider/BIRD: schema khác và kết quả execution | Tách fixtures phát triển và domain held-out; independent PostgreSQL oracle, biến đổi IDs/columns/values | Không tuyên bố Spider/BIRD benchmark hoặc routing accuracy từ mocks | Targeted PG/metamorphic + live giới hạn |

Nguồn chính: [RAT-SQL](https://aclanthology.org/2020.acl-main.677/),
[Spider](https://aclanthology.org/D18-1425/),
[BIRD](https://proceedings.neurips.cc/paper_files/paper/2023/hash/83fc8fab1710363050bbd1d4b8cc0021-Abstract-Datasets_and_Benchmarks.html),
[PICARD](https://aclanthology.org/2021.emnlp-main.779/),
[ToTTo](https://aclanthology.org/2020.emnlp-main.89/).
Đây là nguyên tắc thiết kế/đánh giá, không phải bằng chứng mô hình ShopQuery đạt các benchmark.
Giữ Gemini native wire của QueryPlan và các guards; không đổi SDK, timeout, auth hoặc Knowledge endpoint.

### Kết quả của đợt evidence routing — chưa promote toàn bộ

PR[#3](https://github.com/MinhHoang1403/Shopquery-AI/pull/3) merge thành application source
`de0572ebf7e946c3396c5693a9c5a3f27ab6a4ef`. [CI40628380855](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/40628380855)
4/4 PASS:1514 backend,878 PostgreSQL,88 frontend,125 mock browser,10 maintenance,
10 Compose. Trước sửa19/27 tests mới FAIL; sau sửa27/27 PASS. Bổ sung tiếp9 SDK/privacy/
ambiguity checks và2 presentation checks; các suite targeted có overlap, không cộng.
Lượt CI đầu có52 failures do assertions copy cũ/no-metadata summaries; đã sửa đúng
presentation contract, giữ nguyên rows/Decimal/SQL refusal/privacy assertions. Không skip failure.

Thư viện là domain không dùng trong prompt thiết kế.3 biến thể schema mới kiểm12 trường hợp
execution (scalar COUNT/COUNT-column/SUM/AVG, numeric+DATE filter,3table chain,2table ranking),
cùng3 policy threshold boundaries. Oracle đọc fact rows độc lập/PG AVG, không chấm theo SQL
do model tạo. Đổi table/column names, IDs có0 đầu, column order, numeric values, thêm cột dư,
NULL và tên trùng. Đây là scripted execution tests, không phải độ chính xác mô hình trên schema mới.
16 natural-language routing fixtures (6 policy-only,4 SQL,4 Hybrid,1 unsupported,1 unclear)
kiểm dispatch của metadata được script cấp, không dùng chúng để báo model route accuracy.

Operator yêu cầu tự hoàn tất build/deploy trong prompt mới. Sau exact-main CI và0active
leases/no Guest work, cutover API/Web chỉ đổi2image refs. API
`sha256:0704586256cc56c03f7379509d2db58a95191ae9e04d97cc3fe8f4d04ab5a20e`, Web
`sha256:b2188879d84d6069f66dd73a13210bb810d269a23366aa77d6d4fd6eb307a7b3`.
Strict88/source/config/health PASS.36data objects và316messages≤390 fingerprint không đổi.
Google existing session/history sau reload PASS; không coi đây là fresh OAuth test.

| Câu UI mới | Correlation | Kết quả |
| --- | --- | --- |
| Xe điện policy-only, Auto |b4c406f7eddb460490f289f25c4f8760|PASS RAG/evidence=documents,citation23,mọi trạng thái,0SQL,2generation/1query,4.053s |
| Giao nhận exact COUNT+SUM |c428a8d352e54d19bad04cba20e164f1|PASS SQL/evidence=tables,192rows/24360000 đúng oracle,2generation/0query,3.328s |
| Khách sạn >100 phòng |713cd9502e24454094e1c1bf900d500f|PASS SQL,16IDs/names đúng oracle,2generation/0query,4.467s |
| Giao nhận câu KPI tự nhiên mới |f1d3dafe938c4717914803d21220505a|FAIL:HYBRID/evidence=both,8rows,policy_sql_scope_incomplete;3generation/1query,17.101s;không gửi follow-up |

Auto routing đúng4/4 evidence routes trong mẫu nhỏ; business correctness3PASS/1FAIL.
Không có provider transport failure trong4requests; không suy SLA hoặc không bao giờ timeout.
Lỗi Hybrid không được gọi PASS chỉ vì có8rows. Intent/scope raw của classifier chưa lưu nên
giá trị cụ thể **UNKNOWN**. Source chứng minh contract cho phép bỏ cả hai và dùng defaults;
nhánh full-classification coverage chỉ nhận khi intent khácnone vàscope=all_entities, còn
fallback lexical grammar không phủ mọi cách diễn đạt. Không khẳng định lần này chắc chắn
model đã bỏ fields. Failing regressions mới tái hiện riêng contract gap: schema không required,
hai SDK chấp nhận payload thiếuintent/scope và tiếp tục tới Hybrid.3tests FAIL trước sửa.

Correction kế tiếp yêu cầu evidence/intent/scope trong wire và local validation, giữ metadata
enum an toàn ở diagnostics/Langfuse để biết nhánh thực. Không nới WHERE/HAVING/LIMIT, không
coi intent là bằng chứng chính sách, không tăng retry hoặc gọi classifier thứhai. Phần này
**FIXED_OFFLINE_LIVE_PENDING** cho đến khi tests/CI/live phù hợp hoàn tất; không tuyên bố
đã giải quyết nguyên nhân duy nhất của trace mới. Knowledge GET/models200/334ms,cóknowledge,
khôngredirect/request-ID; generation vẫn **NOT_VERIFIED**,không đổiauth/model/config.

Cửa sổ mới đã đóng sau4câu:9/16generation,2/5query,0document. Không reuse phần dư sau
failure. NormalgateON/defaultGemini/fallbackOFF/GuestOFF giữ nguyên. Theo rollback gate của
operator, chỉAPI quay về4a80e003/sourcee2722da;Webb2188879 giữ UX đã kiểm.88modules runtime
khớp Git e2722da (chuẩn hóaCRLF/LF),health8080PASS. Đây là source drift có chủ đích với main;
không đổi strict guard để báo current-mainPASS. Main PostgreSQL/Langfuse/volumes giữcontainer.
Không cleanup images khi API candidate chưa được promote ổn định. Tổng thể **RELEASE_BLOCKED**.

Baseline: main `1f7871a16c16f9b840703e50199ec81f41269a9c`, API application
`3fe4cc2`/image `d8ad8aa5`, Web `02d5cbb`/image `ae181335`. Một deployment 8080;
không đổi DB/schema, model, gate, fallback, Guest policy, embedding hoặc Langfuse.
Application hiện hành: API `e2722da`/image `4a80e003`, Web `b75a844`/image `9b735b38`.
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

Yêu cầu bổ sung giữ nguyên công việc và dữ liệu; không mở lại audit kiến trúc. Điều tra
bắt đầu từ API29bb788/Webb75a844. Thay đổi chỉ errors/Gemini response handling/tests/docs
của chính nhiệm vụ; không reset/gộp file ngoài scope. Source e2722da đã push/CI và được
operator duyệt API-only cutover sang image4a80e003, strict88/source/image/env PASS.

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

#### E. CI, cutover và nghiệm thu provider fix

[CI40620972527](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/40620972527)
exact application/test source `e2722da8973883bdeb5cb837e9614001f9be490a`:4/4 PASS,
1.476 backend,875 PostgreSQL,87 frontend,125 browser mock E2E,10 maintenance và10 Compose.
Chỉ API build; immutable digest
`sha256:4a80e003aeb9ea008afcc5b557084db105ad4507130695a5b7fa1d378bc586e7`.
Operator duyệt cutover và tối đa2 câu Gemini/4 generation/1 query/0 document trong trần
còn lại; không xin ngân sách nhiệm vụ mới hoặc reset usage. API source e2722da, one worker,
strict88 modules/no mismatches/no environment drift, health8080 PASS. Web9b735b38/main DB/
six Langfuse services/volumes giữ nguyên; rollback API5675513a/config đã giữ. Không cleanup
image/cache/model/volume hoặc tạo test containers.

| Scenario sau cutover | Correlation | Kết quả thực |
| --- | --- | --- |
| Gói dịch vụ có tổng phí cao nhất, auto route |4f1c2477e09b429b9680f4aed82f230a|PASS: Gemini SQL,2 generation/0 query,4,558s;message388,1row G04/Ưu tiên/7530000 đúng PG oracle đã tính trước. Summary ranking từ sort/limit và SUM provenance; không tự gắn đơn vị. Bảng thu gọn.|
| Hồ sơ khi kiện hư hỏng, explicit /rag |f4a5d34123aa4fa18327bd69e02770d8|PASS_EXPLICIT_RAG:1 generation/1 query,2,287s;message390,citation53 khớp source file/title/content/dataset17. Đủ4 loại bằng chứng, không thêm SQL. Không phải PASS của câu auto-route policy-only đã FAIL.|

Lượt sau provider fix dùng3/4 generation,1/1 query,0 document và đã đóng. Tổng nhiệm vụ
**17/36 generation,4/12 query,0 document**,12 câu/24 messages thêm (max390),không retry,
fallback hoặc chạy Knowledge tiếp sau timeout. Không chủ động gây lỗi trả phí để kiểm
mapping; HTTP/error paths chỉ mocks; successful generation mới chứng minh success path
trên image hiện hành, không chứng minh mọi loại lỗi provider xảy ra live đều đã thử.

Tổng Langfuse12 roots/303 observations,17 generation/4 query observations khớp diagnostics,
không duplicate IDs/calls.31.528 generation tokens có usage khớp từng root;4failed calls
không usage và toàn bộ embedding tokens UNKNOWN. Full metadata privacy check303obs:
không raw input/output,questions/SQL,owner/conversation UUID thật hoặc private credentials/
Knowledge URL. Root totals là subtotals, không cộng trùng child usage. Giá Knowledge và
phần usage thiếu UNKNOWN, không coi0 hoặc báo tổng bill chính xác.

Integrity cuối:36 data objects và292 old messages≤366 vẫn khớp SHA256 fingerprint
ban đầu; chỉ thêm24messages của12requests (316messages,max390). Phiên Google/reload,
history và citation panel trên8080 hoạt động. Không sửa/migrate/xóa/re-embed main data.

Phân loại cuối: scalar/provenance/complete policy/context/presentation và provider
mapping/safety corrections có regression PASS, SQL/Hybrid/DATE/ranking/RAG live bounded
như scorecard. Knowledge reliability/access **UPSTREAM_BLOCKED/ROOT_CAUSE_UNKNOWN**, giữ
manual theo operator. COUNT+SUM exact question mới **NOT_VERIFIED** vì504; false refusal
policy-only **NOT_FIXED**. Historical raw plans không được lưu vẫn **UNKNOWN**.
Vì vậy full correction vẫn **RELEASE_BLOCKED**, không promote Knowledge/default/fallback,
không tag/Stage2 hoặc tuyên bố mọi schema hoạt động. Normal gateON/Gemini default/GuestOFF
và dữ liệu hiện có được giữ. Bản bàn giao docs sau e2722da không đổi image inputs.

Wire JSON Schema là ràng buộc cấu trúc, không tự chứng minh đúng ngữ nghĩa. Đối chiếu
[tài liệu Google](https://ai.google.dev/gemini-api/docs/structured-output?hl=en) với
serialization thực của SDK pinned trong tests. anyOf/enum vẫn phải qua conversion/binder.
Scope proof dùng COUNT khác COUNT(column) để phát hiện NULL, rồi MIN/MAX; semantics theo
[PostgreSQL 17](https://www.postgresql.org/docs/17/functions-aggregate.html).

Không hỗ trợ mọi văn bản chính sách, mọi kỳ có dữ liệu ngoài phạm vi, nhiều quy tắc hoặc
ngoại lệ. Không giả tạo filtered-policy support bằng cách bỏ WHERE/HAVING/LIMIT.
Timeout Knowledge vẫn phụ thuộc upstream; không đổi retry/fallback. BGE/public hosting,
retention/backup Langfuse ngoài phạm vi. Không báo CORRECTNESS_FIX_ACCEPTED trước live.
