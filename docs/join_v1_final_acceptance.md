# JOIN v1 — bàn giao local 8080, 20/10/2026

## Kết quả và giới hạn

- JOIN **ON** trong API runtime, 8080 health OK, web/API/DB healthy.
- Authenticated Google UI: **NOT VERIFIED**. Người dùng báo Chrome từ chối trình
  duyệt không an toàn; không bypass Google, không tạo session giả/xuất cookie.
  Auth A/B, CSRF và owner isolation bằng PostgreSQL integration: PASS.
- Guest UI thật desktop/mobile: **2/2 PASS** ở lượt deploy trước; giữ kết quả đã
  có, không chạy lại chỉ để lặp báo cáo. Test opt-in nằm ở
  `frontend/e2e/relationships-live.spec.ts`.
- SQL/RAG/Hybrid offline với hai model selections: PASS, fake gateways và
  PostgreSQL thật; không gọi provider trong automated offline tests.
- Live theo phê duyệt riêng: **Knowledge SQL/HYBRID PASS; Gemini SQL/HYBRID FAIL**.
  Không tuyên bố toàn bộ live JOIN đã nghiệm thu. Không đổi validator để ép pass.
- Không migration/rebuild/reset main lần nữa trong đợt finalize; local runtime
  vẫn chứa Hybrid local cũ, không đồng nhất hoàn toàn với source commit bên dưới.

## Live synthetic — đúng bốn câu hỏi đã duyệt

Chạy gateway thật qua `run_guest_chat`, PostgreSQL TEMP thật trong network main,
không qua HTTP chat 8080, không phải authenticated browser acceptance. Chỉ gửi hai
bảng giả students/payments (2/3 dòng) và một đoạn rules.md ngưỡng 40; không gửi
dữ liệu thật hoặc lịch sử tài khoản. Không persistent writes, không sửa workspace5.

Oracle PostgreSQL độc lập: An total **50.00**, fact_row_count **2**; Binh total
**0.00**, fact_row_count **1**, GROUP/ORDER theo tên. Theo rules.md: An đạt,
Binh chưa đạt. Chạy cùng câu hỏi cho hai lựa chọn model, không fallback.

| Model thực tế | SQL | Hybrid | Bằng chứng |
| --- | --- | --- | --- |
| iNetCloud `knowledge` | PASS, 5,27s | PASS, 8,49s | INNER fact→dimension, rows khớp oracle, giữ zero/Decimal; Hybrid dẫn đúng rules.md và kết luận đúng cả hai người |
| `gemini-3.5-flash-lite` | FAIL, 3,56s | FAIL, 2,78s | Trả UNSUPPORTED sau SQL generation: không tìm thấy relation khớp; rows=[], không tạo answer số hoặc nguồn giả |

Gemini không lỗi 503 trong lượt này. Thông báo xuất phát từ kiểm tra relation,
nhưng harness không lưu raw SqlDraft trước validator nên **chưa phân biệt chính
xác sai hướng hay sai khóa**; không suy đoán nguyên nhân hoặc sửa source thiếu
bằng chứng. Không gửi thêm câu hỏi ngoài bốn câu đã duyệt để thử lại.

Tổng **11 logical generation calls**, **2 logical embedding calls** (≤14/3 đã
duyệt). Cùng vector tài liệu được dùng lại trong RAM harness, không thêm production
cache. SDK retry/schema retry giữ nguyên; đây không phải bộ đếm HTTP/billing thực tế.
Provider gates/model/fallback/quotas/secrets không đổi. Evidence private:
`C:\Work\ShopQuery-Backups\join-v1-finalize-20261020-0120\live-acceptance.json`.

## Git scope và kiểm thử đúng snapshot

Source commit: `34701b384ce6c96a06de91078a2684041b3e07d2`.
Đã push fast-forward `origin/main`, không force. Snapshot xuất từ index ngoài
repository; hash **từng 45 staged file** khớp bản đã kiểm thử trước commit.
Không dùng git add .; không discard/stash các sửa Hybrid.

Inventory file/hunk được commit (prefix backend/app trừ nơi ghi rõ):

- `core/config.py`, `.env.example`, `compose.yaml`: default JOIN OFF, truyền flag.
- `database/models.py`, `database/join_migration.py`,
  `backend/scripts/migrate_relationships.py`: scoped FK/index, additive metadata,
  explicit migration; không auto-migrate startup.
