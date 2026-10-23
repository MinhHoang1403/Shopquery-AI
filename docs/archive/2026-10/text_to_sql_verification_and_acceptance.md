> HISTORICAL snapshot. Current status: [V2 acceptance](../../v2_final_acceptance.md).

# Final verification — Text-to-SQL / JOIN

Ngày 21/10/2026. Workspace `C:\Work\ShopQuery AI`.

Trạng thái nghiệm thu: **CODE REVIEW PASSED · OFFLINE VERIFIED · POSTGRESQL VERIFIED**.
**Cập nhật mới nhất, 21/10 11:24 giờ Việt Nam: DEPLOYED — LIVE NOT VERIFIED.**
Phần G ghi triển khai API sau phê duyệt riêng; A–F giữ evidence/snapshot của lượt verification
trước deployment. Không diễn giải các dòng “chưa deploy” trong snapshot cũ thành runtime mới.
**Cập nhật cleanup, 21/10 11:38: DOCKER CLEANUP COMPLETE — MAIN STACK HEALTHY —
DEPLOYED — LIVE NOT VERIFIED.** Xem phần H; chỉ hai PostgreSQL test containers bị xóa.

Không có quyền deploy hoặc live trong yêu cầu này. Không commit/push. Không coi ngân sách
đề xuất trong báo cáo cũ hoặc ngân sách Gate D đã dùng là quyền thực hiện.
Đây là giới hạn của lượt verification ban đầu. Phê duyệt deployment riêng sau đó chỉ cho
API build/recreate và operational checks, vẫn không cấp quyền provider live hoặc data audit.

## A. Source review

### A1. Baseline, phạm vi và cách review

- HEAD: `e2151a3d6b37f3a11e83f68553e5985bbe087deb`, branch main; source deployed là
  `50d7bac4e1f6af8adffeb8f317a458f637de7bb0`.
- Bốn production files đang dirty, chưa commit, đúng bản sửa của lượt trước. Review lại
  toàn bộ diff, call sites, AST/SQL semantics và missing edge cases, không giả định HEAD
  đã chứa chúng. Đây là review lại bởi coding agent, không phải chứng nhận bên thứ ba.
- Không sửa production thêm trong lượt này: chưa tìm được regression mới có bằng chứng
  buộc thay đổi logic. Production diff so HEAD vẫn 56 additions / 11 deletions, bốn files.
- Giữ nguyên `handoff.md`, báo cáo investigation và mọi local modifications có sẵn,
  đặc biệt `docs/archive/2026-10/sql_join_root_cause_audit.md`; không reset/checkout/overwrite.
- Đối chiếu AGENTS, handoff, investigation mới nhất, Gate D, JOIN acceptance, SQL correctness
  và source/tests liên quan. Kết luận mới không bị kết luận live lịch sử cũ che lấp.
- `handoff.md` SHA-256 vẫn
  `dddda5a371d81117094a39b357207c72bfa642ff4fe3830c9fb3f1f5dbbdacb4`.

### A2. Bốn production files

| File/function | Kết quả review |
|---|---|
| `text_to_sql/join_policy.py::_normalize_selected_count_order` | Chỉ direct Count ở top-level ORDER BY, exact AST match với SELECT Alias được phép, output alias duy nhất. SELECT Count vẫn phải qua aggregate guard. Không chọn cột/khóa/metric khác. |
| `text_to_sql/join_policy.py::_validate_join_aggregates` | Row count và non-NULL value count vẫn khác; dimension SUM/AVG/count, DISTINCT/filter/nested/count arithmetic vẫn fail-closed. Verified fact JOIN-key count normalization là behavior cũ, không mở rộng sang nullable/non-key. |
| `text_to_sql/validator.py::validate` | Parse/SELECT-only/table/function/column validation trước JOIN policy; cả two/three-table đều revalidate object/function/column sau normalization. Guard invocation vẫn ở pipeline sau validate. |
| `datasets/context.py::build_dataset_sql_context` | Router nhận source/capability/table/column/header/approved relation/root facts; không còn pair SQL instructions/examples. Generator vẫn nhận đầy đủ physical identifiers, SQL subset, pair/tree rules và per-entity grouping ID. |
| `text_to_sql/generator.py::SqlDraft/SqlGenerator.generate` | Success reason=null, refusal sql rỗng+reason; field descriptions và prompt thống nhất. Hybrid chỉ lấy SQL evidence, không bịa policy threshold trước retrieval. Không nới validator hoặc đổi API shape. |

### A3. Chứng minh COUNT-order và giới hạn

