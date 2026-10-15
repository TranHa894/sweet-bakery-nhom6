# Chatbot Sweet Bakery

Python **3.12.10**, Qwen **qwen3.5:4b** qua Ollama local, FastAPI và SQLite. CLI và giao diện web gọi chung service chatbot; không cần API key, không thanh toán/giao hàng thật.

Mặc định đọc **24 sản phẩm mẫu** của nhóm từ `../static/products.json` bằng adapter chỉ đọc. Đây chưa phải menu kinh doanh chính thức. Chatbot chỉ lưu **yêu cầu chờ tư vấn**, chưa xác nhận đơn từ nguồn này.

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
$env:OLLAMA_BASE_URL = 'http://localhost:11434'
$env:OLLAMA_MODEL = 'qwen3.5:4b'
$env:OLLAMA_TIMEOUT_SECONDS = '60'
ollama list
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.check_group_data
.\.venv\Scripts\python.exe -B -X utf8 run_web.py
```

Mở **http://127.0.0.1:8000/**. Website nhóm được phục vụ chỉ đọc tại `/website/`; danh mục chatbot ở `/api/catalog`, trạng thái ở `/health`. Dừng bằng Ctrl+C; có thể chạy `run_web.py --port 8001` nếu cổng bận.

Nếu chưa có môi trường ảo: `py -3.12 -m venv .venv`, rồi cài requirements như trên. Môi trường ảo tách thư viện dự án khỏi Python hệ thống; không đưa `.venv` vào Git. Trong VS Code chọn **Python: Select Interpreter → .venv/Scripts/python.exe**.

Chương trình đọc `chatbot/.env` nếu có; biến môi trường PowerShell ưu tiên hơn. `.env.example` là mẫu công khai. Không ghi khóa dịch vụ hoặc dữ liệu cá nhân thật vào code/log.

Ollama phải chạy và model phải đã cài. Nếu dịch vụ chưa chạy, mở terminal khác và dùng `ollama serve`. Không chạy thêm server Ollama khi ứng dụng Ollama đã phục vụ cổng 11434. Project không tự tải hay đổi model; `ollama list` phải có đúng tên đang cấu hình.

## Terminal và xem bản ghi

Giữ các biến môi trường ở trên, thay lệnh chạy web bằng:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 main.py
```

| Lệnh CLI | Công dụng |
| --- | --- |
| `/new` | Bắt đầu hội thoại riêng; không xóa dữ liệu đã lưu. |
| `/exit` | Kết thúc chương trình. |
| `/draft` | Xem bản nháp, các món và trạng thái hiện tại. |
| `/orders` | Xem bản ghi thuộc phiên hiện tại, gồm yêu cầu chờ tư vấn. |
| `/order ID` | Tra một bản ghi thuộc phiên hiện tại. |
| `/resume CONVERSATION_ID` | Nạp hội thoại thử nghiệm đã lưu sau khi khởi động lại. |

Lệnh quản lý CLI không gửi model. `/resume` là tiện ích local, không phải đăng nhập production. API dùng token phiên ngẫu nhiên; biết conversation_id/order_id không đủ quyền xem dữ liệu của người khác.

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

`LLMWireTurn` là schema JSON gửi/nhận qua HTTP. **order_items bắt buộc có trong output**: `[]` nếu không chọn món; mỗi lựa chọn có product_mention hoặc reference và quantity riêng. Mention chỉ là tên khách nói, repository mới xác minh product_id.

Update là phần thay đổi của lượt hiện tại; null/không đề cập không xóa slot cũ, xóa dùng clear_slots. Cộng/bớt món được code áp dụng đúng thao tác và kiểm tra số lượng; không tự lấy số loại bánh làm số chiếc mỗi loại.

