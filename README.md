# Sweet Bakery Nhóm 6 — bản tích hợp

## Cập nhật website, giữ nguyên chatbot — 03/11/2026

Chỉ nhập các file **ngoài chatbot** từ D:\Sweet-Bakery vào D:\sweet-bakery-nhom6. Không copy chatbot cũ, .venv, runtime/database, mật khẩu hoặc cache từ nguồn. Qwen/hybrid, giao diện/form và dữ liệu riêng của chatbot hiện tại được giữ nguyên.

**Chạy với môi trường đang có**, không cần cài lại:

```powershell
Set-Location 'D:\sweet-bakery-nhom6'
.\chatbot\.venv\Scripts\python.exe -B -X utf8 main.py
```

Hoặc nhấp **CHAY-WEBSITE.bat**. Launcher ưu tiên .venv ở root; nếu chưa có sẽ dùng chatbot\.venv hiện tại, không cài/đổi thư viện trong đó. Dừng server cũ bằng Ctrl+C trước để tránh trùng cổng.

- Website: http://127.0.0.1:8000/ hoặc /website/
- Chatbot: http://127.0.0.1:8000/chatbot/
- Quản lý: http://127.0.0.1:8000/admin.html

Website mới đầy đủ chạy bằng **main.py ở root**; không chạy đồng thời chatbot/run_web.py trên cổng8000. File run_web.py giữ nguyên cho chatbot riêng. Cấu hình model/Ollama/hybrid kế thừa từ chatbot đang có, không tự chuyển sang rule.

main.py điều chỉnh URL HTML và dùng lại handler/session của chatbot cho /api/.... Bản 04/11 nối tool tạo đơn chung qua order_tools_factory; không đổi NLU, prompt hoặc model Qwen. Widget bên ngoài giữ phóng to/thu nhỏ/nút tròn và lịch sử qua chuyển trang, bỏ widget đơn giản bị trùng của bản nguồn.

Trong chế độ tích hợp, giá/tồn kho đọc SQLite website; form chatbot và giỏ hàng cùng tạo đơn vào web_orders/web_order_items, cùng hiển thị trong Admin → Đơn hàng. Database website mặc định runtime/sweet_bakery.sqlite3 được khởi tạo khi chạy server. **Database cũ trong chatbot/runtime vẫn giữ nguyên, không tự nhập đơn/hội thoại sang DB website.**

Đã kiểm tra 20/20 ca API từ hai file tests bằng runner thư viện chuẩn (giữ assertions, không cài pytest);16/16 mục Chrome headless với server/DB thử: URL iframe, giá, quyền phiên, widget, chuyển danh mục, lịch sử, mở sản phẩm, giỏ hàng và chiều rộng mobile. Không gọi model thật; chưa nhấp đúp BAT hoặc thử tunnel/điện thoại thật. Môi trường hiện chưa có pytest; các lệnh pytest bên dưới dành cho môi trường đã cài requirements-dev.txt riêng ở root.

Bộ này đã nối giao diện, server, SQLite và chatbot. Chạy **một server duy nhất**, mở **http://127.0.0.1:8000**. Không dùng Live Server cho bản này.

## 1. Chuẩn bị trên Windows

1. Tải file ZIP bản tích hợp và nhấp chuột phải → **Extract All / Giải nén tất cả**.
2. Chọn thư mục dễ tìm, ví dụ `D:\SweetBakery`. Mở đến thư mục có `main.py`, `requirements.txt`, `CAI-DAT.bat`, `CHAY-WEBSITE.bat`. Đừng chạy ngay trong cửa sổ xem ZIP.
3. Nếu chưa có Python, cài Python 3.12 hoặc 3.13 bản 64 bit từ https://www.python.org/downloads/windows/ . Bản này đã kiểm thử với Python 3.12. Khi dùng bộ cài truyền thống, tích **Add python.exe to PATH**, rồi **Install Now**. Cài xong đóng và mở lại Terminal.
4. Có thể nhấn Windows + R → gõ `cmd` → Enter → gõ `py --version`. Nếu không có lệnh py, thử `python --version`. Cần Python từ 3.11 trở lên; không dùng Python 2.
5. Không cần cài XAMPP, MySQL, SQL Server, Node.js để chạy website; chatbot AI vẫn cần Ollama theo cấu hình đang có. SQLite đi cùng Python. Lần đầu cần Internet để tải thư viện.

