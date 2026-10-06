# Chatbot bán bánh tiếng Việt — local demo

Python **3.12.10**, Qwen qua Ollama, SQLite và giao diện FastAPI đã có. Dự án chạy độc lập: **25 bánh mô phỏng, 35 biến thể, 3 topping, 13 chính sách**, hội thoại nhiều lượt, REVIEW, đơn DEMO chưa thanh toán và ticket local. Chưa có menu/chính sách/backend chính thức của nhóm. Giá/tồn kho/chính sách đọc SQLite; Qwen hiểu ngôn ngữ, code kiểm tra và tạo đơn. Giai đoạn 7 đánh giá tổng thể vẫn tạm hoãn.

## 1. Chạy Windows

Mở PowerShell tại root dự án. Môi trường ảo `.venv` chứa Python/thư viện riêng, không là mã nguồn. Dependency là thư viện chương trình sử dụng. Không cần kích hoạt nếu gọi đúng python.exe.

```powershell
# Chỉ tạo nếu chưa có .venv; giữ Python 3.12.10 đang dùng
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check

$env:DATA_SOURCE = 'local_demo'
$env:ORDER_PROVIDER = 'local_demo'
$env:DATABASE_PATH = 'runtime/chatbot.sqlite3'
$env:TIMEZONE = 'Asia/Ho_Chi_Minh'
$env:CHAT_MODE = 'ollama'
$env:KNOWLEDGE_MODE = 'local_demo'
$env:OLLAMA_BASE_URL = 'http://localhost:11434'
# Đúng tên đã có trên máy này; máy khác phải lấy tên từ ollama list
$env:OLLAMA_MODEL = 'qwen3.5:4b'

.\.venv\Scripts\python.exe -X utf8 -m scripts.database init
.\.venv\Scripts\python.exe -X utf8 -m scripts.database seed
.\.venv\Scripts\python.exe -X utf8 -m scripts.database check
ollama list
Invoke-RestMethod 'http://localhost:11434/api/tags'
.\.venv\Scripts\python.exe -X utf8 main.py
```

`init` nâng schema tại chỗ, backup trước khi nâng v1. `seed` thêm ID chưa có; chạy lại không nhân đôi hoặc ghi đè tồn kho đã trừ. `check` in số bản ghi, khóa ngoại và tính toàn vẹn, không in liên hệ. SQLite không cần dịch vụ database riêng. Path tương đối tính từ root bằng pathlib, path có dấu/khoảng trắng đặt trong dấu nháy.

Ollama chưa chạy: mở ứng dụng Ollama hoặc chạy `ollama serve` ở cửa sổ khác; không chạy lần nữa nếu endpoint đã hoạt động. Project không tải model. Tên model cấu hình sai báo model_not_found, không đổi sang tên khác. Để OLLAMA_MODEL rỗng chỉ chọn Qwen local đã cài. `.env.example` là mẫu; chương trình **chưa tự nạp `.env`**.

VS Code: Ctrl+Shift+P → **Python: Select Interpreter** → chọn `.venv\Scripts\python.exe`. Interpreter là chương trình thực thi Python. Có thể chạy `.\.venv\Scripts\Activate.ps1`; nếu bị chặn, dùng lệnh đầy đủ trên, không thay chính sách PowerShell toàn máy.

## 2. Giao diện hiện có

Trong PowerShell đã đặt cấu hình trên:

```powershell
.\.venv\Scripts\python.exe -X utf8 run_web.py
```

Mở http://127.0.0.1:8000/. Server cũ giữ cổng thì dừng cửa sổ đó bằng Ctrl+C rồi chạy lại; hoặc thêm `--port 8001`. Launcher bật Ollama trước import, một worker, cùng origin. UI có loading/error, thẻ bánh, nguồn, REVIEW và Hội thoại mới. Reload cần phiên/token mới; SQLite vẫn giữ record.

