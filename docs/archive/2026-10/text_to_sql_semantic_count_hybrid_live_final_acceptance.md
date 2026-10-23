> HISTORICAL snapshot. Current status: [V2 acceptance](../../v2_final_acceptance.md).

# Semantic COUNT + Knowledge/Gemini Hybrid — final live acceptance

Ngày21/10/2026, Asia/Ho_Chi_Minh. Local8080, workspace ShopQuery AI.

> **Cập nhật mới nhất: HYBRID LIVE FAILED — KH FAIL / GH NOT RUN.**
> Chủ dự án xác nhận có chat thêm và duyệt tiếp tục với fresh baseline26 bảng.
> Lượt tiếp nối đã chạy1 KH: semantic COUNT/SQL/oracle/retrieval/citation đạt,
> nhưng final answer bỏ KHO02 khỏi phần tóm tắt dù chi tiết ghi KHO02 đạt.
> Dừng live, không chạy GH. Xem mụcI; phần A–H giữ nguyên evidence lượt blocked.

## A. Verdict và ngân sách

**BLOCKED — NO LIVE PROBES.**

Không có kết quả live mới. KH/GH đều **NOT RUN**, không phải FAIL của model hoặc
validator. Dừng tại protected historical fingerprint gate trước khi gửi câu hỏi.
Không dùng CI/oracle/health để thay thế provider/UI acceptance.

| Case | Provider | Semantic COUNT | SQL | Oracle live | Retrieval | KPI live | Citations | History mới | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| KH | Knowledge | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN — preflight blocked |
| GH | Gemini | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN — preflight blocked |

| Budget mới | Max | Thực tế |
|---|---:|---:|
| Logical chat probes | 2 | **0** |
| Logical generation stages | 8 | **0** |
| Query embeddings | 2 | **0** |
| Document embeddings | 0 | **0** |
| Upload / chat retry | 0 | **0** |

Không reserve/send probe, ledger cases=[]; không SDK/structured retry do agent
kích hoạt vì chưa có provider stage nào được gọi. Không tuyên bố toàn hệ thống
không có user requests đồng thời; số0 thuộc tác vụ của agent.

Ngân sách mới còn nguyên nhưng chưa sử dụng được khi historical gate chưa được
giải thích/duyệt. Không reset hoặc dùng ledger Batch A/B cũ.

## B. Runtime/source/config preflight và postflight

Git HEAD/main:
`d9bcce165d6af2124866770c2879a74cbb3a207c`.
Code commit:
`273895d63193a7d05903dd0236045532cc4ef2b1`.
Working tree sạch trước tác vụ. Không sửa production code hoặc tests.

CI của đúng docs HEAD đã kiểm bằng gh CLI:
completed/success, [run39575885127](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39575885127).
Baseline:770 backend unit,682 PG integration,67 frontend unit,105 mock UI.
Không chạy lại suites lớn trong lượt chỉ nghiệm thu này.

| Service | Full ID | Health trước/sau |
|---|---|---|
| API | 8a39b1cb69a0f89c49d6976996f89b29019abdc289bc805f58a25b7aa7b19f72 | healthy / healthy |
| Web | 2af67d527f2e6b63386c7371c4970bc8c21431e063c9db990040d8f271fe211d | healthy / healthy |
| DB | 511c4f5aacccd1ac42261aaa2a7173ae40c5c5e3aa673bb4898d988a8206a3c8 | healthy / healthy |

API image:
`sha256:4bbf907c554099a7d542a53b10b5850b6bfc56d7ba1e9ebb499c696cc2c0151b`.

**72/72 local/runtime module hashes khớp** deployment snapshot, trước và sau:
`47b9d4083e13bf32d79c441681d344dcf3f88ea1e5c679604a8f0db1d7f59586`.
Đúng LF-normalized manifest method trong deployment report. count_contract.py
có mặt; validator gọi analyzer sau graph/grain rồi revalidate không rewrite,
provenance được chuyển tới SQL/Hybrid grounding. Source call-flow review không
phải bằng chứng analyzer đã xử lý một live draft mới: chưa có probe.

