# Bài học giai đoạn 3: Qwen/Ollama và hội thoại có ngữ cảnh riêng

Thực hiện ngày 03/10/2026, Python 3.12.10 trong .venv. Stage_01 và stage_02
giữ nội dung lịch sử; README và các file theo dõi mô tả bản hiện tại.

## 1. Mục tiêu và chức năng đã hoàn thành

Chatbot terminal có hai **mode** (chế độ): rule theo quy tắc và ollama dùng
Qwen đã cài. **LLM** (large language model, mô hình ngôn ngữ lớn) hỗ trợ trích
thông tin câu hỏi và chọn lời mở đầu. Không huấn luyện model trong dự án này.
Rule vẫn là code theo quy tắc, không phải mô hình đã huấn luyện.

Mỗi **conversation** (cuộc hội thoại/phiên) có ID, lịch sử và nhu cầu riêng.
Mặc định giữ 6 lượt; mỗi lượt gồm câu khách và câu bot. Nhu cầu có cấu trúc
lưu riêng nên bỏ các lượt cũ không làm mất ngân sách/hương vị/số người.

**Repository** là thành phần cung cấp dữ liệu qua interface (hợp đồng gọi).
Nguồn empty vẫn chưa có menu; mock vẫn là 5 mẫu có nhãn. Model không tự xác
minh bánh có bán, giá, tồn kho hoặc chính sách; code dùng repository. Không
tạo đơn, database, API web, giao diện website hoặc RAG ở giai đoạn này.

| Nhóm kiến thức | Nội dung mới |
| --- | --- |
| Python | Dictionary/list lồng nhau, deepcopy, UUID, thư viện urllib/json, exception, Pydantic. |
| Backend | HTTP local, timeout/status, tách client và logic, phiên riêng, fallback có chẩn đoán. |
| AI/NLP | Prompt, trích intent/thực thể có cấu trúc, context, giới hạn hiểu của model. |
| Nghiệp vụ | ID/giá/tình trạng từ nguồn; nhu cầu khác thông tin cửa hàng; không tạo đơn. |

**NLU** là hiểu ngôn ngữ tự nhiên; **intent** là ý định (hỏi giá/size/tư vấn…);
**entity** là thông tin trích được (cụm bánh, ngân sách, vị, số người/số lượng).
**Mention** là cụm khách nhắc tới, chưa phải sản phẩm đã xác minh.

## 2. File đã tạo/sửa và trách nhiệm

| File | Vai trò/thay đổi |
| --- | --- |
| app/llm_client.py | Mới: HTTP local, chọn model có sẵn, trích JSON/sửa một lần, validate, chọn lời mở đầu. |
| app/conversation.py | Mới: tạo phiên, lịch sử/nhu cầu riêng, điều phối rule/LLM và xử lý fallback. |
| app/schemas.py | Thêm LLMNLU/LLMOpening và kiểu ChatMessage/Conversation/ConversationTurn; giữ Product/Variant cũ. |
| app/nlu.py | Thêm check_llm_proposal/merge_llm_nlu; đối chiếu câu hiện tại, giữ ID từ nguồn. |
| app/chatbot.py | respond nhận nlu tùy chọn; lỗi truy vấn cuối giữ nhu cầu cũ; bỏ câu thông báo riêng stage 2. |
| app/config.py | Thêm timeout và số lượt context, kiểm tra giới hạn; vẫn đọc biến môi trường. |
| main.py | Dùng conversation; chạy cả rule/ollama, reset phiên, in chẩn đoán. |
| tests/test_llm_client.py | Mới: HTTP/model giả lập, schema, sửa JSON, timeout, model thiếu, lời mở đầu sai. |
| tests/test_conversation.py | Mới: empty/mock, cập nhật nhu cầu, phiên riêng, giới hạn lịch sử, lỗi/fallback. |
| tests/test_chatbot.py | Cập nhật test CLI cho handle_message và mode ollama; giữ test nghiệp vụ cũ. |
| requirements.txt / requirements-dev.txt | Runtime thêm pydantic==2.11.9; dev vẫn kế thừa và pin pytest 8.4.2, chỉ cập nhật chú thích. |
| .env.example | Thêm hai biến mới, ghi model rỗng là khám phá model đã cài; không tự nạp .env. |
| README.md | Cách chạy rule/ollama, Windows/.venv/interpreter, test và giới hạn. |
| docs/project_spec.md | Phạm vi stage 3 và trạng thái nguồn/model/phần cứng. |
| docs/progress.md | Kết quả test giả lập và gọi thật riêng, phần chưa kiểm tra. |
| docs/decisions.md | Quyết định D27–D39, lý do đổi một số quyết định stage 2. |
| docs/contracts.md | Schema/HTTP/client/phiên, chữ ký hàm và quy tắc. |
| docs/data_integration.md | LLM không xác minh sản phẩm; adapter mới vẫn qua interface. |
| docs/next_steps.md | Điều kiện bước sau, việc còn tồn tại. |
| docs/learning/stage_02.md | Thêm ghi chú bài lịch sử, không viết lại bài cũ. |
| docs/learning/stage_03.md | Bài học này. |

