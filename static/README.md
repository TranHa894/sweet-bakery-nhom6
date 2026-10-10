# Sweet Bakery — giao diện Nhóm 6

## Chạy thử

1. Giải nén toàn bộ `Sweet-Bakery-hoan-thien.zip`, giữ nguyên các thư mục.
2. Mở thư mục `Sweet-Bakery` bằng VS Code.
3. Dùng **Live Server → Open with Live Server** trên `index.html`.
   Nếu đã có Python, chạy `python -m http.server 5500` trong thư mục rồi mở `http://localhost:5500`.
4. Chọn bánh → Thêm vào giỏ → Giỏ hàng → Nhập thông tin giao hàng → Tạo đơn hàng mẫu.

Có thể mở trực tiếp index.html để xem, nhưng nên chạy bằng HTTP để giỏ hàng được chia sẻ ổn định giữa các trang. Không cần npm, framework hoặc database để thử giao diện. Ảnh đã có sẵn trong `images/`.

## Chức năng đã hoàn thiện

- Tất cả 24 sản phẩm dùng mã SP, tên và giá từ cùng một danh mục.
- Thêm hàng từ trang chủ, danh mục và chi tiết; cộng dồn cùng mã SP.
- Trang chi tiết cho mọi sản phẩm qua `chi-tiet-san-pham-demo.html?id=SP0024`; không truyền id thì xem Mousse Chanh leo.
- Mua ngay dùng đúng số lượng đã chọn và mở thông tin giao hàng.
- Giỏ hàng lưu trong localStorage: tăng/giảm, nhập số lượng nguyên 1–99, xóa một hoặc toàn bộ, tổng tiền, số lượng trên header, trạng thái trống.
- Đọc được giỏ hàng cũ theo tên; bỏ qua dữ liệu không hợp lệ. Không dùng giá do localStorage cung cấp.
- Tìm kiếm tên có/không dấu trên toàn bộ danh mục; sắp xếp giá/tên trước khi phân trang; giữ tiêu chí khi chuyển trang.
- Form tên, số di động Việt Nam, email tùy chọn, tỉnh/thành phố, phường/xã, địa chỉ cụ thể, ngày/giờ nhận, lời chúc, ghi chú và đồng ý xử lý đơn.
- Chặn trường trống, tên/địa chỉ chỉ có khoảng trắng, số điện thoại sai, email sai, ngày nhận quá khứ và gửi đơn khi giỏ trống.
- Responsive, nhãn form, điều hướng bàn phím, thông báo thêm giỏ không chặn màn hình.
- Loại bỏ nút tài khoản/cửa hàng giả và hotline mẫu. Chưa triển khai đăng nhập vì chưa có dịch vụ tài khoản.

## Chế độ mẫu và dữ liệu cá nhân

`config.js` mặc định `mode: 'demo'`. Tạo đơn chỉ tạo đối tượng trong bộ nhớ của trang, hiển thị kết quả và cho tải JSON. **Không gửi đơn, không thu tiền, không tạo bản ghi database.** Giỏ hàng vẫn được giữ để thử tiếp.

Tên/địa chỉ/điện thoại không lưu vào localStorage. Reload trang sẽ mất form và kết quả mẫu. JSON tải xuống có thông tin vừa nhập: khi thử nhóm nên dùng dữ liệu giả.

Tạm tính chưa gồm phí giao hàng. Ngày/giờ là yêu cầu, chưa bảo đảm được cửa hàng chấp nhận. Chỉ có COD trong giao diện hiện tại.

## File chính

| File                               | Vai trò                                      |
| ---------------------------------- | -------------------------------------------- |
| index.html                         | Trang chủ                                    |
| banh-kem-p1.html, banh-kem-p2.html | Danh mục bánh kem                            |
| banh-mini-p1.html, do-uong-p1.html | Danh mục bánh nhỏ, đồ uống                   |
| tim-kiem.html                      | Tìm trên toàn bộ danh mục                    |
| chi-tiet-san-pham-demo.html        | Chi tiết theo query id                       |
| gio-hang.html                      | Giỏ hàng                                     |
| thanh-toan.html                    | Form và kết quả đơn                          |
| script.js                          | Tất cả xử lý giao diện, giỏ và gửi đơn       |
| products.js                        | Danh mục chạy trong trình duyệt              |
| products.json                      | Dữ liệu cùng danh mục để seed database       |
| config.js                          | Chế độ demo/API, URL API và timeout          |
| API-HANDOFF.md                     | Hợp đồng API và gợi ý bảng database          |
| style.css                          | CSS gốc và phần responsive/hoàn thiện ở cuối |
| images/, bannerr.webp              | Ảnh sản phẩm và banner                       |

Nếu đổi danh mục, sửa `products.json` rồi đồng bộ nội dung sang `products.js` (gán mảng cho `window.SWEET_PRODUCTS`). Các mã có khoảng trống là chủ ý: giữ SP0024 cho Mousse Chanh leo; mã này phải thống nhất với database.

## Những phần còn thuộc server

Database, xác minh tồn kho/giá, phí vận chuyển, lưu đơn, trạng thái đơn, thông báo cửa hàng, đăng nhập và thanh toán online. Xem `API-HANDOFF.md` trước khi bật API. Các giá hiện tại giữ theo file của nhóm, không phải bảng giá Fresh Garden hiện hành.

## Hình ảnh và tham khảo

Giữ banner người dùng cung cấp; ảnh lấy từ các URL đã có trong các file gốc và đóng gói thành WebP để chạy ổn định. URL gốc nằm trong trường `sourceImage`. Một số ảnh/banner vẫn có dấu thương hiệu Fresh Garden. Đây là giao diện bài tập Sweet Bakery; nhóm nên thay bằng ảnh riêng khi triển khai thương hiệu thực tế.
Tham khảo tổ chức danh mục, tìm kiếm và giỏ hàng tại https://www.freshgarden.vn/ (10/10/2026).
