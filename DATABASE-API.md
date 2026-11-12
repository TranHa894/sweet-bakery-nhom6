# Bàn giao tích hợp database/API

## Vì sao đổi server

Server Flask gốc chưa khớp payload frontend (`name/cart` so với `customer/items`); phản hồi `order_id` cũng không khớp `orderId`. create_db.py gốc chỉ tạo users nhưng server đọc products/orders/order_items. Chatbot đã có FastAPI và schema riêng. Bản này dùng một FastAPI, giữ logic chatbot, phục vụ cả frontend trên một origin.

## Tương thích chatbot hiện tại

HTML /chatbot/ được đổi URL /chatbot/static/... khi trả về, không ghi lại file chatbot. API /api/conversations, /api/chat, /api/catalog, /api/checkout, /api/order-requests và /health dùng cùng handler/session với /chatbot/api/...; vẫn kiểm tra Bearer token/conversation. API riêng ở cả hai đường dẫn có Cache-Control: no-store. Database cũ trong chatbot/runtime không bị thay thế hoặc nhập tự động.

## Database

`runtime/sweet_bakery.sqlite3` (đường dẫn tuyệt đối theo thư mục dự án; không phụ thuộc thư mục gõ lệnh). Biến `SWEET_DB_PATH` dùng cho test/đường dẫn tùy chọn.

| Bảng                                          | Vai trò                                                                                                       |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| products                                      | Mã/tên/trạng thái, payload metadata/ảnh/category; dùng chung web và chatbot                                   |
| product_variants                              | Biến thể `SPxxxx-std`, đơn giá VND, stock_quantity; nguồn giá/tồn chính                                       |
| web_orders                                    | Đơn website, họ tên/điện thoại/email, toàn bộ payload địa chỉ/yêu cầu, tạm tính, trạng thái, idempotency hash |
| web_order_items                               | Mặt hàng, quantity, snapshot tên và giá tại thời điểm đặt                                                     |
| conversations, messages, drafts               | Hội thoại chatbot                                                                                             |
| submissions, orders, order_items, tickets     | Bản ghi thử nghiệm/yêu cầu của chatbot; giữ schema gốc, không nhầm với đơn website                            |
| policies, business_settings                   | Chính sách mẫu tối thiểu đã đồng bộ với chức năng web                                                         |
| database_metadata, toppings, product_toppings | Metadata/tables chatbot gốc                                                                                   |

Web không tạo bảng Customers riêng: thông tin khách được snapshot trong đơn, phù hợp checkout không cần tài khoản. Không suy ra tài khoản người dùng từ số điện thoại. SQLite bật khóa ngoại. Mỗi lần đặt: BEGIN IMMEDIATE → kiểm tra idempotency → kiểm tra tất cả mặt hàng → tính giá từ DB → lưu đơn/chi tiết → trừ tồn → commit. Lỗi rollback toàn bộ. Hủy đơn cũng transaction và kiểm tra chuyển trạng thái để không hoàn tồn hai lần.

`initialize()` chỉ thêm sản phẩm thiếu; không reset giá, tồn hoặc đơn. Giữ schema_version=2 của chatbot; các bảng web là phần bổ sung độc lập. Không chạy lệnh reset trong chatbot/scripts/database.py với database tích hợp.

## API cùng origin

