# Giai đoạn 6 — API và giao diện chat local

Ngày thực hiện: 03/10/2026. Python 3.12.10, Windows/PowerShell, .venv hiện có.
Code và API đã kiểm thử; **giao diện chưa được thao tác trong trình duyệt**
vì công cụ không có browser kết nối. Không tải model hoặc deploy.

## 1. Mục tiêu và chức năng đã hoàn thành

**Backend** là phần nhận yêu cầu và xử lý trên máy chủ. **Frontend** là phần
hiển thị, nhận thao tác trong trình duyệt. FastAPI giúp viết backend Python;
HTML mô tả nội dung, CSS định dạng, JavaScript điều khiển frontend.
Giai đoạn này thêm hai phần đó vào các chức năng cũ, không viết lại chatbot.

- GET /health, POST /api/conversations, POST /api/chat, GET /api/order-requests/{id}.
- Tạo phiên riêng bằng token ngẫu nhiên, kiểm tra quyền chat/đọc bản ghi.
- Pydantic kiểm tra request (yêu cầu) và response (phản hồi), giới hạn tin nhắn.
- Chat, trạng thái đang xử lý/lỗi, thẻ sản phẩm/nguồn tài liệu, nhãn dữ liệu.
- Bảng REVIEW trước khi gửi; empty chỉ lưu yêu cầu, mock đủ điều kiện mới đơn DEMO.
- Hội thoại mới không dùng lại lịch sử/nhu cầu của phiên trước.
- Nguồn/model lỗi không tạo sản phẩm hoặc đơn thành công giả.
- Bổ sung sau nghiệm thu ban đầu: mặc định AI, Qwen trích nhiều trường đặt
  bánh trong câu tự nhiên; code kiểm tra trước cập nhật.

Chưa có menu/chính sách/database sản phẩm thật. data/ là folder fixture (dữ
liệu mẫu cho học/test), không phải database. SQLite hiện chỉ lưu chatbot.

## 2. File tạo/sửa và trách nhiệm

| File | Vai trò |
| --- | --- |
| app/api.py — mới | Schema web, factory, token/owner/lock, HTTP routes, chuyển kết quả controller thành JSON; phục vụ UI. |
| static/index.html — mới | Khung chat, thông báo nguồn, hướng dẫn input, nút hội thoại mới. |
| static/style.css — mới | Màu/kích thước/bố cục màn hình lớn và nhỏ, trạng thái focus/disabled. |
| static/chat.js — mới | fetch API, token RAM, hiển thị văn bản/thẻ/nguồn/REVIEW/bản ghi. |
| tests/test_api.py — mới | 31 test mới khi tính parametrization: hai mode, owner, lỗi, validation, REVIEW và concurrency. |
| app/storage.py — sửa | Thêm load_order_request lọc theo ID **và** conversation_id; giữ schema SQLite v1. |
| app/chatbot.py — sửa | Sửa docstring create_state cho đúng việc controller đã lưu state; không đổi thuật toán. |
| requirements.txt — sửa | Thêm FastAPI/Starlette/Uvicorn, giữ Pydantic/tzdata. |
| requirements-dev.txt — sửa | Thêm HTTPX dùng TestClient, giữ pytest. |
| .env.example — sửa | Ghi rõ API/terminal cùng dùng biến DB; README hướng dẫn chọn file web riêng. |
| run_web.py — bổ sung | Launcher Python luôn bật Ollama trước import app, giữ cấu hình nguồn/model/DB hiện có. |
| app/order_nlu.py — bổ sung | Kiểm tra căn cứ câu gốc của slot Qwen; đề xuất không phải sản phẩm đã xác minh. |
| app/schemas.py, llm_client.py, conversation.py, order_flow.py — bổ sung | Schema OrderSlots, HTTP trích slot, routing/cập nhật an toàn và hỏi từng trường thiếu. |
| tests/test_order_nlu.py — bổ sung | 25 test natural slot/grounding/JSON/lỗi/REVIEW/contact/nguồn/đơn đã gửi. |
| README.md — sửa | Lệnh Windows chạy web/terminal, bảng thử và giới hạn kiểm tra. |
| docs/project_spec.md, progress.md, decisions.md, contracts.md, data_integration.md, next_steps.md — sửa | Phạm vi/trạng thái/kết quả/quyết định/hợp đồng và bước sau. |
| docs/learning/stage_06.md — mới | Bài học này. |

