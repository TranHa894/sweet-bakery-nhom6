# Kết quả kiểm thử bản tích hợp — 11/10/2026

## Kiểm tra trước khi cập nhật main — 09/11/2026

- Chạy lại đạt63/63 ca đơn hàng/admin/giao hàng và139/139 ca hybrid/form bằng unittest.
- Chạy lại20/20 ca API/checkout có sẵn bằng runner thư viện chuẩn, giữ assertions và parameterization; chưa cài pytest. Tổng222 ca đạt, dùng model fake và database tạm.
- Cú pháp34 file Python thay đổi, các file JSON và7 file JavaScript chính đều hợp lệ; git diff --check đạt.
- Không chạy lại Qwen thật hoặc trình duyệt trong lần chuẩn bị Git này. Các kết quả Chrome bên dưới là những lần kiểm tra trước, không tính vào222ca.
- Không đưa .env, mật khẩu admin, database/runtime, môi trường ảo hay cache lên GitHub.


## Hủy đơn trong chatbot — 05/11/2026

- **37/37 test_delivery,14/14 test_unified_orders,12/12 test_admin đạt**: tổng63 unittest dùng SQLite tạm riêng.10 ca mới kiểm tra tự hủy đang chờ, quyền phiên, xác nhận strict, chặn trạng thái đã xử lý, retry/alias, rollback nhiều món khi SQL lỗi, admin/khách hủy đồng thời, tranh chấp xác nhận–hủy, giữ bản nháp mới/contact và khởi động lại.
- **13/13 bước Chrome headless đạt** với HTTP/FastAPI/SQLite thật ở DB QA riêng: nút hủy, xác nhận/giữ đơn, polling không làm mất bước xác nhận, ghi trạng thái/ẩn nút, reload, đơn cũ khi form ẩn, admin xác nhận trong lúc đang hủy, từ chối hủy lỗi thời, viewport390px không tràn ngang và không exception JavaScript.
- Kiểm tra import/khởi động app bằng TestClient và server QA thật; cú pháp chat.js đạt. Không gọi Qwen, gửi email hay tạo/hủy đơn trong database đang dùng. Không cài dependency hoặc tạo mới docs.
- Chưa thử trên điện thoại vật lý/Cốc Cốc/tunnel. Luồng câu tự nhiên nhờ hủy vẫn là yêu cầu hỗ trợ; thao tác tự hủy mới dùng nút xác nhận. Token vẫn theo phiên RAM hiện tại; server restart/phiên hết hạn cần nhân viên hỗ trợ đơn cũ.
- Lệnh chạy kiểm thử: .\chatbot\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -p test_delivery.py -v (thay pattern bằng test_unified_orders.py hoặc test_admin.py để chạy từng nhóm).
- TestClient có cảnh báo deprecation httpx từ Starlette; không có kiểm thử thất bại. Không đổi thư viện chỉ để bỏ cảnh báo trong lần sửa này.


## Định dạng ngày giao và dời lịch — 05/11/2026

- 27/27 test_delivery đạt: 8 ca mới về thứ/ngày/năm/giờ Việt Nam, làm tròn10:23–10:33thành10–12h, biên18h, UTC/chuyển năm/Chủ Nhật, không sửa ETA gốc, mã đơn/cách hủy/lưu ý giao thông, đổi ngày cũ/mới, cập nhật lịch đãconfirmed, chống lặp và lưu tin chat.
- 14/14 test_unified_orders và12/12 test_admin đạt; tổng53kiểm thử với DB thử riêng. Không gọi Qwen, dịch vụ bản đồ hay sửa đơn thật.
- Kiểm tra import Python, cú pháp JavaScript và diff whitespace đạt. Chưa chạy lại Chrome/điện thoại thật trong lần sửa định dạng này.
- Không tạo mới docs, không đổi dữ liệu tồn, GPS, model hay thuật toán ETA; cửa sổ1–2giờ chỉ là cách trình bày. Lịch sử thông báo đã lưu trước đó giữ nguyên.


## Giờ giao 08:00–18:00 — 05/11/2026

