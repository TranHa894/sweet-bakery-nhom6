# Bài học giai đoạn 2: chatbot terminal và nguồn dữ liệu thay thế được

Thực hiện ngày 02/10/2026 bằng Python 3.12.10 trong `.venv`. Đây là bài học lịch
sử giai đoạn 2; từ 03/10/2026, README và stage_03 mô tả code hiện tại. Các mô tả
ollama chưa triển khai/runtime chỉ thư viện chuẩn bên dưới đúng tại thời điểm stage 2.

## 1. Mục tiêu và chức năng đã hoàn thành

Chatbot chạy trong **terminal** (cửa sổ nhập lệnh/văn bản), chưa cần website hay
database. Hai **mode** (chế độ) dùng cùng logic: empty khi chưa có nguồn và mock
với 5 sản phẩm giả. Phản hồi luôn nêu mode; mock luôn ghi rõ dữ liệu mẫu.

Có nhiều **intent** (ý định của câu hỏi): greeting, price, size, flavor,
availability, recommendation, policy, order_request, fallback. Một câu có thể
vừa hỏi giá vừa hỏi size. **Entity** (thực thể/thông tin trích từ câu) gồm cụm
bánh, ngân sách, hương vị, số người ăn, số lượng và size cơ bản.

Phân biệt kiến thức:

| Nhóm | Phần thực hiện |
| --- | --- |
| Python | Dictionary (từ điển key–value), list (danh sách), type hint (chú thích kiểu), Protocol (hợp đồng cách gọi), TypedDict (cấu trúc dictionary), regex (mẫu tìm văn bản), JSON (định dạng dữ liệu), exception (lỗi được phát sinh). |
| Backend | Phần xử lý phía máy chủ: hợp đồng nguồn, dependency injection (truyền nguồn từ ngoài vào), state (trạng thái) trong RAM (bộ nhớ đang chạy). |
| AI/NLP | NLU (natural language understanding, hiểu ngôn ngữ tự nhiên) theo từ khóa/quy tắc; chưa dùng LLM. |
| Nghiệp vụ | Giá/tình trạng từ nguồn, unknown không được suy đoán; empty không xác nhận sản phẩm; chưa tạo đơn. |

**Không gọi đây là mô hình đã huấn luyện.** Không dùng Ollama/model/API web hoặc
database ở giai đoạn này. Policy chỉ nhận diện câu hỏi rồi nói thiếu tài liệu.

Tên intent trong code có nghĩa: greeting = chào hỏi; price = giá; size = kích
cỡ; flavor = hương vị; availability = tình trạng có hàng; recommendation = tư
vấn; policy = chính sách; order_request = ý định đặt; fallback = chưa hiểu yêu cầu.

## 2. File tạo/sửa và trách nhiệm

