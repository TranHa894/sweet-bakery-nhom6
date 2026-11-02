# README TẠM — BÀN GIAO CHATBOT SWEET BAKERY CHO AI KHÁC

Cập nhật nội dung: **02/11/2026**. Đây là bản mô tả để AI mới hiểu dự án và tiếp tục công việc; không phải yêu cầu tự triển khai tất cả ý tưởng trong tài liệu.

## 1. Đọc nhanh trước khi làm bất cứ việc gì

- Dự án đang làm là **chatbot nằm trong repository Sweet Bakery của nhóm**.
- Bản mã nguồn đã được kiểm tra khi lập tài liệu: `D:\sweet-bakery-nhom6\chatbot`.
- Máy còn có một bản cũ ở `D:\Chatbot`. Không mặc định đó là bản đang dùng; đối chiếu đường dẫn, cấu trúc và phiên bản prompt trước khi sửa.
- Chủ dự án mới biết Python cơ bản, cần giải thích dễ hiểu và phục vụ thuyết trình/vấn đáp.
- Python **3.12.10**, Windows, VS Code, môi trường `.venv`.
- Luồng AI chính: **Qwen `qwen3.5:4b` qua Ollama local**. Không dùng Gemini/OpenAI API key trong cấu hình hiện tại.
- Nguồn menu đang chọn: **`group_files`**, đọc `../static/products.json`; đã đọc được **24 sản phẩm mẫu** khi kiểm tra tài liệu.
- **Menu hiện tại là dữ liệu tham khảo/mô phỏng**, chưa phải nguồn giá/tồn kho kinh doanh chính thức.
- **SQLite lưu hội thoại và yêu cầu**; có thêm bảng/adapter demo local, nhưng cấu hình đang dùng không lấy menu chính từ các bảng sản phẩm SQLite.
- **`KNOWLEDGE_MODE=empty`**: có code RAG, nhưng chưa có chính sách thật được cấu hình để trả lời.
- **Luồng web hiện lưu yêu cầu chờ tư vấn**, chưa xác nhận đơn kinh doanh thật, chưa thanh toán/giao hàng thật.
- Có giao diện chat độc lập và widget nhúng website; **không còn CLI trò chuyện cho người dùng**.
- Không có thư mục `tests/` hoặc `docs/` trong bản đang làm. Kiểm thử nằm ở `scripts/`; dữ liệu đánh giá nằm ở `evaluation/`.
- Không viết lại dự án, không tạo chatbot thứ hai, không xóa module chỉ vì không thấy nó chạy trong một cấu hình.
- Không tự tải/đổi model, đăng ký dịch vụ, gửi email, tiêu tiền hoặc deploy. Những việc đó cần yêu cầu riêng của người dùng.
- File này là một file bàn giao được người dùng yêu cầu riêng; không được suy ra rằng có thể tạo lại hàng loạt tài liệu `docs/`.

## 2. Quyền chỉnh sửa và nguyên tắc làm việc

1. Mặc định chỉ sửa **bên trong thư mục chatbot đang dùng**. Các lần trước có ủy quyền cụ thể để nối widget với website; không coi đó là quyền sửa mọi file bên ngoài cho mọi việc.
2. Đọc `AGENTS.md` nếu có tại workspace/thư mục cha; không ghi đè nó. Khi lập file này không tìm thấy AGENTS.md ở các vị trí tổ tiên đã kiểm tra.
3. Đọc code thực tế, `README.md`, `evaluation/README.md` và tài liệu này trước khi sửa. README cũ có nhiều mục lịch sử với số liệu/cấu hình cũ; không coi mọi đoạn là trạng thái hiện tại.
4. Kiểm tra import/caller trước khi bỏ code. Các nhánh rule, empty, mock, local_demo vẫn có thể được evaluator hoặc cấu hình khác sử dụng.
5. Giữ tên hàm, đường dẫn, schema và API đang được dùng; nếu phải đổi, cập nhật đầy đủ caller và giải thích.
6. Không tạo lại `tests/`, không tạo tài liệu mới trong `docs/` nếu chưa được yêu cầu.
7. Không sửa/seed/reset database đang dùng để chạy thử. Dùng SQLite `:memory:` hoặc database thử riêng đã xác định rõ.
8. Không log hoặc chép token, nội dung `.env`, tên/điện thoại/địa chỉ khách thật vào báo cáo.
9. Dùng `pathlib` và UTF-8; đường dẫn Windows có khoảng trắng hoặc dấu phải hoạt động.
10. Giữ Qwen làm bộ hiểu câu chính ở chế độ Ollama. Regex/alias được dùng để chuẩn hóa, chọn ví dụ và kiểm chứng; không âm thầm thay bằng rule khi model lỗi.
11. Chỉ dùng class khi cần: schema Pydantic và repository là các chỗ hợp lý; logic nghiệp vụ chủ yếu là hàm.
12. Chạy kiểm tra phù hợp với thay đổi; phân biệt kiểm thử giả, model thật, kiểm tra code và thao tác trình duyệt.
13. Báo chính xác file đã sửa và phần chưa kiểm tra. Không khẳng định “hiểu mọi câu” chỉ từ vài câu smoke.

## 3. Chức năng hiện có và giới hạn

### Đang có

- Chào hỏi, tra cứu giá/thông tin sản phẩm theo dữ liệu.
- Tìm/gợi ý theo nhóm: bánh kem, bánh nhỏ, trà, cà phê; có nhóm tổng quát bánh/đồ uống.
- Lọc theo ngân sách, khoảng giá, giá chính xác, trên/dưới; hỗ trợ nhiều cách viết tiền.
- Lọc theo hương vị, mức ngọt, nhóm vị, kiểu cà phê khi nguồn có metadata.
- Hỏi giá và thuộc tính của nhiều sản phẩm; tách yêu cầu theo đối tượng.
- Tư vấn có lựa chọn nhanh và bỏ qua bước khách đã cung cấp.
- Xem thêm sản phẩm, tránh lặp những sản phẩm đã giới thiệu trong phạm vi lựa chọn đang xem.
- Gợi ý combo nhiều nhóm; tối đa ba combo khác nhau khi dữ liệu cho phép.
- Không có ngân sách: gợi ý các mức giá thấp/vừa/cao có thật, ít hơn ba nếu không đủ mức.
- Thiếu ngân sách: có thể đề xuất tối đa hai combo đúng điều kiện rẻ nhất và ghi số tiền cần thêm.
- Hiểu tên/alias và tham chiếu bằng ngữ cảnh; đối chiếu repository trước khi dùng ID.
- Chọn một/nhiều món qua câu tự nhiên hoặc nút trên thẻ.
- Form nhập thông tin, xem lại, sửa/hủy/xác nhận; ảnh sản phẩm và tổng tiền.
- Sau khi lưu yêu cầu, có thể bắt đầu yêu cầu mới; nhớ liên hệ, không tự chép ngày/lời chúc/ghi chú cũ sang yêu cầu mới.
- Lưu hội thoại, bản nháp, yêu cầu chờ tư vấn và ticket hỗ trợ local.
- Token phiên ràng buộc quyền xem/sửa hội thoại và yêu cầu.
- Widget thu gọn/mở rộng, khôi phục lịch sử qua chuyển trang trong cùng phiên.

