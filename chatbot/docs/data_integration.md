# Kết nối backend nhóm sau local demo

Cập nhật 06/10/2026. Hiện catalog/policy/business tools đọc ghi SQLite local_demo; chưa nguồn chính thức. Không tự tạo adapter API giả hoạt động. data/local_demo_seed.json chỉ seed; SQLite đang chạy mới là nguồn demo sống. Controller intent/context mới vẫn gọi các interface hiện có; contract cho từng scope ở phần cuối tài liệu.

## 1. Interface cần thay

| Nhóm | Interface đang gọi | Local adapter / điểm nối |
| --- | --- | --- |
| Catalog | search_products(filters), get_product(product_id), get_capabilities() | LocalCatalogRepository; factory repositories/catalog.py |
| Metadata nghiệp vụ | get_order_metadata(product_id), get_business_settings() | LocalCatalogRepository, OrderMetadataRepository |
| Knowledge | get_policy_documents(); KnowledgeRepository.get_knowledge() | LocalCatalogRepository → LocalKnowledgeRepository; factory knowledge_loader.py |
| Tools | check_availability(draft), calculate_quote(draft), submit_order_request(draft,key), get_order(id), create_handoff_ticket(...) | create_order_tools closures trong order_service.py |

Tên submit_order_request giữ contract cũ, có ý nghĩa submit_order và trả kết quả phù hợp mode. Sau này factory chọn provider backend thật, không đổi FSM/API. Code SQLite chỉ nằm repo/storage/local business tools/scripts, không NLU/prompt/FSM/route/UI. Repo/tool không có khả năng được trả unsupported, không giả success.

search_products nhận **filters của current_turn**, không lấy danh sách sản phẩm trong draft làm mục tiêu cho mọi câu hỏi. Backend adapter chỉ đối chiếu IDs/filters được caller gửi; không tự cộng sản phẩm từng xuất hiện trong history. conversation_context giữ tham chiếu và order draft giữ yêu cầu riêng. Các scope không đổi interface nguồn; xem docs/fixes/context_product_scope.md.

Sau cải thiện 05/10/2026, một tin nhắn có thể tạo nhiều requests, mỗi query có intent/size/IDs riêng. Adapter phải chịu được nhiều lần đọc độc lập, không gộp size hoặc mục tiêu đơn vào tất cả query. Mention canonical chỉ hợp lệ khi alias trong câu xác định duy nhất cùng ID; backend cần trả alias và xử lý trùng tên rõ. order_product_mentions/order_operation vẫn là đề xuất NLU, không mở quyền create order. Chạy thêm regression intent/context và bộ cuối mới phù hợp nguồn thật; dữ liệu final demo hiện có không chứng minh backend production đúng.

## 2. Mapping dữ liệu và quyền

Thống nhất với nhóm ID external sản phẩm/variant/topping → internal ID ổn định, alias/name, active, giá nguyên VNĐ hoặc null, servings, stock known/unknown, timestamp/version, metadata/allergen. Không dùng tên bánh làm ID hay đoán variant gần giống. Order snapshot giữ ID nguồn/source và tên/giá lúc đặt. Lưu external_order_id để tra cứu, không đồng nhất UUID demo với mã backend.

Capabilities hiện can_accept_real_orders=false. Nguồn chỉ đọc menu không tự bật tạo đơn, dù dữ liệu đầy đủ. Khi có backend, cần **tool create/quote/availability có quyền và xử lý server thật**, không chỉ đổi một cờ. Thống nhất ai kiểm tra stock/lead/giờ/topping/allergen/giá cuối, ai có quyền tạo/tra đơn, auth service và quyền khách. Không để model tự gọi endpoint tùy ý. Bí mật lấy cấu hình bảo vệ, không ghi code/log/docs.

Order tool get_order phải nhận owner hợp lệ hoặc scope được closure ràng buộc; backend kiểm quyền nữa. ID record/conversation không là auth. Token demo RAM không thay hệ thống tài khoản nhóm. Mapping conversation/order/customer cần contract riêng, không lấy user_id do LLM sinh.