| File | Thay đổi và trách nhiệm |
| --- | --- |
| `app/schemas.py` | Mới: Product/Variant, filters/result/NLU/state/response và hàm kiểm tra sản phẩm. |
| `app/repositories/__init__.py` | Mới: đánh dấu package nguồn dữ liệu. |
| `app/repositories/catalog.py` | Mới: Protocol, factory chọn nguồn, wrapper lỗi truy vấn. |
| `app/repositories/mock_catalog.py` | Mới: đọc/kiểm tra JSON mẫu, tìm/lấy sản phẩm, capabilities. |
| `app/repositories/empty_catalog.py` | Mới: trả nguồn chưa cấu hình, không giả hết hàng. |
| `data/mock_catalog.json` | Mới: 5 mẫu có ID cố định và nhãn mock; một mẫu thiếu giá/số người/tình trạng. |
| `app/text_utils.py` | Mới: chuẩn hóa, so cụm từ, định dạng VND. |
| `app/nlu.py` | Mới: nhận nhiều intent và trích entity, phát hiện cần hỏi lại. |
| `app/chatbot.py` | Mới: nhu cầu trong RAM, gọi interface và tạo phản hồi có nhãn. |
| `main.py` | Sửa: thay thông báo nền tảng bằng vòng chat, reset/thoát, giữ tên main(). |
| `tests/test_catalog.py` | Mới: trạng thái nguồn, schema, bộ lọc và fixture lỗi. |
| `tests/test_nlu.py` | Mới: tiếng Việt, entity, nhiều intent, alias động và ambiguity. |
| `tests/test_chatbot.py` | Mới: hành vi, state, hai CLI mode, lỗi nguồn và đầu vào gốc. |
| `requirements-dev.txt` | Sửa: thêm pytest 8.4.2 để kiểm thử. |
| `requirements.txt` | Sửa chú thích: runtime giai đoạn 1–2 vẫn chỉ thư viện chuẩn. |
| `.env.example` | Sửa chú thích; giữ nguyên biến và mặc định, chưa tự nạp .env. |
| `README.md`, `data/README.md` | Sửa cách chạy, thử câu hỏi và vai trò fixture. |
| Các file `docs/project_spec.md`, `progress.md`, `decisions.md`, `contracts.md`, `data_integration.md`, `next_steps.md` | Cập nhật đúng code/trạng thái hiện tại. |
| `docs/learning/stage_01.md` | Thêm ghi chú đây là bài học lịch sử giai đoạn 1. |
| `docs/learning/stage_02.md` | Mới: bài học này. |

Giữ nguyên `app/config.py`, `app/__init__.py`, `.gitignore` và `.venv` đã có.
Không tạo adapter nguồn thật, module rỗng hoặc database sản phẩm.

## 3. Luồng đầu vào → xử lý → đầu ra

```text
CATALOG_MODE → factory → repository empty hoặc mock
                                ↓ truyền vào hàm
Câu gốc → normalize → NLU gọi search_products({}) để lấy tên/alias
        → intents + entities + cờ hỏi lại
        → cập nhật nhu cầu nếu rõ ràng
        → search_products(filters) qua interface
        → status + products/variants
        → phản hồi ghi mode + nhãn mock + state mới
        → main in text và dùng state cho lượt sau
```

**Factory** là hàm tạo đúng thành phần theo lựa chọn; **state** là trạng thái
hội thoại, ở đây chỉ là nhu cầu trong dictionary. **RAM** là bộ nhớ đang chạy;
state mất khi thoát chương trình, không ghi ra file hoặc database.

Với empty, truy vấn trả unconfigured và chatbot chỉ ghi nhận nhu cầu. Với mock,
repository đọc file lúc khởi tạo; mỗi câu dùng dữ liệu đã nạp trong bộ nhớ. Sửa
fixture thì cần khởi động lại chương trình. Source error giữ khác no_results.
**Source** là nguồn dữ liệu; **payload** là phần dữ liệu trong kết quả.

## 4. Hàm chính: tham số, trả về, nơi gọi

