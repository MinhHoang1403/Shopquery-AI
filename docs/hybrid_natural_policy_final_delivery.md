# Hybrid numeric prose policy — final delivery

Ngày 22/10/2026, Asia/Ho_Chi_Minh. Workspace `C:\Work\ShopQuery AI`.

**Checkpoint: DEPLOYED TO 8080 — GIT DELIVERY IN PROGRESS — LIVE PROVIDER NOT VERIFIED.**
Không live Knowledge/Gemini/embedding. Các kết quả live lịch sử KH FAIL/GH NOT RUN
không được đổi thành PASS bởi các fake-provider tests dưới đây.

## A. Root cause và thiết kế

Runtime cũ trả free-form Hybrid answer sau citation membership check; vì vậy summary
có thể bỏ KHO02 dù detail ghi đúng. Bản consistency ngày21/10 thay bằng strict
structured decisions và một status vector dựng cả summary/detail, nhưng chỉ chạy
policy numeric explicit JSON. Prose gốc không có parser/provenance/binding proof.

Bản mới giữ single-source rendering, thêm closed bilingual grammar **deterministic
trước final Hybrid generation**. Không cần model đề xuất/thông dịch rule rồi tin nó.
LLM vẫn chọn rule/output references và đề xuất entity statuses; backend kiểm lại
chúng với source, AST, metadata, count provenance và Decimal. Không repair/call mới.

Các trách nhiệm:

- `natural_policy.py`: `ProseRule` typed candidate, grammar/locale, toàn bộ câu phải
  được consume. Unknown sentence/qualifier → unsupported, không bỏ qua rồi extract
  riêng câu có lợi. Không domain/entity/column/threshold constants trong product.
- `hybrid_policy.py`: `NumericPolicy` và candidate IDs; giữ shopquery-rule-v1;
  parse thành candidate **không phải** VERIFIED conclusion.
- `hybrid_policy_binding.py`: source completeness/version/span/hash, registry và
  approved-key/root/aggregate/units/scope binding; không dùng alias làm proof.
- `hybrid_evidence.py`: exact entity coverage/status/citation checks, deterministic
  summary/detail. `hybrid.py`: reuse existing synthesis call; short redacted errors.
- `datasets/context.py`: thêm typed source headers/table labels/categorical values
  đã có trong registry/context; không đổi SQL permissions/generator/COUNT contract.
- `rag/repository.py`: read-only provenance cho actual retrieved chunks (document
  hash, expected chunk IDs, owner/dataset, text hashes); không fetch extra text.
  Guest RAM có equivalent request-local provenance, không persistent private corpus.

Không framework/dependencies/agent/schema migration, không production frontend edits.
Giữ API answer/sql/rows/sources và attribution/history shape. Explanation vẫn trả
SQL evidence + exact marked quotes, không giả đó là verified classification.

## B. Supported grammar / proof boundary

Đây là **closed grammar**, không engine hiểu mọi câu tự nhiên. Keyword/spelling,
clause order và explicit references phải thuộc subset dưới đây; unsupported không
được gọi là bug cần nới guard. Parser không lấy substring phù hợp rồi bỏ phần còn lại.

Canonical English example (không cần JSON):

> Each course qualifies when sum of amount_paid is at least 30.00 source units.
> Include all rows. Identify each course by course_id.

Vietnamese example:

> Mỗi department đạt nếu tổng hours >= 12.50 source. Tính tất cả dòng.
> Phân biệt từng department theo mã department_id.

Subject/field/key là placeholders từ dataset hiện hành, không template theo domain.
References phải khớp physical source columns **hoặc source headers** theo normalized
Unicode/case/separator equality, không fuzzy similarity. Alias trả về chỉ bind qua AST.
Normalized ambiguity và multiple equivalent output candidates chưa được tự chọn.

