# Bàn giao cho thành viên database/server

## 1. Bật kết nối

Trong `config.js` đổi:

```js
window.SWEET_CONFIG = {
  mode: "api",
  ordersEndpoint: "/api/orders",
  requestTimeoutMs: 15000,
};
```

Phục vụ frontend và API cùng origin là đơn giản nhất. Nếu API khác origin, cấu hình CORS cho đúng origin frontend, method POST và các header `Content-Type`, `Idempotency-Key`; không mở tùy tiện nếu không cần. Hiện frontend không gửi cookie cross-origin và chưa có authentication.

## 2. POST /api/orders

Headers: `Content-Type: application/json`, `Idempotency-Key: <mã duy nhất>`.
Body thực tế frontend gửi:

```json
{
  "customer": {
    "fullName": "Khách kiểm thử",
    "phone": "0912345678",
    "email": null
  },
  "shippingAddress": {
    "province": "Hà Nội",
    "ward": "Phường kiểm thử",
    "addressLine": "123 Đường kiểm thử"
  },
  "delivery": {
    "requestedDate": "2026-12-20",
    "requestedSlot": "afternoon"
  },
  "cakeMessage": "Chúc mừng sinh nhật!",
  "note": "Gọi trước khi giao",
  "paymentMethod": "cod",
  "consent": true,
  "items": [{ "productId": "SP0024", "quantity": 2 }]
}
```

`requestedSlot`: null, `morning`, `afternoon`, `evening`; date có thể null. Thời gian dự kiến theo giờ Việt Nam. Email có thể null. Tiền là số nguyên VND, không dùng chuỗi định dạng hoặc số thực cho tiền.

Server phải tự đọc đơn giá từ Products, kiểm tra trạng thái bán/tồn kho, số lượng nguyên 1–99, dữ liệu khách và địa chỉ, tính tiền và phí giao hàng. **Không tin giá/tổng tiền ở frontend, localStorage hoặc file JSON demo.** POST chỉ gửi id và quantity. Nếu chưa tính được phí giao hàng, trả null và trạng thái chờ xác nhận; không coi null là miễn phí.

## 3. Phản hồi thành công

HTTP 201 (HTTP 200 khi trả lại cùng một đơn do retry cũng được):

```json
{
  "orderId": "SB-2026-000001",
  "status": "pending_confirmation",
  "currency": "VND",
  "subtotal": 700000,
  "shippingFee": null,
  "total": null
}
```

`orderId` bắt buộc là chuỗi không rỗng. Frontend chỉ báo đã gửi yêu cầu sau khi response 2xx có JSON hợp lệ và mã đơn. Nó hiển thị mã đơn; giá trị server trả được giữ trong `serverSummary` của file tải xuống. Frontend không thông báo “đã thanh toán”.

Phản hồi lỗi dùng JSON và status phù hợp: 400/422 cho dữ liệu sai; 409 cho hàng/giá không còn phù hợp; 429 quá nhiều yêu cầu; 500 lỗi server. Gợi ý body `{ "code": "OUT_OF_STOCK", "message": "..." }`. Giao diện hiện hiển thị thông báo lỗi an toàn chung, riêng 409 nhắc kiểm tra sản phẩm/giá; không tự áp dụng sửa giá từ lỗi server.

## 4. Chống trùng và lỗi kết nối

- Khóa nút/form trong lúc request; timeout 15 giây.
- Cùng payload được thử lại trong cùng trang dùng lại Idempotency-Key; sửa payload sẽ tạo key mới.
- Server phải đặt UNIQUE trên key và tạo đơn + chi tiết + giữ tồn kho trong cùng transaction. Cùng key/body trả lại cùng đơn; cùng key khác body trả 409.
- Timeout không chứng minh server chưa tạo đơn. Đừng tạo đơn mới mỗi lần retry cùng key.
- Sau thành công frontend trừ số lượng đã gửi khỏi giỏ, giữ phần thêm ở tab khác. Lỗi giữ form/giỏ.
- Key hiện nằm trong bộ nhớ trang: reload có thể tạo key mới. Khi làm sản phẩm thật nên bổ sung vòng đời checkout/token và API tra cứu trạng thái để khôi phục qua reload.

## 5. Gợi ý database (độc lập hệ quản trị)

| Bảng                 | Cột chính                                                                                                                                                                                                                                                  |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Categories           | id PK, name                                                                                                                                                                                                                                                |
| Products             | id PK (chuỗi SP...), category_id FK, name, price_vnd integer, image_url, is_active, stock_quantity                                                                                                                                                         |
| Customers (tùy chọn) | id PK, full_name, phone, email                                                                                                                                                                                                                             |
| Orders               | id PK, customer_id nullable FK, customer_name, phone, email, province, ward, address_line, requested_date, requested_slot, cake_message, note, payment_method, status, subtotal_vnd, shipping_fee_vnd nullable, total_vnd nullable, consent_at, created_at |
| OrderItems           | id PK, order_id FK, product_id FK, product_name_snapshot, unit_price_vnd, quantity, line_total_vnd                                                                                                                                                         |
| OrderRequests        | idempotency_key UNIQUE, payload_hash, order_id FK, created_at                                                                                                                                                                                              |

Snapshot tên/giá và địa chỉ trong đơn giúp giữ lịch sử khi sản phẩm hoặc khách thay đổi. Cho phép khách mua không cần đăng nhập. Không xem số điện thoại là bằng chứng định danh tài khoản.

Seed 24 sản phẩm từ `products.json`, category `cake` / `mini` / `drink`. Các giá giữ từ giao diện gốc để nhóm kiểm thử; server là nguồn giá chính khi triển khai. Frontend hiện dùng danh mục tĩnh, chưa gọi GET /api/products. Có thể thay mảng `SWEET_PRODUCTS` bằng kết quả API catalog trong bước tiếp theo.

## 6. Kiểm thử thủ công khi nối server

1. Tạo đơn hợp lệ, kiểm tra đúng số dòng, số lượng và giá server trong DB.
2. Gửi lại cùng Idempotency-Key và body: chỉ có một đơn.
3. Gửi mã SP không tồn tại, quantity 0/âm/thập phân/100, email/số điện thoại/địa chỉ sai: server từ chối.
4. Giả lập mất mạng, timeout, response không phải JSON: form/giỏ còn nguyên, không báo thành công giả.
5. Thay giá/tồn kho giữa lúc chọn và gửi: server quyết định, không lấy giá client.
6. Xác nhận phí và lịch giao trước khi chuyển trạng thái đơn.