| Hàm/phương thức | Đầu vào | Trả về | Nơi gọi |
| --- | --- | --- | --- |
| `main()` | Không có | None, đồng thời đọc/in terminal | Guard cuối main.py. |
| `create_catalog_repository(mode)` | empty/mock | Repository theo Protocol | main() và test factory. |
| `safe_search_products(repository, filters, data_mode="unknown")` | Nguồn + bộ lọc + mode nếu đã biết | SearchResult hoặc error an toàn | NLU/respond(). |
| `search_products(filters)` | SearchFilters | SearchResult | NLU nạp tên/alias, chatbot tra nhu cầu, test. |
| `get_product(product_id)` | ID ổn định | ProductResult | Test; sẵn cho nơi cần lấy đầy đủ sản phẩm sau này, chưa dùng trong chatbot. |
| `get_capabilities()` | Không có | CatalogCapabilities | respond(), test. |
| `MockCatalogRepository(data_path=None)` | Đường dẫn mẫu tùy chọn | Đối tượng nguồn mock; giữ lỗi nếu dữ liệu sai | Factory và test với fixture khác. |
| `validate_product(product)` | Dictionary Product | None, hoặc raise ValueError | Constructor mock và test. |
| `matching_variants(product, filters)` | Sản phẩm + bộ lọc | List biến thể thỏa | search_products() trong mock. |
| `matches_product(product, filters)` | Sản phẩm + bộ lọc | bool | search_products() trong mock. |
| `normalize_text(text)` | Câu/cụm chuỗi | Chuỗi chuẩn hóa | NLU, so khớp trong mock, lệnh CLI. |
| `phrase_spans(text, phrase)` | Text đã chuẩn hóa + cụm | List cặp vị trí đầu/cuối | Nhận tên/alias/vị/intent. |
| `format_vnd(value)` | Số nguyên VND | Chuỗi, ví dụ 250.000 đ | Tóm tắt nhu cầu và trình bày sản phẩm. |
| `analyze_message(text, repository)` | Câu gốc + nguồn qua interface | NLUResult | respond(), test NLU. |
| `create_state()` | Không có | ChatState mới | main(), respond() nếu thiếu state, reset/test. |
| `update_needs(state, nlu, data_mode)` | State cũ + phân tích + mode | State mới | respond() khi câu rõ ràng. |
| `summarize_needs(state)` | State | Chuỗi nhắc lại nhu cầu | respond(). |
| `describe_products(products)` | List Product từ repository | Chuỗi trình bày trường đã có | respond() khi success. |
| `make_response(text, capabilities, nlu, state, result, clarification=False)` | Nội dung và kết quả | ChatResponse có nhãn | Các nhánh respond(). |
| `respond(message, repository, state=None)` | Câu + nguồn + state tùy chọn | ChatResponse và state mới | main(), test. |

Các helper NLU gọi trong analyze_message: `find_product_mentions(text, products)`
trả list `(start, end, product_id, term)`; `extract_flavors(text, products)` trả
list `(flavor, start, end)`; `extract_budgets(text)` trả list số nguyên VND;
`parse_money(amount, unit)` trả một số nguyên; `extract_query(text)` trả cụm bánh
chưa nhận diện hoặc None. Chưa có hàm nhận đơn hàng.

## 5. Giải thích code và kiến thức mới

### Schema, dictionary và TypedDict — Python/backend

**Schema** quy định key (tên trường) và kiểu giá trị. Dictionary là cấu trúc
Python lưu cặp key–value. Product có tên/alias/loại/mô tả/vị, các variants,
allergen, customization, thời gian chuẩn bị và nhãn nguồn. **Variant** là biến
thể, ví dụ hai size của cùng một bánh, có giá/số người/tình trạng riêng.

```python
Variant = TypedDict("Variant", {
    "id": str,
    "size": str | None,
    "price_vnd": int | None,
    "servings": int | None,
    "stock_status": StockStatus,
})
```

