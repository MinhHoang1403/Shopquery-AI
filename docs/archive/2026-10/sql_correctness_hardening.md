> HISTORICAL snapshot. Current status: [V2 acceptance](../../v2_final_acceptance.md).

# SQL correctness hardening — 19/10/2026

Báo cáo này cập nhật trạng thái ba findings trong audit trước cho code/import mới;
không coi dữ liệu và response history cũ đã được sửa theo.

## A. Baseline và phân tách working tree

- Baseline local và `origin/main` trước sửa: `b5974eb33dc43ce94855cf8bd597f94e1314453f`.
- Đã đọc `AGENTS.md`, báo cáo `sql_reliability_observability_review.md`, code và runtime.
- Các sửa Hybrid có sẵn tại `datasets/context.py`, `dependencies.py`, `guest/pipeline.py`,
  `routing/router.py`, `test_workspace_prompts.py` và một assertion trong
  `test_guest_integration.py` được giữ nguyên, **không đưa vào commit mới**.
- `test_guest_integration.py` chỉ stage hunk đổi NUMERIC result `300` thành `"300"`;
  assertion router của lượt trước vẫn unstaged. Không ghi đè hay discard source cũ.
- Report/test audit cũ và `live_8080_recheck.md` vẫn ở working tree, không gom vào commit.
- Trước commit, xuất riêng Git index thành snapshot ngoài repo, xác minh Python import
  đúng snapshot; Ruff đạt và **442 test backend không-live đạt** trên DB tạm sạch.
  Do đó bản đã commit không phụ thuộc các sửa Hybrid còn treo trong working tree.

## B. Timestamp: nguyên nhân, contract, implementation

Lỗi cũ: parser giữ datetime aware nhưng mapping SQLAlchemy tạo TIMESTAMP không timezone.
Writer UTC chuyển instant thành wall time UTC trước khi lưu, làm lệch ngày/tháng Việt Nam.

Contract áp dụng **import mới**, dùng chung cho authenticated và Guest:

| Input không NULL trong một cột | Metadata / PostgreSQL | Hành vi |
| --- | --- | --- |
| ISO DATE / native XLSX date | DATE / DATE | Không thêm giờ hoặc offset |
| Datetime không offset | TIMESTAMP / timestamp without time zone | Giữ wall time, không gán timezone |
| Datetime có offset, kể cả Z | TIMESTAMPTZ / timestamp with time zone | Giữ instant; không cam kết lưu lại offset gốc |
| Trộn aware/naive hoặc DATE/datetime | UploadValidationError | Nêu tên cột, yêu cầu thống nhất kiểu; API 422 |

Các offset +07, Z và -04 trong cùng cột **được phép** vì tất cả đều aware, không cần
đoán timezone. NULL không làm đổi contract. XLSX native datetime không mang timezone;
muốn nhập offset phải dùng ô text ISO. Ngày không hợp lệ có lỗi upload gắn tên cột.

Điểm sửa:

- `datasets/parser.py`: `_infer_type`, `_parse_datetime`, `_build_columns`, `_convert_value`.
  Infer awareness, từ chối kiểu thời gian mâu thuẫn, kiểm tra conversion khớp metadata.
- `datasets/repository.py:SQL_TYPES`: thêm `TIMESTAMPTZ` bằng `TIMESTAMP(timezone=True)`.
  Giữ nguyên mapping TIMESTAMP cũ. Guest TEMP tables dùng cùng mapping nên không cần
  thay quyền SQL, schema context builder hoặc thêm nhánh Guest riêng.
- Context tự ghi `instant TIMESTAMPTZ` từ ColumnSpec. Prompt generator và executor đã có
  contract `Asia/Ho_Chi_Minh`, literal biên +07 và range `>= start AND < end`, giữ nguyên.