| Thành phần | Supported | Unsupported / needs clarification |
| --- | --- | --- |
| Aggregate | tổng/sum of/total, trung bình/average, số dòng/row count, non-NULL count | DISTINCT/FILTER/compound expression/dimension measure |
| Operator | >=, >, <=, <, =; ít nhất/tối thiểu/từ…trở lên/lớn hơn/nhỏ hơn/không vượt quá/tối đa/bằng; at least/no less than/greater than/more than/at most/no more than/not exceeding/less than/equals/equal to | Implicit “đạt ngưỡng” không rõ operator, double negation, compound boolean |
| Number | Exact signed Decimal, zero/boundary; explicit en-US/vi-VN sentence cho thousands/decimal separators | Comma hoặc dạng 1.000 mơ hồ thiếu locale; float/NaN/Infinity |
| Unit | source/source units = raw field units; explicit unit token phải có trong actual source header/column tokens; count units rows/values đúng kind | Currency/scale/time conversion, unit chỉ xuất hiện trong output alias, unknown unit |
| Scope | Explicit all rows / mọi trạng thái; no SQL WHERE/HAVING/LIMIT | Date/category/status filter, top-N, missing/unmatched entities outside INNER result |
| Identity | Selected ID/code convention + unique/non-NULL returned tuples; verified relationship target key dù không có suffix ID | Display-name guess, computed/cast IDs, unproved composite/global uniqueness |
| Authority | Whole single-chunk retrieved document, registered expected IDs/hash/owner/dataset đúng | Multi-chunk/partial document, unknown authority, hidden cross-document exceptions |
| Exceptions | Unknown/restrictive clause làm từ chối proof; full body consumed | Không giải compound/override/exception precedence |

Conservative auxiliary grammar hỗ trợ record-relative clause, explicit all-status
sentence, approved `qua … và liên kết …` path, identity sentence, SUM ignores NULL/
zero-valid sentence và final classification instruction. Những free references
trong chúng phải bind lại metadata, không được chứa restriction chưa kiểm chứng:

- Record label khớp fact label đã bỏ numeric prefix; short record noun phải thuộc
  vocabulary của label đó. Status example phải là exact observed categorical value.
- “Qua…” phải khớp intermediate label và actual approved fact→intermediate→entity
  path, không chỉ có tên bảng trong prompt.
- Criterion/final metric label và neutral section heading phải thuộc source/subject
  vocabulary + finite grammar words. Unknown qualifier/heading không được verified.
- Supported numeric document tối đa12000 characters, references bounded100 chars;
  numeric candidate field refs bounded63 trong typed contract.

DocumentScope là backend-derived, không model-supplied. Prose proof chỉ cho extracted
text của document snapshot; không chứng minh tính xác thực dữ liệu, OCR/Word content
đã ingest thiếu từ trước, global precedence của mọi tài liệu hoặc mọi NL intent.

JSON rule vẫn dùng được, nhưng không override prose: nếu phần ngoài block không
parse/bind được đầy đủ hoặc khác operator/threshold/metric/entity, không verified.
Multiple rules/candidates chưa có composition proof → fail closed. Không thêm
block, re-ingest hoặc sửa tài liệu main để tạo PASS.

## C. Exact original KH prose acceptance

Đã copy **nguyên bytes synthetic file đã lưu** sang
`backend/tests/fixtures/gate_d_original_kpi.md`. SHA-256 cả hai:
`eecd50cc75196867364b3cd312cd6712b0d9933e359445f57f7c313926f419aa`.
Không sửa threshold/data/oracle/document trên main. Source body chunk hash lịch sử:
`15f159e4bd6ad052a668315cc1813f3b1fbfbe0775d07aafd02636cd0d4b5bf6`.

Exact comparison span (nằm trong whole-chunk quote, không cắt mất auxiliary clauses):

> Trong bộ dữ liệu giả lập này, một kho đạt KPI tổng phí khi tổng phi_giao_vnd
> của các đơn thuộc kho đó từ 500000.00 VND trở lên.

