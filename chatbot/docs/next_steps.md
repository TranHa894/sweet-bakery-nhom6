# Bước tiếp theo sau hoàn thiện local

Cập nhật 06/10/2026. Chạy độc lập SQLite local_demo đã có. Lần cải thiện intent/context thêm requests/operation/few-shot và 74 nhãn (dev 48/final 26); 406 test logic đạt. Đã đo Qwen trên code cuối: dev intent 39/48, test cuối intent 20/26, scope 13/15, behavior 21/26; báo cáo giữ cả lỗi. Draft unchanged 29/29 dev và 17/17 test ở các lượt có nhãn tương ứng. Smoke lỗi gốc chạy lại sau D96 đạt 4/4 với Qwen thật. Lỗi smoke RAG rộng cũ vẫn giữ, không thay bằng số liệu NLU. **Stage 7 đánh giá tổng thể tạm hoãn**; đánh giá hẹp intent/context là yêu cầu hiện tại.

## Kiểm tra thủ công còn lại

Sau sửa 05/10/2026, chạy lệnh pytest trong terminal Windows đã báo lỗi để
xác minh `.pytest_tmp/run-...` có quyền ghi; hướng dẫn tại
docs/fixes/pytest_temp_permissions.md. Trong phiên công cụ,21 test ngữ cảnh
đạt và356 test đạt khi mô phỏng nhánh Temp bị chặn. Không cần restart API
cho thay đổi cấu hình test này.

1. Dừng server cũ rồi chạy README, browser Chrome/Edge thử local_demo, empty, mock; labels/cards/sources/loading/error, REVIEW edit/confirm, Hội thoại mới, màn hình nhỏ.
2. Thử lỗi Ollama: giữ draft, báo thử lại; không tự rule/confirmed. Empty không sản phẩm bịa/chính sách demo như thật, lưu yêu cầu chờ tư vấn.
3. Token khác không đọc conversation/order; restart cần session mới. UI chữ khách render textContent, cần kiểm DOM/XSS thật.
4. CLI /draft /orders /order, restart /resume, test fake contact. Không reset database đang dùng; nếu reset có --confirm/backup.
5. Thử A–F trong docs/fixes/context_product_scope.md trên UI: đặt socola rồi hỏi dâu trong **cùng hội thoại**, không bấm Hội thoại mới giữa hai câu. Sau giá/bảo quản dâu, draft socola giữ nguyên. Thử tham chiếu rõ/mơ hồ, hỏi hai bánh và đổi sản phẩm làm mất REVIEW; hai tab/phiên không lẫn dữ liệu.
6. Chạy lại smoke rộng Qwen khi cần đánh giá luồng đầy đủ sau cập nhật prompt giờ mở cửa; giữ các lần thất bại. Chưa thay kiểm thử chức năng bằng kết luận độ chính xác model.
7. Đọc report intent/context cùng bài học mới: lượt modelerror phải giữ draft/noorder. Không tối ưu thêm theo nhãn final đã chấm; nếu sửa tiếp, mở rộng dev và chuẩn bị final mới độc lập. Kiểm trên UI câu vừa đổi bánh vừa hỏi giá bánh khác, size riêng, phủ định, thêm/xóa, REVIEW invalidation.

Công cụ browser không khả dụng trong lần triển khai này; chỉ HTTP và TestClient đã kiểm, không nói UI nghiệm thu bằng mắt.

## Giới hạn còn tồn tại

- Một loại bánh/variant mỗi draft; quantity nhiều, nhiều loại hỏi chọn rõ. Chưa giỏ nhiều dòng.
- Qwen vẫn sai ở viết tắt, phủ định, đổi loại, hand-off hoặc slot nhiều trường; dev có 7/48 lượt bị validation/grounding từ chối và test cuối có 5/26. Operation thêm/xóa model thật 0/2, request binding 1/3. Retry tối đa một lần, guard giữ draft khi lỗi; test logic đạt không chứng minh model đã ổn định. Các lần đo cũ giữ trong previous_runs.
- Context prompt rút gọn, chưa hỗ trợ chắc mọi phép tính tương đối/viết tắt/phủ định/liên kết. CurrentTurn/focus/order draft tách riêng; có first/second/last/cheaper/order trên kết quả đã xác minh, mơ hồ hỏi lại. Hỏi nhiều bánh không có nghĩa draft hỗ trợ nhiều dòng.
- RAG có thể chọn nguồn thừa; quote/ID hợp lệ không chứng minh đúng nghĩa. Embedding chưa tải/chạy, development cũ không đại diện corpus mới.
- Dị ứng đi ticket thận trọng; không cam kết sức khỏe. Liên hệ chỉ giả DEMO/TEST; chưa PII detector hoàn chỉnh.
- API token/lock RAM, 1worker, TTL8h/cap200; chưa login/resume web bền/đa worker/rate-limit/HTTPS. CLI local resume không là auth. Không nhiều writer cùng conversation; test cạnh tranh stock không thay stress test hệ thống.
- Ticket pending local, chưa thông báo nhân viên bên ngoài. Đơn unpaid, không gọi giao/thanh toán.
- Có warning Starlette/HTTPX deprecation; chưa thay dependency để bỏ warning.
- Chưa backend/menu/chính sách thật; không tự chuyển DEMO thành thật, không tự deploy/model download.

## Khi nhóm cung cấp backend

Chốt schema/ID mapping/capabilities, endpoint/auth/quyền tạo & tra đơn, giá/stock chuẩn, quote/transaction/idempotency. Thay repo/knowledge/tool factory theo data_integration.md, provider duy nhất, read-only không nhận đơn. Tạo phiên nguồn mới, backup/archive SQLite demo, chạy regression và UI/model smoke. Không tạo adapter giả success trước contract.

## Điều kiện bắt đầu stage 7 khi được yêu cầu

Đọc AGENTS nếu có và docs/code hiện tại, suite đạt; bổ sung UI nghiệm thu; chốt development/held-out độc lập, tiêu chí accuracy/abstention/citations/FSM/latency và nhãn dữ liệu. Không dùng gold trong retrieval/prompt. Người học nắm repository/Pydantic/FSM/SQLtransaction/context/token. Không cần backend thật để đánh giá local demo, nhưng không gán số liệu demo cho production.