## 2. Cách dễ nhất: mở file chạy tự động

1. Nhấp đúp **CHAY-WEBSITE.bat**.
2. Lần đầu, chương trình tạo môi trường `.venv`, cài thư viện và tạo database; chờ trong cửa sổ đen. Không tắt giữa chừng.
3. Khi server sẵn sàng, trình duyệt tự mở **http://127.0.0.1:8000**. Nếu không tự mở, tự gõ địa chỉ đó vào Chrome.
4. Giữ cửa sổ đen đang chạy. Nó chính là server của bạn. Tắt cửa sổ thì website ngừng hoạt động.
5. Khi muốn dừng, nhấn **Ctrl + C** trong cửa sổ server. Lần sau chỉ mở lại **CHAY-WEBSITE.bat**; không phải tạo lại database.

`CAI-DAT.bat` dành cho cài hoặc cài lại thư viện. Nó không xóa đơn/tồn kho. Khi nhấp riêng, cửa sổ có thể đóng sau khi cài xong; tiếp tục mở CHAY-WEBSITE.bat.

## 3. Cách chạy bằng VS Code / PowerShell

1. Mở VS Code → File → Open Folder → chọn đúng thư mục có main.py ở ngoài cùng.
2. Chọn Terminal → New Terminal.
3. Nhập lần lượt các lệnh sau. Chờ mỗi lệnh xong rồi mới nhập lệnh tiếp:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe create_db.py
.\.venv\Scripts\python.exe main.py
```

Nếu máy không có `py`, thay lệnh đầu bằng `python -m venv .venv`.

Mở **http://127.0.0.1:8000**. Các lệnh gọi trực tiếp Python trong `.venv` nên không cần Activate.ps1, không cần thay đổi ExecutionPolicy. Đừng chạy main.py bên trong thư mục chatbot khi muốn mở cả website.

macOS/Linux: `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`, `.venv/bin/python main.py`.

## 4. Thử đặt đơn và xem database qua trang quản lý

1. Ở trang chủ, thêm bánh Mousse Hawaii hoặc sản phẩm khác vào giỏ.
2. Mở Giỏ hàng, tăng/giảm số lượng và bấm **Nhập thông tin giao hàng**.
3. Điền tên, số di động Việt Nam hợp lệ, tỉnh/thành phố, phường/xã và địa chỉ. Trong bài tập hãy dùng thông tin kiểm thử, không gửi thông tin người khác.
4. Tích ô đồng ý rồi bấm **Gửi yêu cầu đặt hàng**.
5. Nếu thành công sẽ có mã dạng `SB-...`; giỏ được trừ số lượng đã đặt. Đơn được **lưu thật vào SQLite trên máy chạy server**, không chỉ nằm trong trình duyệt.
6. Mở **http://127.0.0.1:8000/admin.html** (nhập trực tiếp địa chỉ; trang chủ không thêm liên kết quản trị).
7. Trong File Explorer, mở thư mục `runtime` → mở `admin-password.txt` bằng Notepad → sao chép mật khẩu vào form đăng nhập. File này được tạo khi khởi động server lần đầu. Không cần tên đăng nhập.
8. Trang quản lý hiển thị mã đơn, tên/điện thoại/email, địa chỉ, thời gian mong muốn, mặt hàng, số lượng, tạm tính, lời chúc, ghi chú.
9. Có thể đổi **Chờ xác nhận → Đã xác nhận → Hoàn tất**, hoặc hủy đơn chưa hoàn tất. Hủy sẽ hoàn lại tồn kho đúng một lần. Đơn hoàn tất/đã hủy không được đổi ngược.
10. Tắt và chạy lại server rồi vào quản lý: các đơn vẫn còn.

Phí giao hàng hiện là **chờ xác nhận**, không hiểu là 0 đồng. Hoàn tất đơn không có nghĩa đã thu tiền; chưa có nghiệp vụ xác nhận thanh toán riêng. Trang quản trị lọc đơn trên server và phân trang 20 đơn; màn hình chatbot tải tối đa 100 yêu cầu và 100 phiếu hỗ trợ mới nhất.

## 5. Dùng chatbot

- Bấm **Tư vấn chọn bánh** ở góc dưới bên phải.
- Thử “giá Mousse Chanh leo”, “bánh dưới 400k”, “chính sách giao hàng”.
- Chatbot giữ nút đặt món/form riêng. Nút **Xem bánh** mở chi tiết website; tại đó có thể thêm vào giỏ website. Không thêm nút trong chatbot.
- Bot và website đọc **cùng mã sản phẩm, giá và tồn kho trong database**. Kế thừa CHAT_MODE/OLLAMA_MODEL/NLU_ENGINE hiện tại; không tải model và không cần API key.
- **Đặt ngay trong chatbot:** chọn món → điền form → Xem lại đơn hàng → Xác nhận đặt hàng. Nhận mã SB-... và xem cùng đơn giỏ hàng tại Admin → Đơn hàng. Chưa gửi form/xác nhận thì chưa tạo đơn. Phiếu hỗ trợ và yêu cầu tư vấn cũ vẫn giữ ở Tư vấn & hỗ trợ.
- Size, khẩu phần, thành phần chưa được nhóm cung cấp nên không bịa dữ liệu. “Tiêu chuẩn” là mã biến thể nội bộ, không là số cm. Luồng đặt tích hợp kiểm tra sản phẩm, giá, tồn và thông tin khách theo cùng contract với giỏ hàng; lịch nhận/phí giao vẫn cần cửa hàng xác nhận.
- Trang chatbot đầy đủ: **http://127.0.0.1:8000/chatbot/**.
- Hướng dẫn chatbot hiện tại: chatbot/README.md và chatbot/README___.MD. File ở root hướng dẫn website tích hợp; không áp cấu hình chatbot cũ từ bản nguồn.

## 6. File và dữ liệu quan trọng

| Đường dẫn                    | Công dụng                                                           |
| ---------------------------- | ------------------------------------------------------------------- |
| main.py                      | Server chung, API sản phẩm/đơn, đăng nhập quản lý, tích hợp chatbot |
| database.py                  | Tạo schema và seed 24 sản phẩm, kết nối SQLite                      |
| create_db.py                 | Tạo/nâng schema, thêm seed còn thiếu, không reset dữ liệu           |
| static/                      | Các trang HTML, CSS, JS, ảnh                                        |
| static/config.js             | API cùng origin, đã bật mode api                                    |
| static/products.json         | Dữ liệu để seed lần đầu; không là nguồn giá khi website đang chạy   |
| chatbot/app/                 | Logic chatbot của nhóm                                              |
| runtime/sweet_bakery.sqlite3 | Database dùng chung, tự tạo lúc chạy                                |
| runtime/admin-password.txt   | Mật khẩu quản lý sinh ngẫu nhiên trên máy của bạn                   |
| tests/test_integration.py    | Kiểm thử API tích hợp                                               |
| KET-QUA-KIEM-THU.md          | Kết quả và giới hạn đã kiểm tra                                     |
| DATABASE-API.md              | Sơ đồ bảng, route và ghi chú bàn giao                               |

Tồn kho khởi tạo là **100 đơn vị mỗi sản phẩm để demo**, không phải tồn thực của cửa hàng. Chạy lại create_db.py không tăng tồn lại về 100, không sửa giá hiện có và không xóa đơn. Sửa products.json sau lần chạy đầu không tự ghi đè database; người phụ trách DB cần cập nhật bảng product_variants/products có kiểm soát.

Database orders.db kiểu cũ (nếu máy bạn có) không bị ghi đè hoặc tự nhập vào bản này. Bản ZIP nhóm gửi không có file database đó. Nguồn dữ liệu của bản tích hợp là runtime/sweet_bakery.sqlite3.

## 7. Sao lưu, chuyển máy, đổi mật khẩu

- Dừng server bằng Ctrl+C rồi sao chép **cả thư mục runtime** để sao lưu. Database chứa thông tin đơn và hội thoại; không đưa dữ liệu khách/mật khẩu lên GitHub.
- Gửi bộ mã nguồn cho máy khác, không kèm `.venv`. Trên máy mới chạy CHAY-WEBSITE.bat để cài lại môi trường.
- Nếu muốn mang cả đơn sang máy khác, sau khi dừng server sao chép database vào đúng thư mục runtime của máy mới. Không chép đè database đang chạy.
- Đổi mật khẩu: dừng server, sửa nội dung một dòng trong runtime/admin-password.txt rồi chạy lại. Hoặc đặt biến môi trường SWEET_ADMIN_PASSWORD; biến này có ưu tiên hơn file.
- Muốn tạo bộ dữ liệu demo sạch: dừng server, **đổi tên** file database cũ thành file sao lưu, rồi chạy lại. Không xóa database nếu còn cần đơn cũ.

## 8. Lỗi thường gặp

| Hiện tượng                                          | Cách xử lý                                                                                                                                         |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Trang báo không tải được danh mục                   | Kiểm tra server đang chạy; mở 127.0.0.1:8000, không mở file HTML trực tiếp hoặc port 5500 của Live Server.                                         |
| py / python không được nhận diện                    | Cài Python, bật PATH, mở lại Terminal. Thử lệnh còn lại.                                                                                           |
| ModuleNotFoundError                                 | Chạy lại CAI-DAT.bat, hoặc lệnh pip ở phần 3 bằng đúng Python trong .venv.                                                                         |
| Pip không cài được                                  | Kiểm tra Internet và thông báo lỗi; không bỏ qua rồi chạy. Chụp cửa sổ lỗi để nhóm kiểm tra.                                                       |
| Port 8000 đang được dùng / WinError 10048           | Tắt server Sweet Bakery cũ; chỉ chạy một lần. Hoặc PowerShell: `$env:PORT="8001"`, sau đó chạy main.py và mở 127.0.0.1:8001.                       |
| Đăng nhập sai                                       | Sao chép đúng file mật khẩu của bộ dự án đang chạy; kiểm tra biến SWEET_ADMIN_PASSWORD nếu đã đặt. Sau 10 lần sai trong một phút cần chờ một phút. |
| Không tìm thấy admin-password.txt                   | Phải chạy main.py/CHAY-WEBSITE.bat ít nhất một lần; create_db.py chỉ tạo DB. Nếu đã đặt SWEET_ADMIN_PASSWORD thì dùng giá trị biến đó.             |
| Khởi động lại server, quản lý/chat mất phiên        | Đăng nhập lại quản lý hoặc tạo hội thoại mới. Đơn đã lưu vẫn còn trong DB.                                                                         |
| Bot hỏi lại size/thành phần hoặc không xác nhận đơn | Danh mục chưa có dữ liệu đó; dùng giỏ để đặt đơn website, không đoán size/thành phần.                                                              |
| Máy khác không mở được 127.0.0.1 của bạn            | 127.0.0.1 chỉ trỏ về máy đang dùng. Bản này chạy local, chưa triển khai lên hosting.                                                               |

## 9. Mức hoàn thiện hiện tại

Đã có luồng local đầy đủ: xem sản phẩm → giỏ → thông tin khách → API xác thực/tính giá từ DB → lưu đơn/trừ tồn → quản lý xem/xác nhận/hủy → tồn được hoàn khi hủy. Chatbot tích hợp và dùng chung catalog.

Chưa có cổng thanh toán, gửi email/SMS, hãng vận chuyển, định phí giao hàng, tài khoản khách hàng hoặc hosting công khai. Đây là bản đồ án chạy trên máy, không tự trở thành hệ thống bán hàng công khai. Không có đơn thử của quá trình kiểm tra hay mật khẩu cố định được đóng gói trong ZIP.

Tài liệu Python tham khảo: https://docs.python.org/3/library/venv.html .


## Trang quản trị mới — 04/11/2026

Sau khi thay code, dừng server cũ bằng Ctrl+C rồi chạy lại:
```powershell
cd D:\sweet-bakery-nhom6
.\chatbot\.venv\Scripts\python.exe -B -X utf8 main.py
```
Mở http://127.0.0.1:8000/admin.html hoặc /website/admin.html và đăng nhập bằng mật khẩu hiện có.

- **Tổng quan:** số đơn hôm nay, đơn chờ xử lý, giá trị tiền hàng của đơn hoàn tất, số sản phẩm đang bán; biểu đồ 7 ngày theo giờ Việt Nam và đơn mới nhất. Giá trị hoàn tất chưa phải doanh thu đã thu tiền.
- **Đơn hàng:** lọc trạng thái/ngày, tìm tên không dấu/mã/điện thoại, phân trang, xem chi tiết có ảnh, in đơn và xuất CSV của trang hiện tại. Đổi trạng thái cần xác nhận. Hủy hoàn tồn đúng một lần; giữ quy tắc chuyển trạng thái cũ.
- **Sản phẩm:** tìm kiếm, lọc nhóm/hiển thị/tồn thấp; sửa giá VNĐ nguyên, tồn không âm và tạm ẩn/mở bán. Nguồn là SQLite dùng chung; không sửa products.json. Nếu giá/tồn thay đổi trong lúc mở form, hệ thống báo xung đột thay vì ghi đè. Đơn cũ giữ snapshot giá.
- **Tư vấn & hỗ trợ:** xem phiếu hỗ trợ và yêu cầu tư vấn cũ. Đơn mới từ chatbot nằm chung ở Đơn hàng; không tự biến yêu cầu cũ thành đơn.
- Giao diện có bố cục riêng cho máy tính/điện thoại, dùng CSS độc lập trong static/admin.css.

Kiểm thử admin không cần cài thêm thư viện:
```powershell
.\chatbot\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -p test_admin.py -v
```
Bộ kiểm thử dùng DB tạm riêng trong runtime; không dùng DB/mật khẩu thật. Không tự thêm tài khoản, sản phẩm mới, xác nhận thanh toán hoặc thay chính sách cửa hàng.


## Đơn hàng chung từ chatbot và giỏ — 04/11/2026

Chạy main.py ở root để dùng tích hợp này. Không cần chạy create_db.py hoặc reset DB: startup chỉ thêm bảng web_order_links cho quyền sở hữu và chống trùng; giữ nguyên đơn, tồn kho, yêu cầu cũ.

Hai nơi gọi cùng service trong website_orders.py: kiểm tra schema → BEGIN IMMEDIATE → kiểm tra giá/tồn → lưu snapshot đơn và trừ tồn → lưu liên kết hội thoại/bản nháp → commit. Cùng mã SB-..., trạng thái đầu pending_confirmation (Chờ xác nhận), COD, chưa xác nhận thu tiền/phí giao. Bấm lặp không tạo đơn hoặc trừ tồn thêm. Sửa bản xem lại buộc xác nhận lại.

- Admin → Đơn hàng: cùng xem, xác nhận, hoàn tất, hủy và in đơn của cả hai nguồn. Nhãn Chatbot/Website chỉ giúp biết nguồn đến.
- Sau khi gửi đơn, khách vẫn có thể đặt đơn tiếp theo trong cùng hội thoại. Ghi nhớ thông tin liên hệ; không tự dùng lại ngày/giờ nhận, lời chúc hoặc ghi chú.
- Tư vấn & hỗ trợ giữ phiếu hỗ trợ/yêu cầu cũ. Không tự chuyển lịch sử thành đơn và trừ tồn khi khách chưa xác nhận.
- Chatbot chạy riêng bằng run_web.py giữ provider mặc định; muốn tạo đơn chung với trang quản trị phải chạy main.py ở root.

File nên đọc: website_orders.py (schema + service + adapter), main.py (ghép route/provider), database.py (bảng liên kết), chatbot/app/checkout.py và order_flow.py (xem lại/xác nhận), chatbot/static/chat.js (nhãn/nút đặt hàng).

Kiểm tra luồng đơn chung, không gọi Qwen thật:
```powershell
.\chatbot\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -p test_unified_orders.py -v
```


## Định vị và theo dõi giao hàng trong chatbot — 05/11/2026

Không còn gửi email: đã bỏ module SMTP, worker, API gửi lại và cấu hình email vừa bổ sung. Trường email liên hệ cũ vẫn tùy chọn, không kích hoạt gửi thư.

- Cửa hàng đặt tại cơ sở 1 Đại học Công nghiệp Hà Nội, 298 Cầu Diễn. Tọa độ trong .env là điểm tham chiếu khuôn viên; kiểm tra/chỉnh STORE_LATITUDE và STORE_LONGITUDE nếu muốn đúng cổng nhận hàng.
- Form chatbot và trang thanh toán có Vị trí hiện tại, Mở bản đồ và Bỏ vị trí. GPS chỉ lấy khi bấm/cấp quyền; có thể chọn điểm hoặc kéo ghim. Ghim xanh là cửa hàng; ghim cam là nơi giao.
- Chọn ghim hợp lệ thì không bắt nhập tỉnh/phường/địa chỉ chữ; vẫn nên bổ sung số nhà, phòng, tầng để giao chính xác. Không tự đoán địa chỉ nhà từ GPS. Nếu bỏ ghim hoặc từ chối quyền, nhập địa chỉ đầy đủ như trước.
- Bản đồ Leaflet 1.9.4 chỉ tải khi mở, có kiểm tra integrity và ghi nguồn OpenStreetMap. Người dùng đã đồng ý dịch vụ ngoài; không gửi tên/điện thoại/email tới bản đồ. Dịch vụ tile thấy IP/khu vực đang xem; không tải bản đồ hàng loạt.
- GPS cần HTTPS hoặc localhost. Trên điện thoại dùng link HTTPS (ví dụ tunnel), không dùng địa chỉ HTTP LAN để yêu cầu GPS.
- Khi gửi đơn: chatbot hiện khoảng thời gian dự kiến tính từ lúc cửa hàng bắt đầu xử lý. Admin xác nhận hoặc Bắt đầu giao sẽ cập nhật giờ nhận dự kiến; admin có thể nhập giờ riêng theo múi giờ Việt Nam.
- Chat đọc cập nhật mỗi 15 giây khi tab đang hiển thị, không gọi Qwen và không gửi lại đơn. Mỗi đơn chỉ hiển thị thông báo khi trạng thái thay đổi; thông báo được lưu lịch sử và chỉ phiên sở hữu xem được.
- Admin bấm Đã giao đến địa chỉ khi đã kiểm tra việc giao; chatbot thông báo cửa hàng đã đánh dấu giao xong. Đây không phải GPS theo dõi tài xế hoặc chứng minh khách đã nhận.
- ETA dùng khoảng cách đường chim bay × hệ số đường, tốc độ trung bình và thời gian chuẩn bị/đệm; không có tuyến đường thực hoặc dữ liệu giao thông. Ngoài bán kính ước tính hoặc chỉ có địa chỉ chữ thì chờ cửa hàng xác nhận.
- Giữ nguyên đặt đơn chung, giá, tồn kho, chống trùng, hoàn tồn khi hủy, Qwen và các chức năng tư vấn.

Cấu hình ở .env ngoài root (biến môi trường được ưu tiên): STORE_ADDRESS, STORE_LATITUDE, STORE_LONGITUDE, DELIVERY_PREPARATION_MINUTES, DELIVERY_SPEED_KMH, DELIVERY_ROAD_FACTOR, DELIVERY_BUFFER_MINUTES, DELIVERY_ESTIMATE_RADIUS_KM. Mặc định 20 phút chuẩn bị, 20 km/h, hệ số 1.35, đệm 10 phút và bán kính 50 km chỉ là thông số ước tính kỹ thuật, chưa phải cam kết vận hành của cửa hàng.

File cần đọc: website_delivery.py (tính ETA/thông báo), website_orders.py (lưu vị trí và tra cứu đơn đúng chủ), main.py (admin cập nhật), static/delivery-map.js (GPS/bản đồ), chatbot/static/chat.js (hiện trạng thái).

Sau khi dừng server cũ, chạy lại như đầu README; Ctrl+F5 để nạp giao diện. Không reset database. Startup chỉ thêm bảng web_delivery_updates, không tạo bảng email hoặc đổi bảng đơn cũ.

Kiểm thử riêng, dùng DB tạm:
```powershell
.\chatbot\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -p test_delivery.py -v
```


### Giờ giao hàng — cập nhật 05/11/2026

Chỉ giao **08:00–18:00 theo giờ Việt Nam**. Form giỏ hàng và chatbot còn hai khung 08:00–12:00 / 12:00–18:00. Vẫn nhận yêu cầu đặt ngoài giờ; ETA trước 08:00 được tính từ 08:00, ngoài giờ hoặc không đủ thời gian trước 18:00 sẽ dự kiến sang ngày tiếp theo.

Admin không thể nhập giờ nhận ban đêm, bắt đầu giao ngoài giờ hoặc bắt đầu chuyến có ETA sang ngày sau. Mốc nhận 18:00 được chấp nhận nhưng khoảng ETA không kéo dài quá 18:00. Việc đánh dấu đơn đã giao vẫn là ghi nhận của nhân viên, không phải theo dõi GPS tự động.

Đơn cũ chọn giao tối không bị sửa/xóa: khi xác nhận, admin cần liên hệ khách và nhập giờ nhận mới hợp lệ. ETA cũ ngoài giờ được báo cần xác nhận lại thay vì tiếp tục hiển thị giờ giao ban đêm. Quy định này là giờ giao, không tự thay đổi giờ mở cửa hay dữ liệu tồn kho.


### Cách hiển thị lịch giao — cập nhật 05/11/2026

Thông báo giao hàng luôn ghi mã đơn đầy đủ, thứ/ngày/tháng/năm, khung giờ và giờ Việt Nam; kèm giờ giao08:00–18:00, lưu ý giao thông và cách hủy đơn đang chờ xác nhận hoặc nhờ nhân viên kiểm tra đơn đã xử lý. Nếu chưa có lịch hợp lệ, nói rõ chưa xác định, không tự bịa ngày giờ.

Khung ETA gốc dưới60phút chỉ được mở rộng khi hiển thị thành khoảng1–2giờ. Ví dụ10:23–10:33 ngày06/11/2026 thành Thứ Sáu,06/11/2026,khoảng10:00–12:00(giờ Việt Nam). Sát giờ đóng cửa chỉ dùng17:00–18:00, không kéo quá18h. ETA gốc vẫn giữ để kiểm tra nghiệp vụ.

Khi ngày giao đổi so với lịch trước, thông báo ghi Lịch giao đã cập nhật, lịch cũ và lịch mới đầy đủ ngày/năm/giờ. Admin có nút Chỉnh giờ giao trên đơn đã xác nhận; thao tác này không tạo đơn, đổi trạng thái hay trừ tồn thêm. Gửi lại cùng lịch không tạo thông báo trùng.

Lịch sử tin nhắn cũ được giữ nguyên; phần theo dõi đơn và thông báo mới dùng định dạng mới. Chạy lại main.py và Ctrl+F5 để nạp bản cập nhật.


### Hủy đơn trong chatbot — cập nhật 05/11/2026

- Đơn đang chờ cửa hàng xác nhận có nút **Hủy đơn** dưới trạng thái đơn. Bấm nút, chọn **Xác nhận hủy đơn** hoặc **Giữ đơn**; mở bước xác nhận chưa hủy đơn.
- Khách chỉ tự hủy đơn thuộc cuộc trò chuyện/phiên còn hiệu lực. Không dùng mã đơn làm mật khẩu. Nếu admin đã xác nhận, đang giao hoặc đã giao, hệ thống không tự hủy; nhắn **nhờ nhân viên hủy đơn** kèm mã để lưu yêu cầu hỗ trợ. Nhắn câu hủy qua Qwen hiện vẫn đi qua hỗ trợ, không thay thế bước xác nhận bằng nút.
- Hủy thành công cập nhật cùng đơn trong admin, lưu thông báo vào lịch sử và hoàn tồn đúng một lần. Hủy lặp hoặc admin/khách bấm đồng thời không hoàn tồn hai lần. SQL lỗi sẽ rollback cả trạng thái, tồn và tin nhắn.
- Có thể hủy đơn cũ đang chờ khi đã bắt đầu bản nháp mới; thông tin đang điền và contact không bị sửa. Giao diện đọc trạng thái mỗi15giây khi mở tab, không gọi Qwen. Khi đổi sang chủ đề khác, đơn đang chờ có thao tác hủy trong thông báo theo dõi.
- Nguồn standalone không hỗ trợ hủy thì báo rõ, không giả thành công. Muốn dùng đơn chung với admin, chạy **main.py ở thư mục gốc**, không chạy riêng chatbot/run_web.py.

Sau khi dừng server cũ bằng Ctrl+C:
```powershell
cd "D:\sweet-bakery-nhom6"
.\chatbot\.venv\Scripts\python.exe -B -X utf8 main.py
```
Mở http://127.0.0.1:8000/website/ và Ctrl+F5 để nạp giao diện mới. Không cần reset database.