Whole evidence còn chứa all-status, fact→driver→warehouse identity, SUM NULL/zero và
final classification clauses. Candidate giữ exact whole quote/span0..len,
document hash và text hash; parser/binder consume/verify cả các câu đó.

Typed rule: SUM(source phi_giao_vnd), entity source kho_id, operator gte,
threshold Decimal500000.00, declared VND khớp source token vnd, all rows/no filters,
ID grouping và approved chain từ metadata. Rule ID derived từ chunk text hash,
không tên file/KHO02/threshold hardcode trong production.

| ID | SQL SUM | COUNT rows | Independent verdict |
| --- | ---: | ---: | --- |
| KHO01 | 393500.00 | 10 | Not qualified |
| KHO02 | 598000.00 | 10 | Qualified |
| KHO03 | 502000.00 | 10 | Qualified |
| KHO04 | 439000.00 | 10 | Not qualified |
| KHO05 | 540000.00 | 10 | Qualified |

`test_original_prose_integration.py`: 4 supported-positive cases (2 fake provider IDs
× standard/business COUNT alias), 16 unsafe-negative cases (4 mutations × same
matrix). Real validator, execution guard, PostgreSQL reader execution, persisted
original prose/fake embeddings/actual scoped retrieval, backend binding, summary/
details/citations và authenticated API history roundtrip; owner B404, no extra calls.
Positive summary: **Qualified: KHO02, KHO03, KHO05.** Mỗi detail giữ exact SQL values.
Negative exception/unit mismatch/invented rule/ambiguous metric không persist success.

Fail-before: original prose parser regression nhận0 candidates thay vì1; after nhận1.
Đó là parser capability proof. GateF PostgreSQL/API tests mới chứng minh binding và
verdict; không nhầm hai mức đó. Không có live provider accuracy evidence mới.

## D. Cross-domain / adversarial results

New natural matrix: **36 positives** =6 domains ×1/2/3-table evidence ×2 fake model IDs;
36 JSON-rule cases được giữ để kiểm compatibility. Oracle từ independent PostgreSQL
VALUES trên fixture facts và separate literal thresholds/comparisons, không dùng
production parser/evaluator hoặc generated SQL làm expected.

| Domain | Metric / synthetic threshold | Topologies | Natural proof |
| --- | --- | --- | --- |
| Logistics | Fees /500000.00 | single/pair/chain | Supported subset |
| Tuition | Payments /30.00 | single/pair/chain | Supported subset |
| Staffing | Hours /12.50 | single/pair/chain | Supported subset |
| Sales | Revenue /40.00 | single/pair/chain | Supported subset |
| Energy | kWh /12.50 | single/pair/chain | Supported subset |
| Maintenance | Downtime /0.00 | single/pair/star | Threshold exercise, not operational safety certification |

UUID physical names, shuffled upload/table/column order, duplicate names, source IDs,
NULL/all-NULL/zero/equal values, reversed decisions và presentation aliases được giữ.
Natural unit suite có22 explicit operator expectations ×4 aggregates, locale/boundary/
long Decimal, wrong owner/workspace, partial/missing scope, mutated body/hash, fake
citations, missing entities, count-row/value mismatch, wrong root/metric/key/unit,
unknown exceptions/qualifiers, conflicting JSON/prose và instruction-bearing text.
Unrelated retrieved document không được dùng làm authority/citation cho verdict.

Hai policy fixtures cũ không-logistics được viết rõ source metric/ID/all-row scope,
neutral source-bound titles theo grammar mới, giữ thresholds/oracles/security/filters.
Mixed JSON/prose fixtures cũng ghi cùng source rule, không tiếp tục giả vờ câu chỉ
nói alias “total” đã chứng minh source binding. **KH gốc không bị rewrite.**
Những legacy ambiguous prose vẫn thuộc UNVERIFIED/explanation; không hạ guard để
giữ successful qualified statuses không có proof như trước.

