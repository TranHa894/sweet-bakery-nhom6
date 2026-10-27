# Chatbot Sweet Bakery

Python **3.12.10**, Qwen **qwen3.5:4b** qua Ollama local, FastAPI và SQLite. Giao diện web gọi service chatbot; không cần API key, không thanh toán/giao hàng thật.

Mặc định đọc **24 sản phẩm mẫu** của nhóm từ `../static/products.json` bằng adapter chỉ đọc. Đây chưa phải menu kinh doanh chính thức. Chatbot chỉ lưu **yêu cầu chờ tư vấn**, chưa xác nhận đơn từ nguồn này.





## Nút xem thêm cho cả tìm trực tiếp — 27/10/2026

Đã sửa nhánh bị bỏ sót: “tìm bánh dưới 400k” có advice=none, trước đây chỉ trả 4 món và không có nút dù còn kết quả. Hiện mọi truy vấn gợi ý/tìm sản phẩm đều dùng phân trang. Lượt đầu của tìm trực tiếp giữ tối đa 4 món; các lượt xem thêm trả tối đa 3 món chưa xem. Chỉ ẩn nút khi hết toàn bộ kết quả phù hợp. Không thêm lại nút hỏi giá dưới thẻ.

next_advice_page dùng chung cho nhánh trực tiếp và tư vấn theo bước; product_answer thu các trang vào cùng lượt trả lời. advice_page lưu một trang hoặc queries của tối đa bốn bộ lọc. Khi xem thêm, xử lý nhóm còn kết quả kế tiếp, mỗi lần tối đa 3 món, giữ bộ lọc và xếp hạng trước. ID đã xem được đối chiếu giữa các nhóm nên món nằm trong nhiều nhóm không xuất hiện lại. remaining_ids giúp bỏ nút ngay cả khi các nhóm có kết quả chồng lấn. Bộ nhớ chỉ có ID/bộ lọc/thông tin xếp hạng, không chứa bản sao menu và không gửi vào prompt. Schema SQLite/API, model và giới hạn gọi Qwen không đổi.

**Đã kiểm tra:** scripts/check_checkout.py 31/31 nhóm (thêm 5 nhóm trực tiếp, nhiều nhóm ngân sách khác nhau, nhóm chồng lấn, nhóm ít món và xếp hạng rẻ nhất). Fake toàn bộ 495/495 dev + 56/56 test đạt; không đổi nhãn dữ liệu cho bản sửa này. Model/DB fake và RAM tách khỏi dữ liệu đang dùng.

**Qwen thật/API:** đúng câu “tìm bánh dưới 400k”, 15 bánh được trả theo 4+3+3+3+2, không trùng, không lẫn trà/cà phê, chỉ có nút xem thêm khi còn món. Năm lượt mỗi lượt một lần gọi (18,48 giây lượt đầu, 3,79–3,96 giây các lượt sau trên máy thử). Chrome headless dùng model giả xác nhận nút xuất hiện ngay ở 4/15, các lượt kế tiếp có 7/10/13/15 thẻ khác nhau, rồi nút biến mất; không có nút giá hoặc lỗi JavaScript. Chưa chạy toàn bộ 551 mẫu với Qwen.

Dừng server cũ và chạy lại run_web.py để nhận phần sửa backend.

## Xem thêm sản phẩm không lặp — 27/10/2026

Đã bỏ các nút “Giá [tên sản phẩm]” dưới thẻ gợi ý vì giá đã hiện trên thẻ. Phần dưới chỉ có “Xem thêm lựa chọn khác” khi còn món chưa xem; các nút chọn loại/độ ngọt/hương vị vẫn hoạt động.

Mỗi lần bấm “Xem thêm lựa chọn khác” trả tối đa **3 sản phẩm chưa được giới thiệu** trong cùng điều kiện tìm kiếm. Nếu chỉ còn 1–2 món thì trả đúng số còn lại. Khi hết, nút được bỏ ngay khỏi phản hồi; câu kết cũng không mời xem thêm nữa. Nếu vẫn gõ xem thêm sau khi hết, bot thông báo đã giới thiệu hết và không phát lại món cũ.

Nguyên nhân cũ: chỉ loại ID ở lượt gần nhất, hết kết quả lại lấy ba món đầu và luôn thêm nút. next_advice_page trong app/advice.py lưu bộ lọc, nguồn và ID đã xem của một đợt tư vấn vào advice_page riêng conversation; app/conversation.py dùng trang mới để trả lời. Tìm loại/vị/ngân sách mới khởi đầu đợt mới; hỏi giá xen ngang hoặc tải lại trang trong cùng phiên hợp lệ vẫn giữ ID đã xem. Phiên cũ chưa có advice_page loại ít nhất các món của lượt đang hiện rồi bắt đầu tích lũy. Bộ nhớ chỉ lưu ID/bộ lọc, không cache bản sao menu hoặc gửi lịch sử trang vào prompt.

Nút đang hiện được giải mã thành advice=more/refine sau khi Qwen trả output hợp lệ, cùng cơ chế chốt lựa chọn đã có. Qwen vẫn hiểu câu tự nhiên; không tăng prompt/token/retry hoặc đổi model. Lỗi nguồn/model không tiêu thụ trang; không tự nới hương vị/ngân sách khi bấm xem thêm.

**Đã chạy:** 26/26 nhóm API trong scripts/check_checkout.py, gồm sáu nhóm mới về bốn trang không trùng, trang cuối còn một món, nhóm chỉ có ba món, bộ lọc, hỏi giá xen ngang/tải lại, phiên riêng và lỗi nguồn/model. Fake 495/495 dev + 56/56 test đạt; sửa đúng một kỳ vọng dev cũ từng yêu cầu phát lại sản phẩm khi đã hết, không đổi nhãn NLU hoặc bộ test cuối. DB kiểm tra trong RAM.

**Qwen thật/API:** 12 bánh kem qua bốn lượt 3+3+3+3 không trùng; nút chỉ có ở ba lượt đầu. Gõ thêm lần nữa trả rỗng và thông báo hết, không tạo yêu cầu đặt hàng. Năm lượt đều một lần gọi model (18,22 giây lượt đầu; các lượt tiếp 3,99–5,54 giây trên máy đang thử). Chrome headless/model giả xác nhận 12 thẻ sản phẩm không trùng, nút mất ở lượt cuối và vẫn mất sau tải lại, không lỗi JavaScript. Chưa chạy toàn bộ 551 mẫu bằng Qwen.

Chạy lại run_web.py để nhận mã mới; lệnh kiểm tra: .\.venv\Scripts\python.exe -B -X utf8 -m scripts.check_checkout.

## Sửa vòng lặp khi chọn hương vị — 27/10/2026

Đã tái hiện bằng Qwen thật: “gợi ý bánh kem” → “Ngọt vừa” → “Kem/vani/trang trí”. Lượt cuối model chỉ trả loại bánh/độ ngọt, bỏ taste_family nên bot hỏi lại. Sau sửa, cùng JSON thiếu trường đó vẫn ghi nhận đúng lựa chọn bảng đang chờ và trả 1–3 bánh nhóm kem/vani, giữ ngọt vừa.

app/advice.py giải mã nhãn hoặc số của **bảng đang hiển thị** thành field/value đã biết. app/conversation.py chỉ áp dụng delta này sau khi đầu ra Qwen hợp lệ; dùng refine để giữ yêu cầu trước. Đây là xử lý lựa chọn giao diện, không phân loại câu tự nhiên bằng từ khóa. Câu khách tự viết vẫn qua luồng Qwen hiện có. Bảng cũ/phiên khác không được dùng; model lỗi hoặc trả thao tác đặt hàng cho nút tư vấn thì giữ trạng thái trước, không tạo đơn.

Không đổi prompt, model, giới hạn context/token hoặc số lần gọi. Không sửa dữ liệu sản phẩm, API/JS/CSS, không đổi schema database. Có thể dùng cả nhãn, số thứ tự và nhãn không dấu của bước đang chờ.

**Đã chạy:** 20/20 nhóm trong scripts/check_checkout.py (thêm 4 nhóm hồi quy, gồm mô phỏng model bỏ sót hương vị); 495/495 dev + 56/56 test bằng fake; chuỗi ba lượt Qwen thật đạt, một lần gọi mỗi lượt. Qwen vẫn bỏ trường ở JSON lượt cuối trong phép thử, nhưng lựa chọn nút được ghi nhận chắc chắn ở code và trả đúng bánh. Chưa chạy toàn bộ 551 lượt với model thật. Chạy lại server để nhận bản sửa; lệnh kiểm tra là .\.venv\Scripts\python.exe -B -X utf8 -m scripts.check_checkout.

## Sửa câu đặt nhiều món, độ ngọt và khung đơn — 27/10/2026, v56

- Hai câu “Hãy đặt cho tôi 3 cái bánh cuộn vani và 2 cà phê muối” và “đặt 3 bánh cuộn vani và 2 cà phê muối” đều phải giữ đúng hai dòng, số lượng 3/2. Nguyên nhân đã tái hiện: bộ chọn ví dụ lấy nhầm mẫu hỏi giá/phủ định, model sinh thêm intent price rồi lần sửa thiếu order_operation. build_turn_messages trong app/llm_client.py chọn mẫu đặt thuần phù hợp; grammar của nhánh đặt yêu cầu order_operation. Qwen vẫn hiểu câu chính; không dùng regex để tự tạo đơn.
- “Gợi ý bánh kem ngọt” chưa cho biết mức ngọt. Trước đây model tự gán high rồi bị check_turn_grounding từ chối vì khách chưa nói “ngọt nhiều”. Prompt và ví dụ mới để mức ngọt chưa xác định; bot hỏi ba nút Ngọt nhiều/Ngọt vừa/Ít ngọt. Khách đã nói rõ mức thì không hỏi lại.
- show_checkout là cờ hiển thị, tách khỏi order_draft. app/conversation.py, app/api.py và showReview trong static/chat.js không mở lại form/phiếu cũ sau câu tư vấn hoặc lỗi model. Bản nháp, yêu cầu đã gửi và dữ liệu form đang gõ được giữ; “xem lại yêu cầu” mở lại khung. Snapshot REVIEW cũ chưa có cờ mới vẫn mở được khi khôi phục phiên.
- Form, bản xem lại và yêu cầu đã lưu có ảnh nguồn đồng kích thước **48 × 48 px**, object-fit: cover. Đổi món trong form đổi ảnh theo món. app/checkout.py lưu image_url bên cạnh snapshot tên/giá; ảnh là thông tin hiển thị, không phải điều kiện giá. UI chỉ nhận đường dẫn ảnh cục bộ hợp lệ; ảnh lỗi không chặn phần xem lại/xác nhận.
- Thêm 6 few-shot (273 mẫu trong ngân hàng, tối đa 2 mẫu được chọn mỗi lượt) và 6 lượt dev. Không fine-tune, không tăng context/token/retry hay đổi model.

**Đã kiểm tra:** 495/495 lượt dev + 56/56 test dùng model giả; 16/16 nhóm API/checkout trên SQLite RAM. Chrome headless với model giả: ảnh tải được và đều 48px ở iframe 408px/1280px, không tràn ngang; giữ nội dung form chưa gửi; ẩn phiếu sau lỗi/tư vấn và khi tải lại; không có lỗi JavaScript. Không ghi vào database đang dùng.

**Qwen thật:** 6 lượt kiểm tra đã đạt, mỗi lượt 1 lần gọi. Hai cách đặt đều đúng 3 bánh vani + 2 cà phê muối; qua API tổng tiền hàng 195.000đ. Sau lưu, “gợi ý bánh kem ngọt” hỏi mức ngọt; “ngọt nhiều” gợi ý Mật ngọt/Choco ngọc trai, không đổi hoặc hiện lại phiếu cũ. Thời gian đo khoảng 5,16–11,77 giây/lượt; câu đặt dài trước sửa lỗi sau 2 lần gọi, 20,55 giây. Đây là phép đo nhỏ trên máy hiện tại, không bảo đảm mọi câu đều nhanh/đúng và chưa chạy toàn bộ bộ mẫu với model thật.