- `datasets/relationships.py`, `datasets/relationship_repository.py`: explicit
  confirmation, revision/full-data checks, owner scope, execution guard.
- `datasets/context.py` **chỉ hunks JOIN**: approved relation/types/conditional SQL
  rules. Không stage routing_context và Hybrid routing separation cũ.
- `dependencies.py`, `guest/pipeline.py` **chỉ hunks JOIN**: scoped policies và
  TEMP mapping. Router trong snapshot vẫn dùng schema_context như baseline.
- `api/routes.py`, `api/relationship_routes.py`, `main.py`: runtime flag, scope và
  endpoints; `guest/relationship_routes.py`, `guest/routes.py`, `guest/store.py`,
  `guest/worker.py`: capability/RAM/quota/remapping/isolated full-data preview.
- `core/errors.py`, `routing/service.py`, `text_to_sql/generator.py`: fail-closed
  UNSUPPORTED/hướng dẫn khai báo, không tạo partial answer.
- `text_to_sql/join_policy.py`, `text_to_sql/validator.py`,
  `text_to_sql/pipeline.py`, `routing/hybrid.py`: exact approved INNER JOIN,
  restricted fact aggregates, execution guard và fact-grain grounding. Thay đổi
  HybridPipeline ở đây là JOIN grain mới, **không phải Hybrid routing cũ**.
- `backend/tests/test_auth_integration.py`: cập nhật tên dependency được guard.
  Tests mới: `test_relationships.py`, `test_relationships_integration.py`,
  `test_relationship_api_integration.py`, `test_guest_relationships.py`,
  `test_guest_relationships_integration.py`, `test_join_policy.py`,
  `test_join_golden_integration.py`, `test_join_migration_integration.py`.
- Frontend: `src/types.ts`, `src/api.ts`, `src/guest.ts`,
  `src/components/DatasetUploadDialog.tsx`, `GuestUploadDialog.tsx`,
  `RelationshipPanel.tsx`, `RelationshipPanel.test.tsx`, `src/styles.css`,
  `e2e/relationships-mock.spec.ts`, `e2e/relationships-live.spec.ts`, `package.json`.

Giữ **unstaged** Hybrid cũ trong đúng sáu file: datasets/context.py,
dependencies.py, guest/pipeline.py, routing/router.py,
backend/tests/test_guest_integration.py, backend/tests/test_workspace_prompts.py.
`test_sql_schema_audit.py` và manual login setup vẫn untracked, không gom commit.
Các file docs bị xóa sẵn trước finalize cũng không stage/restore. Hai báo cáo JOIN
untracked từ lượt trước không còn trên disk; dùng evidence private/kết quả đã ghi
trong bàn giao trước, không giả vờ đã đọc lại file còn tồn tại.
Đã đọc SQL hardening report từ Git HEAD vì bản working tree bị xóa.

Đúng staged snapshot, không có .env/Hybrid chưa commit:

- Ruff PASS; **141 unit/regression PASS** (JOIN, alias, workspace prompt baseline,
  SQL pipeline và routing/Hybrid).
- **80 PostgreSQL/Auth tests PASS**: relationship lifecycle/isolation/CSRF,
  Guest remapping SQL/RAG/Hybrid cả hai models, five-domain golden oracle,
  Decimal/NULL/zero/Vietnam month boundaries. DB disposable riêng, không main.
- Frontend lint/typecheck/build PASS; **3 component + 4 browser mock PASS**,
  Auth/Guest ở desktop1440/mobile390.
- Không lặp full555/63/95 ở local. GitHub CI chạy đầy đủ trên đúng commit mới.

## Docker và bảo vệ dữ liệu

- ShopQuery main **3→3 containers**, đều giữ nguyên IDs/healthy; toàn host **17→17**
  sau khi loại test tạm của đợt này. Không tác động 14 containers dự án khác.
- Xóa đúng test tmpfs `1a7cccae894a129dba0335a4ca0960964d7e245c3f44e41ed29b901f05dd115d`
  sau tests, đã xác minh label `shopquery.test=join-v1-final-snapshot` và không có
  volume/bind. Database giả lập trong tmpfs bị loại bỏ, tái tạo được từ fixtures.
