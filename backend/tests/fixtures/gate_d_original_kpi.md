# KPI tổng phí kho synthetic

Trong bộ dữ liệu giả lập này, một kho đạt KPI tổng phí khi tổng phi_giao_vnd của các đơn thuộc kho đó từ 500000.00 VND trở lên. Tính tất cả trạng thái đơn giao hàng, không chỉ trạng thái Đã giao. Xác định kho của đơn qua tài xế và liên kết kho_id; phân biệt từng kho theo mã kho_id, không gộp theo tên. SUM bỏ qua giá trị NULL, giữ số 0 là giá trị hợp lệ. Trả kết luận đạt hoặc chưa đạt cho từng kho dựa trên tổng phí SQL thực tế, không áp dụng KPI khác.