### Không được mô tả như đã hoàn tất

- Chưa nối adapter tạo đơn chính thức của backend nhóm.
- Chưa xác nhận tồn kho kinh doanh thật; nguồn menu nhóm hiện trả `in_stock` mô phỏng theo yêu cầu trước.
- Chưa có chính sách cửa hàng thật trong cấu hình đang dùng.
- Không có bằng chứng đủ để bảo đảm mọi cách diễn đạt đều được hiểu đúng.
- Chưa fine-tune/huấn luyện lại trọng số Qwen; few-shot là hướng dẫn trong prompt.
- Chưa có email/Gmail, n8n, PDF gửi khách hoặc quy trình cửa hàng xác nhận qua email. Các phần này mới được thảo luận.
- Không tích hợp thanh toán/vận chuyển thật, tài khoản production, trang quản trị đầy đủ, triển khai thường trực.
- Giai đoạn đánh giá tổng thể toàn hệ thống chưa được coi là hoàn tất chỉ vì các smoke đã đạt.

## 4. Công nghệ và dependency

- Python 3.12.10; `sqlite3`, `urllib.request`, `pathlib`, `unittest` từ thư viện chuẩn.
- FastAPI cho HTTP API, Uvicorn chạy server.
- Pydantic v2 cho request/response/schema LLM/nguồn dữ liệu.
- SQLite; không ORM/SQLAlchemy trong bản này.
- HTML/CSS/JavaScript thuần; không React, không streaming token ở giao diện.
- Ollama HTTP local; không LangChain, framework agent, Redis, Celery hoặc microservices.
- Cloudflared là chương trình ngoài tùy chọn để chia sẻ link; không nằm trong dependency pip.

`requirements.txt` đang ghim: pydantic 2.11.9, fastapi 0.142.2, starlette 1.7.0, uvicorn 0.53.0, tzdata 2026.4.
`requirements-dev.txt` chỉ tham chiếu requirements.txt.

**Chênh lệch đã phát hiện khi đọc môi trường ngày 02/11:** .venv đang có **pydantic 2.14.0**, khác pin 2.11.9; các bản FastAPI/Starlette/Uvicorn nêu trên khớp. Không tự hạ/nâng dependency trong nhiệm vụ chỉ lập tài liệu này. Chưa xác minh cài sạch từ các pin cho toàn bộ kiểm thử.

Script API test dùng `fastapi.testclient` và cần HTTP client phù hợp. .venv hiện có `httpx 0.28.1`, chưa có `httpx2`, trong khi httpx chưa được liệt kê trực tiếp trong requirements. Đã thấy cảnh báo deprecation từ Starlette khi chạy test. AI sau cần kiểm tra điều kiện này nếu tái tạo môi trường; không gọi lỗi thiếu thư viện test là lỗi chatbot.

## 5. Cấu trúc thư mục và trách nhiệm file

```text
chatbot/
├── run_web.py
├── run_tunnel.py
├── README.md
├── README___.MD                 # file bàn giao này
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── api.py
│   ├── conversation.py
│   ├── llm_client.py
│   ├── schemas.py
│   ├── text_utils.py
│   ├── order_nlu.py
│   ├── advice.py
│   ├── checkout.py
│   ├── order_flow.py
│   ├── order_service.py
│   ├── handoff.py
│   ├── storage.py
│   ├── knowledge_loader.py
│   ├── retrieval.py
│   ├── chatbot.py
│   ├── nlu.py
│   └── repositories/
│       ├── __init__.py
│       ├── catalog.py
│       ├── group_catalog.py
│       ├── local_catalog.py
│       ├── mock_catalog.py
│       └── empty_catalog.py
├── data/
│   ├── README.md
│   ├── recommendation_profiles.json
│   ├── nlu_few_shots.json
│   ├── sample_policies.json
│   ├── schema_v2.sql
│   ├── local_demo_seed.json
│   ├── mock_catalog.json
│   └── mock_order_metadata.json
├── evaluation/
│   ├── README.md
│   ├── intent_context_dev.json
│   ├── intent_context_test.json
│   └── retrieval_dev.json
├── scripts/
│   ├── __init__.py
│   ├── check_checkout.py
│   ├── check_context_scope.py
│   ├── check_group_data.py
│   ├── check_rag.py
│   ├── prepare_intent_dataset.py
│   ├── evaluate_intent_context.py
│   ├── compare_intent_context.py
│   ├── evaluate_retrieval.py
│   ├── build_index.py
│   └── database.py
├── static/
│   ├── index.html
│   ├── style.css
│   └── chat.js
└── runtime/                    # DB/binary/index/report sinh lúc chạy; không đưa lên Git
```