- 19/19 test_delivery đạt (7 ca mới, 12 ca cũ cập nhật đồng hồ cố định): trước 08h, ban ngày, sát giờ đóng cửa, sau 18h, qua ngày, mốc đúng18h, múi giờ UTC/VN, từ chối giờ nhận đêm/không timezone, chặn bắt đầu giao đêm hoặc ETA sang ngày sau, loại khung evening mới, dữ liệu/ETA cũ không bị ghi đè.
- 14/14 test_unified_orders và12/12 test_admin đạt. Tổng45 kiểm thử dùng database tạm, không sửa DB đang dùng.
- Kiểm tra import Python, cú pháp JavaScript và HTML trả từ API đạt. Chưa chạy lại Chrome, GPS điện thoại hoặc Qwen thật trong lần chỉnh giờ này; không thay phần NLU/model/bản đồ hoặc gọi dịch vụ ngoài.
- Không tạo mới docs, không reset/đổi đơn hay tồn kho. README/DATABASE-API được cập nhật quy định giờ giao; đây không phải thay đổi giờ mở cửa.


## Định vị / ETA trong chat, bỏ email — 05/11/2026

- 12/12 kiểm thử tests/test_delivery.py đạt: GPS/địa chỉ chữ, schema vị trí, ETA, quyền phiên, xác nhận/đang giao/đã giao, lịch sử, không lặp, rollback trạng thái/tin, hủy hoàn tồn, dữ liệu cũ và không còn API/module/table gửi email.
- 14/14 ca đơn chung, 12/12 ca quản trị và 20/20 ca API tích hợp có sẵn đạt; 20 ca dùng runner thư viện chuẩn giữ assertions vì môi trường chưa có pytest.
- 139/139 checkout/hybrid standalone đạt. Không đổi prompt/model/NLU hoặc cài thư viện AI.
- 18/18 kiểm tra Chrome headless đạt với HTTP/FastAPI/SQLite thật ở DB QA riêng: GPS mô phỏng, từ chối quyền, Leaflet 1.9.4 thật, chọn điểm map, bỏ ghim/lấy lại GPS, form nhỏ 390px, xem lại/lưu ghim, ETA, thông báo xác nhận/đang giao/đã giao, chống lặp, khôi phục lịch sử, admin và form giỏ vẫn có định vị, không exception JavaScript. Tiles được chặn/thay ảnh trống trong test; không tải bản đồ OSM hàng loạt hoặc gửi vị trí thật.
- Chưa xác minh GPS trên điện thoại thật, bản đồ tile thực qua Cốc Cốc/tunnel, độ đúng ETA ngoài thực địa hoặc Qwen thật trong kịch bản này. ETA là xấp xỉ kỹ thuật, không có traffic/routing.
- Module website_notifications.py, cấu hình SMTP và API gửi email đã gỡ. Không gửi email ra ngoài trong quá trình triển khai. Dữ liệu đang dùng không bị reset/thêm đơn thử; chỉ DB QA được dùng.


## Đặt đơn chung chatbot / giỏ hàng — 04/11/2026

- 14/14 kiểm thử mới trong tests/test_unified_orders.py đạt: đơn nhiều món, cùng danh sách quản trị, xác nhận lặp/alias, quyền phiên, sửa REVIEW, giá thay đổi, thiếu tồn, rollback SQL, hủy hoàn tồn, đặt tiếp giữ contact, cạnh tranh tồn cuối, khởi tạo lại, lịch sử cũ và xác nhận/handoff qua câu tự nhiên với LLM fake.
- 12/12 unittest quản trị và 20/20 ca tích hợp API đạt. Ca mounted checkout được cập nhật theo yêu cầu mới: kỳ vọng order_id và đơn chung thay cho request_id/tư vấn. 20 ca chạy bằng runner thư viện chuẩn (giữ assertions), môi trường chưa có pytest.
- 139/139 ca checkout/hybrid hiện có đạt; NLU/prompt/model không bị đổi.
- 12/12 kiểm tra Chrome headless đạt với HTTP/SQLite thật ở DB QA riêng và đầu ra NLU giả: form nhiều món, tổng 115.000đ, nút xác nhận đặt hàng, mã SB, trạng thái đã gửi, cùng danh sách admin, chi tiết đơn, xác nhận/hủy hoàn tồn, giữ lịch sử khi chuyển trang và không có exception JavaScript. Khung rộng 390px không tràn ngang.
- Không tạo đơn thử vào database đang dùng; không đổi mật khẩu/model hoặc cài dependency. Chưa chạy kịch bản với Qwen thật, điện thoại vật lý hoặc tunnel.
- Startup sẽ thêm bảng liên kết mới khi chạy lại main.py; không reset/migrate các yêu cầu tư vấn cũ thành đơn.


## Thiết kế lại quản trị — 04/11/2026