`int | None` nghĩa là số nguyên hoặc chưa có thông tin. `TypedDict` giúp mô tả
dictionary cho người đọc/công cụ; không tự kiểm tra giá trị lúc chạy. `Literal`
mô tả một tập giá trị cố định, như các status. Dự án dùng hàm validate_product
để kiểm tra dữ liệu mock lúc nạp. Xem [tài liệu typing](https://docs.python.org/3.12/library/typing.html).

Mọi field Product/Variant đều có mặt; một số được phép None. Khác biệt quan
trọng: null/None chưa biết; giá 0 là giá trị đã biết nếu thực sự miễn phí;
stock unknown chưa biết, out_of_stock mới là nguồn báo hết hàng. Allergen None
không có nghĩa bánh an toàn cho người dị ứng.

### Interface, Protocol và repository — backend

**Interface** là hợp đồng gọi/kết quả. **Repository** cung cấp dữ liệu theo
hợp đồng, che cách lưu/đọc. **Adapter** là triển khai cho một nguồn cụ thể.

```python
class CatalogRepository(Protocol):
    def search_products(self, filters: SearchFilters) -> SearchResult: ...
    def get_product(self, product_id: str) -> ProductResult: ...
    def get_capabilities(self) -> CatalogCapabilities: ...
```

Protocol chỉ khai báo chữ ký; dấu `...` không phải adapter giả. Nguồn có đúng
ba phương thức có thể được truyền vào logic mà không phải kế thừa. Protocol
không tự xác minh dữ liệu nguồn ở runtime. Hai class repository giữ trách nhiệm
nguồn; schema dùng TypedDict dạng hàm và logic dùng hàm, không có class chatbot.

Đọc `status` trước payload. `products=[]` có thể xuất hiện với unconfigured,
no_results hoặc error; không suy chúng đều là hết hàng. get_capabilities mô tả
mode/nhãn/cấu hình/chính sách/quyền nhận đơn, không chứng minh truy vấn đang khỏe.

### Dependency injection — backend, giải thích đơn giản

**Dependency** là phần code cần dùng; ở đây là nguồn dữ liệu. **Dependency
injection** nghĩa là đưa nguồn vào từ ngoài thay vì để chatbot tự tạo nguồn:

```python
repository = create_catalog_repository(CATALOG_MODE)
response = respond(message, repository, state)
```

Bạn có thể gọi `respond("giá và size bánh socola", MockCatalogRepository())`
hoặc cùng hàm với EmptyCatalogRepository. Không sửa chatbot.py để đổi nguồn.
Chatbot biết ba cách hỏi nguồn, không biết file nằm đâu, bảng nào hoặc API ngoài
gọi thế nào. Đây là tổ chức code backend, không phải framework agent.

### JSON và ranh giới dữ liệu — Python/backend

**JSON** là định dạng văn bản lưu dữ liệu theo object/list/string/number/boolean/null.
Trong Python, các cấu trúc tương ứng là dict/list/str/int hoặc float/bool/None.
JSON dùng dấu nháy kép, true/false/null; Python dùng True/False/None.

```python
document = json.loads(path.read_text(encoding="utf-8"))
products = document["products"]
```

Chỉ mock repository làm việc này. UTF-8 là cách mã hóa chữ, cần cho tên tiếng
Việt. Sau khi đọc, kiểm tra nhãn mock/schema/ID trùng. File thiếu/hỏng trả error,
không biến thành empty/no_results. Mock JSON là fixture cho học/test, chưa phải
adapter JSON thật. `data/` vẫn là thư mục, không phải database.

### Chuẩn hóa, regex và nhiều intent — Python/AI-NLP

**Regex** (regular expression, biểu thức chính quy) mô tả mẫu chuỗi. Ví dụ:

```python
re.findall(r"\b(\d+)\s*(?:nguoi|khach|suat|phan)\b", normalized)
```

`r"..."` là raw string, giữ dấu gạch chéo cho regex. `\b` là ranh giới từ;
`\d+` là một hoặc nhiều chữ số; `\s*` là khoảng trắng có thể vắng;
`(...)` lấy nhóm; `(?:a|b)` chọn một mẫu nhưng không lấy nhóm riêng.
Với `cho 6 nguoi`, findall trả `["6"]`, rồi int() đổi thành số 6.

Regex tiền có đơn vị k/nghìn/triệu/VND/đồng hoặc từ chỉ ngân sách, nên “6 người,
2 bánh” không thành giá. Dấu chấm/phẩy giữ để đọc 300.000 hoặc 1,5 triệu.
Cụm ngân sách là mức tối đa mỗi bánh; “dưới” dùng <, “tối đa” dùng <=.

normalize_text tạo chuỗi chữ thường, bỏ dấu và khoảng trắng dư; raw_text giữ
câu đầu vào, kể cả hoa/dấu/khoảng trắng. Main không strip câu trước khi đưa vào
NLU; chỉ kiểm tra riêng câu rỗng/lệnh. Đây là xử lý văn bản, không phải huấn luyện.

NLU lấy tên/alias/ID từ search_products({}), ưu tiên cụm dài để alias con không
đánh nhầm bánh. Từ vựng hương vị phổ thông giúp ghi nhận ở empty, không chứng
minh có bánh bán. Khi nhận diện bánh, flavor chuẩn lấy từ dữ liệu nguồn.

Nhận intent bằng nhiều lần kiểm tra, không dùng chuỗi if/elif loại trừ nhau:

```python
for intent, phrases in INTENT_PHRASES.items():
    if any(phrase_spans(normalized, phrase) for phrase in phrases):
        intents.append(intent)
```

Vì vậy “giá và size bánh...” có cả price và size. Fallback là nhánh khi chưa
nhận diện được. NLU chưa biết mọi cách nói; không cố giải quyết tự động câu mơ hồ.

### Liên kết thuộc tính, lọc biến thể và state — nghiệp vụ/backend

“Socola 300k và dâu 200k” có nhiều bánh/giá. Dù người đọc đoán được liên kết,
code giai đoạn này chưa có parser liên kết tổng quát, nên hỏi lại. Alias trùng,
nhiều giá trị mâu thuẫn, số người/số lượng/size không dương và loại trừ chưa hỗ
trợ cũng hỏi lại. Không chọn bánh hoặc cập nhật state từ câu đó.

Ngược lại, “giá và size bánh socola và bánh dâu” chỉ hỏi các trường chung, không
gán nhiều giá trị nên có thể trình bày cả hai. Giá/số người/size của một yêu cầu
phải khớp **cùng biến thể**: size nhỏ rẻ nhưng không đủ người không thể ghép với
size lớn đắt để giả vờ thỏa cả hai. Search chỉ trả variants phù hợp.

`deepcopy` sao chép cả các list/dict bên trong. Nó tránh code gọi làm thay đổi
dữ liệu mock hoặc state cũ. Câu chỉ bổ sung thuộc tính tiếp tục nhu cầu; nhắc
bánh mới reset bộ lọc. Mọi thông tin state là nhu cầu người dùng, không phải đơn.

### Kiểm thử — Python/backend

**pytest** chạy các hàm test_; **assert** kiểm tra một điều kiện mong đợi.
**Fixture pytest** là đầu vào hỗ trợ test: tmp_path tạo chỗ file tạm;
monkeypatch thay tạm một hàm để thử lỗi; capsys thu output. Chúng khác fixture
dữ liệu JSON: một bên là công cụ test, một bên là bộ dữ liệu mẫu.

Parametrize chạy cùng test với nhiều đầu vào. Subprocess chạy tiến trình Python
con để kiểm tra main thực sự đọc câu hỏi/thoát với từng mode. Xem
[hướng dẫn pytest](https://docs.pytest.org/en/stable/getting-started.html).

## 6. Lý do chọn, giới hạn và phương án khác

- Runtime chỉ dùng thư viện chuẩn; chưa đưa Pydantic/FastAPI vào trước giai đoạn API.
- Dictionary/TypedDict dễ xem và chuyển thành JSON, hàm validation đủ nhỏ cho mẫu.
  Pydantic có thể phù hợp khi cần validation request/API sau này.
- Protocol + repository vừa đủ để thay nguồn, không cần framework agent/DI container.
- Regex dễ trình bày và kiểm thử, chạy khi chưa có model; giới hạn ở từ khóa/cách
  viết đã hỗ trợ. LLM sau này giúp hiểu/diễn đạt nhưng code vẫn kiểm soát nghiệp vụ.
- Chỉ mock biết file JSON, tên/giá/tình trạng không nằm trong prompt/logic.
- State trong RAM đủ cho terminal ngắn; SQLite lưu hội thoại nằm ở giai đoạn sau.
- Hỏi lại bảo thủ khi nhiều bánh/thuộc tính hoặc loại trừ; chưa liên kết câu phức tạp.

Giới hạn thực tế: số đếm phải là chữ số, chưa đọc “hai bánh”; chưa fuzzy match
cho mọi lỗi gõ, khoảng ngân sách tổng quát, giỏ hàng hoặc ngân sách cả đơn. “Tầm”/
“khoảng” hiểu đơn giản là ngưỡng tối đa. Số người/giá tính cho một bánh; quantity
chỉ ghi nhận, chưa tính tiền tổng/tồn kho số lượng. Chưa có chính sách thật,
đặt/xác nhận đơn, API, UI, model, lưu phiên hoặc đánh giá chất lượng tổng thể.

## 7. Lệnh Windows, câu hỏi mẫu và kết quả mong đợi

PowerShell tại root dự án:

```powershell
cd D:\Chatbot
.\.venv\Scripts\python.exe -m pip --disable-pip-version-check install -r requirements-dev.txt
$env:CHAT_MODE = "rule"
$env:CATALOG_MODE = "mock"
.\.venv\Scripts\python.exe main.py
```

Nếu chưa có .venv, tạo bằng `py -3.12 -m venv .venv`; trong VS Code chọn
`.venv\Scripts\python.exe` qua Python: Select Interpreter như stage_01.
Nhập câu hỏi **trong chương trình**, không phải lệnh PowerShell.

| Câu hỏi | Mong đợi trong mock |
| --- | --- |
| `socola dưới 300k` | mock-001, chỉ 16 cm/250.000 đ/6 người/còn hàng mẫu. |
| `giá và size bánh socola` | Hai variants: 16 cm/250.000 đ và 20 cm/350.000 đ. |
| `giá bánh sầu riêng` | no_results, nguồn hoạt động; không nói nguồn chưa cấu hình. |
| `giá và size bánh tart chanh còn hàng không` | 18 cm, chưa có giá/số người/tình trạng. |
| `socola 300k và dâu 200k` | Hỏi lại, không cập nhật nhu cầu từ câu mơ hồ. |
| `chính sách giao hàng` | Thiếu tài liệu, không bịa phí hay cam kết. |
| `đặt 2 bánh socola` | Ghi nhận quantity=2, nói chưa tạo/xác nhận đơn. |

Ví dụ nội dung kết quả đầu tiên, mọi giá/tình trạng là mẫu:

```text
[Nguồn: mock] [DỮ LIỆU MẪU mock — chỉ học và kiểm thử]
...
- Bánh kem socola [mock-001], vị socola:
  • 16 cm: 250.000 đ; khoảng 6 người; còn hàng.
...
```

Gõ `thoát`, rồi chạy mode empty:

```powershell
$env:CATALOG_MODE = "empty"
.\.venv\Scripts\python.exe main.py
```

Nhập `socola`, rồi `dưới 300k cho 6 người, 2 bánh`. Bot nhớ nhu cầu, nêu
`[Nguồn: empty]` và “Chưa có menu để đối chiếu”; products vẫn rỗng, status
unconfigured. Gõ `mới` để xóa nhu cầu, `thoát` để kết thúc. Khi xong, nếu muốn
trở về mặc định trong terminal, bỏ biến bằng Remove-Item Env:CATALOG_MODE và
Remove-Item Env:CHAT_MODE.

Gọi trực tiếp từ Python để xem cấu trúc thay vì chỉ text:

```python
from app.chatbot import respond
from app.repositories.mock_catalog import MockCatalogRepository

result = respond("socola dưới 300k", MockCatalogRepository())
print(result["intents"])
print(result["catalog_status"])
print(result["products"][0]["variants"])
```

## 8. Kiểm thử thực tế và phần chưa kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q main.py app tests
.\.venv\Scripts\python.exe -m pip check
```

Kết quả đã chạy ngày 02/10/2026:

- **63 passed in 0.52s**, pytest 8.4.2, mã thoát 0.
- compileall mã thoát 0; pip check: `No broken requirements found.`
- CLI mock và empty thực sự được chạy trong subprocess: câu hỏi, reset, thoát
  và kết thúc khi hết đầu vào đều đạt. Import main không mở terminal hoặc nạp mẫu.
- Contract test phân biệt bốn status, ID/nhãn, unknown, biến thể thỏa đồng thời,
  bản sao không sửa nguồn, JSON/schema sai và file thiếu.
- NLU test nhiều intent, tiền/đếm tách nhau, câu mơ hồ/alias trùng và tên/vị mới
  do nguồn cung cấp. Main giữ nguyên câu gốc, kể cả khoảng trắng/chữ hoa.
- Chatbot test empty nhớ nhu cầu, giá/size đúng mẫu, unknown không bịa, policy/
  order thiếu chức năng, mọi response có mode, exception không lộ chi tiết.
- Rà soát cuối: 20 file mục tiêu có nội dung UTF-8, đủ 12 mục học, 9 link nội bộ
  hợp lệ, 5 mẫu; NLU/chatbot không đọc JSON hoặc chọn repository cụ thể.

Lệnh cài pytest đầu bị sandbox chặn mạng WinError 10013; cài lại với quyền mạng
đã thành công. Chỉ thêm pytest và dependency nhỏ vào .venv; không thư viện AI/model.

Chưa kiểm tra: dữ liệu thật, adapter thật, Ollama/Qwen, RAM/GPU, website/API,
database, đơn hàng, UI VS Code, Ctrl+C bằng bàn phím thật và Git ignore trong
repository. Chưa đo độ đúng NLU trên tập độc lập; số test đạt không phải độ
chính xác chatbot ngoài thực tế.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Cách xử lý |
| --- | --- |
| Thấy empty dù muốn xem mẫu | Đặt `$env:CATALOG_MODE = "mock"` trước khi chạy lại, kiểm tra biến tồn tại trong đúng terminal. |
| Sửa .env nhưng không đổi mode | Chưa có loader .env; dùng biến môi trường PowerShell. |
| Chọn ollama thì không mở chat | Chưa tích hợp giai đoạn 3; đặt CHAT_MODE=rule, không tự tải model. |
| Fixture thiếu/hỏng/nhãn không đúng | Kiểm tra data/mock_catalog.json, syntax JSON/schema/ID. Repository trả error, không phải no_results. |
| Bánh không tìm thấy trong mẫu | Kiểm tra tên/alias, bộ lọc và nhãn nguồn; không suy cửa hàng thật không bán. |
| Bánh có giá chưa biết bị bỏ khi lọc ngân sách | Đúng hợp đồng: không đủ thông tin để xác nhận giá dưới ngưỡng. None không thay bằng 0. |
| Giá rẻ có size nhỏ nhưng yêu cầu nhiều người không có kết quả | Các điều kiện phải thỏa cùng biến thể; xem ngân sách/số người và dữ liệu mẫu. |
| Bot hỏi lại nhiều bánh hoặc câu phủ định | Chưa hỗ trợ liên kết/loại trừ tổng quát; thử từng nhu cầu, có thể dùng mới/reset. |
| Câu mới còn dùng bộ lọc trước | Câu chỉ thuộc tính nối tiếp state; dùng mới/reset hoặc nhắc rõ bánh mới. |
| Sửa JSON trong khi chạy không cập nhật | Fixture nạp một lần lúc khởi tạo; thoát và chạy lại. |
| Không có pytest hoặc mạng chặn | Dùng pip của .venv cài requirements-dev khi có mạng; runtime chatbot không cần pytest. Không báo test đã đạt nếu chưa chạy. |
| Không tìm thấy app khi chạy test | Tại root dùng `.\.venv\Scripts\python.exe -m pytest -q`, tránh gọi pip/python khác môi trường. |
| Dấu tiếng Việt lỗi | Lưu file UTF-8; thử `.\.venv\Scripts\python.exe -X utf8 main.py`; tránh pipe ASCII trên PowerShell 5.1. |

## 10. Năm câu hỏi vấn đáp/phỏng vấn kèm gợi ý

1. **Schema khác file JSON thế nào?** Schema là hợp đồng cấu trúc nội bộ; JSON
   là định dạng lưu. Adapter đọc JSON/database/API đều chuyển về cùng Product/Variant.
2. **Vì sao cần status nếu products đã là list?** [] có thể là chưa cấu hình,
   không có kết quả hoặc lỗi; mỗi trường hợp cần phản hồi khác, không suy hết hàng.
3. **Dependency injection trong code nằm ở đâu?** Main tạo repository rồi truyền
   vào respond/analyze_message; chatbot không tự chọn nguồn và không biết file JSON.
4. **Vì sao nhận tên/alias từ nguồn và giá theo biến thể?** Thay menu không sửa
   NLU; dữ liệu giá/size/số người cùng biến thể tránh ghép các thông tin không đi cùng nhau.
5. **Vì sao nhiều bánh/thuộc tính cần hỏi lại, và rule có phải model đã huấn luyện?**
   Chưa chắc liên kết nên không tự gán. Rule là quy tắc code; LLM sau này hỗ trợ
   hiểu/diễn đạt, code vẫn kiểm tra nguồn và kiểm soát nghiệp vụ.

## 11. Ba bài tập nhỏ để tự thực hành

1. **Alias mới không sửa logic:** thêm một alias riêng cho mock-001 trong JSON,
   giữ nguyên ID/nhãn. Chạy lại, hỏi giá/size bằng alias mới và giải thích đường
   dữ liệu đi qua repository/NLU. Chạy test sau khi sửa.
2. **Quan sát unknown:** viết một script nhỏ gọi get_product("mock-005"), in
   price_vnd/servings/stock_status; dùng json.dumps(..., ensure_ascii=False) xem
   None thành null. Thử search có ngân sách/số người và giải thích vì sao không
   thể coi mẫu này đáp ứng điều kiện. Không sửa None thành 0.
3. **Thêm cách nói:** thêm “chọn giúp” vào cụm recommendation, thử câu “chọn giúp”
   và viết một test kiểm tra intent trước/sau. Không đưa tên bánh/giá vào quy tắc.
   Ghi giả định từ khóa mới để biết giới hạn của nó.

Các bài tập chưa được thực hiện tự động. Nếu giữ thay đổi có ảnh hưởng hợp đồng,
cập nhật docs/tests cùng code. Không bỏ nhãn mock hoặc tạo đơn thật.

## 12. Kiến thức cần học trước giai đoạn tiếp theo

- Python: dict/list lồng nhau, type hint, hàm trả dữ liệu, exception, class nhỏ và copy.
- Backend: HTTP request/response, JSON payload, timeout, lỗi dịch vụ; cấu hình theo môi trường.
- AI/NLP: LLM và prompting (viết đầu vào hướng dẫn model); output cần validation,
  phân biệt nội dung có căn cứ từ dữ liệu và nội dung model tự sinh.
- Nghiệp vụ: LLM không tự tạo giá/tồn kho, không xác nhận đơn từ phỏng đoán;
  empty/mock và chính sách thiếu vẫn phải phản hồi trung thực.
- Công cụ: kiểm tra RAM/GPU, dịch vụ Ollama/model đã có; chưa tự tải model hoặc
  cài thư viện AI. Khi dịch vụ thiếu, vẫn kiểm thử phần độc lập bằng dữ liệu giả lập.

Đề xuất giai đoạn 3 là Qwen/Ollama local có kiểm soát; chỉ thực hiện khi bạn
yêu cầu. Không cần nguồn kinh doanh thật để học client, nhưng chạy model thật
cần dịch vụ/model phù hợp được xác minh trước.