- `config.py`: nạp riêng chatbot/.env, biến môi trường ưu tiên, kiểm tra giá trị, giải đường dẫn tương đối từ project.
- `api.py`: tạo app, xác thực phiên, mở connection, giữ lock, gọi service, validate response; không viết lại logic hiểu câu.
- `conversation.py`: controller chính; tách phạm vi hỏi/đặt, xử lý tiếp nối, trả lời thông tin trước hành động, lưu lượt chat.
- `llm_client.py`: HTTP Ollama, chọn model đã cài, schema, prompt, few-shot, validate và retry có giới hạn.
- `schemas.py`: Product/filters, LLMWireTurn/LLMTurn, requests, reference, bundle budget, kiểu kết quả; chuẩn hóa nhãn vị tương đương.
- `text_utils.py`: Unicode/tiền/viết tắt/nhóm sản phẩm và bằng chứng sở thích dùng chung.
- `order_nlu.py`: đối chiếu mention/reference với repository, chuẩn hóa proposal và kiểm chứng thông tin trích xuất; không tự tạo đơn.
- `advice.py`: tư vấn từng bước, lựa chọn nhanh, xem thêm và thuật toán combo.
- `checkout.py`: form web, tính tiền từ server, revision/token xác nhận, nhớ liên hệ.
- `order_flow.py`: FSM, trường còn thiếu, update/review/confirm/cancel/handoff.
- `order_service.py`: factory các tools, kiểm tra/báo giá/lưu yêu cầu, nhánh demo local, quyền tra cứu.
- `handoff.py`: lý do/tóm tắt và ticket local; không tự thông báo nhân viên bên ngoài đã nhận.
- `storage.py`: sqlite3, migration/backup, ghi/đọc conversation/messages/draft/submission/ticket, chống trùng.
- `knowledge_loader.py`: interface `get_knowledge()` và các nguồn empty/sample/local.
- `retrieval.py`: keyword retrieval, tùy chọn vector, kiểm chứng câu/nguồn RAG.
- `chatbot.py` và `nlu.py`: nhánh rule còn dùng khi chọn chủ động; không phải controller Qwen chính, không xóa tùy tiện.
- `static/`: toàn bộ giao diện chat, card/combo/form; không chứa nguồn giá chuẩn.
- `evaluation/`: dữ liệu có nhãn; không phải module runtime và không dùng toàn bộ làm prompt.
- `scripts/`: kiểm tra/evaluate/quản lý dữ liệu; tên prepare_intent_dataset hiện chỉ kiểm tra nhãn, không tự huấn luyện/generate lại dataset.

## 6. Cấu hình hiện tại, mặc định và những chỗ dễ hiểu nhầm

Snapshot các giá trị không bí mật đã đọc từ config khi lập tài liệu:

```text
Python=3.12.10
DATA_SOURCE=group_files
CHAT_MODE=ollama
OLLAMA_MODEL=qwen3.5:4b
ORDER_PROVIDER=local_demo
KNOWLEDGE_MODE=empty
RETRIEVAL_MODE=keyword
CONTEXT_MAX_TURNS=6
OLLAMA_TIMEOUT_SECONDS=60
OLLAMA_KEEP_ALIVE_SECONDS=900
```

`.env.example` khuyến nghị `ORDER_PROVIDER=unsupported` cho menu nhóm, trong khi giá trị resolve ở máy kiểm tra là `local_demo`. **Không sửa âm thầm để đồng nhất**. Dù biến này là local_demo, GroupCatalogRepository hiện báo `can_create_demo_orders=False` và `can_accept_real_orders=False`; nguồn nhóm vẫn chỉ cho yêu cầu chờ tư vấn.

Các tên cấu hình khác:
- `GROUP_CATALOG_PATH=../static/products.json`.
- `DATABASE_PATH=runtime/chatbot.sqlite3`, `TIMEZONE=Asia/Ho_Chi_Minh`.
- `OLLAMA_BASE_URL=http://127.0.0.1:11434`.
- `KNOWLEDGE_PATH=data/sample_policies.json`.
- `RETRIEVAL_TOP_K=3`, `RETRIEVAL_MIN_SCORE=0.15`.
- `EMBEDDING_MODEL=` rỗng; `VECTOR_INDEX_PATH=runtime/policy_vectors.json`; `VECTOR_MIN_SCORE=0.5`.
- `CHAT_DEBUG=false`; timing debug chỉ nên chứa chỉ số, không prompt/PII.
- `CATALOG_MODE` và `CHATBOT_DB_PATH` là tên cũ còn tương thích.

Config chấp nhận nguồn `empty/mock/local_demo/group_files`. Giá trị `backend` chưa có adapter và bị từ chối. `CHAT_MODE` là `ollama/rule`. Không tự đổi sang rule khi Ollama lỗi.

## 7. Nguồn sản phẩm, phân nhóm và metadata

Catalog Protocol trong `app/repositories/catalog.py`:
```python
search_products(filters)
get_product(product_id)
get_capabilities()
```

Các kết quả phân biệt `unconfigured/no_results/success/error`; không dùng list rỗng thay mọi trạng thái.

- `GroupCatalogRepository`: adapter chỉ đọc menu nhóm; category nguồn cake/mini/drink được ánh xạ sang cream_cake/mini/tea/coffee/drink.
- `LocalCatalogRepository`: đọc SQLite demo, có thể dùng chung connection cho transaction.
- `MockCatalogRepository`: bộ mock nhỏ phục vụ nhánh cũ và kiểm tra.
- `EmptyCatalogRepository`: chưa có nguồn; không giả vờ cửa hàng hết hàng.

Product có ID/tên/alias/nhóm/mô tả/flavor/variants/allergen/customization/lead time/source/is_mock; có thêm metadata tư vấn/ảnh tùy adapter.
Variant có ID, size, giá VNĐ nguyên, servings, stock_status; null nghĩa chưa có thông tin, không dùng giá 0 làm sentinel.
Nguồn nhóm tạo một variant `<product_id>:listed`, `size=None`, `servings=None`, tồn kho mô phỏng in_stock; không tự thêm nhiều size.

Các loại nội bộ: `cream_cake, mini, tea, coffee`; `cake` bao gồm bánh, `drink` bao gồm đồ uống.
- `sweetness`: high/ngọt nhiều, medium/ngọt vừa, low/ít ngọt, sweet/ngọt chung.
- `taste_family`: fruit, chocolate, cream, milk_tea, fruit_tea, matcha, vanilla, coffee_cream.
- `coffee_style`: strong/đậm đắng, creamy/béo mặn dễ uống, mild/dịu ít đắng.
- Vị cụ thể như dâu dùng `flavor`; không tự suy thành phần/allergen từ mô tả vị.
- Với combo, bare “ngọt” dùng sweet, lọc medium hoặc high; không mặc định high.
- Alias/tên được lấy từ repository; không hardcode toàn menu/giá vào NLU hoặc system prompt.
- `recommendation_profiles.json` là phân loại mô phỏng theo thông tin người dùng; không phải xác nhận dinh dưỡng hoặc độ an toàn dị ứng.
- Nguồn nhóm không hỗ trợ xác minh size, số người ăn, dịp hay loại trừ allergen; không bỏ qua điều kiện an toàn để đề xuất.

