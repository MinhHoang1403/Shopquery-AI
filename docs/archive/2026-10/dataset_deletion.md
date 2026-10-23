> HISTORICAL snapshot. Current status: [V2 acceptance](../../v2_final_acceptance.md).

# Quản lý xóa bộ dữ liệu và nguồn upload

Ngày kiểm tra: 19/10/2026 (giờ Việt Nam). Baseline Git: `3d441af`. Kết quả live được thu thập trên bản local đã build vào Docker trước commit bàn giao. SHA và kết quả CI của commit bàn giao được báo riêng sau push/xác minh.

## Hành vi bàn giao

- Sidebar **Quản lý dữ liệu** → **Quản lý bộ hiện có** → chọn bộ cần quản lý.
- Nút thùng rác cạnh bảng CSV/XLSX xóa bảng vật lý tương ứng và metadata. Với workbook, mỗi sheet đã import là một bảng riêng; không tự xóa các bảng khác cùng tên file.
- Nút thùng rác cạnh tài liệu xóa tài liệu và chunks/embeddings liên quan.
- **Xóa bộ dữ liệu** xóa toàn bộ nguồn trong đúng workspace. Nếu có chat, mặc định backend trả `409`; phải chọn rõ **Xóa cả lịch sử chat gắn với bộ dữ liệu này** hoặc xóa các chat trước. Khi đồng ý, chỉ chat/tin nhắn gắn với bộ đó bị xóa. Không gán lại lịch sử sang cửa hàng mẫu.
- Mọi thao tác có bước xác nhận, cảnh báo vĩnh viễn, nút hủy và trạng thái đang xử lý. Không cho đổi workspace/gửi trùng thao tác trong khi xóa; không cho xóa trong lúc chat hiện tại đang chạy.
- Xóa một nguồn giữ nguyên lịch sử có kết quả/trích đoạn đã lưu; người dùng được cảnh báo chúng có thể lỗi thời. File gốc trên máy không bị xóa. Không có thùng rác/khôi phục trong UI.
- Chỉ nguồn upload có thể xóa. Không có thao tác xóa cửa hàng mẫu; nguồn không thuộc workspace hoặc không tồn tại trả `404`.
- Sau xóa, số nguồn cập nhật ngay. Xóa bộ đang chọn đưa giao diện về chat mới với dữ liệu mẫu, bỏ chat đã xóa khỏi sidebar. Khi quản lý tiếp, chọn rõ bộ khác thay vì tự hiển thị nhầm bộ kế tiếp.

## Triển khai và bảo vệ

Không đổi schema, model AI, embedding, SQL validator hay dependencies. Backend bổ sung `DatasetRepository.delete_table` và `delete`, cùng hai DELETE endpoint. API xóa tài liệu đã có được giữ nguyên; UI thay xác nhận native bằng cùng luồng xác nhận inline cho mọi loại nguồn.

Xóa bảng/toàn bộ workspace khóa bản ghi dataset và thực hiện DDL/metadata trong cùng transaction. Chỉ lấy định danh vật lý từ registry của đúng dataset, qua `SQLAlchemy Table` với schema cố định `uploaded_data`; không nhận tên bảng từ client, không dùng `DROP CASCADE`. Xóa tài liệu/chunks và tin nhắn dựa vào các khóa ngoại cascade đã có. Kiểm thử PostgreSQL xác minh rollback thực tế khi có lỗi giữa các bước DROP.

