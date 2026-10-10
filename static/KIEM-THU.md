# Kết quả kiểm tra giao diện

Ngày kiểm tra: 10/10/2026. Chạy bằng Chromium headless, frontend được phục vụ qua HTTP nội bộ. API được giả lập để kiểm tra hành vi giao diện; chưa kết nối database/server thật của nhóm.

Đã kiểm tra đạt:
- Thêm từ trang chủ và danh mục; thêm cùng mã từ trang chi tiết được cộng dồn đúng.
- Trang chi tiết dùng số lượng đã nhập; Mua ngay mở đúng trang thông tin giao hàng.
- Tăng số lượng, tính lại tạm tính và số lượng trên header.
- Nhập số lượng trống bị từ chối, không làm tổng tiền thành NaN.
- Xóa một mặt hàng; hủy/xác nhận xóa toàn bộ; trạng thái giỏ trống ẩn nút tiếp tục.
- Tìm kiếm tên không dấu, kết quả trống; sắp xếp giá toàn danh mục trước khi phân trang, giữ sort khi chuyển trang.
- Mã sản phẩm không tồn tại hiển thị thông báo.
- localStorage chứa JSON hỏng không làm ứng dụng dừng; giỏ trống không cho nhập đơn.
- Form thiếu trường bắt buộc hoặc số điện thoại sai không tạo đơn.
- Form hợp lệ tạo đơn DEMO, tải JSON có đúng hai dòng hàng, số lượng và tạm tính kiểm thử 2.360.000 VND; thông tin cá nhân không có trong localStorage.
- API giả lập HTTP 500 giữ giỏ và form; lần thử lại cùng payload giữ Idempotency-Key; HTTP 201 có orderId mới hiển thị kết quả và trừ hàng đã gửi.
- Payload API gửi productId/quantity, không gửi đơn giá để server tin trực tiếp.
- Cả 9 trang không tràn ngang ở viewport 390px; ảnh sản phẩm tải được.
- Không ghi nhận JavaScript exception trong các luồng trên.
- Kiểm tra trực quan ảnh chụp trang chủ, giỏ hàng và form trên desktop/mobile.
- HTML/CSS/JS đã định dạng lại; các đường dẫn file nội bộ tồn tại.

Giới hạn: chưa kiểm thử trên thiết bị iOS/Android thực, chưa kiểm thử thanh toán online, tồn kho, CORS và lưu đơn trong server thật. Thành viên backend cần chạy checklist trong API-HANDOFF.md sau khi kết nối.