Phụ thuộc bên ngoài chatbot:
- `../static/products.json` là menu đọc thực tế, không phải tự mặc định đọc products.js.
- `../static/` được mount thành `/website/` nếu tồn tại; ảnh và trang sản phẩm cần giữ đúng URL.
- Widget của website có phần tích hợp ngoài chatbot; không sửa chúng nếu nhiệm vụ không cho phép.
- Khi chuyển chỉ folder chatbot sang máy khác, cần chia sẻ kèm nguồn menu/website phụ thuộc hoặc cấu hình adapter khác rõ ràng. Không có file ngoài không được giả báo group_files thành công.

## 8. Đường đi của một tin nhắn

```text
static/chat.js
→ POST /api/chat + Bearer session token
→ api.authorize + kiểm tra conversation_id + lock phiên
→ load_conversation(SQLite)
→ conversation.handle_message
→ llm_client.build_turn_messages
→ Qwen /api/chat trả JSON theo schema
→ Pydantic + normalize + check_turn_grounding/check_catalog_grounding
→ resolve_message_scopes: tách hỏi thông tin và sửa đơn
→ repository / advice / RAG trả thông tin
→ FSM + tools thực hiện hành động hợp lệ nếu có
→ finish_turn + lưu transaction
→ api.make_chat_view
→ JS render text/card/combo/form
```

Các endpoint form không cần gọi Qwen để hiểu lại thao tác nút bấm. Giá, tiền, quyền truy cập và thao tác ghi do Python kiểm soát.
Câu có cả hỏi giá và đặt món phải trả phần thông tin trước; không bỏ câu hỏi chỉ vì thấy ý định đặt.
Hiện giới hạn tối đa **4 request thông tin và 4 loại information intent** mỗi tin; vượt giới hạn có thông báo chia tin, không âm thầm bỏ ý.
Giới hạn tin API **2000 ký tự** là giới hạn kỹ thuật, không phải chính sách cửa hàng.
Câu trả lời giá/combo phần lớn được Python dựng từ dữ liệu; không gọi thêm LLM tự do để viết lại mọi câu trả lời.

## 9. Qwen, prompt và schema: những gì cần giữ

- Model hiện cấu hình `qwen3.5:4b`; chọn theo tên đã cài, không tự pull model/cloud.
- Chat HTTP dùng Python urllib, kiểm tra endpoint local/status/timeout/model/response.
- Request thực: `think=False`, `stream=False`, `temperature=0`, `presence_penalty=0`, `num_ctx=4096`, `num_predict=768`, `keep_alive` theo config.
- `think=False` **đã có**; không mặc định coi thiếu tham số này là nguyên nhân lỗi. Nó không bảo đảm hiểu đúng.
- Đọc `message.content`; phần thinking nếu có là trường khác.
- `format` nhận JSON schema từ Pydantic, có các nhánh thông tin/đặt hàng/combo.
- `LLMWireTurn` dùng updates dạng list `[{field,value}]` trên HTTP; sau parse đổi sang `LLMTurn` với updates có cấu trúc.
- Model chỉ trích delta của lượt hiện tại. Không đề cập = giữ thông tin cũ; xóa dùng `clear_slots` rõ ràng.
- Model không được tự phát minh product_id; tên là mention, repository mới xác minh.
- `build_turn_messages` chọn tối đa hai few-shot từ 314 mẫu; thường một mẫu đúng cấu trúc combo.
- Ngữ cảnh gửi model là tóm tắt có cấu trúc, không toàn bộ lịch sử/raw token/contact/card.
- Version prompt/dataset ví dụ hiện tại: `intent-context-v67-compositional-preferences`.
- JSON/grounding sai được sửa tối đa **một lần**, dùng chung deadline. Retry giữ output trước để sửa phần sai, bỏ few-shot ở lượt sửa.
- Nếu đã xác minh thiếu ngân sách CHUNG, schema repair buộc `bundle_budget`; không áp điều này cho hai giới hạn giá riêng.
- Lỗi cuối: không thực hiện ghi đơn, giữ trạng thái hợp lệ trước đó; không âm thầm fallback rule.
- Pydantic kiểm tra cấu trúc/kiểu; grounding kiểm tra nội dung dựa câu khách. Hai việc khác nhau, cả hai có thể cần sửa nếu contract thiếu hợp lý.
- Không tăng context hoặc nạp tất cả few-shot theo cảm tính; cần đo prompt, latency và chất lượng trên câu chưa thấy.

Ví dụ JSON tối giản cho “bánh nhỏ và cà phê đắng trong giá 86k”:
```json
{
  "bundle_budget": {"question": "trong giá 86k", "budget_vnd": 86000, "price_inclusive": true},
  "intents": ["recommendation"],
  "requests": [
    {"intents": ["recommendation"], "product_mentions": [], "question": "bánh nhỏ",
     "quantity": 1, "search_scope": "new", "filters": {"product_type": "mini", "flavor": null}},
    {"intents": ["recommendation"], "product_mentions": [], "question": "cà phê đắng",
     "quantity": 1, "search_scope": "new",
     "filters": {"product_type": "coffee", "flavor": null, "coffee_style": "strong"}}
  ]
}
```

Không ép mọi default field xuất trong mọi JSON nếu HTTP schema đã có cách rút gọn.

## 10. Ngữ cảnh và chống trộn sản phẩm

Phải phân biệt:
1. `current_turn/current_request`: câu hỏi/đối tượng ở lượt hiện tại.
2. `discussion_context`, choices và nhu cầu: thông tin để hiểu tiếp nối.
3. `order`: bản nháp muốn đặt, không phải danh sách sản phẩm luôn đưa vào truy vấn.

Các vùng khác: `needs`, `product_choices`, `pending_information_request`, `pending_order_request`, `advice_pending`, `bundle_context`, `checkout_contact`.
`request_memory` lưu thứ tự yêu cầu, tối đa 8 mục; prompt lấy tóm tắt 4 mục gần đây. History ngắn mặc định 6 lượt, lưu riêng với slot có cấu trúc.