Tham chiếu thiết kế: [PostgreSQL dependency tracking](https://www.postgresql.org/docs/current/ddl-depend.html), [SQLAlchemy Table.drop](https://docs.sqlalchemy.org/en/20/core/metadata.html#sqlalchemy.schema.Table.drop).

Các endpoint mới:

```text
DELETE /api/datasets/{dataset_id}/tables/{table_id}
DELETE /api/datasets/{dataset_id}?delete_conversations=false
```

Đặt `delete_conversations=true` chỉ khi người dùng đồng ý xóa lịch sử. Thành công trả `204` không body; `404` cho nguồn sai scope/không tồn tại; `409` khi chưa đồng ý xóa chat liên quan. Không cần gọi provider AI để xóa. Quyền quản lý vẫn dùng chung trong môi trường local: chưa có authentication/phân quyền người dùng; tính năng này không bổ sung multi-tenant access control.

## Kết quả kiểm thử

| Kiểm tra | Kết quả |
| --- | --- |
| Ruff | Pass |
| Backend unit/API | 172 passed, 70 deselected; thêm 8 test xóa |
| PostgreSQL integration trên database test riêng | 62 passed, 180 deselected; thêm 5 test, không skip |
| Frontend Vitest | 31 passed; thêm 7 test, gồm reset chat đang xem sau xóa |
| Frontend lint, typecheck, build | Pass |
| Playwright mock: import và xóa trên 5 viewport | 10 passed; 2 ca × desktop 1440/1280, tablet 768, mobile 390/320 |
| Docker API/web build và health qua Nginx | Pass |

Backend integration chạy không đọc `.env`, bỏ biến cấu hình hai provider, không gọi AI. Kiểm tra thực tế: xóa một bảng và bảng cuối, cập nhật metadata legacy, giữ tài liệu/chat khi xóa riêng bảng, sai scope không xóa, xóa cả bộ kèm chunks/embeddings/chat/tin nhắn, giữ workspace khác/default corpus, rollback DDL khi lỗi và xóa bộ rỗng. Database integration tạm không phải database ứng dụng.

Frontend kiểm tra hủy không gửi DELETE, đúng ID/scope của nguồn, lỗi API không tự biến thành thành công, không tự tích xóa lịch sử, retry sau xác nhận, chặn thao tác trùng/đổi workspace, chặn xóa khi chat đang chạy, cập nhật số bảng/tài liệu và reset lựa chọn sau xóa cả bộ. Đã sửa việc chọn lại cùng file sau import/xóa để file input phát sinh sự kiện mới.

## Live trên giao diện thật

Đã sao lưu database local trước rebuild. Tạo riêng workspace **Kiểm thử xóa dữ liệu · 19-10-2026**, ID **8**, qua UI, import hai CSV fixture và nạp `policy.md` giả lập qua UI (1 chunk). Không dùng file/dữ liệu nhạy cảm. Người dùng xác nhận chỉ cho phép xóa workspace kiểm thử ID 8 và các nguồn/chat thuộc nó.

1. Chọn xóa bảng `sales`, rồi **Hủy xóa**: bảng còn nguyên.
2. Xác nhận xóa `sales`: mất đúng bảng đó; `workspace_orders` và tài liệu còn nguyên.
3. Xóa `policy.md`: tài liệu/chunks của ID 8 về 0, bảng `workspace_orders` vẫn còn.
4. Tạo một conversation rỗng có tên **Kiểm thử lịch sử xóa · ID 8** bằng API để kiểm tra ràng buộc lịch sử, không gọi AI hoặc tạo đáp án giả. Reload UI và mở lại quản lý: chỉ còn 1 bảng, 0 tài liệu.
5. Thử xóa cả bộ khi chưa tích xóa lịch sử: UI hiển thị đúng lỗi `409`, không xóa nguồn.
6. Tích đồng ý xóa lịch sử và xác nhận: ID 8 biến mất khỏi dữ liệu/API/sidebar; chat kiểm thử biến mất; UI chuyển về chat mới và dữ liệu mẫu.

Đối chiếu PostgreSQL/API sau kiểm thử: còn nguyên **7 workspace, 7 bảng upload, 1 tài liệu upload, 28 chunks, 12 conversation và 72 tin nhắn** đã có trước đợt này. Dữ liệu cửa hàng không thay đổi: **150 products, 2.000 orders, 4.019 order items**. Không xóa bộ dữ liệu hoặc lịch sử cũ. Workspace ID 8 bị xóa vĩnh viễn khỏi giao diện; file fixture gốc vẫn còn.

Ảnh bằng chứng và bản sao lưu chỉ ở thư mục local ngoài Git. Không chạy lại smoke SQL/RAG/Hybrid hai provider trong đợt này vì không đổi pipeline AI; không tuyên bố bộ Playwright mock đầy đủ đã chạy. Các kết quả trong bảng là kiểm thử local trước commit. CI sau push kiểm tra riêng Ruff, backend unit, PostgreSQL integration trên database riêng không cần API key, cùng frontend lint/typecheck/Vitest/build; không chạy lại live AI hoặc Playwright.
