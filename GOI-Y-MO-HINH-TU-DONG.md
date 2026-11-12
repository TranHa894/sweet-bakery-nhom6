# Đề xuất Mô hình Tự động hóa cho Dự án Sweet Bakery (Thực tập Cơ sở Ngành)

Tài liệu này phân tích kiến trúc hiện tại của dự án **Sweet Bakery** (`FastAPI` + `SQLite` + `Chatbot Rule/Ollama`) và đề xuất **4 mô hình tự động hóa** thực tế, vừa dễ triển khai trực tiếp trên nền tảng code sẵn có của nhóm, vừa tạo điểm nhấn kỹ thuật rõ nét khi báo cáo đồ án môn **Thực tập Cơ sở Ngành**.

---

## 1. Hiện trạng tự động hóa đã có trong bản cập nhật này

Trong phiên bản vừa nâng cấp, hệ thống đã có sẵn các cơ chế tự động nền tảng:
1. **Tự động giữ & hoàn trả tồn kho theo trạng thái đơn (`Transactional Stock Reservation`)**:
   - Khi khách đặt đơn tại `/api/orders`, hệ thống dùng giao dịch SQLite (`BEGIN IMMEDIATE`) để kiểm tra và trừ tồn kho tức thì.
   - Khi Admin chuyển trạng thái đơn sang `Đã hủy` (`cancelled`), hệ thống tự động cộng trả lại đúng số lượng từng biến thể bánh vào bảng `product_variants`.
2. **Bảng Giám sát Vận hành & Cảnh báo Tự động (`Auto-Monitor Panel` trên trang Admin)**:
   - Tự động phát hiện các đơn hàng `Chờ xác nhận` quá 15 phút (cảnh báo SLA xử lý đơn).
   - Tự động thống kê tải đơn hàng theo 3 khung giờ giao bánh (`Sáng 08–12h`, `Chiều 12–17h`, `Tối 17–20h`).
   - Tự động theo dõi biến động tồn kho từ `/api/products` và số phiếu tư vấn mới từ Chatbot.

---

## 2. Gợi ý 4 Mô hình Tự động hóa Nâng cao cho Đồ án

### Mô hình 1: Tự động chuyển đổi Phiếu tư vấn Chatbot thành Đơn hàng chính thức (`One-Click / Auto Lead-to-Order Pipeline`)
- **Vấn đề hiện tại**: Khách hàng điền form đặt bánh trong Chatbot được lưu vào bảng `submissions` (dạng bản nháp chờ tư vấn) tách biệt hoàn toàn với bảng `web_orders`, khiến Admin phải nhập tay lại nếu khách chốt đơn.
- **Cơ chế tự động hóa**:
  - Bổ sung API `POST /api/admin/chatbot-requests/{id}/convert` trong `main.py`.
  - Khi khách đã xác nhận qua Chatbot (hoặc khi Admin bấm nút **"Duyệt thành đơn chính thức"** trên thẻ tư vấn Chatbot), hệ thống tự động:
    1. Kiểm tra tồn kho thực tế trong `product_variants`.
    2. Sinh mã đơn `SB-YYYYMMDD-...` và chuyển dữ liệu từ `submissions` sang `web_orders` + `web_order_items`.
    3. Trừ tồn kho tự động và đánh dấu phiếu tư vấn đã được chuyển đổi.
- **Độ khó**: Thấp (1–2 buổi code). Rất khớp với kiến trúc hiện tại của nhóm.

