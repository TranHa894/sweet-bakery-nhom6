# Website tích hợp chatbot hiện tại

Chỉ file ngoài chatbot được nhập từ D:\Sweet-Bakery sang D:\sweet-bakery-nhom6. Không copy chatbot cũ, database, .venv, mật khẩu/cache.

1. Dừng server cũ bằng Ctrl+C.
2. Chạy CHAY-WEBSITE.bat ở root; hoặc dùng lệnh PowerShell ở đầu README.md.
3. Mở http://127.0.0.1:8000/ ; chat riêng /chatbot/ ; quản lý /admin.html.
4. Tải lại trang bằng Ctrl+F5 để nạp JS/CSS mới.

## Chatbot được bảo toàn

- Giữ NLU, Qwen và cấu hình Ollama/hybrid hiện tại. Bản 04/11 thêm interface provider đặt đơn vào API/FSM/form; không tạo lại .env hoặc tự bật rule.
- main.py ghép URL/widget và truyền adapter tạo đơn website vào API chatbot.
- Widget giữ mở cửa sổ nhỏ/toàn màn hình/nút tròn và lịch sử qua chuyển trang.
- Form chatbot và giỏ đều tạo đơn cùng mã SB-... sau khi khách xác nhận. Đơn xuất hiện chung ở Admin → Đơn hàng.
- Giá/tồn kho khi tích hợp đọc DB website; metadata tư vấn dùng repository hiện tại.
- Đơn từ chatbot và website cùng quy trình xử lý. Đơn mới chờ cửa hàng xác nhận, chưa thu tiền; yêu cầu tư vấn cũ không tự chuyển thành đơn.
- Database cũ trong chatbot/runtime giữ nguyên, không tự nhập vào runtime/sweet_bakery.sqlite3.
- main.py ở root chạy toàn website/API/chatbot. run_web.py không bị sửa, dành cho chatbot riêng; không chạy hai server cùng cổng.

## Kiểm tra 03/11/2026

20/20 ca API và16/16 mục Chrome headless đạt với DB thử. Gồm giá/tồn kho, quyền phiên/admin, form/xác nhận lặp, khôi phục lịch sử, đổi danh mục, mở món và giỏ hàng. Không gọi model thật, không cài dependency. Chưa thử nhấp đúp BAT hoặc tunnel/điện thoại thật. Hướng dẫn và giới hạn ở README.md.
