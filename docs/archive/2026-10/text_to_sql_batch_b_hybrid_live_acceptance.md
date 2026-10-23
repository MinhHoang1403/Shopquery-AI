> HISTORICAL snapshot. Current status: [V2 acceptance](../../v2_final_acceptance.md).

# Batch B — Hybrid live acceptance

Ngày 21/10/2026, UTC+07:00. Workspace `C:\Work\ShopQuery AI`, ứng dụng local 8080.

**Cập nhật cuối: BATCH B HYBRID LIVE FAILED. KH FAIL, GH NOT RUN theo stop condition.**

Sau khi người dùng bật lại quyền browser, đã xác minh Google session thật và chạy KH
đúng một lần trên UI 8080. Router chọn HYBRID nhưng validator từ chối ở
**join_aggregate / count_star_alias**, trước execution guard, SQL execution và retrieval.
Không retry KH, không chạy GH hoặc dùng ngân sách còn lại để thử may rủi.

Thực tế **1 chat / 2 logical generation stages / 0 query embeddings / 0 document embeddings**.
Không fake answer/citation, không đổi production code/runtime/config, không commit/push.
Lịch sử KH reload PASS và protected integrity PASS không làm live Hybrid trở thành PASS.

Lịch sử lượt đầu: preflight đã đạt nhưng browser tool bị tắt, 0 calls, báo BLOCKED.
Giữ evidence đó ở thư mục gốc; lượt tiếp tục dùng fresh baseline riêng trong
`batch-b-20261021/live-resume-1`, cùng ledger tổng, không reset budget.

## A. Baseline và prerequisites

Đã đọc toàn bộ AGENTS.md, handoff, investigation, verification/acceptance, Batch A,
root-cause và JOIN reliability reports; review SQL/RAG/Hybrid, dependency wiring,
generation/embedding selection, repository scope và safe diagnostics. Các kết luận cũ
“chưa deploy” trong handoff/report là snapshot lịch sử; dùng baseline hiện tại dưới đây.

| Thành phần | Kết quả read-only trước/sau |
|---|---|
| API | `fd62fc397a91153f36bf9a3bc378283d0664e1754b2993a86d2b6433b664e67f` |
| Web | `2af67d527f2e6b63386c7371c4970bc8c21431e063c9db990040d8f271fe211d` |
| PostgreSQL | `511c4f5aacccd1ac42261aaa2a7173ae40c5c5e3aa673bb4898d988a8206a3c8` |
| API image | `sha256:1a96e048886281ff5d7742e21cb1374e2e88571556c769bcdad3b29990b36417` |
| App source manifest | `bd500b4c2a56631f91751a086c5e092178f4fc9c6a642b7d5acada2e66a1e238`, 71/71 modules khớp local/runtime |
| Main volume | `shopquery-ai_postgres_auth_20261019` |
| Health | Ba services healthy, RestartCount=0; 8001/api/health và 8080/api/health HTTP 200 |
| Compose | compose.yaml + .env.compose-ui.yaml + .env.join-v1.yaml; merged API environment khớp runtime |
| Environment digest | `ddcd7de55005f7fb5dcf88cbdf7614354867ba0e58a864c9e618ae4e28dd60c7`, khớp Batch A |

JOIN=true; Knowledge `knowledge`; Gemini `gemini-3.5-flash-lite`; embedding
`gemini-embedding-2`/768; fallback=false. Không thay gates, retries/timeouts, quotas,
OAuth, prompts, models hoặc secrets. Digest so toàn bộ environment trong memory;
không in hoặc lưu full resolved environment.

### Workspace 13

- Đúng tên **Root audit synthetic · 21-10-2026**, registry và physical table identifiers
  khớp Batch A. PostgreSQL target xác minh `current_database() = shopquery`.
- 50 delivery orders / 15 drivers / 5 warehouses; catalog columns/types khớp mapping
  upload hiện có (`TEXT` metadata → SQLAlchemy String → PostgreSQL varchar).
- Owner metadata khớp Google user hiển thị ở UI. Sau khi quyền browser hoạt động,
  phiên đã đăng nhập truy cập được workspace 13; reload vẫn giữ đúng account/workspace.
  Không quan sát fresh OAuth flow và không đọc/export cookie/token.
- Đúng hai relationships orders.tai_xe_id → drivers.tai_xe_id và drivers.kho_id →
  warehouses.kho_id. Revisions/statistics khớp Batch A; full-data verification hiện tại
  valid, zero source/target NULL keys, duplicate target keys và orphans.
