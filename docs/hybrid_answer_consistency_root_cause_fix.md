# Hybrid answer consistency — structured evidence root-cause fix

> Báo cáo lịch sử của patch consistency ngày21/10. Khả năng natural-policy và trạng
> thái triển khai/Git mới hơn nằm trong [final delivery](hybrid_natural_policy_final_delivery.md).
> Không sửa lại kết quả live KH FAIL/GH NOT RUN của lượt trước.

Ngày 21/10/2026, local workspace `C:\Work\ShopQuery AI`.

**PATCHED OFFLINE — NOT DEPLOYED. LIVE HYBRID NOT VERIFIED.**

Không gọi Knowledge/Gemini/embedding, không gửi lại KH/GH, không thay runtime
8080, main database, `.env`, provider gates/model/quota/retry hoặc OAuth.
Không commit/push. Báo cáo live cũ và lịch sử KH thất bại được giữ nguyên.

## 1. Lỗi quan sát thật và giới hạn kết luận

Theo mục I của `text_to_sql_semantic_count_hybrid_live_final_acceptance.md`:

- KH Knowledge HYBRID, requested=used Knowledge, không fallback, không API error.
- SQL/COUNT/JOIN ba bảng đúng, 5 SQL rows khớp PostgreSQL oracle.
- Citation chunk22 của `live_gate_d_kpi.md` hỗ trợ tổng phí >=500000.00,
  mọi trạng thái. Retrieval/citation đúng không chứng minh narrative đúng.
- Summary chỉ liệt kê KHO03/KHO05; chi tiết lại ghi KHO02 đạt với 598000.00.
- Oracle: KHO02/KHO03/KHO05 đạt. **KH FAIL, GH NOT RUN**.
- Lượt live cũ dùng 1 chat/4 logical generations/1 query embedding. Không dùng
  thêm ngân sách trong tác vụ hiện tại.

Không biết cơ chế nội bộ model gây omission. Nguyên nhân ứng dụng đã chứng minh:
`HybridAnswerDraft` trước đây chỉ có `answer` và `used_chunk_ids`; pipeline chỉ
kiểm citation membership rồi trả nguyên `draft.answer`. Không có authoritative
entity decision set, coverage check, metric/policy binding hoặc consistency gate.
SQL pipeline đã đúng nên không sửa SQL validator, JOIN policy hay COUNT contract.

Phân biệt sáu mức bằng chứng:

| Mức | Điều đã/chưa chứng minh |
| --- | --- |
| SQL correctness | Rows từ SQL đã validated/execution-guarded, đối chiếu oracle |
| Document correctness | Nội dung nguồn hỗ trợ rule đang xét; retrieval không tự chứng minh rule |
| Citation membership | IDs có trong retrieved chunks; không đồng nghĩa kết luận đúng |
| Per-entity classification | Phải có identity coverage và proof metric/rule cụ thể |
| Summary/detail consistency | Hai phần được dựng từ cùng status vector, không hai narrative |
| Natural-language correctness | Không được suy ra chỉ từ JSON hợp lệ hoặc fake model tests |

## 2. Fail-before / pass-after

`test_observed_kh_freeform_contradiction_is_not_a_successful_answer` dùng 5 synthetic
rows đúng các tổng tiền/count, policy prose và chunk22; fake response giữ chính
kiểu mâu thuẫn summary bỏ KHO02/detail xác nhận KHO02. SQL/RAG fake stages đã
hoàn thành trước final synthesis; không provider calls.

Trước bản sửa: regression **FAIL — DID NOT RAISE ModelResponseError**; implementation
cũ chấp nhận response. Sau sửa: PASS, free-form draft không còn hợp đồng hợp lệ.
Không đổi oracle để khớp answer. Fixture tái hiện dùng aliases nội bộ của test,
không phải tuyên bố đã capture raw live SqlDraft.

Positive companion test dùng cùng 5 tổng tiền, nhưng **policy block synthetic
tường minh riêng**, rồi kiểm `Qualified: KHO02, KHO03, KHO05.` và từng dòng detail.
Không thay tài liệu/main chunk22 để tạo kết quả này. Replay policy prose gốc phải
UNVERIFIED; không gọi đó là POLICY SEMANTICS VERIFIED.

## 3. Internal contract và single source of truth

`HybridAnswerDraft` mới là strict Pydantic DTO, tất cả fields bắt buộc, extra fields
bị chặn, model instances được revalidate kể cả nested decisions/notes:

- `mode`: classification hoặc explanation; `language`: vi/en.
- `identity_fields`: selected stable-ID output fields; `metric_field`, `rule_id`.
- `decisions`: entity_values, status, supporting_chunk_ids.
- `notes`: chunk_id và exact quote từ chunk thật; `used_chunk_ids`.
- Status: qualified, not_qualified, insufficient_evidence, unverified.

Không có `answer`, `summary`, copied metric values hoặc qualified-ID list thứ hai
do model viết. Numeric values luôn lấy từ SQL rows, không từ bản chép của model.

Flow: validated SQL rows → exact entity coverage → evidence/policy checks → một
ordered status vector → deterministic summary + deterministic detail table.
Decision order có thể khác SQL order; binding theo ID chứ không theo vị trí/tên.
SQL intermediate answer không được dùng làm final evidence/narrative.

### Identity binding

Đọc AST của SQL **đã được SQL pipeline chấp nhận**, bind output aliases về selected
columns. Chỉ hỗ trợ source column `id`, `code`, `*_id`, `*_code`; không đoán display
name là khóa. Aggregate phải GROUP BY selected ID column hoặc alias tương đương.
IDs phải là string/integer không NULL/bool/float, unique trong returned evidence.
Coverage phải exact: không thiếu/thừa/trùng/contradictory entity.

Đây là capability giới hạn: kiểm returned-set uniqueness và explicit identifier
binding, không phải registry chứng minh primary key/ngữ nghĩa identity của mọi
dataset. Naming convention khác, ID bị cast/computed hoặc grouping ordinal chưa
được hỗ trợ sẽ fail closed. Composite identity có thể dùng UNVERIFIED; numeric
policy verifier hiện chỉ hỗ trợ một identity field.

### Explanation không buộc decision matrix

Question không cần phân loại có thể dùng explanation: SQL table + exact document
excerpts, có nhãn rõ “không phải phân loại đã xác minh”. Không free-form synthesis,
không quyết định entity tự do, không tự phát sinh list đối nghịch.

Public API/HybridResult shape vẫn giữ answer/sql/rows/sources/model attribution.
**Nội dung answer có thay đổi có chủ ý**: explanation ưu tiên bảng và trích dẫn,
không còn đoạn giải thích tự do do model viết. Mode selection và vi/en selection
vẫn do model đề xuất; backend không chứng minh NL intent/language detection.
Explanation không được coi là đã hoàn tất yêu cầu classification. Ngoài vi/en
chưa có rendering contract. Đây là giới hạn cần review trước deployment/live.

## 4. Policy proof: phạm vi hỗ trợ cụ thể

Không thêm regex interpreter suy diễn policy tự nhiên. NumericPolicy chỉ chạy khi
retrieved document có nguyên block JSON được phân định rõ:

````text
```shopquery-rule-v1
{"version":1,"rule_id":"synthetic-policy","entity_column":"student_id","metric_column":"amount_paid","aggregate":"sum","operator":"gte","threshold":"30.00","unit":"source","scope":"all_rows"}
```
````

Đây là format khả năng tính toán mới trong nội dung tài liệu, **không phải rule
trích tự động từ prose, migration, semantic catalog hay evidence chứng minh policy
tự nhiên tương đương**. Không tự upload/chuyển đổi tài liệu người dùng.

Supported proof:

- Block strict, duplicate JSON keys/rule IDs bị chặn; rule phải thực sự retrieved,
  uniquely bound và được cite bởi mỗi decision. Multiple executable rules chưa
  có composition proof nên classification verified bị từ chối.
- Entity source column và metric source column phải khớp selected AST bindings.
- SUM/AVG direct source column; không arithmetic/casts/DISTINCT expressions.
- ROW_COUNT/NON_NULL_VALUE_COUNT dùng typed backend CountMetric, không suy từ alias;
  row rule cần `metric_column="*"`; value rule cần đúng source column.
- Operators gte/gt/lte/lt/eq; threshold là decimal string, comparison dùng Decimal,
  không float conversion, rounding, arithmetic context hoặc copied model numbers.
- `unit=source`: chỉ so cùng đơn vị raw source field, **không chứng minh/chuyển đổi
  VND/USD, giờ/phút, gross/net hoặc thực thể nghiệp vụ chỉ từ một tên cột**.
- `scope=all_rows`: evidence trên matched fact rows của validated SQL, không tự mở
  rộng sang unmatched entities. WHERE/HAVING/LIMIT bị chặn ở verified mode vì chưa
  có proof scope/filter/top-N. SQL-only semantics không thay đổi.
