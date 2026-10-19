# Nghiệm thu prompt đa lĩnh vực

Ngày kiểm tra: 19/10/2026 (giờ Việt Nam). Baseline Git: `93fca7e`. Các kết quả live dưới đây được thu thập trên mã local đã build lại vào API Docker trước khi commit bàn giao. SHA và run CI của commit bàn giao được báo riêng khi push/xác minh hoàn tất; file không tự chứa SHA của chính commit tạo ra nó.

## Kết luận

Prompt đã hỗ trợ workspace upload theo schema/tài liệu thực tế thay vì mặc định mọi dữ liệu là bán hàng. Qua giao diện `http://127.0.0.1:8080/`, cả Knowledge và Gemini đều trả đúng các ca giả lập ở 5 lĩnh vực: doanh thu, học phí, giờ làm, vận tải và điện năng.

- 14 lượt SQL/RAG/Hybrid đa lĩnh vực đạt đối chứng sau sửa mapping bảng.
- 2 lượt thiếu trường dữ liệu trả `UNSUPPORTED`, không tạo SQL/rows/nguồn.
- 2 lượt hồi quy SQL cửa hàng mẫu đạt đối chứng múi giờ Việt Nam.
- Tổng 18 lượt hoàn tất đúng tiêu chí; ngoài ra có 1 lỗi SQL ban đầu được giữ trong lịch sử, không tính là pass.

Đây là smoke có ground truth, không chứng minh truy vấn được mọi lĩnh vực/mọi file hoặc mọi câu hỏi. Không đổi model, database schema, embedding, retry/fallback hay quyền SQL. Chưa thêm phân quyền theo người dùng hoặc JOIN bảng upload.

## Thay đổi mã và lý do

| File | Thay đổi |
| --- | --- |
| `backend/app/routing/router.py` | Phân loại theo loại bằng chứng, ví dụ đa lĩnh vực; nhận context nguồn đang chọn; không dùng cửa hàng làm nguồn thay thế khi thiếu dữ liệu. |
| `backend/app/dependencies.py` | Truyền context workspace vào router của cả hai provider. |
| `backend/app/datasets/context.py` | Mô tả workspace độc lập lĩnh vực; tách tên hiển thị, tên file/header và định danh SQL; yêu cầu copy đúng tên bảng fully qualified. |
| `backend/app/text_to_sql/generator.py` | Sinh SQL theo cột/kiểu thực tế, không tự thêm quy tắc bán hàng hoặc bịa công thức/điều kiện/đơn vị. Giữ quy tắc múi giờ, NULL/0 và giới hạn SQL. |
| `backend/app/text_to_sql/schema_context.py` | Chuyển yêu cầu category/shipping và JOIN của cửa hàng vào context riêng của default store. |
| `backend/app/routing/hybrid.py` | Đối chiếu bản ghi/nhóm bất kỳ với tài liệu; không bắt học viên/nhân sự/phép đo phải có thuộc tính sản phẩm. Vẫn giữ quy tắc category code khi áp dụng cho cửa hàng. |
| `backend/app/rag/pipeline.py` | Hướng dẫn trả lời theo tài liệu của lĩnh vực bất kỳ; không bịa facts/rules hoặc citation. |
| `backend/tests/test_workspace_prompts.py` | 17 regression tests cho context/prompt/dependency wiring, RAG/Hybrid học phí và các giới hạn SQL không đổi. |