| Method/URL                   | Chức năng                                                             |
| ---------------------------- | --------------------------------------------------------------------- |
| GET /api/health              | Kiểm tra server/database                                              |
| GET /api/products            | Danh sách frontend từ SQLite: id, name, price, stock, category, image |
| POST /api/orders             | Nhận đúng payload form hiện có; yêu cầu Idempotency-Key               |
| POST /api/admin/login        | JSON password; nhận cookie HttpOnly SameSite=Strict                   |
| POST /api/admin/logout       | Hủy phiên và cookie                                                   |
| GET /api/admin/orders        | Cần đăng nhập; đơn website và danh sách bản ghi chatbot tách riêng    |
| PATCH /api/admin/orders/{id} | Cần đăng nhập; JSON status: confirmed/completed/cancelled             |
| /chatbot/api/*               | API mô-đun chatbot gốc, dùng Bearer session theo contract cũ          |
| /chatbot/                    | UI chatbot đầy đủ, iframe trong website trỏ tới đây                   |

POST /api/orders giữ hợp đồng `customer`, `shippingAddress`, `delivery`, `cakeMessage`, `note`, `paymentMethod: cod`, `consent: true`, `items: [{productId, quantity}]`. Số lượng là integer 1–99, tối đa 24 mã khác nhau, không nhận mã trùng. Chặn trường thừa như đơn giá người dùng tự gửi. Email tùy chọn; số di động Việt Nam và ngày nhận được kiểm tra ở server theo múi giờ Việt Nam. Tên, địa chỉ được trim và kiểm tra độ dài.

HTTP 201 trả `orderId` dạng chuỗi, `status`, `currency`, `subtotal`, `shippingFee: null`, `total: null`, `createdAt`, `paymentStatus: unpaid`. Retry cùng key và payload trả cùng đơn (200), không trừ tồn lần nữa. Key cũ nhưng payload khác → 409. Hết hàng/mã không tồn tại → 409. Dữ liệu sai → 422. Frontend chỉ xóa hàng đã gửi sau thành công.

Idempotency frontend hiện tồn tại trong bộ nhớ trang; reload tạo key mới. Trước khi retry sau timeout/reload, kiểm tra quản lý để tránh tạo lại một đơn đã nhận. Không có API công khai đọc thông tin khách theo mã đơn.

## Authentication và phạm vi

Mật khẩu ngẫu nhiên riêng từng máy; file runtime không public. Có thể dùng SWEET_ADMIN_PASSWORD. Session quản lý ở RAM, hết hạn 8 giờ, server restart mất session. Cookie chỉ dùng localhost HTTP; nếu triển khai Internet cần HTTPS, secure cookie, quản lý tài khoản/hash mật khẩu, giới hạn request, backup, giám sát và quy trình xử lý dữ liệu cá nhân đầy đủ. Main mặc định bind 127.0.0.1.

Iframe chỉ được yêu cầu thêm sản phẩm khi postMessage có đúng origin, đúng source iframe và mã SP tồn tại. Danh mục không tải được thì frontend dừng luồng mua, không âm thầm lấy giá từ JS cũ. Khi server đổi giá sau lúc khách mở trang, giá lúc POST từ database là giá được lưu và hiển thị lại ở kết quả.

## Kiểm thử

Tại thư mục ngoài cùng:

```
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest tests -q
```

Bộ chatbot hiện tại ở chatbot/scripts, không có chatbot/tests. Chuyển vào chatbot rồi chạy .\.venv\Scripts\python.exe -B -X utf8 -m unittest -q scripts.check_checkout scripts.check_hybrid. Bộ tests ở root kiểm tra website riêng bằng DB thử.


## Quản trị bổ sung — 04/11/2026

Giữ cookie sweet_admin và bảo vệ cùng-origin hiện có. Tất cả API dưới đây cần đăng nhập; không dùng ID như bằng chứng quyền truy cập.

- GET /api/admin/session: kiểm tra phiên hiện tại.
- GET /api/admin/overview: tổng số đơn theo trạng thái, đơn hôm nay, tiền hàng đơn hoàn tất (không xác nhận đã thu tiền), nhịp đơn 7 ngày theo Asia/Ho_Chi_Minh, tồn thấp ≤10 để cảnh báo vận hành, các bản ghi mới nhất. Ngưỡng tồn thấp là tiêu chí hiển thị quản trị, không là chính sách bán hàng.
- GET /api/admin/orders: giữ orders/chatbotRequests để tương thích. Thêm total, limit, offset; hỗ trợ q (tìm không dấu), status, dateFrom/dateTo (ngày theo giờ Việt Nam, hai đầu được tính), limit 1–500, offset ≥0 và include_requests=false để tránh tải tư vấn khi phân trang. UI dùng limit=20; giá trị mặc định API vẫn là 500.
- GET /api/admin/products: gồm cả sản phẩm tạm ẩn. Mỗi bản ghi có id/name/category/image/price/stock/active/revision.
- PATCH /api/admin/products/{id}: JSON price (integer VNĐ 0–1.000.000.000), stock (integer 0–1.000.000), active (boolean), expectedRevision (hash nhận từ lần đọc). Các giới hạn trên là ràng buộc kỹ thuật nhập liệu. BEGIN IMMEDIATE kiểm tra hash của dữ liệu hiện tại trước khi sửa. Giá/tồn/hiển thị đã đổi → 409 product_changed_reload. Không ghi đè tồn sau đơn hàng xảy ra trong lúc mở form. Không cho đổi ID, tên, nhóm hay metadata chatbot tại API này.
- GET /api/admin/requests: records có recordType consultation/ticket, id, created_at từ row lưu trữ và nội dung payload. Tối đa 100 bản ghi mỗi loại; tổng đếm ở total. Không sửa state của chatbot hay tự chuyển yêu cầu tư vấn thành đơn website.

Không cần đổi schema hoặc migrate DB: dùng lại bảng hiện có. Sửa sản phẩm chỉ ghi products.active/updated_at và product_variants.price_vnd/stock_quantity/stock_status; không xóa sản phẩm/đơn, không sửa snapshot đơn cũ. Seed lại vẫn giữ giá/tồn đã chỉnh.

CSV được tạo ở trình duyệt, chỉ xuất trang đơn đang thấy, có UTF-8 BOM và bảo vệ ô bắt đầu bằng dấu công thức. In đơn dùng hộp chi tiết hiện tại và CSS print. Không có gửi email hoặc thu tiền tự động.


## Luồng đặt đơn chung — 04/11/2026

Nguồn giỏ và chatbot đều tạo một đơn trong web_orders/web_order_items qua website_orders.place_order; không ghi bản thứ hai vào submissions. API POST /api/orders giữ nguyên payload, response bổ sung orderSource website/chatbot. Giá, snapshot, tồn kho, trạng thái và nghiệp vụ hủy dùng chung.

Thêm bảng web_order_links(order_id PK/FK web_orders, conversation_id FK conversations, draft_id FK drafts, revision, payload). UNIQUE(draft_id,revision) và web_orders.idempotency_key chống trùng; payload lưu thông tin kết quả của tool để phục hồi/tra cứu trong phạm vi chủ hội thoại. Đây là liên kết quyền sở hữu, không là bảng đơn kinh doanh thứ hai. Migration CREATE TABLE IF NOT EXISTS giữ nguyên dữ liệu cũ.

- app.api.create_app nhận order_tools_factory tùy chọn. main.py truyền create_website_order_tools; standalone không truyền nên giữ hành vi cũ.
- ConversationView/ChatView thêm checkout_mode: order khi tích hợp; request khi standalone. ChatView có order_id, còn request_id/demo_order_id giữ nghĩa cũ. CheckoutView có order_id; record_id bằng mã SB khi đã tạo đơn.
- FSM thêm ORDER_SUBMITTED: đơn đã gửi, không đồng nghĩa cửa hàng đã xác nhận. Trạng thái quản trị vẫn ở web_orders.status với pending_confirmation → confirmed → completed/cancelled.
- Tool trả kind=website_order, confirmed=true nghĩa đã xác nhận gửi và transaction tạo đơn thành công; order_status mới là trạng thái xử lý cửa hàng. Không dùng confirmed này để kết luận đã thu tiền hoặc giao hàng.
- GET /api/order-requests/{id} vẫn cần Bearer/session; adapter kiểm tra web_order_links.conversation_id rồi mới trả dữ liệu đơn. ID không là quyền truy cập. Trả order_status hiện tại từ web_orders, kể cả sau khi admin hủy.
- Form chatbot được map sang Order Pydantic dùng chung. Xác nhận bằng nút hoặc câu tự nhiên đều cần REVIEW/form hiện tại. Tool đối chiếu lại giá snapshot trong transaction, không gọi HTTP vòng về server và không gọi thêm LLM.
- Transaction gồm tạo đơn, trừ tồn, link và lưu conversation/draft; lỗi SQLite rollback toàn bộ. SAVEPOINT trong adapter ngăn tool lỗi để lại nửa đơn. Hủy đơn đang chờ xác nhận qua endpoint xác nhận riêng; đơn đã được cửa hàng xử lý đi qua hỗ trợ, không sửa thẳng bằng slot.

Yêu cầu tư vấn đã có trong submissions vẫn là lịch sử; không backfill thành đơn, không tự trừ tồn. Admin → Đơn hàng hiển thị toàn bộ đơn mới từ cả hai nguồn. Tư vấn & hỗ trợ chỉ còn phiếu hỗ trợ và các yêu cầu cũ/nguồn standalone.

ToolResult có message tùy chọn để giải thích lỗi nghiệp vụ; error vẫn giữ mã máy đọc. Chỉ trả thông báo thành công khi status=available và transaction đã được lưu.


## Vị trí / ETA / thông báo trong chat — 05/11/2026

SMTP đã gỡ theo yêu cầu; không có service, worker hoặc API gửi email. SQLite thực chưa có bảng email nên không phải xóa dữ liệu hoặc rebuild bảng đơn.

- Address có location tùy chọn: {latitude: float [-90,90], longitude: float [-180,180], accuracy: float không âm hoặc null}; chặn NaN/Infinity, bool, trường thừa. Khi không có location, tỉnh/phường/địa chỉ đầy đủ vẫn bắt buộc. Khi có location, địa chỉ chữ có thể bổ sung để chỉ dẫn phòng/tầng.
- CheckoutForm có deliveryLocation cùng schema; adapter map sang shippingAddress.location. Ghim đi cùng revision và hash form; bản xem lại/consent hiện có vẫn bắt buộc. Contact ghi nhớ vị trí đã chọn như địa chỉ; không dùng GPS liên tục.
- GET /api/store: địa điểm cửa hàng và thông số ETA công khai, không có SMTP/secret.
- POST /api/delivery/estimate: nhận location hợp lệ; tính toán local, không lưu vị trí từ bước xem thử hoặc gọi routing ngoài.
- Bảng web_delivery_updates(order_id PK/FK web_orders, payload, dispatched_at, delivered_at, updated_at) lưu ETA, thông báo và mốc giao. Không rebuild CHECK status của web_orders: trạng thái đang giao được suy từ status confirmed + dispatched_at. order_view/filter/overview/tool get_order dùng cùng trạng thái hiệu lực.
- PATCH /api/admin/orders/{id}: thêm delivering; expectedArrival tùy chọn cần ISO timezone và thời điểm tương lai. Chuỗi UI datetime-local được gửi cùng +07:00. Các chuyển trạng thái cũ vẫn hợp lệ; confirmed → delivering → completed được hỗ trợ. completed chỉ do admin ghi nhận, không tự phát hiện người nhận.
- GET /api/order-updates (và /chatbot/api/order-updates): Bearer session bắt buộc; tối đa 30 đơn của conversation hiện tại, chỉ trả mã/trạng thái/thông báo/ETA. Không trả địa chỉ, tọa độ, tên hoặc điện thoại. Standalone trả danh sách rỗng.
- OrderRequestView và CheckoutView thêm delivery_tracking; API order-requests giữ kiểm tra quyền cũ.
- Khi admin thay trạng thái, DB lưu mốc giao và một tin assistant trong messages cùng transaction. Cập nhật lặp cùng status không tạo lại thông báo; SQL lỗi rollback cả trạng thái và tin nhắn.
- Frontend polling mỗi 15 giây khi tab hiển thị, một request đang chạy mỗi lần; token cũ không cập nhật nhầm phiên mới. Không gọi model, không tự xác nhận hoặc gửi lại đơn. Lịch sử server giữ thông báo; UI nhớ dấu trạng thái theo session để tránh lặp.
- Idempotency đơn trước đây không có location vẫn tương thích khi field mới là null. Giá/tồn/đơn snapshot không bị reset.

Phụ thuộc frontend: Leaflet 1.9.4 từ unpkg (SRI), tiles OpenStreetMap có attribution; chỉ tải khi khách bấm mở map/GPS. Không reverse-geocode địa chỉ nhà bằng dịch vụ ngoài. Tham khảo: https://leafletjs.com/examples-v1/quick-start/ , https://operations.osmfoundation.org/policies/tiles/ , https://developer.mozilla.org/en-US/docs/Web/API/Geolocation/getCurrentPosition .


### Giới hạn giờ giao 08:00–18:00 — 05/11/2026

website_delivery.fit_delivery_window giữ toàn bộ khoảng ETA trong một ngày giao theo Asia/Ho_Chi_Minh; không cộng thời gian giao qua đêm. Trước mở cửa bắt đầu từ 08:00; nếu không đủ thời gian trước 18:00 chuyển khâu xử lý sang 08:00 ngày tiếp theo. Nếu cả chuyến dài quá 10 giờ thì trả cần cửa hàng xác nhận, không dựng ETA.

Order.delivery.requestedSlot và CheckoutForm.deliverySlot của đơn mới chỉ nhận morning/afternoon (hoặc trống/null). Evening cũ vẫn được đọc trong lịch sử, không tự chuyển thành khung mới. PATCH admin chặn expectedArrival ngoài 08:00–18:00 (422 delivery_hours); mốc 18:00 được giữ chính xác và cắt phần đệm để không vượt 18:00. Bắt đầu delivering ngoài 08:00 đến trước 18:00 trả409 delivery_closed; không kịp giao trong ngày trả409 delivery_exceeds_hours. Đơn cũ chọn evening cần expectedArrival hợp lệ khi confirmed (409 legacy_delivery_slot).

delivery_info chỉ đánh dấu ETA cũ ngoài giờ là chưa xác minh khi đọc, không ghi đè snapshot hay lịch sử DB. Bản đồ/GPS, thông báo chat và giao dịch trừ/hoàn tồn giữ nguyên.


### Định dạng lịch giao cho khách — 05/11/2026

website_delivery.customer_delivery_window(estimate) trả startsAt/endsAt/text để trình bày (weekday tiếng Việt, dd/mm/yyyy, HH:MM–HH:MM, giờ Việt Nam). ETA không hợp lệ/không biết trả null. Khung gốc dưới60phút được làm tròn giờ bắt đầu xuống và mở rộng tối đa2giờ, giới hạn08–18h; mốc18h có thể hiển thị17–18h. Không ghi đè earliestAt/latestAt, không dùng cửa sổ làm tròn để ra quyết định tồn/giờ giao.

Kết quả estimate bổ sung displayWindow, cùng dùng ở API preview, admin và chatbot. delivery_info tạo lại text bằng helper thay vì tiếp tục dùng thông báo phút lẻ đã lưu từ bản cũ; không rewrite DB/lịch sử khi đọc.

delivery_dates_changed so ngày Việt Nam của lịch cũ/mới, gồm năm. Khi admin cập nhật ngày, payload web_delivery_updates lưu previousEstimate và text chứa cũ/mới; tin messages dùng cùng text trong cùng transaction. Lần đầu/chỉ đổi giờ cùng ngày không gắn thông báo đổi ngày giả.

PATCH admin với status=confirmed và expectedArrival mới hỗ trợ dời lịch đơn đã confirmed; vẫn validate giờ08–18/timezone/tương lai. Cùng lịch gửi lại là no-op; không trừ tồn hoặc tạo đơn mới. Đơn completed/cancelled vẫn không được mở lại.

Thông báo luôn kèm đầy đủ order_id, lưu ý giờ giao/giao thông và cách hủy đơn đang chờ xác nhận bằng nút hoặc nhờ nhân viên với đơn đã xử lý. Chỉ khẳng định đã hủy khi transaction hủy thành công; không gọi model để định dạng.


### Hủy đơn do khách xác nhận — 05/11/2026

POST /api/order-requests/{id}/cancel (alias /chatbot/api/order-requests/{id}/cancel), Bearer token của conversation sở hữu đơn, body JSON **{"confirmed": true}** với key dùng dấu ngoặc kép. Pydantic chặn thiếu trường, false, chuỗi/số thay bool và trường thừa. Không cần gửi lại tên, địa chỉ, GPS hay đơn giá.

- Trả OrderUpdateView: order_id, status, message, updated_at, estimate, can_cancel. can_cancel chỉ true khi pending_confirmation. delivery_tracking và GET /api/order-updates cũng có cờ này; frontend không tự suy diễn quyền hủy.
- 401: phiên không hợp lệ;404: không tìm thấy hoặc không thuộc phiên (cùng thông báo);409: đơn đã xử lý hoặc adapter không hỗ trợ;422: thiếu xác nhận hợp lệ;503: SQLite lỗi. ID đơn không phải quyền truy cập.
- Adapter website cung cấp tool cancel_order. API giữ lock riêng phiên và BEGIN IMMEDIATE trước khi gọi; source standalone thiếu tool trả409 cancellation_unsupported, không tạo bản ghi hủy giả.
- website_orders.cancel_order dùng chung cho admin và khách: đọc lại trạng thái và owner, kiểm tra quyền, hoàn tồn từ snapshot web_order_items, cập nhật web_orders/web_delivery_updates và lưu messages trong một transaction. Caller commit/rollback; helper không tự commit.
- Đây là giới hạn của luồng tự phục vụ hiện tại: khách chỉ tự hủy pending_confirmation. Admin giữ quyền hủy pending/confirmed/delivering như trước. completed không hủy qua thao tác này. Gửi lại khi đã cancelled trả cùng kết quả, không hoàn tồn/ghi tin lần nữa.
- Chỉ cập nhật snapshot conversation/draft nếu nó còn trỏ đúng đơn hủy. Bản nháp mới/contact không bị ghi đè. Đơn đã hủy vẫn giữ mã, dòng hàng, lịch giao cũ và lịch sử để tra cứu; không xóa dữ liệu.
- Frontend cần hai thao tác Hủy đơn → Xác nhận hủy đơn; Giữ đơn chỉ đóng bước xác nhận. Poll không đổi không làm mất bước xác nhận đang mở. Nếu admin xử lý trước lúc POST hủy, server trả409, UI hướng nhờ nhân viên. Không gửi email, không gọi Qwen hoặc API vận chuyển.


## Tích hợp Tự động Thông báo Đa kênh & Cảnh báo SLA (Event-Driven Auto-Alert & SLA Escalation) — 12/11/2026

Mô-đun `automation_alerts.py` được kết nối trực tiếp vào `database.py`, `website_orders.py`, `main.py` và giao diện quản trị SPA (`static/admin.html`, `static/admin.js`, `static/admin.css`):

- **Bảng dữ liệu mới** (tự động khởi tạo an toàn cùng `database.initialize`):
  - `automation_settings(id PRIMARY KEY, payload, updated_at)`: lưu ngưỡng `sla_minutes` (mặc định 15 phút), `low_stock_threshold` (mặc định 20), cấu hình kênh Telegram Bot / Webhook / Email SMTP và các cờ bật/tắt thông báo.
  - `automation_events(id PRIMARY KEY AUTOINCREMENT, dedupe_key UNIQUE, event_type, severity, reference_id, channel, recipient, title, message, delivery_status, created_at)`: lưu nhật ký thông báo tự động chống trùng lặp (`INSERT OR IGNORE`).
- **Luồng phát sự kiện tự động (Event-Driven)**:
  - Khi tạo đơn hàng mới (từ Giỏ hàng Website hoặc Chatbot qua `website_orders.place_order`): tự động phát sự kiện `order_created` cho Quản lý và Khách hàng, đồng thời kiểm tra tồn kho thực tế và phát `low_stock_alert` nếu chạm ngưỡng.
  - Khi đổi trạng thái đơn (`confirmed`, `delivering`, `completed`) hoặc hủy đơn (`cancelled` từ Khách hàng hoặc Quản trị viên): tự động phát sự kiện `order_status_changed`.
- **Luồng giám sát & leo thang SLA (Time-Driven SLA Escalation)**:
  - Luồng nền `background_sla_worker` và các API quản trị tự động quét các đơn `pending_confirmation` vượt quá `sla_minutes` để gắn cờ quá hạn và phát cảnh báo `sla_breach_warning`, đồng thời đồng bộ các phiếu tư vấn (`submissions`) và phiếu hỗ trợ (`tickets`) từ Chatbot.
- **API Quản trị Auto-Alert & SLA**:
  - `GET /api/admin/automation`: trả về `settings`, `slaSummary` và danh sách `events` mới nhất.
  - `PUT /api/admin/automation/settings`: cập nhật ngưỡng SLA, ngưỡng tồn kho và cấu hình kênh thông báo.
  - `POST /api/admin/automation/scan`: quét SLA tức thì và tùy chọn phát thông báo kiểm thử (`test_alert: true`).