- NULL → insufficient_evidence; zero là số thật; exactly-on-boundary đúng theo
  operator. Wrong proposed status bị từ chối, không âm thầm sửa verdict.

Natural-language/complex/missing executable policy: chỉ UNVERIFIED (hoặc
insufficient_evidence cho NULL), không qualified/not_qualified. Source quote có
thật chỉ chứng minh quote membership, không tự chứng minh business inference.

**Policy prose hiện có của KH vẫn POLICY SEMANTICS NOT SUPPORTED cho deterministic
qualification.** Có thể trả evidence UNVERIFIED thành công thay vì bịa verdict;
không được coi đây là đã sửa mọi Hybrid business question. Format/source-unit/
scope hạn chế trên là trade-off an toàn, không phải natural-policy reasoning engine.
Verifier cũng **không chứng minh toàn bộ prose xung quanh block không có ngoại lệ
hoặc mâu thuẫn**. Proof chỉ có hiệu lực cho block tường minh được coi là rule
authoritative theo contract; cần review quyền tác giả/binding policy trước khi
dùng nghiệp vụ thật. Không dùng một block tự thêm để hợp thức hóa prose mơ hồ.

## 5. Security / fail closed / compatibility

- Missing/extra/duplicate entity, fabricated IDs/quotes/chunks, unrelated cited
  chunks, duplicate refs, wrong rule/metric/count kind/status đều bị chặn.
- Tập used citations phải đúng tập evidence thực sự referenced; giữ Source objects
  từ retrieved chunks, không model-generated file names hoặc source content.
- Markdown cell values được escape HTML/table/newline/link markup; quotes đánh
  dấu evidence không phải instructions hoặc kết luận đã verified.
- Validation error dùng ModelResponseError hữu hạn; public API giữ error mapping
  hiện có, không lộ raw SQL/policy/internal reason ra thông báo lỗi.
- Consistency error không phải ProviderError: không retry/fallback model để sửa.
  Không thêm generation stage, retry loop hay LLM repair call. SDK/Knowledge
  structured-schema retry vốn có giữ nguyên; không tuyên bố một logical call
  luôn bằng một HTTP request.
- SQL-only/RAG-only không sửa. SELECT-only, graph/key/grain guard, readonly executor,
  max-row overflow error, owner scoping, Guest isolation và CSRF giữ nguyên.
- Public response shape và persistence serialization không thay đổi, không migration.
  Lịch sử cũ vẫn nguyên văn; không rewrite KH FAIL thành thành công.
- Knowledge/Gemini DTO serializers đã kiểm bằng actual adapters + mocked HTTP;
  chưa chứng minh provider thật luôn sinh schema đúng.
- Không raw prompts, customer records, cookies, OAuth credentials hoặc provider
  secrets vào report/log. Test chỉ dùng synthetic inputs và ephemeral identities.

## 6. Files thay đổi

Production: `backend/app/routing/hybrid.py` gọi structured validation/composition;
`hybrid_evidence.py` identity/coverage/citation/AST binding + rendering;
`hybrid_policy.py` strict explicit numeric rule/Decimal comparison.

Tests mới: `test_hybrid_answer_consistency.py`, `test_hybrid_evidence_adapters.py`,
`test_hybrid_evidence_integration.py`, shared synthetic `hybrid_fixtures.py`.
Tests Hybrid fake drafts cũ được migrate sang schema mới trong routing/workspace,
guest/domain/relationship/three-table/gate-D suites; SQL rows/oracles/security
assertions không bị bỏ. Gate-D prose replay giữ natural fixture và kiểm UNVERIFIED,
không giả vờ prose đã verified. Numeric-proof fixtures mới có block explicit riêng.
`frontend/src/components/ChatMessage.test.tsx` thêm table/Decimal/NULL/restore rendering.
Không production frontend edits, dependency/framework/model/architecture changes.

## 7. Cross-domain và regression evidence

New PostgreSQL matrix: 6 domains × 3 table counts × 2 fake model IDs = **36 scenarios**,
một parameterized test definition. Logistics fees >=500000.00; tuition payments
>=30.00; staffing hours >=12.50; sales revenue >=40.00; energy consumption >=12.50;
maintenance downtime >=0.00 (synthetic threshold exercise, không diễn giải là KPI
an toàn vận hành). Oracle từ independent PostgreSQL VALUES + direct Decimal
comparison trên nguồn fixture, không gọi production verifier để tạo expected.

