# Sweet Bakery — sửa font và quản lý đơn hàng

## Lần nhập website — 03/11/2026

Giữ nguyên chatbot của D:\sweet-bakery-nhom6; chỉ cập nhật website bên ngoài từ D:\Sweet-Bakery. Kết quả mới: 20/20 ca API bằng runner thư viện chuẩn, giữ assertions của file nguồn;16/16 mục Chrome headless với server/DB thử. Không gọi model thật, không cài dependency hoặc đổi DB đang dùng. Hướng dẫn chính xác ở README.md và HUONG-DAN-CHATBOT-MOI.md.

Phần bên dưới là tài liệu lịch sử từ bản nguồn, không phải toàn bộ kết quả mới của lần nhập này.

## Chạy trên Windows
1. Giải nén toàn bộ thư mục Sweet-Bakery. Không chỉ mở một file HTML.
2. Chạy CAI-DAT.bat nếu máy chưa cài môi trường dự án.
3. Chạy CHAY-WEBSITE.bat và giữ cửa sổ này mở.
4. Cửa hàng: http://127.0.0.1:8000/
5. Quản trị: tự nhập http://127.0.0.1:8000/admin.html vào trình duyệt. Trang chủ không có liên kết đến trang này.
6. Mật khẩu được server tạo khi khởi động lần đầu: mở runtime/admin-password.txt trong thư mục dự án. Nếu đã đặt biến SWEET_ADMIN_PASSWORD, dùng giá trị biến đó.

## Sử dụng quản lý đơn
- Đặt thử một đơn tại cửa hàng, sau đó vào trang admin, đăng nhập và bấm Làm mới.
- Tìm theo mã đơn, tên khách hoặc số điện thoại; kết hợp bộ lọc trạng thái.
- Bấm Xem chi tiết đơn hàng để xem địa chỉ, sản phẩm, ngày giao mong muốn, lời chúc và ghi chú.
- Chờ xác nhận → Đã xác nhận → Hoàn tất. Có thể hủy đơn chờ xác nhận hoặc đã xác nhận; server hoàn lại tồn kho khi hủy.
- Đơn hoàn tất/đã hủy không đổi ngược trạng thái.
- Thống kê và tìm kiếm áp dụng cho tối đa 500 đơn mới nhất được API trả về.
- Đây là dự án chạy local. Phí vận chuyển chưa được nhập/xác nhận qua admin; chưa tích hợp thu tiền hoặc gửi thông báo.
- Trang admin có xác thực ở API. Việc không đặt liên kết trên trang chủ chỉ để tách điều hướng.

## Sửa lỗi font
- Giữ nguyên nội dung tiếng Việt, chuẩn hóa Unicode NFC và UTF-8.
- Thay font Georgia ở tiêu đề/câu trang trí bằng Arial với font dự phòng hỗ trợ tiếng Việt.
- Thêm static/font-fix.css vào các trang, bao gồm trang thanh toán có trong ảnh.
- Bảy trang HTML gửi kèm là nền nội dung cho bản cập nhật; các tài nguyên và API bổ sung được lấy từ bản Sweet-Bakery-tich-hop.zip hiện có.
- Các tên file trong static/ không có hậu tố (2), khớp với liên kết trong website.
- Nếu đang chạy bản tích hợp cũ, sao lưu thư mục runtime trước khi thay các file. Không xóa database cũ.

## Kiểm thử
- 18 bài kiểm thử tích hợp API đạt: kiểm tra dữ liệu đơn, giá/tồn kho, đăng nhập, đổi trạng thái, hủy đơn và hoàn tồn kho, chatbot và kiểm tra nguồn request.
- Không đóng gói database kiểm thử hay mật khẩu kiểm thử.
- Kiểm tra logic hiển thị admin: thống kê, tìm kiếm, lọc trạng thái và escape HTML đạt. Các liên kết CSS/JS nội bộ hợp lệ.
- Chưa xác minh trực quan bằng trình duyệt tự động vì môi trường không tải được Chromium.