Nếu một projection duy nhất là `COUNT(E) AS a`, direct `ORDER BY COUNT(E)` có thể dùng
output label `a`. PostgreSQL ưu tiên output name khi ORDER BY đơn giản trùng tên input;
normalizer giữ alias Identifier/quoting và không sửa sort flags.
[PostgreSQL 17 ORDER BY](https://www.postgresql.org/docs/17/queries-order.html).

Đã review SQLGlot **29.0.1**, không bật qualify/optimizer tổng quát.
[Source version tương ứng](https://github.com/tobymao/sqlglot/blob/v29.0.1/sqlglot/optimizer/qualify.py).

Đã kiểm thêm:

- COUNT(*)/COUNT(nullable measure); selected canonical aliases; 2-table và 3-table chain/star.
- Multiple sort expressions, hai COUNT khác nhau cùng ở ORDER BY, ASC/DESC, NULLS FIRST/LAST,
  LIMIT, lower quoted và upper unquoted aliases; uppercase quoted vẫn ngoài contract.
- Source có cột tên `fact_row_count` nhưng không selected: output alias vẫn phân giải đúng.
- Source column có cùng output name cũng selected, duplicate aliases, nested COUNT(SUM),
  DISTINCT hoặc COUNT khác projection: không normalize để vượt guard.
- HAVING COUNT và aggregate không có selected projection tương ứng tiếp tục fail-closed;
  không mở thêm HAVING contract hoặc arbitrary repair.
- PostgreSQL raw/canonical/validated results đối chiếu exact oracle. AST assertions giữ
  SELECT expressions, WHERE, GROUP BY, LIMIT, predicates ON và sort flags; chỉ bindings
  INNER tương đương có thể canonicalize theo behavior đã duyệt trước.
- Kết quả validate idempotent; owner/revision execution guard vẫn chạy trước real executor.

**B1 baseline replay mới trong lượt này:** load riêng policy từ pinned commit `50d7bac`
vào process test, thay hai policy function bằng mock patch trong process, không đổi source
hoặc runtime. Bốn tổ hợp 2/3 bảng × COUNT(*)/COUNT(column) bị từ chối đúng
`count_star_alias`/`count_column_alias`; cùng SQL với policy hiện tại PASS. Đây là
isolated policy comparison, không phải chạy một server build cũ.

### A4. Auth/Guest, adapters và Hybrid

Auth và Guest đều dùng context builder đã sửa; schema namespace/owner boundary khác nhau
giữ nguyên. Full integration gồm Guest TEMP và authenticated API/session/history; mock
HTTP tests đi qua cả Gemini và Knowledge adapters. Không thay models, retries hoặc fallback.

Hybrid vẫn SQL-first: route -> SqlDraft -> validator/guard/executor -> SQL grounding ->
scoped retrieval -> synthesis -> citation ID check. Tests mới kiểm exact policy threshold,
SQL rows, sources và history. Khi generator trả unsupported, phải dừng trước validator/
executor/retrieval, không có SQL-grounding hoặc Hybrid answer giả. Khi SQL draft sai cũng
không dùng retrieval/synthesis để che lỗi. Không suy ra nguyên nhân model GH cũ từ prompt.

### A5. Invariants

SELECT-only, allowlist tables/columns/functions, exact approved ON, tối đa 3 tables/2 edges,
root fact từ metadata, dimension entity ID grouping, numeric fact measures, row/value-count
semantics, Decimal/BIGINT/NULL/zero, Asia/Ho_Chi_Minh time boundaries, owner/workspace/CSRF,
revision locks, execution timeout/row cap, truthful refusal/model attribution đều giữ nguyên.

## B. Regression results

### B1. Tests/fixtures bổ sung trong lượt này

- `tests/gate_d_fixture.py`: dựng ba CSV synthetic logistics, không phụ thuộc file private
  lúc chạy CI. Có 50 facts/15 drivers/5 warehouses, tất cả source headers/types/extra columns,
  4 NULL fees, 3 zero fees, status distributions như fixture gốc. Dữ liệu giả, không credentials.
- `tests/test_gate_d_replay_integration.py`: 8 positive scripted candidates cho exact bốn
  câu hỏi × hai model selections, authenticated API, real PG guard/executor/retrieval,
  exact rows/answer evidence, policy >=500000, citation và history GET/foreign-owner 404.
  Thêm 7 negative hypotheses, chặn trước execution/retrieval và không echo raw reason.
- `tests/test_count_order_edges_integration.py`: 6 PostgreSQL edge cases trên sáu domain,
  CSV/XLSX, random physical names, chain/star, reverse bindings, sorted top-N, quoting/casing,
  WHERE và time range; raw/canonical/guarded SQL đều khớp oracle.
- `tests/test_sql_generation_contract.py`: thêm 5 unit cases về source-name shadowing,
  duplicate output, nested aggregate, quoted case và hai selected COUNT sort metrics.

Tăng **26 distinct tests** so lượt trước: 5 unit + 21 integration. Không cộng targeted reruns
hoặc các parameterized golden subsets lần thứ hai. Không thêm/deactivate security tests.

### B2. Môi trường

Container test riêng `shopquery-ai-reliability-research`, ID `9eaf77a22e7d`, label
`shopquery.test=reliability-investigation-20261021`, loopback **15438**, PG **17.8**,
image `pgvector/pgvector:0.8.1-pg17-trixie`. Data tmpfs `/var/lib/postgresql/data`,
inspect `.Mounts=[]`, không main named volume.

Khởi động lại container test đã dừng của lượt trước làm tmpfs init lại; không giữ giả định
database cũ còn tồn tại. Targeted DB `shopquery_test_reliability_investigation`; full suite
trên DB mới **`shopquery_test_final_verification`**, `current_database()` kiểm trước chạy.
Setup/reader role riêng; test safety guard không bị tắt. Không chạy trên main `shopquery`.

Process test đặt `SQL_JOIN_V1_ENABLED=false`, JOIN fixtures bật rõ ràng; generation keys/
endpoint bị đặt rỗng. Các adapters/gateways/embedders dùng mocks, không bật opt-in live.

Frontend dùng Vite test server **127.0.0.1:15173**, Playwright mock specs với API intercepts,
không dùng 8080 hoặc Google storage state. Không chọn các live test scripts.

### B3. Bảng kết quả

| Test group | Previous baseline | Current result | Status |
|---|---|---|---|
| Ruff | PASS | PASS sau chỉnh style trong các tests mới | PASS |
| Unit | 630 | **635 PASS**, 574 deselected, 22.63 giây | PASS |
| PostgreSQL full | 537 | **558 PASS**, 651 deselected, 204.98 giây | PASS |
| COUNT-order integration cũ | 24 | **24 PASS** trong full integration; không cộng lại vào tổng | PASS |
| COUNT-order edges mới | — | **6 PASS**, 5.64 giây targeted | PASS |
| Gate D offline API replay mới | — | **15 PASS**, 15.26 giây targeted | PASS |
| SQL generation contract | 32 | **37 PASS**, 2.52 giây targeted; thuộc unit 635 | PASS |
| Frontend lint/typecheck | PASS lịch sử | Cả hai exit 0 | PASS |
| Frontend Vitest | 66 | **66 PASS**, 9 files, 17.25 giây | PASS |
| Frontend build | PASS lịch sử | tsc + Vite build exit 0 | PASS |
| Playwright mock UI | 105 | **105 PASS**, 5 viewports, 3.4 phút | PASS |
| Providers/Google UI live | NOT RUN bản sửa | **NOT RUN**, 0 generation / 0 embedding live | NOT RUN |
| Deploy / commit / push / CI SHA mới | NOT DONE | **NOT DONE** | AWAITING APPROVAL |

Full unit: `pytest -m 'not integration and not live' -q --tb=short`.
Full PG: `pytest -m integration -q --tb=short` trên target riêng nói trên.
FE: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, `npm run test:e2e`
với `SHOPQUERY_E2E_START_SERVER=1`, `SHOPQUERY_E2E_BASE_URL=http://127.0.0.1:15173`.

Tổng backend distinct **1193 = 635 unit + 558 integration**, tăng 26 so baseline 1167.
16 tests opt-in live không chạy. Không có failing tests còn treo. Ruff và
`git diff --check` cuối PASS (Git chỉ cảnh báo LF/CRLF). Sau kiểm thử, đã dừng đúng
container test `9eaf77a22e7d` để không chạy dư, không xóa container/image/volume. Tmpfs
chỉ chứa dữ liệu giả dùng một lần, có thể tái tạo bằng fixtures; không phải backup evidence.
Không dừng hoặc recreate main services.

Lint ban đầu phát hiện style-only trong tests mới (literal split, line length, pytest fixture
name shadowing); đã sửa, không hạ security assertions. Không có production regression mới
được phát hiện trong review/targeted runs. Không coi lệnh còn chạy là PASS.

### B4. Coverage và giới hạn số liệu

Full PG chứa 144 domain golden cases cũ, 24 COUNT-order cases cũ và mọi suites auth/owner/
Guest/relationship/SQL correctness/timezone/RAG/Hybrid/provider mock liên quan. Sáu domain:
giao vận, học phí, bán hàng, nhân sự, năng lượng và bảo trì holdout. Independent oracle
không lấy generated SQL làm expected; exact entity IDs, names, sums/averages/counts,
NULL vs zero và ordering được đối chiếu ở các cases tương ứng.

105 browser tests kiểm evidence/history/Decimal/zero/NULL, model/fallback display, refusal,
dataset/relationship management, auth/Guest transitions và responsive layout. Đây là mock UI,
không phải Google live hoặc full UI-to-provider acceptance.

Fake Gateway scripts route/draft/answer. Vì vậy 8/8 positive offline replay **không phải**
Knowledge/Gemini accuracy; số mẫu nhỏ, có fixtures dùng chung, không có statistical reliability
claim. Negative 7/7 chặn đúng stage chỉ là coverage cho các hypotheses đã nêu.

## C. Gate D root-cause closure

### C1. Tái tạo fixture và oracle

Đã so parsed rows của ba CSV dựng bởi `gate_d_fixture.uploads()` với đúng ba CSV synthetic
gốc ở Downloads, không dùng main database. Exact fact projection 50 rows khớp saved oracle
ngoài Git `C:\Work\ShopQuery-Backups\live-gate-d-20261021\oracle.json`.
Oracle saved SHA-256 `bda5e5aac8a08af94713c66778b1357ac5831a306db36aa999ea834c15f587ee`.

Oracle mới dùng PG VALUES từ business mapping đã biết, **trước dựng scripted draft**.
15 driver groups và 5 warehouse groups khớp saved oracle về ID/name/SUM/COUNT. Tổng phí
2472500.00; warehouse totals 393500.00 / 598000.00 / 502000.00 / 439000.00 / 540000.00,
mỗi kho 10 facts. KPI >=500000.00, all statuses, qualifying KHO02/KHO03/KHO05.

Physical tables trong DB test là UUID mới, không dùng registry/table IDs main. Một automatic
orders->drivers edge và một manual drivers->warehouses edge, approved metadata + real owner
guard. Sáu SQL replay có document_count=0 như live cũ; hai Hybrid thêm một policy chunk
bằng fake embedding. Policy test là bản ngắn cùng điều kiện KPI, không thay tài liệu main.

### C2. Exact questions giữ nguyên

Q1: “Liệt kê don_id, phi_giao_vnd và trang_thai của toàn bộ đơn giao hàng, tính tất cả
trạng thái; sắp xếp don_id tăng dần. Giữ nguyên giá trị 0 và NULL, không thay NULL bằng 0.”

Q2: “Theo từng tài xế, cho biết mã tai_xe_id, tên ten_tai_xe, tổng phi_giao_vnd và số dòng
đơn giao hàng, tính tất cả trạng thái. Phân biệt tài xế theo mã ID; đếm dòng đơn, không đếm tài xế.”

Q3: “Theo từng kho, cho biết mã kho_id, tên ten_kho, tổng phi_giao_vnd và số dòng đơn giao
hàng, tính tất cả trạng thái. Dùng liên kết đơn giao hàng → tài xế → kho; phân biệt kho theo mã ID.”

QH: “Theo tài liệu live_gate_d_kpi.md, những kho nào đạt KPI tổng phí? Với từng kho, cho
biết mã kho_id, tên ten_kho, tổng phi_giao_vnd của tất cả trạng thái, số dòng đơn và kết luận
đạt/chưa đạt. Kết hợp dữ liệu đơn giao hàng → tài xế → kho với điều kiện trong tài liệu,
phân biệt kho theo mã ID.”

### C3. Phạm vi fix theo dạng draft

| Hypothesis / behavior | Kết quả hiện tại | Classification |
|---|---|---|
| SELECT COUNT(*) đúng alias, lặp ở ORDER BY | Raw/canonical oracle + validated pipeline PASS | FIXED AND VERIFIED offline/PG |
| SELECT COUNT(nullable measure) AS fact_value_count, lặp ở ORDER BY | Giữ non-NULL count khác row count; PASS | FIXED AND VERIFIED offline/PG |
| SELECT COUNT(*) AS delivery_count thật sự không đúng contract | count_star_alias, không executor/retrieval | INTENDED UNSUPPORTED |
| COUNT(column) sai SELECT alias | count_column_alias, không executor/retrieval | INTENDED UNSUPPORTED |
| COUNT(nullable measure) AS fact_row_count | count_column_alias, không chuyển sang COUNT(*) | INTENDED UNSUPPORTED |
| Dimension SUM | dimension_column, không đổi thành fact SUM | INTENDED UNSUPPORTED |
| Thiếu ID GROUP BY / sai key ON | join_grain / join_key, không tự thêm ID/sửa khóa | INTENDED UNSUPPORTED |
| SqlDraft có nonempty unsupported_reason | generator_unsupported trước execution/retrieval | INTENDED fail-closed behavior; lý do model thật UNKNOWN |

### C4. Closure từng probe lịch sử — KHÔNG gán draft giả thành draft cũ

| ID | Original stage/reason | Offline evidence mới | Historical live closure |
|---|---|---|---|
| K1 | SQL PASS, 50 rows | Q1 scripted + exact PG oracle + history PASS | Chưa live lại source mới |
| K2 | join_aggregate/count_star_alias | Q2 selected COUNT-order hợp lệ PASS; wrong SELECT alias vẫn refuse | UNKNOWN / REQUIRES LIVE PROVIDER |
| K3 | join_aggregate/count_star_alias | Q3 rooted three-table selected COUNT-order PASS; wrong grain/key vẫn refuse | UNKNOWN / REQUIRES LIVE PROVIDER |
| G1 | SQL PASS, 50 rows | Q1 scripted + exact PG oracle + history PASS | Chưa live lại source mới |
| G2 | SQL PASS, 15 groups | Q2 scripted + exact PG oracle + history PASS | Chưa live lại source mới |
| G3 | join_aggregate/count_column_alias | Nullable-value COUNT-order hợp lệ PASS trong matrix; wrong COUNT row/value còn chặn | UNKNOWN / REQUIRES LIVE PROVIDER |
| KH | HYBRID -> count_star_alias trước retrieval | QH scripted SQL->PG->retrieval->KPI/citation/history PASS; wrong draft vẫn fail trước RAG | UNKNOWN / REQUIRES LIVE PROVIDER |
| GH | generator_unsupported trước validator | Nonempty reason tái hiện fail-closed; valid scripted QH đi hết pipeline | UNKNOWN / REQUIRES LIVE PROVIDER |

**Không có failure live lịch sử nào trong năm cases được chứng minh đã khép hoàn toàn**:
raw rejected drafts không được lưu. Lỗi application COUNT-order được fix không đồng nghĩa
cả năm model failures đều có cùng nguyên nhân. Không suy từ offline answer hoặc generic UI.

## D. Read-only preflight và deployment readiness

### D1. Runtime identity hiện tại

| Service | Container ID prefix | Port | Health |
|---|---|---|---|
| web | 2af67d527f2e | 127.0.0.1:8080 | healthy |
| api | ea2a3f3688ea | 127.0.0.1:8001 | healthy |
| db | 511c4f5aaccc | 127.0.0.1:15432 | healthy |

GET `http://127.0.0.1:8080/api/health`: status ok. Không gửi chat/upload hoặc dùng Google
session. Database volume vẫn `shopquery-ai_postgres_auth_20261019`; bootstrap bind mount
read-only như cũ. Không recreate PostgreSQL/web/API, không migration hoặc main SQL writes.

API/web compose labels: `compose.yaml`, `.env.compose-ui.yaml`, `.env.join-v1.yaml`.
DB compose label còn base + UI override từ lúc tạo; JOIN override chỉ tác động api, không
là lý do recreate DB. Khi deploy phải dùng đủ ba files, tuyệt đối không chạy base một mình.

Allowlisted runtime/merged Compose khớp, 0 mismatches: JOIN=true, provider data gate=true,
Guest AI/enabled=true; Knowledge `knowledge`, Gemini `gemini-3.5-flash-lite`, embedding
`gemini-embedding-2`/768; fallback=false; Gemini attempts=3/timeout=30000ms; Knowledge
attempts=1/timeout=60s; chat-user/hour=30, Guest questions/session=5, Guest timeout=120s.
Không xuất endpoint credentials, OAuth secrets, allowlist email hoặc full resolved env.

### D2. Source/runtime và rollback

- Hash **71 Python modules** runtime khớp pinned source commit `50d7bac` (0 mismatches).
- Local khác runtime đúng bốn production files của patch, không có module mismatch khác.
- Runtime manifest SHA-256:
  `715c5b01327e970c67930c304529c6bce5f44a38be82231512885f22c770c167`.
- Working-tree production manifest SHA-256:
  `bd500b4c2a56631f91751a086c5e092178f4fc9c6a642b7d5acada2e66a1e238`.
- Đây là module-map hashes với LF-normalized file bytes, không phải Git commit hoặc image ID.
  Source mới chưa được commit và chưa deploy; mismatch bốn files ở bước chuẩn bị là dự kiến.

Current immutable API image có sẵn:
`sha256:09fb41dc043ee14bf52de6baf9d0a611f28287c87e599632e03b2f7aeaabf9d7`.
Current web image:
`sha256:5ca6e17125f12574cf8cdf4d030b6a0a209007e9469b264e94e6d98056090146`.

**Phát hiện vận hành:** tags `rollback-root-audit-20261021` còn tồn tại nhưng API trỏ
`sha256:9253bf...`, web trỏ `sha256:f5e708...`, không phải current images nói trên.
Không coi tên tag là bằng chứng rollback đúng version. Chưa sửa tags hoặc build images.
Khi được phép deploy, phải giữ/current-tag hoặc pin đúng current API immutable ID đã hash
và kiểm tra image vẫn tồn tại ngay trước build. Không dùng hai tag cũ một cách mù quáng.

### D3. Data integrity / prerequisites chưa đọc trên main

Không kết nối main database trong lượt này để hash dữ liệu hoặc xác minh owner/relationship
hiện tại. Không có quyền main-metadata/fingerprint mới theo Gate E; không lấy hashes lịch sử
làm “before” mới hoặc tuyên bố toàn database không có concurrent writes.

Evidence cũ xác nhận workspace synthetic **13**, 50/15/5, hai edges và policy một chunk.
Tình trạng hiện tại của owner, tables/revisions, document/vector và session Google còn cần
read-only preflight được duyệt. Không đọc/xuất cookies/tokens, không tạo session giả trên main.

### D4. Deployment plan — CHƯA THỰC HIỆN

1. Xin duyệt API deployment, read-only synthetic metadata + protected fingerprints, window
   ảnh hưởng Guest, và ngân sách/capture evidence live riêng. Không mở quyền từ lượt trước.
2. Freeze source snapshot theo production manifest; xác minh dirty files không đổi sau tests,
   không giả HEAD có patch. Nếu source đổi, test lại phần ảnh hưởng trước deploy.
3. Đối chiếu container/database/volume/ports + đầy đủ Compose overrides + allowlisted settings.
   Kiểm chứng synthetic13 owner/edges/types/revisions/policy; dừng nếu khác evidence dự kiến.
4. Đọc counts/fingerprints business được duyệt; không hash/xuất session secrets. Phối hợp
   drain in-flight chat/upload và tránh concurrent destructive writes lúc so before/after.
   Không có migration nên không cần chạm schema/DB volume.
5. Giữ immutable current API image/rollback config trước build; chỉ build/recreate **api**
   với ba Compose files và `--no-deps`; không recreate db/web, không restart toàn stack.
6. Kiểm health, module manifest mới, flag/gates/models/settings, API/web/DB IDs và database
   identity; chỉ API ID được phép đổi. Không tự gọi AI để “smoke” khi chưa có budget live.
7. So protected data hashes và owner isolation read-only; whitelist đúng operational counters
   hoặc synthetic conversations nếu đã được duyệt, không bỏ qua dataset khác.
8. Nếu health/module/config/data mismatch: dừng trước probes. Rollback API image là thao tác
   main riêng trong quyền triển khai được duyệt; **không restore/reset database**. Nếu chưa
   được cấp rollback authority, báo tình trạng/xin quyết định thay vì tự hành động.

API recreation làm mất **Guest in-memory sessions/files/history và in-flight requests**;
thông báo/drain trước. Google sessions lưu DB không bị reset bởi thiết kế, nhưng request
đang chạy có thể gián đoạn. Không hứa bảo toàn Guest state qua recreate.

## E. Live acceptance plan — chờ duyệt, không có results mới

### E1. Chia batch / budget

| Batch đề xuất | Cases | Max chats | Logical generation stages | Query embeddings | Trạng thái |
|---|---|---:|---:|---:|---|
| A, ưu tiên SQL cũ thất bại | K2 Q2, K3 Q3, G3 Q3 | 3 | 9 | 0 | NOT RUN / AWAITING APPROVAL |
| B, chỉ sau A đạt và được duyệt | KH QH, GH QH | 2 | 8 | 2 | NOT RUN / AWAITING APPROVAL |
| C, các SQL cũ từng pass | K1 Q1, G1 Q1, G2 Q2 | 3 | 9 | 0 | NOT RUN / AWAITING APPROVAL |
| D, sáu câu mới của investigation §I | 2-table, 3-table, Hybrid × hai providers | 6 | 20 | 2 | NOT RUN / AWAITING APPROVAL |

Đề nghị duyệt **A+B trước: 5 chats, tối đa 17 logical generation stages, 2 query embeddings**.
Cả tám câu cũ là 8/26/2; nếu thêm cả sáu câu mới thì tổng 14/46/4. Không tự thực hiện
14 probes. Không cần document embedding mới nếu chunk/vector hiện tại còn hợp lệ.

Mọi batch cần chốt source/runtime, fixture, exact questions, budget và capture scope.
SDK retries và Knowledge structured-format attempts có thể tăng HTTP requests/cost; logical
stages không phải HTTP hard cap. Không tự retry chat, repair SQL hoặc chọn lần may mắn PASS.

### E2. Oracle và evidence cần thu

Trước provider calls, read-only PG oracle chốt independent IDs/names/row multiset/order/
SUM/AVG exact Decimal/row counts/non-NULL counts/null-zero và policy threshold/citation IDs.
Giữ đúng câu hỏi cũ, workspace13 và policy gốc cho phép so trước/sau. Không dùng SQL model
làm expected hoặc ghi results vào prompt như “đáp án”.

Mỗi probe ghi case ID, requested/actual model, fallback, route, safe stage/reason,
execution reached, rows/count correctness, answer, citations và history reload. Google login
do user thực hiện bình thường. Nếu cần chứng minh normalizer thực sự được kích hoạt live,
cần **duyệt riêng capture raw SqlDraft chỉ của synthetic request** vào private evidence ngoài
Git; không bật raw prompt/SQL/result logging toàn production. Không có raw draft thì chỉ
được xác nhận result đúng, không khẳng định normalizer đã chạy.

### E3. Stop conditions

Dừng ở failure đầu tiên: wrong source/owner/workspace/revision, unexplained fingerprint
change, silent fallback, unsafe acceptance, wrong SQL semantics/oracle, provider/quota error,
retrieval/citation/grounding/history mismatch. Không tự tiếp tục batch sau để “lấy tỷ lệ đẹp”.
Giữ fail-closed; báo chính xác stage và phần chưa biết, không phỏng đoán raw draft cũ.

## F. Remaining risks / decision

- Chưa triển khai patch trên 8080; user hỏi lại trên main lúc này vẫn dùng code cũ.
- Năm failures Gate D thực tế chưa được live closure; valid hypothetical candidates không
  chứng minh Knowledge/Gemini sẽ sinh cùng SQL hoặc hết generator_unsupported.
- COUNT alias sai thật sự, unknown-policy business formula, label-only category grouping,
  HAVING COUNT, unsupported joins/graphs vẫn có thể bị từ chối đúng contract.
- Synthesis/grounding là model-generated; citation-ID validation không chứng minh mọi kết
  luận đều đúng. Offline script không đo độ ổn định provider across independent runs.
- Main current synthetic prerequisites/fingerprints chưa kiểm vì chờ quyền; các tag rollback
  cũ khác current image, phải dùng pinned image đúng version trong plan mới.
- Không đổi main data/schema/timestamps/embeddings/OAuth/gates/models/quotas; không VPS,
  Langfuse, global prune hoặc Docker volume cleanup. Không tự commit/push.

Sau live regression nếu đạt, mới đề xuất robustness budget riêng cho paraphrases, random
schema names/physical IDs, unrelated tables, upload order, duplicate labels, equivalent SQL
forms, Guest/auth và independent provider runs. Không suy reliability thống kê hoặc tính đúng
100% từ bộ câu hỏi cố định. Trạng thái hiện tại dừng đúng ranh giới xin phê duyệt.

## G. Triển khai API local 8080 — 21/10/2026

### G1. Quyền và preflight

Thực hiện theo yêu cầu deployment riêng đính kèm `a1db6930-48ab-4da0-b904-bb706db88aac`.
Cho phép bảo vệ image, build/recreate chỉ API, health/config/source verification và reload
Nginx nếu xác minh lỗi DNS. Không cho phép provider calls, embeddings, upload, business data
audit/fingerprints, main writes/migration/restore, commit hoặc push.

Source không đổi so bộ **635 unit + 558 integration** đã đạt; chỉ đúng bốn production files
dirty như A2. Local production manifest vẫn
`bd500b4c2a56631f91751a086c5e092178f4fc9c6a642b7d5acada2e66a1e238`.
Không chạy lại test DB hoặc bộ test lớn vì không có source change. Git HEAD vẫn e2151a3;
image mới chứa working-tree patch, không phải source nguyên trạng HEAD.

Preflight xác minh health/IDs/ports/volume và đầy đủ ba Compose files. So merged Compose
với runtime environment hoàn toàn trong process, chỉ xuất mismatch names/hash/allowlisted
non-secret settings: 0 mismatch; không lưu/export full environment hoặc credentials.

Đã thông báo Guest RAM state sẽ mất khi recreate. Chỉ đọc **aggregate operational counts**
trong read-only transaction, statement timeout 3 giây: `resource_leases` chưa hết hạn và
`resource_limits` theo prefix Guest lease; không đọc key/user/account/session/chat content.
Hai lần kiểm (preflight và ngay trước recreate): authenticated_active=0, guest_active=0.
Không khẳng định đây là maintenance lock ngăn mọi request mới; đây là quiescence snapshot
ngay trước đổi API, kết hợp graceful shutdown. Không sửa gate/quota để chặn người dùng.

### G2. Rollback protection và build

Lấy image từ API container đang chạy, xác minh bằng immutable ID và so báo cáo. Tạo tag
mới **`shopquery-ai-api:rollback-pre-textsql-20261021`**, trước đó chưa tồn tại, trỏ đúng:

`sha256:09fb41dc043ee14bf52de6baf9d0a611f28287c87e599632e03b2f7aeaabf9d7`.

Không ghi đè/xóa các rollback tags cũ. Không dùng tag rollback-root-audit sai baseline.

Build đúng lệnh:

```powershell
docker compose -p shopquery-ai -f compose.yaml -f .env.compose-ui.yaml -f .env.join-v1.yaml build api
```

Build PASS, `uv sync --frozen --no-dev`; dependency layer cached, chỉ reinstall project.
Trước recreate, chạy candidate image chỉ để đọc source/package metadata, **network none**,
entrypoint Python, container kiểm tra một lần tự remove. Không chạy application server,
không DB/provider connections. 71 modules khớp source, **70 package versions** so API cũ
không khác; local source kiểm lại chưa thay đổi trong lúc build.

Recreate lúc khoảng **11:23:25 +07:00**:

```powershell
docker compose -p shopquery-ai -f compose.yaml -f .env.compose-ui.yaml -f .env.join-v1.yaml up -d --no-deps --no-build api
```

Compose chỉ recreate/start API. Có warning volume cũ `shopquery-ai_postgres_data` không
khớp volume active và được **left untouched**. Không làm theo gợi ý remove volume; không
delete/prune hoặc tác động volume active `shopquery-ai_postgres_auth_20261019`.

### G3. Before/after

| Hạng mục | Trước | Sau |
|---|---|---|
| API image ID | sha256:09fb41dc043ee14b… | sha256:1a96e048886281ff… |
| API container ID | ea2a3f3688ea | **fd62fc397a91** |
| Web container ID | 2af67d527f2e | **Không đổi** |
| DB container ID | 511c4f5aaccc | **Không đổi** |
| DB volume | shopquery-ai_postgres_auth_20261019 | **Không đổi** |
| Python source manifest | 715c5b01327e970c… | **bd500b4c2a56631f…**, khớp source đã test |
| 8001 direct health | HTTP 200, status ok | **HTTP 200, status ok** |
| 8080 proxy health | HTTP 200, status ok | **HTTP 200, status ok** |
| API/web/DB health | healthy / healthy / healthy | **healthy / healthy / healthy** |
| JOIN / gates / models / fallback / quotas | Snapshot D1 | **Không đổi**, full environment comparison PASS |
| Rollback image | Current image verified; new tag chưa tồn tại | **Đã bảo vệ đúng image cũ bằng tag mới** |

Full API image mới:
`sha256:1a96e048886281ff5d7742e21cb1374e2e88571556c769bcdad3b29990b36417`.

Full API container mới:
`fd62fc397a91153f36bf9a3bc378283d0664e1754b2993a86d2b6433b664e67f`.

Full source manifest sau deploy:
`bd500b4c2a56631f91751a086c5e092178f4fc9c6a642b7d5acada2e66a1e238`.

Postflight hoàn tất **11:24:25 +07:00**: 71/71 runtime module hashes khớp local snapshot,
0 source mismatches; bốn patched modules đã nằm trong API mới. Full environment digest
trước/sau bằng nhau; merged Compose/runtime 0 mismatch. Không đổi OAuth/provider secrets,
model/gates/fallback/quotas. JOIN=true; Knowledge=knowledge; Gemini=gemini-3.5-flash-lite;
embedding=gemini-embedding-2/768; fallback=false.

Nginx proxy 8080 OK ngay sau recreate và khi postflight; **không có 502 quan sát được**,
không có lý do reload. Không sửa/reload/rebuild/recreate web. Hai test containers trên
15437/15438 giữ trạng thái exited, không start/recreate chúng.

### G4. Integrity scope / không được suy rộng

Không chạy migrations, schema setup, restore, seed, re-ingest, upload hoặc queries lên bảng
business/accounts/sessions/conversations. Main DB chỉ được đọc current_database và hai
operational aggregate counts cần preflight; không protected data fingerprints. App startup
lifespan đã review: Guest cleanup task, không migration/seed lúc boot. Không tự rollback DB.

DB container/volume và source security guards giữ nguyên; **không có fresh business-data
fingerprint comparison** nên không tuyên bố đã chứng minh toàn DB bất biến trước mọi thao tác
đồng thời của người dùng. Không tạo Google session giả, không đọc/export cookies/tokens.

Guest contexts/files/history RAM không được giữ qua recreate; thao tác restart làm mất state
Guest như đã thông báo. Không xóa durable user datasets/chat history. Không hứa Google login
UI còn hiệu lực nếu chưa kiểm qua session của người dùng.

### G5. Recovery chuẩn bị, KHÔNG THỰC HIỆN

Chưa được phép tự rollback main. Nếu cần, xin duyệt rồi dùng current-baseline immutable
image đã bảo vệ ở G2. Chuẩn bị override riêng với nội dung sau, không đổi `.env`/base Compose:

```yaml
services:
  api:
    image: sha256:09fb41dc043ee14bf52de6baf9d0a611f28287c87e599632e03b2f7aeaabf9d7
```

Chỉ sau approval và xác minh image/tag identity, thêm override sau ba files hiện hành:

```powershell
docker compose -p shopquery-ai -f compose.yaml -f .env.compose-ui.yaml -f .env.join-v1.yaml -f '<approved-rollback-override.yaml>' up -d --no-deps --no-build api
```

Sau rollback phải lặp health/config/old-module manifest và kiểm proxy; chỉ test/reload Nginx
nếu xác minh upstream stale. Không restore DB/volumes. Lệnh trên là recovery plan, chưa chạy.

### G6. Kết luận và bước live tiếp theo

**DEPLOYED — LIVE NOT VERIFIED.** Bản sửa đã phục vụ tại 8080 qua API mới; không dùng health
PASS để tuyên bố SQL/JOIN/Hybrid/model accuracy đã PASS. Lượt deployment có **0 generation,
0 embedding, 0 live chat probes**. Không commit/push hoặc CI SHA mới; dirty files được giữ.

Chờ duyệt riêng Batch A: **K2, K3, G3**, tối đa **3 chats / 9 logical generation stages /
0 embeddings**. Nếu A đạt, chờ duyệt hoặc cấp trước có điều kiện cho Batch B: **KH, GH**,
tối đa **2 chats / 8 logical generation stages / 2 query embeddings**. SDK retries có thể
tăng HTTP requests. Mọi main synthetic metadata/oracle/fingerprint access và raw synthetic
SqlDraft private capture phải có scope được duyệt riêng; không tái sử dụng budget Gate D.

## H. Post-deployment Docker cleanup and integrity audit

Ngày 21/10/2026, theo phê duyệt riêng `7dc3757e-8605-4448-a3a1-88009cb63cca`:
chỉ xóa hai test containers nếu Gates A/B/C đạt. Không cấp quyền deploy/recreate main,
xóa images/volumes/networks/backup, provider calls hoặc private data audit.

### H1. Main runtime trước/sau

Preflight snapshot **11:36:34 +07:00**; xóa lúc **11:38:01 +07:00**; postflight snapshot
**11:38:40 +07:00**, rồi kiểm lại kết nối read-only của API đến PostgreSQL.

| Thành phần | Trước cleanup | Sau cleanup | Kết quả |
|---|---|---|---|
| Web ID | 2af67d527f2e | 2af67d527f2e | Không đổi, healthy |
| API ID | fd62fc397a91 | fd62fc397a91 | Không đổi, healthy |
| DB ID | 511c4f5aaccc | 511c4f5aaccc | Không đổi, healthy |
| API image | sha256:1a96e048886281ff… | Cùng immutable ID | PASS |
| Source manifest | bd500b4c2a56631f… | Cùng SHA-256, 71/71 modules | PASS |
| Health 8080/8001 | HTTP 200, status ok / ok | HTTP 200, status ok / ok | PASS |
| Main volume | shopquery-ai_postgres_auth_20261019 | Tồn tại, mount trên đúng DB | PASS |
| Archived volume | shopquery-ai_postgres_data tồn tại | Vẫn tồn tại | PASS |
| Rollback tag | rollback-pre-textsql-20261021 -> sha256:09fb41dc043ee14b… | Cùng tag/image | PASS |

Full source manifest:
`bd500b4c2a56631f91751a086c5e092178f4fc9c6a642b7d5acada2e66a1e238`.
Full API image:
`sha256:1a96e048886281ff5d7742e21cb1374e2e88571556c769bcdad3b29990b36417`.
Full protected rollback image:
`sha256:09fb41dc043ee14bf52de6baf9d0a611f28287c87e599632e03b2f7aeaabf9d7`.
Full main container IDs giữ đúng phần G; snapshot fields IDs/images/health/ports/networks/
mounts/StartedAt/RestartCount trước và sau **khớp toàn bộ**. RestartCount cả ba bằng 0.
Web và DB images vẫn 5ca6e17125f1… / 137f044b0efe…; không rebuild hoặc restart service.

### H2. Ports, dependencies, network và DB connection

- Web `127.0.0.1:8080->80`, API `127.0.0.1:8001->8000`, DB `127.0.0.1:15432->5432`
  không đổi. Main dùng network `shopquery-ai_backend` (ID 38e1562d2e1a…).
- Web `getent hosts api` resolve **172.20.0.2**, đúng API IP. Nginx config có
  `proxy_pass http://api:8000`; `nginx -t` PASS, không reload/config edit.
- Main API hai database URL được kiểm **chỉ host/port/database**, không xuất credentials:
  đều `db:5432/shopquery`, không cổng test 15437/15438.
- Connection thật qua `get_readonly_engine()` trong API, transaction READ ONLY,
  statement_timeout=3s: `current_database()=shopquery`, server **172.20.0.3:5432**,
  transaction_read_only=on. `db` DNS cũng 172.20.0.3, đúng main DB IP. Kết quả trước/sau khớp.
- Merged Compose chỉ có db/api/web; dependency db=[], api=[db], web=[api]. Không test service.
  Main không có Links/VolumesFrom hoặc shared-container network reference đến hai targets.
- PostgreSQL mount main named volume đúng; bootstrap SQL bind read-only giữ nguyên. Archived
  volume không phải data mount active. Không chạy SQL bootstrap, migrate, seed hoặc restore.

### H3. Source và cấu hình an toàn

71 runtime Python modules so cùng LF-normalized SHA-256 method với local; 0 mismatches và
đúng manifest deployed. Bốn patched files (`join_policy.py`, `validator.py`, `context.py`,
`generator.py`) vẫn trong runtime, không có local patch mới cần sync/redeploy.

Merged Compose/runtime environment so trong process: 0 mismatches; environment digest
trước/sau và deployment bằng nhau. Chỉ xuất allowlisted settings, không dump environment,
endpoint, credentials, OAuth secret, email allowlist hoặc cookies.

JOIN=true; default=inetcloud-knowledge; Knowledge=knowledge; Gemini=gemini-3.5-flash-lite;
embedding=gemini-embedding-2/768; fallback=false; provider data gate=true; Guest enabled/AI=true.
Knowledge endpoint và Gemini key có cấu hình (boolean presence check, không giá trị).
Gemini timeout/attempts 30000ms/3, Knowledge 60s/1; beta chat 30/user/hour, upload 60/hour,
concurrency 1/user và 4/system, Guest 5 questions/session, timeout 120s, concurrency 2;
toàn bộ quota keys khác trong allowlist cũng không đổi.

### H4. Hai test containers: identity và điều kiện xóa

| Container | Identity verified | Mounts safe | Removed | Reason |
|---|---|---|---|---|
| 15437, shopquery-ai-join-final-test | Full ID 682e6264b33a…, label shopquery.test=gemini-join-final | Mounts=[], tmpfs-only data | Có | Exited(0), không dependency, không evidence duy nhất |
| 15438, shopquery-ai-reliability-research | Full ID 9eaf77a22e7d…, label shopquery.test=reliability-investigation-20261021 | Mounts=[], tmpfs-only data | Có | Exited(0), không dependency, không evidence duy nhất |

Full immutable IDs đã resolve và kiểm lại **ngay trước** `docker rm`:

```text
682e6264b33af6c522f3b3b367c981476301877bda6c2e4d6b8df5caf9d34862
9eaf77a22e7df62d8be29787c9339c3b1b1197b72450b81b28c811b35f551d1f
```

Chi tiết independent inspect của từng target:

- 15437 tạo 20/10 03:25:26Z, last start 21/10 01:52:43Z, stopped 02:20:28Z.
  Host port loopback15437, tmpfs `/var/lib/postgresql/data` với
  `rw,noexec,nosuid,size=768m`.
- 15438 tạo 21/10 03:35:57Z, last start 03:59:07Z, stopped 04:12:34Z.
  Host port loopback15438, tmpfs `/var/lib/postgresql/data`.
- Cả hai dùng `pgvector/pgvector:0.8.1-pg17-trixie`, immutable image 137f044b0efe…
  (image chung main DB vẫn giữ); State=exited, ExitCode=0, PID=0, không active exec.
- Không named volume, không bind mount, không main/archived volume; không Compose project
  label, Links hoặc VolumesFrom. Network bridge, không chung main backend network.
- Đã kiểm Docker container-sharing references của các containers khác trước xóa: không
  target nào được tham chiếu qua Links, VolumesFrom hoặc network_mode container-sharing.
- Không thấy host Python pytest process đang chạy. Không start/stop test target để inspect.
- `docker diff` mỗi container chỉ có `C /run`, `C /run/postgresql`; không có thư mục
  export/evidence/data khác trong writable layer cần giữ. PostgreSQL data là tmpfs dùng một lần.
- Evidence ngoài Docker vẫn tồn tại: private three-table live report,
  `live-gate-d-20261021/oracle.json` và source regression fixtures/tests. Không xóa/sửa backup.

Lệnh thực thi duy nhất để xóa:

```powershell
docker rm 682e6264b33af6c522f3b3b367c981476301877bda6c2e4d6b8df5caf9d34862 9eaf77a22e7df62d8be29787c9339c3b1b1197b72450b81b28c811b35f551d1f
```

Không force, không volumes flag, không wildcard/label selection, không prune/down. Cả hai
IDs trả thành công và không còn trong full `docker ps -a` inventory.

Container metadata/logs cũ không thể khôi phục thành cùng immutable ID sau `rm`. Có thể
tạo lại test environment bằng image còn giữ và fixtures/scripts; không mất dữ liệu người dùng.
Không coi container tmpfs là backup: PostgreSQL tmpfs data đã disposable/lost qua lần stop
trước đó, không có durable dataset cần chuyển đi trong lượt cleanup này.

### H5. Kiểm kê host và security/integrity scope

| Tài nguyên | Trước | Sau | Đối chiếu exact sets |
|---|---:|---:|---|
| Containers toàn host | 19 | 17 | Chỉ đúng hai full IDs bị xóa; không thêm container |
| Image IDs | 49 | 49 | Không đổi |
| Named volumes | 28 | 28 | Không đổi |
| Networks | 7 | 7 | Không đổi |

Không tác động dự án Docker khác; chỉ đọc metadata dependency/inventory cần kiểm tra.
Không xóa main/archived volumes, images, networks, rollback tags hoặc backups. Không
recreate/restart main containers. Không sửa source/config/schema/business data/relationships/
embeddings/migration ledger; không deploy hoặc rollback. Không gọi chat API, generation,
embedding, upload hoặc tự đăng nhập. Không xuất secrets. Không commit/push.

Main SQL trong audit chỉ đọc metadata kết nối/transaction; **không đọc raw customer rows,
accounts, sessions hoặc private history**. Không có protected business-data fingerprint
comparison trong scope này. Vì vậy volume identity + health **không chứng minh byte-for-byte
toàn bộ database bất biến**; không gán operational changes đồng thời của người dùng là lỗi.
Synthetic workspace13 metadata chưa xác minh mới vì quyền đọc đó vẫn cần scope riêng.

Một lệnh postflight ban đầu bị lỗi quoting Python CLI trước khi query chạy; đã chạy lại
đúng invocation, read-only DB connection PASS. Không phải application/DB regression.
Không sửa source nên không chạy lại full unit/integration/frontend; kết quả tests §B là
baseline của chính manifest đang chạy. `git diff --check` cuối PASS.

### H6. Final status và live readiness

**DOCKER CLEANUP COMPLETE — MAIN STACK HEALTHY — DEPLOYED — LIVE NOT VERIFIED**.

API source mới vẫn phục vụ 8080, JOIN bật, cấu hình hai providers có mặt, source call flow
khớp bản đã kiểm thử; DB kết nối đúng main, Nginx proxy OK. Main không cần hai PostgreSQL
test containers vừa xóa. Đây là readiness kỹ thuật, không nghiệm thu chất lượng model.

Chờ duyệt riêng **Batch A: K2/K3/G3**, tối đa **3 chats / 9 logical generation stages /
0 embeddings**. **Batch B: KH/GH**, tối đa **2 chats / 8 logical generation stages /
2 query embeddings**, chỉ sau A đạt và có phê duyệt. Chốt riêng quyền synthetic13 metadata/
oracle và private synthetic draft evidence nếu cần. Lượt cleanup có **0 live probes,
0 generation, 0 embedding**; không tái sử dụng ngân sách Gate D.