Quy tắc:
- “Đặt socola → bánh dâu giá bao nhiêu?” chỉ hỏi giá dâu; giữ nháp socola.
- “Bánh đó giá bao nhiêu?” dùng focus/choice khi rõ; mơ hồ thì hỏi lại.
- “Đổi bánh đang đặt sang dâu” mới là sửa đơn; kiểm tra lại dữ liệu phụ thuộc và bỏ REVIEW cũ.
- Hỏi rõ nhiều bánh thì trả đúng các bánh được hỏi.
- Câu tìm nhóm mới không tự mang ngân sách/vị của nhóm trước; câu “vẫn/giữ/như cũ” mới có căn cứ kế thừa.
- Không xóa lịch sử toàn phiên để chữa lỗi ngữ cảnh.
- Model lỗi không được lưu proposal sai làm context cho lượt sau.
- Sau khi lỗi, câu hợp lệ tiếp theo phải vẫn chạy được trong cùng phiên.
- Câu “món ít ngọt hơn” sau combo nhiều nhóm có thể chưa rõ đổi món nào; không tự đoán bánh thay cho trà.
- Không hiển thị form/REVIEW trở lại sau mọi câu tư vấn không liên quan.

## 11. Tư vấn và combo

`advice.recommend_bundles(repository, components, budget, data_mode, limit=3)`:
- Lọc riêng từng component theo group/vị/độ ngọt/điều kiện trước.
- Chỉ dùng giá variant có dữ liệu; tính tiền nguyên VNĐ bằng Python.
- Tổng = tổng đơn giá × số lượng từng món.
- Có ngân sách: tìm tối đa ba combo khác nhau, ưu tiên đa dạng; cắt sớm nhánh vượt trần bằng chi phí còn lại tối thiểu.
- Không ngân sách: thấp/giữa/cao có thật; ít phương án hơn nếu chỉ có ít mức giá.
- Không đủ ngân sách nhưng đủ món đúng điều kiện: tối đa hai tổ hợp rẻ nhất, ghi tiền cần thêm; không nới vị/allergen/số lượng để giả phù hợp.
- Dưới/trên nghiêm ngặt khác với không quá/ít nhất có lấy biên.
- “Trong giá/trong mức giá/trong tầm giá/khoảng giá X” là trần xấp xỉ theo quy tắc hiện có; giá đúng/cùng giá vẫn là exact.
- Ngân sách CHUNG khác giá riêng: “bánh dưới 400k và cà phê trên 40k” không tự biến thành combo tổng 400k.
- Các khung combo riêng, ảnh/tiền/số lượng, lời giải thích ngắn. Text xưng mình/bạn, gọi combo, kết bằng câu hỏi mở.
- Không tự gọi món bán chạy khi không có dữ liệu bán chạy.
- Nút xem thêm chỉ hiện khi còn sản phẩm chưa đưa trong lựa chọn hiện tại; không lặp đến vô hạn.
- Nút đặt món/combo gửi ID và số lượng tới checkout; server lấy lại giá, không tin giá client.

## 12. FSM, form, xác nhận và handoff

Trạng thái nội bộ: BROWSING, COLLECTING, REVIEW, DEMO_CONFIRMED, CANCELLED, HANDOFF.
Với group_files, bản lưu là `submissions.kind=waiting_consultation`; UI checkout có stage `form/review/completed/cancelled`. `completed` không có nghĩa là đơn kinh doanh được cửa hàng nhận.

`order_flow` quản lý draft_id, revision, slots, verification, review, submission; thay đổi nháp phải làm mất hiệu lực snapshot REVIEW.
`checkout` kiểm tra draft_id/revision/confirmation_token; có kiểm tra giá hiện tại trước gửi; không gửi đơn ngay khi khách vừa đổi thông tin.
“Đồng ý nhưng đổi...” là sửa, phải review lại.
Lặp xác nhận cùng request không tạo trùng nhờ idempotency và snapshot/hash.

Form hiện có fullName, phone, email tùy chọn, province, ward, addressLine, deliveryDate/deliverySlot tùy chọn, cakeMessage, note, consent và items.
- Backend kiểm tra tên, định dạng số di động VN, email khi có, consent, số lượng, ID và giới hạn kỹ thuật.
- Form hỗ trợ tối đa 20 dòng, số lượng từng dòng 1–99; khác với giới hạn 4 request NLU, không được trộn hai giới hạn.
- Chữ trên bánh chuẩn hóa NFC.
- Thông tin lịch nhận/lời chúc/ghi chú là yêu cầu khách, chưa được cửa hàng xác minh.
- Luồng chat nguồn nhóm không hỏi slot pickup_at/fulfillment/address; các trường cùng tên hoặc lịch trong form/legacy schema vẫn có thể tồn tại. Không xóa hàng loạt chỉ vì chúng không xuất hiện trong chat.
- Schema group không có size thật: đừng tái bắt khách chọn size/topping chỉ vì schema chung còn field.
- Giữ liên hệ cho yêu cầu tiếp theo; ngày/lời chúc/ghi chú không tự dùng lại.

Handoff: khách nhờ nhân viên, fallback liên tiếp, dị ứng nghiêm trọng, khiếu nại, yêu cầu sửa/hủy sau xác nhận hoặc nghiệp vụ chưa hỗ trợ. Ticket local có lý do và tóm tắt; không nói đã gửi cho người ngoài khi chỉ lưu SQLite.

Các tools từ `order_service.create_order_tools` gồm kiểm tra tình trạng, báo giá, gửi yêu cầu, tra cứu và tạo ticket; tên thực có `submit_order_request`, giữ theo factory hiện tại.
ToolStatus: `available/unavailable/unknown/unsupported/error`.
Local_demo có transaction + kiểm tra/trừ kho + snapshot/idempotency; nguồn group_files không được gọi nhánh này để xác nhận đơn thật.

## 13. RAG: code có sẵn, cấu hình hiện chưa có nguồn

KnowledgeRepository dùng `get_knowledge()`, tách khỏi catalog.
Nguồn empty không đọc chính sách mẫu; sample đọc JSON mô phỏng; local_demo đọc policies SQLite.
Mỗi điều khoản có ID/title/content/version/is_mock; một điều khoản là một chunk.
Keyword index dùng IDF/trùng từ và ưu tiên tiêu đề, tối đa 3 chunk; cache/index gắn hash nội dung/phiên bản.
Khi có nguồn, Qwen chọn source_id + sentence_ids; Python mở rộng thành trích đoạn nguyên văn và kiểm tra ID/phiên bản/câu hợp lệ.
Nguồn hợp lệ chưa chứng minh tài liệu trả lời đúng toàn bộ câu hỏi.
Không có nguồn phải báo thiếu thông tin; không dùng tri thức chung để bịa chính sách, giá, kho hoặc allergen.
Vector/embedding và cosine similarity có nhánh tùy chọn, chưa có model embedding cấu hình; không tự tải. `scripts/build_index.py` là công cụ tùy chọn, không phải điều kiện bắt đầu dùng keyword.