- Chỉ đọc scoped metadata/synthetic rows; không confirm lại, không tạo temp tables,
  migration hoặc thực thi generated SQL bằng setup role.

Các audit SQL chạy REPEATABLE READ, READ ONLY, statement timeout 30s, lock timeout 3s,
rollback cuối transaction. Không chạy destructive pytest fixtures trên main.

## B. Independent SQL và document oracle

### SQL oracle mới, trước mọi live request

SELECT tự viết theo approved graph, root orders, INNER JOIN drivers rồi warehouses,
GROUP BY warehouse ID/name, SUM root fact fee và COUNT(*), không lọc trạng thái.
Kết quả so exact Decimal với saved Batch A/Gate D oracle, không lấy model SQL làm expected.

| Warehouse ID | Tổng phí VND | Fact rows | KPI theo policy thật |
|---|---:|---:|---|
| KHO01 | 393500.00 | 10 | Chưa đạt |
| KHO02 | 598000.00 | 10 | Đạt |
| KHO03 | 502000.00 | 10 | Đạt |
| KHO04 | 439000.00 | 10 | Chưa đạt |
| KHO05 | 540000.00 | 10 | Đạt |

Tổng **2472500.00 / 50 facts / 5 identities**. Qualifying IDs:
**KHO02, KHO03, KHO05**, so Decimal với 500000.00, không làm tròn.

### Persisted policy — không dùng file local thay DB âm thầm

Đã đọc trực tiếp đúng scoped document/chunk trong main, rồi mới đối chiếu saved file
Gate D bằng parser/chunker offline (không embedding, không ingestion):

- Workspace 13 có đúng **một document**, `live_gate_d_kpi.md`, **document_id=12**.
- Đúng **một chunk**, **chunk_id=22**, cùng dataset/document/source_file, có vector
  **768 dimensions**, nonzero. Không cần re-ingest/re-embed.
- Nội dung persisted chunk khớp chính xác content/section của saved policy sau parse;
  document hash khớp bytes file saved, namespaced chunk hash khớp công thức ingestion.
- Policy thực sự quy định tổng `phi_giao_vnd >= 500000.00 VND`, **tất cả trạng thái**,
  nối đơn qua tài xế/kho_id, phân biệt bằng kho_id; SUM bỏ NULL, zero là giá trị hợp lệ.
  Không có policy khác trong workspace 13 tạo ambiguity cho phép thử này.

| Evidence | SHA-256 |
|---|---|
| Document content/file | `eecd50cc75196867364b3cd312cd6712b0d9933e359445f57f7c313926f419aa` |
| Persisted chunk text | `15f159e4bd6ad052a668315cc1813f3b1fbfbe0775d07aafd02636cd0d4b5bf6` |
| Vector text representation | `8a17170df62f0f6234546079a41c78f6329f33dd6ffc762f09476cc2d4416b8a` |

Vector presence/dimensions/nonzero và hash không chứng minh semantic retrieval quality.
KH bị chặn trước query embedding/retrieval; GH không chạy. Không có actual retrieved ID set.
ID 22 là eligible persisted evidence, **không được gọi là live retrieved citation**.

Source review xác nhận `RagPipeline.retrieve` gọi đúng một query embedding rồi repository
lọc dataset_id=13 cùng owner existence check, top_k=3. Hybrid giữ SQL-first; citations
chỉ chấp nhận IDs từ chunks thực retrieved. Vì corpus workspace này chỉ một chunk,
successful scoped retrieval dự kiến có ID 22; vẫn phải xác minh sau live, không mô phỏng PASS.

## C. Live probe results

| Case | Provider | SQL | Oracle | Retrieval | KPI | Citations | History | Result |
|---|---|---|---|---|---|---|---|---|
| KH | Knowledge | FAIL validator: count_star_alias; chưa execute | Response rows NOT REACHED | NOT REACHED | NOT RUN | NOT RUN | Reload PASS (refusal) | FAIL |
| GH | Gemini | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN — dừng sau KH FAIL |

### KH — bằng chứng actual response

- User message **151**, assistant **152**, conversation
  `b04e1d44-e779-4afd-8a59-04bc74124839`, owner matches selected workspace.