Few-shot là ví dụ hướng dẫn trong prompt, không phải huấn luyện lại. Hiện có **64 ví dụ, version v18**; mỗi lượt chọn tối đa **2 ví dụ liên quan**, không đưa đáp án evaluation vào prompt. Ví dụ được sắp theo thứ tự field của schema HTTP; kiểm tra regex chỉ kiểm chứng/chuẩn hóa, Qwen vẫn là bộ hiểu ngôn ngữ chính. Code kiểm tra delta do model trích trước khi bổ sung thông tin ngữ cảnh đã xác minh; dữ liệu cũ không bị coi là model bịa thêm vào câu mới. Structured output (đầu ra có cấu trúc) giới hạn dạng JSON, còn ý nghĩa và căn cứ phải kiểm tra bằng code; xem [tài liệu Ollama](https://docs.ollama.com/capabilities/structured-outputs).

## Ngữ cảnh không dùng chung với đơn

| Vùng nhớ | Dùng để làm gì |
| --- | --- |
| `current_request` | Các câu hỏi và đối tượng của tin nhắn hiện tại. |
| `discussion_context` | Chủ đề đang tham khảo, dùng khi có tham chiếu rõ. |
| `product_choices` | Danh sách lựa chọn đã trả đúng thứ tự; first/second/both/all chỉ trỏ danh sách này. |
| `order` / bản nháp | Món chính, extra_items, số lượng, liên hệ và REVIEW; không tự đổi khi hỏi bánh khác. |
| `request_memory` | Tối đa 8 yêu cầu gần đây có thứ tự/trạng thái; không tự phát lại thao tác cũ. |

Lịch sử giới hạn theo CONTEXT_MAX_TURNS; nhu cầu có cấu trúc lưu riêng. Điều kiện chung đã cung cấp như ngân sách được nhớ khi phù hợp; điều kiện riêng từng câu hỏi không ghi đè lẫn nhau. Điều kiện tránh nguyên liệu được giữ qua lượt và hợp nhất khi khách bổ sung; hỏi “bánh có lạc không?” không tự trở thành dị ứng cá nhân. Yêu cầu xóa điều kiện rõ ràng có hiệu lực ngay với truy vấn hiện tại. Khi nguồn chưa có allergen, bot không khẳng định bánh an toàn hoặc đề xuất bỏ điều kiện dị ứng. Hội thoại và bản nháp từng khách được lưu riêng trong SQLite.

Hỏi Donut rộng có thể trả mọi kết quả đã đối chiếu; không bắt chọn trước mới báo giá/tình trạng. “Cả 2 bánh nhé” sau hỏi thông tin tiếp tục hỏi cả hai, không tự đặt hay quantity=2. “Bánh đó” với nhiều ứng viên vẫn cần làm rõ. Hỏi địa chỉ/giờ cửa hàng là chính sách, không tra bánh đang thảo luận.

## Dữ liệu, đặt bánh và quy tắc an toàn

Menu nhóm có tên, mã SP, nhóm, ảnh và giá niêm yết. **Không có size, số người ăn, tồn kho, allergen, topping, lead time hoặc chính sách chính thức.** Không dùng số 0 thay giá chưa biết hoặc khẳng định còn hàng từ kiến thức model.

Nguồn group_files không hỏi/bắt nhập size, topping, chữ hoặc ngày giờ nhận. Khách tự nêu thông tin chưa đối chiếu vẫn là mong muốn unverified (chưa xác minh). Thu thập món/số lượng, giao hoặc nhận tại cửa hàng, tên/điện thoại giả và địa chỉ giả khi giao.

REVIEW là bản tóm tắt cần khách đồng ý, không phải đơn đã xác nhận. Sửa thông tin làm mất hiệu lực REVIEW cũ; “đồng ý nhưng đổi…” phải REVIEW lại. Thành công chỉ nói **“Đã lưu yêu cầu chờ tư vấn.”** và thêm mã nếu tool thực sự trả mã.

SQLite chatbot lưu hội thoại, bản nháp, yêu cầu và ticket; tách khỏi database sản phẩm/backend nhóm. Idempotency là dùng khóa chống ghi cùng yêu cầu nhiều lần. Transaction là nhóm thao tác database cùng thành công hoặc cùng rollback; không tự reset database đang dùng để sửa lỗi.

Hand-off lưu ticket local khi cần nhân viên/dị ứng/khiếu nại/nghiệp vụ chưa hỗ trợ. Chỉ nói đã ghi nhận, chưa nói nhân viên bên ngoài nhận. Dùng tên DEMO, số TEST và địa chỉ DEMO; không nhập liên hệ thật vào kịch bản thử.

Empty mode chỉ lưu nhu cầu chờ tư vấn; mock/local_demo vẫn có adapter và công cụ demo đang hoạt động. Nguồn thật chỉ được tạo đơn khi adapter có đầy đủ khả năng; nguồn chỉ đọc không tự bật xác nhận. Không đổi yêu cầu/đơn mẫu thành đơn kinh doanh.

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
4. `dat ca2loai, moi1c, lay tai tiem`
5. `Mousse Hawaii giá bao nhiêu?`
6. `thêm 2 bánh Mousse Hawaii nữa`
7. `bớt 1 bánh Mousse Hawaii`
8. `địa chỉ cửa hàng ở đâu, mở cửa mấy giờ?`
9. `tên DEMO Khách A, sđt TEST-A1`
10. `đồng ý gửi yêu cầu`

Kết quả mong đợi: trả thông tin trước, giữ hai Donut khi hỏi Hawaii; thêm/bớt Hawaii còn 1 chiếc. Bản nháp có Donut thường 1, Donut dâu 1, Hawaii 1; hình thức pickup và liên hệ giả đã nhập. Nguồn nhóm thiếu địa chỉ/giờ nên báo chưa đủ tài liệu. Chỉ lưu yêu cầu sau REVIEW hiện tại và đồng ý rõ, không xác nhận đơn kinh doanh. Xem kết quả model thực tế ở phần kiểm tra bên dưới.

## Thử RAG bằng chính sách mẫu

RAG là truy xuất tài liệu rồi dùng LLM chọn thông tin có nguồn; chunk là một điều khoản. Retriever keyword vẫn chạy, không cần tải embedding. Embedding là vector biểu diễn văn bản; chỉ dùng khi đã có model phù hợp và chỉ mục được xây đúng phiên bản.

```powershell
$env:KNOWLEDGE_MODE = 'sample'
.\.venv\Scripts\python.exe -B -X utf8 main.py
# Thử: “Chính sách giao hàng mẫu thế nào?” rồi /exit
Remove-Item Env:\KNOWLEDGE_MODE
```

sample chỉ dùng 5 điều khoản giả lập, luôn có nhãn mẫu và source_id/version. Empty không dùng mẫu như chính sách thật. Trích dẫn hợp lệ không chứng minh toàn bộ câu trả lời đúng; nội dung tài liệu là dữ liệu, không phải lệnh.

## Kiểm tra thực tế và giới hạn

Các kiểm tra độc lập dưới đây có thể chồng lấn; không cộng thành một điểm độ chính xác chatbot:

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

Độ trễ phụ thuộc model và máy. Tại một thời điểm đo, RAM dùng khoảng 94%, còn khoảng 0,61 GB; đây là ảnh chụp trạng thái, không phải cấu hình cố định. Không tự tải model khác để vượt lỗi. Model/JSON/timeout lỗi giữ bản nháp và không ghi đơn; retry sửa JSON tối đa một lần, không tự fallback từ AI sang rule.

Nếu CLI báo không tìm thấy python.exe, kiểm tra đúng thư mục và .venv. Nếu Ollama lỗi, kiểm tra `ollama list`, dịch vụ/cổng và tên model. Nếu menu thiếu/sai JSON, bot báo nguồn chưa cấu hình/lỗi, không tự lấy menu demo thay thế. Dừng server cũ và chạy lại sau khi sửa Python; Ctrl+F5 khi tài nguyên giao diện bị cache.

## Phạm vi lần chỉnh sửa này

Chỉ sửa 10 file đã có trong chatbot: app/schemas.py, app/llm_client.py, app/nlu.py, app/order_nlu.py, app/conversation.py, data/nlu_few_shots.json, evaluation/intent_context_dev.json, scripts/evaluate_intent_context.py và hai README. Không tạo docs/tests/báo cáo mới, không sửa static, menu nhóm, database đang dùng hoặc frontend/backend bên ngoài.

Lỗi nằm ở cả contract NLU và điều phối ngữ cảnh: chọn nhiều món/chọn tiếp chưa nhất quán, và thông tin kế thừa bị kiểm như delta mới. Đã tách danh sách lựa chọn, truy vấn hiện tại và bản nháp; kiểm tra output hiện tại trước khi bổ sung context.

Đã bỏ các hàm hiểu câu cũ không còn nơi gọi (extract_nlu/extract_order_slots/choose_opening và helper gộp proposal cũ), cùng schema tương ứng. Giữ adapter/module còn được CLI/API/evaluator sử dụng; không xóa cả module chỉ vì không dùng trong cấu hình group_files hiện tại.

## Thứ tự đọc code và nối backend sau

1. `app/schemas.py`: intent, slot, reference và validation.
2. `app/llm_client.py` cùng `data/nlu_few_shots.json`: HTTP, prompt và ví dụ.
3. `app/repositories/catalog.py`, `group_catalog.py`: interface và ánh xạ dữ liệu nhóm.
4. `app/knowledge_loader.py`, `retrieval.py`: chính sách và nguồn.
5. `app/conversation.py`: điều phối, bộ nhớ, tách hỏi/đặt.
6. `app/order_nlu.py`, `order_flow.py`, `order_service.py`: kiểm chứng, bản nháp và tool.
7. `app/storage.py`, `app/api.py`, `main.py`: lưu trữ, quyền phiên và hai điểm chạy.

Khi backend sẵn sàng, thay adapter tại factory; giữ interface search_products/get_product/get_capabilities và tools kiểm tra/báo giá/gửi/tra cứu. Cần mapping ID SP/variant, nguồn giá/tồn kho chuẩn, quyền tạo đơn và idempotency xuyên hệ thống. Không ghi cùng đơn vào SQLite demo và backend thật; không tự chuyển dữ liệu mô phỏng thành đơn thật. Chạy lại hồi quy logic, session và giao dịch sau khi nối.
