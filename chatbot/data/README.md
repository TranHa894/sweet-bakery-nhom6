# Dữ liệu trong chatbot

Mặc định DATA_SOURCE=group_files: menu đọc trực tiếp từ ../static/products.json của website nhóm. Không chép/ghi lại file này; NLU/FSM chỉ gọi repository.

Các file ở data phục vụ chế độ demo cũ và cấu hình AI:
- local_demo_seed.json: 25 bánh/35 biến thể/13 chính sách mô phỏng để seed SQLite local_demo.
- schema_v2.sql: cấu trúc SQLite chatbot, không dùng để tạo database sản phẩm của nhóm.
- mock_catalog.json, mock_order_metadata.json: fixture 5 bánh và metadata mẫu cho mode mock.
- sample_policies.json: điều khoản mô phỏng cho KNOWLEDGE_MODE=sample.
- nlu_few_shots.json: ví dụ trích ý định/slot cho prompt Qwen, không phải menu nguồn.

data là thư mục file. Database lưu hội thoại/bản nháp/yêu cầu/đơn demo nằm ở runtime/chatbot.sqlite3. Menu nhóm chưa có size/tồn kho/allergen/chính sách; giữ null/unknown, không lấy metadata của bánh demo ghép sang mã SP của nhóm.