API: GET `/health`, POST `/api/conversations`, POST `/api/chat`, GET `/api/order-requests/{id}`. Chat/get record cần `Authorization: Bearer SESSION_TOKEN` của đúng phiên. Không coi ID là xác thực, không đưa token vào URL/log. Swagger local ở `/docs`. Health không bảo đảm model/nguồn đã sẵn sàng.

Nếu trang hiện “Failed to fetch” hoặc “Không kết nối được API”, hãy mở http://127.0.0.1:8000/health. Nếu không truy cập được, server web chưa chạy hoặc đã dừng; chạy run_web.py và giữ terminal mở, sau đó Ctrl+F5 và bấm Hội thoại mới. Chạy main.py chỉ mở chatbot terminal, không khởi động API. Nếu /health hoạt động nhưng tạo phiên lỗi, kiểm tra thông báo HTTP/server trong runtime/web_demo_stderr.log (khi chạy nền) hoặc cửa sổ đang chạy server; không reset database để chữa lỗi kết nối.

## 3. Bánh mẫu và câu thử

| Bánh | ID | Size | Giá mỗi bánh | Trường hợp |
| --- | --- | --- | --- | --- |
| Bánh kem socola | demo-001 | 16 / 20 cm | 250.000 / 350.000 đ | 6 / 10 người, lead time 12 giờ |
| Bánh kem dâu | demo-002 | 16 / 20 cm | 280.000 / 380.000 đ | Kẹo cốm, dâu tươi |
| Bánh kem vani | demo-003 | 16 / 20 cm | 220.000 / 320.000 đ | Chỉ kẹo cốm |
| Bánh kem trà xanh | demo-004 | 16 / 20 cm | 300.000 / 400.000 đ | Hết hàng |
| Bánh kem caramel | demo-008 | 16 / 20 cm | 280.000 / 380.000 đ | Tồn kho/allergen chưa rõ |
| Brownie socola | demo-012 | hộp 4 chiếc | 45.000 đ | Không viết chữ |
| Bánh mì sourdough | demo-017 | ổ 400 g | 80.000 đ | Lead time 18 giờ |

Đủ 25 bánh tại [seed](data/local_demo_seed.json). Phụ phí topping **mỗi bánh**: kẹo cốm 10.000, dâu tươi 15.000, hạnh nhân lát 20.000 đ; chỉ khi bánh hỗ trợ. Nhận cửa hàng miễn phí; giao địa chỉ `DEMO Nội thành ...` 25.000, `DEMO Ngoại thành ...` 40.000 đ **mỗi đơn**; nơi khác cần xác minh. Tất cả mô phỏng.

Câu thử: “socola dưới 300k”, “giá và size bánh socola”, “chiếc thứ hai giá bao nhiêu”, “loại rẻ hơn”, “topping bánh vani”, “giờ mở cửa”, “phí giao nội thành”, “bánh này có allergen gì”. not_listed không chứng minh an toàn với dị ứng. Nhắc dị ứng chuyển ticket local thận trọng.

Ví dụ tư vấn, kết quả mong đợi (chưa đánh giá mọi cách diễn đạt):

```text
Bạn: Mình cần bánh socola cho 6 người dưới 300k.
Bot: [Nguồn: local_demo, MÔ PHỎNG] Bánh kem socola 16 cm, 250.000 đ...
Bạn: Tăng ngân sách lên 400k.
Bot: Giữ vị/số người; cập nhật ngân sách và tra biến thể phù hợp.
Bạn: Giờ mở cửa của cửa hàng?
Bot: Chính sách mô phỏng 08:00–20:00, nguồn demo-policy-001, demo-1.
```

Ví dụ đặt bánh, đã chạy Qwen thật trong smoke:

```text
Bạn: Mình muốn đặt hai bánh socola size 16 cm, không topping, ghi chữ 'Chúc vui', nhận tại cửa hàng 2099-01-04 10:00, tên DEMO Khách A, sđt TEST-0001.
Bot: REVIEW đơn DEMO: 2 × 250.000 = 500.000 đ; chưa tạo đơn.
Bạn: Đồng ý nhưng đổi sang size 20 cm.
Bot: REVIEW mới: 2 × 350.000 = 700.000 đ; cần xác nhận lại.
Bạn: Xác nhận
Bot: Đơn DEMO, mã DEMO-..., unpaid; lưu và trừ 2 đơn vị tồn kho.
Bạn: Xác nhận
Bot: Trả đơn cũ; không tạo/trừ kho thêm.
```