Dừng server cũ bằng Ctrl+C và chạy lại trong thư mục chatbot:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 run_web.py
```

Thử trên http://127.0.0.1:8000/website/. Các file CSS/JS đã đổi phiên bản URL để tránh dùng bản cache cũ. Nguồn group_files vẫn chỉ lưu **yêu cầu chờ tư vấn**, chưa trở thành đơn kinh doanh hoặc thanh toán thật.

## Form đặt hàng và đặt tiếp trong cùng phiên — 27/10/2026, v55

Đã sửa tình huống gửi yêu cầu xong rồi “đặt thêm cho tôi 1 trà sữa”: tạo bản nháp mới, không sửa hoặc cộng món vào yêu cầu đã gửi. Sửa/hủy yêu cầu đã gửi vẫn cần hỗ trợ. Câu hỏi giá không sửa bản nháp.

**Luồng web với DATA_SOURCE=group_files:** nói món/số lượng → form thông tin → Xem lại yêu cầu → Xác nhận gửi hoặc Quay lại chỉnh sửa/Hủy. Form dùng các trường tương ứng với ../static/thanh-toan.html; không sửa file website nhóm. Có thể chọn/thêm/bỏ món và sửa số lượng ngay trong form. Các trường có dấu * được kiểm tra cả trình duyệt lẫn server.

- Bắt buộc: sản phẩm, số lượng 1–99 mỗi dòng, họ tên, số di động Việt Nam, tỉnh/thành, phường/xã, địa chỉ cụ thể và đồng ý cung cấp thông tin. Giới hạn số dòng là 20 để giới hạn payload; không phải chính sách bán hàng.
- Không bắt buộc: email, ngày nhận, khung giờ, lời chúc, ghi chú. Ngày không ở quá khứ theo giờ Việt Nam. Đây là mong muốn cần cửa hàng xác nhận. Lời chúc chuẩn hóa NFC; giới hạn 100 ký tự theo mẫu form, không tuyên bố tiệm thực hiện được mọi nội dung.
- Ví dụ số 012345678 có 9 chữ số: form yêu cầu sửa thành số di động hợp lệ, không báo lỗi model chung. Không yêu cầu tiền tố DEMO/TEST cho khách.
- Họ tên, điện thoại, email và địa chỉ được nhớ trong cùng conversation. Yêu cầu tiếp theo để trống ngày/khung giờ, lời chúc, ghi chú; cần đồng ý cung cấp thông tin lại. Chat mới không lấy thông tin phiên trước.
- Bản xem lại hiện tên món, số lượng, đơn giá và tổng tiền hàng đọc lại từ repository. Ví dụ 2 Bánh cuộn trà xanh + 1 Cà phê ủ lạnh = 115.000đ. Không nhận giá/tổng tiền do frontend gửi.
- **Menu nhóm vẫn là nguồn tham khảo, chỉ lưu yêu cầu chờ tư vấn có mã. Chưa tạo hóa đơn/đơn kinh doanh thật.** Phí giao và tổng cuối cùng là null/chưa xác định, không tự gán phí 0. Backend nhóm chưa có contract đủ tương thích và quyền tạo đơn từ chatbot.
- Form và nút bấm gọi POST /api/checkout trực tiếp, không qua Qwen; câu tự nhiên vẫn dùng Qwen. Không đổi model, giới hạn context, output, keepalive hoặc số retry.
- Form nằm trong vùng cuộn của chat, một cột ở widget nhỏ, hai cột ở khung lớn. Không tràn ngang. Điền form rồi hỏi thông tin trong cùng revision không mất nội dung đang gõ. Nội dung chưa bấm Xem lại chỉ nằm trong trang hiện tại, chưa đảm bảo giữ qua reload; sau Xem lại được lưu trong bản nháp.
- Các nguồn empty/mock/local_demo giữ luồng yêu cầu cũ; form theo website nhóm chỉ bật ở group_files. Không tự mở quyền tạo đơn thật cho adapter chỉ đọc.

Nguyên nhân bổ sung đã sửa: regex kiểm chứng số đọc tiền tố tr trong “1 trà” thành triệu; nay đơn vị tiền phải có ranh giới từ. Khi đối chiếu tên món, cốc/ly/cái/chiếc là đơn vị đếm, không phải tên sản phẩm (chỉ chuẩn hóa để đối chiếu nguồn, không thay Qwen phân loại ý định). Danh sách trường cùng nội dung nhưng khác thứ tự không còn làm tăng revision khi hỏi giá.

File và trách nhiệm:
- app/checkout.py: schema form, đối chiếu món/giá, các thao tác review/edit/confirm/cancel và snapshot phục vụ UI.
- app/conversation.py, app/order_flow.py: mở bản nháp mới sau yêu cầu đã gửi, giữ liên hệ, ngăn xác nhận khi chưa xem form, ổn định revision.
- app/order_nlu.py, app/llm_client.py: kiểm chứng đơn vị số/tên và cho model biết yêu cầu đã gửi để phân biệt đặt thêm với sửa đơn cũ.
- app/api.py: route form, session token, lock riêng conversation, response checkout và tra cứu snapshot yêu cầu.
- app/storage.py, app/order_service.py: đưa form/tiền hàng vào hash REVIEW và snapshot lưu cùng bản ghi hiện có; không thêm database hay migration xóa dữ liệu.
- static/chat.js, style.css, index.html: form, thông báo validation, xem lại/sửa/hủy, bố cục theo chiều rộng iframe.
- scripts/check_checkout.py: kiểm tra độc lập bằng SQLite RAM/model giả. Không tạo lại tests hoặc docs.

Contract POST /api/checkout: conversation_id, draft_id, revision, action; action=review gửi form, action=confirm gửi confirmation_token của bản xem lại. Token phiên Bearer vẫn bắt buộc; confirmation_token chỉ khóa nội dung REVIEW, không phải xác thực. Sửa bản nháp làm mất REVIEW cũ; xác nhận lặp trả cùng mã. Nguồn/giá thay đổi phải xem lại. Lỗi SQL rollback, không báo đã lưu thành công. HANDOFF không được vượt qua bằng gọi form trực tiếp.

Kiểm tra thực tế:
- Hồi quy model giả: **489/489 dev + 56/56 test** đạt sau các thay đổi. Đây là test controller/validation, không phải độ chính xác Qwen trên 545 câu.
- **12/12 nhóm check_checkout đạt**, gồm nhiều món, dữ liệu bắt buộc/sai, đơn giá nguồn, chống trùng, revision cũ, tạo yêu cầu thứ hai, nhớ liên hệ/xóa trường tạm, quyền phiên, lỗi model/nguồn/SQL, resume, HANDOFF và xác nhận bằng câu tự nhiên.
- Qwen thật qua API/RAM: đặt thêm 1 trà sữa sau bản đã gửi → bản nháp mới; hỏi giá 1 cốc trà sữa → đúng SP0021/25.000đ; mỗi lượt một lần model, đo lần lượt 17,70 và 7,63 giây trong lượt thử. Không coi đây là benchmark tổng thể.
- Chrome headless với Qwen thật: đặt hai món → form → xem lại 115.000đ → sửa → gửi → đặt thêm trà sữa → gửi yêu cầu thứ hai 25.000đ → reload; đạt, không lỗi JavaScript. Lượt mở đơn đầu 12,28 giây. Widget thật của website đã thử cửa sổ nhỏ và toàn màn hình, xem lại/hủy đạt.
- Sau khi tiếp tục ngày 27/10: chạy lại 12 nhóm API, kiểm tra UI bằng model giả để xác nhận form đang gõ không mất khi hỏi giá, review/edit/confirm và bố cục widget 408px/1280px; đều đạt, không lỗi JavaScript.
- Thử nghiệm dùng database RAM và profile Chrome riêng, không ghi đơn thử vào database đang dùng. Chưa thử thao tác thủ công trong Cốc Cốc hoặc nối backend kinh doanh thật. Không chạy lại toàn bộ bộ câu hỏi bằng Qwen.

Dừng server cũ bằng Ctrl+C, rồi chạy tại thư mục chatbot:

~~~powershell
.\.venv\Scripts\python.exe -B -X utf8 run_web.py
~~~

Mở http://127.0.0.1:8000/website/. Thử “đặt cho tôi 2 bánh cuộn trà xanh và 1 cà phê ủ lạnh”, điền form, xem lại rồi xác nhận; sau đó “đặt thêm cho tôi 1 trà sữa”. Khi cần kiểm tra lại: .\.venv\Scripts\python.exe -B -X utf8 -m scripts.check_checkout. Có thể tra bản đã lưu qua GET /api/order-requests/{id} bằng token của đúng conversation.

## Gợi ý bánh chung chọn hai loại — 25/10/2026, v54

“gợi ý cho tôi bánh”, “tư vấn giúp mình chọn bánh”, “nên chọn bánh gì” và các câu gợi ý bánh chung được hiểu là product_type=cake; bảng chọn gồm đúng **Bánh kem / Bánh nhỏ**. Chọn bánh kem tiếp tục độ ngọt; chọn bánh nhỏ tiếp tục hương vị. Câu “gợi ý sản phẩm” vẫn có bốn nhóm, câu đã nêu rõ bánh kem không hỏi lại loại.

Menu hai lựa chọn đã có ở v53; lỗi còn lại là câu không có từ “đi” chọn nhầm few-shot gợi ý sản phẩm và bị product_type_mismatch. v54 ưu tiên ví dụ bánh chung khi phù hợp và thêm năm mẫu, ngân hàng 267 ví dụ, mỗi lượt vẫn tối đa hai. Không đổi API/frontend hoặc cấu hình model.

Đã chạy: fake **489/489 dev + 56/56 test**. API/Qwen thật: năm lượt chọn bánh → 2 → Vani → sản phẩm chung → bánh kem rõ loại đều đạt, một model/lượt, 3,95–5,69 giây; câu chính 5,06 giây. Qwen kiểm tra thêm ngữ cảnh cũ và hai cách hỏi chưa đưa vào few-shot đều đạt. Thử nghiệm dùng SQLite RAM; không tạo đơn, không ghi database đang dùng. Chưa chạy toàn bộ 545 lượt bằng Qwen.

Khởi động lại run_web.py để nạp bản sửa. Các mục dưới là lịch sử.

## Tiếp tục tư vấn trong cùng phiên sau lỗi — 25/10/2026, v53

Đã tái hiện trên bản sao ngữ cảnh đang lưu: trước đó chọn bánh kem/ngọt vừa/vị kem, câu “gợi ý cho tôi sản phẩm” bị Qwen gán lại cream_cake. Bộ chọn few-shot gửi mẫu “gợi ý bánh kem”, validator trả product_type_mismatch hai lần. Một số cách viết cũng lỗi ở phiên mới, trong khi thêm từ “đi” có thể chọn ví dụ khác. failed_turn giữ nguyên trạng thái đã xác minh, nên ngữ cảnh/ví dụ gây lệch tiếp tục lặp ở lượt sau; lượt lỗi không tự cập nhật bản nháp hoặc nhu cầu.

Sửa trong app/llm_client.py: gợi ý sản phẩm chung được chọn ví dụ chung, không tự thu hẹp nhóm từ ví dụ cũ; nêu rõ yêu cầu gợi ý mới khác câu chọn vị/slot đang chờ. Ví dụ nhập tên/điện thoại không được ưu tiên lấn câu hỏi có nhóm sản phẩm. app/advice.py chỉ hỏi hai nhóm bánh nếu khách đã nói bánh chung, hoặc trà/cà phê nếu đã nói đồ uống. Ngữ cảnh tham chiếu, điều kiện đã xác minh và bản nháp vẫn tồn tại; không xóa lịch sử để khắc phục.

Kết quả thực tế:
- 262 few-shot hợp schema; vẫn tối đa hai ví dụ/một lượt, không thêm lần model hay đổi cấu hình model.
- Thêm 21 lượt hồi quy: **480/480 dev + 53/53 test fake đạt**. Bao phủ gợi ý lại sau bộ lọc cũ, khi đang thu thập đơn, phiên mới, empty, chọn tiếp loại/vị và phạm vi bánh/đồ uống.
- Qwen thật trên bản sao phiên cũ và phiên mới: cùng “gợi ý cho tôi sản phẩm” đều trả bốn nhóm, một NLU/lượt (4,84 và 3,62 giây); “gợi ý cho tôi bánh đi” trong ngữ cảnh cũ trả hai nhóm bánh, một NLU/5,70 giây.
- API với SQLite RAM: khởi tạo ngữ cảnh cũ + bản nháp hai bánh cuộn vani, chủ động đưa đầu ra model sai để gây lỗi. DB order/needs/history/current_request không đổi. Tiếp tục cùng session bằng Qwen thật: gợi ý sản phẩm → gợi ý vài sản phẩm → Bánh kem → Ít ngọt; **4/4 lượt đạt**, một model/lượt, 4,02–6,30 giây. Bản nháp giữ nguyên, berry 450k được phép xuất hiện khi yêu cầu mới đã bỏ ngân sách cũ; kiểm tra phiên mới tương đương và token chéo 404 đạt; không tạo đơn.
- Không chạy Qwen toàn bộ 533 lượt. Lượt lỗi vẫn chỉ hiện trong phản hồi API, chưa ghi thành messages; lịch sử thành công đã lưu được giữ nguyên như trước.
- Dữ liệu thật đang dùng chỉ được đọc để tái hiện; thử nghiệm dùng bản sao/RAM. Không tạo docs/tests, không sửa frontend/backend của nhóm.

Khởi động lại run_web.py một lần để nạp code mới; xem evaluation/README.md để chạy các ca dev_advice_restart_*.

## Hai nhóm sản phẩm, ngân sách riêng — 25/10/2026, v52

Đã sửa câu “tôi muốn tìm bánh kem dưới 400k và cà phê trên 40k”. Qwen tách hai request nhưng bỏ question (cụm câu để kiểm chứng điều kiện từng request), làm Pydantic từ chối JSON; có lượt còn đổi “trên 40k” thành “dưới 40k”. Bộ chọn few-shot khi đó gửi hai ví dụ câu đơn.

HTTP schema nay yêu cầu trường question; câu đơn được phép null, recommendation nhiều phần vẫn phải có cụm câu hợp lệ. Khi tin nhắn nhiều phần, một trong tối đa hai ví dụ được dành cho mẫu nhiều phần phù hợp. Thêm ví dụ hai/ba/bốn nhóm, hướng giá và biên bao gồm; vẫn giữ Qwen làm bộ hiểu câu, không tự tách câu/điền filter bằng regex. Validator cũng phân biệt ngưỡng “giá cao hơn 40000đ” với so sánh một sản phẩm trước đó.

Kết quả:
- Fake logic: **463/463 dev + 49/49 test đạt**. Thêm 14 lượt dev và bốn lượt test hồi quy; ngân hàng có 257 ví dụ, mỗi request model vẫn chọn tối đa hai.
- Qwen thật đã trả đúng câu gốc, câu rút gọn, không dấu, đảo thứ tự, ba/bốn nhóm và trường hợp biên. Các lượt lỗi trung gian với không quá/ít nhất và cao hơn/thấp hơn được sửa rồi chạy lại; không tính là đạt trước khi sửa. Chưa đánh giá Qwen trên toàn bộ 512 lượt.
- Qua API web thật với Qwen + database RAM: hi, câu gốc hai nhóm, rồi hỏi giá/hương vị món khác đều HTTP 200, engine=ollama, không lỗi, một lần model/lượt. Câu gốc trả bốn bánh kem dưới 400k và ba cà phê 45k trong **12,62 giây**. Trước sửa lượt tái hiện thất bại mất 28,53 giây/hai lần gọi; đây là đo vài lượt, không phải benchmark thống kê.
- Ba và bốn nhóm lần lượt 21,31 và 25,90 giây trong lượt thử đã chạy. Không công bố tốc độ như câu đơn. JSON thiếu cụm câu hoặc sai hướng giá vẫn bị chặn, không sửa bản nháp; lịch sử, quyền phiên và không tạo đơn được kiểm tra.
- Giữ model, context/output budget, số retry và dữ liệu cửa hàng. Đợt này sửa app/llm_client.py, app/order_nlu.py, few-shot, evaluation và các README hiện có; không tạo tests/docs hoặc sửa website bên ngoài.

Dừng server cũ bằng Ctrl+C rồi chạy lại run_web.py để nạp code mới. Các mục phía dưới ghi lịch sử các đợt trước.

## Lỗi bộ cài Ollama — 25/10/2026

Log máy hiện tại ghi cập nhật Ollama bị hủy vì không thay được ollama app.exe (Access is denied), sau đó chạy Qwen lỗi thiếu llama-server.exe. Model vẫn xuất hiện trong /api/tags nhưng request /api/chat tối thiểu cũng trả HTTP 500: chưa đến bước xử lý prompt.

Client đã nhận diện riêng model_runtime_missing; giao diện báo không khởi động được AI, run_web.py in rõ thành phần thiếu. Chỉ đọc tối đa 16 KiB body lỗi để phân loại; không đưa đường dẫn/body của Ollama ra giao diện hoặc log. Lỗi HTTP không retry và không sửa bản nháp.

Đã kiểm tra 7 trường hợp HTTP giả, một lượt chat lỗi giữ nguyên bản nháp/chỉ một lần gọi, và thông báo khởi động (9 kiểm tra đạt). Trước sửa, prewarm thật xác nhận HTTP 500/model_runtime_missing.

Sau khi chủ dự án cho phép sửa Ollama ngoài chatbot, đã chạy bộ cài chính chủ 0.40.11 có sẵn (chữ ký hợp lệ, exit code 0), khôi phục lib/ollama/llama-server.exe và khởi động lại Ollama. API /api/version trả 0.40.11, Qwen qwen3.5:4b nạp thành công HTTP 200 trong 12,03 giây. Không tải lại hoặc đổi model; hai manifest có hash và 10 blob có tên/kích thước khớp trước khi sửa.

Thử Qwen thật qua API web với SQLite trong RAM: hi (4,05 giây), gợi ý bánh nhỏ vị vani dưới 50k (6,36 giây, đúng Bánh cuộn vani), giá và hương vị bánh cuộn trà xanh (5,06 giây, đúng sản phẩm). Cả ba HTTP 200, engine=ollama, không lỗi, một lần gọi model/lượt. Lịch sử, quyền phiên và không tạo đơn đều đạt.

Đã chạy run_web.py trên cổng tạm: /health, trang chat, JavaScript và /website/ đều HTTP 200. Server kiểm tra đã dừng; Ollama tiếp tục chạy nền. Không ghi hội thoại kiểm tra vào database đang dùng. Chưa kiểm tra thao tác bằng trình duyệt thủ công hoặc chạy lại toàn bộ 494 mẫu trong đợt sửa bộ cài này.

Log cài sửa nằm ở runtime/ollama-repair-install.log (Git bỏ qua). Xem https://docs.ollama.com/windows để biết vị trí bộ cài, log và model trên Windows.

## Tiếp tục và rà bộ tình huống — 25/10/2026, v51

Đã hoàn tất luồng tư vấn v50 bên dưới và rà lại bộ câu hỏi theo hành vi mới.

- Bộ hiện tại: **449 lượt dev / 127 hội thoại**, **45 lượt test / 20 hội thoại**. Đợt này thêm **57 lượt**: 41 tình huống dev, 4 JSON giả đi qua client thật và 12 câu holdout mới. Holdout là bộ kiểm tra riêng, không đưa vào prompt.
- Đồng bộ 50 nhãn gợi ý cũ và hai lượt tiếp nối: gợi ý chung hỏi sở thích; khi đủ điều kiện trả tối đa ba món. Các câu xem danh sách, nhiều yêu cầu, đặt hàng và kiểm tra quyền vẫn được giữ.
- Sửa bộ lọc vị cũ còn sót khi đổi sở thích; ngân sách và dị ứng vẫn giữ. Sửa validator bác sai matcha/trà xanh, coffee_cream/cà phê-kem và black/đen. Tên đồ uống có thể được biểu diễn đầy đủ bằng nhóm + vị; không áp dụng ngoại lệ này cho thao tác đặt món hoặc bỏ qua tên riêng.
- Qwen được biết một giá trị nhóm đang tìm để hiểu câu nối. Ngân hàng có **244 ví dụ** nhưng chỉ chọn tối đa **hai ví dụ mỗi lượt**. Không chép toàn menu hoặc bộ đánh giá vào prompt; không fine-tune, không tăng model/context/output budget hay số retry.

Kết quả thực tế sau sửa:
- **449/449 dev + 45/45 test đạt bằng model giả**; trong đó bốn ca JSON giả đi qua parser/validation của client, mỗi ca một lần gọi giả. Toàn bộ 244 ví dụ hợp schema; mã Python kiểm tra cú pháp đạt.
- Qwen thật: các lần chạy cuối của chuỗi đổi vị đạt **5/5 hành vi**, chuỗi cà phê đạt **3/3 hành vi**; mỗi lượt một NLU, **4,04–6,29 giây**. Lượt đầu của đợt kiểm tra mất 34,36 giây. Đây là phép thử nhỏ, chưa phải benchmark tốc độ toàn chatbot.
- Nhãn trích xuất khớp cứng chỉ **1/8** trong hai chuỗi trên: model có thể dùng tên vị tương đương, nhắc lại nhóm đã biết hoặc trả advice=none. Các ràng buộc sản phẩm/ngân sách/bản nháp vẫn đạt ở tám lượt này. Không coi kết quả hành vi là độ chính xác trích xuất hoàn hảo.
- Chưa chạy Qwen trên toàn bộ 494 lượt. Không chạy lại trình duyệt trong đợt rà v51; kết quả UI v50 được ghi riêng bên dưới. Không sửa website bên ngoài, dữ liệu đơn đang dùng, hoặc tạo docs/tests.

Đọc [evaluation/README.md](evaluation/README.md) để chạy kiểm tra. Các mục v50 trở xuống ghi lịch sử từng đợt, không phải số lượng mẫu hiện tại.

## Tư vấn theo menu, nút chọn và ảnh — 24/10/2026, v50

Qwen hiểu câu; Python lọc nguồn và điều khiển bước hỏi. Không chép menu vào system prompt hoặc fine-tune model.

- “Gợi ý giúp mình” hỏi loại món; Bánh kem/Trà hỏi độ ngọt, Cà phê hỏi kiểu uống, Bánh nhỏ hỏi vị. Chỉ hỏi bước còn thiếu. Nếu độ ngọt đã lọc còn 1–3 món thì gợi ý ngay; nếu còn nhiều món có thể hỏi nhóm vị.
- Câu đủ điều kiện như “Bánh kem trái cây ít ngọt dưới 400k” trả ngay. Nhiều nhóm trong một câu vẫn là các truy vấn riêng (tối đa bốn), không ép vào bảng hỏi đơn lẻ.
- Nút chọn hoặc số trong bảng đang hiển thị được giải mã thành câu có các điều kiện đã chọn, rồi vẫn qua Qwen/validation. Không dùng số của bảng cũ sau khi chuyển việc.
- Gợi ý theo bước tối đa ba món, có tên, giá nguồn và mô tả. Không hiện mã trong lời tư vấn/thẻ; ID vẫn cần bên trong API/link để đối chiếu. Ảnh local từ website tải lazy; ảnh lỗi tự ẩn.
- “Gì cũng được” chọn đa dạng trong điều kiện đã có, không gọi là bán chạy vì chưa có số liệu bán. “Xem thêm lựa chọn khác” giữ bộ lọc. Nếu thiếu đúng vị, chỉ mời xem vị khác và nói rõ; vẫn giữ ngân sách/nhóm/độ ngọt/dị ứng.
- advice_pending/quick_replies tách khỏi order_draft. Hỏi tư vấn không sửa đơn/REVIEW; tải lại trang khôi phục nút đang chờ bằng phiên hiện có.

Nguồn phân loại: data/recommendation_profiles.json chứa 24 hồ sơ do bạn cung cấp, đối chiếu ID/tên/nhóm với menu website; **không có bản sao giá**. Adapter lấy giá/ảnh từ nguồn hiện có. Metadata khác tên/nhóm không được áp nhầm khi tái dùng ID; có version/source/is_mock, cache theo thời gian sửa và không ghi DB trong lượt chat.

Vàng anh và Biển ngọc được ghi **vị ngọt, ngọt vừa** theo xác nhận của bạn; thành phần vị cụ thể chưa xác nhận. Không tự gán vani/trái cây hay tính an toàn dị ứng. Nguồn nhóm vẫn là dữ liệu tham khảo, chỉ lưu yêu cầu chờ tư vấn, chưa bật tạo đơn kinh doanh.

File nên đọc: data/recommendation_profiles.json → app/repositories/group_catalog.py → app/advice.py → app/schemas.py → app/conversation.py → app/api.py → static/chat.js. Truy vấn thêm sweetness, taste_family, coffee_style và advice. Nhãn tương đương trong JSON model được chuẩn hóa/validate, không tự phân loại intent từ câu khách.

Prompt tối đa hai ví dụ; ưu tiên mẫu trùng câu để tránh học nhầm ngân sách từ mẫu dài. Giữ qwen3.5:4b, num_ctx=4096, num_predict=768, timeout 60 giây, keepalive/prewarm và tối đa một lần sửa JSON. Không thêm lượt model để viết lời giới thiệu.

Kiểm tra thực tế:
- **404/404 dev + 33/33 test** bằng model giả; 238 ví dụ hợp schema. Thêm 20 lượt dev. Hai kỳ vọng cũ dev-178/dev-273 đổi theo metadata vị ngọt/vani bạn vừa cung cấp; bộ test cuối không đổi.
- Guard: 24 ID/giá khớp nguồn, vị khác vẫn dưới ngân sách, empty không bịa món, REVIEW hợp lệ/phiên riêng giữ nguyên.
- API/model giả + SQLite RAM: nút/số chọn, ảnh 200, resume giữ nút, lưu câu gốc, token chéo 404, timeout không sửa draft.
- Chrome headless/profile riêng: bấm loại/độ ngọt, hai ảnh thật, không hiện mã, reload giữ phiên/thẻ/nút, màn hình 390px không tràn ngang, không lỗi JavaScript; đã dọn profile.
- Qwen thật đã chạy chuỗi gợi ý → 1 → 3; trà/cà phê; “gì cũng được”; hai nhóm bánh kem+trà. Lượt đầu từng timeout, các lần trung gian còn lỗi sao chép ngân sách/nhãn vị được sửa tiếp, không tính là đạt.
- Sau sửa cuối, ba câu trọng điểm (trái cây ít ngọt dưới 400k; trái cây ít ngọt; bánh nhỏ cà phê/kem) **3/3 đúng, một NLU/câu, 12,33–15,33 giây**. Chưa chạy Qwen trên cả 437 mẫu hoặc benchmark máy khác; không gọi đây là độ chính xác/tốc độ toàn chatbot.
- Không sửa giá/website/giỏ/checkout, schema SQL, model hoặc DB đang dùng; không tạo tests/ hay docs/.

Khởi động lại run_web.py trong thư mục chatbot, mở URL website mà chương trình in ra hoặc http://127.0.0.1:8000/ để thử chat riêng. Bấm Chat mới để thử từ đầu.

## Nhiều yêu cầu và chuyển danh mục — 24/10/2026, v49

Đã sửa hai lỗi đang được báo, không thay model hoặc tạo chatbot thứ hai.

### Câu có nhiều yêu cầu

“Giới thiệu cho tôi một vài sản phẩm như bánh kem và trà” phải có hai request recommendation: cream_cake và tea. Intent là loại mục đích (ví dụ hỏi giá/tư vấn); request là một phần hỏi có đối tượng/điều kiện riêng. Hai nhóm có cùng intent vẫn cần hai truy vấn. Không được lấy danh sách của nhóm đầu làm đáp án cho cả câu.

Luồng giữ nguyên: Qwen → schema Pydantic → kiểm chứng tên/nhóm → từng truy vấn repository → trả lời từng phần → xử lý đặt hàng hợp lệ. Hỏi thông tin không sửa draft; điều kiện của trà không gán sang bánh kem. Câu trả lời nhiều nhóm thêm nhãn “Bánh kem:”, “Trà:” để dễ đọc.

Giới hạn hiện tại là **4 phần hỏi và 4 loại intent thông tin** mỗi tin. Thuộc tính cùng đối tượng có thể gộp một request trong giới hạn đó. Grammar và LLMWireTurn chặn output quá bốn; khi Qwen khai báo hơn bốn phần/loại, code chuyển toàn lượt thành thông báo giới hạn trung tính, không bỏ phần thứ năm im lặng hoặc thực hiện đơn một phần. Bản nháp/REVIEW giữ nguyên, thông báo vẫn được lưu trong lịch sử. Đây là kiểm tra số lượng từ JSON model, không đếm intent bằng regex.

mentioned_catalog_groups trong text_utils chỉ chọn ví dụ/kiểm chứng nhóm rõ; không tự tạo intent/filter/ID. Tên bánh nguồn và “vị trà xanh” được loại khỏi bằng chứng nhóm đồ uống. check_catalog_grounding bác output bỏ sót nhóm để Qwen sửa tối đa một lần. Cách viết cafe/cà phê hoặc không dấu được đối chiếu bằng alias đã thống nhất; chủ đề không có trong câu vẫn bị bác.

Few-shot v49 có 217 ví dụ, mỗi lượt vẫn tối đa hai. Hai mẫu năm phần cũ đổi về bốn; thêm cặp/ba/bốn nhóm và thông báo vượt giới hạn. Không fine-tune, không đưa evaluation vào prompt. Giữ Qwen qwen3.5:4b, num_ctx=4096, num_predict=768, keepalive/prewarm, timeout 60 giây và tối đa một lần sửa. Schema nội bộ vẫn đọc payload lịch sử cũ; giới hạn mới nằm ở luồng HTTP LLM. Các test fake legacy năm phần chỉ kiểm tra tương thích controller, không chứng minh Qwen mới được phép xử lý quá giới hạn.

Thử:
1. giới thiệu cho tôi một vài sản phẩm như bánh kem và trà
2. gợi ý bánh nhỏ và cà phê
3. gợi ý bánh kem, bánh nhỏ, trà và cà phê
4. gợi ý bánh kem dưới 400k và trà dưới 30k

Menu hiện có: câu 1 trả tối đa 4 bánh kem và 3 trà; câu 2 tối đa 4 bánh nhỏ và 3 cà phê; câu 3 có đủ bốn nhóm. Giá/tình trạng vẫn từ repository, không do model dựng. Chưa có nguồn thì nói chưa có menu, không bịa bánh/giá.

File nên đọc: app/text_utils.py → app/schemas.py → app/llm_client.py → app/order_nlu.py → app/conversation.py. Bộ thử và lệnh ở evaluation/README.md.

Kiểm tra thực tế sau sửa:
- 384/384 dev + 33/33 test model giả đạt; 14/14 lượt mới qua fake JSON → schema → grounding → controller; 217 ví dụ hợp schema.
- Trước sửa, hai câu cặp nhóm đã lỗi sau hai lần NLU, khoảng 29,6 giây/lượt. Lần trung gian 14 lượt đạt 11/14 hành vi, còn lỗi cafe trong clause và vượt giới hạn. Đã đọc JSON thật để sửa: model khai báo năm intent nhưng chỉ bốn request.
- Bộ Qwen cuối trọng điểm: **8/8 hành vi**, **7/8 extraction_exact**, 8 lần gọi, tổng **183,03 giây**, **16,86–43,02 giây/lượt**. Đủ hai nhóm, viết không dấu, bốn nhóm, hỏi giữa lúc đặt, empty và vượt giới hạn. Một lượt đặt có khác nhãn phụ nhưng hành vi đúng; không gọi đây là độ chính xác toàn chatbot.
- Lượt bốn nhóm 27,85 giây; lượt đầu 43,02 giây có khoảng 33,14 giây ở prompt evaluation. Ollama báo size_vram=0 (CPU), model đang nạp khoảng 3,14 GB, context 4096. Dựng prompt Python khoảng 33–58 ms trung vị trong các lần thử; phần lớn thời gian nằm ở model. Chưa có benchmark có kiểm soát để khẳng định tăng tốc toàn cục.
- API fake/RAM: trả đủ hai nhóm, khôi phục lịch sử/REVIEW, overflow lưu lịch sử và giữ REVIEW, JSON sai không sửa draft, token chéo bị chặn; số đơn tạo=0. Không gọi lại Qwen cho phục hồi trang hoặc thêm vòng model vào luồng bình thường.

### Mất widget khi chuyển danh mục

Sửa cache trước đó chưa đủ: đã tái hiện Cốc Cốc lấy HTML danh mục cũ từ disk cache, trong đó chưa có thẻ widget. Chỉ sửa script.js hoặc thêm no-cache ở server không thay được trang mà browser không gửi request lại.

Hiện URL các trang website có site_v=20261024-3, phiên bản cố định khi cập nhật, không timestamp theo mỗi click. Widget chuẩn hóa link nội bộ, giữ nguyên id/q/page, áp dụng cả link sản phẩm, form tìm kiếm GET và script mua ngay. config.js/script.js/widget script có phiên bản đồng bộ. HTML mới dùng no-store; JS/CSS kiểm tra ETag; ảnh giữ cache. pageshow khởi tạo idempotent khi quay lại từ BFCache. Không đổi giỏ hàng/checkout hoặc model.

run_web.py in địa chỉ website có phiên bản mới. Sau khởi động lại server, mở trực tiếp:
**http://127.0.0.1:8000/website/?site_v=20261024-3**

Không cần F5 mỗi khi chuyển danh mục. Kiểm tra đã chạy trên Cốc Cốc với profile tạm: nạp sẵn 9 trang HTML cũ vào cache, chuyển danh mục 12 lần không reload/F5, thêm phân trang/giỏ/checkout/tìm kiếm, giữ cùng conversation và hai tin nhắn khi widget mở hoặc thu thành nút tròn; không lỗi JavaScript. Chỉ RAM/profile kiểm tra riêng, không đọc/xóa cache cá nhân hay sửa database đang dùng.

## Widget chat trên website — 24/10/2026

Chạy một server để xem website và chatbot cùng origin:

```powershell
Set-Location 'D:\sweet-bakery-nhom6\chatbot'
.\.venv\Scripts\python.exe -B -X utf8 run_web.py
```

Mở **http://127.0.0.1:8000/website/?site_v=20261024-3** để dùng website với widget bên phải. Trang chat độc lập vẫn ở http://127.0.0.1:8000/ hoặc /chatbot/. run_web giữ prewarm và cấu hình Qwen, đồng thời in cả địa chỉ website và chat độc lập. Chạy --port 8001 thì các trang cùng origin dùng cổng mới tự động.

- Nút tròn mở khung chat; nút phóng to chuyển sang toàn bộ khung nhìn, bấm lần nữa về cửa sổ nhỏ; nút dấu trừ hoặc Escape thu về nút tròn. Thu nhỏ không hủy iframe hay lượt đang xử lý.
- Cùng giao diện/logic chatbot hiện tại, không tạo chatbot khác. iframe chỉ tải khi mở hoặc khi khôi phục trạng thái đang mở; tải trang/thu phóng không gọi Qwen.
- Khi chuyển trang, tải lại hoặc quay lại: sessionStorage của tab giữ conversation_id và token ngẫu nhiên. GET /api/conversations/{id} kiểm tra token/owner rồi đọc 100 tin đã lưu gần nhất và trạng thái REVIEW. Tin nhắn cũ dùng bản đã che liên hệ từ storage; không gửi lại tin/đơn hoặc tăng context của Qwen.
- Thẻ sản phẩm của truy vấn gần nhất có request scope được khôi phục; những lượt cũ còn nguyên văn bản. Bấm Xem bánh trong iframe mở chi tiết ở trang website cha. Thông điệp iframe chỉ nhận khi đúng origin và đúng window, không truyền token qua postMessage/URL.
- Giữ phiên trong cùng tab khi server còn chạy và token còn hạn (hiện 8 giờ). Đóng tab hoặc bấm Chat mới bắt đầu phiên khác. Sau khi server khởi động lại, session registry trong RAM không còn: giao diện yêu cầu Chat mới, không dùng ID để vượt quyền xem hội thoại cũ.
- Không dùng localStorage để lưu token. Nếu trình duyệt chặn sessionStorage thì có thông báo, chat trong trang hiện tại vẫn dùng được nhưng không đảm bảo khôi phục qua chuyển trang.

Nếu website chạy bằng Live Server/Flask riêng: giữ server run_web đang chạy; widget mặc định kết nối cùng hostname ở cổng 8000. Có thể đặt static/config.js của website: chatbotUrl: "http://127.0.0.1:8001/chatbot/" khi đổi cổng. Đây là URL trang chat, không phải API key. iframe gọi API ở origin của chính nó nên không cần mở CORS toàn cục. Nên mở website bằng HTTP, không mở file://.

File tích hợp: ../static/chatbot-widget.js và chatbot-widget.css; 9 trang HTML tải widget trực tiếp bằng script có phiên bản URL; ../static/config.js cấu hình URL. Widget không phụ thuộc script.js của giỏ hàng. Trong chatbot: app/api.py thêm route khôi phục phiên và alias /chatbot/; app/storage.py đọc lịch sử theo owner; static/chat.js/style.css/index.html hỗ trợ nhúng/khôi phục; run_web.py in thêm địa chỉ website. Không sửa menu, main.py, giỏ hàng, checkout, schema SQL, model hoặc FSM. Không thêm thư viện, tests/docs hay báo cáo.

Đã kiểm tra:
- 403/403 logic hồi quy (370 dev + 33 test) dùng model giả; không gọi lại Qwen thật vì lần này không đổi NLU/prompt.
- TestClient: 15 trang/tài nguyên trả 200; 10 lượt chat với JSON model giả; khôi phục history/cards/REVIEW, hai phiên riêng, token thiếu/hết hạn 401 và truy cập chéo 404. Giới hạn 100 tin, thứ tự, không gọi LLM khi khôi phục và không tạo đơn đều đúng.
- Kiểm tra đồng thời: resume chờ lượt chat đang chạy theo lock phiên, nhận đúng lịch sử sau đó; chỉ một lần gọi model, không gửi trùng.
- Chrome headless đã chạy thao tác desktop 1365×900 và mobile 390×844: chat, window/fullscreen/circle/Escape, liên kết sản phẩm, chuyển menu/reload/back và Chat mới; không có lỗi JavaScript.
- Website cổng 8767 và chatbot cổng 8766 thử riêng: chat tiếp sau khi thu gọn/chuyển trang, liên kết sang chi tiết và giỏ hàng giữ nguyên; postMessage giả không điều khiển được widget.
- Tất cả kiểm tra dùng SQLite RAM/profile trình duyệt tạm, không ghi/reset database đang dùng. Chưa thử thủ công Safari/Firefox, triển khai Internet hoặc khôi phục quyền sau restart server.

### Lịch sử lần sửa tải widget/cache trên Cốc Cốc — 24/10/2026

Đã tái hiện trường hợp browser dùng script.js cũ: sản phẩm vẫn hiện nhưng widget không được nạp. Tách thẻ script chatbot-widget.js?v=20261024-2 vào cả 9 trang HTML và bỏ loader cũ ở script.js. Script giỏ hàng cũ hoặc bị lỗi không ngăn widget chạy.

Server trả Cache-Control: no-cache cho HTML/JS/CSS để browser kiểm tra lại ETag; ảnh giữ cache và API vẫn no-store. Không đổi Qwen, session, FSM hoặc dữ liệu. Sau cập nhật lần đầu cần Ctrl+F5 để bỏ HTML đã cache trước đó.

Đã thử bằng Cốc Cốc 152 với profile tạm: widget vẫn hiện khi mô phỏng script.js cũ, hỏi giá 35.000đ, phóng toàn màn hình/thu nhỏ/nút tròn và giữ hai tin sau mở lại; không lỗi JavaScript. TestClient kiểm tra 7 đường dẫn cache, 304 cho static không đổi (trang /chatbot/ FileResponse trả 200 hợp lệ), API no-store, 9 trang mỗi trang đúng một thẻ widget; hồi quy API/history/REVIEW/quyền phiên/lock vẫn đạt. Chỉ model giả/rule và SQLite RAM, không gọi lại Qwen hoặc ghi database đang dùng.

Lúc kiểm tra, địa chỉ http://127.0.0.1:8000/website/ chưa có server trả lời. Cần chạy run_web.py và giữ terminal mở; đây là website local, không phải link đã deploy. Phiên/cache/hồ sơ Cốc Cốc cá nhân chưa được truy cập hoặc thay đổi; không kết luận nguyên nhân duy nhất trên profile của người dùng.

## Chạy trên Windows

Mở PowerShell trong đúng thư mục chatbot:

```powershell
Set-Location 'D:\sweet-bakery-nhom6\chatbot'
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DATA_SOURCE = 'group_files'
$env:GROUP_CATALOG_PATH = '../static/products.json'
$env:ORDER_PROVIDER = 'unsupported'
$env:KNOWLEDGE_MODE = 'empty'
$env:DATABASE_PATH = 'runtime/chatbot.sqlite3'
$env:CHAT_MODE = 'ollama'
$env:OLLAMA_BASE_URL = 'http://127.0.0.1:11434'
$env:OLLAMA_MODEL = 'qwen3.5:4b'
$env:OLLAMA_TIMEOUT_SECONDS = '60'
ollama list
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.database classify-flavors
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.check_group_data
.\.venv\Scripts\python.exe -B -X utf8 run_web.py
```

Mở **http://127.0.0.1:8000/**. Website nhóm được phục vụ chỉ đọc tại `/website/`; danh mục chatbot ở `/api/catalog`, trạng thái ở `/health`. Dừng bằng Ctrl+C; có thể chạy `run_web.py --port 8001` nếu cổng bận.

Nếu chưa có môi trường ảo: `py -3.12 -m venv .venv`, rồi cài requirements như trên. Môi trường ảo tách thư viện dự án khỏi Python hệ thống; không đưa `.venv` vào Git. Trong VS Code chọn **Python: Select Interpreter → .venv/Scripts/python.exe**.

Chương trình đọc `chatbot/.env` nếu có; biến môi trường PowerShell ưu tiên hơn. `.env.example` là mẫu công khai. Không ghi khóa dịch vụ hoặc dữ liệu cá nhân thật vào code/log.

Ollama phải chạy và model phải đã cài. Nếu dịch vụ chưa chạy, mở terminal khác và dùng `ollama serve`. Không chạy thêm server Ollama khi ứng dụng Ollama đã phục vụ cổng 11434. Project không tự tải hay đổi model; `ollama list` phải có đúng tên đang cấu hình.

## Chat trên web

Chạy run_web.py rồi mở http://127.0.0.1:8000/. Nhấn **Chat mới** để bắt đầu phiên riêng. Bản tóm tắt yêu cầu được hiển thị trước khi lưu; API tra cứu yêu cầu vẫn kiểm tra token phiên và quyền sở hữu. Biết conversation_id/order_id không đủ quyền xem dữ liệu của người khác.

Đã bỏ giao diện chat hỏi–đáp trong terminal. Các lệnh quản lý database, kiểm tra dữ liệu và đánh giá vẫn chạy bằng PowerShell khi cần. Web không import entry terminal, nên việc bỏ nó giúp mã nguồn gọn hơn, không làm Qwen trên web suy luận nhanh hơn hoặc giảm RAM model.

Kiểm tra sau khi gỡ: 33 file Python hợp cú pháp; import API/run_web không nạp module terminal. TestClient tải trang/JS/CSS/health/catalog trả 200 (24 sản phẩm), tạo phiên 201, chat với model giả 200; thiếu token 401, truy cập chéo phiên 404, tin nhắn quá dài 422. Dùng SQLite RAM, không ghi database đang dùng. run_web.py --help hoạt động. Chưa gọi lại Qwen thật hoặc click/render trình duyệt trong lần gỡ này. Các dependency hiện tại vẫn cần cho web nên giữ nguyên.



## Đổi nhóm gợi ý không giữ nhầm giá — v48, 20/10/2026

Đã tái hiện bằng Qwen thật: “giá bánh trên 400k” trả hai mousse 450k, rồi “gợi ý trà/cà phê/bánh nhỏ” không có kết quả; “gợi ý bánh kem” vẫn chỉ hai mousse. Model đã trả search_scope=new, nhưng conversation.apply_query_updates cố ý giữ hai cận giá cũ. Vì vậy đây có lỗi quản lý bộ lọc của Python, không chỉ lỗi hiểu câu của model.

Quy tắc hiện tại:
- Tìm mới (requests.search_scope=new): bỏ nhóm, vị, số người, size, dịp và toàn bộ khoảng giá cũ; chỉ áp dụng điều kiện của yêu cầu mới. Dị ứng và bản nháp đặt hàng không bị xóa.
- Câu nối chỉ đổi giá/vị hoặc nói rõ “vẫn/giữ/như cũ” dùng refine. “Vẫn trong ngân sách đó, gợi ý trà” giữ ngân sách; “gợi ý trà” là tìm mới. Có thể lặp cùng nhóm “gợi ý bánh kem” để xem nhóm đó không bị khóa vào giá trước.
- Bỏ cờ inclusive nếu không còn cận tiền tương ứng. Không xóa lịch sử, không sửa slot/revision/REVIEW khi chỉ hỏi thông tin.

File sửa: app/conversation.py (apply_query_updates); app/llm_client.py (prompt, chọn mẫu, hướng dẫn sửa JSON); app/order_nlu.py (check_turn_grounding kiểm chứng scope thực sự kế thừa sai); data/nlu_few_shots.json (v48, 209 mẫu, mỗi lượt vẫn tối đa hai). Bổ sung 20 lượt vào evaluation/intent_context_dev.json, giữ nguyên 350 nhãn cũ và 33 câu test cuối. Qwen vẫn là bộ hiểu câu chính, không có fine-tuning hay nhánh regex thay model.

Chuỗi thử trên Chat mới:
1. già bánh trên 400k
2. gợi ý cho tôi một số loại trà
3. gợi ý cho tôi một số loại cà phê
4. gợi ý cà phê
5. gợi ý bánh kem
6. gợi ý bánh nhỏ

Kỳ vọng với menu nhóm đang đọc: bước 1 có hai mousse 450.000đ; trà có 3 loại, cà phê có 3 loại; bánh kem gợi ý tối đa 4/12, bánh nhỏ tối đa 4/6. Danh sách gợi ý không có ràng buộc giá được lấy từ toàn nhóm và có thể thay đổi thứ tự. Hỏi xen giữa lúc đang đặt không đổi món/số lượng trong bản nháp. Nguồn empty vẫn thông báo chưa có menu.

Kiểm tra thực tế sau sửa cuối:
- Logic model giả: 370/370 dev + 33/33 test đạt; 20/20 lượt mới qua cả fake JSON client/schema/grounding; 209 ví dụ hợp schema.
- Qwen local qwen3.5:4b: 20/20 lượt đạt hành vi, 14/20 khớp toàn bộ nhãn trích xuất; 20 lần NLU, tổng 102,01 giây, 3,65–7,86 giây/lượt. Không coi đây là độ chính xác toàn chatbot. Lần trung gian 17/20 còn lỗi giữ giá tham chiếu và câu hai nhóm đã được sửa rồi chạy lại; không cộng lượt lỗi vào điểm cuối.
- API TestClient: 13 lượt chat 200, 5 tài nguyên GET 200, tạo hai phiên 201; ngữ cảnh nhóm, bản nháp, số lượng, timeout, cách ly phiên và 401/404/422 đúng. SQLite chỉ trong RAM, số đơn tạo=0. Kiểm tra REVIEW/timeout, giữ dị ứng, giá mới/refine và cờ biên rời đạt.
- Dựng prompt trung vị khoảng 25 ms/15 lần, vẫn tối đa hai ví dụ. Giữ prewarm, keepalive, model, num_ctx=4096, num_predict=768, giới hạn sửa một lần và deadline 60 giây. Chưa đo benchmark nhiều lần, chưa đánh giá Qwen toàn bộ 370 lượt hoặc click/render trình duyệt.
- Không sửa database đang dùng, menu/website bên ngoài, frontend hoặc dependency; không tạo thêm docs/tests/report/module.

Ctrl+C server cũ rồi chạy lại run_web.py để nạp code; bấm Chat mới để thử từ đầu. Hội thoại cũ vẫn được giữ và yêu cầu tìm mới tiếp theo tự bỏ giá cũ. Lệnh kiểm tra nằm trong evaluation/README.md.

## Giá tiền, câu nối và trạng thái hàng — v47, 20/10/2026

Đã sửa chuỗi “gợi ý một số sản phẩm cùng giá 35k” → “sản phẩm trên 100k”. Câu sau tìm lại toàn danh mục với giá >100.000đ, không bắt khách chọn trong các thẻ 35.000đ trước đó; bản nháp đang đặt giữ nguyên. Nếu khách chỉ nói “trên 100000 thì sao?”, điều kiện giá mới thay điều kiện cũ và vẫn giữ nhóm đã nêu rõ. “Sản phẩm…” là tìm toàn menu; “sản phẩm đó/thứ hai…” vẫn là tham chiếu.

- 35k, 35000, 35.000, 35 nghìn/ngàn, 35000đ và 35,000 đồng được đối chiếu thành 35.000 VNĐ trong câu hỏi giá. “Cùng/đồng/đúng giá X” hoặc “sản phẩm giá X” lọc hai cận bằng X; “ngân sách X/tối đa X” là cận trên. Không tự hiểu số 35 không đơn vị thành 35 nghìn.
- “2 bánh … giá 35000” giữ số lượng=2, không dùng giá làm số lượng. Giá bán cuối luôn lấy từ repository.
- Tên bánh đứng riêng sau tư vấn đã hoàn tất là đối tượng xem mới. continue_information không phát lại khoảng giá cũ vào câu này; các câu đang chờ chọn món, số thứ tự và luồng đặt vẫn giữ cách xử lý riêng.
- Theo yêu cầu, **24 sản phẩm menu nhóm luôn có stock_status=in_stock** trong adapter chatbot. Đây là mặc định của nguồn mẫu group_files, không ghi vào JSON website hay giả lập số lượng kho. available_only hoạt động với nguồn này. Mock/local_demo, empty và adapter thật không bị thay kho; can_accept_real_orders/can_create_demo_orders của nguồn nhóm vẫn false, nên không tự bật xác nhận đơn.
- Sửa build_turn_messages để chọn đúng ví dụ tiền/giá theo nhóm; không ép mẫu nhập liên hệ khi khách hỏi sản phẩm hoặc giá. 202 few-shot lưu trên đĩa, mỗi lượt vẫn tối đa hai. Giữ Qwen, prewarm, num_ctx=4096, num_predict=768, tối đa một lần sửa và deadline 60 giây. Không thêm dependency/module/docs/tests/report.

Thử trên Chat mới:
1. gợi ý một số sản phầm cùng giá 35k
2. sản phẩm trên 100k
3. bánh cuộn trà xanh
4. sản phẩm giá 35000
5. sản phẩm đúng 35000 VNĐ
6. sản phẩm từ 35000 tới 45000 có gì?
7. Bánh cuộn trà xanh còn hàng không?

Kỳ vọng: đúng 35.000đ có 6 bánh nhỏ, hiển thị tối đa 4; trên 100.000đ có 12 bánh kem, hiển thị tối đa 4. Bánh cuộn trà xanh giá 35.000đ, trạng thái còn hàng. Không hỏi lại lựa chọn chỉ để đổi cận tiền.

Kiểm tra thực tế:
- Model giả/controller: **350/350 dev + 33/33 test**; 29 lượt mới qua cả fake JSON client/schema/grounding đạt 29/29; 202 ví dụ hợp schema. Chỉ bốn kỳ vọng chữ tồn kho cũ (dev-063/065/071/309) đổi sang “còn hàng” theo yêu cầu; không đổi nhãn intent cũ hoặc bộ test cuối.
- Qwen thật qwen3.5:4b: **29/29 hành vi**, **26/29 extraction_exact**, 30 lần NLU, tổng 195,51 giây; **3,74–13,89 giây/lượt**. Một khoảng giá không đơn vị cần sửa một lần; phần lớn lượt dùng một lần gọi. Khác toàn bộ nhãn trích xuất vẫn được báo riêng, không coi model đã hiểu mọi câu.
- Trước sửa tái hiện được sai “cùng giá” thành cận trên/cận dưới và thiếu ví dụ cho sản phẩm/tiền không đơn vị; có lượt hai lần gọi vẫn lỗi. Lần trung gian 23/27 còn lỗi VNĐ/giá theo nhóm/câu nối/tồn kho không được tính đạt; đã sửa rồi chạy lại.
- Tám dạng tiền, giá so với ngân sách/ngày/số nhỏ, số lượng, tham chiếu, mặc định hàng và giữ REVIEW khi timeout đã kiểm tra. Chuẩn bị prompt trung vị khoảng 28 ms/15 lần trên máy này; model vẫn chiếm phần lớn thời gian, không phải chatbot phản hồi tức thời.
- API TestClient: 5 tài nguyên GET 200, catalog 24 sản phẩm in_stock, hai phiên 201, 9 lượt chat 200; đổi giá/giữ draft/số lượng/timeout và 401/404/422 đúng. Chỉ SQLite RAM, không ghi/reset DB đang dùng; không tạo đơn. Chưa click/render trực tiếp trình duyệt.

Đọc app/text_utils.py → app/llm_client.py → app/order_nlu.py → app/conversation.py → app/repositories/group_catalog.py. Chi tiết nhãn/lệnh chạy ở evaluation/README.md. Đây là cải thiện prompt/ví dụ/validation, không fine-tuning. Ctrl+C web cũ rồi chạy lại run_web.py để nạp thay đổi.

## Nhiều yêu cầu trong một tin nhắn — v46, 20/10/2026

Đã thử câu có 3–5 yêu cầu khác nhau: hỏi thuộc tính từng món, hỏi giá năm món, tư vấn nhiều nhóm với ngân sách riêng, hỏi chính sách chưa có nguồn, hỏi xen giữa lúc đặt và thêm món. Dữ liệu thử nằm trong evaluation/intent_context_dev.json, không gửi nhãn đó cho Qwen.

Lỗi tìm thấy: Qwen ghép thuộc tính của nhiều món thành một yêu cầu, tự lọc mọi tên thành bánh nên mất cà phê, và gán nhầm nhóm/ngân sách. Một lượt “thêm 1 bánh… rồi hỏi giá/vị/tồn kho” còn chọn ví dụ nhập tên liên hệ, lặp câu hỏi và thiếu thao tác thêm.

Đã sửa:
- llm_client.build_turn_messages chọn mẫu nhiều yêu cầu phù hợp, không ép mẫu liên hệ khi khách đang hỏi/chọn nhiều món. Tổng 185 ví dụ, vẫn tối đa hai ví dụ mỗi lượt.
- schemas kiểm tra điều kiện tìm chỉ đi với recommendation; mỗi câu tư vấn trong tin nhắn nhiều yêu cầu phải có clause nguyên văn để kiểm chứng riêng. order_items phải có thao tác select/add/remove rõ, không gom món chỉ hỏi thông tin vào đơn.
- order_nlu.check_catalog_grounding bác lỗi bỏ/gán sai câu hỏi vị có tên nguồn rõ; không biến sở thích/phủ định thành câu hỏi vị. Qwen vẫn hiểu câu, code không tự trích ý định thay model.
- conversation.deduplicate_information_tasks gộp thuộc tính cùng sản phẩm/cùng điều kiện vào một lần tra cứu. Không gộp các nhóm tư vấn khác nhau. Mỗi scope lưu result_product_ids để kiểm tra kết quả từng yêu cầu; bộ nhớ giữ tối đa năm câu hỏi trong mỗi lượt, tám lượt tóm tắt, context model vẫn giới hạn như trước.
- Grammar model giới hạn tám request thay vì cho lặp đến 16; schema nội bộ vẫn đọc payload cũ. Giữ model/num_ctx=4096, num_predict=768, prewarm, timeout 60 giây và tối đa một lần sửa. Không thêm dependency hoặc sửa frontend/menu/database đang dùng.

Kết quả thực tế:
- Logic model giả: **321/321 dev + 33/33 test**; 185 mẫu hợp schema. 14 lượt mới còn qua JSON client/schema/grounding giả: 14/14.
- Qwen thật: đầu đợt bốn câu chọn lọc chỉ một câu trả đủ đúng; không lấy lượt lạnh 22,22 giây làm benchmark. Sau các sửa cuối, **14/14 lượt đạt hành vi và nhãn extraction**, 14 lần gọi NLU, tổng **171,89 giây**, **5,19–30,28 giây/lượt** trên máy này.
- Hỏi thông tin 3–5 yêu cầu: khoảng 5–11 giây; ba/bốn nhóm tư vấn: khoảng 19–30 giây; vừa hỏi vừa đặt/thêm: khoảng 11–15 giây. Lượt thêm từng bị lặp 37,43 giây đã đúng ở 15,27 giây trong lần chạy sau. Chưa có benchmark lặp nhiều lần để kết luận tăng tốc toàn cục; câu tư vấn nhiều điều kiện vẫn chậm.
- 13 kiểm tra guard/gộp/REVIEW/timeout/retry/phủ định đạt. Năm thuộc tính một món được gộp thành một truy vấn. Model sai không phá REVIEW hay tạo đơn.
- API TestClient: 5 tài nguyên GET 200, hai phiên 201, 9 lượt chat 200; đúng các món/bản nháp, phiên tách biệt, 401/404/422 và timeout đúng. SQLite thử chỉ trong RAM, đơn ghi nhận=0. Chưa click/render trực tiếp trình duyệt.
- Nguồn group_files vẫn chỉ lưu yêu cầu chờ tư vấn; thiếu chính sách/tồn kho/allergen thì nói chưa đủ dữ liệu. Không biến dữ liệu nguồn thiếu thành khẳng định có hàng hoặc chính sách thật.

Khởi động lại web rồi chọn Chat mới. Ví dụ:
1. “Cho mình giá bánh kem Vàng anh, hương vị bánh cuộn vani và cà phê muối còn không?”
2. “Gợi ý bánh kem 300k đến 400k, bánh nhỏ vị dâu dưới 50k và trà dưới 30k.”
3. “Bánh kem Vàng anh giá bao nhiêu, bánh cuộn vani vị gì, cà phê muối còn không? Đặt giúp tôi 2 bánh cuộn vani.”
4. Tiếp tục: “Thêm 1 bánh cuộn trà xanh. Mousse Hawaii giá bao nhiêu, bánh cuộn vani vị gì, cà phê muối còn không?”

Không coi 14 lượt đạt là mọi câu tiếng Việt đều đúng hoặc model đã được fine-tune. Chức năng còn phụ thuộc dữ liệu nguồn và tốc độ suy luận Ollama.

## Ngân sách và cách nói tương đương — v45, 19/10/2026

Đã sửa lỗi “tôi có 300k đến 400k có bánh kem nào trong giá đó ko”. Menu có 10 bánh kem trong khoảng này; bot hiển thị tối đa 4 kết quả, lấy giá từ repository. Trước sửa, bộ chọn ví dụ ghép mẫu hỏi giá/đặt bánh vào câu tìm theo khoảng, Qwen bỏ hoặc đảo cận giá. Lượt model thử trước sửa bị từ chối sau hai lần gọi; đây không phải thiếu sản phẩm.

Bộ chọn ví dụ và bộ kiểm chứng dùng chung cách đọc tiền trong app/text_utils.py. Qwen vẫn trích ý định, nhóm, vị, khoảng tiền và hành động; Python kiểm tra JSON, bằng chứng số và nguồn sản phẩm. Không tự gán filter bằng regex hay bỏ qua model khi lỗi.

Các cách nói được bổ sung:
- Khoảng tiền: “300k đến 400k”, “300-400k”, “300 đến 400 nghìn”, “0,3tr đến 0,4tr”, “300.000đ đến 400.000đ”.
- Cận giá: dưới/chưa tới/rẻ hơn; trên/đắt hơn; không quá/không vượt/tối đa; không dưới/ít nhất/trở lên; trở xuống/đổ xuống; đúng một mức giá.
- Nhóm: bánh kem/bánh sinh nhật/gato, bánh nhỏ/bánh mini/bánh ăn vặt, cà phê/cafe/coffee/cf; câu có hoặc không dấu, ko/bn/bao nhiu.
- Tên rút gọn như “cf muối”, “gato Vàng anh” được đối chiếu alias sinh từ tên nguồn, không hardcode ID/giá trong NLU.
- Hỏi nhóm cùng khoảng tiền mới bỏ vị cũ không được nhắc lại; “vẫn/giữ vị đó” hoặc câu nối chỉ đổi ngân sách giữ điều kiện còn phù hợp. Hỏi thông tin không sửa bản nháp.

Thử trên **Chat mới**:
1. tôi có 300k đến 400k có bánh kem nào trong giá đó ko
2. 300-400k có bánh sinh nhật nào không?
3. Có gato nào không vượt 400k?
4. cf muối bn tiền, còn bán ko?
5. Gợi ý bánh kem vị dâu dưới 400k → Có bánh kem nào từ 300k đến 400k?

Câu đầu hiện trả Mousse Hawaii 320.000 đ, Mousse Chanh leo 350.000 đ, Mây trắng 360.000 đ, Mây xanh 360.000 đ; tổng 10 sản phẩm phù hợp trong menu đang đọc. Hai câu có cùng điều kiện dùng cùng bộ lọc; không tự tạo thêm bánh khi không có kết quả. “Giá bao nhiêu?” dùng sản phẩm đang trao đổi nếu rõ; khi chưa có đối tượng vẫn cần hỏi tên, không đoán.

Kiểm tra thực tế:
- Model giả/controller: **307/307 dev + 33/33 test**. Thêm 34 lượt trong 8 hội thoại, giữ nguyên nội dung bộ test cuối.
- 34 lượt mới còn được chạy qua client JSON giả → schema → grounding → controller: **34/34**, mỗi lượt một lần gọi giả. Không dùng số này làm độ chính xác Qwen.
- **Qwen thật qwen3.5:4b: 34/34 hành vi**, 27/34 khớp toàn bộ nhãn trích xuất, 36 lần NLU, tổng 214,94 giây; 3,18–10,62 giây/lượt. Hai lượt cần sửa một lần. Khác biểu diễn alias/filter mặc định không đồng nghĩa câu trả lời sai; vẫn chưa chứng minh mọi câu tiếng Việt đều được hiểu.
- 175 ví dụ đi qua schema; 25 kiểm tra tiền/alias và 6 kiểm tra sai cận/scope/retry/timeout đạt. Chuẩn bị prompt khoảng 20 ms trung vị/15 lần trên máy này, không phải thời gian model.
- API TestClient: trang/JS/CSS/health/catalog 200, hai phiên 201, bảy lượt chat 200; lỗi nguồn/timeout rõ, bản nháp không đổi khi hỏi, phiên khác 404/thiếu token 401, quá dài 422; không tạo đơn.
- Mọi hội thoại thử dùng SQLite RAM; không ghi/reset database đang dùng hoặc sửa menu/website nhóm. Chưa click/render trình duyệt. Giữ prewarm, model, num_ctx=4096, tối đa hai few-shot và một lần sửa, không thêm dependency hoặc file docs/tests/report.

Khởi động lại run_web.py để nạp code mới, rồi Chat mới. Đây là cải thiện prompt, ví dụ và kiểm chứng đầu ra; **không phải fine-tuning/huấn luyện lại trọng số**.

## Hương vị danh mục — v44, 19/10/2026

Đã lưu phân loại của **24 sản phẩm nhóm** vào SQLite chatbot, trong bảng database_metadata, key **catalog_flavors:group_files:v1**. Mỗi mã SP có tên/nhóm đối chiếu, product_type, flavor và style_tags. Dùng một bản ghi JSON nhỏ trong bảng sẵn có; không nhân bản menu/giá/tồn kho thành nguồn thứ hai, không sửa 25 sản phẩm local_demo hay file website nhóm.

- **Bánh kem (12)**: vị chanh leo, vải–hoa hồng, quả mọng, socola được nêu rõ ở 4 bánh; 8 tên trang trí như Hawaii, Vàng anh, Mây trắng chưa đủ căn cứ, giữ flavor=null.
- **Bánh ngọt nhỏ (6)**: socola, trà xanh, vani, socola–dâu, tiramisu theo đúng tên.
- **Trà (3)**: trà sữa, Thái xanh, đào. Không tự coi Thái xanh là matcha.
- **Cà phê (3)**: cà phê và muối theo tên; đen/ủ lạnh lưu riêng trong style_tags vì là đặc điểm chế biến. Bộ lọc chấp nhận kiểu này trong yêu cầu vị nhưng câu trả lời phân biệt với hương vị.

Tên tương đương được đối chiếu bằng từ vựng: vanilla/vani, strawberry/dâu tây/dâu, matcha/trà xanh, passion fruit/chanh dây/chanh leo, cold brew/ủ lạnh. Không suy độ ngọt, độ đắng, thành phần/allergen từ kiến thức chung. Điều kiện không có dữ liệu không được tự coi là thỏa.

Adapter đọc metadata một lần rồi cache trong bộ nhớ. Không ghi SQLite hoặc gọi model riêng để phân loại mỗi tin nhắn. Tên/nhóm sản phẩm đổi thì không áp nhãn cũ; giá luôn đọc từ file nguồn hiện tại. Chạy lại phân loại sau khi cập nhật menu, rồi khởi động lại web để nạp cache:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.database classify-flavors
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.check_group_data
.\.venv\Scripts\python.exe -B -X utf8 run_web.py
```

