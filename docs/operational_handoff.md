# Bàn giao vận hành ShopQuery AI

Ngày 27/10/2026, múi giờ Asia/Saigon. Hệ thống chuyển sang sử dụng và bảo trì có
kiểm soát trong phạm vi đã nghiệm thu. Đợt này không sửa logic AI, migration hay dữ
liệu; không gọi provider, thêm stack hoặc thay đổi runtime.

Trạng thái bàn giao: **OPERATIONAL_HANDOFF_READY_WITH_LIMITATIONS**, chỉ có hiệu lực
khi CI đúng commit bàn giao đã PASS. Đối chiếu
[CI trên main](https://github.com/MinhHoang1403/Shopquery-AI/actions/workflows/ci.yml?query=branch%3Amain)
với `git rev-parse HEAD origin/main`; CI đang chạy không được coi là PASS.
Application source vẫn là `3fe4cc2`; thay đổi tài liệu/công cụ không cần rebuild API.
SHA và kết quả CI cuối cùng được trả trong biên bản bàn giao cho operator.

## A. Tổng kiểm kê

Baseline `24ab3c8` có 339 file được Git quản lý: backend 224, frontend 68, data 10,
docs 11, scripts 5, ops 5, GitHub workflows 2 và root/editor/config 14. Đã đọc toàn bộ
tracked text để kiểm kê; phân tích AST của 215 file Python, lập đồ thị import của
88 app modules và đối chiếu entrypoints/imports/config/tests của 38 frontend source files.

Rà soát các điều kiện bắt buộc ở planner/binder/compiler/coverage/executor,
auth/owner/context/persistence, retrieval/policy verification và telemetry, đối chiếu
regression tests và bằng chứng oracle đã có. Kiểm kê tĩnh không chứng minh mọi dòng
đều không có lỗi. Không đọc lại toàn bộ dependency trong node_modules/venv hoặc weights.

Giữ các thư mục .github, .vscode, backend, data, docs, frontend, infrastructure, ops,
scripts, AGENTS và root Compose/config. Phân loại theo từng file được lưu trong private
handoff inventory ngoài Git. Sau hợp nhất có 345 tracked files: thêm 5 file công cụ/
dependency/test và 2 tài liệu chức năng, bỏ 1 workflow lặp. Không commit generated fixtures.

## B. Cleanup và hợp nhất

| File/nhóm | Chức năng cũ | Bằng chứng dư thừa | Hành động | Kiểm chứng |
| --- | --- | --- | --- | --- |
| .github/workflows/observability.yml | 132 backend tests và 10 Compose checks | Full backend suite đã chứa toàn bộ subset; branch trigger đã kết thúc | Gộp Compose job vào CI chính, bỏ workflow lặp | Full CI và 10 Compose tests |
| docs/deployment.md | Runbook xen nhật ký preflight/cutover | Nhiều trạng thái và image refs đã bị thay thế | Giữ runbook hiện hành; liên kết lịch sử Git bất biến | Commands/source/images/links |
| docs/v2_final_acceptance.md | 1.520 dòng nhật ký nghiệm thu | Trùng root causes/scorecards ở audit và telemetry report | Giữ phạm vi, guards và giới hạn hiện hành; dẫn bản Git đầy đủ | Bằng chứng lịch sử được bảo toàn |
| docs/architecture_audit.md | Audit xen nhật ký runtime | Phần runtime/cleanup lặp deployment | Giữ root causes, so sánh A/B/C, oracle và security evidence | Git permalink giữ bản đầy đủ |
| README và docs khác | Một số mô tả dev/Guest/BGE/CI lỗi thời | Đối chiếu source và cấu hình hiệu lực | Viết lại README, sửa mô tả sai | Links/commands và runtime |
| .ruff_cache, backend caches | Metadata lint/pytest có thể tái tạo | Ignored; không phải source/dữ liệu | Xóa các đường dẫn cố định đã kiểm | Git diff và runtime |
| __pycache__ của app/tests/scripts | Python bytecode | Generated/ignored; không phải interpreter hoặc weights | Xóa 14 thư mục đã kiểm | Giữ .venv |
| frontend/dist, test-results, tsbuildinfo | Build và mock E2E outputs | Runtime phục vụ assets trong image; CI tái tạo được | Xóa artifacts local hết nhu cầu | Giữ node_modules/source |
| .env/private YAMLs, Compose dev/GPU | Cấu hình runtime/bảo trì | Labels và scripts còn tham chiếu | Giữ nguyên, kể cả identifier v1 | Strict verifier |
| Data/migrations/fixtures/models/volumes | Dữ liệu, phục hồi và regression | Runtime/DB/tests/build inputs còn cần | Giữ, không reset/re-embed/prune | Fingerprints và CI |

Đã xóa 357 generated files trong 20 đường dẫn cố định, tổng dung lượng logic
11.519.908 bytes (khoảng 10,99 MiB). Không đo chính xác dung lượng đĩa vật lý thu hồi.
Lệnh tổng hợp dùng duyệt đệ quy bị automatic policy chặn trước khi xóa; các thao tác
sau đó dùng danh sách đường dẫn cố định, đã kiểm phạm vi, Git tracking và reparse points.

Không xóa production module chỉ vì thiếu static reference. Giữ hai cặp helper giống
AST: `_safe_filename` 6 dòng trong table/document parsers và `_fail` 2 dòng ở hai policy
modules. Đây là helper cục bộ tại ranh giới kiểm tra; tách chúng chỉ để giảm vài dòng
sẽ thêm phụ thuộc mà chưa có lợi ích đủ rõ. Vòng import tĩnh ban đầu liên quan
TYPE_CHECKING/lazy imports, không phải bằng chứng vòng phụ thuộc khi khởi động.
Không thấy TODO/debug print/breakpoint qua tìm kiếm trong production Python/TypeScript.

## C. Logic và thuật toán

Các trạng thái PASS dưới đây áp dụng cho phạm vi hỗ trợ; không có nghĩa mọi schema
hoặc mọi câu hỏi đều được hỗ trợ.

| Phạm vi | Trạng thái | Căn cứ và giới hạn |
| --- | --- | --- |
| Structured SQL, WHERE/HAVING, filters/expressions | PASS | Pydantic/SDK contracts, compiler/security/golden và PostgreSQL oracle; không free-form SQL |
| N:1 JOIN, fact/grouping grain | PASS | Relationship IDs/revisions và keys đã kiểm; tối đa 3 bảng; từ chối fanout/joins ngoài phạm vi |
| COUNT, Decimal, NULL | PASS | COUNT provenance, NUMERIC chính xác và independent PostgreSQL oracle; không tự đổi NULL thành 0 |
| RAG, upload, chunks, citations | PASS | Parser/owner/citation regression và live baseline; đợt này không upload hoặc re-embed mới |
| Hybrid coverage và verification | PASS | Kiểm plan và compiled coverage trước execute; đủ entities, Decimal và quy tắc gắn nguồn |
| Context và persistence | PASS | Cùng owner/conversation/dataset; Hybrid premise phải verified; giữ lịch sử, chặn cross-owner |
| Authentication, CSRF, quotas | PASS | Offline/CI negative guards và session hiện hành; không thử fresh Google sign-in |
| Frontend, workspace, model, results | PASS | 85 component/unit và 125 mock E2E baseline; kiểm lại UI hiện hành |
| Knowledge reliability trên tập rộng | PARTIAL | 15 PASS/1 UNKNOWN; JOIN mới PASS không xóa UNKNOWN hoặc đủ để đổi mặc định |
| Langfuse | PARTIAL | 6 trace thật/234 observations, usage/privacy/fail-open; còn giới hạn retention/restore |
| BGE production và public hosting | UNKNOWN | Chưa nghiệm thu; không bật hoặc benchmark trong đợt này |
| Lời gọi provider mới | NOT_APPLICABLE | Không đổi logic AI; 0 generation, 0 query và 0 document embeddings |

[Nghiệm thu hệ thống](v2_final_acceptance.md), [bằng chứng kỹ thuật](architecture_audit.md)
và [telemetry](observability_acceptance.md) phân biệt mock, PostgreSQL, UI và provider.
Không dùng HTTP 200 làm bằng chứng câu trả lời đúng.

## D. Kiểm thử

- Baseline CI `24ab3c8`: 1.391 backend, 857 PostgreSQL integration, 85 frontend,
  125 browser mock và 10 Compose tests PASS. 132 telemetry tests đã nằm trong backend suite.
- Thêm 10 maintenance tests: PASS local với pinned dependencies và font thật; kiểm
  reproducibility của 6 file, parse PDF/DOCX và các ca từ chối input/overwrite.
- CI chính sau hợp nhất chạy backend/contracts/golden/security, PostgreSQL cô lập,
  frontend lint/typecheck/unit/build/E2E, 10 maintenance và 10 Compose tests.
  Không tạo local Docker test stack hoặc seed/reset main DB.
- Strict verifier kiểm 88 modules, source/image/env, health/readiness và dữ liệu.
  Dùng lại bằng chứng sáu câu AI đã nghiệm thu, không phát sinh generation mới.

## E. README

README đã viết lại phần giới thiệu, kiến trúc, chức năng và giới hạn, models,
prerequisites/env, thứ tự Compose, release/restart, bảo mật, kiểm thử và Langfuse.
Links nội bộ được kiểm; commands đối chiếu script/config thực. Template dùng Gemini
mặc định, attempts 1 và gate OFF cho cài mới; private runtime giữ gate ON.

## F. Ba script bảo trì

| File | Lỗi/giới hạn phát hiện | Phần sửa và kiểm thử | Trạng thái |
| --- | --- | --- | --- |
| generate_maintenance_demo.py | Output mặc định/ghi đè; dependencies/fonts ngầm; PDF invariant chưa truyền tới document | Output tuyệt đối và mới, exclusive creation, preflight; sửa ReportLab invariant; test tái tạo binary | Đưa vào Git cùng tests |
| maintenance_documents.py | Nội dung synthetic chưa được quản lý/lint | Giữ nội dung, format literals; parse PDF/DOCX và kiểm Unicode | Đưa vào Git cùng tests |
| maintenance_oracle.py | Default fixture không có; ghi đè JSON; input validation và giả định phân bố đích | Input/output rõ ràng; headers/keys/FK/Decimal/date/status/policy guards; tính lại CSV, bỏ assertions 15/15 và 100/group; perturbation test | Đưa vào Git cùng tests |

Dependency và tests riêng; không sửa backend dependencies/app/image hoặc nhập fixtures
vào production. Xem [cách dùng và giới hạn AVG](maintenance_tools.md).
56 câu đặc tả không đồng nghĩa 56 tests đã chạy. Test artifacts chỉ ở thư mục tạm do
test sở hữu và đã dọn.

## G. GitHub và branches

Trước: `main` và `codex/shopquery-mvp-v2-stage1`
(`c4329b2be5fd5928342b033bd9b1b0816f26a82f`). Branch cũ có merge-base chính là
`c4329b2`, 0 unique commits ngoài main và không có diff công việc độc lập. Không có PR
mở, worktree hoặc automation sử dụng. Đã xóa remote/local bằng phương pháp non-force,
fetch-prune và xác minh chỉ còn main/origin/main. Không rewrite history hoặc xóa tags.

Hai nhóm commit: maintenance utilities/tests/docs; README/CI/docs consolidation.
Push main và exact-head CI trước kết luận cuối. Chỉ stage danh sách file đã phân loại;
không stage secrets, private evidence hoặc caches. Working tree cuối không còn ba
script untracked. SHA/CI cuối được trả trong bàn giao để tránh tạo commit chỉ để ghi
lại SHA của chính tài liệu này.

## H. Docker và dữ liệu

| Thành phần | Source | Immutable image |
| --- | --- | --- |
| API | 3fe4cc2 | sha256:d8ad8aa5e3425b803bcec9c61a5e84dd5e950a2e07dc978d70c64d7c33dcbbb2 |
| Web | 02d5cbb | sha256:ae181335b61aa738f6b0b1c2c1c450fe46a5ba26b4688d5c294d541975696a58 |
| Main PostgreSQL | pgvector/pg17 | sha256:137f044b0efe3d57f39b972b9b53641b1f2045b99d879e298bbf514a25787dcf |

Giữ rollback API `52701da8`/source `8a2c6aa` và private config. Không build/redeploy;
sáu Langfuse image pins, năm volumes và networks giữ nguyên. Các digest đầy đủ, protected
volume và thứ tự Compose nằm trong [deployment runbook](deployment.md).

Giữ 49 images hiện có: active, rollback, images còn được containers tham chiếu và
images UNKNOWN của dự án khác. Đợt này không có obsolete candidate mới đủ bằng chứng
để xóa. Không dọn Docker cache/volumes, models hoặc thay Windows/WSL/security settings.

Fingerprint read-only tại đầu đợt gồm 33 data objects và 250 messages đến ID 324;
protected volume `shopquery-ai_postgres_auth_20261019`. Cuối đợt đối chiếu lại fingerprints,
containers, cấu hình, session và traces cũ. Phân biệt thay đổi hợp lệ do operator sử
dụng app với thay đổi từ nhiệm vụ; không tự rollback dữ liệu người dùng.

## I. GitHub cuối đợt

Chỉ bàn giao sau khi local main bằng origin/main, CI đúng HEAD đạt, working tree sạch
và không còn untracked files thuộc nhiệm vụ. Kết quả exact-head, số tests thực tế và
SHA cuối phải đọc từ CI/Git, không suy ra từ baseline.

## J. Giới hạn còn lại

Embedding token usage không được upstream trả; Knowledge cost UNKNOWN và Gemini cost
là ước tính. Retention tự động chưa được nghiệm thu trong edition Langfuse hiện tại;
**BACKUP_RESTORE_NOT_VERIFIED**. Tập đánh giá Knowledge rộng còn UNKNOWN; BGE chưa
đạt production acceptance. Public TLS, least-privilege, offsite restore và capacity
chưa nghiệm thu. Không phát hiện critical/high failure đã xác nhận trong phạm vi này;
không tuyên bố zero bugs hoặc enterprise-ready.