## 3. Nguồn chuẩn và chống double-write

Backend là nguồn chuẩn cho giá/tồn kho/khả năng nhận đơn thật. Quote/review lưu revision/fingerprint hoặc quote_token từ backend; xác nhận kiểm lại. Backend phải tạo đơn và trừ/giữ tồn atomically với idempotency key; HTTP timeout không chứng minh đơn chưa tạo, truy vấn theo key trước retry. Không thực hiện check stock và create tách rời để gọi là an toàn.

Chọn **một order provider** theo cấu hình. Khi provider backend, không đồng thời submit SQLite demo và backend rồi coi cả hai là đơn. SQLite có thể chỉ lưu trace/cache tham chiếu external ID, không nhận trách nhiệm trừ kho/tạo đơn thứ hai. Không retry vô hạn. Lỗi nguồn phân biệt error/unknown/unsupported/unavailable, không biến thành thành công hoặc quay sang demo im lặng.

## 4. Chuyển SQLite demo

Backup và giữ archive demo để học, đặt DATABASE_PATH file riêng nếu cần. Không tự chuyển seed/DEMO orders/tickets/contact TEST thành đơn thật. Dùng conversation mới khi chuyển data source, tránh mang product_id/review/quote cũ sang nguồn khác. Chỉ migrate record nào được nhóm phê duyệt có quy tắc rõ; không bỏ is_demo để gọi thật. Schema v1→v2 hiện giữ submissions ID và thêm orders cùng ID, không nhân đôi business order.

## 5. Chính sách thật và phiên bản

Chỉ nạp chính sách nhóm phê duyệt qua knowledge adapter riêng, với policy_id/title/content/version/is_mock=false có provenance. Giữ một điều khoản một chunk, version/hash thay khi nội dung đổi. Qwen nhận tài liệu như dữ liệu; validate source/quote không đủ chứng minh nghĩa đúng. Không dùng 13 điều khoản demo cho đơn thật. Chỉnh policies SQLite demo bằng SQL tham số + tăng version; seed lại cố ý không overwrite record cũ.

Embedding tùy chọn sau: chỉ tải khi được yêu cầu, pin model/revision, CPU/vector/cosine local, index manifest có model/corpus hash/version, xây lại khi corpus/model đổi. Hiện keyword retrieval chạy được; chưa embedding/reranker/hybrid. Bộ development cũ 27 câu thuộc sample policies không đại diện corpus13 local demo, không gán kết quả đó cho backend/corpus mới.

## 6. Regression trước đổi provider

Chạy toàn suite fake/DB riêng, contract fixture backend và smoke model thật. Chạy lại: seed/migration; giá/size/budget/active/allergen; multi-intent/reference; natural slots/delta/clear; variant/topping/stock/unknown; lead/openinghours/Unicode; thiếu slot/review revision/consent kèm sửa; repeated confirmation/idempotency; rollback partial/concurrent oversell; modelerror giữ state; owner/isolation/restart; policy source/no-source; handoff/outsidehours/complaint. Với backend thêm HTTP status/timeout/auth/quoteexpiry/idempotency reconciliation/partialoutage.

Giữ regression tests/test_context_product_scope.py: đặt A → hỏi B chỉ trả B và draft A không đổi; tham chiếu rõ/mơ hồ; đổi bánh kiểm lại size/topping và REVIEW; hỏi nhiều bánh đủ kết quả; hai phiên tách biệt. Adapter mới có alias khác vẫn phải đạt các hành vi này bằng fixture nguồn tương ứng.

Thử UI bằng browser thật, tab/token khác không đọc record. Backend read-only phải submit unsupported. Không kết luận fake test là model accuracy hay ID nguồn hợp lệ là policy answer đúng. Stage 7 chất lượng tổng thể vẫn cần phạm vi riêng.
