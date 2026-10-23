> HISTORICAL snapshot; current status: [V2 acceptance](../../v2_final_acceptance.md).

# ShopQuery AI — current handoff

Tiếp tục từ [báo cáo Giai đoạn 1](stage1_implementation_report.md) và
[architecture](../../architecture.md). File này chỉ dẫn nơi tiếp nhận, không duy trì
một snapshot trạng thái thứ hai.

Baseline: `0062e47d75cc51646bf9b45409a12aa49288552e`.
Nhánh: `codex/shopquery-mvp-v2-stage1`; draft PR chưa được phép merge.

Không gọi live Knowledge/Gemini/embeddings, chạy benchmark 150 câu, migration/reset/
re-ingest main hoặc xóa volumes/backups trong Giai đoạn 1. Main/dev có database
riêng; kiểm source/config bằng `scripts/verify-runtime.ps1` trước khi làm với 8080.

Handoff cũ ở Git baseline; báo cáo cũ ở `docs/archive/`. Tệp người dùng có sẵn
`docs/hybrid_live_acceptance_20261022.md` được giữ nguyên ngoài commit. Nó ghi
KH PASS/GH FAIL và key drift của runtime cũ, không chứng minh candidate này live PASS.