Không tạo module chatbot/adapter mới hoặc ghi đè AGENTS.md. runtime/*.sqlite3
và *.log sinh khi thử, bị .gitignore bỏ qua; không phải mã nguồn, cũng như .venv.

## 3. Luồng đầu vào → xử lý → đầu ra

```text
Trình duyệt mở / → nhận HTML → tải CSS + JavaScript cùng máy/cổng
  → POST /api/conversations {} → tạo conversation và token riêng
  → nhập câu → POST /api/chat {conversation_id, message} + Bearer header
  → Pydantic validate → token/owner → lock của phiên → nạp SQLite
  → handle_message → NLU/rule hoặc Qwen → catalog/RAG hoặc FSM/tool cũ
  → lưu history/needs/draft/request/demo/ticket như giai đoạn 5
  → make_chat_view → Pydantic response → JSON về trình duyệt
  → textContent + DOM → văn bản, sản phẩm, nguồn, trạng thái, REVIEW
```

**JSON** là định dạng văn bản biểu diễn object/list/string/number/bool/null.
HTTP mang JSON giữa frontend và backend; JSON không tự cấp quyền hoặc chứng
minh dữ liệu đúng. Giá null khác giá 0; không đổi null thành “miễn phí”.

Khi khách gửi “xác nhận”, API vẫn gọi handle_message. FSM kiểm tra REVIEW,
service kiểm tra lại nguồn/giá/khả dụng; API không tự chèn SQL tạo đơn.
GET bản ghi chỉ đọc submission của owner token để UI phân biệt hai loại.

## 4. Các hàm chính, tham số và kết quả

| Hàm | Input → output | Nơi gọi |
| --- | --- | --- |
| create_app(...) | Repo/knowledge, db_path, chế độ/client/timeout, session_seconds → FastAPI instance | app.api:app khi Uvicorn import; tests dùng DB tạm/repo truyền vào. |
| get_data_mode(repository) | Repo → chuỗi mode, unknown nếu đọc capability lỗi | health/start_conversation, không suy có sản phẩm. |
| authorize(authorization) | Header Bearer → session owner/lock/expiry; lỗi HTTP 401 | chat/get_order_request; closure bên trong factory. |
| health() | Không input → HealthView | GET /health, chỉ liveness (API đang đáp ứng), không kiểm tra model sinh. |
| start_conversation(body) | CreateConversationRequest {} → ConversationView, HTTP 201 | POST /api/conversations; server tạo ID/token. |
| chat(body, authorization) | ChatRequest + header → ChatView | POST /api/chat; gọi controller cũ. |
| make_chat_view(turn, knowledge_mode) | ConversationTurn + mode → dict contract web | chat; không trả history, prompt hoặc token. |
| get_order_request(id, authorization) | ID + header → OrderRequestView hoặc 404 | GET /api/order-requests/{id}; không đọc chéo owner. |
| load_order_request(connection, record_id, conversation_id) | SQLite connection/ID/owner → dict hoặc None | API get_order_request; SQL tham số trong storage. |
| API schema check_message/check_confirmation | Object Pydantic → self hợp lệ, hoặc lỗi validation | Pydantic khi nhận/serialize dữ liệu. |
| api(path, body) trong JS | Đường dẫn, object hoặc undefined → Promise JSON / throw Error | startConversation/send/showSavedRecord. |
| startConversation() | Không input → cập nhật session/UI sau fetch | Khi tải JS và bấm Hội thoại mới. |
| send(text) | Chuỗi khách → chat request, render kết quả | Submit form, Enter, quick buttons, nút REVIEW. |
| element(tag, text, className) | Thẻ/chữ/class → DOM node | Các hàm render; text dùng textContent. |
| showModes/showProducts/showSources/showReview | Kết quả API → cập nhật DOM | send; showModes còn dùng khi tạo phiên. |
| showSavedRecord(parent, data) | Parent DOM + ID response → GET bản ghi, thẻ kết quả | send sau phản hồi đã lưu. |
| setBusy(value)/showError(message) | bool/chuỗi → trạng thái controls/thông báo | Khi fetch bắt đầu/kết thúc hoặc lỗi. |

**Closure** là hàm giữ tham chiếu biến thuộc phạm vi bên ngoài. authorize và
routes trong create_app dùng sessions/catalog/db_path của đúng app instance.
Test tạo app khác không dùng chung registry token.

## 5. Code then chốt và kiến thức mới

### Python: cấu trúc và schema

Class APIModel kế thừa BaseModel của Pydantic, đặt strict=True và extra=forbid.
strict không biến số/bool thành chuỗi; extra từ chối field ngoài hợp đồng.
Field đặt giới hạn. Logic nghiệp vụ vẫn là hàm/dict, class ở đây dùng theo
yêu cầu validation của thư viện, không là framework agent.

```python
class ChatRequest(APIModel):
    conversation_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
```

model_validator còn từ chối message chỉ có khoảng trắng. Không strip/normalize
toàn tin nhắn trước controller, vì cần giữ nguyên chữ trên bánh. Schema web
ProductView mirror schema cũ; TypedDict cũ chỉ gợi ý kiểu, Pydantic thực sự
kiểm tra runtime (khi chương trình chạy).

### Backend: API contract, HTTP và cùng origin

**API contract** là thỏa thuận về đường dẫn, method, header, body, kiểu kết
quả và lỗi. HTTP GET dùng đọc; POST tạo/xử lý. Body là nội dung JSON; header
là thông tin kèm request, ở đây có Authorization và Content-Type.

201 tạo phiên; 200 phản hồi; 401 token không hợp lệ; 404 không thấy/không
thuộc owner; 422 sai schema; 503 storage/capacity; 500 response sai schema.
HTTP 200 không chứng minh truy vấn nguồn thành công: phải đọc catalog_status,
policy_status, errors/engine/message. UI không biến error thành “đã đặt”.

Origin gồm **giao thức + host + cổng**. /static và /api cùng origin; JS dùng
đường dẫn tương đối. http://localhost:8000 và http://127.0.0.1:8000 khác host;
hãy mở đúng URL đã chọn. Không mở index.html bằng file:// hoặc Live Server.

Decorator @application.post khai báo route; response_model kiểm tra và sinh
schema OpenAPI (mô tả API dùng cho /docs). API không đọc JSON menu trực tiếp.

### Backend: session và quyền truy cập

**Session** là phiên tương tác gắn với một khách; **token** là bí mật chứng
minh quyền truy cập phiên đó. **UUID** chỉ là ID định danh, không phải mật khẩu.

```python
token = secrets.token_urlsafe(32)
digest = hashlib.sha256(token.encode()).hexdigest()
# registry chỉ lưu digest → owner, expiry, lock
```

secrets lấy ngẫu nhiên phù hợp cho token; 32 byte có 256 bit entropy (mức độ
khó đoán). SHA-256 tạo hash, không cần lưu token nguyên văn trên server.
Client gửi Bearer header: ai có token có quyền của phiên; không chia sẻ token.
Mỗi token chỉ dùng một conversation. Body ID khác owner bị từ chối trước đọc DB.

GET record cũng có kiểm tra owner trong SQL:

```python
connection.execute(
    "SELECT payload FROM submissions WHERE id=? AND conversation_id=?",
    (record_id, conversation_id),
)
```

Placeholder ? truyền giá trị riêng, không nối câu SQL với input. Không có
record hoặc thuộc khách khác đều None/404. Schema SQLite không đổi.
API no-store yêu cầu HTTP không cache token/bản ghi; validation lỗi chỉ trả
loc/type, không echo nguyên input. UI token chỉ RAM tab, mất khi reload.

### Backend: đồng bộ, threadpool, SQLite và lock

**Event loop** điều phối các tác vụ async; gọi HTTP đồng bộ lâu ngay trong
async def sẽ chặn nó. **Threadpool** là nhóm luồng dùng chạy việc đồng bộ.
Route dùng def, FastAPI chuyển route vào threadpool theo
[tài liệu concurrency chính thức](https://fastapi.tiangolo.com/async/#path-operation-functions).
Client Ollama urllib cũ không cần viết lại async trong stage này.

SQLite connection được mở/dùng/đóng trong cùng route thread, không tạo một
connection toàn app. closing đảm bảo đóng khi có lỗi; with connection ở
controller quyết định commit/rollback như stage 5. Lock là khóa: một lượt
cùng phiên chạy xong trước khi lượt thứ hai sửa state. Khách khác có khóa
riêng; /health vẫn đáp ứng khi một controller đang chờ.

Registry và lock chỉ RAM của một process; chạy --workers 1. Không nói khóa
này bảo vệ nhiều server/worker hoặc CLI cùng ghi vào phiên web.

### Frontend: fetch, Promise và textContent

fetch gửi HTTP mà không tải lại trang. **Promise** biểu diễn kết quả sẽ có
trong tương lai; await chờ kết quả, try/catch/finally xử lý thành công/lỗi/
khôi phục nút gửi. Đây là async phía JavaScript, khác việc route Python def.

```javascript
const node = document.createElement("p");
node.textContent = source.quote;
parent.append(node);
```

**DOM** là cấu trúc các phần tử của trang. textContent gán văn bản; chuỗi
`<img ...>` chỉ hiện chữ, không tạo thẻ. Không dùng innerHTML cho văn bản
khách/model/nguồn. replaceChildren xóa node cũ mà không parse HTML động.
UI chặn gửi chồng khi busy; khóa backend vẫn cần vì khách có thể gọi API trực tiếp.

### AI/NLP và nghiệp vụ: giữ ranh giới

AI/NLP hiểu câu và lấy trích đoạn qua controller cũ; không tự tạo menu/ID/giá.
Rule là code theo quy tắc, không phải mô hình đã huấn luyện. Nguồn tài liệu
có ID hợp lệ không chứng minh mọi câu trả lời đúng nghĩa; không dùng RAG
sample để tính đơn thật. API chỉ trình bày source đã kiểm tra.

Nghiệp vụ: REVIEW là bản nháp cần xem lại; requires_confirmation không là
confirmed. Empty có request_id/confirmed=false/quote=null. Mock đủ nguồn có
demo_order_id/confirmed=true với nhãn DEMO; vẫn không thanh toán/giao thật.
Nguồn unavailable không có nút gửi. Sửa slot bỏ review; service recheck nguồn
và idempotency (chống xử lý trùng cùng lần gửi) như stage 5. Ticket pending
không nghĩa nhân viên đã nhận.

## 6. Lý do lựa chọn, giới hạn và phương án khác

- Hàm route nhỏ gọi logic cũ, factory truyền repo: dễ trình bày và thay nguồn.
- Plain JS cùng origin đủ bài tập; React/streaming/CORS không cần cho stage này.
- Token hash RAM và một worker đủ thử local; DB phiên bền nhưng token không bền.
  Có thể lưu session hash bền sau khi chốt resume/revocation/TTL/multi-worker.
- Connection từng lượt tránh lỗi SQLite khác thread, không cần async database.
  Có thể đổi client async sau khi đo tải thật; chưa làm vì không cần nghiệm thu.
- Có bảng REVIEW cấu trúc và labels rõ; chưa form ecommerce, giỏ nhiều dòng,
  tài khoản, dữ liệu thật hoặc đơn kinh doanh.
- Token/header là quyền phiên, chưa hệ thống login/HTTPS/rate limit production.
  Default loopback và không deploy. 2000 ký tự/8 giờ/200 phiên là giới hạn kỹ thuật.
- Lỗi browse tên cũ và greeting nhắc nhu cầu cũ còn từ stage trước; Hội thoại
  mới để thử câu độc lập. Chưa đánh giá NLP tổng thể hoặc độ ổn định Qwen.
- Browser automation hiện không có browser; cú pháp/HTTP đúng chưa chứng minh
  bố cục, Enter, thẻ, REVIEW, lỗi hoặc textContent chạy đúng trong DOM thực tế.

## 7. Chạy Windows và ví dụ thử

Tạo .venv nếu thiếu bằng py -3.12 -m venv .venv, chọn interpreter
`.venv\Scripts\python.exe` trong VS Code. Không ghi .venv vào Git. Sau đó:

```powershell
cd D:\Chatbot
.\.venv\Scripts\python.exe -m pip --disable-pip-version-check install -r requirements-dev.txt
$env:CATALOG_MODE = "empty"
$env:KNOWLEDGE_MODE = "empty"
$env:CHAT_MODE = "rule"
$env:CHATBOT_DB_PATH = "runtime/chatbot_web.sqlite3"
.\.venv\Scripts\python.exe -X utf8 -m uvicorn app.api:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Mở http://127.0.0.1:8000/. Không đóng terminal; Ctrl+C dừng. .env.example là
mẫu, code chưa tự nạp .env. Muốn đổi mode dừng, đặt biến rồi chạy lại server.
Mock: CATALOG_MODE=mock; tài liệu mẫu: KNOWLEDGE_MODE=sample.
Qwen: xem README mục 3, kiểm tra /api/tags, đặt CHAT_MODE=ollama/model đúng tên
đã cài; không tải model. Rule chạy được khi Ollama tắt.

| Thử | Mong đợi |
| --- | --- |
| Empty: `socola dưới 300k` | Ghi nhận nhu cầu, chưa có menu, products=[], không thẻ bịa. |
| Mock: câu trên | Thẻ mẫu socola 16 cm/250.000 đ; giá từ nguồn, không từ UI. |
| Mock: `giá và size bánh socola` | Giá/size variants, có nhãn mẫu. |
| Empty policy: `chính sách giao hàng` | Chưa có tài liệu, sources=[]. |
| Sample policy: câu trên | Trích điều khoản mock có source_id/version; không chính sách thật. |
| `Mình cần bánh socola cho 6 người dưới 300k.` rồi `Tăng ngân sách lên 400k.` | Giữ nhu cầu và cập nhật ngân sách riêng phiên. |
| `Hội thoại mới` / tab mới | Phiên riêng, không kế thừa needs của khách trước. |

Gửi từng dòng riêng (copy từng dòng vào ô chat, không cả khối):

```text
đặt bánh
nhu cầu: bánh học tập
size: 16 cm
số lượng: 2
topping: không
chữ: Chúc vui
ngày nhận: 2099-01-04 10:00
nhận: cửa hàng
tên: DEMO Khách A
sđt: TEST-0001
xem lại
```

Empty: thấy unverified/không báo giá và nút gửi yêu cầu chờ tư vấn. Chỉ sau
bấm gửi mới có request_id; chưa xác nhận đơn/nhân viên. Mock: thêm tin
`mã bánh: mock-001` **trước xem lại**, có nguồn mẫu cho size/chữ/stock.
REVIEW demo tổng 500.000 đ, đủ điều kiện mới nút xác nhận DEMO.
Sửa số lượng thành 3 trước gửi: REVIEW cũ mất, xem lại tổng demo 750.000 đ.
Thử nhập 11 để thấy nguồn mẫu báo không đủ khả dụng, không có nút gửi.

Để kiểm tra API thủ công ở PowerShell terminal khác, giữ token trong biến,
không in hoặc ghi file:

```powershell
$base = "http://127.0.0.1:8000"
$session = Invoke-RestMethod -Method Post -Uri "$base/api/conversations" -ContentType "application/json" -Body '{}'
$headers = @{ Authorization = "Bearer $($session.session_token)" }
$body = @{ conversation_id=$session.conversation_id; message="socola dưới 300k" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/api/chat" -Headers $headers -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

Tạo `$sessionB` bằng POST thứ hai, dùng header token B với ID A: phải 404.
UUID A làm token phải 401. GET record của A bằng B phải 404. Chỉ dùng liên hệ giả.

## 8. Kiểm thử đã chạy, kết quả thật và chưa kiểm tra

| Kiểm tra thực tế | Kết quả |
| --- | --- |
| Nền trước sửa | 231 test đạt trong 3,92 giây. Không AGENTS.md; đọc code và tracking. |
| Pytest cuối nghiệm thu ban đầu | **262 passed, 1 warning in 6.60s**, exit 0; 31 test API mới. Bổ sung sau đó: 287 test đạt, 25 test order NLU mới; xem progress. |
| API tests | TestClient/in-process HTTP, SQLite file tạm thật; không dùng socket hoặc model thật. |
| Hai server Uvicorn local | HTTP thật tại 8765 empty/empty/rule, 8766 mock/sample/rule; /health và HTML/CSS/JS đều 200. |
| HTTP empty full flow | 0 products/0 sources; REVIEW → waiting_consultation, confirmed=false; lại xác nhận cùng ID, token B GET record A 404. |
| HTTP mock full flow | 1 product/1 source cho các câu thử; REVIEW → demo_order, confirmed=true, tổng mẫu 500.000 đ; retry cùng ID, token B 404. |
| HTTP header | API no-store ở lần smoke sau sửa middleware. |
| Lỗi/validation/quyền | 401 thiếu/sai/expired/restart token, 404 owner, 422 input, 503 DB, 500 response sai; repo search/capability và knowledge lỗi không thành thành công. |
| Concurrency | Hai edit cùng phiên đều được lưu; controller chờ giả lập, /health vẫn trả trước khi controller được cho chạy tiếp. |
| Model timeout/not found/connection error | Monkeypatch kết quả client, API rule_fallback rõ; **không gọi Qwen thật**. Test JSON sai cũ vẫn đạt trong suite. |
| pip check | No broken requirements found; đã cài dependency nhỏ trong .venv. |
| Python compileall | Không lỗi; pytest cũng import/chạy code cuối. |
| JavaScript | Parser V8 chấp nhận chat.js; chỉ kiểm tra cú pháp, không thực thi DOM. |
| Browser | Mở iab báo Browser is not available; listBrowsers trả []; chưa thử UI trực tiếp. |

Lần test API đầu có 1 lỗi assertion vì test đọc needs.max_price_vnd thay vì
needs.filters.max_price_vnd. Sửa test theo schema hiện có, không đổi nghiệp
vụ để làm test đạt. Starlette 1.7.0 cảnh báo TestClient HTTPX deprecated,
đề nghị HTTPX2; vẫn dùng HTTPX stable đã pin, 1 warning không bị giấu.
Node không có trong PATH, không chạy được node --check; đã kiểm tra cú pháp
bằng V8 qua công cụ, không cài Node/browser mới.

Sau yêu cầu bổ sung: đã gọi Qwen thật qwen3.5:4b cho câu nhiều slot. Empty
thành công trong26,28s sau một lần http_error28,59s; phép thử tối thiểu 'OK'
HTTP200 trong21,80s giữa hai lần. Launcher Python + Uvicorn mock full-flow
thật engine=ollama, REVIEW tổng500.000đ, chỉ sau xác nhận mới đơn DEMO,
44,59s toàn luồng. Không coi vài lần thử là độ ổn định/độ chính xác tổng thể.
PowerShell chặn launcher .ps1 ở thử đầu: đã thay bằng run_web.py, không đổi
execution policy; launcher Python đã chạy thật và ghi đè CHAT_MODE=rule.

Chưa kiểm tra bố cục desktop/mobile, Enter/Shift+Enter, controls disabled/lỗi,
thẻ/nguồn/REVIEW, textContent chống HTML trong browser thực tế. Cần dùng bảng
ở mục 7 và thử chữ chứa `<b>DEMO</b>` trong empty REVIEW: phải thấy chữ nguyên
văn, không thẻ b. Đã thử Qwen slot theo ghi chú bổ sung, chưa đo hiệu năng
nhiều khách/worker, không đo lại retrieval/model stage4. Các kết quả đó vẫn là lịch sử.

## 9. Lỗi thường gặp và xử lý

| Lỗi | Cách xử lý |
| --- | --- |
| No module named fastapi/uvicorn/httpx | Cài requirements-dev bằng đúng python.exe .venv, kiểm tra interpreter VS Code. |
| Cổng 8000 bận | Dừng server của bạn hoặc dùng 8001 rồi mở đúng URL. Không tự tắt tiến trình không rõ chủ. |
| UI không gửi được | Kiểm tra terminal server, mở qua http://127.0.0.1:cổng, không file:///Live Server. |
| 401 sau sửa file/restart/reload | Hội thoại mới; token RAM cũ không được khôi phục bằng UUID. |
| 404 record | Kiểm tra token đúng phiên và ID response; không lấy token tab khác. |
| 422 | message chuỗi không rỗng, <=2000; body chỉ field cho phép. |
| 503 storage | Kiểm tra CHATBOT_DB_PATH/quyền/lock SQLite; không coi câu gửi lỗi là đã xác nhận. |
| Gửi xác nhận nhưng không có đơn | Kiểm tra REVIEW, unverified/stock/error; empty luôn request, mock thiếu nguồn cũng chờ tư vấn. |
| .env đổi mà mode không đổi | Đặt biến PowerShell trước chạy, .env chưa tự nạp; restart server. |
| Ollama timeout/model_not_found | Kiểm tra tags/tên/timeout như README, hoặc rule; không tải model tự động. |
| Xem tên bánh cũ trong câu chung/chào | Bấm Hội thoại mới để thử độc lập; lỗi NLU cũ còn trong next_steps. |

Lỗi mạng sau gửi có thể server đã lưu nhưng client chưa nhận. Retry cùng bản
REVIEW dùng idempotency cũ; UI không tự tạo ID đơn hoặc báo success. Nếu vừa
sửa trường, gửi “xem lại” để nhận bản tóm tắt hiện tại trước xác nhận.

## 10. Năm câu hỏi vấn đáp kèm gợi ý

1. **Frontend và backend chia trách nhiệm thế nào?** Frontend nhập/hiển thị;
   backend validate/quyền và gọi controller. UI không quyết định sản phẩm/giá.
2. **Vì sao biết conversation UUID chưa được đọc yêu cầu?** ID định danh,
   token ngẫu nhiên chứng minh quyền. So owner ở route và SQL; khách khác 404.
3. **Vì sao route def phù hợp client Ollama hiện tại?** Client HTTP đồng bộ;
   FastAPI chạy def trong threadpool, không chặn event loop. Connection SQLite
   mở/dùng/đóng trong thread đó, khóa cùng phiên để tránh lost update.
4. **requires_confirmation khác confirmed ra sao?** Cờ đầu mời khách xem/gửi
   REVIEW; confirmed chỉ record demo đủ điều kiện. Empty lưu chờ tư vấn false.
   Sửa slot cần review mới; service vẫn kiểm tra nguồn sau bấm gửi.
5. **textContent và Pydantic bảo đảm điều gì, không bảo đảm gì?** textContent
   tránh parse chữ thành HTML; Pydantic kiểm tra kiểu/schema. Không tự chứng
   minh câu trả lời đúng nghĩa, nguồn thật hoặc đã đáp ứng điều kiện nghiệp vụ.

## 11. Ba bài tập nhỏ tự sửa

1. Thêm quick button “giá và size bánh socola” bằng data-message, không thêm
   giá/tồn kho vào JS. Thử empty/mock, giải thích vì sao UI không là nguồn catalog.
2. Thêm nhãn màu cho catalog_status ở UI: unconfigured/no_results/error khác
   nhau. Dùng textContent và response status, không suy từ products.length.
3. Thêm test API gửi số lượng sai khi đang REVIEW: bản cũ bị bỏ, xác nhận
   không tạo record; sau sửa hợp lệ/xem lại mới cho gửi. Dùng SQLite tạm và
   contacts DEMO/TEST, không test trên dữ liệu runtime đang dùng.

## 12. Học trước bước tiếp theo và tích hợp widget

Học HTTP status/header/JSON, Pydantic, fetch/Promise/DOM, owner/token vs ID,
threadpool/lock/transaction và đọc kiểm thử. Phân biệt: Python là ngôn ngữ/
hàm/kiểu; backend là API/quyền/storage; AI/NLP là hiểu câu/RAG; nghiệp vụ là
nguồn xác minh/REVIEW/yêu cầu/demo, không để frontend hoặc LLM tự xác nhận.

**Widget** là khung chat nhỏ nhúng trong trang bán bánh. Khi website thật có
sẵn, có thể đưa phần chat-panel/CSS/JS vào trang hoặc phục vụ UI hiện tại
trong iframe cùng origin. JS giữ relative API URLs và tạo phiên riêng. Khi
API và website ở hai server, reverse proxy (máy trung gian chuyển đường dẫn
tới dịch vụ) có thể đưa /api và /static về cùng origin. Nếu khác origin cần
chốt CORS (quy tắc browser cho phép gọi chéo origin), auth và HTTPS trong
phạm vi riêng; không tự thêm CORS=* hoặc token chung cho mọi khách.

Không nối widget trực tiếp database sản phẩm hoặc SQLite chatbot. Khi có
nguồn thật, triển khai repository/tool adapter đúng contracts rồi inject
vào backend, cập nhật nhãn mode/test; frontend tiếp tục dùng response chuẩn.
Chưa deploy hoặc thực hiện bước tích hợp thật trong stage này.

### Bổ sung thực hành AI mặc định và câu đặt tự nhiên

User đã chọn Qwen hiểu thông tin đặt bánh tự nhiên; đây là bổ sung stage6,
không phải tự thực hiện stage7. CHAT_MODE mặc định ollama, timeout config60.
Mở web bằng `.\.venv\Scripts\python.exe -X utf8 run_web.py`; --port đổi cổng.
Nếu đang chạy server cũ: Ctrl+C, chạy lại, reload và Hội thoại mới. Không cần
gõ CHAT_MODE mỗi lần; launcher đặt AI trước import để bỏ rule còn sót.

Luồng mới: câu có thông tin đặt bánh → should_extract_order → select_model
→ extract_order_slots → Pydantic LLMOrderSlots → check_order_proposal →
apply_order_proposal → update_slot → câu hỏi trường còn thiếu → REVIEW/
submit cũ do code. Không gửi menu/contact cũ vào model; không có field
product_id/giá/confirmed trong schema. JSON sai sửa tối đa một lần.

**Grounding** (đối chiếu căn cứ) kiểm tra cụm/size/chữ/topping/date/contact
trong câu hiện tại và lượng có marker bánh/cái/số lượng; hỗ trợ số viết một
đến mười. Không copy slot cũ vào đề xuất mới. Null giữ giá trị cũ; nhiều bánh
chưa rõ liên kết, date 'mai', số người bị nhầm lượng hoặc giá trị tự bịa bị
từ chối/hỏi lại. Từng slot vẫn unverified đến lúc nguồn kiểm tra tại REVIEW.
Sai một field từ chối cả phần cập nhật AI của lượt, bỏ REVIEW cũ. Rule NLU
có thể đã ghi vài trường rõ trong câu bắt đầu; không nói toàn lượt chưa lưu.

| Hàm bổ sung | Tham số → trả về / nơi gọi |
| --- | --- |
| run_web.main | CLI --port → chạy Uvicorn, đặt env ollama trước import / entry script. |
| extract_order_slots | message,draft,base_url,model,timeout → data/error/attempts / conversation trước SQL transaction. |
| should_extract_order | message,draft,nlu → bool / controller chọn nhánh; lệnh thuần/field:value/handoff không AI. |
| contains_unsafe_contact | message → bool / chặn contact chưa nhãn giả, không model/không lưu raw. Không là detector PII đầy đủ. |
| check_order_proposal | message,nlu,LLMOrderSlots → mã lỗi hoặc None / apply. |
| apply_order_proposal | message,draft,nlu,proposal → draft mới,text,error / merge. |
| merge_order_extraction | handled,draft,message,nlu,extraction → handled mới,error / controller giữ FSM trước thêm slot AI. |
| business_command_text | message → chuỗi che quote sau ghi chữ / flow và gate, tránh chữ trên bánh kích hoạt handoff. |

Thử: “Mình muốn đặt hai bánh socola size 16 cm, không topping, ghi chữ 'Chúc
vui'.” Bot ghi trường rồi hỏi ngày nhận; nhập “Nhận tại cửa hàng lúc
2099-01-04 10:00, tên DEMO Khách A, sđt TEST-0001.” Sau đó xem lại/xác nhận.
Sửa “Tăng số lượng lên3 bánh” trước gửi phải bỏ REVIEW; sau demo đã confirmed
phải ticket, không sửa record. Empty vẫn request; mock đủ metadata mới DEMO.

Lựa chọn này dùng model để hiểu, code để ghi/kiểm tra/xác nhận; chưa diễn đạt
tự do toàn câu, chưa hiểu mọi phủ định/cách nói hoặc quantity lớn bằng chữ.
Lệnh “đặt bánh” thuần không có slot để trích nên engine=rule vẫn bình thường;
UI cho biết mode AI đang chọn và engine từng lượt riêng. Ollama lỗi có
rule_fallback; model có sẵn không bảo đảm mọi lần sinh thành công.

Vấn đáp thêm để giải thích bổ sung: vì sao default khác env override (env
được ưu tiên, launcher đặt lại); vì sao mention khác ID (nguồn xác minh);
vì sao chữ 'xác nhận' trên bánh không submit (chỉ lệnh riêng mới consent);
vì sao null không xóa slot (câu mới không nêu giá trị cũ); vì sao287 test
không là độ chính xác Qwen (đa số model giả lập, thử thật chỉ vài câu).

Bài tập thêm: mở rộng số lượng 'mười một' có kiểm tra căn cứ; thêm regression
model copy ngày/contact cũ; hiển thị lỗi order_nlu thân thiện trong UI bằng
textContent. Học thêm regex/JSON strict, copy-on-update, grounding và khác nhau
giữa đề xuất AI, dữ liệu repository và quyết định nghiệp vụ.

Trước giai đoạn 7: kiểm tra UI thực tế hai mode theo mục 7–8, suite đạt,
hiểu quyền/REVIEW/nguồn lỗi, đọc next_steps và chờ yêu cầu phạm vi tiếp theo.