Cơ sở thiết kế prompt: chỉ dẫn rõ ràng, context và ví dụ đa dạng theo [Google Gemini prompt design strategies](https://ai.google.dev/gemini-api/docs/prompting-strategies). Đây là lựa chọn triển khai được kiểm tra bằng test/live của dự án, không phải bảo đảm độ chính xác từ nhà cung cấp. Bảo vệ thực thi vẫn do validator, role đọc và scope ở backend, không chỉ dựa vào prompt.

## Bộ dữ liệu giả lập

Workbook bàn giao `du_lieu_gia_lap_da_linh_vuc.xlsx` có 5 sheet, mỗi sheet 6 dòng, header/cấu trúc khác nhau. Không có người thật, thông tin cá nhân thật hoặc số liệu doanh nghiệp. Ngày và số được lưu có kiểu; các mã là text. File này là artifact bàn giao local, không đặt trong source/backend image.

| Sheet / workspace | Cột chính | Đối chứng được tính trước khi gọi AI |
| --- | --- | --- |
| `Doanh_thu` | Mã giao dịch, Ngày, Khu vực, Doanh thu, Trạng thái | Tháng 10/2026, chỉ `Đã thu`: Bắc 1.200.000; Nam 1.200.000; Trung 600.000. Loại dòng `Chưa thu` và dòng 30/09. |
| `Hoc_phi` | Mã học viên, Họ tên, Lớp, Học phí phải nộp, Đã đóng | Phải nộp 27.000.000; đã đóng 18.500.000; còn nợ 8.500.000. Có học viên đã đóng 0 và học viên không còn nợ. |
| `Gio_lam` | Mã nhân sự, Tên giả lập, Phòng ban, Giờ làm | Kế toán 290 giờ; Kỹ thuật 280 giờ; Vận hành 260 giờ. |
| `Van_tai` | Mã chuyến, Tuyến, Khối lượng kg, Cước vận chuyển | Bắc: 30 kg / 280.000; Nam: 40 kg / 380.000; Trung: 17 kg / 180.000. |
| `Nang_luong` | Mã đo, Ngày đo, Trạm, Điện tiêu thụ kWh | Tháng 10/2026: Trạm A 250 kWh; Trạm B 430 kWh, gồm một phép đo bằng 0. |

Đã import từng sheet bằng file chooser/preview/import thật trên UI thành **5 workspace riêng**, tên bắt đầu `Đa lĩnh vực ·`. Chọn đúng sheet trước import; không giả API hoặc nạp trực tiếp bảng bằng SQL để thay luồng upload.

Workspace học phí có thêm `quy_dinh_hoc_phi_gia_lap.md`, upload/embedding thật tạo 3 chunks. Quy định kiểm thử: còn nợ = phải nộp − đã đóng; nhắc khi nợ **lớn hơn** 1.000.000; hạn 31/10/2026; không có quy định lãi phạt hay đình chỉ học. Đây không phải chính sách của một trường thật.

## Kết quả live hai model

Thời gian dưới đây là giây giữa timestamp user/assistant lưu trong PostgreSQL, không phải benchmark hoặc thời gian render toàn trình duyệt. Mỗi ca một lượt/model sau bản sửa mapping.

| Ca | Route | Knowledge | Gemini | Đối chứng |
| --- | --- | --- | --- | --- |
| Doanh thu tháng 10 theo khu vực, trạng thái `Đã thu` | SQL | Pass, 5,766 s | Pass, 3,444 s | 3 nhóm khớp toàn bộ tổng; không thêm `completed`. |
| Tổng phải nộp/đã đóng/còn nợ học phí | SQL | Pass, 4,894 s | Pass, 2,871 s | 27.000.000 / 18.500.000 / 8.500.000; 6 học viên. |
| Tổng giờ làm theo phòng ban | SQL | Pass, 4,794 s | Pass, 2,932 s | 290 / 280 / 260 đúng từng phòng ban. |
| Tổng khối lượng và cước theo tuyến | SQL | Pass, 5,774 s | Pass, 3,385 s | 3 tuyến đúng cả 2 chỉ tiêu. |
| Tổng điện tháng 10 theo trạm | SQL | Pass, 5,113 s | Pass, 3,070 s | A 250; B 430; mỗi trạm 3 dòng, giữ phép đo 0. |
| Điều kiện nhắc và hạn đóng trong tài liệu | RAG | Pass, 4,810 s | Pass, 2,755 s | `> 1.000.000`, ngày 31/10/2026; 2 nguồn thật. |
| Học viên cần nhắc theo quy định tài liệu | HYBRID | Pass, 11,508 s | Pass, 5,206 s | HV002: 1.500.000; HV003: 2.000.000; HV005: 4.000.000. Loại HV006 nợ đúng 1.000.000. |
| Hỏi học phí trong workspace Điện năng | UNSUPPORTED | Pass, 2,149 s | Pass, 1,250 s | Không chạy sang workspace học phí, không SQL/rows/sources giả. |

Hybrid SQL trả 4 học viên còn nợ, bao gồm HV006 để đối chiếu; câu trả lời cuối áp dụng quy định và chỉ kết luận 3 học viên cần nhắc. Không coi 4 SQL rows là 4 người đủ điều kiện.

Đã kiểm tra response lưu qua API và đối chứng độc lập bằng `SELECT` với role `shopquery_reader`. Các phép cộng/nhóm được tính trước bằng JavaScript từ dữ liệu mẫu, rồi so với PostgreSQL sau import và với từng response. Không lấy câu trả lời AI làm expected result. Toàn bộ source `chunk_id/source_file/section_title/content` khớp database và đúng `dataset_id` học phí; không dùng corpus cửa hàng.

Cả 18 lượt hoàn tất có `error=null`, `requested_model=used_model`, `fallback_used=false`. Fallback cấu hình đang tắt. Không có 429/503 được ghi nhận trong các lượt này; không suy ra upstream sẽ luôn khả dụng.

## Lỗi phát hiện trong quá trình kiểm tra

### Tên hiển thị bị dùng làm bảng SQL

Lượt doanh thu Knowledge đầu tiên trả lỗi `Table is not allowed: Doanh_thu`. Model đã chọn tên sheet/display label thay vì `uploaded_data.dataset_<id>`. Validator chặn, không thực thi nhầm bảng, không tạo rows/citations/đáp án giả. Đây là lỗi SQL generation/mapping, không có bằng chứng là lỗi upstream 503.

Đã sửa context để ghi riêng **Display label (not an SQL identifier)**, **SQL table identifier (copy exactly)** và source filename; thêm regression assertion. Gửi lại nguyên câu hỏi trên UI: Knowledge pass; Gemini cũng pass cùng câu hỏi. Lỗi cũ vẫn lưu trong chat doanh thu, không xóa để che kết quả.

### Môi trường integration test cần database sạch

Lần chạy đầu trên database test mới: 57 pass. Khi chạy lại nguyên suite trên cùng database đã có fixture, có 6 fail/51 pass vì tên dataset fixture trùng (`UniqueViolation`/`ResourceConflictError`), không phải do prompt sinh sai hoặc database ứng dụng bị ghi. Đã tạo database kiểm thử mới sạch và chạy lại bản cuối: **57 pass, không skip**. Hai database test tạm đã được dọn; không sửa framework test hoặc nới ràng buộc unique chỉ để tạo pass. CI hiện tạo database mới mỗi job nên không tái sử dụng trạng thái này.

## Hồi quy cửa hàng và lịch sử

- Hỏi top 5 tháng 9/2025 trên UI với cả hai model: đúng IDs 10, 47, 120, 123, 135 và quantity 15, 14, 11, 11, 10 theo SQL PostgreSQL độc lập có biên `+07`. Hai sản phẩm đồng hạng 11 có thể đổi thứ tự.
- Đã chuyển chat, tải lại trang, rồi mở lại chat học phí từ lịch sử: đủ **12 tin nhắn**, đúng workspace, nhãn Knowledge/Gemini, SQL, rows và citations. Mở lại panel nguồn và trích đoạn thành công sau reload.
- Hiện reload chọn hội thoại cập nhật gần nhất, không bảo đảm tự giữ chat đang xem nếu đó là chat cũ; phải chọn lại từ lịch sử. Không mất nội dung đã lưu.
- 5 chat workspace có lần lượt: doanh thu 6 tin nhắn (gồm cặp hỏi/lỗi đầu), học phí 12, giờ làm 4, vận tải 4, điện năng 8. Chat hồi quy cửa hàng thêm 4 tin nhắn. Không sửa/xóa lịch sử cũ.
- Console không ghi nhận warn/error ở lần đọc sau reload. Trên viewport hẹp, thông báo import có thể che nút chat mới trong sidebar; đã đóng thông báo trước thao tác. Không sửa UI trong đợt prompt này.

## Kiểm thử và bảo toàn dữ liệu

| Kiểm tra | Kết quả cuối |
| --- | --- |
| Ruff | Pass |
| Backend unit/API/security/parser | 164 passed, 65 deselected; tăng 17 test |
| PostgreSQL integration, database mới sạch | 57 passed, 172 deselected, không skip |
| Frontend Vitest | 24 passed |
| Docker API build / health qua Nginx | Pass |
| Đối chứng workspace và hồi quy qua UI/API/DB | 18 lượt đạt, 1 lỗi ban đầu giữ lại |

Unit tests dùng stub để kiểm tra hợp đồng/context/guardrails, không chứng minh LLM phân loại đúng; các ca live phía trên kiểm chứng riêng hành vi hai provider. Frontend không sửa; không chạy lại Playwright mock toàn bộ, frontend build hoặc tải hệ thống trong đợt live này. Bảng trên là kết quả local trước commit; CI sau push kiểm tra riêng Ruff, backend unit, PostgreSQL integration và frontend quality, không chạy lại live AI.

Trước/sau lần kiểm tra, dữ liệu nghiệp vụ mẫu giữ nguyên 150 products / 2.000 orders / 4.019 order items. Workspace tăng 2 → 7, bảng upload 2 → 7, tài liệu upload 0 → 1, chunks 25 → 28, đúng phần giả lập đã thêm. Đã sao lưu database trước rebuild API. Model/embedding/schema/giới hạn bảo mật không thay đổi. Không đưa `.env`, private endpoint, key, dump, log hoặc ảnh local vào source.

## Cách mở lại mẫu và giới hạn

Trên giao diện, chọn workspace có tiền tố `Đa lĩnh vực ·`, tạo chat mới và chọn Knowledge/Gemini. Dùng câu hỏi trong ma trận; học phí có sẵn bảng và tài liệu để thử đủ SQL/RAG/Hybrid. Các file mẫu và ảnh/evidence JSON được bàn giao local, không nhúng đường dẫn máy cá nhân vào repository.

Chưa hỗ trợ JOIN giữa bảng upload, schema tùy ý ngoài workspace, các hàm SQL bị validator cấm, OCR hoặc dữ liệu thiếu trường cần thiết. Tên cột/kiểu dữ liệu cần rõ; schema hợp lệ không bảo đảm hiểu đúng mọi nghiệp vụ hoặc công thức không được mô tả. Chưa có authentication/phân quyền người dùng: workspace isolation không phải multi-tenant access control. Chỉ dùng dữ liệu giả lập hoặc dữ liệu đã được phép chia sẻ với provider; chưa đủ điều kiện public production.