Container identities/images/StartedAt/RestartCount/mounts/ports/networks,
70 package versions và volume metadata khớp deployment baseline, cả trước/sau.
Active volume shopquery-ai_postgres_auth_20261019; archived
shopquery-ai_postgres_data còn nguyên. Ba Compose files đúng
compose.yaml + .env.compose-ui.yaml + .env.join-v1.yaml.
Không recreate/restart/build bất kỳ service nào.

Environment digest trước/sau và deployment:
`5593c011af92e092eb2d7d4fdb59a01d4ad4b37137e63a452159e782090e236f`.
Chỉ digest/allowlisted settings, không export full env/secret values.
Merged Compose/runtime0 mismatch. JOIN=true; Knowledge=knowledge;
Gemini=gemini-3.5-flash-lite; embedding=gemini-embedding-2/768; fallback=false.
Gates/quotas/retries/timeouts/OAuth không đổi. API target đúng db:5432/shopquery.
GET health8001/8080 status ok; không gọi chat để smoke-test.

## C. Browser và owner scope

Áp dụng computer-use skill; dùng browser automation cho UI thật, không fake session
hoặc backend chat calls. Inventory lúc đầu không có tab8080; đã mở tab8080 mới.
Phiên Google bình thường còn hợp lệ, không cần người dùng đăng nhập lại.
Không đọc/export cookies, access tokens, OAuth/session secrets.

UI khôi phục conversation thuộc workspace khác lúc mở trang. Không mở thêm
evidence hoặc gửi câu hỏi ở workspace đó; đã chuyển ngay sang chat mới và chọn
**Root audit synthetic · 21-10-2026**. Không sử dụng nội dung lịch sử đó làm oracle.
Không đưa PII hoặc private chat text vào báo cáo/evidence acceptance.

Authorized dataset13 owner khớp expected account đang hiển thị; private metadata
check chỉ lưu boolean match, không email trong public report. UI xác nhận3 bảng/
1 tài liệu, model mặc định Knowledge. Chưa nhập hoặc gửi câu hỏi nghiệm thu.
Tab được giữ để tiếp tục sau khi xử lý blocker; không tự đăng nhập hoặc đổi quyền.

## D. Fresh synthetic metadata/SQL/document oracles

Read-only audit qua main connection: REPEATABLE READ, READ ONLY,
statement_timeout30s, lock_timeout3s, rollback cuối phiên.
Không thực thi provider-generated SQL bằng setup role; chưa có generated SQL.

Ba physical table identifiers/catalog/source headers/types khớp saved synthetic
registry. Exactly2 approved edges, đúng direction/revision; full-data verification
valid, target unique, no NULL keys/orphans. Không xác nhận lại/sửa relationships.

| Synthetic source | Rows | Fresh hash trước=sau |
|---|---:|---|
| 01_kho_dieu_phoi | 5 | `620f96493460345ced5238deefbe74fa2e5d0bde56577cd375401ab50b868ec6` |
| 02_tai_xe | 15 | `26067db192f694b212bb119164d4449fc78f4785e8049b373b5d2fcc2a66cc93` |
| 03_don_giao_hang | 50 | `9f46ec4e1aa93f68f2fb31ef2b015d6e1c4eaf12a599249719fe6606eb75625c` |

Fresh independent SQL oracle tự viết theo approved graph, trước mọi live request;
không lấy generated SQL làm expected. So từng identity/name/Decimal/SUM/COUNT với
saved oracle: exact match.

| kho_id | ten_kho | SUM phi_giao_vnd | COUNT fact rows | Persisted policy KPI |
|---|---|---:|---:|---|
| KHO01 | Kho Hà Nội | 393500.00 | 10 | Chưa đạt |
| KHO02 | Kho Hải Phòng | 598000.00 | 10 | Đạt |
| KHO03 | Kho Đà Nẵng | 502000.00 | 10 | Đạt |
| KHO04 | Kho TP.HCM | 439000.00 | 10 | Chưa đạt |
| KHO05 | Kho Cần Thơ | 540000.00 | 10 | Đạt |

Tổng2472500.00/50 fact rows/5 entities. Qualifying KHO02,KHO03,KHO05.
Source table hashes khớp fixture lịch sử có4 NULL/3 zero fees; không gọi đó là
một live COUNT/non-NULL validation mới.

