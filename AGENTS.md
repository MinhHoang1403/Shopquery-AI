# ShopQuery AI development guide

- Viết Python rõ ràng, tuân thủ PEP 8, dùng type hints và chia module theo trách nhiệm.
- Chỉ thêm comment hoặc docstring khi chúng giải thích interface, business rule hoặc logic khó.
- Đặt tên theo chức năng; không đưa mã kế hoạch, trạng thái công việc hoặc tên chung chung vào source code.
- Các quyết định AI, dữ liệu và bảo mật quan trọng phải dựa trên tài liệu chính thức hoặc nguồn kỹ thuật có thể kiểm chứng.
- Chỉ triển khai đúng phạm vi được yêu cầu; tránh framework, abstraction và hạ tầng không cần thiết.
- Không tự thay đổi kiến trúc, model bắt buộc hoặc mở rộng sang project khác.
- Luôn chạy các test liên quan sau khi chỉnh sửa và báo cáo trung thực phần đã/chưa kiểm chứng.
- Không commit secrets, `.env`, dữ liệu nhạy cảm, cache, virtual environment hoặc log.