Fixtures đổi tên physical tables/column order, duplicate display names, stable IDs,
nullable/all-NULL groups, zero và equal values. Decisions đảo thứ tự vẫn đúng.
Unit metamorphisms đảo SQL rows, đổi display names/physical names/presentation
aliases, thêm unrelated/instruction-bearing chunk, đổi threshold; coverage/status
summary/detail được kiểm đồng thời. Unit boundaries có negative thresholds,
exact BIGINT-scale Decimal equality và float/nonfinite rejection.

API/history mới: 2 model IDs × valid/contradictory = 4 scenarios. Valid trả đúng
5 rows/3 qualifying IDs/citation; contradictory không persist fake success,
không rows/sql/sources. History reload qua API giữ exact response, owner B 404,
không thêm gateway calls. Guest/session/CSRF/isolation vẫn kiểm bởi full regression.

### Test execution

Kết quả chốt source (không cộng các lượt chạy lại vào tổng số tests):

| Suite | Kết quả | Phân biệt definitions/scenarios |
| --- | --- | --- |
| Backend unit, not integration/not live | **847 PASS**, 20.00s | 239 distinct function definitions; 847 collected parameterized cases |
| Contract tests mới (nằm trong unit ở trên) | **77 PASS** | 19 definitions; 73 consistency/policy cases + 4 provider-adapter cases |
| PostgreSQL full, isolated, not live | **722 PASS**, 256.43s | 107 distinct definitions; 722 parameterized cases; thêm 36 cross-domain và 4 API/history cases |
| Frontend Vitest | **68 PASS**, 9 files | Thêm 1 rendering/restore case so baseline67 |
| UI mock Playwright | **105 PASS**, 3.2 phút | 20 test declarations; relationship guest/auth mở rộng thành 21 cases/profile × 5 viewports |
| Ruff app/tests | **PASS** | Không bỏ security assertions/ignore mới để né lỗi production |
| FE ESLint / TypeScript / Vite build | **PASS / PASS / PASS** | Build artifacts local, không deploy web |
| git diff --check | **PASS** | Chỉ warning CRLF checkout convention, không whitespace errors |
| Provider/embedding live; UI8080 patched | **NOT RUN** | Không có quyền trong tác vụ này |

Chạy unit: `python -m pytest tests -m "not integration and not live" -q`;
PG: `python -m pytest tests -m "integration and not live" -q` với process env
trỏ duy nhất disposable test DB và RUN_DATABASE_TESTS=1.
UI mock: npm run test:e2e với Vite riêng `127.0.0.1:15173`, không Google storage
state, không gửi câu hỏi tới main8080. Source/runtime regression không phải live AI.
Các lượt có harness interference không được tính PASS: hai runner ban đầu dùng
chung disposable DB gây deadlock/fingerprint drift; đã dừng overlap và chạy lại
tuần tự. Không sửa production schema/security để làm xanh lỗi test orchestration.
Một fixture DOCX ban đầu đặt rule fence trong cell bị parser flatten newline;
đã đặt explicit rule trong paragraph riêng và giữ table-prose coverage nguyên.
Full PG đầu tiên 720 PASS/2 FAIL vì mock trong auth suite vẫn tạo free-form DTO;
đã cập nhật mock, giữ owner/exact-row/citation assertions. Targeted auth+gate-D
63 PASS trước lượt full cuối trên database mới. Không gọi đó là provider/schema
failure của model thật.

DB test duy nhất được tạo bởi tác vụ: `shopquery-ai-hybrid-consistency-test`,
ID `679f09e1ec81dff88c82452689a8583e7e1cd22fdf2f5c928a747a0e1c9e2ee4`,
label `shopquery.test=hybrid-consistency-20261021`, loopback port15442,
pgvector0.8.1/PG17. Data directory dùng tmpfs, **không named/bind mounts**.
DB names `shopquery_test_hybrid_consistency`, `_full` và `_final`; test safety guard được
giữ, setup/reader accounts riêng. Process test env blank generation credentials,
fallback/provider gates OFF, fake embedder. Không dùng main DB URL/volume.
Private JUnit evidence: `C:\Work\ShopQuery-Backups\hybrid-consistency-unit.xml`
và `shopquery_test_hybrid_consistency_final.xml`; full-run fail evidence `_full.xml`
được giữ riêng; không đưa evidence artifacts vào Git.

Full backend tổng **1569 scenarios** (847 unit + 722 PostgreSQL), **346 distinct
definitions** (239 +107), không đếm lại targeted/re-runs. So baseline770/682,
tăng77 unit và40 PostgreSQL scenarios. 16 provider-live tests được deselect, không
coi là PASS hoặc lỗi; không có một live request nào trong các số trên.