Lệnh phân loại chỉ ghi metadata trong database bên trong chatbot; chạy lặp không nhân bản và không sửa dữ liệu ngoài phân loại. Database đã được cập nhật trong lần sửa này: **16 sản phẩm có vị nêu trong tên, 8 chưa xác định**. Các bảng sản phẩm/tồn kho/hội thoại/đơn và metadata khác đã được đối chiếu giữ nguyên.

Thử trên Chat mới: “Gợi ý bánh nhỏ vị vanilla dưới 50k”, “Bánh nhỏ vị dâu tây dưới 50k có loại nào?”, “Gợi ý bánh kem vị chanh dây dưới 400k”, “Gợi ý trà vị sữa dưới 30k”, “Gợi ý cà phê cold brew dưới 50k”. Thứ tự đọc code: app/repositories/mock_catalog.py → group_catalog.py → scripts/database.py → app/order_nlu.py.

Kiểm tra thực tế:

- **273/273 lượt dev + 33/33 lượt test fake**, 159 ví dụ hợp schema. Thêm dev-262…273, giữ nguyên bộ test cuối.
- **22 trường hợp lọc/lưu trữ** đạt, gồm giá, đúng nhóm/vị, nhãn chưa biết, dị ứng thiếu dữ liệu, phân loại lặp, cache một lần, đổi tên/giá nguồn, metadata sai và đường dẫn có dấu/khoảng trắng. Database thử tạm đã xóa.
- **Qwen thật: trước sửa phần hiểu câu 10/12, sau sửa 12/12 hành vi** trên hai hội thoại vị/kiểu pha; extraction_exact sau sửa 9/12 vì có cách biểu diễn/alias khác nhãn. Hai câu hồi quy khoảng giá cà phê và trà dưới 50k đều đạt, mỗi câu một lần NLU.
- 12 lượt chính mất 5,42–14,02 giây/lượt; 14 lần NLU (hai lượt sửa một lần). Không công bố tốc độ tức thời hoặc độ chính xác toàn bộ model. Sửa code kiểm chứng chanh_day/chanh dây, giữ dấu để “đến 50k” không bị coi là cà phê “đen”; chọn mẫu theo chủ đề thay vì ghép lệnh đặt vào câu tư vấn.
- API đọc đúng 24 phân loại từ SQLite, 12 lượt chat qua TestClient trả 200 đúng sản phẩm; phiên mới 201, thiếu token 401/truy cập chéo phiên 404, không tạo đơn. 33 file Python hợp cú pháp và import được API/run_web.
- Chưa click/render trình duyệt; chưa có công thức/khẳng định hương vị chính thức cho 8 tên chưa rõ. Giữ Qwen, prewarm, context, timeout, tối đa hai few-shot và một lần sửa. Không tạo docs/tests/report hay thêm dependency.