Giữ các repository/data mẫu/text_utils và .gitignore đã có; không tạo adapter
JSON/database/API thật hoặc module rỗng. Không ghi đè AGENTS.md, không tải model.

## 3. Luồng đầu vào → xử lý → đầu ra

```text
main → tạo repository theo CATALOG_MODE + conversation mới
câu gốc + đúng phiên khách → handle_message
  → rule phân tích + kiểm tra nguồn
  → rule mode: dùng kết quả rule, không HTTP
  → ollama mode: tags chọn model đã cài (cache tên trong phiên)
      → chat: câu hiện tại + lịch sử riêng + nhu cầu → JSON
      → Pydantic → sai thì sửa 1 lần; lỗi thì fallback rule
      → kiểm tra nghĩa cơ bản → sai thì fallback rule có mã lỗi
      → hợp nhất NLU; ID chỉ từ tên/alias nguồn
  → respond: hỏi lại nếu mơ hồ, cập nhật nhu cầu nếu rõ
      → search_products(filters) → status và products từ repository
      → code tạo phản hồi có mode/nhãn mock
  → nếu NLU LLM được chấp nhận: chọn lời mở đầu an toàn
  → lưu cặp user/assistant vào phiên mới → cắt lịch sử cũ
  → trả response + conversation mới + chẩn đoán → main in
```

**Cache** ở đây chỉ là nhớ tên model đã chọn trong phiên; không phải Redis
hay cache dữ liệu cửa hàng. **Fallback** là đường xử lý dự phòng: lỗi LLM
dùng rule cho lượt đó, có thông báo; không đổi nguồn catalog thành mock.

Lỗi repository luôn là error, khác no_results hoặc unconfigured. Nếu truy
vấn cuối lỗi, không ghi đè nhu cầu và không thêm lời mở đầu thành công. Chính
sách thiếu vẫn nói thiếu; order_request chỉ ghi nhận ý định, không tạo đơn.

## 4. Hàm chính: tham số, giá trị trả về, nơi gọi

| Hàm | Tham số chính | Trả về | Nơi gọi |
| --- | --- | --- | --- |
| request_json | base_url, path, payload=None, timeout=30 | dict ok/data/error/http_status | select_model/chat. |
| select_model | base_url, configured_model="", timeout=5 | dict model/error | handle_message khi cần chọn tên. |
| chat | messages, base_url, model, response_schema, timeout=30 | LLMCallResult | extract_nlu/choose_opening. |
| build_nlu_messages | message, history, needs | list ChatMessage | extract_nlu. |
| extract_nlu | message, history, needs, base_url, model, timeout | LLMExtractionResult data/error/attempts/repaired | handle_message. |
| choose_opening | facts, base_url, model, timeout | dict opening/error | handle_message sau phản hồi nghiệp vụ không lỗi nguồn. |
| analyze_message | text, repository | NLUResult rule | handle_message/respond cũ/test. |
| check_llm_proposal | proposal: LLMNLU, rule: NLUResult | mã lỗi str hoặc None | handle_message trước hợp nhất. |
| merge_llm_nlu | text, proposal, repository, rule_result=None | NLUResult nội bộ | handle_message khi đề xuất hợp lệ. |
| new_conversation | conversation_id=None, max_turns=6 từ config | Conversation mới | main/reset/test/người gọi. |
| handle_message | message, repository, conversation; keyword chat_mode/base_url/model/timeout | ConversationTurn | main/test/người gọi Python. |
| respond | message, repository, state=None; keyword nlu=None | ChatResponse | controller; vẫn gọi trực tiếp như stage 2 được. |
| update_needs | state, nlu, data_mode | ChatState mới | respond; thuộc tính cập nhật giữ thông tin trước. |
| main | không có | None; nhập/in terminal | guard cuối main.py. |

