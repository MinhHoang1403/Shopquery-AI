# Development

```powershell
cd backend
uv sync --locked --extra reranker
cd ..
./scripts/dev.ps1 -Build
./scripts/verify-runtime.ps1
```

Dùng `compose.yaml` rồi `compose.dev.yaml`, project `shopquery-ai`. Chỉ vận hành
`devdb`, `api`, `web`; không recreate main `db`. Đọc [deployment](deployment.md)
trước lần chuyển runtime đầu, không chạy Compose không có service/override rõ ràng.

| Service | Endpoint | Source/database |
| --- | --- | --- |
| web | 127.0.0.1:8080 | Vite development, React source read-only bind |
| api | 127.0.0.1:8001 | `/app/app` read-only bind + Uvicorn reload |
| devdb | 127.0.0.1:15433 | `shopquery_dev` + `shopquery_test_stage1`, volume dev riêng |
| db main | Giữ cổng/volume baseline | Không phải sandbox |

Banner Development phân biệt dữ liệu thử nghiệm. Google/provider credentials và
paid gates bị override tắt/rỗng. Tài khoản/lịch sử main không hiện trong dev DB,
vẫn nằm nguyên ở main volume. Không bật provider để thử key.

API watchfiles và Vite dùng polling cho bind mount Windows, không chồng Compose
Watch. Proxy ghi đè forwarded IP từ socket peer. Vite chỉ dành cho localhost dev.

`dev.ps1` tìm BGE trong Hugging Face cache user hoặc nhận `-ModelPath`.
`BGE_MODEL_PATH` là host snapshot; `RAG_RERANKER_PATH=/models/bge` trong API.
Mount read-only, không copy weights vào image/Git. Pinned revision
`953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, weights/tokenizer hashes được kiểm khi load.
Extra `reranker` khóa Sentence Transformers/PyTorch CPU. CPU đã smoke; host CUDA
không có nghĩa Docker CUDA inference đã nghiệm thu. HF offline, remote code tắt.

| Thay đổi | Thao tác |
| --- | --- |
| Python/React source | Reload/HMR tự động; verify-runtime |
| Python/npm dependency | Lock + targeted tests, `dev.ps1 -Build` |
| Environment/key | Controlled API/web recreate; source reload không nạp env mới |
| Schema | Reviewed migration riêng, không tự migrate main |
| Release | Reviewed pinned image; chưa merge/release trong Giai đoạn 1 |

`requirements.txt` là export runtime mặc định từ uv.lock, không bao gồm optional
reranker. Native dùng `uv sync --locked --extra reranker`. Không commit `.env`/weights.