## Nhập thông tin liên hệ bình thường — v43

Đã bỏ quy định tên bắt đầu DEMO và điện thoại bắt đầu TEST ở prompt, tiền kiểm tra tin nhắn, FSM và bước kiểm tra trước khi gửi. Bot hỏi “Bạn cho mình tên người liên hệ nhé.”, rồi “Bạn cho mình số điện thoại liên hệ nhé.”. Có thể cung cấp tên và điện thoại cùng câu; thông tin đã nhận không bị hỏi lại khi chen ngang hỏi giá.

Điện thoại được giữ dạng chuỗi để không mất số 0 đầu. Code chấp nhận 8–15 chữ số, dấu + ở đầu và dấu cách/chấm/gạch nối, rồi bỏ dấu phân cách khi lưu. Đây chỉ là kiểm tra cú pháp, không xác minh số đang hoạt động hay quyền sở hữu. Sai định dạng thì bot chỉ rõ cần nhập lại, giữ bản nháp và bước liên hệ đang chờ. Bản REVIEW chưa gửi dùng mã TEST từ phiên cũ phải nhập lại số; snapshot yêu cầu đã gửi không bị đổi.

Ví dụ (tên và số dưới đây là dữ liệu tổng hợp cho tài liệu):

1. Đặt giúp mình 2 Bánh cuộn vani.
2. Khách An.
3. 0900000001.
4. Kiểm tra bản tóm tắt rồi nói: Xác nhận gửi yêu cầu.