## 14. API, session và frontend

API chính:
- GET /health; GET /api/catalog.
- POST /api/conversations body {}.
- GET /api/conversations/{id}.
- POST /api/chat.
- POST /api/checkout/start; POST /api/checkout.
- GET /api/order-requests/{id}.
- GET / và /chatbot/ phục vụ UI; /static phục vụ tài nguyên chatbot; /website mount website nhóm.

Chat response: conversation_id, message, state, products, recommendation_groups, quick_replies, sources, data_mode, catalog_source, knowledge_mode, catalog_status, policy_status, requires_confirmation, review, request_id/demo_order_id, engine, errors, checkout, show_checkout.

Token ngẫu nhiên 256 bit, server chỉ giữ hash, TTL mặc định 8 giờ; registry session nằm trong RAM, có lock mỗi phiên. Không coi UUID là xác thực.
SQLite giữ nội dung qua restart nhưng registry token không tự tồn tại qua restart; đừng hứa phiên cũ luôn khôi phục sau khi server dừng.
Chỉ một worker trong launcher; nhiều worker/máy cần thiết kế session chung trước.
JS dùng sessionStorage theo tab và cùng origin; restore qua API có quyền. Không gửi token trên URL hoặc log.
Render text bằng textContent; kiểm tra đường dẫn ảnh/link. Form/ảnh/card phải vừa cả iframe nhỏ và khung lớn.
HTTP 200 chỉ cho biết API đã trả response, vẫn phải xem errors/engine để biết lượt chat có thành công.

Font: lần sửa giao diện gần nhất đổi heading tiếng Việt Georgia sang Segoe UI/Arial qua --font-ui và tăng line-height; index trỏ CSS `?v=font-20261101-v68`. Đây là version tài nguyên UI, khác version prompt v67. Nội dung HTML đã kiểm tra UTF-8/NFC; chưa kiểm tra trực quan trình duyệt ở lần sửa đó.

## 15. SQLite và dữ liệu riêng tư

`storage.open_storage` mở SQLite, bật foreign_keys, kiểm tra schema version; migration có bảo toàn/backup phù hợp.
Bảng có thể có: conversations, drafts, submissions, tickets; schema_v2 thêm database_metadata, products, product_variants, toppings, product_toppings, policies, business_settings, messages, orders, order_items và index.
Không được suy “bảng products tồn tại” thành “chatbot group_files đang lấy menu từ đó”.
Draft/conversation lưu payload JSON và revision. Submissions có idempotency_key UNIQUE, payload_hash và kind.
Đơn demo có snapshot, source/is_demo, unpaid và DEMO_CONFIRMED; không phải đơn thật.
Thông tin liên hệ có thể nằm trong payload form/draft; việc che history không biến toàn DB thành dữ liệu vô danh. **Không đưa DB khách lên AI/GitHub.**
`.gitignore` bỏ .venv, .env, cache, DB, log, runtime/; không dùng .venv như mã nguồn.
Khi sửa storage, kiểm tra cả quyền conversation và transaction; không commit đơn tách rời rồi quên lưu trạng thái hội thoại.

## 16. Chạy trên Windows

Chạy trong đúng thư mục chatbot. Dùng interpreter bên trong .venv để không phụ thuộc activation.

```powershell
cd "D:\sweet-bakery-nhom6\chatbot"
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -X utf8 run_web.py
```

Launcher in `http://127.0.0.1:8000/website/`. Chat riêng: `http://127.0.0.1:8000/chatbot/` hoặc `/`.
Host hiện bind `127.0.0.1`, không tự truy cập LAN bằng IP nếu chưa đổi cách bind.
Prewarm mặc định bật, chạy thread nền; không cần thêm --prewarm mỗi lần. Có --no-prewarm, --port 8001, --chat-mode rule cho chẩn đoán chủ động.
Đổi Python cần Ctrl+C và chạy lại server; F5 không nạp Python. Đổi CSS/JS có thể cần Ctrl+F5.

Máy mới, chỉ khi chưa có .venv:
```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```
Kiểm tra bản Python thực tế nếu cần đúng 3.12.10; selector -3.12 không bảo đảm patch .10. Không ghi đè .env đã có.
VS Code: Python: Select Interpreter → .venv\Scripts\python.exe.
Không sao chép nguyên .venv giữa máy; cài lại từ dependency và đối chiếu phần chênh lệch phiên bản ở trên.

Kiểm tra Ollama (không tải model):
```powershell
ollama --version
ollama list
ollama ps
Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags"
```
Nếu Ollama chưa chạy, mở dịch vụ/app hoặc dùng ollama serve ở terminal riêng. Không chạy serve thứ hai nếu cổng đã có dịch vụ.
Web lên không chứng minh model đã sẵn sàng. Prewarm chỉ nạp model đã cài; dừng web không nhất thiết dừng Ollama/giải phóng model ngay.

Tunnel tùy chọn:
```powershell
.\.venv\Scripts\python.exe -X utf8 run_tunnel.py
```
Cần cloudflared sẵn trong runtime hoặc PATH. Script tự chạy run_web nếu cần, hoặc dùng server có sẵn; in link https://...trycloudflare.com/website/.
Link quick tunnel có thể đổi; máy chạy web/Ollama/tunnel phải bật và có mạng. Tunnel không biến máy tắt thành dịch vụ luôn hoạt động.
Không chạy tunnel tự động chỉ để kiểm tra tài liệu hoặc test logic.

## 17. Database: lệnh công cụ và mức tác động

Nguồn group_files không cần seed menu SQLite để đọc 24 sản phẩm.
`scripts.database` có init/seed/check/reset/classify-flavors.
Ví dụ khởi tạo/check trên file đã chọn rõ:
```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.database init --database runtime/demo_sandbox.sqlite3
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.database seed --database runtime/demo_sandbox.sqlite3
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.database check --database runtime/demo_sandbox.sqlite3
```
Các lệnh init/check mở storage có thể tạo/migrate file; không gọi là thao tác read-only hoàn toàn.
Seed demo có cơ chế không nhân đôi/không ghi đè tồn kho đã thay đổi. Không tự seed vào DB khách.
`classify-flavors` là thao tác ghi metadata, không tự chạy để “chỉ xem phân loại”.
Reset là thao tác riêng, chỉ trên demo đã xác minh, cần cờ xác nhận và có thể xóa hội thoại/đơn demo trong file đó:
```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.database reset --database runtime/demo_sandbox.sqlite3 --confirm
```
Không thực thi reset trong nhiệm vụ bình thường; không xóa file SQLite bằng Remove-Item để chữa lỗi.