Sau full PASS, đã inspect lại exact container ID/name/label/port/tmpfs/no mounts,
xác nhận runner kết thúc, rồi stop/remove **duy nhất container test vừa tạo**.
Tmpfs/test databases synthetic bị hủy cùng container, không có dữ liệu cần khôi
phục; JUnit evidence ở ngoài repository được giữ. Không xóa image/named volume,
không global prune, không thao tác container thuộc project khác. API/web/DB chính
vẫn cùng IDs và healthy sau cleanup.

## 8. Source/runtime/Git và bước tiếp theo

HEAD vẫn `d9bcce165d6af2124866770c2879a74cbb3a207c`, changes chưa commit/push;
không CI SHA mới. Báo cáo live untracked đã có trước tác vụ được giữ nguyên.
Source mới khác runtime có chủ ý; 8080 **chưa có bản sửa này**.

Main containers được kiểm read-only vẫn running/healthy, IDs không đổi:

- API `8a39b1cb69a0…`, image `sha256:4bbf907c554099a7d542a53b10b5850b6bfc56d7ba1e9ebb499c696cc2c0151b`.
- Web `2af67d527f2e…`, image `sha256:5ca6e17125f12574cf8cdf4d030b6a0a209007e9469b264e94e6d98056090146`.
- DB `511c4f5aaccc…`, main volume không thao tác.
- Runtime hybrid.py SHA256 `4e8a74ba599f86a2539c79c7e8710f7e76fa8a784a7fc8fabda0a063f6adfcb8`;
  vẫn implementation cũ, 72 Python modules trong image. Local hybrid.py LF-normalized
  SHA256 `22cecaf71f680333915428c332ce116397fb2168494ff1f52982161fd4627a29`,
  thêm hai production modules, không thay runtime source.
- Main volume vẫn `shopquery-ai_postgres_auth_20261019`; bootstrap bind mount read-only.
  Không migration, recreate, restore, seed main. Không đọc/rebaseline fingerprints
  dữ liệu main trong tác vụ offline; không suy health=protected data proof mới.

Deployment đề xuất, **chưa được thực hiện**: review capability/answer-format changes
và policy proof limitations; approve exact diff/SHA; record runtime settings/image/
DB/volume identity và rollback image; build/recreate API-only đúng compose overrides,
không DB/web recreate, không migrations hoặc provider config changes. Health/module
hash/owner/Guest/CSRF offline smoke; rollback API image nếu không đạt. Vì không DB
migration nên rollback source không phải restore data. Không tự rollback đè main.

Sau deployment cần phê duyệt riêng live regression: tối đa **2 chats, 8 logical
generations, 2 query embeddings, 0 document embeddings** nếu policy còn hợp lệ.
KH trước; chỉ KH fully PASS mới GH, không manual retries. SDK/adapter retries có
thể làm HTTP requests cao hơn. Independent oracle + citations + exact entity set +
summary/detail + history UI reload + protected before/after fingerprints.

**Không lén thay prose hiện có bằng numeric rule để tuyên bố live PASS.** Nếu mục
tiêu là verified KPI trên prose cũ, phải có bước review/binding semantics được duyệt
riêng; ngân sách trên không tự cấp quyền ingest/re-embed policy mới. Natural prose
UNVERIFIED hoặc explanation-only không đủ điều kiện verified KPI acceptance.
Nếu browser tắt thì UI acceptance vẫn NOT RUN; API persistence không thay thế UI.

## 9. Kết luận theo phạm vi proof

- **CONSISTENCY VERIFIED OFFLINE**: một decision set, coverage/citation gate,
  deterministic summary/detail, không narrative độc lập ghi đè.
- **POLICY SEMANTICS VERIFIED OFFLINE**: chỉ explicit, source-unit, all-rows numeric
  policy format và supported AST/count bindings nêu trên; fake provider + PostgreSQL.
- **POLICY SEMANTICS NOT SUPPORTED**: prose KPI gốc, complex/multiple policies,
  conversions, filtered/top-N scope hoặc identity/aggregate ngoài contract.
- **PATCHED OFFLINE — NOT DEPLOYED**.
- **LIVE HYBRID NOT VERIFIED**. Historical KH FAIL/GH NOT RUN không bị thay kết luận.

Nguồn kỹ thuật: [Pydantic strict validation](https://docs.pydantic.dev/latest/concepts/strict_mode/),
[Python Decimal](https://docs.python.org/3.11/library/decimal.html),
[Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output).
Schema hợp lệ không đảm bảo business semantics; backend phải kiểm proof riêng.
