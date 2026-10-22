# Kiểm thử

Giai đoạn 1 chỉ offline regression/smoke, không benchmark 150 câu hoặc live AI.
Kết quả thực chạy nằm trong báo cáo Giai đoạn 1; test counts lịch sử không đại diện
source hiện tại.

```powershell
./scripts/test.ps1
./scripts/test.ps1 -Integration -Tests tests/test_hybrid_evidence_integration.py
cd backend
uv run --no-sync ruff check app scripts tests
cd ../frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
$env:SHOPQUERY_E2E_START_SERVER='1'
$env:SHOPQUERY_E2E_BASE_URL='http://127.0.0.1:5173'
npm run test:e2e
```

Script tạm đặt test database/provider settings/JOIN default rồi khôi phục environment.
Non-live tests chặn HTTPX real transports; mock transports/TestClient vẫn hoạt động.
Integration fixtures kiểm exact `SHOPQUERY_TEST_DATABASE_URL` và tên test/CI trước
DDL. Không dùng dev application DB hoặc main DB làm fixture target.

Test DB `shopquery_test_stage1` nằm trên devdb:15433, tạo cùng volume dev mới. Tests
có thể tạo/drop fixtures ở đó; không reset/re-ingest main hoặc xóa volumes.

CI: Ruff/unit, PostgreSQL service `shopquery_ci` + reader riêng, frontend quality/
mock browser. Draft PR vào main kích hoạt workflow; feature push đơn thuần không
chạy workflow hiện hữu. CI regression không phải Stage 2 live acceptance.

Targeted checks: plan IDs/binds/COUNT/JOIN/NULL/Decimal; local model load/cache/
ranking/scope/fallback; Hybrid evidence sequence, binding, decisions/citations;
auth/Guest isolation. Real-model smoke dùng synthetic text/local weights, không
chứng minh retrieval quality. Giai đoạn 2 cần independent holdout, comprehensive
benchmark/regression, retrieval quality/latency, live providers và release gates.

`test_plan_providers.py` đi qua real Knowledge/Gemini serializers với HTTP mock;
`test_plan_factory_integration.py` nối adapter → planner → compiler → PostgreSQL.
`test_plan_expressions_integration.py` kiểm arithmetic/calendar/OR/HAVING bằng oracle
độc lập. Fixed SQL adversarial fixtures dùng `sql_validation_fixtures.py` để kiểm
validator/execution/grounding; chúng không được tính là provider-planning proof.
`plan_fixtures.py` chỉ chuyển static regression SQL sang mocked PlanDecision, giữ
nguyên expected rows; helper này không được import từ production.
