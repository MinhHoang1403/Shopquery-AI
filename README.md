# ShopQuery AI

[![CI](https://github.com/MinhHoang1403/Shopquery-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/MinhHoang1403/Shopquery-AI/actions/workflows/ci.yml)

Trợ lý phân tích bảng và tài liệu bằng FastAPI, React/TypeScript, PostgreSQL/pgvector.
Hỗ trợ SQL, RAG, Hybrid, Google OIDC, không gian cá nhân và Guest tạm thời.

**STAGE 2 PARTIAL — ACCEPTANCE BLOCKED.** 8080 đã chạy release API/Nginx với main DB,
Google login/history hoạt động, BGE tạm hoãn và dùng vector-only có sẵn. RAG thật của
Gemini/Knowledge đã đạt phạm vi policy fixture; SQL/Hybrid còn blocker. Paid gates
đã tắt sau bounded acceptance. PR#1 đã merge về main theo chỉ đạo consolidation; chưa tag hoặc tuyên bố V2 hoàn tất.
Nguồn trạng thái hiện tại: [nghiệm thu V2](docs/v2_final_acceptance.md).
Chi tiết QueryPlan/CUDA development: [báo cáo Giai đoạn 1](docs/archive/2026-10/stage1_implementation_report.md).
Các báo cáo trong `docs/archive/` chỉ phản ánh thời điểm lịch sử.

## Tài liệu hiện hành

- [Kiến trúc](docs/architecture.md) và [khả năng/giới hạn](docs/capabilities.md).
- [Development](docs/development.md), [kiểm thử](docs/testing.md).
- [Runtime/deployment](docs/deployment.md), [bảo mật](docs/security.md).
- [Authentication/migration](docs/authentication.md), [nguồn kỹ thuật](docs/technical_references.md).

## Development local

8080 hiện dành cho release đang hoạt động. Chỉ chạy các lệnh chuyển development
dưới đây khi chủ động có maintenance window; chúng thay API/Web sang DevDB.
Vận hành release thường ngày theo [runbook](docs/deployment.md), không bật hot reload.

Cần Docker Desktop/Compose hỗ trợ `!override`, PowerShell, Git, Python 3.11/uv;
Node 24 nếu chạy frontend tests native. Đọc [AGENTS.md](AGENTS.md) trước khi sửa source.

```powershell
cd backend
uv sync --locked --extra reranker
cd ..
./scripts/dev.ps1 -Build
./scripts/verify-runtime.ps1
```

Script chỉ vận hành `devdb`, `api`, `web`, project `shopquery-ai`, bằng `compose.yaml`
rồi `compose.dev.yaml`. Database development riêng; main database không phải sandbox.
BGE phải có sẵn ở snapshot xác minh; dùng `-ModelPath` nếu cache ở vị trí khác.
Không tải model tự động. Trước lần chuyển từ main, đọc [deployment](docs/deployment.md).

Mở [http://127.0.0.1:8080](http://127.0.0.1:8080). Banner Development phân biệt dữ liệu
thử nghiệm; tài khoản/lịch sử main vẫn ở volume main. Dev tắt AI trả phí và Google
credentials. Python bind mount + reload, React Vite HMR. Dependencies cần rebuild;
environment cần recreate API/web có kiểm soát. Không chạy base Compose một mình
trên máy đã có local overrides volume/port riêng.

```powershell
./scripts/test.ps1
./scripts/test.ps1 -Integration -Tests tests/test_hybrid_evidence_integration.py
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Integration chỉ dùng `shopquery_test_stage1` trên dev PostgreSQL cổng 15433.
Không reset main hoặc dùng provider keys. Benchmark/live acceptance thuộc Giai đoạn 2.
Không commit secrets, `.env`, weights, cache, logs hoặc dữ liệu người dùng.
Main là source chính; BGE/SQL/Hybrid chưa đạt không được ghi full acceptance hoặc tag V2.