- Correlation ID `a572671ad82e458a85644ccdf1c6d502`; request duration **7115.935 ms**.
- Workspace binding, approval, schema metadata: success; **3 allowed tables / 2 approved edges**.
- Router stage success, route **HYBRID**. Generator/structured parsing, SQL parse và column
  resolution success; sau đó **join_aggregate status=failure, reason=count_star_alias**.
- `sql_validated=false`, `execution_reached=false`, result_rows=0. Không có stage
  execution_guard, sql_execution, answer_grounding hoặc document_retrieval trong trace.
- Persisted response: requested_model=used_model=`inetcloud-knowledge`, fallback=false,
  final route=UNSUPPORTED, error=null, sql=null, rows=[], sources=[]. HTTP nghiệp vụ/error=null
  không có nghĩa acceptance PASS. Không có evidence provider 503/timeout trong request này.
- UI hiển thị “Chưa thể trả lời” và refusal ngắn. Reload thật giữ cùng Knowledge, câu hỏi,
  answer/refusal và không có evidence giả; đọc lại đúng hai synthetic messages cho thấy
  content/response_metadata giữ nguyên. Screenshot mới `KH-history.png`, không dùng ảnh cũ.
- Model attribution dựa trên metadata + selected gateway/config + safe diagnostics;
  không có independent provider billing trace hoặc raw SqlDraft capture.

Đã gửi **nguyên văn một lần** câu QH sau, không inject oracle/threshold/SQL template:

> Theo tài liệu live_gate_d_kpi.md, những kho nào đạt KPI tổng phí? Với từng kho, cho biết mã kho_id, tên ten_kho, tổng phi_giao_vnd của tất cả trạng thái, số dòng đơn và kết luận đạt/chưa đạt. Kết hợp dữ liệu đơn giao hàng → tài xế → kho với điều kiện trong tài liệu, phân biệt kho theo mã ID.

Đã dừng đúng failure đầu tiên. GH không có request/correlation/model result để báo.

## D. Root-cause closure

| Historical failure | Điều đã chứng minh | Batch B closure hiện tại |
|---|---|---|
| KH join_aggregate/count_star_alias | COUNT-order false refusal được tái hiện/sửa và kiểm thử offline; runtime hiện có fix | **Vẫn FAIL cùng subtype** trong KH mới; raw biểu thức/clause chưa biết |
| GH generator_unsupported | Prompt SQL-evidence-only/Hybrid boundary được làm rõ; valid scripted flow đã chạy offline | **NOT RUN**, không khẳng định lỗi đã giải quyết |

Batch A K2/K3/G3 PASS không thay thế Hybrid acceptance. Không có raw rejected SqlDraft
lịch sử hoặc KH mới để quy mọi failure cho ORDER BY/alias hoặc missing policy instruction.
Không bật instrumentation/raw production logging, không capture rejected draft mới.

### Đối chiếu offline sau failure, không patch

Review `_validate_join_aggregates`/`_normalize_selected_count_order` xác nhận subtype vẫn
có nhiều hình dạng đầu vào. Ba counterexamples synthetic trên validator hiện hành đều
tái hiện `count_star_alias`:

1. SELECT COUNT(*) dùng alias khác canonical row aliases.
2. SELECT chỉ SUM nhưng ORDER BY COUNT(*) không có selected COUNT tương ứng.
3. SELECT chỉ SUM nhưng HAVING COUNT(*) không có Alias parent.

Canonical SELECT COUNT(*) AS fact_row_count + repeated ORDER BY cùng COUNT vẫn validate
PASS. Đây là **hypotheses**, không phải raw SQL của KH. Chưa biết case nào ứng với live
request; không thể chứng minh normalizer đã/không kích hoạt từ final refusal.

Targeted offline hiện có: `test_sql_generation_contract.py`, `test_join_policy.py`,
`test_routing_and_hybrid.py`, `test_diagnostics.py`: **127 PASS, 6.52s**. Process test đặt
JOIN=false, provider credentials/endpoints rỗng, không integration/live opt-in hoặc DB
fixture main. Giữ assertions COUNT semantics, wrong keys/dimension aggregates, no executor/
answer on refusal và diagnostics redaction. Không cộng 127 vào 400 Batch A vì overlap.
Không có production bug mới đủ bằng chứng để chọn patch cụ thể cho KH; cần raw synthetic
draft có scope được duyệt hoặc diagnostic clause metadata bổ sung trong nhiệm vụ riêng.

## E. Budget ledger