Web hiển thị “Danh mục tham khảo”, bỏ dòng yêu cầu liên hệ DEMO/TEST. Menu nhóm vẫn là nguồn tham khảo chỉ đọc, thiếu tồn kho và công cụ tạo đơn kinh doanh: kết quả cuối là “Đã lưu yêu cầu chờ tư vấn.”, kèm mã thực sự trả về. Chưa tích hợp xác nhận đơn, thanh toán hay gửi thông báo cho nhân viên. Chế độ mock/local_demo còn giữ nhãn mô phỏng đúng nguồn.

Giữ Qwen local, prewarm, num_ctx=4096, tối đa hai ví dụ mỗi lượt và tối đa một lần sửa JSON. Không thêm dependency, file docs/tests hoặc thay đổi website/menu nhóm. Lệnh chạy vẫn là .\.venv\Scripts\python.exe -B -X utf8 run_web.py; Ctrl+C chương trình cũ rồi chạy lại để nạp sửa đổi.

Kiểm tra thực tế trên bản v43:
- Fake model/SQLite RAM: 261/261 lượt dev, 33/33 lượt test đạt hành vi; 156 ví dụ đi qua schema hợp lệ.
- Qwen thật: 10/10 lượt chọn lọc đạt hành vi, không lỗi model cuối; thời gian 3,26–12,21 giây/lượt, tổng 59,31 giây. Gồm luồng tám lượt và câu cung cấp món/tên/số trong một lần.
- So khớp toàn bộ nhãn NLU chỉ đạt 1/10 ở mười lượt đó, khác với điểm hành vi: còn khác biểu diễn null/none, vị trí số lượng và chuẩn hóa số. Chưa đánh giá mọi câu hoặc công bố model hiểu hoàn hảo.
- API TestClient tải trang/JS/CSS/health/catalog trả 200, tạo phiên 201, tám lượt chat trả 200; một yêu cầu chờ tư vấn, một ticket, không có đơn kinh doanh. Xác nhận lặp giữ cùng mã. Token thiếu 401; truy cập chéo phiên 404; model timeout giữ nguyên bản nháp.
- 33 file Python hợp cú pháp, import API/run_web và run_web.py --help hoạt động. Kiểm tra số có dấu phân cách, số sai, bản nháp cũ, snapshot đã gửi, giữ revision khi số không đổi, che liên hệ trong lịch sử và không gửi lại liên hệ cũ trong prompt đều đạt.
- Chỉ dùng SQLite RAM cho các kiểm tra, không ghi/reset database đang dùng. Chưa click/render trên trình duyệt hay kiểm tra số điện thoại thực sự liên lạc được; chưa nối backend xác nhận đơn.

## Năm vai trò và đường đi dữ liệu

Intent là ý định; slot là thông tin như sản phẩm/số lượng. Schema là cấu trúc dữ liệu được Pydantic kiểm tra. LLM (mô hình ngôn ngữ lớn) đề xuất cách hiểu và hỗ trợ diễn đạt; Python kiểm tra và thực hiện nghiệp vụ.

| Vai trò | File chính | Trách nhiệm |
| --- | --- | --- |
| LLM hiểu ngôn ngữ | `llm_client.py`, `schemas.py`, `data/nlu_few_shots.json` | Qwen trích nhiều intent, câu hỏi riêng, mention, tham chiếu và thay đổi slot; không quyết định giá/tồn kho. |
| RAG hỏi chính sách | `knowledge_loader.py`, `retrieval.py` | Nạp tài liệu, tìm tối đa 3 điều khoản, gửi nguồn cho Qwen và kiểm tra trích dẫn. |
| Catalog lấy sản phẩm | `repositories/catalog.py`, `repositories/group_catalog.py` | Đối chiếu tên/alias, ID, giá và khả năng của nguồn; logic không đọc JSON nhóm trực tiếp. |
| FSM và business tools | `order_flow.py`, `order_nlu.py`, `order_service.py`, `handoff.py` | Cập nhật bản nháp, kiểm tra điều kiện, REVIEW/xác nhận và lưu yêu cầu hoặc ticket hợp lệ. |
| Bộ nhớ và điều phối | `conversation.py`, `storage.py` | Tách ngữ cảnh từng khách, trả câu hỏi trước thao tác đặt, lưu/khôi phục hội thoại. |

```text
Tin nhắn + tóm tắt ngữ cảnh → Qwen → Pydantic + kiểm tra căn cứ
→ repository / RAG → trả các câu hỏi rõ trước
→ FSM + tool hợp lệ → phản hồi + lưu SQLite chatbot
```

Repository là lớp lấy dữ liệu qua interface. FSM là máy trạng thái: BROWSING → COLLECTING → REVIEW; sau đó nguồn nhóm chỉ lưu chờ tư vấn/HANDOFF. Tool là hàm nghiệp vụ có kết quả rõ, không phải lời model tự tuyên bố đã tạo đơn.

`LLMWireTurn` là schema JSON gửi/nhận qua HTTP. **intents và requests luôn bắt buộc**. Lượt thông tin được bỏ action/product_mentions/order_items/updates rỗng; Python điền default (giá trị mặc định) trước khi kiểm tra schema nội bộ. **Khi có order_request, cả bốn trường đó phải thực sự có trong JSON**, kể cả khi rỗng; không dùng default để che thiếu dữ liệu đặt hàng. Mỗi order_item có product_mention hoặc reference và quantity riêng. Mention chỉ là tên khách nói, repository mới xác minh product_id.

Update là phần thay đổi của lượt hiện tại; null/không đề cập không xóa slot cũ, xóa dùng clear_slots. Cộng/bớt món được code áp dụng đúng thao tác và kiểm tra số lượng; không tự lấy số loại bánh làm số chiếc mỗi loại.

