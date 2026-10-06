# Đặc tả hiện tại — chatbot local demo

Cập nhật 06/10/2026. Hoàn thiện chạy độc lập sau stage 6 và cải thiện intent/context theo yêu cầu; stage 7 đánh giá tổng thể **tạm hoãn**. Python 3.12.10, Windows/VS Code/.venv; ưu tiên hàm/dictionary dễ học, class cho repository/Protocol/Pydantic.

## Mục tiêu và phạm vi

- Tìm/tư vấn bánh từ interface catalog, không hardcode dữ liệu vào NLU/prompt/FSM/route/UI.
- Hỏi chính sách bằng RAG có nguồn/version, thiếu nguồn nói chưa đủ thông tin.
- Hội thoại nhiều lượt, Qwen hiểu intent/slot; code kiểm tra dữ liệu/REVIEW/consent.
- Tách current_turn (đối tượng câu hỏi hiện tại), conversation_context (tham chiếu) và order_draft (key order). Hỏi giá/bảo quản bánh khác không sửa đơn; tên rõ ưu tiên, tham chiếu mơ hồ hỏi lại. Sửa đơn rõ ràng tăng revision và bỏ REVIEW cũ.
- Đặt đơn DEMO/unpaid và handoff local, lưu context qua restart CLI.
- CLI độc lập và API/UI stage 6 dùng chung controller.
- Đánh giá định lượng là mục tiêu toàn đồ án. Lần cải thiện hiện tại có bộ hẹp74lượt có nhãn (dev48/final26), test fake và Qwen thật riêng; không là đánh giá tổng thể giai đoạn7 hoặc RAG accuracy.

Chưa làm thanh toán/giao thật, nhận diện ảnh, huấn luyện/fine-tuning LLM, cá nhân hóa lịch sử mua, website quản trị, backend thương mại điện tử đầy đủ, production login, deploy, Redis/Celery/microservices/framework agent.

## Trạng thái dữ liệu và công nghệ

| Thành phần | Hiện tại |
| --- | --- |
| Menu/chính sách/backend chính thức | Chưa có; sẽ nối adapter sau |
| Database local | sqlite3, SQLite schema v2, cùng file lưu catalog/policy/conversation/draft/demoorder/ticket, trách nhiệm module tách riêng |
| Seed mô phỏng | 25 bánh / 35 biến thể / 3 topping / 13 chính sách, ID ổn định, is_demo/is_mock/source |
| Fixture cũ | mock 5 bánh/sample 5 điều khoản giữ cho bài học/test |
| Model | Qwen local qwen3.5:4b đã cài, không tải/đổi model; Ollama HTTP loopback |
| Retrieval | Từ khóa, top_k tối đa 3, policy_id/version/hash; embedding chưa triển khai |
| Dependencies | requirements hiện có: Pydantic/FastAPI/Uvicorn/tzdata/pytest/HTTPX; không thêm ORM hay AI nặng |
| Lưu trữ | UTC; nhận/hiển thị Asia/Ho_Chi_Minh; pathlib cho đường dẫn |

Default DATA_SOURCE=local_demo, ORDER_PROVIDER=local_demo, KNOWLEDGE_MODE=local_demo, CHAT_MODE=ollama, DATABASE_PATH=runtime/chatbot.sqlite3. Alias CATALOG_MODE/CHATBOT_DB_PATH vẫn hỗ trợ khi biến mới chưa có; .env chưa tự nạp. Không tải model khi thiếu. data là folder seed/schema, **SQLite runtime mới là database**.

## Kiến trúc và bảo đảm hành vi

Entry CLI/API → conversation.handle_message → Qwen structured output → Pydantic + căn cứ câu gốc → repository xác minh mention/ID → context/FSM → RAG hoặc order tools → response có nhãn dữ liệu.

Qwen đề xuất intent, action và delta. Slot chưa nói giữ nguyên, updates thay đổi, clear_slots xóa rõ. Không keyword fallback khi AI lỗi. Chỉ CHAT_MODE=rule chủ động chạy offline. Lỗi model không đổi draft/state và không tạo đơn; retry JSON/grounding tối đa một lần. Lịch sử/slots riêng khách, lịch sử hữu hạn, prompt context rút gọn tránh copy dữ liệu cũ.

Output có requests riêng cho từng đối tượng/intent/size, order_product_mentions và operation riêng cho đặt/sửa/thêm/xóa. Tên canonical chỉ được chấp nhận qua alias duy nhất cùng sản phẩm. Few-shot bánh A/B/C không chứa menu/gold final; hint từ vựng catalog không sinh intent/IDs thay Qwen. Hỏi thông tin có thể xen giữa thu thập đơn; thêm loại thứ hai hỏi lại vì draft hiện chỉ một loại, không âm thầm thay thế. Nếu yêu cầu thêm làm REVIEW chưa rõ, REVIEW cũ mất hiệu lực.

Một sản phẩm/biến thể mỗi bản nháp, quantity nhiều. Đề cập nhiều loại hỏi chọn; không âm thầm bỏ loại. BROWSING → COLLECTING → REVIEW → DEMO_CONFIRMED, CANCELLED/HANDOFF. Sửa revision xóa review cũ; đồng ý kèm sửa phải xem lại. Confirmed bất biến, sửa/hủy chuyển ticket.

Source chuẩn cho giá/stock/allergen/metadata là database demo, không kiến thức Qwen. Unknown không biến thành hết hàng/giá0/an toàn dị ứng. Dị ứng đi ticket thận trọng; not_listed không bảo đảm an toàn. Chỉ liên hệ giả DEMO/TEST. Topping/phí chữ mỗi bánh, phí giao mỗi đơn theo business settings.

Xác nhận yêu cầu REVIEW hiện tại và kiểm tra cuối trong transaction SQLite: active/variant/topping/stock/lead/giờ nhận/chữ/liên hệ/quote. BEGIN IMMEDIATE, UPDATE stock có điều kiện, UNIQUE idempotency key; stock/order/item/context cùng commit hoặc rollback. Đơn có snapshot/is_demo/source/payment_status=unpaid, không gọi dịch vụ ngoài.

API token256bit owner/TTL8h/lock riêng phiên, một worker; không coi UUID là auth. Route đồng bộ threadpool. UI textContent. CLI resume local không đem lên web. Migration v1 có backup, giữ dữ liệu và ID, không retro-trừ kho đơn cũ. Seed lặp không overwrite tồn; reset riêng --confirm/verifieddemo/runtime/backup.

Kết quả thực tế và phần chưa kiểm tra tại progress.md. Cần tự kiểm UI trình duyệt, đánh giá rộng Qwen/RAG, contract backend và chạy regression trước tích hợp. Không tuyên bố production.