Model có thể trích thiếu; trả lời câu hỏi bổ sung bằng câu tự nhiên. Thiếu slot/model lỗi/kiểm tra sai không tạo đơn. Ngày 2099 là ngày thử để không vướng lead time; giờ nhận 08:00 đến trước 20:00. “Chiều mai” hỏi thêm giờ, không tự đoán. Chỉ liên hệ **GIẢ**: tên/địa chỉ `DEMO ...`, điện thoại `TEST-...`. Một bản nháp hỗ trợ một sản phẩm, quantity nhiều; nhiều loại sẽ hỏi chọn, không tự bỏ loại thứ hai.

Đã sửa lỗi lẫn đối tượng truy vấn và bản nháp. Trong **cùng hội thoại**, thử “Tôi muốn đặt bánh socola” rồi “Bánh dâu giá bao nhiêu?”: chỉ giá dâu, draft socola không đổi. Hỏi “bánh đó” dùng ngữ cảnh khi rõ; có nhiều ứng viên thì hỏi lại. “Đổi sang bánh dâu” mới sửa draft và bỏ REVIEW cũ. Xem [giải thích code, A–F và vấn đáp](docs/fixes/context_product_scope.md). Server đang chạy cần restart để nhận code; sau restart tạo phiên/token mới một lần, rồi giữ cùng phiên khi thử hai câu.

## 4. Xem dữ liệu đã lưu

Trong CLI: `/draft`, `/orders`, `/order ID_BẢN_GHI`, `/new`, `/exit`. Bot in ID khi xác nhận; mã `DEMO-...` khác ID truy vấn. Sau restart: `/resume CONVERSATION_ID` rồi `/orders`. CLI local không là cơ chế đăng nhập web; `/order` chỉ lấy record thuộc phiên hiện tại. Không dùng CLI và API sửa đồng thời cùng phiên.

Lệnh quản lý `/...` không gọi model; **mọi tin nhắn nghiệp vụ Ollama đều qua Qwen**, kể cả xác nhận/hủy. Web giữ token phiên để gọi GET record. Ticket pending chỉ local, chưa nhân viên bên ngoài nhận.