`*` trong chữ ký hàm yêu cầu tham số phía sau truyền theo tên, ví dụ
`chat_mode="rule"`. Nó làm lời gọi rõ ràng, không đổi ba tham số cũ của respond.
Các hàm schema .model_json_schema()/.model_validate_json() do Pydantic cung cấp.

ConversationTurn có response, conversation, engine, model, llm_error,
nlu_attempts, phrasing_status. Engine rule/ollama/rule_fallback/source_error
khác catalog_status unconfigured/no_results/success/error. Thành công trích
NLU không đồng nghĩa có sản phẩm hoặc có chính sách/đơn.

## 5. Code then chốt và thuật ngữ mới

### HTTP và API local — backend

**HTTP** là giao thức gửi yêu cầu/nhận phản hồi. **Client** là chương trình
gọi dịch vụ; Ollama là dịch vụ chạy trên máy. **API** là giao diện gọi dịch
vụ; **endpoint** là đường dẫn như /api/chat. **Local/loopback** nghĩa là cùng
máy, ví dụ localhost:11434; không phải deploy website lên Internet.

GET /api/tags đọc danh sách tên model đã cài. POST /api/chat gửi JSON
model/messages/format/stream. Trong code, stream=false để nhận một phản hồi
đầy đủ thay vì đọc dần từng đoạn. Format là JSON schema; đây là định dạng
Ollama hỗ trợ cho structured output. Xem
[API chat](https://docs.ollama.com/api/chat),
[API tags](https://docs.ollama.com/api/tags) và
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

**HTTP status** là mã kết quả: 2xx thành công, 404 không tìm thấy, 5xx lỗi
dịch vụ. Client vẫn kiểm tra body JSON, done, tên model và content; status
200 chưa bảo đảm body đúng. **Timeout** là giới hạn chờ ở thao tác mạng, giúp
không chờ vô hạn khi model chậm. Timeout áp dụng từng yêu cầu, không phải
toàn lượt; có thể có tags, hai lần NLU và một lần lời mở đầu.

```python
body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
request = Request(url, data=body, method="POST", headers=headers)
with urlopen(request, timeout=timeout) as response:
    data = json.loads(response.read().decode("utf-8"))
```

Đoạn này rút gọn phần gửi/đọc; code thật có status/try-except. **UTF-8** là
mã hóa chữ Việt; encode đổi chuỗi thành byte để gửi, decode đổi byte về chuỗi.
Không dùng json.loads để đọc byte lỗi rồi giả vờ truy vấn thành công.

select_model không gọi /api/pull. Tên cụ thể sai trả model_not_found, không
âm thầm thay tên khác. Khi rỗng, chọn Qwen local nhỏ nhất theo dung lượng
file trong tags, bỏ cloud/remote; không bảo đảm dung lượng đó phù hợp RAM.

### Prompt và structured output — AI/NLP

**Prompt** là đầu vào hướng dẫn model. System message đặt nhiệm vụ; user
message chứa câu hiện tại/nhu cầu; lịch sử giúp hiểu câu nối tiếp. Quy tắc
trong prompt không phải bảo đảm an toàn tuyệt đối: model có thể hiểu sai
hoặc làm theo yêu cầu không phù hợp; code vẫn kiểm soát dữ liệu/nghiệp vụ.

**Structured output** là kết quả theo cấu trúc thống nhất thay vì đoạn văn
tự do. LLMNLU chứa intents, product_mentions, budget_vnd, flavor, servings,
quantity, size, price_inclusive. Không có product_id, price_vnd, stock_status
hoặc đơn hàng. Ngân sách là nhu cầu, không phải giá bán.

Ví dụ cấu trúc mong đợi cho nhu cầu một bánh; tên bên dưới chỉ là khách nhắc:

```json
{
  "intents": ["recommendation", "flavor", "size"],
  "product_mentions": ["bánh socola"],
  "budget_vnd": 300000,
  "flavor": "socola",
  "servings": 6,
  "quantity": null,
  "size": null,
  "price_inclusive": false
}
```

JSON null là Python None: không có thông tin, không dùng giá 0 để thay phần
thiếu. Danh sách intent không cần đúng nguyên một thứ tự; code giữ intent
an toàn từ rule và thêm đề xuất hợp lệ. Có thể có intent model đoán dư.
requires_clarification thuộc NLUResult **nội bộ do code tính**, không phải
field LLM. Thử thật cho thấy model tự bật cờ này cả với câu rõ ràng, nên
giao quyết định cho các kiểm tra nhiều tên/thuộc tính, mâu thuẫn, loại trừ…

### Validation — Python/backend

**Validation** là kiểm tra dữ liệu thỏa điều kiện trước khi sử dụng.
**Pydantic** là thư viện kiểm tra/khai báo schema. Hai class nhỏ kế thừa
BaseModel cần để dùng khả năng này; logic vẫn là hàm, không có class agent/chatbot.

```python
class LLMNLU(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)
    # Các field đầy đủ xem app/schemas.py.
    budget_vnd: int | None = Field(ge=0)
    servings: int | None = Field(ge=1)
```

Strict kiểm tra kiểu chặt: không đổi "300000" thành số; extra=forbid cấm field
ngoài hợp đồng. ge là greater than or equal: giới hạn >=. `int | None` cho
phép null nhưng không có default nên key vẫn bắt buộc có mặt. TypedDict cũ
chỉ mô tả kiểu; BaseModel mới kiểm tra lúc chạy. `.model_json_schema()` tạo
mô tả schema và `.model_validate_json()` kiểm tra/đọc JSON, theo
[tài liệu Pydantic](https://docs.pydantic.dev/latest/concepts/json/).

Nếu JSON sai hoặc thiếu key/sai kiểu, extract_nlu thêm một yêu cầu sửa, tổng
tối đa hai lần. Lần thứ hai vẫn sai thì invalid_nlu_json, quay về rule. Nếu
timeout/HTTP/model lỗi thì dừng ngay, không giả vờ đó là lỗi cú pháp cần sửa.

**JSON đúng schema chưa chứng minh ý nghĩa đúng.** check_llm_proposal còn
kiểm tra mention có trong câu hiện tại, số có trái regex hay không, và thuộc
tính mới có dấu hiệu tương ứng trong câu. Sao chép “bánh socola” từ lượt cũ
sang câu chỉ tăng ngân sách bị invalid_nlu_mentions; dùng rule câu hiện tại
để tăng ngân sách, giữ nhu cầu đã lưu. Không thử sửa thêm ngoài vòng JSON.

merge_llm_nlu không nhận ID từ model. ID giữ từ tên/alias của repository đã
đối chiếu qua analyze_message. Tên chưa tìm thấy chỉ thành query/term chưa
xác minh; nguồn quyết định unconfigured/no_results/success/error.

### Context, lịch sử và nhu cầu — backend/AI-NLP

**Context** là thông tin đưa cho model hiểu lượt hiện tại: hướng dẫn, một số
lượt trước, nhu cầu đã lưu. **Token** là đơn vị model xử lý văn bản, không
bằng chính xác một ký tự hoặc một từ. Số lượt/ký tự là giới hạn đơn giản,
chưa đo token chính xác; câu quá dài có thể vượt cửa sổ context của model.

```python
current = deepcopy(conversation)
current["history"] = current["history"][-2 * current["max_turns"]:]
```

Deepcopy sao chép cả list/dict lồng nhau, tránh sửa phiên cũ/người khác. Slice
âm lấy các mục cuối; mỗi lượt có hai message nên nhân 2. Lịch sử gửi model
còn được cắt tối đa 1000 ký tự/message. Nhu cầu lưu riêng ở needs, không được
xóa khi cắt history. UUID là mã định danh được tạo cho phiên, không phải tài
khoản người dùng hay dữ liệu khách hàng.

Khi gọi handle_message phải nhận lại conversation mới. Không có biến toàn
cục chứa history của mọi khách. Nếu sau này viết API, API phải giữ đúng ID →
phiên và xử lý đồng thời; giai đoạn này chưa triển khai kho phiên/SQLite.

### Diễn đạt và nghiệp vụ

LLMOpening chỉ chấp nhận ba câu mở đầu. Khi cần hỏi lại, schema gửi model
chỉ cho câu hỏi lại; khi không cần, cho hai câu ghi nhận/đối chiếu. Sau khi
nhận vẫn kiểm tra cờ, không tin schema generation là tuyệt đối.

Phần còn lại do describe_products/summarize_needs/respond tạo từ repository
và nhu cầu. Model không được tự viết giá, “còn hàng”, phí giao hàng hay “đơn
đã xác nhận”. Nếu lời mở đầu sai, giữ mẫu code và báo lỗi diễn đạt. Đây là
diễn đạt giới hạn, chưa phải sinh tự do toàn bộ câu trả lời.

## 6. Vì sao chọn cách này, giới hạn và phương án khác

- urllib đủ cho hai endpoint; chưa cần SDK hoặc dependency HTTP riêng. Hạn
  chế: code đồng bộ, chưa có deadline toàn lượt/cơ chế xử lý nhiều khách đồng thời.
- Pydantic ở biên LLM theo yêu cầu stage 3; giữ schema/repository cũ, không
  viết lại dự án hoặc class hóa toàn bộ logic.
- Rule + validation + kiểm tra nghĩa giúp hoạt động khi model lỗi/chưa có.
  Không chỉ sửa prompt rồi tin rằng model không bịa.
- Lịch sử/nhu cầu riêng trong RAM đủ terminal; SQLite chỉ thêm khi được yêu cầu.
- Lời mở đầu giới hạn giúp kiểm soát thông tin; phương án sinh lại toàn câu
  từ fact cũng có nguy cơ thêm cam kết/giá, cần đánh giá riêng trước khi mở rộng.
- Không hardcode menu trong prompt/logic; thay nguồn qua interface như stage 2.

Giới hạn: kiểm tra nghĩa chỉ một số dấu hiệu, model có thể đoán dư intent,
copy thông tin hoặc hiểu sai mà chưa bị phát hiện. Rule không hiểu mọi cách
nói, lỗi gõ, liên kết nhiều bánh, phủ định hay ngân sách tổng đơn. LLM có thể
hiểu số viết bằng chữ trong test giả lập; chưa đo khả năng đó trên tập thật.
Temperature=0 không bảo đảm hiểu đúng/lặp lại y hệt. Một lượt có tối đa hai
request NLU và một request lời mở đầu nên có thể chậm. Giá/số người mỗi bánh,
quantity chỉ ghi nhận; chưa có chính sách thật, đơn/API/UI hoặc persistence.

## 7. Lệnh Windows, câu hỏi mẫu và kết quả mong đợi

PowerShell tại root, dùng Python môi trường; chọn interpreter như README:

```powershell
cd D:\Chatbot
.\.venv\Scripts\python.exe -m pip --disable-pip-version-check install -r requirements-dev.txt
$env:CATALOG_MODE = "empty"
$env:CHAT_MODE = "rule"
.\.venv\Scripts\python.exe -X utf8 main.py
```

Trong bot, nhập hai câu:

```text
Mình cần bánh socola cho 6 người dưới 300k.
Tăng ngân sách lên 400k.
thoát
```

Mong đợi: filters chứa vị socola/6 người; max_price_vnd đổi 300000 → 400000;
products rỗng; thông báo chưa có menu. Lượt sau không reset vị/số người.

Chỉ thử Ollama khi có dịch vụ/model đã cài, không tải model:

```powershell
ollama list
(Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5).models | Select-Object name,size
$env:CHAT_MODE = "ollama"
$env:OLLAMA_MODEL = "qwen3.5:4b"
$env:OLLAMA_TIMEOUT_SECONDS = "60"
.\.venv\Scripts\python.exe -X utf8 main.py
```

Tên trên đã có ở máy này; máy khác dùng đúng tên trong tags. Rỗng có thể khám
phá Qwen local đã cài. Nếu chưa có Ollama/model, dùng rule; không cần tải để
chạy test. Nếu dịch vụ chưa chạy, mở ứng dụng Ollama hoặc `ollama serve` trong
terminal riêng; có dịch vụ rồi thì không cần mở thêm.

Sau khi thoát bot, đổi `$env:CATALOG_MODE = "mock"` và chạy lại. Thử:

| Câu | Mong đợi |
| --- | --- |
| giá và size bánh socola | Mock-001, hai size 16/20 cm và giá 250.000/350.000 đ, có nhãn mẫu. |
| socola dưới 300k | Chỉ biến thể 16 cm/250.000 đ, không ghép giá nhỏ với số người size lớn. |
| giá bánh sầu riêng | no_results; khác empty unconfigured. |
| socola 300k và dâu 200k | Hỏi lại, không gán hai giá tùy ý. |
| đặt 2 bánh socola, chính sách giao hàng | Ghi nhận ý định, thiếu chính sách; chưa tạo đơn. |

Quan sát dòng “Bộ hiểu câu”: ollama/rule_fallback/source_error. Lỗi LLM không
được hiểu là nguồn dữ liệu lỗi; mock vẫn có nhãn mẫu. Có tên model không chứng
minh sinh thành công; xem engine/llm_error/phrasing. Gõ mới để reset cả phiên.

Gọi bằng Python để xem nhu cầu/lịch sử có cấu trúc:

```python
from app.conversation import new_conversation, handle_message
from app.repositories.empty_catalog import EmptyCatalogRepository

repo = EmptyCatalogRepository()
conversation = new_conversation()
for message in ["socola cho 6 người dưới 300k", "Tăng ngân sách lên 400k"]:
    turn = handle_message(message, repo, conversation, chat_mode="rule")
    conversation = turn["conversation"]
print(conversation["needs"])
print(len(conversation["history"]))  # 4 message = 2 lượt
```

## 8. Kiểm thử đã chạy, kết quả thật, phần chưa kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q main.py app tests
.\.venv\Scripts\python.exe -m pip check
```

**Giả lập:** 120 passed in 1.63s, mã thoát 0. HTTP/model bị thay bằng
monkeypatch (thay tạm hàm khi test), không gọi model thật. Test nguồn mock là
dữ liệu mẫu; test mock HTTP là phản hồi dịch vụ giả, hai khái niệm khác nhau.

Kiểm tra: empty/mock; riêng lịch sử/nhu cầu và cắt context; reset; JSON sai
hai lần/sửa lần hai; strict type/field cấm; HTTP/status/timeout/model không
có; đề xuất copy mention/số mâu thuẫn; enum sai; nguồn lỗi trước/sau LLM;
giá/tình trạng/policy/order không lấy từ model. CLI rule hai nguồn/import/EOF
được chạy qua subprocess (tiến trình con). compileall/pip check đạt; kết quả
rà soát cuối cập nhật trong progress.md.

**Gọi model thật riêng:** GET tags thành công, đã cài qwen3.5:4b. Ba lượt
đầu với timeout 30s bị timeout và fallback đúng. Thử sau đó có JSON hợp lệ;
phát hiện cờ hỏi lại sai và copy mention cũ, đã thêm kiểm tra trong code.

Bản cuối, timeout 60s, model có sẵn, ba kiểm tra hành vi đều đạt:

| Lượt thật | Bộ hiểu/diễn đạt thực tế | Kết quả | Thời gian cả lượt |
| --- | --- | --- | --- |
| Empty: nhu cầu socola/6 người/dưới 300k | ollama, NLU 1 lần, lời mở đầu success | Ghi nhu cầu; chưa có menu, không có sản phẩm. | 33.20s |
| Cùng phiên: tăng lên 400k | rule_fallback, invalid_nlu_mentions, không gọi lời mở đầu | Model copy tên bánh cũ; từ chối đề xuất. Rule tăng 400k, giữ vị/6 người. | 11.08s |
| Mock: giá và size bánh socola | ollama, NLU 1 lần, lời mở đầu success | 16/20 cm, 250.000/350.000 đ đúng mẫu và nhãn. | 16.34s |

Không nói cả ba lượt dùng LLM thành công; lượt cập nhật là fallback. Đây là
vài smoke check (thử nhanh đường chạy), không là bộ đánh giá độ chính xác/
ổn định. Thời gian phụ thuộc trạng thái máy, không cam kết tốc độ các lượt sau.

Đã chạy main.py với tên cố ý không có qwen-stage3-not-installed: báo
model_not_found, rule_fallback, NLU 0 lần; vẫn xử lý hai câu nhu cầu/400k đúng
và thoát mã 0. Không tải/gọi model thiếu. Đây là thử lỗi trên Ollama thật,
khác test transport giả lập; không cần xóa model đang cài để thử trường hợp này.

GPU đã đọc: RTX 2050, 4096 MiB VRAM (bộ nhớ GPU). RAM chưa đọc được vì CIM
bị Access denied. Chưa kiểm tra tập ngôn ngữ độc lập, tải đồng thời, nguồn thật,
API/UI/SQLite/đơn, thao tác UI VS Code/interpreter, Ctrl+C bằng bàn phím thật
và Git ignore trong repository. Không tải model hoặc tạo dữ liệu khách thật.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Cách xử lý |
| --- | --- |
| ModuleNotFoundError: pydantic | Cài requirements-dev hoặc requirements bằng python.exe trong .venv. |
| Sửa .env không đổi chế độ | Chưa có loader .env; đặt biến PowerShell trước khi chạy lại Python. |
| connection_error | Kiểm tra tags, mở Ollama/serve nếu dịch vụ chưa chạy; dùng rule khi chưa có. |
| model_not_found | Tên phải khớp tags, kể cả tag sau dấu hai chấm. Không tự tải/đổi model. |
| timeout | Thử 60s qua cấu hình; kiểm tra tải máy/model có sẵn. Fallback không chứng minh model chạy tốt. |
| invalid_config | Kiểm tra URL local/timeout; chưa hỗ trợ endpoint trên máy từ xa. |
| invalid_response/http_error | Body/status dịch vụ sai; kiểm tra Ollama. Code không coi đó là query thành công. |
| invalid_nlu_json | Sau một lần sửa vẫn sai schema; lượt dùng rule, xem cấu hình/prompt/test. |
| invalid_nlu_mentions | Model thêm/copy cụm không có ở câu hiện tại; rule xử lý câu gốc. Đây là kiểm tra bảo vệ nhu cầu. |
| nlu_rule_conflict/invalid_nlu_context | Model số sai hoặc copy thuộc tính cũ; dùng rule cho lượt đó, không ghi đè từ đề xuất. |
| invalid_opening_json/choice | Phần mở đầu bị từ chối; giữ thông tin từ code, không sửa giá/tồn kho để khớp model. |
| Nguồn error | Kiểm tra adapter/fixture; không dùng model hoặc mock khác để giả thành công. |
| Hội thoại bị quên thuộc tính | Phải truyền lại turn["conversation"], tránh tạo phiên mới mỗi câu. |
| Khách này thấy nhu cầu khách khác | Kiểm tra cách người gọi giữ phiên; mỗi khách cần object/ID riêng. |
| Context quá dài | Giảm số lượt, rút câu, dùng reset; chưa có đếm token chính xác. |
| Bot hỏi lại nhiều bánh | Chưa liên kết thuộc tính tổng quát; nêu từng bánh/nhu cầu rõ ràng. |
| Tiếng Việt lỗi qua pipe | Dùng -X utf8, file UTF-8; PowerShell 5.1 cần OutputEncoding UTF-8 nếu truyền script qua pipe. |

Không in phản hồi lỗi dịch vụ/exception riêng tư ra khách. Chỉ dùng mã lỗi
đã chốt. Chưa có log hội thoại bền hoặc API key trong code.

## 10. Năm câu hỏi vấn đáp/phỏng vấn kèm gợi ý

1. **HTTP API local khác import một hàm Python thế nào?** Client gửi request
   JSON cho dịch vụ Ollama, có timeout/status/lỗi kết nối; import nạp module
   trong tiến trình. Không phải gọi API web của chatbot đã deploy.
2. **Structured output và validation bảo đảm được gì?** Hợp đồng key/kiểu/
   giới hạn; không chứng minh khách muốn gì hoặc cửa hàng có sản phẩm. Cần
   kiểm tra nghĩa cơ bản và repository xác minh.
3. **Vì sao product_mentions không phải product_id?** Cụm khách/model nhắc
   chưa xác minh. Chỉ đối chiếu tên/alias nguồn mới giữ ID hợp lệ, nguồn empty
   không tự có ID dù LLM có thể diễn đạt trôi chảy.
4. **Giữ nhu cầu khi cắt context thế nào và tránh chung lịch sử ra sao?**
   Mỗi conversation mới có UUID/history/needs riêng; deepcopy trả phiên mới.
   History giới hạn lượt, needs tách riêng; người gọi giữ đúng phiên khách.
5. **Timeout/JSON sai/model thiếu/source lỗi xử lý khác nhau thế nào?** JSON
   sai sửa 1 lần, transport/model dừng ngay rồi rule có thông báo. Source lỗi
   vẫn error, không thay bằng mock/LLM. NLU thành công cũng không tạo đơn.

## 11. Ba bài tập nhỏ để tự sửa code

1. **Quan sát cắt lịch sử:** dùng new_conversation(max_turns=2), gửi 4 câu
   bằng rule. In len(history) và needs, giải thích vì sao lịch sử còn 4
   message nhưng ngân sách/vị/số người vẫn có. Thử tạo hai phiên độc lập.
2. **Test model copy ngữ cảnh:** đọc test_model_copying_old_mentions_and_attributes_falls_back_to_current_rule.
   Đổi đề xuất giả thành budget_vnd sai với câu hiện tại, chạy test liên quan
   và viết assert llm_error=nlu_rule_conflict; kiểm tra ngân sách rule đúng.
3. **Thêm lời mở đầu an toàn:** thêm một câu trung tính vào Opening, không có
   giá/tồn kho/đơn/chính sách; cập nhật test lựa chọn theo cờ và chạy suite.
   Nếu giữ thay đổi, cập nhật contracts/decisions để enum code/tài liệu khớp.

Chưa tự làm các bài tập này. Không tải model hoặc thay mẫu thành dữ liệu thật
chỉ để thử. Dùng pytest/monkeypatch kiểm tra lỗi độc lập với Ollama.

## 12. Kiến thức cần học trước bước tiếp theo

- Python: type hint/dict lồng nhau, sao chép, exception, hàm nhận keyword,
  BaseModel và cách trả dữ liệu có cấu trúc.
- Backend: request/response JSON, HTTP status, phiên theo ID, validation đầu
  vào, đồng thời; phân biệt lỗi nguồn/LLM/API và không dùng chung state.
- AI/NLP: prompt không là bảo đảm; schema/kiểm tra nghĩa/nguồn xác minh là các
  lớp khác nhau. Context có giới hạn, test giả lập không đo chất lượng model thật.
- Nghiệp vụ: empty không xác nhận sản phẩm; mock có nhãn; chính sách cần nguồn,
  đặt hàng mô phỏng vẫn cần luồng xác nhận khi được triển khai sau.
- Công cụ: .venv/interpreter đúng, biến PowerShell, kiểm tra tags và theo dõi
  engine/fallback. Đọc progress/next_steps trước khi yêu cầu giai đoạn sau.

Đề xuất bước sau là API chat local qua FastAPI; chỉ thực hiện theo phạm vi
người dùng yêu cầu. Chưa bắt buộc có database sản phẩm thật hoặc model đủ nhanh
để học/kiểm thử API bằng rule. Giai đoạn 3 kết thúc tại client và hội thoại.