## E. Regression / privacy / test environment

Full PostgreSQL cuối đã PASS trên database mới `_final_v2`.

| Suite | Kết quả chốt |
| --- | --- |
| Backend unit | **974 PASS**, 250 definitions, 27.95s |
| PostgreSQL integration | **778 PASS**, 108 definitions, 321.36s; 0 fail/error/skip |
| Frontend Vitest | **68 PASS**, 9 files |
| Playwright UI mock | **105 PASS**, isolated Vite15173; không main Google UI/live AI |
| Ruff / ESLint / typecheck / build / diff check | **PASS** |
| Original prose / cross-domain | 4 original positives +16 negatives;36 natural-domain positives; nằm trong full PG trên |
| Knowledge/Gemini/embedding live | **NOT RUN**,0 calls |

Tổng backend1752 parameterized scenarios/358 distinct definitions; không cộng lại
targeted/re-runs. So baseline847/722, thêm127 unit và56 PG. Security suites vẫn gồm
SELECT/table/column/ON/grain/revision/read-only/owner/CSRF/Guest/citation/privacy;
SQL validator/count/generator/executor source không đổi. Full PG deselect990
non-integration/live cases, unit deselect794 integration/live cases; đó không phải
skips hay live PASS.
New natural unit expectations độc lập operator dictionary của production; không
đếm repetitions/re-runs thành tests distinct.

Disposable container duy nhất: `shopquery-ai-natural-policy-test`,
`b7cbfb781030b6cc232e64df76127ec3903a8f47ee4b61b53ed7e9ced5d4c253`,
label natural-policy-20261022, loopback15443, tmpfs data, Mounts=[], không main hoặc
archived volume. DB `shopquery_test_natural_policy`, fresh full `_final`.
Test safety guard giữ nguyên, provider credentials/endpoints blank trong process,
fake generation/embeddings/mocked HTTP; không gọi providers thật.
Sau full PASS đã inspect lại exactID/label/no mounts/tmpfs/loopback15443 rồi stop/rm
duy nhất container này. Synthetic test DBs/tmpfs bị hủy, không cần khôi phục;
private JUnit giữ nguyên ngoài repo. Không prune/xóa images hoặc named volumes.
Private runner/JUnit: `C:\Work\ShopQuery-Backups\natural_policy_offline.py`,
`shopquery_test_natural_policy.xml`, `shopquery_test_natural_policy_final_v2.xml`.

Full PG đầu:750 PASS/28 FAIL. Đã xác định regex tách từ ở heading dùng escape
thừa (`[^\\W_]` thay vì `[^\W_]`), ghép cả heading nhiều từ thành một token;
KPI gốc và mixed-prose cases bị từ chối dù từng từ source-bound hợp lệ. Sửa đúng
hai expressions, thêm3 tests heading positive/negative; targeted72 PASS bao gồm
toàn bộ28 cases từng FAIL. Không thay fixture KH/oracle hay bỏ authority checks.
Một lượt unit thiếu process-env isolation vô tình đọc `.env` local JOIN ON, làm mock owner
None lỗi trước khi thực thi DB. Lượt chốt chạy từ backend với process env offline
JOIN/provider gates OFF, URLs chỉ disposable DB, đạt974/974. Không sửa main config.

Targeted đầu có fixture errors missing imported accounts (đã sửa test wiring),
mixed legacy prose contract refusals (đã làm fixtures tường minh, không nới proof),
và ambiguous-metric mutation vô tình sửa cả ORDER BY (đã giới hạn mutation vào SELECT
đầu tiên để thực sự exercise policy binder). Không đổi business oracle cho model.

Source span/headers/IDs/owner/document metadata không được logger xuất raw. Public
API giữ generic safe refusal, không raw policy/SQL/internal reason. COUNT semantic
contract, exact ON/root/grain, readonly execution, owner/revision/CSRF/provider gates
không nới; fallback/retry/timeouts/models/OAuth nguyên trạng. Không migrations.