Persisted document/chunk:
- live_gate_d_kpi.md, document12, chunk22.
- Đúng một document/chunk trong workspace13; dataset/document/source binding đúng.
- Embedding768 dimensions, nonzero.
- File/document hash:
  `eecd50cc75196867364b3cd312cd6712b0d9933e359445f57f7c313926f419aa`.
- Chunk text hash:
  `15f159e4bd6ad052a668315cc1813f3b1fbfbe0775d07aafd02636cd0d4b5bf6`.
- Persisted content/section/hash khớp saved synthetic policy bằng parser/chunker
  offline; không embedding/ingestion.
- Policy tổng phi_giao_vnd tất cả trạng thái >=500000.00, group kho_id,
  JOIN qua tài xế, SUM bỏ NULL và giữ zero.

Metadata/revisions/statistics, policy/chunk/vector evidence trước/sau bằng nhau.
Chunk22 là **eligible persisted evidence**, chưa được actual live retrieve/cite.

## E. Blocker — protected history drift

Dùng đúng scope26 bảng và exclusion predicates của Gate D/Batch A/B:
loại auth/session/OIDC, counters/leases; loại workspace13 khỏi scoped metadata/
history bằng exact clauses có sẵn. Không tự thêm/bỏ bảng hoặc thay hash method.
Hash/count tính server-side; không xuất raw customer rows hoặc private chat text.

Fresh before: **2026-10-21T16:35:54.076945+07:00**.
Fresh after: **2026-10-21T16:37:15.254259+07:00**.

Historical26-table aggregate:
`f73b828698b29380b28b5ae89a654df52115bef858ed7a4c246a2b11c84fa736`.

Fresh before=after26-table aggregate:
`c4ffe3daf04d2c1a20eb502b6613478526c7ceb4db401f39fe0b898da05afd6a`.

24/26 tables khớp historical. Hai khác biệt đã có **trước mọi live probe**:

| Protected table (không gồm synthetic13) | Historical rows | Fresh rows | Hash |
|---|---:|---:|---|
| public.chat_conversations | 7 | 7 | Khác historical |
| public.chat_messages | 52 | 54 | Khác historical |

Historical conversation hash:
`3bff0a15aa369274aaacb5564d3c0c27f252515231176c9f36794dc952aac95a`.
Fresh conversation hash:
`c740da116990d5ffe542f27dcfbb496fe6d8e0350eab9d0aa06a070a59eb7a07`.
Historical messages hash:
`5c732c6b2e0467f64d4a85b57d94ae41aba960bd340c1885facb059f2b0a9ad5`.
Fresh messages hash:
`5f6423dfd605d5a1d7761eb45f7cec4c09752f90c6dad46aade1a1710d0dd81f`.

**Confirmed:** protected chat_messages tăng2 rows, conversations count không đổi
nhưng row content hash thay đổi. Không có protected business/source table drift khác.
Các số này không đủ chứng minh authorship, role của2 messages hoặc mọi thay đổi
chỉ là append/timestamp/model updates. Hoạt động chat thông thường là giả thuyết
hợp lý, **không phải nguyên nhân đã xác minh**. Không đọc private conversation
contents hoặc mở rộng audit để suy đoán.

Theo yêu cầu, historical mismatch chưa giải thích được phải dừng trước live.
Gate vẫn **FAIL/BLOCKED**. Không tự lấy fresh baseline thay historical, không
loại hai history tables hoặc sửa/xóa messages để làm hash khớp.

Postflight đối chiếu fresh26 trước/sau exact match; việc này chỉ cho thấy không
quan sát thêm drift trong cửa sổ preflight/postflight, **không sửa historical gate
thành PASS**. Helper vẫn giữ ledger BLOCKED, historical_gate_pass=false.

## F. Exact fresh protected matrix

Mỗi dòng: fresh before=after count/hash. Không xuất row contents.
Historical comparison không đồng nghĩa toàn database byte-for-byte bất biến ngoài
scope đã định nghĩa.

