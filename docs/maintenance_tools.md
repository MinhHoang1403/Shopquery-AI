# Bộ dữ liệu synthetic bảo trì

Ba modules `scripts/generate_maintenance_demo.py`, `maintenance_documents.py` và
`maintenance_oracle.py` tạo dữ liệu giả để kiểm thử offline. Chúng không đọc `.env`,
không kết nối database/Docker/provider, không upload dữ liệu vào 8080.

## Dependencies và tạo dữ liệu

Cần Python 3.11/uv và hai TTF Unicode regular/bold có sẵn. Requirements riêng pin
ReportLab 4.4.9, python-docx 1.2.0 và pypdf 6.21.2; không sửa dependency/API image.
Dùng tại repository root, thay đường dẫn output bằng thư mục **chưa tồn tại** với
parent đã có. Không có default output hoặc chế độ overwrite:

```powershell
uv run --no-project --with-requirements scripts/requirements-maintenance.txt python scripts/generate_maintenance_demo.py --output C:/Work/maintenance-fixture --font C:/Windows/Fonts/arial.ttf --bold-font C:/Windows/Fonts/arialbd.ttf
uv run --no-project --with-requirements scripts/requirements-maintenance.txt python scripts/maintenance_oracle.py --input C:/Work/maintenance-fixture --output C:/Work/maintenance-oracle.json
```

Output phải absolute, thư mục generator phải mới, JSON oracle phải chưa tồn tại.
File đích dùng exclusive creation. Dependencies/fonts được kiểm trước khi tạo output.
Nếu phát sinh I/O lỗi giữa chừng, CLI báo lỗi và giữ phần đã tạo để kiểm tra; không
xóa/ghi đè tự động hoặc retry vào cùng folder. Không truyền main DB URL cho tools.

Sáu nguồn:30 trung tâm,60 dịch vụ,3000 phiếu CSV; một chính sách KPI MD; quy trình DOCX;
sổ tay PDF có text layer. Fixed seed/ngày chốt được ghi trong source, số liệu/bộ tên
hoàn toàn synthetic. Cùng dependencies/fonts/environment tạo lại byte-identical;
không hứa cùng PDF bytes giữa Arial Windows và DejaVu Linux.

## Oracle và phạm vi

Oracle tính lại từ CSV thực, không lấy target totals trong generator làm expected
answer. Kiểm headers, PK uniqueness, FK, Decimal hữu hạn/nonnegative/tối đa2 chữ số
thập phân, ngày/trạng thái, shape 30/60/3000 và source file bounds. Policy phải đúng
bản synthetic được hỗ trợ; thay policy bị từ chối thay vì tự suy luật mới.

KPI cố định 8.000.000 VND, mọi trạng thái; cùng rule dùng cho generator document và oracle.
SUM dùng Decimal; AVG lặp vô hạn chỉ có biểu diễn Decimal precision 50 và exact rational
numerator/denominator ở tổng thể, không được xem chuỗi50 digits là byte-exact PostgreSQL
AVG. So SQL NUMERIC cần đối chiếu exact rational/scale PostgreSQL trong test riêng.
NULL note tương ứng ô trống/whitespace; số 0 là giá trị hợp lệ.

JSON gồm sums/counts/groupings/KPI, hashes sáu nguồn và56 question specifications.
Các SQL templates dùng `{C}`, `{S}`, `{F}` chưa gắn physical table names; tools **không
thực thi SQL**. Các negative/security specifications là kế hoạch ca kiểm, không phải
bằng chứng đã chạy security tests. Muốn import/live test cần operator cho phép dữ liệu,
provider budget và quy trình nghiệm thu riêng; bộ fixture này chưa được nạp production.

## Tests

```powershell
uv run --no-project --with-requirements scripts/requirements-maintenance.txt python scripts/test_maintenance_tools.py
```

10 unittests dùng đúng subtree temporary do test tạo, tự dọn sau kiểm; không copy source
hoặc xóa thư mục người dùng. Kiểm CLI/no-overwrite, fonts failure, headers/duplicate keys,
FK/NaN/negative/scale/date/status/policy refusal, độc lập target totals, Decimal boundary,
parse DOCX/PDF/Unicode và reproducibility. CI chính chạy cùng command trên Ubuntu dùng
DejaVu Sans có sẵn; Windows dùng Arial. Không cần Google/LLM/Docker credentials.