Few-shot là ví dụ hướng dẫn trong prompt, không phải huấn luyện lại. Hiện có **159 ví dụ, version v44**; mỗi lượt chọn tối đa **2 ví dụ liên quan**, không đưa đáp án evaluation vào prompt. Ví dụ được sắp theo thứ tự field của schema HTTP; kiểm tra regex chỉ kiểm chứng/chuẩn hóa, Qwen vẫn là bộ hiểu ngôn ngữ chính. Code kiểm tra delta do model trích trước khi bổ sung thông tin ngữ cảnh đã xác minh; dữ liệu cũ không bị coi là model bịa thêm vào câu mới. Structured output (đầu ra có cấu trúc) giới hạn dạng JSON, còn ý nghĩa và căn cứ phải kiểm tra bằng code; xem [tài liệu Ollama](https://docs.ollama.com/capabilities/structured-outputs).

## Ngữ cảnh không dùng chung với đơn

| Vùng nhớ | Dùng để làm gì |
| --- | --- |
| `current_request` | Các câu hỏi và đối tượng của tin nhắn hiện tại. |
| `discussion_context` | Chủ đề đang tham khảo, dùng khi có tham chiếu rõ. |
| `product_choices` | Danh sách sản phẩm đang tham khảo, có thứ tự; tách khỏi ứng viên của yêu cầu đặt. |
| `order` / bản nháp | Món chính, extra_items, số lượng, liên hệ và REVIEW; không tự đổi khi hỏi bánh khác. |
| `request_memory` | Tối đa 8 yêu cầu/câu hỏi có thứ tự, điều kiện và trạng thái; không lưu liên hệ hoặc tự phát lại thao tác cũ. |

Lịch sử giới hạn theo CONTEXT_MAX_TURNS; nhu cầu có cấu trúc lưu riêng. Điều kiện chung đã cung cấp như ngân sách được nhớ khi phù hợp; điều kiện riêng từng câu hỏi không ghi đè lẫn nhau. Điều kiện tránh nguyên liệu được giữ qua lượt và hợp nhất khi khách bổ sung; hỏi “bánh có lạc không?” không tự trở thành dị ứng cá nhân. Yêu cầu xóa điều kiện rõ ràng có hiệu lực ngay với truy vấn hiện tại. Khi nguồn chưa có allergen, bot không khẳng định bánh an toàn hoặc đề xuất bỏ điều kiện dị ứng. Hội thoại và bản nháp từng khách được lưu riêng trong SQLite.

Hỏi Donut rộng có thể trả mọi kết quả đã đối chiếu; không bắt chọn trước mới báo giá/tình trạng. “Cả 2 bánh nhé” sau hỏi thông tin tiếp tục hỏi cả hai, không tự đặt hay quantity=2. “Bánh đó” với nhiều ứng viên vẫn cần làm rõ. Hỏi địa chỉ/giờ cửa hàng là chính sách, không tra bánh đang thảo luận.

## Lỗi câu ngắn “trà dưới 50k” — v42, 18/10/2026

Đã tái hiện trên Qwen thật: nguồn nhóm trả ba món trà 25.000đ nhưng prompt chọn “Tôi tìm trà hương dâu” hoặc “Shop có những loại trà nào?”, không có mẫu cận giá trà phù hợp. Model tự thêm dâu, thiếu cận trên hoặc dùng min_budget_vnd; guard trả budget_direction_mismatch/ungrounded_slot sau hai lần gọi. Đây là lỗ hổng độ phủ và chọn ví dụ của v41; kết quả fake trước đó không chứng minh model đã hiểu đúng câu ngắn này.

Sửa app/llm_client.py: khi câu tìm có ngân sách, không chọn mẫu tư vấn chỉ nhóm/vị mà thiếu cận giá. Chỉ đổi ví dụ gửi prompt, không gán intent/slot bằng regex. Thêm bốn mẫu trà dưới/trên/từ/khoảng; mẫu trà không quá giữ flavor=null khi không hỏi vị. Giữ Qwen, schema, kiểm tra nghiệp vụ, timeout, prewarm và tối đa hai ví dụ mỗi lượt.

Kết quả thực tế:
- Trước sửa, ba lượt trà trong bốn lượt kiểm tra lỗi, cà phê đạt. “Trà dưới 50k” phiên mới mất 11,67 giây/hai lần gọi rồi lỗi.
- Sau sửa, cả bốn lượt đạt, mỗi lượt một lần gọi; cùng câu phiên mới 5,52 giây, trả Trà sữa Thái xanh, Trà đào và Trà sữa, đều 25.000đ. Lượt trà đổi lại sau cà phê 5,25 giây; “có trà nào dưới 50k ko” 5,13 giây.
- Qwen thật thêm 6/6 lượt biên giá và 2/2 lượt đặt vani rồi hỏi trà đạt hành vi; hai câu vani/dâu cũ cũng trả đúng. Tổng 14 lượt chọn lọc đạt hành vi. Trong 8 lượt evaluator về biên/đơn, extraction_exact chỉ 4/8 do khác biểu diễn scope/mention; không công bố toàn bộ NLU đúng hay độ chính xác toàn model.
- Fake/RAM: 251/251 dev + 33/33 test, 155/155 ví dụ roundtrip schema đạt; cú pháp app hợp lệ. Thêm dev-241…251, giữ nguyên 240 lượt cũ và bộ test 33 lượt.

Không tạo file mới, không ghi database đang dùng hoặc đổi frontend/menu. Chưa click/render trình duyệt. Dừng chương trình cũ rồi chạy lại run_web.py để nạp code mới.

## Hỏi lựa chọn trước khi mua — bản v41, 18/10/2026

Thông báo “Chưa xử lý được lượt này” là thông báo chung khi bước model/validation thất bại, không đủ để kết luận từ ảnh rằng cửa hàng không có bánh. Câu đầu trong ảnh chưa tái hiện lỗi ở phiên mới trên v40, nhưng trace cho thấy bộ chọn mẫu ghép cả câu hủy bản nháp vào câu muốn tìm bánh. Đã tái hiện lỗi thật ở các cách nói liên quan: “không quá 35k”, “còn khoảng 40k”, “tối đa 40k thôi”. Model chép cận dưới từ mẫu khoảng hai số hoặc dùng sai điều kiện lấy biên; code từ chối nên bot báo lỗi. Thử thêm còn phát hiện tìm mới cùng nhóm giữ nhầm vị vani cũ.

Đã sửa trong hai module hiện có:
- app/llm_client.py: làm rõ muốn mua khi hỏi lựa chọn khác với chọn món để đặt; chọn ví dụ cùng nhóm và kiểu cận giá. budget_shapes chỉ lọc ví dụ hướng dẫn, không gán intent/số tiền thay Qwen. Câu hỏi đầy đủ nêu nhóm tìm mới dùng new; câu chỉ đổi vị/giá hoặc nói vẫn/giữ dùng refine. Hướng dẫn retry số sai không còn mặc định mọi lỗi số là số lượng bánh.
- app/order_nlu.py: refine với type=null được kế thừa khi nhóm thật khớp lời khách, áp dụng cả bánh nhỏ/kem/trà/cà phê. Nhóm sai hoặc new thiếu nhóm vẫn bị từ chối; guard không tự sửa proposal hay bản nháp.

Bổ sung 16 pattern vào data/nlu_few_shots.json: muốn mua nhưng đang tìm lựa chọn, không dấu/viết tắt, tên bánh kèm hỏi giá/còn hàng, chọn mua rõ, tham chiếu, phủ định mua, nhiều nhóm và các cách nói ngân sách. Mỗi lượt vẫn tối đa 2 ví dụ. Đây là few-shot, không fine-tune trọng số. Rút các default rỗng trong file mẫu; 151/151 ví dụ đọc qua Pydantic giữ nguyên ý nghĩa và trường bắt buộc khi đặt. File sau rút gọn khoảng 130 KB so với khoảng 180 KB nếu giữ default, giảm khoảng 28%; không thêm cache hội thoại hoặc thư viện.

Kết quả thực tế bản cuối:
- Qwen thật: 21/21 lượt của bốn nhóm shopping đạt hành vi, thêm 2/2 lượt tìm mới sau vị cũ đạt. Tổng 23 lượt, 24 lần gọi NLU, không lỗi cuối; một lượt tìm trà cần sửa JSON một lần.
- Trong 21 lượt chính, thời gian 4,26–13,14 giây, tổng 139,21 giây. Sáu câu nhóm bánh nhỏ/ngân sách khoảng 5,6–5,9 giây mỗi lượt; hai lượt kiểm tra vị cũ tổng 13,12 giây. Đợt thử trước khi sửa cận giá còn 3/21 lượt lỗi, không tính những lần đó là đạt.
- So khớp toàn bộ trường NLU với nhãn đạt 15/21 + 2/2, khác với điểm hành vi. Các khác biệt còn gồm alias trùng/khác hoa thường, biểu diễn action/reference, search_scope và cờ biên giá; chưa thể tuyên bố model hiểu mọi câu chính xác.
- Model giả: 240/240 dev + 33/33 test; 25 kiểm tra guard nhóm và 151 roundtrip schema đạt. 34 file Python đúng cú pháp; 8 module import được; API khởi động qua TestClient, GET /health, /, /api/catalog đều 200, 24 sản phẩm.
- Tracemalloc khi dựng prompt 15 lần: đỉnh cấp phát Python khoảng 784.410 xuống 666.727 byte. Đây không phải RAM toàn máy/Ollama; phần model vẫn giữ cấu hình cũ. Lần gọi đầu trước sửa từng mất 52,70 giây nhưng chưa tách thời gian nạp, nên không dùng nó để công bố phần trăm tăng tốc.

Thử lại sau khi Ctrl+C và chạy lại run_web.py:
```text
t muốn mua bánh nhỏ có giá dưới 50k, bạn có ko
có bánh nhỏ nào không quá 35k không
t còn khoảng 40k, có bánh nhỏ nào ko
Tôi muốn mua Bánh cuộn vani, giá bao nhiêu?
Mua giúp tôi 2 Bánh cuộn vani nhé
thêm 1 bánh đang đặt
```

Chỉ sửa chatbot; SQLite thử nằm trong RAM, không ghi đơn vào database đang dùng. Không thêm docs/tests/report hoặc sửa menu/frontend. Chưa kiểm tra click/render trình duyệt, chưa chạy toàn bộ 273 lượt bằng Qwen thật. Giữ model, schema nhánh an toàn, prewarm, keep-alive, context 4096 và deadline/retry hiện có.

## Sửa câu tư vấn đồng nghĩa và tốc độ — 18/10/2026

Nguyên nhân đã tái hiện nằm ở cả mẫu hướng dẫn và kiểm chứng bằng code: hai mẫu tìm bánh theo vị/ngân sách cho product_type=null, trái với guard; bộ chọn ví dụ còn ghép câu tìm theo vị với câu hỏi thuộc tính của một bánh có tên. Guard cũng đòi model nhắc lại cake ở câu lọc tiếp dù nhu cầu đã có đúng cake. Lỗi làm lượt bị từ chối và gọi sửa JSON thêm.

Đã đồng bộ mẫu, tách “có vị X dưới Y” khỏi “bánh A có vị gì”, giữ tối đa hai mẫu. Câu đầy đủ/rút gọn/không dấu vẫn do Qwen hiểu; so từ chỉ chọn ví dụ, không gán intent/slot thay model. Guard chấp nhận nhóm kế thừa đúng ở refine, vẫn từ chối nhóm sai hoặc truy vấn new thiếu nhóm. Câu hỏi không sửa bản nháp; đổi vị/ngân sách không chép giá trị chủ đề cũ.

Để giảm token sinh, HTTP JSON có hai nhánh anyOf hoàn chỉnh: nhánh thông tin chỉ bắt buộc intents/requests và loại order_request; nhánh nghiệp vụ bắt buộc sáu trường như trước. Python kiểm tra độc lập bằng explicit_order_wire_fields trước khi sang schema nội bộ. Bản thử chỉ bỏ field rỗng toàn cục từng làm câu vừa hỏi vừa đặt timeout 60 giây; đã sửa bằng nhánh nghiệp vụ đầy đủ và chạy lại thành công. Không nới validation đặt hàng để đổi lấy tốc độ. Tham khảo [ràng buộc JSON Schema của llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md).

Kết quả bản cuối v40, Qwen local qwen3.5:4b:
- Đúng chuỗi 9 lượt người dùng: 9/9 hành vi đạt; 9 lần NLU, không retry, tổng 48,08 giây, mỗi lượt 5,19–5,74 giây. Lặp câu/khoảng trắng cuối/đổi dâu-vani/câu rút gọn đều giữ bản nháp.
- Cùng câu vani đầy đủ ở hội thoại mới: v37 mất 14,67 giây/2 lần gọi/vẫn lỗi; v40 trả đúng trong 5,41 giây/1 lần gọi, token sinh giảm 76 xuống 55. Đây là phép đo trước/sau của câu đã tái hiện, không phải cam kết độ trễ chung.
- 7/7 smoke bổ sung đạt: chào, hỏi giá rồi đặt 2 bánh cuộn trà xanh, hỏi giá/vị bánh vani giữ món đang đặt, thêm một bánh đang đặt, tìm cà phê vị vani, câu dâu ở phiên mới và câu không dấu. Bảy lần NLU, tổng 37,64 giây; câu vừa hỏi vừa đặt 8,72 giây, một lần gọi.
- Câu cùng vị trả cùng bánh/giá từ repository hiện tại: SP0015 bánh cuộn vani và SP0017 Donut dâu, đều 35.000đ. Chỉ kiểm tra kết quả hiện có, không cache giá/tồn kho hay tự tạo sản phẩm.

Kiểm tra logic giả lập cuối: 217/217 dev + 33/33 test; 135/135 ví dụ chuyển qua wire rồi đọc lại giữ nguyên dữ liệu; 23 kiểm tra schema/an toàn đạt, gồm output đặt thiếu field, số lượng sai và model lỗi giữ nguyên bản nháp. Các kiểm tra controller/timeout trước đó cũng giữ REVIEW, không tạo đơn. 34 file Python hợp lệ cú pháp, 8 module import được; TestClient khởi động app và GET /health, /, /api/catalog đều 200, catalog 24 sản phẩm. Toàn bộ SQLite thử dùng RAM, không reset/chạm dữ liệu thật.

Không đổi model, options, context 4096, prewarm, keep-alive, timeout hoặc giới hạn retry. Không tạo file docs/tests/report, không sửa frontend/menu nhóm. Số đo tốc độ là khi model đã nạp; chưa chạy Qwen trên toàn bộ 250 lượt hoặc kiểm tra click/render trình duyệt. Chất lượng hiểu câu vẫn có giới hạn, không dùng kết quả fake để công bố độ chính xác model.

Web đang chạy không tự nạp lại module Python. Dừng Ctrl+C và chạy lại run_web.py ở đúng thư mục chatbot; chỉ F5 trình duyệt không tải schema/prompt mới.

## Sửa chính sách và phạm vi tìm kiếm — 17/10/2026

Lỗi đã tái hiện ở cả Qwen và code: câu “chính sách” bị model tự đổi thành câu hỏi giao hàng; ví dụ được chọn khiến “bánh” bị hiểu thành “bánh kem”; code giữ vị dâu khi khách tìm mới trong cùng nhóm bánh kem. Không sửa bằng cách xóa lịch sử.

Mỗi InformationRequest có search_scope:
- new: câu tư vấn độc lập; bỏ nhóm/vị/số người/dịp/size của chủ đề cũ, kể cả khi nhóm mới trùng nhóm trước.
- refine (mặc định): câu nối chỉ sửa vị/ngân sách hoặc dùng tham chiếu; giữ những điều kiện chưa đổi.
- Ngân sách và điều kiện tránh nguyên liệu được giữ nếu chưa được thay đổi/xóa rõ; cận giá mới thay cửa sổ giá cũ. Không thay bản nháp/REVIEW khi chỉ hỏi thông tin.
- Không kết hợp new với reference của sản phẩm cũ/mốc so giá; từng câu hỏi trong tin nhắn có phạm vi riêng.

Python vẫn giữ đầy đủ nhóm sản phẩm trong nhu cầu và bộ nhớ. Prompt chỉ nhận tên trường đã ghi nhận, không nhận lại giá trị nhóm cũ để tránh model chép nó vào kết quả mới; bộ chọn ví dụ vẫn dùng ngữ cảnh thật và tối đa hai mẫu. Guard kiểm tra model không tự đổi nhóm trong câu chỉ đổi vị/giá. Chính sách chung giữ nguyên câu khách nói; thiếu nguồn thì báo thiếu, không tự dựng chính sách.

Thử lại theo thứ tự:
- chính sách → thông báo chưa có tài liệu khi KNOWLEDGE_MODE=empty.
- có bánh nào có vị dâu trên 200k ko → hiện chưa có sản phẩm được ghi vị dâu và giá trên 200k trong nguồn.
- vị dâu dưới 200k → Donut sô cô la hương dâu, SP0017, 35.000đ.
- có bánh kem nào trên 300k ko → gợi ý đúng nhóm bánh kem, không giữ vị dâu.
- có bánh nào trên 300k ko → tìm toàn bộ nhóm bánh, không gồm đồ uống.

Kiểm tra trên bản v37: 205/205 dev + 33/33 test dùng model giả đạt; 135 ví dụ hợp lệ và dựng prompt không sửa conversation; 34 file Python hợp cú pháp, 7 module/entry point import được. FastAPI khởi động trong TestClient, /health, / và /api/catalog trả 200 (24 sản phẩm). JSON lỗi/timeout giữ bản nháp; TestClient có cảnh báo deprecation của httpx/Starlette nhưng kiểm tra vẫn đạt.

Qwen thật qwen3.5:4b: nguyên chuỗi 5 câu trên và 2 lượt kiểm tra bản nháp/cùng nhóm đạt 7/7; 8 lần NLU, tổng 85,28 giây. Một lượt cần sửa một lần, mất 43,56 giây; sáu lượt còn lại 5,84–7,88 giây. Chưa giải quyết mọi độ trễ hoặc mọi cách diễn đạt. Các lượt lỗi ở bản thử trước không được tính thành công. Đây là smoke có chọn lọc, không phải độ chính xác Qwen trên toàn bộ 238 lượt. Chưa click/render lại giao diện.

Thử bổ sung ba câu với bản nháp hai bánh Vani: “có bánh nào trên 300k ko” → “dưới 380k thôi” → “vani thì sao” đạt 3/3, mỗi câu một lần NLU, lần lượt 14,03 / 8,19 / 6,06 giây. Giữ đúng nhóm bánh và bản nháp; đổi giá không phải nhập lại vị/đối tượng cũ. Tổng hai đợt smoke cuối v37 là 10/10 hành vi, 11 lần NLU/113,56 giây, không suy thành độ chính xác toàn chatbot.

Mọi kiểm tra dùng SQLite RAM; không seed/reset database đang dùng, thay model/Ollama options, sửa frontend nhóm hoặc tạo file docs/tests/report.

## Dữ liệu, đặt bánh và quy tắc an toàn

Menu nhóm có tên, mã SP, nhóm, ảnh và giá niêm yết. **Không có size, số người ăn, tồn kho, allergen, topping, lead time hoặc chính sách chính thức.** Không dùng số 0 thay giá chưa biết hoặc khẳng định còn hàng từ kiến thức model.

Nguồn group_files không hỏi/bắt nhập size, topping, chữ hoặc ngày giờ nhận. Khách tự nêu thông tin chưa đối chiếu vẫn là mong muốn unverified (chưa xác minh). Thu thập món/số lượng và tên, số điện thoại liên hệ bình thường; không yêu cầu tiền tố DEMO/TEST.

**Đã tắt lựa chọn giao hàng/nhận tại cửa hàng và địa chỉ trong luồng đặt.** Không hỏi, không mặc định nhận tại cửa hàng, không cộng phí giao vào REVIEW. Schema/database giữ trường cũ để tương thích bản ghi đã lưu; chúng bị bỏ qua và ẩn trong luồng hiện tại. REVIEW cũ chưa gửi sẽ mất hiệu lực khi cấu hình đổi; snapshot yêu cầu đã lưu được giữ. Câu hỏi chính sách giao hàng vẫn trả theo nguồn chính sách.

REVIEW là bản tóm tắt cần khách đồng ý, không phải đơn đã xác nhận. Sửa thông tin làm mất hiệu lực REVIEW cũ; “đồng ý nhưng đổi…” phải REVIEW lại. Thành công chỉ nói **“Đã lưu yêu cầu chờ tư vấn.”** và thêm mã nếu tool thực sự trả mã.

SQLite chatbot lưu hội thoại, bản nháp, yêu cầu và ticket; tách khỏi database sản phẩm/backend nhóm. Idempotency là dùng khóa chống ghi cùng yêu cầu nhiều lần. Transaction là nhóm thao tác database cùng thành công hoặc cùng rollback; không tự reset database đang dùng để sửa lỗi.

Hand-off lưu ticket local khi cần nhân viên/dị ứng/khiếu nại/nghiệp vụ chưa hỗ trợ. Chỉ nói đã ghi nhận, chưa nói nhân viên bên ngoài nhận. Thông tin liên hệ cần thiết được lưu trong bản nháp/yêu cầu; lịch sử tin nhắn che thông tin đã nhận, prompt lượt sau không gửi lại giá trị liên hệ. Bộ đánh giá dùng liên hệ tổng hợp.

Empty mode chỉ lưu nhu cầu chờ tư vấn; mock/local_demo vẫn có adapter và công cụ demo đang hoạt động. Nguồn thật chỉ được tạo đơn khi adapter có đầy đủ khả năng; nguồn chỉ đọc không tự bật xác nhận. Không đổi yêu cầu/đơn mẫu thành đơn kinh doanh.

## Nhóm sản phẩm, hương vị và yêu cầu đang chờ

Đã đối chiếu 24 sản phẩm trong products.js với products.json của nhóm: ID, tên, giá và category khớp nhau. Adapter Python tiếp tục chỉ đọc JSON, không thực thi JavaScript hoặc ghi ra thư mục nhóm.

- 12 **bánh kem**: category=cake, product_type=cream_cake.
- 6 **bánh ngọt nhỏ**: category=mini, product_type=mini.
- 3 **trà**, 3 **cà phê**: cùng category=drink, tách tea/coffee theo tên nguồn.
- cake là mọi bánh; drink là mọi đồ uống. “Bánh cuộn trà xanh” là bánh nhỏ, không phải trà uống.

Hương vị chỉ lấy từ thực sự có trong tên nguồn: socola/choco, vani/vanilla, trà xanh/matcha, dâu, đào, chanh leo… **16 sản phẩm có vị ghi trong tên**, **8 sản phẩm chưa biết vị**. Response ghi “Vị ghi trong tên”, không coi đây là danh sách nguyên liệu/allergen. “Mây hồng” không suy thành dâu; “Mây xanh” không suy thành trà xanh. Không có kết quả thì báo không tìm thấy. Đổi từ bánh nhỏ sang trà/cà phê không giữ vị nhóm cũ nếu khách không nhắc lại.

Bộ nhớ tách câu hỏi hiện tại, chủ đề tham khảo và bản nháp. Yêu cầu đặt chưa rõ loại giữ ứng viên/số lượng riêng; hỏi giá bánh khác không thay ứng viên đó. request_memory giữ tối đa 8 mục theo thứ tự, gửi 4 tóm tắt cuối cho Qwen; không tăng giới hạn lịch sử. Câu hỏi đã trả lời có trạng thái riêng; chọn xong/hủy cập nhật yêu cầu cũ. Model đặt tên ở câu hỏi con cũng mở phạm vi tư vấn mới, tránh bộ lọc cũ nhiễm lượt tiếp theo.

Trong cùng một phiên, thử:
```text
đặt 2 bánh donut
bánh donut
Mousse Hawaii giá bn?
loại thứ hai giá bn?
loại dâu nhé
bánh đó giá bn?
```

Hai Donut khác nhau nên vẫn cần chọn loại, nhưng bot **giữ số lượng 2**. Hỏi Hawaii chỉ trả Hawaii; hỏi giá loại thứ hai chỉ trả giá Donut dâu, chưa tự đặt. “Loại dâu nhé” mới chọn vào bản nháp; “bánh đó” sau đó là Donut dâu. Chọn cả hai không tự hiểu hai chiếc mỗi loại.

Thử nhóm/vị:
```text
có bánh kem socola không
có bánh ngọt nhỏ vị trà xanh ko
bánh nhỏ vani thì sao
cho xem trà
cà phê thì sao
có trà vị dâu không
đào thì sao
```

Theo menu hiện tại: Choco ngọc trai; bánh cuộn trà xanh; bánh cuộn vani; 3 trà; 3 cà phê; không tìm thấy trà dâu; hỏi tiếp đào trả Trà đào. Sản phẩm/giá/trạng thái nguồn lấy từ repository.

## Kiểm tra đợt sửa hiện tại — 15/10/2026

- Model giả + SQLite RAM: **162/162 dev, 33/33 test** đạt, không model/source error. Đây là kiểm thử logic, không phải độ chính xác Qwen.
- **129/129** few-shot hợp lệ; **1.548** lần dựng prompt qua các trạng thái/nguồn, tối đa 2 ví dụ. Catalog/type/flavor: **283/283** kiểm tra đạt.
- API dùng model giả: **134** kiểm tra cùng **14** kiểm tra session cũ đạt; có quyền sở hữu yêu cầu, REVIEW không có giao/nhận và xác nhận lặp không lưu trùng. Memory/xử lý lỗi: **119/119** đạt. Các nhóm kiểm tra có thể chồng lấn, không cộng thành điểm chatbot.
- Qwen thật qwen3.5:4b đã thử **15 lượt/3 phiên RAM**: yêu cầu hai bánh cuộn, bỏ câu nhận tại cửa hàng, Donut nhắc lại/hỏi xen ngang/chọn vị, và nhóm bánh/trà/cà phê. Không lỗi model/nguồn; mỗi lượt một lần gọi, **3,77–7,05 giây/lượt** lúc đo.
- Sau đợt sửa cuối, chạy lại đúng chuỗi **6 lượt chuyển nhóm/vị**: bánh kem socola → bánh nhỏ trà xanh → “vani thì sao” → cà phê → trà dâu → “đào thì sao”. Đạt **6/6** hành vi, không lỗi nguồn/model; **5,03–11,23 giây/lượt**, câu cà phê cần một lần sửa JSON. Lần trước cùng chuỗi chỉ đạt **4/6** vì clear nhầm và mất nhóm sau không có kết quả. Đây là so sánh trên sáu câu đã chọn, không phải độ chính xác toàn chatbot.
- Bản cuối: cú pháp **35 file Python**, import **10 module**, **39** kiểm tra nhóm/vị/null/dị ứng và **19** kiểm tra bộ nhớ/lỗi không ghi database đều đạt. Nhóm tạm thời được giữ riêng, kể cả khi không có bánh khớp, và không xóa preferences/bản nháp khi chỉ hỏi giá.
- Bản cuối thử thêm **6/6 lượt Donut**: đặt hai → nhắc lại → hỏi Hawaii → chọn dâu → thêm một → hỏi giá bánh đó. Giữ số lượng hai khi chờ, sau chọn/thêm có đúng ba Donut dâu; không lỗi model/nguồn. **4,42–11,16 giây/lượt**, câu thêm một cần sửa JSON một lần.
- Kiểm tra khởi tạo API bản cuối: trang chủ, JS/CSS, health và catalog đều HTTP 200; tạo phiên HTTP 201, xem yêu cầu không có token HTTP 401. Dùng TestClient + SQLite RAM, chưa phải kiểm tra click/render trình duyệt.
- Lần thử riêng trước đó có **10 lượt** sau sửa chọn ví dụ, hành vi kiểm tra đạt; “thêm 1 bánh này” tăng 2 lên 3 và cần sửa JSON một lần (**11,47 giây**). Không cam kết mọi câu chỉ gọi model một lần.
- Trong quá trình sửa từng gặp JSON sai khi nhắc lại Donut và truy vấn bánh nhỏ vani không khớp. Đã sửa chọn ví dụ theo yêu cầu đang chờ, đặt message sau context, bổ sung nhãn nhóm/vị trong query rồi thử lại đúng các câu.

Giữ tối ưu: num_ctx=4096, num_predict=768, keep-alive 900 giây, prewarm mặc định bật, có thể tắt, tối đa 2 few-shot và một lần sửa JSON trong cùng deadline; không thêm lần gọi chỉ để diễn đạt. Few-shot là hướng dẫn, **không fine-tune** Qwen.

Thử nghiệm dùng RAM, không reset/seed database đang sử dụng, không tải/đổi model/thêm dependency. Không tạo docs/tests/report mới; không sửa static hoặc file ngoài chatbot. Chưa click/render GUI trong đợt này; chưa đánh giá Qwen toàn bộ **195 lượt (162 dev + 33 test)**. Menu nhóm vẫn thiếu tồn kho/allergen/chính sách chính thức; chỉ lưu yêu cầu chờ tư vấn.

## Bánh để thử và một chuỗi hội thoại

| Sản phẩm mẫu | ID | Giá niêm yết |
| --- | --- | --- |
| Bánh donut sô cô la | SP0016 | 35.000 đ |
| Bánh donut sô cô la hương dâu | SP0017 | 35.000 đ |
| Mousse Hawaii | SP0001 | 320.000 đ |
| Mousse Chanh leo | SP0024 | 350.000 đ |

Trong **cùng một phiên**, thử lần lượt:

1. `ban co banh donut ko`
2. `cả 2 bánh nhé`
3. `bánh thứ hai giá bn?`
4. `dat ca2loai, moi1c`
5. `Mousse Hawaii giá bao nhiêu?`
6. `thêm 2 bánh Mousse Hawaii nữa`
7. `bớt 1 bánh Mousse Hawaii`
8. `địa chỉ cửa hàng ở đâu, mở cửa mấy giờ?`
9. `tên Khách An, sđt 0900000001`
10. `đồng ý gửi yêu cầu`

Kết quả mong đợi: trả thông tin trước, giữ hai Donut khi hỏi Hawaii; thêm/bớt Hawaii còn 1 chiếc. Bản nháp có Donut thường 1, Donut dâu 1, Hawaii 1; không có lựa chọn giao/nhận; thông tin liên hệ đã nhập. Nguồn nhóm thiếu địa chỉ/giờ nên báo chưa đủ tài liệu. Chỉ lưu yêu cầu sau REVIEW hiện tại và đồng ý rõ, không xác nhận đơn kinh doanh. Xem kết quả model thực tế ở phần kiểm tra bên dưới.

## Thử RAG bằng chính sách mẫu

RAG là truy xuất tài liệu rồi dùng LLM chọn thông tin có nguồn; chunk là một điều khoản. Retriever keyword vẫn chạy, không cần tải embedding. Embedding là vector biểu diễn văn bản; chỉ dùng khi đã có model phù hợp và chỉ mục được xây đúng phiên bản.

```powershell
$env:KNOWLEDGE_MODE = 'sample'
.\.venv\Scripts\python.exe -B -X utf8 run_web.py
# Mở http://127.0.0.1:8000/ và hỏi “Chính sách giao hàng mẫu thế nào?”. Dừng bằng Ctrl+C.
Remove-Item Env:\KNOWLEDGE_MODE
```

sample chỉ dùng 5 điều khoản giả lập, luôn có nhãn mẫu và source_id/version. Empty không dùng mẫu như chính sách thật. Trích dẫn hợp lệ không chứng minh toàn bộ câu trả lời đúng; nội dung tài liệu là dữ liệu, không phải lệnh.

## Tư vấn ngân sách và so giá — 17/10/2026

Đợt v34 trước đó dùng intent-context-v34-budget-boundaries và 135 few-shot. Giữ Qwen qwen3.5:4b, sáu field JSON bắt buộc, tối đa hai ví dụ và một lần sửa trong deadline. Không fine-tune, thêm dependency hoặc gọi thêm model để xếp giá. System prompt group_files 4.907 ký tự, bản v30 là 4.829.

- “Tôi còn khoảng 300k” dùng trần 300.000 đồng, không tự dựng khoảng cộng/trừ. “30-40k” dùng chung đơn vị. Dưới/trên loại biên; không quá/tối đa/từ/ít nhất nhận biên.
- Gợi ý lọc nhóm, vị, ngân sách và điều kiện bắt buộc trước, rồi chọn tối đa 4 sản phẩm. Có ngân sách thì xếp giá tăng dần; không có bộ lọc/xếp giá thì lấy ngẫu nhiên trong tập hợp hợp lệ, vẫn giữ nhóm/vị khách yêu cầu.
- Rẻ/đắt nhất chỉ theo giá đã có trong nguồn, giữ đúng biến thể tạo nên giá đó; có thể trả nhiều sản phẩm đồng giá, tối đa 4. Giá chưa biết không phải 0.
- “Còn bánh nào rẻ/đắt hơn?” dùng một sản phẩm đã đối chiếu làm mốc, đọc lại giá từ repository. Ưu tiên cùng vị đã được ghi nhận; nếu chưa có thì gợi ý tối đa 4 lựa chọn khác và nói rõ. Có ít hơn thì trả số có, không bịa cho đủ.
- Giữ ngân sách tới khi khách đổi/bỏ. Không nới vị nêu rõ hoặc điều kiện tránh nguyên liệu. Mốc có nhiều biến thể giá/mơ hồ cần chọn rõ; giá chưa biết thì không so sánh.
- Hỏi/gợi ý không sửa draft. Danh sách mới trở thành lựa chọn có thứ tự mới; “loại thứ hai” trỏ đúng thẻ vừa trả.

Contract: InformationRequest.price_preference = none / lowest / highest / cheaper_than / more_expensive_than, chỉ dùng tra cứu, không phải slot đơn. Tên/reference của truy vấn tương đối là mốc; scope.comparison_product_ids giữ ID đã xác minh riêng với scope.filters tìm sản phẩm khác. Reference.cheaper cũ vẫn chỉ chọn trong danh sách đã đưa.

File chính: schemas.py định nghĩa contract; llm_client.py và nlu_few_shots.json hướng dẫn Qwen; order_nlu.py kiểm chứng nhóm/tiền/biên giá rồi cho model sửa; conversation.py giải mốc, lọc và xếp gợi ý. Regex chỉ kiểm chứng, không tự gán intent/ID/slot. Bộ kiểm chứng số giữ dấu gạch nối/thập phân; normalize_text chung không đổi.

Thử từng hội thoại mới:
- “Tôi còn khoảng 300k.”
- “Trong khoảng 350k đến 400k thì có các sản phẩm nào?”
- “Có bánh kem nào dưới 360k không?” → Hawaii 320k và Chanh leo 350k.
- “Có bánh kem nào không quá 360k?” → nhận cả bánh kem giá đúng 360k.
- “Bánh kem vị socola có loại rẻ nhất ko?”
- “Bánh kem Choco ngọc trai giá bao nhiêu?” → “Còn bánh nào đắt hơn ko?” → “Loại thứ hai giá bao nhiêu?”
- “Gợi ý trà dưới 30k”; “Có cà phê nào từ 40k trở lên?”; “Gợi ý bánh nhỏ vị vani dưới 40k.”

Kiểm tra: 185/185 dev + 33/33 test fake, 38/38 kiểm tra biên fake/RAM và 135 mẫu prompt hợp lệ. Qwen thật: bộ chính 14/14 lượt đạt sau sửa nhầm nhóm; bộ bổ sung 4/4 sau sửa biên ngân sách. Không tính lượt lỗi trước sửa thành đạt. Lượt chính khoảng 4,19–14,73 giây; trà dưới 30k còn cần sửa một lần, khoảng 12 giây. Không suy ra độ chính xác toàn model hoặc hứa trả tức thời. Chưa chạy toàn bộ 218 lượt bằng Qwen hoặc click/render trình duyệt. Test dùng SQLite RAM, không seed/reset database đang dùng, không tạo report/docs/tests mới.

Chạy lại kiểm tra logic (không cần model):
```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --engine fake --split dev --label budget_v34
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --engine fake --split test --label budget_v34
```

## Prompt, ngữ cảnh và tốc độ — 17/10/2026

Đợt tối ưu trước dùng prompt intent-context-v30-compact-scoped và 129 few-shot v30. Không fine-tune, đổi model, thêm dependency hay viết lại FSM/API.

- app/llm_client.py: system prompt nhóm quy tắc theo output, câu hỏi, đối tượng, ngữ cảnh, đặt hàng, tham chiếu, bộ lọc và xác nhận. Giữ sáu field JSON bắt buộc, Pydantic/grounding và tối đa một lần sửa trong deadline.
- Chọn ví dụ theo trạng thái được khai báo và yêu cầu đang chờ; tên catalog chỉ bị ẩn khi tính độ giống ví dụ, tin nhắn thật/alias gửi model giữ nguyên. Ví dụ thứ hai phải bổ sung từ khớp mới. Vẫn tối đa hai ví dụ; không dùng bước này để quyết định intent hoặc sửa đơn.
- Python giữ toàn bộ giá trị nhu cầu, lịch sử, draft và các ID. Bản chiếu gửi model chỉ nêu trường nhu cầu đã có, nhóm sản phẩm và tóm tắt yêu cầu có thứ tự; không lặp tên/giá trị filter cũ đã xử lý. Tên ứng viên đang chờ chọn vẫn được gửi để hiểu chọn vị. Đây là nén prompt, không xóa lịch sử/SQLite.
- data/nlu_few_shots.json: sửa các mẫu hỏi giá kèm đặt, liên hệ thuần, xem lại và đổi ngân sách; khai báo REVIEW cho mẫu xác nhận legacy. Bỏ bộ lọc trùng trong ba mẫu tư vấn, giữ số lượng và câu hỏi riêng. Ví dụ đổi ngân sách dùng đúng context chiếu hiện tại để không dạy chép lại socola/số người cũ.
- app/order_nlu.py: với yêu cầu đặt thuần có cụm rõ “bánh đang đặt”, kiểm tra model dùng tham chiếu order thay vì last của bánh đang xem. Sai thì từ chối và cho Qwen sửa tối đa một lần; không tự gán ID hoặc intent bằng regex. Câu hỏi thông tin xen lệnh đặt không bị áp kiểm tra toàn câu này.

Đo bằng Qwen thật qwen3.5:4b trên cùng 16 câu/5 phiên RAM, model đã nạp:
- Cả hai bản đạt kiểm tra hành vi cơ bản; bản cuối thêm kiểm tra liên kết câu hỏi với từng bánh, giá không lặp và không phát lại câu hỏi cũ khi nhập liên hệ.
- System prompt group_files: 5.768 → 4.829 ký tự. Prompt thực tế còn tùy context/ví dụ; không lấy ký tự thay cho token.
- Tổng 16 lượt: 116,82 → 88,30 giây, khoảng 24% trên bộ câu này; số lần gọi NLU 20 → 16. Bản cuối 16/16 hành vi đạt, mỗi lượt NLU một lần.
- Liên hệ sau hỏi giá/đặt: 14,34 → 6,16 giây; xem lại: 9,96 → 2,76; đồng ý kèm sửa số lượng: 12,26 → 4,82; xác nhận: 8,96 → 3,19. REVIEW đổi revision và chỉ lưu một yêu cầu chờ tư vấn.
- Không phải mọi câu nhanh hơn: câu tìm bánh dưới 300k đo 6,09 → 9,63 giây; model vẫn có thể sinh lặp filter dù prompt/ví dụ đã yêu cầu bỏ lặp. Một phép đo mỗi câu chưa chứng minh hiệu năng trong mọi tải máy hoặc độ chính xác toàn chatbot.
- Trong quá trình rút gọn đã loại các bản làm sai delta ngân sách, chép sở thích cũ hoặc lọc nhầm ví dụ theo FSM. Không tính các lượt lỗi thành lượt đạt.

Kiểm tra logic bản cuối: 162/162 dev + 33/33 test fake đạt, 129 ví dụ/268 kiểm tra wire, 1.548 lần dựng prompt, 34 cache/API guards, 90 kiểm tra bản chiếu bộ nhớ và 22 kiểm tra guard tham chiếu đơn đạt. Các nhóm có thể chồng lấn. Model giả không đo khả năng hiểu Qwen. Mọi kiểm tra dùng SQLite RAM, không ghi/reset database thật hoặc tạo report/docs/tests.

Thử thêm Qwen thật trên bản cuối: **13/13 lượt / 4 phiên RAM** đạt các hành vi kiểm tra: ba ý định trên một bánh; bảo quản theo “bánh này”; đặt không dấu/viết tắt; hỏi giá bánh khác giữ draft; thêm vào đúng bánh đang đặt; hủy; Donut chưa rõ loại/nhắc lại/chọn dâu/thêm; đặt hai loại mỗi loại một; hỏi giá kèm chính sách mẫu có nguồn. Lần thử trước đạt 11/13, phát hiện lỗi coi “bánh này” là tên và thêm nhầm bánh vừa hỏi giá. Đã sửa hai mẫu hiện có rồi chạy lại toàn bộ; các lượt lỗi không tính thành đạt. Một lượt chọn dâu vẫn cần sửa JSON, **14,14 giây**. 22 guard checks xác nhận hai output sai giữ nguyên cả conversation/draft, không lưu đơn; output sửa đúng tăng Vanilla từ 2 lên 3 dù đang xem Donut.

Giữ nguyên Qwen, context 4096, num_predict 768, keep-alive 900 giây, prewarm và các điều kiện xác nhận. Chưa đánh giá toàn bộ 195 lượt bằng Qwen hoặc click/render trình duyệt trong đợt này. Câu dài hoặc mơ hồ vẫn có thể cần sửa JSON/làm rõ; các câu hỏi giá không tự thay món trong bản nháp.

## Tối ưu theo cấu hình máy — 16/10/2026

Đợt này đo lại trên Intel Core i5-12450HX, RAM khả dụng hệ thống khoảng 11,7 GiB và NVIDIA RTX 2050 4 GB. Ollama báo chia model khoảng 51% CPU / 49% GPU; Qwen sinh khoảng 12–13 token/giây trong các lượt đo. Phần Python ngoài model thường khoảng 20–40 ms; phần lớn thời gian nằm ở sinh JSON. Đây là số đo tại thời điểm kiểm tra, không phải cam kết tốc độ mọi máy.

Thay code tại các file đang có, không thêm module/dependency:
- app/llm_client.py: yêu cầu JSON một dòng; giữ đủ sáu field bắt buộc và kiểm tra Pydantic/grounding. Schema tĩnh được dựng một lần rồi deepcopy cho từng nguồn; chỉ cache schema, không cache câu khách hoặc kết quả model.
- data/nlu_few_shots.json: giữ 129 ví dụ, version v26; sửa hai mẫu thêm/bớt theo delta (lượng thay đổi). Đang có hai bánh, khách thêm một thì model trích một; Python mới cộng thành ba, tránh phải gọi sửa vì model tự cộng trước.
- app/schemas.py và app/retrieval.py: RAG dùng output nội bộ RAGWireAnswer, chỉ chọn source_id và sentence_ids. Python kiểm tra nguồn/số câu, lấy đoạn nguyên văn và chuyển lại RAGAnswer/citations cũ, kèm version. Model không cần sinh lại cả đoạn chính sách. Kiểm tra nguồn/đoạn vẫn chưa chứng minh câu trả lời đúng mọi ngữ nghĩa.
- Không giảm num_ctx=4096 hoặc num_predict=768; giữ hai few-shot tối đa, sửa JSON tối đa một lần trong deadline chung, keep-alive 900 giây và prewarm mặc định. Thử giảm batch/giới hạn thread không có lợi đáng kể nên không giữ các thử nghiệm đó. Bản bỏ bớt field bắt buộc gây giảm ổn định ở câu hỏi kèm đặt đã bị loại; bản cuối giữ sáu field.

Đo trước/sau cùng câu hỏi trên Qwen thật qwen3.5:4b đã nạp, mỗi bản một lượt trong cùng chuỗi:
- “hello”: 4,72 → 2,91 giây; output 52 → 27 token.
- Sau đặt hai Donut và chọn dâu, “thêm 1 bánh này nữa”: 11,41 → 6,27 giây; từ hai lần gọi sửa còn một lần gọi; số lượng cuối đúng ba.
- Hỏi phí giao hàng mô phỏng: 14,05 → 7,20 giây; riêng output RAG 64 → 25 token, giữ nguồn sample-policy-001/version 1.0 và phí 25.000 đồng.
- Hỏi giờ mở cửa khi sample không có điều khoản đó: 32,03 → 6,01 giây. Bản trước chọn ba điều khoản liên quan nhưng không trả lời được giờ; bản cuối báo chưa đủ thông tin, không gán các thời hạn đặt/đổi trả thành giờ mở cửa.
- Cả 12 lượt bộ đo cuối không lỗi model/nguồn, mỗi lượt NLU một lần; hai câu chính sách thêm một bước RAG. Khoảng 2,91–7,20 giây/lượt. Các câu còn lại như tìm theo ngân sách có tốc độ gần bản trước; không suy ra phần trăm tăng tốc cho toàn chatbot.

Kiểm tra bản cuối:
- Qwen thật thêm 11/11 lượt nhiều ý định, phủ định đặt, hỏi giá trước khi đặt, REVIEW, sửa số lượng khi đồng ý, xác nhận lặp và empty giữ nhu cầu. Chỉ lưu một yêu cầu chờ tư vấn, không tạo đơn kinh doanh. Câu hỏi giá kèm đặt vẫn cần sửa JSON một lần, mất 19,98 giây: đây là giới hạn còn lại.
- Fake model: 162/162 dev + 33/33 test đạt, không lỗi model/nguồn. Đây là kiểm thử logic, không phải độ chính xác Qwen.
- 129/129 few-shot hợp lệ; 1.548/1.548 lần dựng prompt; 10/10 kiểm tra schema cache/cách ly bản sao; 268/268 kiểm tra wire schema. Các nhóm có thể chồng lấn.
- RAG 112/112; API/cú pháp/import 87/87 đạt. Có kiểm tra nguồn/số câu sai, JSON sai, timeout/model thiếu/truncated giữ draft, session, giới hạn tin nhắn và hợp đồng sản phẩm/nguồn.
- Khởi động uvicorn thật bằng run_web.py ở rule mode, cổng trống và SQLite RAM: trang chủ, JS, CSS, health và catalog HTTP 200; 24 sản phẩm, server sẵn sàng khoảng 1,48 giây. Model thật được kiểm tra qua service dùng bởi API ở các lượt trên. Chưa click/render GUI hoặc chạy hết 195 lượt bằng Qwen.

Mọi hội thoại kiểm tra dùng SQLite RAM. Không seed/reset/sửa database đang dùng, .env, frontend hoặc file ngoài chatbot; không tạo docs/tests/report. Có cảnh báo Starlette/httpx cũ trong TestClient nhưng không làm kiểm tra thất bại. Ctrl+C server cũ rồi chạy lại lệnh Windows ở đầu README để dùng mã mới; prewarm tự bật, không cần thêm cờ.

## Kết quả lịch sử trước tối ưu

Các kết quả ở mục này là trước lần tối ưu tốc độ 15/10/2026. Kiểm tra độc lập có thể chồng lấn; không cộng thành một điểm độ chính xác chatbot. Kết quả tối ưu mới ở mục tiếp theo:

| Nhóm kiểm tra | Kết quả hiện tại |
| --- | --- |
| Logic dùng NLU giả + SQLite RAM | Dev **86/86**, test riêng **33/33** đạt; không đo khả năng hiểu Qwen. |
| HTTP/API dùng model giả | **26** kiểm tra mới và **20** kiểm tra khởi động đạt; không phải click trình duyệt. |
| Client, phân tách ngữ cảnh, helper | **43** client, **25** scope và **243** helper đạt. |
| Retrieval 27 câu | Recall@3=1.0; MRR=0.97619; từ chối truy xuất ở câu không có đáp án=0.5 (3/6). Đây không phải độ đúng câu trả lời RAG. |

Qwen thật qua Ollama **qwen3.5:4b** đã chạy các lần smoke riêng, tất cả dùng SQLite RAM:
- **10/10 lượt nối tiếp** theo chuỗi trên: hai Donut, hỏi riêng Hawaii, thêm/bớt món, REVIEW và lưu một yêu cầu chờ tư vấn; **0 đơn đã xác nhận**.
- **6/6 tình huống độc lập**: nhiều câu hỏi kèm đặt, ngân sách, RAG chính sách mẫu có nguồn, empty mode, hai món với số lượng khác nhau, dị ứng cần nhân viên.
- Sau sửa bộ nhớ dị ứng, **3/3 lượt** kiểm tra lưu ràng buộc, giữ ràng buộc khi tư vấn tiếp và hỏi thành phần không bị coi là dị ứng cá nhân đạt.
- Sau bản sửa controller cuối, **2/2 lượt đúng ảnh lỗi**: ban co banh donut ko → cả 2 bánh nhé; trả thông tin cả hai Donut, state BROWSING và không chọn món vào draft.
- Sau sửa delta nhu cầu, **2/2 lượt empty**: socola/6 người/dưới 300k, rồi tăng lên 400k; giữ vị và số người, không tạo sản phẩm/bản nháp đặt.

Các lần này kiểm tra hành vi sau controller, không phải điểm extraction_exact. Thời gian quan sát khoảng **15–37 giây/lượt**; một lượt bớt món cần lần sửa JSON thứ hai. Quá trình chỉnh prompt trước đó từng gặp JSON sai, thiếu slot và timeout; không cộng những lần đó như thành công. Fake bổ sung **14** kiểm tra dị ứng/xóa điều kiện, **9** kiểm tra chọn tiếp/xóa và thay điều kiện/không sửa draft/từ chối delta thiếu căn cứ, **7** tóm tắt empty/diễn đạt, cùng kiểm tra cú pháp **35** file Python, import **12** module và schema **64** ví dụ đều đạt.

Bộ dev/test tổng **119 lượt** chưa được đánh giá toàn bộ bằng Qwen thật. Smoke test chỉ kiểm tra nhanh các tình huống được chọn; không bảo đảm hiểu mọi cách viết tắt. Chưa kiểm tra trực tiếp click/render GUI hoặc tạo đơn trên backend nhóm.

## Tối ưu tốc độ — 15/10/2026

Thay code cũ trong client/schema/context, không thêm module hoặc dependency. Giữ Qwen và model đang cài, API/FSM/repository cũ. Prompt ít lặp hơn; wire chỉ bắt buộc 6 field: intents/action/product_mentions/order_items/updates/requests. Pydantic bổ sung default nội bộ, không suy ra đồng ý hay thông tin khách. Mỗi order_item vẫn buộc có product_mention/reference/quantity để không bỏ tên hoặc số lượng riêng. Không cache NLU theo câu khách vì ngữ cảnh có thể khác.

Đã đo cùng chuỗi 5 câu (hello, hỏi Donut, cả hai, đặt cả hai mỗi loại 1/lấy tại tiệm, hỏi Hawaii). Cả trước và bản cuối đều đạt hành vi **5/5**. Bốn lượt sau câu chào đều dùng model đã nạp:
- Trước: **19,359 / 17,844 / 17,422 / 19,203 giây**.
- Sau: **4,094 / 4,828 / 7,000 / 5,422 giây**.
- Trung vị **18,52 → 5,13 giây**, giảm khoảng **72% trên 4 mẫu warm này**, không phải cam kết toàn chatbot.
- Chào trước **35,94 giây** gồm khoảng **13,14 giây nạp model**; sau **5,67 giây khi đã nạp**, hai số này không dùng tính phần trăm cải thiện.
- Prompt chào **8.660 → 4.793 ký tự**; output **132 → 54 token**. Ký tự không phải token.
- GET metadata localhost đo hai lần **2,063/2,047 giây**; IPv4 **0,015/~0 giây**. Config chuẩn hóa endpoint mặc định localhost:11434 sang 127.0.0.1:11434 để bỏ độ trễ local đã xác minh, không sửa .env riêng.
- Qwen thật bổ sung **3/3** ca cuối: nhiều câu hỏi + hai món số lượng 2/1 (**13,50s**), empty giữ vị/6 người/ngân sách (**7,34s**), RAG phí mẫu có source_id/version (**11,48s**).
- Trong lúc rút gọn từng gặp bỏ order_items, JSON thiếu target và nhận nhầm phí giao thành giá bánh. Đã giữ target bắt buộc, thay ví dụ chính sách và thêm một ví dụ A/B số lượng riêng; các lần lỗi không tính là đạt.

Kiểm tra ở lần tối ưu trước khi bổ sung mẫu: fake dev **86/86**, test **33/33**, **22 API/client**, **20 cấu hình/launcher**, **37 DOM giả**, 65 ví dụ hợp lệ. SQLite thử nghiệm ở RAM; không ghi/reset database đang dùng. Chưa kiểm tra click/render trình duyệt hoặc đánh giá toàn bộ 119 lượt bằng model thật. TestClient có cảnh báo httpx cũ, không cài thêm thư viện để xử lý ngoài phạm vi.

Client giữ một lần hiểu câu bình thường, sửa JSON tối đa một lần. NLU và các phần RAG cùng lượt dùng chung ngân sách timeout; lỗi vẫn giữ draft và không ghi đơn. Không thêm lần gọi chỉ để diễn đạt, không stream JSON NLU. Web hiển thị bubble đang xử lý ngay, sau 3 giây hiện thời gian đã chờ thực tế; không làm chậm bằng hiệu ứng gõ chữ.

Để tránh nạp lạnh khi chat sau một khoảng nghỉ, keep-alive mặc định **900 giây**, cấu hình OLLAMA_KEEP_ALIVE_SECONDS nhận 0–1800. Giữ model lâu cũng giữ RAM lâu; có thể đặt 300 nếu cần giải phóng sớm. Từ 16/10/2026, chạy run_web.py sẽ **tự nạp trước model ở nền** (prewarm), không cần thêm tham số. Việc nạp không chặn URL/server:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 run_web.py
```

Prewarm đưa model đã cài vào RAM/VRAM trước khi chat để giảm thời gian nạp ở lượt đầu; không huấn luyện model hoặc làm mọi lượt trả lời nhanh như nhau. Chờ dòng “Đã nạp trước model local.” nếu muốn thử sau khi nạp xong. Model vẫn chiếm bộ nhớ trong khoảng keep-alive; nếu nghỉ quá thời gian này có thể phải nạp lại.

Muốn tắt cho một lần chạy, dùng `--no-prewarm`. Cờ `--prewarm` cũ vẫn dùng được. Khi chạy rule mode hoặc OLLAMA_KEEP_ALIVE_SECONDS=0, không gửi yêu cầu nạp trước. Ollama phải đang chạy và model phải đã được cài; prewarm không tự khởi động Ollama hoặc tải model.

Không tải model khi thiếu. Sau khi sửa hãy Ctrl+C/chạy lại server và Ctrl+F5 trình duyệt để dùng code/asset mới. Muốn xem timing an toàn ở terminal:

```powershell
$env:CHAT_DEBUG = 'true'
.\.venv\Scripts\python.exe -B -X utf8 run_web.py
# Sau khi dừng:
Remove-Item Env:\CHAT_DEBUG
```

Log timing chỉ có số liệu, không có câu khách/prompt/output/token phiên. duration của Ollama là nanosecond: chia 1.000.000.000 để ra giây. ollama ps khi đo cho thấy **51% CPU / 49% GPU**, model khoảng 3,8 GB; RAM có lúc dùng **91%**, còn khoảng **0,99 GB**. Đây là trạng thái tại thời điểm đo; không ép GPU, đổi model, driver hay cấu hình Windows. Tốc độ vẫn phụ thuộc tải máy và độ phức tạp câu hỏi.

Nếu PowerShell báo không tìm thấy python.exe, kiểm tra đúng thư mục và .venv. Nếu Ollama lỗi, kiểm tra `ollama list`, dịch vụ/cổng và tên model. Nếu menu thiếu/sai JSON, bot báo nguồn chưa cấu hình/lỗi, không tự lấy menu demo thay thế. Dừng server cũ và chạy lại sau khi sửa Python; Ctrl+F5 khi tài nguyên giao diện bị cache.

## Phạm vi lần cải thiện ngữ cảnh trước đó

Chỉ sửa 10 file đã có trong chatbot: app/schemas.py, app/llm_client.py, app/nlu.py, app/order_nlu.py, app/conversation.py, data/nlu_few_shots.json, evaluation/intent_context_dev.json, scripts/evaluate_intent_context.py và hai README. Không tạo docs/tests/báo cáo mới, không sửa static, menu nhóm, database đang dùng hoặc frontend/backend bên ngoài.

Lỗi nằm ở cả contract NLU và điều phối ngữ cảnh: chọn nhiều món/chọn tiếp chưa nhất quán, và thông tin kế thừa bị kiểm như delta mới. Đã tách danh sách lựa chọn, truy vấn hiện tại và bản nháp; kiểm tra output hiện tại trước khi bổ sung context.

Đã bỏ các hàm hiểu câu cũ không còn nơi gọi (extract_nlu/extract_order_slots/choose_opening và helper gộp proposal cũ), cùng schema tương ứng. Giữ adapter/module còn được API/evaluator sử dụng; không xóa cả module chỉ vì không dùng trong cấu hình group_files hiện tại.


## Lần bổ sung mẫu trước đợt sửa nhóm/vị — 15/10/2026

Đã tăng từ 65 lên **112 few-shot** (47 mẫu mới) và từ 86 lên **136 lượt dev** (50 lượt mới). Giữ nguyên bộ test riêng 33 lượt. Ví dụ mới gồm ngân sách, bánh/đồ uống, hỏi nhiều bánh/nhiều ý định, không dấu/viết tắt, tham chiếu, thêm/bớt món, hủy, REVIEW, dị ứng và nhờ tư vấn. Đây là ví dụ hướng dẫn và dữ liệu đánh giá, **không huấn luyện lại trọng số Qwen**.

Các lỗi thực tế đã sửa:

- “Có bánh nào dưới 300k ko?” là tìm danh sách theo điều kiện, không bắt khách nêu tên một bánh.
- “Bánh trên 300k” dùng cận dưới; không mang trần giá cũ sang lượt mới. Khoảng giá phải cùng thỏa trên một biến thể; giá chưa biết không được coi là 0.
- product_type=cake gồm bánh kem/bánh nhỏ, loại đồ uống khỏi tư vấn bánh; drink dùng cho đồ uống. “Dưới/trên” không lấy giá bằng biên, “tối đa/ít nhất/từ…đến…” lấy biên.
- Câu hỏi thông tin giữ bản nháp; continuation có giá mới không lấy bộ lọc cũ gây khoảng giá trái nhau/exception.
- Chỉ chấp nhận first/second khi khách thực sự nêu số thứ tự; không tự chọn chiếc đầu tiên cho “bánh này” khi có nhiều lựa chọn.
- “Không đặt nữa, hủy yêu cầu” khác với “không hủy”. Thao tác chưa hỗ trợ trong giỏ nhiều món hỏi rõ và giữ các món cũ.

Bộ chọn ví dụ xét mức liên quan của từ và ngữ cảnh, vẫn **tối đa hai ví dụ mỗi lượt**. Tên hiện tại đã đối chiếu catalog không bị ghép với mẫu chỉ tham chiếu từ lịch sử; các mẫu cũ chưa có kind vẫn được sử dụng. Đây chỉ là chọn ví dụ cho prompt, không gán intent bằng từ khóa. Điều kiện tư vấn ưu tiên nằm riêng trong requests.filters để giảm JSON lặp. Giữ model, context 4096, keep-alive, prewarm, deadline chung, một lần sửa JSON tối đa và giao diện đang xử lý như lần tối ưu trước.

Thử theo chuỗi:
```text
có bánh nào dưới 300k ko
bánh trên 300k thì sao
bánh từ 200k đến 400k
đồ uống dưới 50k
```

Thử tham chiếu và giữ đơn:
```text
giá Donut
cả hai giá nha
đặt cả hai loại, mỗi loại 1c, lấy tại tiệm
Mousse Hawaii giá bao nhiêu?
```

Lệnh kiểm tra dùng dữ liệu thử riêng, không tạo thêm tests/docs hay báo cáo mặc định:
```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.prepare_intent_dataset
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split test --engine fake
```

Kết quả của lần bổ sung trước (không phải số lượt bộ hiện tại):

- Fake + SQLite RAM: **136/136 dev, 33/33 test**, bao gồm kiểm tra không chấp nhận lượt model/nguồn lỗi là thành công chỉ vì draft giữ nguyên.
- **112/112** ví dụ hợp lệ; **35 file Python** hợp lệ cú pháp; **14/14** kiểm tra API giả lập về session, quyền truy cập, input và context. Không click/render GUI trong lần này.
- Qwen local trên 20 lượt mở rộng trước bản chỉnh cuối: **19/20 lượt không lỗi model**, output NLU trùng toàn bộ nhãn **12/20**. Một lỗi tư vấn ít ngọt bị hiểu thành dị ứng đã được sửa ví dụ/grammar và thử lại; những khác biệt NLU còn có cách ghi reference, none/null, operation và gộp câu chính sách.
- Bản cuối chạy **11 lượt smoke**: 6 lượt ngân sách/loại/vị và 5 lượt chào → Donut → cả hai → đặt mỗi loại 1 → hỏi giá bánh khác. Các hành vi kiểm tra đạt, không lỗi model/nguồn; một lượt sửa JSON một lần. Đây không phải độ chính xác toàn chatbot.
- Chuỗi 5 lượt cuối mất **4,97 / 3,91 / 4,54 / 7,05 / 4,24 giây**, mỗi lượt gọi model một lần, giữ hai món Donut khi hỏi Hawaii. Trong chuỗi ngân sách có một lượt sửa JSON mất **15,67 giây**; câu ít ngọt nhiều điều kiện mất **11,95 giây**. Không cam kết mọi câu nhanh như câu chào.
- filters trên HTTP yêu cầu xét product_type/flavor, dùng null nếu chưa đề cập; null không xóa sở thích cũ. Ít ngọt là sở thích vị, không phải dị ứng. Nếu nguồn thiếu metadata thì báo thiếu, không suy ra bánh đáp ứng.

Mọi thử nghiệm lưu trong RAM; không seed/reset database đang dùng, tải model, tạo báo cáo hay thêm thư mục docs/tests. Chưa đánh giá Qwen toàn bộ **169 lượt**, chưa kiểm tra click/render trình duyệt hoặc backend nhóm.

Evaluator kiểm tra cả bộ lọc và ID biến thể, không chỉ ID sản phẩm. Chi tiết nhãn/lệnh thử Qwen: evaluation/README.md. Menu nhóm vẫn thiếu tồn kho, metadata hương vị/thành phần đầy đủ, số người ăn và chính sách; hiểu đúng câu không có nghĩa nguồn đã có thông tin để trả lời. Sửa trực tiếp một món sang món khác trong giỏ nhiều món còn cần bỏ/thêm riêng, chưa tự đổi.

## Thứ tự đọc code và nối backend sau

1. `app/schemas.py`: intent, slot, reference và validation.
2. `app/llm_client.py` cùng `data/nlu_few_shots.json`: HTTP, prompt và ví dụ.
3. `app/repositories/catalog.py`, `group_catalog.py`: interface và ánh xạ dữ liệu nhóm.
4. `app/knowledge_loader.py`, `retrieval.py`: chính sách và nguồn.
5. `app/conversation.py`: điều phối, bộ nhớ, tách hỏi/đặt.
6. `app/order_nlu.py`, `order_flow.py`, `order_service.py`: kiểm chứng, bản nháp và tool.
7. `app/storage.py`, `app/api.py`, `run_web.py`: lưu trữ, quyền phiên và khởi động web.

Khi backend sẵn sàng, thay adapter tại factory; giữ interface search_products/get_product/get_capabilities và tools kiểm tra/báo giá/gửi/tra cứu. Cần mapping ID SP/variant, nguồn giá/tồn kho chuẩn, quyền tạo đơn và idempotency xuyên hệ thống. Không ghi cùng đơn vào SQLite demo và backend thật; không tự chuyển dữ liệu mô phỏng thành đơn thật. Chạy lại hồi quy logic, session và giao dịch sau khi nối.