| Fully qualified table | Rows trước=sau | SHA-256 trước=sau | So historical |
|---|---:|---|---|
| public.categories | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | Khớp historical |
| public.chat_conversations | 7 | `c740da116990d5ffe542f27dcfbb496fe6d8e0350eab9d0aa06a070a59eb7a07` | Khác historical |
| public.chat_messages | 54 | `5f6423dfd605d5a1d7761eb45f7cec4c09752f90c6dad46aade1a1710d0dd81f` | Khác historical |
| public.dataset_documents | 3 | `ef814e7dda2a785a489d5f02900d37cd14876a7006ab6ae8a297616150b641c8` | Khớp historical |
| public.dataset_relationships | 3 | `77ee93f4e0313c3d58e1668e1aebbe585f4192bdb718a121cb1f12f8d8da1a66` | Khớp historical |
| public.dataset_tables | 14 | `748337496998ed6c8c89fa9b316f11780d7a37210b130f471a34f43ad90d6509` | Khớp historical |
| public.datasets | 7 | `9e0f86c79efdca100ca11d503ee62ebe6c5b870a3122c5752f7a3dd8bf77496d` | Khớp historical |
| public.document_chunks | 13 | `b392ae510526a4f49b83436dc4d77d09ad2ca520e1149cb34a3b778c614fc219` | Khớp historical |
| public.order_items | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | Khớp historical |
| public.orders | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | Khớp historical |
| public.products | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | Khớp historical |
| public.schema_migrations | 2 | `719885e21c0bdaeb1501623a5eeb12fbde79a358109d687ea2e6a8518fb3fd54` | Khớp historical |
| uploaded_data.dataset_086722ed634f40ef8896a6a1c988e3f8 | 50 | `9f46ec4e1aa93f68f2fb31ef2b015d6e1c4eaf12a599249719fe6606eb75625c` | Khớp historical |
| uploaded_data.dataset_08bc443109ed472c87c3db78e29543e7 | 8 | `d24753760a22dbc5270a5b6efdef00ebdb1778560c480969c0a74f470cd577e0` | Khớp historical |
| uploaded_data.dataset_31432ce91bd0468e9adc203bb7099a49 | 150 | `028b8e0156318da3dbe462e61d9d0570c28d75b845033736d92f0c5e30484d88` | Khớp historical |
| uploaded_data.dataset_38e0025dfd124f21b566fa998268ef24 | 2000 | `108ac04ac73eb54734d42c56b53d2934835d25be41846fc0a4028a9a8ecf302a` | Khớp historical |
| uploaded_data.dataset_5098e8184ca14def93b04e1f30f82116 | 5 | `620f96493460345ced5238deefbe74fa2e5d0bde56577cd375401ab50b868ec6` | Khớp historical |
| uploaded_data.dataset_6168d435c6664b05ad268cb70d42feb0 | 12 | `c72ccf30fb832be7be490510df4250a87d14e542d7fb4e61870800690eed7a3c` | Khớp historical |
| uploaded_data.dataset_7c7bd4ddd79344c98ad5476bcec095aa | 7 | `bd49884c5f945585c757fb2a19017bfef8717b8e1efb488ec507c0c256f6e45a` | Khớp historical |
| uploaded_data.dataset_929e9308a7ec43949ca0bc31d3e0764f | 12 | `8df87d531b5bece2560a411ccea58af3f412a66de18caad72415974379b9e6ad` | Khớp historical |
| uploaded_data.dataset_9f400b3d21154054a85599b4238ee065 | 14 | `e2c0cf3246f807d6ae52032fdceb4372595197d8881be3ca449d1d67212dadb8` | Khớp historical |
| uploaded_data.dataset_bafe53d0f9cc4e85aa02166d5e36b907 | 15 | `26067db192f694b212bb119164d4449fc78f4785e8049b373b5d2fcc2a66cc93` | Khớp historical |
| uploaded_data.dataset_df59e073b42d4357b857ab0080854947 | 5 | `e2ccf9429267447c0ef83e37ef0883c4b5e5a5da26e654ced535cc35f2f3d4b1` | Khớp historical |
| uploaded_data.dataset_e7702896349f47efb3201e2bda3becd7 | 7 | `bd49884c5f945585c757fb2a19017bfef8717b8e1efb488ec507c0c256f6e45a` | Khớp historical |
| uploaded_data.dataset_ec6c0c0fdff94096a4c443bc46448c21 | 12 | `1337c8ceaaefbdb67f572623842da9a2af17017eaa259d9904720b58f7ae30fb` | Khớp historical |
| uploaded_data.dataset_fb22101c59d84973ba8954c5ffbe88f0 | 12 | `1337c8ceaaefbdb67f572623842da9a2af17017eaa259d9904720b58f7ae30fb` | Khớp historical |