- 12/12 unittest quản trị đạt trên Windows/Python 3.12: auth, tổng quan, lọc/tìm kiếm/phân trang/ngày theo giờ Việt Nam, sửa giá/tồn, ẩn/mở sản phẩm, xung đột tồn, snapshot đơn, hủy hoàn tồn một lần, yêu cầu chatbot tách biệt và bảo vệ tài nguyên.
- 20/20 ca API/checkout có sẵn đạt, giữ nguyên assertions bằng runner thư viện chuẩn vì môi trường hiện chưa có pytest. Không gọi đây là lần chạy pytest.
- Chrome headless với FastAPI và SQLite thử riêng: 22/22 kiểm tra đạt, gồm đăng nhập, thống kê thật từ fixtures, CSV và chống công thức, tìm không dấu, chi tiết có ảnh, xác nhận trạng thái, sửa giá/tồn, chặn ghi đè, render ticket bằng text, màn hình 1440px/390px, hết phiên và đăng xuất. Không có exception JavaScript.
- Đã xem ảnh desktop/mobile để chỉnh menu điện thoại, đăng xuất và khoảng cách chữ. Ảnh xem trước ở runtime/admin-preview-desktop.png và runtime/admin-preview-mobile.png (dữ liệu giả lập, không dùng DB thật).
- Không sửa thư mục chatbot; không cài dependency, không gọi Ollama, không đổi mật khẩu hoặc dữ liệu đang sử dụng.
- Chưa thử trên điện thoại vật lý, Cốc Cốc, máy in thật hoặc tải đồng thời nhiều quản trị viên. Chrome emulation không thay thế kiểm tra thiết bị thật. Server main.py đang mở cần dừng/chạy lại để nạp API mới.


## Lần nhập website — 03/11/2026

Giữ nguyên chatbot của D:\sweet-bakery-nhom6; chỉ cập nhật website bên ngoài từ D:\Sweet-Bakery. Kết quả mới: 20/20 ca API bằng runner thư viện chuẩn, giữ assertions của file nguồn;16/16 mục Chrome headless với server/DB thử. Không gọi model thật, không cài dependency hoặc đổi DB đang dùng. Hướng dẫn chính xác ở README.md và HUONG-DAN-CHATBOT-MOI.md.

Phần bên dưới là tài liệu lịch sử từ bản nguồn, không phải toàn bộ kết quả mới của lần nhập này.

## API và database
- **18/18 kiểm thử tích hợp đạt** (`tests/test_integration.py`).
- **406/406 kiểm thử gốc chatbot đạt** (chạy riêng trong thư mục chatbot).
- Kiểm tra lưu đơn, tạm tính lấy từ DB, idempotency không tạo/trừ tồn trùng, kiểm tra số lượng sai và product trùng, dữ liệu khách thiếu/sai, thiếu đồng ý, rollback khi thiếu tồn, seed lại không reset đơn/tồn.
- Quản lý bắt buộc đăng nhập, kiểm tra trạng thái hợp lệ, hủy đơn hoàn tồn một lần, logout mất quyền.
- Chatbot cần session token; chatbot và website phản ánh cùng giá khi DB được cập nhật.
- Các đường dẫn main.py, database và file mật khẩu không được phục vụ công khai. Chặn POST từ origin khác.

## Trình duyệt với server thật
Chạy Chromium headless kết nối FastAPI và SQLite tạm (không mock API):
1. Thêm sản phẩm từ trang chủ và trang chi tiết.
2. Mở iframe chatbot, hỏi giá Mousse Chanh leo, thêm sản phẩm từ bot vào cùng giỏ hàng.
3. Điền form, gửi đơn, nhận mã SB và tạm tính 1.370.000 VND đúng dữ liệu thử; giỏ được trừ hàng.
4. Đăng nhập quản lý, thấy đúng thông tin khách và các dòng hàng.
5. Xác nhận rồi hủy đơn, kiểm tra tồn được trả về số ban đầu.
6. Kiểm tra 10 trang ở viewport rộng 390px, không tràn ngang toàn trang. Đã xem ảnh chụp quản lý và chatbot nhúng để kiểm tra bố cục.
7. Không ghi nhận JavaScript exception.

## Giới hạn xác minh
- Chạy kiểm thử trong môi trường Linux/Python 3.12/Chromium. File BAT đã chuẩn bị cho Windows và kiểm tra nội dung/CRLF; chưa chạy trực tiếp trên máy Windows của người dùng.
- Chưa kiểm tra thiết bị iOS/Android thực hoặc chế độ Ollama.
- Bộ test có cảnh báo deprecation từ thư viện test HTTP, không phải lỗi chạy ứng dụng.
- Không có giao dịch thanh toán thật, email/SMS, vận chuyển hoặc hosting.
- ZIP không chứa database sinh ra từ kiểm thử, token đăng nhập hoặc mật khẩu cố định.