## 5. Kiểm thử và reset

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_context_product_scope.py
.\.venv\Scripts\python.exe -X utf8 -m compileall -q app main.py scripts tests
# Model thật, database smoke riêng, không tải model
.\.venv\Scripts\python.exe -X utf8 -m scripts.check_local_demo
.\.venv\Scripts\python.exe -X utf8 -m scripts.check_context_scope
```

pytest dùng fake model, DB riêng, chặn mạng Ollama; suite hiện tại **406 passed, 1 warning**. Smoke scope **4/4 đạt với Qwen thật trên code bàn giao sau D96** tại [báo cáo scope](evaluation/context_scope_after.json): đặt socola/hỏi giá dâu/bảo quản dâu/giá cả hai, draft socola giữ nguyên. Bộ đo đầy đủ code cuối xem [progress](docs/progress.md). Smoke rộng trước đó [báo cáo](evaluation/local_demo_smoke_report.json) có policyintent sai nên passed=false; [thử lại policy riêng](evaluation/context_scope_policy_followup.json) đạt. Giữ các lần lỗi; không coi đo NLU mới là đã chạy lại toàn bộ smoke RAG rộng. Giai đoạn 7 tổng thể vẫn hoãn.

Lần cải thiện intent/context có **74 lượt nhãn: dev 48/final 26**. Output mới chia từng request theo intent/tên/size và tách mục tiêu đơn. Hỏi bánh khác giữ draft; lệnh thêm không tự thay loại bánh. Prompt few-shot trừu tượng, không fine-tune/đổi model. Xem [bài học code và vấn đáp](docs/learning/intent_context_improvement.md) và [quy trình đánh giá](evaluation/intent_context_protocol.md).

Đo Qwen thật trên code cuối: dev đúng toàn bộ intent **33/48 → 39/48**, F1 **0,7500 → 0,8842**; test cuối **20/26 intent, 13/15 scope sản phẩm, 21/26 tiêu chí hành vi**. Draft giữ nguyên đạt **29/29 dev, 17/17 test** ở những lượt có nhãn tương ứng. Lỗi validation/grounding dev tăng **2 → 7**, test cuối có **5 lỗi**; câu viết tắt/phủ định và thêm/xóa bánh chưa ổn định. Không gọi 406 test fake là 406 câu Qwen hiểu đúng. Xem [báo cáo so sánh](evaluation/intent_context_comparison_report.json) và [trace test cuối](evaluation/intent_context_final_test_report.json).

```powershell
# Test logic bằng output giả, không gọi model thật
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_intent_context_improvement.py tests/test_context_product_scope.py
# Đo Qwen thật; DB riêng, giữ mọi lượt lỗi trong report
.\.venv\Scripts\python.exe -X utf8 -m scripts.evaluate_intent_context --split dev --label after
.\.venv\Scripts\python.exe -X utf8 -m scripts.evaluate_intent_context --split test --label final
.\.venv\Scripts\python.exe -X utf8 -m scripts.compare_intent_context
```

Chỉ `--split dev` dùng điều chỉnh; không đưa nhãn final vào prompt. Đo serial, có thể lâu; `completed=true` nghĩa đã đo hết, không nghĩa tất cả đúng. Chạy lại lưu `previous_runs`. Baseline lịch sử đã lưu, không chạy `--label before` trên code mới để gọi là kết quả trước sửa. Reports NLU không đo RAG accuracy hoặc UI click/render.

Test tự tạo thư mục riêng `.pytest_tmp/run-...` trong project, bỏ qua Git. Nếu trước đây gặp `PermissionError: [WinError 5]` trong `_pytest/tmpdir.py` tại AppData/Temp, bản sửa này tránh dùng nhánh thư mục đó cho `tmp_path`; chạy lại cùng lệnh, không cần Administrator hoặc reset database. Xem [giải thích lỗi quyền và kiểm tra thực tế](docs/fixes/pytest_temp_permissions.md). Nếu tự truyền `--basetemp`, chỉ chọn thư mục riêng cho test vì pytest có thể xóa nội dung thư mục đó trước khi chạy.

Reset **xóa hội thoại/đơn/ticket và khôi phục seed** trong đúng DB demo đã xác minh thuộc runtime, backup trước; dừng server/CLI và chỉ dùng khi muốn xóa:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.database reset --database 'runtime/chatbot.sqlite3' --confirm
```

Không cờ thì từ chối; không xóa file/path tùy ý. Test không reset DB đang dùng. Muốn DB khác: đặt DATABASE_PATH rồi init/seed. Thiếu nguồn: DATA_SOURCE=empty, KNOWLEDGE_MODE=empty; mock/sample là fixture bài học cũ. CHAT_MODE=rule chỉ offline chủ động, không là model đã huấn luyện; AI lỗi **không tự chuyển rule**.

## 6. Đọc và tích hợp

[bài học local](docs/learning/local_chatbot_completion.md) → [config](app/config.py) → [schemas](app/schemas.py) → [repository](app/repositories/local_catalog.py) → [conversation](app/conversation.py) → [FSM](app/order_flow.py) → [tools](app/order_service.py) → [storage](app/storage.py) → [API](app/api.py). stage_01–06 là lịch sử.

[contracts](docs/contracts.md) là hợp đồng module hiện tại; [data_integration](docs/data_integration.md) hướng dẫn backend sau. Không tự chuyển đơn DEMO thành thật. Chưa multi-item, embedding, production login, thanh toán/giao thật, deploy hoặc đánh giá chất lượng rộng. Không thêm thư viện AI nặng.