## G. COUNT verification và giới hạn

Old alias-based guard đã được thay typed analyzer theo AST + approved active INNER
edges. ROW_COUNT khác NON_NULL_VALUE_COUNT; business aliases là labels, không proof.
Exact ON/root/entity grain, SELECT-only, owner/revision/read-only execution giữ nguyên.

Bằng chứng offline/CI của semantic redesign vẫn PASS trên cùng manifest.
Trong lượt này chưa có live SqlDraft, actual CountKind/alias, normalization event,
execution guard, rows/grounding, retrieval/citations hoặc history reload mới.
Không tạo fake values hoặc đánh dấu những bước này PASS từ code inspection.

DISTINCT/FILTER/nesting/HAVING/unprojected metric sorting và unsafe graph/grain
vẫn có thể unsupported đúng thiết kế. Historical KH raw draft shape vẫn UNKNOWN.
Không capture raw rejected draft hoặc bật logging mới.

Failure classification hiện tại: **preflight integrity blocker**, không phải
validator false refusal, generation mistake, provider/RAG/citation failure.
Không có correlation ID chat mới vì chưa gửi probe.

## H. Changes, evidence và hướng xử lý cần phê duyệt

Không sửa production source/tests/config, không deploy/restart, migration/restore/
seed/upload/re-ingest, relationship/data/history/quota resets, Docker cleanup hoặc
commit/push. Main queries chỉ read-only trong phạm vi được duyệt.
UI new-chat/dataset selection không tạo chat response; ledger cases=[].

