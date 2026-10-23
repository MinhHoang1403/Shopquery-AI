# ShopQuery AI

[![CI](https://github.com/MinhHoang1403/Shopquery-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/MinhHoang1403/Shopquery-AI/actions/workflows/ci.yml)

Trợ lý phân tích bảng và tài liệu bằng FastAPI, React/TypeScript, PostgreSQL/pgvector.
Hỗ trợ SQL, RAG, Hybrid, Google OIDC, không gian cá nhân và Guest tạm thời.

**MVP demo chính: [http://127.0.0.1:8080](http://127.0.0.1:8080).** Một Compose project
`shopquery-ai` chạy API, Nginx Web và main PostgreSQL. Google login/history hoạt động;
operator đã bật Knowledge, Gemini và document embeddings cho tài khoản đăng nhập.
Giữ provider gate ON cho sử dụng thường ngày, cùng authentication, quota và rate limit.
Guest preview hoạt động; Guest AI chưa được duyệt. Fallback OFF là lựa chọn cấu hình.
SQL/RAG/Hybrid và follow-up đã có bằng chứng live trong phạm vi KPI synthetic;
không coi đó là bảo đảm cho mọi dữ liệu. Auto-JOIN hiện chỉ nhận tên khóa theo quy tắc
bảo thủ; khóa nghiệp vụ như `ma_tram`/`ma_goi` cần xác nhận quan hệ trong UI.
BGE tạm hoãn, retrieval dùng vector-only. Chưa tag hoặc tuyên bố nghiệm thu V2 đầy đủ.
Nguồn trạng thái hiện tại: [nghiệm thu V2](docs/v2_final_acceptance.md).
Chi tiết QueryPlan/CUDA development: [báo cáo Giai đoạn 1](docs/archive/2026-10/stage1_implementation_report.md).
Các báo cáo trong `docs/archive/` chỉ phản ánh thời điểm lịch sử.

## Tài liệu hiện hành

- [Kiến trúc](docs/architecture.md) và [khả năng/giới hạn](docs/capabilities.md).
- [Development](docs/development.md), [kiểm thử](docs/testing.md).
- [Runtime/deployment](docs/deployment.md), [bảo mật](docs/security.md).
- [Authentication/migration](docs/authentication.md), [nguồn kỹ thuật](docs/technical_references.md).

## Quy trình làm việc trên bản chính

GitHub `main` → local `main` → targeted tests → commit/push → build service thay đổi
→ pin digest trong private `.env.release` → deploy8080 → verify. Không cần build
image khi chỉ sửa docs hoặc dọn cache. Không tạo candidate/sandbox app stack.

Cần Docker Desktop/Compose hỗ trợ `!override`, PowerShell, Git, Python 3.11/uv;
Node 24 nếu chạy frontend tests native. Đọc [AGENTS.md](AGENTS.md) trước khi sửa source.

```powershell
git switch main
git pull --ff-only
# Sửa source; chọn tests đúng phần thay đổi, ví dụ:
./scripts/test.ps1 -Tests tests/test_plan_binding.py
git add -p
git commit -m "Describe the verified change"
git push origin main
# Build/pin riêng API hoặc Web theo docs/deployment.md, rồi:
./scripts/release.ps1 -Deploy -Service api
./scripts/release.ps1
Invoke-RestMethod http://127.0.0.1:8080/api/health
```

Private `.env`, `.env.release` và local overrides phải được giữ, không commit.
Không chạy base Compose một mình trên máy đã có overrides riêng. Chuyển API/Web
sang development là thao tác maintenance có gián đoạn; `scripts/dev.ps1` và Compose
dev vẫn là công cụ source, không phải deployment thứ hai cần chạy thường trực.
Test DB dùng volume riêng được giữ lại, chỉ khởi động khi integration test cần.

```powershell
./scripts/test.ps1 -Tests tests/test_plan_binding.py
# Chỉ khởi động isolated DevDB khi cần integration; không đổi API/Web8080:
docker compose -p shopquery-ai -f compose.yaml -f compose.dev.yaml up -d --no-deps --wait devdb
./scripts/test.ps1 -Integration -Tests tests/test_hybrid_evidence_integration.py
docker compose -p shopquery-ai -f compose.yaml -f compose.dev.yaml stop devdb
cd frontend
npm ci
npm run lint
npm run typecheck
npm test -- --run src/components/DatasetUploadDialog.test.tsx
npm run build
```

Integration chỉ dùng `shopquery_test_stage1` trên dev PostgreSQL cổng 15433.
Không reset main hoặc dùng provider keys. Benchmark/live acceptance thuộc Giai đoạn 2.
Không commit secrets, `.env`, weights, cache, logs hoặc dữ liệu người dùng.
Main là source chính; BGE/SQL/Hybrid chưa đạt không được ghi full acceptance hoặc tag V2.