- One-shot live check dùng --rm, không còn container. Không còn container thử
  nghiệm JOIN cần dọn. Không có network thử nghiệm riêng tồn dư.
- Xóa hai candidate không có container dùng: `shopquery-ai-api:join-v1-check`
  ID `f9d53d672c5d`, `shopquery-ai-web:join-v1-check` ID `6775e314e61c`.
  Không cần cho rollback; giữ image main và hai recovery tags pre-join-20261020.
  Candidate có thể build lại từ source; không xóa bất kỳ volume nào.
- DB exact ID `511c4f5aacccd1ac42261aaa2a7173ae40c5c5e3aa673bb4898d988a8206a3c8`,
  database shopquery, volume `shopquery-ai_postgres_auth_20261019` không đổi.
  Archived volume `shopquery-ai_postgres_data` vẫn còn. DB15432/API8001/web8080.
- Workspace5 còn hai bảng/một confirmed relation; accounts/history không reset.
  Chỉ đọc schema marker trong đợt này, không chạy lại migration main.
- Fingerprints sau live/cleanup: 21 bảng business/auth/history gốc khớp baseline
  (loại đúng hàng synthetic workspace5), orphan references=0; reader/Guest vẫn
  không có quyền metadata. Hai bảng vận hành quota/lease có lifecycle riêng.
- Backup `C:\Work\ShopQuery-Backups\join-v1-20261020-0047\main.dump` còn nguyên:
  **114902 bytes**, SHA256
  `A9B458A5EE1C21966F9407E659075D2EADF6E071B4E244B9E07A2C9F18078138`.
  Backup 00:34 và roles/evidence cũng giữ nguyên, không đưa vào Git.

Runtime dùng actual Compose files `compose.yaml`, `.env.compose-ui.yaml`,
`.env.join-v1.yaml` (hai local overrides ignored, không commit).
Tắt khẩn cấp: chỉ đổi flag trong override JOIN thành false rồi chạy
`docker compose -f compose.yaml -f .env.compose-ui.yaml -f .env.join-v1.yaml up -d --no-deps api`.
Flag OFF **không rollback DDL**; không tự restore đè main hoặc xóa metadata.

## CI và việc còn lại

CI source: [run 39301794070](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39301794070),
đúng SHA `34701b384ce6c96a06de91078a2684041b3e07d2`: **completed/success**,
cả Backend quality, PostgreSQL integration và Frontend quality **success**.
Backend Ruff + **382 unit tests**, PostgreSQL **161 integration tests**, Frontend
lint/typecheck/build + **63 unit/95 browser tests** PASS. Tổng backend offline
**543** cho snapshot này; không đồng nhất với 555 ở working tree có audit/Hybrid
chưa commit. Không sửa workflow hoặc loại security tests để đạt CI.

Báo cáo này commit riêng sau source CI, không trộn các docs deletion/Hybrid cũ;
CI của documentation-only HEAD được kiểm tra và báo đúng SHA trong trả lời bàn giao,
không dùng CI source cũ để tự nhận CI cho HEAD mới.

CI `b8304ae` ([run 39302498473](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39302498473))
có Backend/PostgreSQL PASS nhưng Frontend **94/95 UI PASS, 1 timeout** ở test
Guest provider gate off/tablet768. Trace chứng minh helper `openUploads` gọi
`isVisible()` trước khi auth bootstrap render header: false khiến bỏ qua mở menu;
sau đó click nút sidebar ngoài viewport đến timeout. Đây là race trong helper,
không phải provider gate/JOIN bị lỗi. Sửa duy nhất test helper đợi `.chat-header`
visible, thêm regression auth response được giữ lại rồi release có kiểm soát.
Không force click, sleep, tăng timeout, bỏ assertion hoặc sửa production code.
Regression mới tái hiện timeout với helper cũ trên tablet; helper đã sửa đạt
**18/18 targeted runs** (hai test × desktop/tablet/mobile × ba lần), lint/typecheck PASS.
CI follow-up đúng SHA được kiểm tra trước trả lời bàn giao, không rerun mù để che lỗi.

Hai giới hạn nghiệm thu còn lại: Google UI chưa xác minh và Gemini JOIN live chưa
đạt. Không có bằng chứng yêu cầu nới SQL policy hoặc đổi kiến trúc/model. Không VPS,
Langfuse, framework, repair loop hay migration mới trong đợt này.