Thay đổi repository duy nhất của lượt này: báo cáo local này.
Private helper/evidence ngoài Git:
`C:\Work\ShopQuery-Backups\semantic_count_live_final.py`,
`C:\Work\ShopQuery-Backups\semantic-count-kh-gh-20261021-final\`:
ledger.json, before/after runtime snapshots, synthetic-before/after.json,
protected-before/after.json. Không overwrite/reset evidence các lượt cũ.
Protected helper giữ nguyên historical assertion; postflight chỉ lưu equality
fresh before/after và vẫn kết luận historical gate chưa PASS.

Một lệnh PowerShell summary đầu bị parser error trước khi đọc/query chạy; sửa
cú pháp và đọc lại metadata đã có, không phải lỗi ứng dụng hoặc thêm provider call.

Cần chủ dự án xác nhận có hoạt động chat ngoài synthetic13 sau baseline Batch A/B
và phê duyệt **rebaseline riêng historical history drift**:
- Chấp nhận fresh26 baseline sau khi giải thích được chênh lệch; không xóa/bỏ hai bảng.
- Khi tiếp tục lấy fresh before mới, giữ đủ26 tables/exact predicates và so before/
  after nghiêm ngặt; giữ synthetic source/relations/policy oracle không đổi.
- Không reset ledger hay ngân sách đã dùng; hiện0/2 chats,0/8 generations,0/2 query
  embeddings. Ghi approval mới rồi tạo snapshot tiếp nối, không overwrite lần blocked.
- Nếu không phải hoạt động chat được người dùng biết/duyệt: giữ BLOCKED, xin phạm vi
  read-only metadata bổ sung, không tự đọc private text hoặc khôi phục DB.

Sau khi blocker được duyệt, chỉ chạy KH nguyên văn một lần, kiểm đủ COUNT/SQL/
oracle/retrieval/KPI/citations/history/integrity rồi mới GH. Không cross-domain
holdout, thêm probe, retry hoặc sửa/deploy trong nhiệm vụ acceptance này.

**Kết luận cuối lượt: BLOCKED — NO LIVE PROBES.**

## I. Live resume sau xác nhận của chủ dự án

### I1. Approval, source và fresh baseline

Chủ dự án xác nhận đã chat thêm sau historical snapshot và yêu cầu tiếp tục test,
có cho mở rộng ngân sách. Đã thông báo chỉ dùng trần có sẵn2 chats/8 generations/
2 query embeddings trước, không tự dùng thêm probes hoặc retry. Approval này
cho phép rebaseline drift lịch sử, không bỏ history tables/security assertions.

Giữ ledger cũ/cases rỗng và evidence blocked; thêm approval record + subfolder
`live-resume-1` riêng. Không overwrite snapshots trước đó. Fresh26 baseline lấy
lại và so đúng bảng/clauses/hash method; chỉ historical differences ở2 history
tables đã được user giải thích. 24 bảng khác vẫn khớp historical.

Fresh before=after aggregate:
`c4ffe3daf04d2c1a20eb502b6613478526c7ceb4db401f39fe0b898da05afd6a`.
26/26 count/hash bằng nhau trong cửa sổ live, không exclusion mới. Synthetic50/
15/5, exact2 edges/revisions/statistics, policy12/chunk22/content/vector cũng
không đổi. Runtime vẫn manifest72 ở mụcB, cùng IDs/images/config và healthy.

### I2. KH actual live result

Google session thật và workspace13 đã kiểm qua UI; New Chat, Knowledge selection.
Gửi đúng câu hỏi nguyên văn ở attachment, một lần qua nút Gửi câu hỏi; không
oracle injection, API chat trực tiếp, mock session hoặc provider retry thủ công.

- Conversation synthetic mới: `740f1b45-b983-46b4-b230-556443bea118`.
- Correlation: `651608bcdea6468d9d2e6756ebbc193b`.
- Server duration:19113.856ms.
- Requested=used=`inetcloud-knowledge`; fallback=false; error=null.
- Router HYBRID, final route HYBRID;3 allowed tables/2 approved edges.
- Parse/columns/graph/revalidation/execution_guard/sql_execution đều success.
- SQL5 warehouse rows, exact ID/name/Decimal SUM/COUNT bằng independent oracle.
- Selected count alias **so_dong_don**, semantic **ROW_COUNT**, argument COUNT(*),
  nonnull proof star_rows, scope matched_fact_rows. Không bị reject chỉ vì alias
  nghiệp vụ khác canonical. SUM alias tong_phi_giao_vnd.
- Accepted final SQL SHA-256:
  `4db4f0c057106d15da4f8c3a09befc70454480d4dd95415677cc8b550fa046e3`.
- Không WHERE/HAVING/date/status filter hoặc bỏ required table. GROUP identity
  đúng kho_id; không policy threshold được đẩy vào SQL trước retrieval.

Private verifier replay accepted final SQL bằng current validator/context authorized,
typed count provenance và execution guard, executor dùng reader READ ONLY; rows
khớp cả persisted response lẫn oracle. Replay này **không phải raw draft capture**,
không thêm generation/embedding và không phải normalization live evidence.

Diagnostics không có aggregate_normalization event; không khẳng định live đã
rewrite ORDER/alias. Last aggregate facts là SUM do analyzer tiếp tục duyệt;
không dùng final count_argument_shape=not_applicable để phủ nhận COUNT đã có.
CountKind được chứng minh bằng accepted SQL + exact current analyzer replay,
không phải typed metrics đã được production logger xuất trực tiếp.

Scoped document_retrieval thực sự success sau SQL execution, sau đó Hybrid
answer_grounding success. Actual cited source chunk22 của live_gate_d_kpi.md,
content/section khớp persisted policy. Vì workspace có đúng1 eligible chunk và
source phải thuộc retrieved chunks theo runtime validation, có bằng chứng chunk22
đã được retrieve và dùng. Không có trace toàn bộ retrieval candidate list; không
khẳng định thêm IDs không được quan sát. Policy threshold/content support PASS.

### I3. Failure có bằng chứng — final synthesis tự mâu thuẫn

Câu trả lời đã persist mở đầu:

> Các kho đạt KPI tổng phí (tổng phi_giao_vnd >= 500000.00 VND) là KHO03 và KHO05.

Nhưng chi tiết cùng câu trả lời ghi:

> KHO02 (Kho Hải Phòng): Tổng phí 598000.00 VND, 10 dòng đơn. Kết luận: Đạt.

Oracle/document xác nhận KHO02 **phải đạt**, cùng KHO03/KHO05. Các5 chi tiết
đều đúng số tiền/count/kết luận, nhưng summary bỏ1 kho đạt nên answer tổng thể
không nhất quán. Không bỏ qua summary chỉ vì SQL rows hoặc đoạn chi tiết đúng.

**KH FAIL ở manual semantic review của Hybrid final answer.** Không phải COUNT
validator false refusal, wrong JOIN/owner/revision, PostgreSQL execution failure,
provider503 hoặc missing document. Safe stages success chỉ chứng minh application
steps hoàn tất; không bảo đảm narrative đúng. Không thể kết luận cơ chế nội bộ
model gây omission từ một response này.

### I4. Browser/history và stop condition

Sau khi gửi KH, người dùng nhắn “tiếp tục làm”; khi đọc kết quả, công cụ browser
báo Local browser use is disabled in Work settings. Không retry submit, không
dùng backend API thay UI hoặc đọc cookie/token. Response/diagnostics thu bằng
read-only authorized synthetic conversation evidence.

DB history đã kiểm lại đúng2 messages, content/response/model/evidence giữ nguyên.
**UI result/evidence inspection và reload history mới NOT RUN do browser bị tắt.**
Không dùng persistence check để tuyên bố UI reload PASS; không có screenshot mới.
Không cần thêm live call để khẳng định failure summary vì persisted final answer
đã đủ evidence. **GH NOT RUN** theo failure stop condition, không probe thứ3 hoặc
phần ngân sách mở rộng. Không gọi lại KH để tìm response tốt hơn.

### I5. Results, budget và integrity

| Case | Semantic COUNT | SQL/oracle | Retrieval/citation content | Final KPI answer | DB persistence | UI reload | Verdict |
|---|---|---|---|---|---|---|---|
| KH Knowledge | PASS, business alias ROW_COUNT | PASS5 rows | PASSchunk22 | FAILsummary omits KHO02 | Exact PASS | NOT RUNbrowser disabled | FAIL |
| GH Gemini | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUNstop after KH |

Budget thực tế: **1 chat /4 logical generation stages /1 query embedding /
0 document embeddings**. Stage order router→draft→SQLgrounding→retrieval→Hybrid
synthesis đã đối chiếu diagnostics/source. Không instrument HTTP attempts/billing;
SDK/structured retries có thể cao hơn logical calls. Không dùng extra budget.

Postflight26 protected tables khớp fresh before; synthetic source/relationships/
policy/vector không đổi. Scoped message watermark ghi đúng **1 new conversation,
1 user +1 assistant,0 errors**, owner binding đúng; không xóa chúng để khớp hashes.
Auth/operational quota lifecycle ngoài protected immutable scope giữ quy tắc cũ.
API/web/DB IDs/images/StartedAt/settings/source hashes không đổi, health8001/8080OK.
Không migration/restore/seed/upload/re-ingest, sửa source/tests/.env/gates/model/
retry/quota/OAuth, Docker restart/cleanup, commit hoặc push.

Private evidence tại subfolder live-resume-1: fresh before/after snapshots,
KH-response.json, KH-diagnostics.json, KH-verification.json,
KH-history-verified.json và new-messages-summary.json; parent ledger giữ approval/
budget/caseFAIL. Không raw rejected draft, cookies/tokens hoặc customer text.
Repository chỉ sửa báo cáo này; không chạy lại full regression vì không source change.

### I6. Bước offline tiếp theo — chưa thực hiện

Tái hiện đúng response summary/detail mâu thuẫn bằng fake final Hybrid draft,
SQL rows và persisted synthetic policy. Đánh giá hợp đồng kết luận structured
theo entity IDs và kiểm tính nhất quán narrative/evidence, với minimal regression
không thêm provider calls/agent/repair loop. Không dùng keyword replacement hoặc
tự vá một kho trong text; cần design/review phạm vi phù hợp trước implementation.

Việc COUNT business alias đã live PASS không chứng minh mọi COUNT variant; Hybrid
full acceptance vẫn FAIL và Gemini chưa được kiểm trên lượt này. Historical raw
KH root cause vẫn UNKNOWN. Không khẳng định “mọi lỗi COUNT đã hết” từ1 probe.

**Kết luận mới nhất: HYBRID LIVE FAILED — KH FAIL / GH NOT RUN.**