## F. Operational deployment gate

Frozen source:76 app modules, LF UTF8 manifest sorted POSIX path bằng ordinal order:
`a6e093c37172b3bceedc7a22a5ff5e3002da4949217c098c6b258e00caacd8b2`.
Một preflight manifest đầu dùng PowerShell cultural sort thay vì ordinal nên báo
false mismatch; đã đối chiếu đúng serialization Python/sorted, không sửa source
hoặc bypass mismatch. Current helper pin đúng manifest trên, dừng nếu source drift.
Snapshot trước sửa regex có local manifest c52c2e60…; source freeze cuối và build
candidate phải dùng a6e093c3… sau regression fix, không lấy snapshot cũ làm proof.

Read-only preflight: old runtime72/72 vẫn baseline manifest47b9…, config digest
`5593c011af92e092eb2d7d4fdb59a01d4ad4b37137e63a452159e782090e236f`,
merged Compose0 differences; JOIN/provider gates giữON theo cấu hình chủ dự án,
fallbackOFF; không phát sinh AI call do bật sẵn gate.

Main API old `8a39b1cb69a0…`, image
`sha256:4bbf907c554099a7d542a53b10b5850b6bfc56d7ba1e9ebb499c696cc2c0151b`.
Web `2af67d527f2e…`, DB `511c4f5aaccc…`; active volume
`shopquery-ai_postgres_auth_20261019`, archived `shopquery-ai_postgres_data` giữ nguyên.
Ba files compose.yaml + .env.compose-ui.yaml + .env.join-v1.yaml bắt buộc dùng đủ.
Không build Web vì không production FE change. API recreate làm mất Guest RAM
state/files/history; quiescence operational counts phải0 ngay trước thao tác.

Protected preflight dùng đúng26 tables/hash algorithm/exclusions đã duyệt:
`c4ffe3daf04d2c1a20eb502b6613478526c7ceb4db401f39fe0b898da05afd6a`,
0 differences so latest approved baseline. Hash server-side trong REPEATABLE READ /
READ ONLY, timeout30s/lock3s; không xuất private row contents. Operational counts
authenticated/Guest active0; không reset leases/quota hoặc giả maintenance lock.

### Deployment PASS —22/10/2026 khoảng09:55–09:57 +07

- Build/recreate **API only**, đủ ba Compose files; không build/recreate/reload web,
  không recreate DB. Không reset/migration/restore/seed/re-ingest hoặc chat smoke.
- New API `75086624f3f2ec25c85e4f5c3c44bc8e074f1d1dfe30d3591be9a2545c2f44f3`.
- New image `sha256:e48449814155713a9724dd1d816ec58baebd81738640cba2fe79d820b3b38132`.
- Candidate chạy network=none:76 modules AST/compile/imports PASS,70 installed
  Python packages exact-match baseline. Runtime76 modules exact-match frozen manifest.
- API/Web/DB healthy, health8001 và health8080 đều status=ok;
  Nginx chuyển đúng API. Startup vài giây đầu có connection-ended/502 trong lúc
  API chưa ready; sau readiness cả hai health PASS, không cần restart web.
- Web/DB toàn bộ recorded properties giữ nguyên; một lần `docker inspect` đảo thứ
  tự hai DB mounts nên strict-array compare báo khác. Đã so lại từng mount đầy đủ
  fields theo Destination: chính xác cùng bind read-only và volume, không mount drift.
  Không bỏ property khác hoặc rebaseline dữ liệu để làm PASS. Evidence cũ được giữ.
- Environment digest giữ5593c011…; JOIN ON, Knowledge/Gemini models, embedding2/768,
  quotas/retries/timeouts/fallbackOFF/OAuth/provider gates như trước. Không `.env` edits.
