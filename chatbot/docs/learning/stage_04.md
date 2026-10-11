# Giai đoạn 4 — Hỏi đáp từ tài liệu bằng RAG

Ngày thực hiện: 03/10/2026. Python 3.12.10 trong .venv trên Windows.
Đây là bài học theo code thực tế; stage_01–03 giữ lại để đọc lịch sử.

## 1. Mục tiêu và chức năng đã hoàn thành

**RAG** (Retrieval-Augmented Generation) là truy xuất tài liệu liên quan rồi
đưa vào mô hình ngôn ngữ để hỗ trợ trả lời. **Retrieval** là tìm đoạn liên
quan; **generation** là bước model tạo output dựa trên những đoạn đã nhận.
Không huấn luyện lại Qwen trong bước này. Khái niệm được trình bày trong
[bài báo RAG](https://arxiv.org/abs/2005.11401); code học tập ở đây dùng từ khóa
và trích xuất quote, không tái hiện toàn bộ hệ thống trong bài báo.

Đã có nguồn kiến thức riêng, hai mode:

- `empty`: chưa có chính sách; không mở file sample, nói chưa đủ thông tin.
- `sample`: 5 điều khoản giả lập về giao hàng, thanh toán, đổi trả, bảo quản,
  tùy chỉnh. Luôn nêu MÔ PHỎNG, không áp dụng cho đơn thật.

Một điều khoản là một **chunk** (đoạn được dùng làm đơn vị truy xuất).
**Retriever** là bộ phận xếp hạng/lấy các chunk; bản này dùng từ khóa, mặc
định lấy tối đa 3. Trong rule mode, code hiển thị đoạn để đối chiếu. Trong
ollama mode, Qwen chọn quote nguyên văn và source_id trong các chunk đã gửi;
code kiểm tra rồi trình bày. Đây là **RAG trích xuất** có giới hạn, chưa cho
model viết lại tự do chính sách. Rule là chương trình theo quy tắc, không
gọi là mô hình đã huấn luyện.

Nguồn menu `CATALOG_MODE=empty/mock` độc lập với nguồn chính sách
`KNOWLEDGE_MODE=empty/sample`. Chưa có chính sách thật/database sản phẩm,
đơn, API web hoặc giao diện website. Chưa tải/cài/chạy embedding.

## 2. File tạo/sửa và trách nhiệm

Đường dẫn dưới đây tính từ root D:\Chatbot. File liên quan giai đoạn trước
được sửa nhỏ; không viết lại dự án hay tạo adapter tương lai rỗng.

| File | Trách nhiệm/thay đổi |
| --- | --- |
| app/knowledge_loader.py — mới | Protocol nguồn kiến thức; loader JSON/validation/hash; adapter empty/sample và factory. |
| app/retrieval.py — mới | Tách từ, index RAM, xếp hạng <=3 chunk, kiểm tra quote/nguồn và tạo PolicyResponse. |
| data/sample_policies.json — mới | 5 điều khoản mô phỏng, ID ổn định/version/is_mock. Không là database. |
| app/schemas.py | Thêm PolicyClause/KnowledgeResult/KnowledgeChunk/RetrievalResult/PolicyResponse và hai schema Pydantic RAG. ChatResponse thêm policy. |
| app/config.py, .env.example | Thêm KNOWLEDGE_MODE/PATH, RETRIEVAL_TOP_K/MIN_SCORE; mặc định empty. |
| app/llm_client.py | Thêm prompt tài liệu và extract_policy_answer, dùng lại HTTP local/timeout/JSON schema. |
| app/nlu.py | Thêm từ ngôn ngữ nhận diện policy như COD/chuyển khoản/tùy chỉnh; không thêm giá trị chính sách. |
| app/chatbot.py | Câu chỉ hỏi policy giữ nhu cầu; include_policy_notice giúp controller ghép kết quả nguồn riêng. |
| app/conversation.py | Inject knowledge_repository, route policy, ghép kết quả, giữ chẩn đoán RAG/nguồn lỗi. |
| main.py | Chọn nguồn kiến thức ngoài logic, truyền vào controller, in mode và dòng RAG. |
| tests/test_retrieval.py — mới | Loader/retriever/RAG giả lập/validation/routing/CLI và development gold. |
| evaluation/retrieval_dev.json — mới | 27 câu development có source chuẩn, gồm 6 câu không có đáp án. |
| scripts/evaluate_retrieval.py — mới | Chạy retriever thật, tính chỉ số, ghi báo cáo có hash/phiên bản. |
| scripts/check_rag.py — mới | Smoke test HTTP Qwen thật riêng, 3 câu, không tải model. |
| scripts/__init__.py — mới | Đánh dấu package để chạy python -m scripts...; có mô tả mục đích. |
| evaluation/retrieval_report.json — sinh khi đo | Kết quả từng câu, điểm, ID, thời gian, chỉ số và hash. |
| evaluation/rag_smoke_report.json — sinh khi thử thật | Output/engine/error/thời gian của ba tình huống; tách khỏi pytest. |
| README.md, data/README.md | Lệnh Windows hiện tại, ví dụ hỏi, mode, file dữ liệu và giới hạn đã đo. |
| docs/project_spec.md, progress.md | Phạm vi thực tế và kết quả đã chạy/chưa chạy. |
| docs/decisions.md, contracts.md | Lý do kỹ thuật, interface/schema/quy tắc mới, tương thích tên cũ. |
| docs/data_integration.md, next_steps.md | Thay sample bằng nguồn thật; bước embedding và điều kiện stage tiếp theo. |
| docs/learning/stage_04.md | Bài học này, phục vụ hiểu/trình bày code. |

requirements.txt/dev không đổi: runtime vẫn Pydantic 2.11.9, kiểm thử pytest
8.4.2. Không cần scripts/build_index.py: chỉ mục từ khóa được dựng lại trong
RAM mỗi lần hỏi, chưa có vector cần lưu trên đĩa.

## 3. Luồng đầu vào → xử lý → đầu ra

Ví dụ CATALOG_MODE=empty, KNOWLEDGE_MODE=sample, CHAT_MODE=ollama:

```text
"Phí giao hàng là bao nhiêu?"
  → main nhập câu, gọi handle_message với hai repository
  → rule NLU nhận ý định policy
  → knowledge_repository.get_knowledge()
  → loader đọc/validate 5 điều khoản, tính SHA-256
  → mỗi điều khoản thành chunk, tách từ và dựng index
  → xếp hạng, lọc ngưỡng, lấy tối đa 3 chunk
  → Qwen nhận câu hỏi + chunk dạng JSON dữ liệu
  → JSON {supported, quotes:[{source_id, quote}]}
  → Pydantic + kiểm tra source_id/quote nguyên văn
  → code in nhãn sample + trích đoạn + nguồn/phiên bản
  → lưu lịch sử riêng của conversation, giữ nhu cầu bánh cũ
```

Empty đi từ loader → unconfigured → nói thiếu chính sách; không đọc mẫu và
không gửi chunk cho Qwen. File sai đi → error; không đổi thành “không tìm thấy”.
Nguồn hợp lệ nhưng không có chunk khớp đi → no_results → chưa đủ thông tin.
Nguồn có đoạn khớp nhưng Qwen thấy chưa đủ đi → insufficient, source_ids=[].
Model lỗi đi → rule_fallback, hiển thị đoạn nguồn thật để đối chiếu và mã lỗi.

Hai trạng thái cần đọc riêng: `catalog_status` là trạng thái menu;
`response.policy.status` là kết quả chính sách. Catalog chưa có không làm
kiến thức sample biến mất. Ngược lại có catalog mock không có nghĩa có tài
liệu chính sách. `answered` chỉ nghĩa đã trình bày trích đoạn hợp lệ, chưa là
chứng minh đáp án đầy đủ/đúng ý.

## 4. Các hàm chính: tham số, trả về, nơi gọi

| Hàm/phương thức | Tham số chính | Giá trị trả về | Nơi gọi |
| --- | --- | --- | --- |
| load_knowledge(mode, path=None) | empty/sample và đường dẫn tùy chọn | KnowledgeResult | Hai adapter/test. |
| KnowledgeRepository.get_knowledge() | Không có | KnowledgeResult | retrieve, evaluator. |
| create_knowledge_repository(mode, path=None) | Mode, path | Repository phù hợp | main. |
| tokenize(text) | Chuỗi | set[str] từ/cặp âm tiết | build_keyword_index/retrieve. |
| build_keyword_index(knowledge) | KnowledgeResult đã hợp lệ | dict tài liệu/IDF/hash/version | retrieve. |
| retrieve(question, repository=None, top_k=3, min_score=0.15) | Câu hỏi, nguồn, số chunk/ngưỡng | RetrievalResult | controller, evaluator, test. |
| build_policy_messages(question, retrieval) | Câu hỏi và top chunk | list ChatMessage system/user | extract_policy_answer. |
| extract_policy_answer(question, retrieval, base_url, model, timeout=30) | Chunk/URL local/tên/timeout | RAGExtractionResult: data/error/attempts | controller, test. |
| validate_rag_answer(answer, retrieval) | Pydantic RAGAnswer + chunk | Mã lỗi hoặc None | Client và make_policy_response. |
| make_policy_response(retrieval, answer=None, *, engine="rule", llm_error=None, attempts=0) | Nguồn và output đã validate/tùy chọn | PolicyResponse | Controller/test. |
| handle_message(message, repository, conversation, *, knowledge_repository=None, ...) | Hai nguồn, phiên riêng và cấu hình | ConversationTurn/bản sao phiên mới | main/script smoke/test. |
| respond(message, repository, state=None, *, nlu=None, include_policy_notice=True) | Hợp đồng cũ + cờ ghép policy | ChatResponse, policy ban đầu None | controller/test. |
| evaluate(dataset, repository, top_k=3, min_score=0.15) | Development gold và nguồn sample | dict báo cáo metric/từng câu | CLI evaluate/test. |
| scripts.check_rag.main() | Không có, đọc cấu hình | None, ghi báo cáo; exit 1 nếu hành vi lệch kỳ vọng | python -m scripts.check_rag. |

Các tên hàm cũ và Product/Variant/CatalogRepository giữ nguyên. Tham số mới
`knowledge_repository` và `include_policy_notice` là **keyword-only**: phải
truyền bằng tên sau dấu `*`, giúp tránh nhầm hai nguồn. Quy tắc chi tiết ở
[contracts](../contracts.md).

## 5. Code then chốt và kiến thức mới

### Python: dữ liệu, Protocol, JSON và hash

**Schema** là cấu trúc/kiểu thống nhất. PolicyClause dùng TypedDict để mô tả
dictionary có id/title/content/version/is_mock. Type hint giúp đọc code,
không tự kiểm tra runtime; loader kiểm tra key/kiểu/nhãn/ID trùng. RAGAnswer
dùng Pydantic để kiểm tra dữ liệu không đáng tin từ model.

**Protocol** là hợp đồng phương thức. **Dependency injection** nghĩa là
main tạo nguồn rồi truyền vào hàm. Retriever nhận KnowledgeRepository thay
vì tự chọn SampleKnowledgeRepository hoặc mở JSON:

```python
knowledge_repository = create_knowledge_repository(KNOWLEDGE_MODE)
turn = handle_message(
    message, repository, conversation,
    knowledge_repository=knowledge_repository,
)
```

Hai adapter dùng class vì chúng triển khai phương thức repo và sample giữ
đường dẫn. Logic truy xuất, kiểm tra và hội thoại vẫn là hàm. **Adapter** là
một cách triển khai hợp đồng cho nguồn cụ thể; sau này thêm nguồn khác ở
biên, không sửa câu SQL/field API ngoài trong controller.

**JSON** là định dạng văn bản dữ liệu. JSON true/null tương ứng Python
True/None, chuỗi/key dùng dấu nháy kép, không có comment hoặc dấu phẩy cuối.
File mẫu có root schema_version/is_mock/clauses; version từng clause khác
với schema_version của định dạng file. Loader dùng utf-8-sig để chấp nhận
UTF-8 có/không BOM (ký hiệu đầu file có thể do công cụ Windows thêm).

```python
if mode == "empty":
    return result  # nằm trước read_bytes: không dùng sample ngầm
raw = data_path.read_bytes()
document = json.loads(raw.decode("utf-8-sig"))
```

**SHA-256** là hàm tạo dấu vân tay nội dung; hash ở đây từ byte tài liệu.
Nội dung hoặc chỉ định dạng JSON thay đổi cũng làm hash khác. Hash giúp nhận
biết phiên bản corpus (tập tài liệu), không chứng minh tài liệu đúng/thật.

### AI/NLP: tách từ, index và điểm truy xuất

NLP là xử lý ngôn ngữ tự nhiên. **Index** (chỉ mục) là dữ liệu giúp tra cứu;
bản này là danh sách tập term và trọng số trong RAM. Term là từ hoặc cặp âm
tiết được dùng để khớp. **Regex** là biểu thức mô tả mẫu ký tự, ở đây `\w+`
lấy các nhóm chữ/số; `re.sub` dùng alias ngôn ngữ như ship → giao hàng.
Nó không tự hiểu toàn bộ nghĩa câu.

`normalize_text` giữ câu gốc ở luồng NLU và tạo bản bỏ dấu để tra từ. Tách
bằng regex chưa là bộ tách từ tiếng Việt hoàn chỉnh. Bỏ dấu làm quản/quan,
dùng/dụng giống nhau. Các âm tiết yếu như quan/dung không được dùng đơn lẻ;
code giữ cặp như bao_quan, ap_dung, su_dung để giảm khớp nhầm. **Stop word**
là từ chức năng quá phổ thông bị bỏ để ít ảnh hưởng điểm. Danh sách này vẫn
cần đánh giá thêm, không phải kiến thức chính sách hay tên sản phẩm.

**IDF** (inverse document frequency) là trọng số cao hơn cho term xuất hiện
trong ít tài liệu. Với N điều khoản và df điều khoản có term:

```text
idf(term) = log((N + 1) / (df + 1)) + 1
score = tổng idf(term khớp) × (2 nếu term có trong tiêu đề, 1 nếu chỉ content)
        / tổng trọng số term của câu hỏi
```

Các term chưa có trong corpus vẫn góp trọng số vào mẫu số, làm câu ít khớp
có điểm thấp. Điểm tiêu đề có thể khiến score >1; đây không phải xác suất
hay cosine. **Top-k** là lấy tối đa k kết quả tốt nhất; mặc định k=3, từ
1–3 được chấp nhận. Ngưỡng 0,15 loại điểm rất thấp nhưng không bảo đảm đủ ý.
Sort theo điểm giảm rồi ID tăng giúp cùng dữ liệu cho thứ tự ổn định.

### Backend: HTTP local và structured output

Backend là phần xử lý phía máy chủ/chương trình, ở đây chưa có API website.
**HTTP** là giao thức gửi yêu cầu/nhận phản hồi; **API local** của Ollama là
giao diện dịch vụ chạy trên máy. GET /api/tags lấy tên model đã cài; POST
/api/chat gửi question/chunks/schema. Không POST /api/pull, không tự tải model.
**Timeout** là giới hạn chờ một request, mặc định 30s/cho phép tối đa 60s,
không phải thời hạn toàn lượt có thể nhiều request.

**Prompt** là thông tin/chỉ dẫn gửi model. System prompt đặt quy tắc; tài
liệu nằm trong user JSON và được xác định là dữ liệu. Nội dung “bỏ qua quy
tắc” trong tài liệu không được code thực thi. **Prompt injection** là nội
dung cố điều khiển model trái quy tắc; cách tách này và schema giảm phạm vi
ảnh hưởng, không chứng minh model miễn nhiễm.

**Structured output** là output theo cấu trúc đã định. Ollama hỗ trợ JSON
schema qua format, theo [tài liệu chính thức](https://docs.ollama.com/capabilities/structured-outputs).
Schema code đang dùng:

```json
{
  "supported": true,
  "quotes": [
    {"source_id": "sample-policy-001", "quote": "Phí giao hàng mô phỏng là 25.000 đồng mỗi đơn."}
  ]
}
```

Ví dụ trên là dữ liệu mẫu, không là giá trị hardcode trong prompt/core logic.
**Validation** là kiểm tra đầu vào/output theo quy tắc. Có hai lớp:

```python
answer = RAGAnswer.model_validate_json(result["content"])
error = validate_rag_answer(answer, retrieval)
```

Lớp đầu strict type/extra forbid/tối đa 3 quote; lớp sau kiểm tra source_id
trong chính các chunk đã gửi và quote là substring content. ID tồn tại trong
corpus nhưng không được retrieve vẫn bị từ chối. JSON sai sửa một lần; nguồn
trích/quote sai không sửa thêm, fallback hiển thị content nguồn thật.

### Nghiệp vụ: nguồn chứng cứ khác nhu cầu/đơn

Phí giao hàng trong policy không phải ngân sách bánh. Câu chỉ hỏi chính sách
giữ nguyên conversation.needs. Catalog mới xác nhận product_id/biến thể/
giá/tồn kho/allergen; tài liệu chung và LLM không thay thế nguồn đó. Sample
không được áp dụng cho đơn thật; hiện chưa tạo cả đơn mô phỏng.

Source_id hợp lệ là kiểm tra cấu trúc. Quote nguyên văn thêm bằng chứng về
nguồn, nhưng model có thể chọn đoạn không liên quan hoặc bỏ điều kiện. Ví
dụ đoạn “trong 2 giờ” nếu bỏ “bị hỏng hoặc sai nội dung” sẽ làm câu trả lời
thiếu điều kiện dù substring đúng. Cần đọc câu hỏi/toàn điều khoản và đánh
giá nghĩa; không gọi ID đúng là đã chứng minh toàn câu đúng.

## 6. Lý do chọn cách này, giới hạn và phương án khác

5 tài liệu ngắn phù hợp từ khóa/thư viện chuẩn: không cài AI nặng, dễ tự
trình bày và đo. Dựng lại index mỗi lượt tránh stale index (chỉ mục cũ chưa
cập nhật); chi phí tăng theo số tài liệu, chưa phù hợp nguồn lớn. Hash và
keyword-v1 giúp mô tả đúng lần đo, không cần index đĩa giả hoạt động.

RAG trích xuất giữ phản hồi trong nội dung có thể đối chiếu. Cách khác là
cho LLM viết answer tự do rồi kèm citations, nhưng ID hợp lệ không ngăn bịa
nội dung answer; bản đầu chọn quote-only. Giới hạn: câu trả lời ít tự nhiên,
rule/fallback có đoạn thừa, quote có thể thiếu nghĩa/điều kiện. Câu hỏi nhiều
ý và lượt “còn điều đó thì sao?” chưa dùng lịch sử để xác định chủ đề RAG.
History vẫn riêng/bounded, nhưng RAG hiện gửi câu của lượt hiện tại.

**Embedding** là biểu diễn văn bản thành **vector** (dãy số) sao cho có thể
so mức gần nhau. **Cosine similarity** là độ giống hướng hai vector:
`dot(q,d)/(norm(q)*norm(d))`; norm là độ dài vector, không chia cho 0.
Embedding có thể giúp câu khác từ nhưng gần nghĩa; điểm cao cũng chưa chứng
minh đáp án. Có thể lưu vector local thay vì database vector phức tạp.

Ứng viên chưa tải là
[paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2).
Model card mô tả 50 ngôn ngữ và vector 384 chiều; chưa đo chất lượng tiếng
Việt/CPU/RAM máy này. Chưa cài sentence-transformers/Torch, chưa có vector
hoặc cosine chạy thật. Bước tải chỉ sau yêu cầu người dùng:

1. Xác minh RAM/dung lượng/CPU, đọc model card/license và chốt model.
2. Pin model revision bằng commit SHA (mã phiên bản nội dung chính xác); chốt
   phiên bản dependency, tải snapshot đúng revision về folder local.
3. Nạp từ đường dẫn local với local_files_only=True và device="cpu" để lúc
   chạy không tự tải. Encode chunk/câu hỏi, kiểm tra chiều/norm.
4. Index cần manifest (file mô tả phiên bản): model_id/revision, chiều vector,
   chuẩn hóa, corpus_sha256, chunking_version, index_schema_version/thời gian.
5. Thay tài liệu/model/chia chunk phải rebuild. Khi có index đĩa thật mới tạo
   scripts/build_index.py. Đo cùng gold với keyword trước khi quyết định dùng.

Đây là quy trình chuẩn bị, không phải adapter/file embedding đã triển khai.
Không cần pgvector/hybrid search/reranker trong stage này. Chi tiết thay nguồn
và chuẩn bị tải ở [data_integration](../data_integration.md).

## 7. Lệnh Windows, câu hỏi mẫu và kết quả mong đợi

PowerShell tại D:\Chatbot, .venv sẵn có. Nếu mới clone, làm hướng dẫn tạo venv/
dependency/interpreter trong [README](../../README.md). Không tạo lại .venv
có sẵn; .venv không là code và không đưa Git. .env chưa tự nạp.

```powershell
cd D:\Chatbot
$env:CATALOG_MODE = "empty"
$env:CHAT_MODE = "rule"
$env:KNOWLEDGE_MODE = "empty"
.\.venv\Scripts\python.exe -X utf8 main.py
```

Hỏi `Chính sách giao hàng là gì?` → “[Kiến thức: empty]”, thiếu tài liệu,
không có nguồn trích. Gõ thoát; chạy sample:

```powershell
$env:KNOWLEDGE_MODE = "sample"
.\.venv\Scripts\python.exe -X utf8 main.py
```

| Câu nhập trong chatbot | Kết quả mong đợi sample/rule |
| --- | --- |
| Phí giao hàng là bao nhiêu? | Trích nguồn 001, phí giả lập 25.000 đồng/đơn, nhãn mô phỏng. |
| Thanh toán COD được không? | Nguồn 002: tiền mặt/chuyển khoản chỉ mô phỏng, không gửi tiền thật. |
| Thời hạn đổi trả? | Nguồn 003: 2 giờ và điều kiện hỏng/sai, không vì đổi ý. |
| Bảo quản trong ngăn mát thế nào? | Nguồn 004: 2–8 độ C/24 giờ trong bài tập, chưa áp dụng bánh thật. |
| Viết chữ lên bánh cần báo trước bao lâu? | Nguồn 005: tối thiểu 24 giờ trong bài tập. |
| Bánh có đậu phộng gây dị ứng không? | Không xác nhận an toàn dị ứng khi catalog thiếu thông tin. |
| Có giao hàng quốc tế không? | Retriever có thể lấy 001; rule đưa đoạn đối chiếu, không có căn cứ để khẳng định giao quốc tế. |

Gõ mới/reset trước câu độc lập; thoát rồi đổi mode mới có tác dụng. Thử
catalog mock kết hợp policy sample chỉ cần đổi CATALOG_MODE, không sửa code.

Qwen đã có trên máy này là qwen3.5:4b; trên máy khác phải dùng tên đã cài:

```powershell
ollama list
(Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5).models | Select-Object name,size
$env:CHAT_MODE = "ollama"
$env:KNOWLEDGE_MODE = "sample"
$env:OLLAMA_MODEL = "qwen3.5:4b"
$env:OLLAMA_TIMEOUT_SECONDS = "60"
.\.venv\Scripts\python.exe -X utf8 main.py
```

Hỏi phí: kỳ vọng RAG=ollama, ID nguồn hợp lệ, quote từ tài liệu. Nếu timeout/
model thiếu/JSON sai: RAG=rule_fallback có mã lỗi, đoạn nguồn vẫn mô phỏng.
Với câu policy thuần, NLU=0 nhưng RAG attempts có thể 1/2. Tên model hiển
thị chỉ là tên đã chọn, không tự chứng minh model sinh thành công.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -X utf8 -m scripts.evaluate_retrieval
# Chỉ lệnh này gọi model thật; cần Ollama, dùng cấu hình ở trên
.\.venv\Scripts\python.exe -X utf8 -m scripts.check_rag
```

Evaluator nhận --dataset/--policies/--output/--top-k/--min-score khi cần so
sánh, ví dụ `--top-k 1 --output evaluation/retrieval_top1.json`. Đọc từng
câu trước kết luận. Báo cáo mặc định bị cập nhật khi chạy lại; giữ bản riêng
nếu cần so các phiên bản.

## 8. Kiểm thử đã chạy, kết quả thật và chưa kiểm tra

Nền stage 3: 120 passed in 1.58s. Lần đầu test mới: 157 đạt/2 lỗi do từ đơn
yếu khớp nhầm; đã sửa tokenizer, giữ nguyên kỳ vọng test. Bản cuối:

| Kiểm tra | Kết quả thực tế |
| --- | --- |
| pytest | **170 passed in 2.60s**, exit 0; model/HTTP giả lập. |
| Empty/sample, nguồn/file lỗi, top <=3, đổi tài liệu/version | Đạt trong test; empty không mở sample. |
| JSON/sửa tối đa 1, ID ngoài top, quote bịa, field tạo đơn, injection dạng dữ liệu | Đạt bằng fake output; không thực thi nội dung tài liệu. |
| Timeout/unsupported, giữ needs, hai CLI rule | Đạt; không dùng phí policy làm ngân sách bánh. |
| compileall main/app/scripts/tests | Exit 0, không lỗi cú pháp. |
| pip check | Exit 0, No broken requirements found. |
| scripts.evaluate_retrieval | Exit 0; 27 câu chạy retriever thật, không dùng Qwen. |
| Controller với 21 câu policy development | Empty 21/21 unconfigured, sample 21/21 route policy/chứa gold; rule, không đo nghĩa model. |
| scripts.check_rag | Exit 0, 3/3 hành vi; hai lượt sinh Qwen thật và một lượt empty không sinh. |

Sau lượt 159 test, rà soát development qua controller phát hiện một số câu
như “phí vận chuyển”, “ngăn mát/ngăn đá” chưa route policy. Đã bổ sung cụm từ
nhận diện chung, thêm 10 test cho empty/sample giữ needs và một test hỏi cả
giá/size + policy để hai nguồn cùng hoạt động; kết quả cuối 170 test ở bảng.
Không đưa ID nguồn/giá trị điều khoản vào NLU, không đổi retriever sau lần đo.

**Development set** là bộ câu dùng phát triển/điều chỉnh. **Gold** là nguồn
chuẩn do người phát triển gán dựa trên điều khoản; evaluator dùng để chấm,
không gửi cho retriever/model. Có 21 câu có đáp án (một câu cần hai nguồn),
6 câu không có đáp án. Tập này chưa là held-out độc lập.

| Chỉ số/ý nghĩa | Giá trị đã đo |
| --- | --- |
| Recall@3: trung bình số gold được lấy / số gold, trên câu có đáp án | 100%. |
| Hit@1: nguồn đầu thuộc gold, trên câu có đáp án | 20/21 = 95,24%. |
| MRR@3: trung bình 1/vị trí gold đầu tiên, không có thì 0 | 0,97619. |
| Abstention: trả rỗng đúng trên câu không có đáp án | 3/6 = 50%. |
| Exact source set: tập ID lấy được đúng toàn bộ gold, không thừa/thiếu | 10/27 = 37,04%. |
| Thời gian retrieval trung bình, gồm đọc/index | 0,680889 ms trong lần đo, không gồm LLM. |

Recall cao vẫn có thể precision thấp (precision là tỷ lệ kết quả lấy ra có
liên quan). Báo cáo hiện đo exact set để thấy đoạn thừa; chưa báo precision
thành metric riêng. **False positive** là lấy đoạn khi gold không có nguồn:
câu giá bánh, giờ mở cửa, giao quốc tế còn khớp nhầm. Câu “Bánh dùng trong
bao lâu sau khi nhận?” lấy gold ở hạng 2. Vì vậy không gọi 100% recall là
100% đúng chatbot. Có thể xem từng câu ở
[retrieval_report](../../evaluation/retrieval_report.json).

Qwen thật, timeout 60s, qwen3.5:4b đã cài, không tải:

| Câu hỏi | Kết quả | Thời gian |
| --- | --- | --- |
| Empty: chính sách giao hàng | unconfigured/not_used, source_ids=[], 0 lần sinh. | 0,01s |
| Sample: phí giao hàng mô phỏng | ollama/answered, 1 lần, quote phí 25.000 đồng từ 001. | 25,82s |
| Sample: giao hàng quốc tế | ollama/insufficient, 1 lần, không trích nguồn vì chưa đủ thông tin. | 5,74s |

Output và kiểm tra tại [rag_smoke_report](../../evaluation/rag_smoke_report.json).
Chỉ hai lượt model thành công trong lần thử; không suy ra độ ổn định, tốc độ
hoặc độ đúng toàn bộ tập 27 câu. Chưa thử RAG trên nhiều khách đồng thời,
chính sách thật/mâu thuẫn/dài, mọi kiểu injection, paraphrase rộng hoặc hiệu
năng embedding CPU. RAM chưa xác minh; GPU 4 GB không đủ chứng cứ để chọn
model embedding. Chưa có index vector/cosine thật.

## 9. Lỗi thường gặp và cách xử lý

| Triệu chứng | Cách kiểm tra/xử lý |
| --- | --- |
| Sample file tồn tại nhưng bot nói empty | Xem $env:KNOWLEDGE_MODE, đặt sample trước khi chạy lại; .env chưa tự nạp. |
| Chọn catalog mock nhưng thiếu policy | Hai nguồn độc lập; đặt KNOWLEDGE_MODE riêng. |
| invalid_knowledge_data | Kiểm tra path/JSON/5 key clause/ID trùng/is_mock/version/content; đừng xóa nhãn mock. |
| no_results hoặc đoạn không đúng ý | Đọc query/score/từng chunk; thử cách hỏi rõ hơn, thêm dev case. Không tự chèn gold ID vào thuật toán. |
| Quote/model bị từ chối | Đọc invalid_rag_json/source/quote; giữ fallback, kiểm tra output có nguyên văn và nguồn thuộc top chunks. |
| connection_error/model_not_found | Kiểm tra tags/tên đúng. Mở Ollama hoặc ollama serve khi chưa chạy; dùng rule nếu chưa có model, không tự tải. |
| timeout | Thử tối đa 60s; xem RAG engine/llm_error. Không gọi fallback là model thành công. |
| Model trả một quote đúng nhưng thiếu điều kiện | Đối chiếu toàn điều khoản/câu hỏi; thêm test/dev và kiểm tra nghĩa thủ công. Source ID không đủ để chứng minh. |
| Giá trị cấu hình bị ValueError | TOP_K phải 1–3, MIN_SCORE >0 <=1, mode đúng; đặt lại trước chạy Python. |
| ModuleNotFoundError: scripts/app | Chạy từ root, dùng python -m scripts.evaluate_retrieval, không chạy trực tiếp file trong scripts. |
| Chữ Việt sai khi pipe PowerShell 5.1 | Dùng python -X utf8; script gửi qua pipe cần $OutputEncoding = [System.Text.UTF8Encoding]::new(). |
| Truy vấn bánh chung/greeting vẫn mang tên bánh cũ | Đây là lỗi giai đoạn trước đã chẩn đoán, chưa sửa ở stage 4. Gõ mới/reset để thử độc lập; backlog trong next_steps. |

Không đổi cả dự án hoặc bỏ validation chỉ để che lỗi model. Không thay nguồn
lỗi bằng sample khiến khách nghĩ đã đọc chính sách thật.

## 10. Năm câu hỏi vấn đáp/phỏng vấn và gợi ý trả lời

1. **RAG khác huấn luyện model ở đâu?** Gợi ý: retrieve tài liệu rồi đưa vào
   context của lần gọi; trọng số Qwen không được cập nhật. Bản này output là quote.
2. **Vì sao cần KnowledgeRepository khi chỉ có JSON?** Gợi ý: logic biết hợp
   đồng get_knowledge, không biết path/định dạng; main inject nguồn. Có thể
   thêm adapter thật sau, giữ trạng thái thiếu/lỗi và không sửa retrieval.
3. **Source ID hợp lệ đã đủ chưa?** Gợi ý: chưa. Phải thuộc chunk đã gửi, quote
   phải nguyên văn; vẫn cần kiểm tra liên quan/điều kiện/đầy đủ/ngày hiệu lực.
4. **Vì sao Recall@3=100% mà chatbot chưa đáng tin hoàn toàn?** Gợi ý: metric
   chỉ tính lấy đủ gold ở câu có đáp án; còn đoạn thừa, 3/6 câu không có đáp
   án vẫn lấy nguồn, model có thể chọn sai đoạn. Dev chưa là held-out.
5. **Tài liệu thay đổi thì làm gì với index?** Gợi ý: hiện đọc/dựng lại RAM
   mỗi lượt, hash mới; index vector tương lai phải so hash/model revision/
   chunking và rebuild. Cập nhật gold, test và đo lại; không chỉ đổi source ID.

## 11. Ba bài tập nhỏ tự thực hành

1. Sửa một điều khoản sample: đổi nội dung phí và tăng version, giữ is_mock/ID.
   Hỏi lại rule, xem quote/version/hash. Cập nhật kỳ vọng smoke phí nếu cần,
   chạy test/đo, rồi phục hồi bản cũ để đối chiếu. Không sửa giá trong prompt.
2. Chạy evaluator với top_k=1 vào file báo cáo riêng. So Recall/Hit/Exact set
   với top_k=3; giải thích câu đa chính sách cần hai nguồn và ảnh hưởng đoạn thừa.
3. Thêm 3 câu không có đáp án và 2 câu diễn đạt khác vào dev JSON, gán gold
   sau đọc tài liệu. Chạy đo, chọn một false positive/false negative (bỏ sót
   nguồn) để giải thích; không hardcode câu hỏi/ID vào retriever.

Các bài tập là việc người học tự làm, chưa được agent chạy ở giai đoạn này.
Nếu đổi dữ liệu, báo cáo/test hiện tại là lịch sử phiên bản cũ; chạy lại trước
khi trình bày số liệu mới.

## 12. Kiến thức cần học trước bước tiếp theo

Python: dictionary/list/set, type hint/Protocol, keyword-only, deepcopy,
exception, pathlib, json, import/package và chạy module với -m. Backend:
GET/POST/status/timeout, request/response schema, phiên riêng và giới hạn dữ
liệu; FastAPI chỉ học khi bước tiếp theo được yêu cầu. AI/NLP: token/term/
context, retrieval khác generation, IDF/top-k, validation khác đúng nghĩa,
gold/dev/held-out và cách đọc metric. Nghiệp vụ: menu khác chính sách, unknown
khác hết hàng, mock khác thật, xác nhận đơn mô phỏng và kiểm tra giá/khả dụng.

Điều kiện sang giai đoạn 5: chạy được hai mode kiến thức, giải thích nguồn/
quote/fallback, đọc được báo cáo và giới hạn chưa đúng; pytest hiện tại đạt;
người dùng yêu cầu phạm vi bước 5. Thiếu policy/menu thật không chặn API local
hoặc học phần độc lập. Embedding là nhánh tùy chọn, phải có yêu cầu tải/chốt
thiết bị trước; không là điều kiện bắt buộc để tiếp tục bản từ khóa.