### Mô hình 2: Tự động tính Phí giao hàng theo Khu vực & Giới hạn Năng lực Bếp theo Khung giờ (`Auto-Zone Shipping & Kitchen Slot Capacity`)
- **Vấn đề hiện tại**: Tất cả đơn hàng đang để `shipping_fee = None` (*"Phí giao hàng chờ xác nhận"*), và khách có thể đặt dồn 50 chiếc bánh kem vào cùng một buổi sáng mà hệ thống chưa cảnh báo quá tải lò nướng/thợ trang trí.
- **Cơ chế tự động hóa**:
  - **Tự động định giá vận chuyển (`Zone-based Pricing`)**: Tạo bảng cấu hình khoảng cách theo Quận/Phường (`ward` / `province`). Ví dụ: Nội thành gần (15.000đ), Nội thành xa (30.000đ), Ngoại thành (45.000đ), và **Tự động miễn phí vận chuyển (Freeship)** cho đơn hàng có `subtotal >= 500.000đ`.
  - **Tự động điều tiết ca làm bánh (`Slot Capacity Limiter`)**: Giới hạn mỗi khung giờ (`morning`, `afternoon`, `evening`) trong một ngày chỉ nhận tối đa `N` chiếc bánh kem lớn (ví dụ: 15 bánh/ca). Nếu ca đó đã đầy, API tự động khóa khung giờ đó trên trang Thanh toán và gợi ý khách chuyển sang khung giờ kế tiếp.
- **Độ khó**: Trung bình. Giải quyết bài toán nghiệp vụ đặc thù của tiệm bánh tươi (Fresh Bakery Fulfillment).

### Mô hình 3: Tự động gửi Thông báo Đa kênh & Nhắc lịch theo Sự kiện (`Event-Driven Webhook / Email & SLA Escalation`)
- **Vấn đề hiện tại**: Khi khách đặt bánh xong hoặc khi Admin duyệt đơn, chưa có thông báo tự động gửi về điện thoại người quản lý hay email của khách hàng.
- **Cơ chế tự động hóa**:
  - Sử dụng `BackgroundTasks` có sẵn của `FastAPI` để kích hoạt tác vụ ngầm mà không làm chậm tốc độ phản hồi web:
    1. **Khi có đơn mới (`Order Created`)**: Tự động bắn tin nhắn qua **Telegram Bot API / Discord Webhook** về nhóm chat của tiệm (miễn phí 100%, chỉ cần 10 dòng code `urllib.request`) kèm mã đơn, tên bánh, lời chúc viết trên bánh và giờ giao.
    2. **Khi Admin đổi trạng thái (`Status Updated`)**: Tự động gửi Email xác nhận đơn hàng (qua `smtplib` Gmail App Password) tới email của khách hàng kèm hóa đơn điện tử HTML.
    3. **Tự động hủy giữ kho đơn treo (`Auto-Expire Unconfirmed Orders`)**: Tác vụ định kỳ kiểm tra nếu đơn quá 24h không liên lạc được khách thì tự động gắn cờ nhắc Admin hoặc hoàn kho.
- **Độ khó**: Thấp – Trung bình. Rất trực quan khi demo trực tiếp trước hội đồng chấm đồ án (đặt đơn trên web → điện thoại reo thông báo Telegram ngay lập tức).

### Mô hình 4: Mô hình Gợi ý Bánh & Mua kèm Tự động (`Automated Recommendation & Cross-Sell Engine`)
- **Vấn đề hiện tại**: Trang chi tiết sản phẩm và giỏ hàng mới chỉ hiển thị danh sách tĩnh, chưa tự động cá nhân hóa hoặc gợi ý mua kèm để tăng giá trị đơn hàng (AOV).
- **Cơ chế tự động hóa**:
  - **Content-Based Filtering & Rule-Based Cross-selling**:
    - Khi khách thêm một chiếc **Bánh kem lớn (`category = cake`)** vào giỏ hàng, hệ thống tự động kích hoạt thanh gợi ý *"Combo tiệc trọn vẹn"*: gợi ý thêm 2–3 món **Bánh ngọt mini (`mini`)** hoặc **Đồ uống (`drink`)** đang còn nhiều tồn kho.
  - **Collaborative / Co-occurrence Scoring từ dữ liệu thực**:
    - Truy vấn trực tiếp bảng `web_order_items` bằng SQL để tìm các cặp sản phẩm thường được mua cùng nhau nhất (`SELECT b.product_id, COUNT(*) ... GROUP BY b.product_id`) và tự động hiển thị ở mục *"Khách hàng thường mua cùng"* tại trang Giỏ hàng và Chatbot.
- **Độ khó**: Trung bình. Thể hiện tư duy ứng dụng Khoa học Dữ liệu / Hệ gợi ý (Recommender System) vào thương mại điện tử.