- Protected-before/pre-recreate/after đều26 tables,0differences, SHA c4ffe3da… nêu trên.
  Read-only quiescence ngay trước recreate: authenticated0/Guest0. Không reset leases.
- Rollback tag mới `shopquery-ai-api:rollback-pre-natural-policy-20261022` trỏ đúng
  pinned old image4bbf907c…; không overwrite tag khác. Nếu cần rollback, dùng đủ
  Compose files + temporary API image override trỏ pinned old image, API-only
  no-deps/no-build sau quiescence; không restore DB. **Chưa cần rollback.**
- Compose cảnh báo archived volume label không khớp selected active volume nhưng
  giữ nó nguyên vẹn; active/archived volume metadata và DB identity không đổi.

Fingerprint scope **không mở rộng**: loại users/user_sessions/oidc_flows; loại
dataset13 metadata/document/history theo predicates cũ, nhưng vẫn gồm physical
uploaded source tables trong danh sách26 đã duyệt. Vì vậy không tuyên bố hash này
chứng minh dataset13 policy vectors/history hay auth activity bất biến. Không có
ingestion/history/auth/database write được tác vụ này thực hiện trên main; không
đọc/xuất thêm raw nội dung main để bù scope. Provider/live/browser acceptance vẫn NOT RUN.
Private before/candidate/after/protected JSON tại
`C:\Work\ShopQuery-Backups\hybrid-natural-deployment-20261022`, không commit.

## G. GitHub delivery

Baseline main HEAD `d9bcce165d6af2124866770c2879a74cbb3a207c`; repo PUBLIC,
default main đã verify. Working tree giữ reviewed changes của task consistency cũ
và task hiện tại; chưa stage/commit/push tại checkpoint. Không force/reset/rebase.
Exact stage inventory, secret scan, remote SHA và CI đúng SHA sẽ được ghi sau
deployment PASS. Không lấy CI cũ hoặc local tests làm CI mới.

Không public .env/secrets/backups/JUnit/provider transcripts/customer rows/cookies/
tokens/logs/venv/cache/build output. Original policy fixture chỉ là dữ liệu synthetic
đã được phép; không copy dữ liệu thật hoặc file bí mật vào repository.

## H. Limitations / live plan

Không giải mọi natural prose/policy precedence, foreign languages ngoài vi/en,
unit conversion, partial/multi-chunk authority, filtered/compound/top-N rules,
unproved composite IDs, hidden exceptions hoặc semantically ambiguous references.
Unknown proof → UNVERIFIED/INSUFFICIENT_EVIDENCE hoặc safe refusal, không fabricated
qualified list. Model vẫn có thể chọn sai metric/mode hoặc sinh schema/status sai;
backend không tự sửa sang câu hỏi khác. Offline proof không đo provider repeatability.

Live regression **chỉ đề xuất**, không dùng ngân sách cũ: KH trước, chỉ KH fullyPASS
mới GH; tối đa2 chats/8 logical generations/2 query embeddings/0 document embeddings
nếu policy hợp lệ. SDK/adapter retries có thể tăng HTTP requests. Real Google UI,
original prose, independent oracle, fresh fingerprints, exact citations/summary/
details/model/history reload; dừng lỗi đầu, không manual retry. Browser unavailable
thì UI live NOT RUN, API history không thay thế browser acceptance.

Nguồn kỹ thuật: [PostgreSQL aggregates](https://www.postgresql.org/docs/17/functions-aggregate.html),
[Python fullmatch](https://docs.python.org/3.11/library/re.html#re.fullmatch),
[Python Decimal](https://docs.python.org/3.11/library/decimal.html),
[Pydantic strict](https://docs.pydantic.dev/latest/concepts/strict_mode/).
Các nguồn chứng minh semantics của thư viện; không phải chứng nhận grammar hiểu
mọi policy nghiệp vụ hoặc source data/header declarations đều xác thực ngoài đời.