PostgreSQL phân biệt timestamp có/không timezone; TIMESTAMPTZ giữ instant và hiển thị
theo session timezone. [Tài liệu PostgreSQL 17](https://www.postgresql.org/docs/17/datatype-datetime.html),
[SQLAlchemy TIMESTAMP](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#sqlalchemy.dialects.postgresql.TIMESTAMP).

## C. Decimal: contract end-to-end

Trước sửa đã đọc API models, frontend types, ResultTable, SQL grounding và Hybrid prompt.
UI hiện dùng `String(value)`, không ép cell sang Number/parseFloat; response trước đó cho
phép string nhưng executor vẫn làm mất precision qua float.

- Mọi Python Decimal từ PostgreSQL NUMERIC → `format(value, "f")`, JSON **string**,
  giữ chữ số/scale, không làm tròn hay đổi đơn vị. Áp dụng cả Decimal nguyên và zero.
- INTEGER/COUNT vẫn JSON integer; NULL vẫn JSON null. SUM(BIGINT) của PostgreSQL trả
  NUMERIC nên cũng là string, ví dụ `"300"`; không phụ thuộc số có phần lẻ hay không.
- `_json_safe` dùng cho SQL results và persisted dataset preview; parser `_json_value`
  cũng giữ Decimal lossless. Preview CSV vốn giữ nguyên text của file.
- API `ChatResponse.rows` và `DatasetPreviewResponse.rows` dùng JsonValue, có mô tả
  contract. Frontend có ResultRow contract; ResultTable vẫn render nguyên giá trị.
- SQL và Hybrid grounding prompts giải thích decimal strings, zero/null và yêu cầu
  giữ nguyên chữ số, không scientific notation/float conversion. Không tự tính thêm
  số liệu hoặc dùng LLM để sửa dữ liệu.
- Test DB → executor → HTTP → conversation metadata và restore giữ nguyên string.
  Unit test kiểm tra JSON đưa vào grounding và frontend render sau JSON round-trip.

Giới hạn: không khôi phục số đã mất precision trong lịch sử cũ hoặc trong numeric cell
Excel trước khi upload. AVG có thể được PostgreSQL làm tròn theo quy tắc NUMERIC;
serializer giữ nguyên kết quả PostgreSQL, không hứa biểu diễn phân số vô hạn chính xác.
BIGINT ngoài miền số nguyên an toàn JavaScript vẫn là rủi ro riêng của contract INTEGER,
không được tự đổi trong đợt sửa NUMERIC này. Prompt không phải bằng chứng LLM luôn tuân thủ.

## D. Validator alias hardening

`SqlValidator._validate_columns` không còn bỏ qua mọi cột trùng tên output alias.

- Cột trong SELECT/WHERE/HAVING và biểu thức phải được kiểm tra với schema thật.
- Alias chỉ resolve ở standalone ORDER BY/GROUP BY. ORDER BY ưu tiên output name;
  GROUP BY ưu tiên input name. Alias không cấp quyền cho cột nguồn chưa tồn tại.
- Alias output trùng tên nhưng khác expression bị từ chối khi được tham chiếu mơ hồ;
  hai output cùng expression vẫn được phép như PostgreSQL.
- Table alias phải duy nhất; alias che qualifier gốc. Unqualified column được đếm theo
  từng table binding, kể cả self-JOIN ở demo policy, không chỉ tên bảng vật lý duy nhất.
- Qualified column phải đúng binding/schema, không nhận prefix schema/catalog khác.
- Thêm chặn AST Window rõ ràng, phù hợp subset/prompt hiện tại; không mở quyền mới.
- `max_tables=1` và no-JOIN của uploaded/Guest không đổi. Demo joins vốn được cho phép
  theo schema demo vẫn qua các representative tests. CTE/subquery/DML/locks, function
  allowlist, read-only transaction, result cap và timeout giữ nguyên.

Đối chiếu quy tắc name resolution trong [PostgreSQL SELECT](https://www.postgresql.org/docs/17/sql-select.html).
Validator vẫn là bộ kiểm tra subset/allowlist, không phải bộ chứng minh mọi SQL có
semantics aggregate hợp lệ. PostgreSQL vẫn có thể từ chối các câu sai quy tắc grouping.

## E. Test trước/sau và PostgreSQL execution evidence

| Giai đoạn | Kết quả |
| --- | --- |
| Timestamp trước sửa | 12 fail, 2 pass trong regression mới |
| Timestamp sau sửa bước đầu | 45 pass parser/contract/schema audit; 6 pass PG timestamp/Guest |
| Decimal trước sửa | 8 fail, 3 pass trong regression mới |
| Decimal sau sửa | Unit/API/grounding đạt; DB/API/preview/history round-trip đạt |
| Alias trước sửa | 20 fail, 20 pass; sau sửa và thêm pipeline guard: 42 pass |
| Working tree backend offline cuối | 337 passed, 133 deselected |
| Working tree PostgreSQL integration | 117 passed, 351 deselected tại lần chạy đó |
| Staged snapshot không Hybrid cũ | Ruff đạt; 442 passed, 8 live deselected |
| Frontend | ESLint, TypeScript, build đạt; Vitest 60/60 |
| Playwright mock | 85/85, năm viewport |
| UI thật 8080, không auth mock | 4/4, desktop 1440 và mobile 390 |
| Docker build | API/web đạt; không thêm dependency |

PostgreSQL tests dùng container riêng `shopquery-ai-correctness-pg`, port 15435,
tmpfs, database tên `shopquery_test_correctness*`. Mỗi target được kiểm tra bằng
`require_test_database`; fixture schema setup chỉ chạy trong DB test, không trên main.
Container test đúng ID/label đã được dừng và xoá sau nghiệm thu; tmpfs chỉ chứa dữ liệu
giả lập không cần giữ. Không xoá volume hoặc container của stack chính/dự án khác.
Một lần chạy integration đầu có 9 assertion cũ đòi JSON number; đã cập nhật chính xác
theo contract NUMERIC string, không bỏ assertion về giá trị/NULL/COUNT/ownership.
Chạy lại suite trên DB tạm sạch đạt 117/117.

Evidence trong `test_sql_correctness_integration.py`:

- CSV/XLSX × writer UTC/Asia/Ho_Chi_Minh: persisted DATE/TIMESTAMP/TIMESTAMPTZ được
  kiểm tra qua information_schema và giá trị thật; instant so sánh aware datetime.
- Sáu mốc có +07/Z/-04 ở 30/9–1/10 và 31/12–1/1. Theo giờ Việt Nam, tháng 10 có
  COUNT=2, SUM=50; tháng 1 có COUNT=2, SUM=100 ở cả hai writer timezone.
- Guest TEMP CSV/XLSX có timestamp with time zone, instant đúng và COUNT tháng 1=2.
- SUM NUMERIC thật = `12345678901234567890.120000000000000000000002`; AVG đối chiếu
  trực tiếp raw Decimal PostgreSQL. COUNT=4, non-NULL=3; API/history/preview không mất số.
- Sáu positive alias queries thực thi thật, gồm ORDER/GROUP output/input-name collision
  và duplicate-identical aliases. Negative aliases bị chặn trước executor/answer gateway.

UI thật dùng Guest browser context mới, không đụng tab Google đang mở. Preview/upload
file giả lập, xác minh API metadata TIMESTAMPTZ, cell `12345678901234567890.12`, 422 cho
mixed aware/naive và file hợp lệ đã thêm không bị mất khi preview file lỗi.
Không gọi Knowledge/Gemini generation/embedding live trong lượt hardening; regression
pipeline dùng controlled gateways và PostgreSQL thật. Không coi mock là provider live.

## F. File/module thay đổi

- SQL production: `datasets/parser.py`, `datasets/repository.py`, `text_to_sql/executor.py`,
  `text_to_sql/pipeline.py`, `text_to_sql/validator.py`, `routing/hybrid.py`, `api/models.py`.
- Regression mới: `test_timestamp_contract.py`, `test_decimal_contract.py`,
  `test_sql_alias_validation.py`, `test_sql_correctness_integration.py`.
- Cập nhật kỳ vọng NUMERIC: `test_auth_integration.py`, `test_management_integration.py`,
  một hunk `test_guest_integration.py`; không sửa assertion bảo mật/rollback.
- Decimal UI contract/test: `frontend/src/types.ts`, `components/ResponseEvidence.tsx`,
  `components/ResultTable.test.tsx`, `e2e/sql-correctness-live.spec.ts`.
- UI commit riêng từ audit: `App.tsx`, `Sidebar.tsx`, `styles.css`, `Sidebar.test.tsx`,
  `e2e/auth-mock.spec.ts`, `e2e/guest-ui-live.spec.ts`. Bỏ login/hint footer trùng;
  giữ header login, Tệp tạm thời, AccountMenu; không redesign.
- Test audit cũ trong working tree được cập nhật TIMESTAMPTZ/lossless/alias expectations,
  không đưa vào commit để tránh gom đợt audit/Hybrid chưa review.

## G. Main database và bảo mật

Không reset, seed, migration, ALTER cột cũ, xoá volume hoặc sửa dữ liệu main.
Fingerprint read-only trước/sau khớp trên **17 bảng**: 10 bảng nghiệp vụ/history và 7 bảng
uploaded. Không xuất row contents; kiểm tra hash/count. Main vẫn 4 workspace, 7 bảng,
28 messages tại thời điểm inventory. Counter/quota Guest có thể tăng do thao tác UI hợp lệ;
không giả vờ mọi bảng vận hành đều bất biến.
Helper `legacy_fingerprints` bỏ qua field `owner_user_id` theo thiết kế có sẵn;
đây không phải pentest hoặc chứng minh toàn database/ownership bất biến chỉ bằng hash.

Không đổi OIDC/session/CSRF, owner checks, CRUD transaction/confirmation/cascade,
retention/history semantics, model selection, embedding, provider gate hoặc fallback.
117 integration gồm Guest/auth SQL/RAG/Hybrid, A/B isolation và rollback.
Không nâng đặc quyền LLM; không natural-language writes.

## H. Runtime 8080

Build API/web thành công, chỉ **API recreate**; web giữ container hiện có vì bundle runtime
không đổi, PostgreSQL không recreate. Không chạy setup/migration lúc API start.

- API: `sha256:8115b46586002b4daca835e37ebd6333f8f9c4d0d30d7f9fe6458829acbc5851`.
- Web: `sha256:ddb7648ba3abb74bc893e4c005f71e36c1e9507112394ed4bf1c05d14dcf99de`.
- DB: `sha256:137f044b0efe3d57f39b972b9b53641b1f2045b99d879e298bbf514a25787dcf`.
- Cả ba healthy; `http://127.0.0.1:8080/api/health` trả 200.
- Provider gate/Guest AI vẫn true; Knowledge default; Gemini `gemini-3.5-flash-lite`;
  embedding `gemini-embedding-2`; fallback false. So sánh trước/sau không đổi.
- API recreation làm mới RAM Guest theo lifecycle hiện tại, không xoá lịch sử tài khoản.
- Runtime API vẫn chứa các sửa Hybrid local đã tồn tại trước nhiệm vụ; không đồng nhất
  toàn runtime với clean Git HEAD. Commit snapshot/CI được kiểm tra riêng.
- Hash source (chuẩn hoá CRLF/LF) của bảy file production hardening trong API container
  khớp source local sau deploy.

## I. Legacy-data risks

Inventory metadata main read-only có **một cột timestamp without time zone**:
workspace ID 1 / dataset_table ID 1 / `order_date`. Không đọc email/identity hoặc kết luận
cột này chắc chắn sai. Metadata không cho biết input gốc từng có offset hay writer timezone.

Không thể phục hồi offset/instant đã mất chỉ từ wall time hiện có. Kế hoạch riêng nếu cần:
đối chiếu file gốc và contract từng cột, backup, thống kê biên tháng, thử trên clone DB,
duyệt migration có mapping rõ ràng hoặc re-import có xác nhận. Không dùng ALTER ...
AT TIME ZONE với giả định chung cho mọi dòng. History cũ không tự được tái tính/đổi kiểu.

Các rủi ro ngoài phạm vi: units/locale inference, 0/1 BOOLEAN, all-NULL TEXT,
context/parser budget, BIGINT/JS, lỗi provider và LLM-generated SQL không chính xác.
Không tuyên bố hệ thống không còn mọi lỗi chỉ từ các regression đạt.

## J. Commit/push/CI

- `3bd5cf6647e8013d74d67f6a58627cc6d8432899` — SQL correctness + tests/decimal UI contract.
- `945a55dfab24971828b0e5d02ed066c4310b46cc` — Guest sidebar cleanup + tests riêng.
- Đã push fast-forward lên `origin/main`, không force; không commit `.env`, credentials,
  dumps, raw fixtures, logs, cache hoặc thay đổi Hybrid chưa review.
- CI cho hai commit code: [GitHub Actions run 39278729274](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39278729274).
  Kiểm tra lúc 22:36 giờ Việt Nam: workflow và cả ba jobs vẫn **queued**, chưa có steps
  chạy. Chưa có kết luận CI pass/fail; không dùng kết quả local thay CI. Trạng thái mới
  hơn được báo riêng trong kết quả bàn giao nếu GitHub cấp runner sau thời điểm này.

## K. JOIN v1 readiness

Chưa triển khai JOIN, relationship schema/UI/migration, Langfuse/LangSmith hay VPS.
Ba fixes không làm metadata quan hệ trở nên đáng tin cậy; vẫn giữ `max_tables=1`.

Nếu duyệt lượt sau: tối đa hai bảng cùng authorized workspace, một quan hệ người dùng
xác nhận; backend-owned allowlist có table/revision/key/type/uniqueness/cardinality;
SQLGlot kiểm tra JOIN ON predicate; kiểm tra orphan/NULL/fan-out/grain/double counting;
Guest mapping capability → TEMP và authenticated owner isolation riêng; PostgreSQL
golden tests so COUNT/SUM trước/sau. Không suy đoán quan hệ từ tên cột hoặc tự nới validator.