| Hạng mục | Được duyệt | Thực tế |
|---|---:|---:|
| Chat probes | 2 | **1 (KH)** |
| Logical generation stages | 8 | **2 (router + SQL draft)** |
| Query embeddings | 2 | **0** |
| Document embeddings/ingestion | 0 | **0** |

Ledger riêng `C:\Work\ShopQuery-Backups\batch-b-20261021\ledger.json`, cases=[KH FAIL];
không reset hoặc thay ledger Batch A/Gate D. Collector chỉ đọc synthetic evidence;
provider calls đi qua **UI thật**, không gọi API chat trực tiếp/embedding smoke.
Hai generation stages và zero embedding suy từ verified control flow + trace; không có
HTTP attempt instrumentation. Không khẳng định chỉ có hai HTTP requests hoặc không SDK retry.

Khi live được chạy, successful flow giữ 4 stages: router → draft → SQL grounding →
Hybrid synthesis; đúng một query embedding giữa SQL và synthesis. SDK retries và
Knowledge structured-format attempts hiện hữu có thể tăng HTTP requests, không phải
extra logical chats. Không đồng nhất logical stage count với HTTP/billing count.

## F. Data integrity và runtime

Lượt blocked giữ snapshot **13:41:02 +07:00**. Lượt live có **fresh synthetic snapshot
14:12:36 +07:00**, protected-before mới trước KH; postflight sau failure lúc khoảng
**14:14:50 +07:00**. Không dùng historical hash giả làm snapshot mới. Protected scope
đúng map 26 bảng Gate D/Batch A, loại auth/session/OIDC và operational counters/leases;
dataset-scoped registry/docs/history loại workspace 13 theo cùng clauses đã duyệt.
Fingerprints tính server-side, không xuất raw customer rows/private conversation contents.

```text
26-table map trước: f73b828698b29380b28b5ae89a654df52115bef858ed7a4c246a2b11c84fa736
26-table map sau:   f73b828698b29380b28b5ae89a654df52115bef858ed7a4c246a2b11c84fa736
```

26/26 row counts và hashes bằng fresh baseline, khớp historical evidence, không ngoại lệ.

| Synthetic table | Rows | SHA-256 trước = sau |
|---|---:|---|
| 01_kho_dieu_phoi | 5 | `620f96493460345ced5238deefbe74fa2e5d0bde56577cd375401ab50b868ec6` |
| 02_tai_xe | 15 | `26067db192f694b212bb119164d4449fc78f4785e8049b373b5d2fcc2a66cc93` |
| 03_don_giao_hang | 50 | `9f46ec4e1aa93f68f2fb31ef2b015d6e1c4eaf12a599249719fe6606eb75625c` |

Relationship metadata/revision/verification map hash trước=sau:
`b6efa9f655ef7aa09af8c455039007f129e3620bdc967af96f1ae7e8f776517d`.
Policy metadata/content/vector hashes trước/sau khớp toàn bộ, cùng document/chunk IDs.
Synthetic message high watermark **150 → 152** trong cửa sổ live: đúng một user turn 151
và assistant turn 152 của conversation mới, owner đúng; collector scoped watermark chỉ
nhận hai messages này. Giữ conversation/refusal history và corresponding quota effects.
Không đọc nội dung các chat cũ để suy ra hoạt động người dùng giữa Batch A và fresh baseline.

Không reset history/quotas, không sửa accounts/sessions hoặc đọc session secrets.
Không tuyên bố toàn DB byte-for-byte bất biến ngoài scope hashes. API/web/DB IDs,
images, 71-module manifest, environment digest và health giữ nguyên. Không Docker
cleanup/restart/build hoặc DB test mới; targeted validator/Hybrid/diagnostics unit tests
không cần PostgreSQL integration fixtures.

