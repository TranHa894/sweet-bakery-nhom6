# Dữ liệu học tập

`data/` là folder chứa file, không tự là database. Nguồn đang chạy là SQLite runtime/chatbot.sqlite3 (DATABASE_PATH). Chưa có nguồn chính thức của nhóm.

- local_demo_seed.json: 25 bánh/35 biến thể/3 topping/13 chính sách và metadata nghiệp vụ, ID ổn định, nhãn local_demo/is_mock/is_demo. Seed chỉ dữ liệu ban đầu; SQLite là dữ liệu sống sau đặt đơn.
- schema_v2.sql: bổ sung bảng vào storage v1; khóa ngoại và CHECK bảo vệ giá/tồn kho.
- mock_catalog.json, mock_order_metadata.json, sample_policies.json: fixture nhỏ giữ cho bài học và mode mock/sample.

Chạy init/seed/check bằng `python -m scripts.database` trong .venv. Seed không ghi đè ID có sẵn, stock/price/policy đã chỉnh. Sửa file seed không tự đổi SQLite đang chạy. Chỉnh policies bằng SQL tham số, tăng version; lần retrieval sau đọc nội dung/hash mới, không sửa chatbot. Reset riêng cần --confirm, backup và kiểm tra demo; xem README root.

Unknown khác hết hàng; null giá khác 0. not_listed không là chứng minh an toàn dị ứng. Giới hạn chữ/lead time/phí là metadata mô phỏng. Database runtime/backup không đưa vào Git. Không lưu liên hệ thật, API key hay thông tin thanh toán. Xem [tích hợp](../docs/data_integration.md).