## 18. Kiểm thử, số liệu và lệnh

Không có tests/; dùng script hiện có. Các lệnh dưới chạy từ chatbot:
```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest -q scripts.check_checkout
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.check_context_scope
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.check_group_data
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.check_rag
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.prepare_intent_dataset
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --engine fake --split dev
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --engine fake --split test
```

Qwen thật, chọn ít ca đúng lỗi đang sửa; không chạy toàn bộ vô cớ:
```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --engine ollama --dialogue dev_combo_coffee_preferences_v67
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --engine ollama --dialogue dev_within_price_combo_v66
```
Các tên dialogue khác hữu ích: dev_combo_budget_collecting_v65, dev_combo_budget_pending_v65.
Evaluator dùng SQLite RAM và mặc định không ghi báo cáo. Nếu yêu cầu --output, chỉ cho runtime/*.json.
`compare_intent_context.py` dùng so sánh report; xem --help trước khi truyền tham số.
Retrieval: `python -m scripts.evaluate_retrieval` đo truy xuất, không phải độ đúng toàn bộ câu trả lời LLM.
Không đưa nhãn test cuối vào prompt/few-shot. Fake inject nhãn để đo controller, **không đo khả năng hiểu Qwen**.

Kết quả lịch sử đã chạy ngày 01/11/2026, không phải được chạy lại ngày lập tài liệu:
- 96/96 kiểm tra check_checkout.
- 536/536 dev fake, 60/60 test fake; 314 few-shot hợp lệ.
- 4/4 câu Qwen thật ở dialogue v67 đạt cả nhãn và hành vi: 24,73 / 12,68 / 13,27 / 14,84 giây, một inference/câu.
- Thêm hai lượt API/Qwen với bản nháp thiết lập bằng fake: đúng hai câu 80k/86k, HTTP 200, combo 80k, draft không đổi, không ghi đơn; 12,07 / 11,81 giây.
- V66: 6/6 hành vi, 4/6 extraction_exact, khoảng 13,17–14,57 giây.
- Không gộp smoke chồng lấn để tuyên bố độ chính xác toàn chatbot. Chưa chạy Qwen toàn bộ 596 lượt hiện tại.
- Ngày lập tài liệu chỉ đọc config/count/cú pháp cấu trúc/catalog an toàn; không gọi Qwen mới, không chạy full test, không kiểm tra thủ công browser/tunnel.

## 19. Lỗi thường gặp và quy trình chẩn đoán

Câu `Chưa xử lý được lượt này. Bạn có thể thử lại.` là fallback của `conversation.failed_turn` cho mã chưa có thông báo riêng.
Mã cụ thể nằm trong response `errors`; `engine=llm_error` có thể là lỗi grounding, không nhất thiết lỗi dịch vụ model.
Timeout, model không thấy, lỗi kết nối, output_truncated, JSON sai có một số thông báo riêng.
Không tìm thấy sản phẩm hợp lệ phải là no_results, không nên giả làm lỗi model.
Chưa có chính sách là empty/insufficient, không tự bịa chính sách.

Cách đọc lỗi web: F12 → Network → POST /api/chat → Response → errors/engine/catalog_status.
So ba thứ: **câu hiện tại → JSON Qwen thực trả → quy tắc Python chặn**. Chỉ in synthetic data khi trace, không log contact/token thật.

Mã hay gặp:
- invalid_turn_json: Pydantic/schema không hợp lệ.
- invalid_prompt_examples: lỗi đọc/xây ví dụ prompt.
- missing_catalog_group_request: thiếu một nhóm món.
- missing_bundle_budget/missing_budget_constraint: thiếu ngân sách.
- budget_direction_mismatch: sai hướng/biên hoặc giá exact nhầm.
- missing_coffee_preference/missing_taste_preference/missing_advice_preference: bỏ điều kiện.
- ungrounded_advice_preference/ungrounded_number/invalid_turn_mention: thông tin không có căn cứ.
- missing_new_search_scope/conflicting_continuation/no_pending_order: ngữ cảnh hoặc tiếp nối.
- source_error/storage_error: nguồn hoặc SQLite; không đổ hết cho Qwen.

Các lỗi đã sửa, cần giữ hồi quy:
- Đặt socola rồi hỏi dâu: không gộp cả hai vào câu hỏi giá.
- Câu tìm nhóm mới không giữ trần giá/hương vị cũ.
- “Trong giá 70k” không bị hiểu thành đúng 70k.
- Hai/ba nhóm có vị riêng không gộp hoặc truyền vị sang nhau.
- Model ghi flavor=strong ở coffee: schema chuyển sang coffee_style khi tương đương, vẫn bác xung đột.
- Few-shot chọn mẫu chỉ có nhóm mà bỏ điều kiện cà phê/vị: ranking hiện xét cả sweetness/taste_family/coffee_style/flavor.
- Lượt model lỗi không làm câu tiếp theo tiếp tục sai do trạng thái bị ghi hỏng.
- Tư vấn không liên quan không tự bật lại form.
- REVIEW thay đổi phải xác nhận lại; xác nhận lặp không lưu trùng.
- Không “sửa” bằng cách gỡ toàn bộ validator hoặc bắt mọi khách phải dùng một câu cố định.

## 20. Câu kiểm tra mẫu và kỳ vọng

- “gợi ý cho tôi bánh”: hỏi hai lựa chọn bánh kem/bánh nhỏ nếu chưa có điều kiện rõ.
- “bánh kem dưới 400k và cà phê trên 40k”: hai giới hạn giá riêng, không áp 400k như tổng.
- “cho tôi bánh kem, trà ngọt vừa và cà phê nhé bạn”: combo không ngân sách, các mức giá thực.
- “bánh kem ngọt nhiều, trà ngọt vừa trong tầm giá 400k”: Choco ngọc trai + trà sữa là một phương án 385k theo menu hiện tại.
- “cho tôi combo bánh nhỏ và trà ngọt trong giá 70k nhé”: có combo 60k, còn dư 10k; ngọt chỉ áp cho trà.
- “đề xuất cho tôi bánh nhỏ và cà phê đắng trong giá 80k nhé”: combo 80k, cà phê đen.
- “đề xuất cho tôi bánh nhỏ, cà phê đắng trong giá 86k nhé”: combo 80k, còn dư 6k.
- “gợi ý bánh nhỏ vị vani và cà phê béo mặn nhẹ trong giá 90k”: vani + cà phê muối, 80k.
- “đề xuất bánh kem trái cây ít ngọt với trà ngọt vừa trong giá 400k”: giữ đúng cả vị và hai mức ngọt, có phương án 375k.
- “combo bánh nhỏ và trà ngọt trong giá 55k”: thông báo thiếu tiền, phương án tối thiểu 60k cần thêm 5k.
- “đặt 2 bánh cuộn vani” → hỏi giá bánh khác → quay lại yêu cầu: draft không tự đổi.
- Sau một lỗi model, gửi lại câu hợp lệ ở cùng phiên phải có khả năng thành công.
- Hai session không xem/sửa yêu cầu của nhau.
Đây là kỳ vọng gắn với menu hiện tại; nếu menu thay đổi, cập nhật kỳ vọng theo nguồn được xác minh.

## 21. Hướng cải thiện tiếp theo, không tự làm khi chưa có nhiệm vụ

Ưu tiên chất lượng NLU và chẩn đoán thay vì tiếp tục thêm mẫu theo từng câu:
1. Phân nhóm lỗi model/schema/grounding/context/repository; thu thập raw output bằng dữ liệu thử.
2. Rút gọn schema/prompt đúng chỗ; cân nhắc chuẩn hóa nhãn tương đương nhưng không gán slot không được nói.
3. Bộ chọn few-shot cần xét điều kiện gắn với từng đối tượng, tránh ví dụ ngược độ ngọt/kiểu cà phê.
4. Đánh giá các cách nói chưa đưa vào mẫu; tách development và test cuối.
5. So độ đúng + số lần model gọi + thời gian; thử cùng điều kiện máy, phân biệt nạp model với lượt ấm.
6. Không tăng num_ctx hoặc đổi model trước khi có số đo và sự đồng ý.

Khi có backend nhóm:
- Thêm adapter thực theo interface hiện có; mapping ID/variant, nguồn giá/kho chuẩn.
- Tool tạo/tra đơn cần quyền và idempotency xuyên hệ thống; chỉ đọc menu không tự được tạo đơn.
- Chọn một hệ thống ghi đơn chuẩn; không ghi cùng đơn vào SQLite demo và backend thật.
- Không chuyển submission/demo_order cũ thành đơn thật.
- Chạy lại hồi quy session, transaction, REVIEW, nhiều món, lỗi nguồn và context.

Ý tưởng đã bàn nhưng CHƯA làm:
- Gmail gửi chi tiết yêu cầu cho khách và thông báo cho cửa hàng sau lưu thành công.
- n8n/webhook hoặc background task có trạng thái chờ/gửi/lỗi và chống trùng.
- Email “đã nhận yêu cầu” khác “cửa hàng đã xác nhận đơn”; không gửi xác nhận thật trước nguồn có quyền.
- Voice, CI tự chạy kiểm thử, tự động cập nhật tri thức.
Không tự cài n8n, tạo tài khoản, gửi email, thêm API key hoặc thay kiến trúc chỉ vì đọc mục này.

## 22. Đưa dự án cho AI khác như thế nào

### Nếu AI có quyền đọc workspace

Đưa file này trước, yêu cầu nó xác nhận đúng thư mục, đọc code liên quan và nêu khác biệt giữa tài liệu/code trước khi sửa.
Thứ tự đọc gợi ý:
1. README___.MD → README.md → evaluation/README.md.
2. app/config.py → app/schemas.py → app/llm_client.py → data/nlu_few_shots.json.
3. app/conversation.py → app/order_nlu.py → app/advice.py.
4. app/repositories/catalog.py + app/repositories/group_catalog.py; data/recommendation_profiles.json.
5. app/checkout.py → order_flow.py → order_service.py → storage.py.
6. knowledge_loader.py/retrieval.py → api.py → static/chat.js, static/style.css, static/index.html.
7. scripts/check_checkout.py, evaluate_intent_context.py và dataset phù hợp lỗi.

### Nếu AI chỉ nhận file đính kèm

Chỉ một README giúp hiểu bối cảnh, **không đủ để sửa chính xác code**.
Gửi kèm source chatbot (app/, static/, data/, evaluation/, scripts/, launchers, requirements, .env.example, README) và menu/ảnh/trang ngoài cần thiết nếu có quyền chia sẻ.
Không gửi .env, .venv, runtime database/log/report thật, cache, token hoặc dữ liệu khách. Ghi rõ nếu bản chia sẻ bị thiếu menu ngoài.
Nếu giới hạn file: bắt đầu từ config/schemas/llm_client/conversation/order_nlu/advice và các mẫu liên quan; thêm API/checkout khi lỗi ở form, repository khi lỗi dữ liệu.

### Prompt mở đầu có thể copy

> Hãy đọc README___.MD trước, rồi kiểm tra implementation thực tế của chatbot.
> Đây là dự án Python/FastAPI + Qwen qua Ollama, source menu group_files, SQLite lưu hội thoại/yêu cầu.
> Mặc định chỉ sửa trong thư mục chatbot đang dùng, không tạo lại tests/docs, không sửa file nhóm bên ngoài nếu tôi chưa cho phép.
> Không tự tải/đổi model, dùng dịch vụ mất phí, reset DB, gửi email hoặc triển khai.
> Giữ Qwen hiểu câu, Python kiểm chứng và kiểm soát nghiệp vụ; không viết lại dự án hoặc bỏ validator để né lỗi.
> Trước khi sửa, đối chiếu câu khách → JSON model → grounding → truy vấn → FSM → response; phân biệt lỗi ở từng bước.
> Dùng DB RAM và fake cho hồi quy, chỉ thử vài câu Qwen thật liên quan khi cần.
> Số liệu fake không phải độ chính xác model. Báo file sửa, kết quả thật và giới hạn.
> Nhiệm vụ cụ thể của tôi là: [điền yêu cầu hoặc câu lỗi].
> Ví dụ lỗi và kết quả mong đợi: [điền].