Private evidence ngoài Git: `C:\Work\ShopQuery-Backups\batch-b-20261021\` giữ snapshot
blocked và ledger tổng. Subfolder **live-resume-1** giữ fresh runtime/synthetic/protected
before/after, KH-response/diagnostics/verification/history screenshot và offline-hypotheses.
Helpers `batch_b_acceptance.py`, `batch_b_live_evidence.py` chỉ audit/evidence read-only
hoặc validator offline; không gửi provider requests, không ghi đè evidence Batch A/Gate D.

## G. Cross-domain implications

Review static không thấy Hybrid hardcode logistics hoặc tên `live_gate_d_kpi.md`:
dynamic SQL metadata/approved graph nằm trong context; DocumentRepository scope bằng
dataset/owner; Hybrid nhận SQL rows và retrieved content/chunk IDs từ workspace hiện tại.
Prompt yêu cầu giữ exact Decimal/NULL/zero và dùng thuộc tính thật, không biến mọi row
thành product. Một số ví dụ demo store vẫn hiện diện nhưng có boundary theo selected
workspace; ảnh hưởng bias provider ngoài logistics chưa được đo.

Batch A đã chạy 400 offline tests trên sáu domain, gồm RAG/Hybrid fake-provider contracts.
Đó là evidence implementation/guards, không chứng minh providers tự hiểu mọi schema/
policy. KH mới bị chặn trước RAG nên Batch B chưa đo live retrieval/synthesis/citations ở logistics,
càng không đo live cross-domain Hybrid. Không thêm shortcuts/domain mapping/repair loop.

## H. Final verdict

**BATCH B HYBRID LIVE FAILED**: KH FAIL tại COUNT aggregate guard, GH NOT RUN theo stop
condition. Phạm vi thực thi là một trong hai probes; không lấy câu trả lời Batch A thay
Hybrid PASS. Quyền browser và authenticated UI đã hoạt động trong lượt tiếp tục này.

Runtime/data/policy/oracle/integrity prerequisites đạt. COUNT-order fix không bảo đảm
mọi COUNT draft sinh bởi model sẽ hợp lệ; chưa xác định raw failing expression/clause.
Không có bằng chứng cần đổi models/retries hoặc nới security; không patch theo phỏng đoán.

## I. Next steps và Git

1. Không chạy lại KH, không chạy GH hoặc dùng phần budget chưa tiêu sau failure. Stop
   condition kết thúc quyền thực thi live của lượt này; probes tương lai cần duyệt riêng.
2. Bước điều tra hẹp tiếp theo: thu riêng raw SqlDraft/unsupported reason của **một
   synthetic request được định danh** vào private evidence nếu được duyệt phương án và
   budget mới; không bật raw logging production hoặc gửi data thật. Hoặc xin duyệt thêm
   bounded diagnostics nêu clause/parent type/count-argument-shape mà không SQL/values.
   Những phương án này chưa triển khai và không tự cấp thêm live call trong task hiện tại.
3. Khi có draft đúng case, replay offline cùng authenticated metadata/context shape,
   kiểm SELECT/ORDER/HAVING count aliases và oracle. Chỉ đề xuất patch nhỏ có evidence;
   không auto-repair COUNT(nullable), key/grain hoặc bỏ guard. Không có bản sửa tối thiểu
   cụ thể được chứng minh cho request KH mới khi thiếu draft; chưa tự patch/deploy.
4. Cross-domain SQL live holdout học phí/nhân sự đề xuất ở Batch A vẫn chưa được duyệt/chạy.
   Sau Batch B PASS có thể xin riêng Hybrid tuition holdout: courses/students/payments,
   policy synthetic **khóa học đạt ngưỡng tổng thanh toán >=40.00**, all payments, preserve
   NULL/zero; Knowledge và Gemini cùng một câu “Theo quy định trong tuition_policy.md,
   khóa học nào đạt ngưỡng? Cho biết course_id, course_title, tổng amount_paid, số dòng
   payments và kết luận từng khóa học; phân biệt theo ID.” Independent fact-mapping PG
   VALUES oracle + document oracle phải chốt trước live. Dự kiến **2 chats / 8 generations /
   2 query embeddings**, thêm tối đa **1 document embedding** nếu policy mới có đúng một
   chunk. Cần duyệt riêng tạo/upload synthetic workspace/document và budget; **chưa thực hiện**.
5. Chỉ đề xuất review rồi commit source/tests/docs đã nghiệm thu sau phê duyệt riêng;
   không commit/push trong task này. HEAD vẫn `e2151a3d6b37f3a11e83f68553e5985bbe087deb`.

Chỉ thêm báo cáo này vào repository; giữ toàn bộ dirty production/tests/docs/handoff có
trước, không sửa prompt/validator/Hybrid source. Không chạy lại full suites/CI vì không có
production source change; 400 tests Batch A và 635/558/66/105 baseline vẫn là kết quả
lịch sử. Chỉ **127 targeted offline tests** vừa chạy sau KH failure; không full regression/
frontend/CI mới. `git diff --check` PASS trước bàn giao.
