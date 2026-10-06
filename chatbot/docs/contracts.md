# Contracts hiện tại — intent/context 06/10/2026

**Phần này là contract có hiệu lực. Các mục stage_01–06 bên dưới được giữ như lịch sử, các mô tả v1/rule_fallback/lệnh bỏ qua Qwen/catalog chưa có không còn mô tả luồng mặc định.** Đọc schema/code thật cùng phần này.

## 1. Config và nguồn

DATA_SOURCE local_demo(default)/empty/mock; CATALOG_MODE alias khi DATA_SOURCE chưa có. ORDER_PROVIDER local_demo(default)/unsupported, không provider thật. DATABASE_PATH(default runtime/chatbot.sqlite3), CHATBOT_DB_PATH alias. CHAT_MODE ollama(default)/rule chủ động. KNOWLEDGE_MODE local_demo(default nếu catalog localdemo)/empty/sample. TIMEZONE chỉ Asia/Ho_Chi_Minh. OLLAMA_BASE_URL loopback, OLLAMA_MODEL exact tag hoặc rỗng chọn Qwen đã cài; timeout<=60/context1..20default6. Không tự nạp .env/model/download/cloud.

Factory chọn nguồn ở main/api. CatalogProtocol vẫn ba phương thức search_products/get_product/get_capabilities. Optional OrderMetadataRepository.get_order_metadata(product_id). LocalCatalogRepository thêm get_policy_documents/get_business_settings/using_connection. KnowledgeRepository giữ get_knowledge(); LocalKnowledgeRepository bridge SQL policy. Không caller business nào viết SQL catalog.

## 2. Catalog/knowledge/result

Product core giữ id/name/aliases/category/description/flavor/variants/allergen/customization/min_lead_hours/source/is_mock. Optional rich: active/is_demo/occasions/allergen_info/storage/shelf_life_hours/topping_options. Variant giữ id/size/price_vnd/servings/stock_status. Giá integer>=0 hoặc null, servings>0 hoặc null, stock enum in_stock/out_of_stock/unknown. SQL stock_quantity>=0 hoặc null. Allergen status contains/may_contain/unknown/not_listed+items+note; legacy allergen được adapter suy từ chính metadata này để không mâu thuẫn; not_listed không an toàn.

SearchFilters: query/product_ids/flavor/max_price_vnd/price_inclusive/servings/size/occasion/exclude_allergens/available_only. Điều kiện bắt buộc lọc trước, sort giá thấp trước; tư vấn chung tối đa5 cards và thông báo count. Nếu khách hỏi tên nhiều bánh rõ ràng, trả tất cả các bánh đã giải đúng trong truy vấn, không cắt còn5. Các status nguồn: unconfigured (chưa có nguồn), no_results (nguồn chạy không phù hợp), success, error; [] chỉ là payload không là toàn bộ trạng thái. Get product error không no_results giả.

PolicyClause id/title/content/version/is_mock, chunk source_id=id/title/content/version/is_mock/score, result corpus_sha256/retriever_version. LocalSQL13/sample5/empty riêng; tối đa3chunk. Qwen RAGAnswer {supported:bool,quotes:[{source_id,quote}]}; ID phải có trong chunks, quote nguyên văn substring content, không thêm answer tự sinh. Không nguồn thì không gọi model dựng chính sách; ID hợp lệ chưa chứng minh nghĩa đúng. Nội dung tài liệu là dữ liệu, không thực thi lệnh.

## 3. Qwen output và context

Luồng mặc định **mọi message nghiệp vụ** dùng extract_turn, kể cả greeting/order/review/confirm/cancel/handoff/policy. LLMTurn:
- intents list: greeting/price/size/flavor/availability/recommendation/policy/order_request/fallback/allergen/topping/storage/description.
- action none/start_order/review/confirm/cancel/handoff.
- product_mentions: cụm tên trong CURRENT message, chưa ID. Tên chuẩn khác nguyên văn chỉ được chấp nhận khi alias trong câu xác định duy nhất cùng sản phẩm qua repository. Alias trùng không được tự chọn. reference none/last/first/second/cheaper/order. Có mention rõ thì chỉ giải các tên hiện tại, reference hiệu lực là none dù model đồng thời trả last. Không tìm thấy tên không quay sang bánh trong draft. Không có tên mới giải reference: last chỉ chọn khi focus/draft có một ID hợp lệ duy nhất, nhiều ứng viên hỏi lại; order chỉ tham chiếu sản phẩm của draft; first/second/cheaper dùng cards đã xác minh. Câu hỏi thông tin không có đối tượng như “giá bao nhiêu?” được giải như tham chiếu ngầm, không tra toàn menu.
- updates TurnUpdates: nullable field chỉ nghĩa không cập nhật; field có giá trị thì set, clear_slots explicit xóa. quantity/servings/budget integer, toppings/allergens list, các field văn bản/boolean theo schema.
- ambiguous bool, handoff_reason none/customer_requested/severe_allergy/complaint/unsupported_business, order_update bool(defaultFalse): chỉ rõ ý định sửa draft, không đánh true vì khách hỏi giá/bảo quản bánh khác.
- requests: tối đa8 `InformationRequest` strict/forbid extra, mỗi phần có intents thông tin, product_mentions, reference và size nullable riêng. Intent request phải có ở list cấp ngoài. Chỉ chứa bánh thực sự được hỏi; tên bị phủ định có thể có ở mentions ngoài để kiểm căn cứ nhưng không được thành mục tiêu query. Câu hỏi thông tin dùng tasks riêng, không union tất cả tên/intent để áp cho mọi bánh.
- order_product_mentions: tối đa10 tên được chọn đặt/đổi/xóa, tách khỏi requests. order_operation none/select_product/add_product/remove_product/update_slots; khác none cần intent order_request. Không có field thì default none. Output cũ không requests vẫn được giải theo mentions chung để tương thích; output hỗn hợp mới thiếu mục tiêu đơn thì hỏi lại, không suy từ tên của câu hỏi.

Dạng HTTP LLMWireTurn thay updates bằng list field/value có discriminator field và type value tương ứng. Chuyển sang TurnUpdates dict nội bộ sau validate strict/forbid extra và từ chối field lặp. Không product_id/stock/price_selling/confirmed từ model. JSON/grounding sai cho model sửa **tối đa một lần**. HTTP/model/timeout lỗi không retry tự động và không rule fallback. Grounding literal/số/consent/clear + catalog omission chỉ chặn/yêu cầu sửa, không sinh intent/slot thay Qwen. Catalog omission không bỏ kiểm tra chỉ vì model trả reference. Guard tên/lệnh xóa dùng câu đã che lettering đặt trong ngoặc sau ghi/viết chữ. Lỗi preserve toàn bộ draft/state cũ, không createorder/update từ kết quả lỗi.

Prompt `intent-context-v8` đọc thư viện17 few-shot trừu tượng từ data/nlu_few_shots.json, chọn tối đa3 ví dụ hợp trạng thái FSM theo priority rồi giữ thứ tự trong file; không dò keyword hoặc đọc evaluation/nhãn final. Priority phải integer. Prompt có schema rút gọn (bỏ annotation title/description/default, giữ constraints/tên field) để model đọc cấu trúc; format HTTP vẫn schema đầy đủ, validation không nới. Order operation nằm trước requests trong schema. Bản v4/v5/v6/v7 thử trên dev và giữ report, không điều chỉnh từ final. current_message_catalog_aliases lấy alias có mặt trong câu từ repository, không ID/giá/stock, không quyết định intent hoặc thay kết quả Qwen. Các messages/ví dụ là dữ liệu; không dùng keyword để chuyển âm thầm sang rule. HTTP client, timeout, tên model/options hiện có giữ nguyên.

Ba phạm vi riêng trong controller:

- CurrentTurn: intents/product_mentions/reference hiệu lực/product_ids/filters của lượt hiện tại; thêm requests (scope của từng query) và order_product_ids riêng. resolve_message_scopes(current,proposal,repository,message) và build_current_turn tạo dict/list riêng; thông tin hỏi bánh mới không thừa hưởng ID/query/size/ngân sách của draft hoặc lượt cũ. Request rỗng last/none không có cue tham chiếu phải kế thừa chủ thể duy nhất của CURRENT turn, không kéo lịch sử vào; nhiều chủ thể chưa rõ hỏi lại. Request trùng sau chuẩn hóa scope được bỏ. Reference first/second/order/cheaper cần cue trước khi dùng context; last có tên trong lượt xét cả chủ thể hiện tại với focus/draft, nhiều ứng viên hỏi lại. Phrase tham chiếu không xác minh được như tên sản phẩm thì hỏi lại. Guard cue không trích intent/thay Qwen. Trong câu hỗn hợp, updates/clear_slots thuộc đơn còn request.size chỉ lọc query. Trả trong kết quả service để test, không persist và không thêm field vào API công khai.
- ConversationContext: focus_product_ids/focus_product_terms, persist ở conversation_context; shown_products riêng giữ cards cho tham chiếu thứ tự/so giá. needs giữ sở thích/ràng buộc tư vấn, không lưu product_ids/query làm mục tiêu truy vấn chung. Legacy filters có hai key này được bỏ khi cập nhật preferences, không xóa history. Ràng buộc dị ứng rõ được giữ riêng để tư vấn tiếp an toàn.
- Order draft: key order giữ tên cũ, slots/revision/review riêng. Hỏi thông tin thuần (action=none, không order_request/recommendation) giữ nguyên draft/bước đang chờ, kể cả model trả nhầm order_update=true. Ý định sửa rõ mới áp dụng delta. Handoff/an toàn vẫn được ưu tiên theo quy tắc nghiệp vụ.

Context còn id/history(max6turns default)/model/unknown_streak. Prompt phân nhóm order_draft(state,filled/missing,product_selected,missing_fields,next_required_field) và conversation_context(focused_product_count,shown_product_count,focus_is_order_product,known_needs_fields), giờlocal. **Không gửi tên bánh cũ, giá trị preferences cũ hoặc botquestions vào extractor**: model chọn reference ký hiệu, Python giải bằng IDs/card thật trong context riêng. Source hints chỉ alias hiện tại. Đây là thay đổi nội bộ prompt theo D95, không xóa history/slots/cards/database hoặc đổi API. Code vẫn giữ đầy đủ slots riêng và persist. Phiên cũ thiếu conversation_context được bổ sung từ cards đã lưu. Không hỗ trợ chắc mọi phép tính tăng/giảm tương đối. Lệnh CLI /draft /orders /order /new /exit /resume là quản lý local, không message nghiệp vụ và không cần model.

## 4. FSM, review và tools

BROWSING → COLLECTING → REVIEW → DEMO_CONFIRMED(localdemo); CANCELLED/HANDOFF. Fixture mock cũ có submission confirmed ở REVIEW để giữ compatibility; localdemo dùng state rõ DEMO_CONFIRMED. Empty lưu waiting_consultation, không confirmed/quote thật.

Một sản phẩm/variant mỗi draft, quantity positive; nhiều tên hỏi chọn, không âm thầm bỏ tên. add_product khi đã có draft hỏi rõ, không đổi sản phẩm ngầm; nếu có REVIEW cũ thì giữ slot nhưng bỏ REVIEW, tăng revision, quay COLLECTING. remove_product chỉ xóa khi mục tiêu đúng draft hoặc chưa xác minh trong empty; mục tiêu khác hỏi lại. Operation trên đơn confirmed đi handoff, kể cả model quên order_update. Slot product_id xác minh hoặc cake_need unverified, size, quantity, toppings, cake_text, pickup_at, fulfillment, name/phone/address. Ngày UTCaware lưu, shop+07 hiển thị; “chiều mai” pending_date rồi hỏi giờ. Giữ chữ NFC, đếm len codepoint, emoji ghép nhiều điểm, không truncate. Contact demo bắt buộc DEMOname/address và TEST-phone, không thật.

Mỗi sửa tăng revision/invalidate review. Đổi sản phẩm bỏ size/toppings/cake_need của bánh cũ, đánh các slot còn giữ là unverified để kiểm lại; giữ quantity/chữ/contact độc lập. Review có revision/slot hash/source fingerprint/verification/availability/issues/quote/product_name. Consent có edit luôn review lại. Confirmation only current review + finalbusinessvalid + transaction success. Confirmed không slot-update; edit/cancel → ticket. Unknown metadata không defaults giả.

OrderTools là callable closures gắn repository/connection/conversationowner:
- check_availability(draft), calculate_quote(draft), submit_order_request(draft,idempotency_key), get_order(id), create_handoff_ticket(reason,summary,idempotency_key).
- ToolResult {status:available/unavailable/unknown/unsupported/error, data, error}; dùng theo tool, unavailableget là không tìm record thuộc owner.
- Availability kiểmactive/variant/topping/knownstock/lead/openinghours/text/fulfillment/contacts/allergy. calculate_quote chỉ validmetadata mới giá; unknown không giá0.
- Quote variant/topping/writing mỗi bánh ×qty + delivery mỗi đơn. Settings/phí từ SQL, không prompt/FSM constants. Mode empty không quote thật, localdemois_mockTrue.
- Submit localdemo BEGINIMMEDIATE+SAVEPOINT, sameconn source recheck + UPDATEstockconditional + submission/orders/item snapshot + context cùngtransaction; caller commit, exception rollback. UNIQUEkey owner/payloadhash checked. Không source thật ngoài adapter hợp lệ, unsupported provider không giả confirmed.

## 5. Storage và quyền

sqlite3 duy nhất, schema user_version2. v1 backup trước migration, giữ4bảng cũ và recordID. drafts/tickets tương đương order_drafts/handoff_tickets; submissions+orders cùngID là hai phần **một đơn**, order_items snapshot. Legacy demo đơn chuyển orders không retro-trừ kho. FKON/check, integerVND/nonnegativestock, UTC, source/is_demo, payment_statusunpaid. open_storage dùng pathlib root, path Unicode/space. Controller owner/order/messages commit cùng transaction.

Seed INSERT...ONCONFLICT DONOTHING, ID ổn định, giữ stock/price đã chỉnh. CLI reset xác minh bằng connection mode=ro trước mở ghi/migrate; file thiếu/chưa được xác minh bị từ chối. Reset riêng confirm + resolvedpath trongruntime + matchopenedpath + environmentlocaldemo + alldemorows, backup trước, rowdelete/reseed transaction; không xóa file tùy ý. Không test reset trên DB đang demo.

API giữ4routes/sameorigin/UItextContent, chat response conversation_id/message/state/products/sources/data_mode/knowledge_mode/requires_confirmation/review/request_id/demo_order_id + diagnostics. Có thể HTTP200 với engine llm_error/source_error; client đọc errors và state. API Pydantic validates, maxmessage2000, validation không echo input, no-store.

Session secrets.token_urlsafe32, onlyhashRAM/TTL8h/capacity200, bearerheader và conversationguard/orderowner; wrongowner404/invalidtoken401. ID khôngauth. def route threadpool/connectionthreadlocal/lockperconversation/1worker. Restarttokeninvalid, SQLpersist; CLI resume local không web auth, không processconcurrentsameconversation.

Ticket pending local có owner/order nếu thuộcowner/reason/priority/summary/missing_information/outside_hours/is_demo/source. Không tuyên bố externalstaffreceived. Debug không token/realcontact, history sanitizer cơ bản; chỉ fake demo được hỗ trợ.

## 6. Môi trường kiểm thử (05/10/2026)

tests/conftest.py luôn chặn Ollama thật và dùng database test riêng. Hook pytest_configure(tryfirst=True) đặt basetemp mới tuyệt đối trong `.pytest_tmp/run-UUID` trước khi tạo tmp_path_factory, trừ khi người chạy đã truyền --basetemp. Không phụ thuộc quyền duyệt thư mục pytest-of-user trong AppData/Temp. Folder .pytest_tmp bị Git bỏ qua; run cũ giữ để xem lỗi, không tự xóa. Không dùng runtime/database demo làm basetemp. Explicit --basetemp vẫn giữ hành vi pytest có thể dọn thư mục do người chạy chọn. Các bước này không sửa cấu hình chatbot/API hoặc quyền Windows.

NLU dataset: dev48turns/11dialogues, final26turns/7dialogues, tổng74; ID/messages không trùng split, nhãn tĩnh riêng với few-shot. Evaluator tạo SQLite riêng, model thật, knowledge empty; không đo RAG correctness. Gold chỉ chấm sau inference, giữ lỗi trong mẫu số. Hash/code version và previous_runs giữ bằng chứng. completed=true không đồng nghĩa accuracy100%. So sánh yêu cầu cùng dataset hash/split/IDs. Xem evaluation/intent_context_protocol.md và docs/learning/intent_context_improvement.md.

---

# Lịch sử contract stage_01–06 (tham khảo, không ghi đè phần hiện tại)

# Hợp đồng giữa các phần của dự án

Cập nhật: 03/10/2026, **giai đoạn 6**. Interface là hợp đồng cách gọi/kết quả;
schema là cấu trúc và kiểu dữ liệu. Các tên bên dưới đã có trong code, trừ phần
được ghi rõ là tương lai.

## 1. Cấu hình và điểm chạy

`app.config` giữ nguyên bốn tên từ giai đoạn 1:

| Tên | Kiểu/mặc định | Quy tắc |
| --- | --- | --- |
| `CATALOG_MODE` | `str`, `empty` | Chỉ empty/mock; strip + lower. |
| `CHAT_MODE` | `str`, `ollama` | AI mặc định theo yêu cầu bổ sung; rule chỉ khi chọn thử offline. |
| `OLLAMA_BASE_URL` | `str`, `http://localhost:11434` | Client chỉ chấp nhận http/https loopback localhost/127.0.0.1/::1; không credentials/query/fragment/path. |
| `OLLAMA_MODEL` | `str`, chuỗi rỗng | Tên chính xác đã cài; rỗng thì chọn Qwen local nhỏ nhất theo size trong tags. Không tải model. |
| `OLLAMA_TIMEOUT_SECONDS` | `float`, 60 | >0 và <=60; timeout cho từng yêu cầu HTTP, không phải thời hạn toàn lượt. |
| `CONTEXT_MAX_TURNS` | `int`, 6 | 1–20; số cặp user/assistant giữ trong lịch sử. |
| `KNOWLEDGE_MODE` | `str`, empty | empty/sample; độc lập CATALOG_MODE. |
| `KNOWLEDGE_PATH` | `str`, data/sample_policies.json | Sample đọc; tương đối so với root dự án. Empty không đọc đường dẫn. |
| `RETRIEVAL_TOP_K` | `int`, 3 | 1–3 chunk tối đa. |
| `RETRIEVAL_MIN_SCORE` | `float`, 0.15 | >0, <=1; ngưỡng khớp, không phải xác suất. |
| `CHATBOT_DB_PATH` | `str`, runtime/chatbot.sqlite3 | SQLite chatbot, tương đối so root; không là nguồn catalog. |

Đọc biến môi trường khi import, chưa tự nạp `.env`. Mode sai/rỗng gây
`ValueError`. Đổi biến và chạy tiến trình mới để nhận cấu hình mới.
`main.main() -> None` nay chạy vòng lặp terminal bằng rule/ollama, thay hợp đồng in
5 dòng ở giai đoạn 1. Tên hàm và đường dẫn được giữ nguyên.

Ollama lỗi thì trả lời rule có thông báo lỗi cho lượt đó; không đổi catalog.
Import `main` không in, gọi mạng hoặc nạp fixture. Lệnh `mới/reset` tạo ID mới,
xóa cả lịch sử và nhu cầu trong RAM;
`thoát/exit/quit`, EOF hoặc Ctrl+C dừng phiên. Có yêu cầu/đơn demo qua FSM,
API có từ stage 6, chưa có đơn thật. Main lưu vào SQLite và đóng connection khi thoát.

## 2. Schema Product và Variant

Product/Variant và kết quả nghiệp vụ trong `app.schemas` vẫn là `TypedDict` dạng
hàm, dữ liệu lúc chạy là dictionary. Class Pydantic dành cho output LLM và API stage 6.
Type hint không tự xác thực dữ liệu; mock gọi
`validate_product(product) -> None`, dữ liệu sai gây `ValueError` tại biên nguồn.

| Trường Product | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id`, `name` | `str` | Mã ổn định, tên có thể đổi. |
| `aliases` | `list[str]` | Tên gọi khác do nguồn cung cấp. |
| `category`, `description` | `str` | Loại và mô tả. |
| `flavor` | `str` hoặc `None` | Hương vị chuẩn trong nguồn hoặc chưa biết. |
| `variants` | `list[Variant]`, ít nhất 1 | Biến thể của cùng sản phẩm. |
| `allergen` | `list[str]` hoặc `None` | Danh sách chất có thể gây dị ứng; None là chưa biết, không phải an toàn dị ứng. |
| `customization` | `list[str]` hoặc `None` | Tùy chỉnh đã biết hoặc chưa biết. |
| `min_lead_hours` | `int >= 0` hoặc `None` | Số giờ chuẩn bị tối thiểu; chưa triển khai kiểm tra thời hạn đặt. |
| `source` | `str` | Nguồn dữ liệu, hiện mock. |
| `is_mock` | `bool` | Dữ liệu mô phỏng hay không. |

| Trường Variant | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `str` | ID biến thể, không trùng trong sản phẩm. |
| `size` | `str` hoặc `None` | Ví dụ 16 cm; không bắt buộc mọi nguồn dùng đơn vị này. |
| `price_vnd` | `int >= 0` hoặc `None` | Giá VND cho một bánh; chưa biết là None, không dùng 0 làm giá thiếu. |
| `servings` | `int >= 1` hoặc `None` | Số người ước lượng cho một bánh. |
| `stock_status` | `in_stock/out_of_stock/preorder/unknown` | Tình trạng được nguồn cung cấp; chưa biết là unknown. |

JSON `null` tương ứng Python `None`. Giá 0 chỉ hợp lệ nếu nguồn thật sự có giá
0, không được tạo ra để thay giá thiếu. Tất cả mẫu hiện dùng giá dương hoặc null.
Mock bắt buộc root `data_mode=mock`, `is_mock=true`, mỗi sản phẩm `source=mock`,
`is_mock=true`, ID sản phẩm không trùng. Validator hiện yêu cầu đúng tập trường
Product/Variant; thay schema phải sửa validator, test và các nơi dùng cùng lúc.

## 3. Interface CatalogRepository

Đường dẫn: `app.repositories.catalog.CatalogRepository`, khai báo bằng
`typing.Protocol`. Repository không cần kế thừa, chỉ cần ba phương thức phù hợp:

| Phương thức | Đầu vào | Trả về |
| --- | --- | --- |
| `search_products(filters)` | `SearchFilters` | `SearchResult` |
| `get_product(product_id)` | `str` | `ProductResult` |
| `get_capabilities()` | Không có | `CatalogCapabilities` |

`SearchResult = {status, data_mode, products, error}`; `products` là list Product.
`ProductResult = {status, data_mode, product, error}`; `product` là Product hoặc None.

| `status` | Nghĩa | Payload |
| --- | --- | --- |
| `unconfigured` | Chưa có nguồn catalog được cấu hình | []/None, error=None. |
| `no_results` | Nguồn hoạt động, truy vấn không có kết quả | []/None, error=None. |
| `success` | Có kết quả | List không rỗng/một Product, error=None. |
| `error` | Nguồn/truy vấn thất bại | []/None, mã lỗi an toàn. |

Không suy trạng thái từ list rỗng. Empty luôn unconfigured, không giả hết hàng.
Mock có file lỗi trả `error=invalid_mock_data`. `safe_search_products()` bắt
exception tại biên nguồn, trả `error=source_error`, không lộ nội dung exception.
Không tự đổi nguồn lỗi thành mock hoặc thành no_results.

`CatalogCapabilities` gồm `data_mode: str`, `is_mock: bool`, `configured: bool`,
`policy_available: bool`, `can_accept_real_orders: bool`. Configured nghĩa là
đã chọn nguồn, không phải kiểm tra sức khỏe thành công; mock bị hỏng vẫn có
configured=True và truy vấn trả error. Hai catalog không cung cấp chính sách
(`policy_available=False`) và không nhận đơn thật. Chính sách nay qua interface
riêng; không suy tình trạng knowledge từ capabilities catalog. Nếu lấy
capabilities lỗi, response mode=unknown, status=error.

## 4. Bộ lọc tìm kiếm

`SearchFilters` cho phép thiếu các key; `{}` yêu cầu toàn bộ catalog.

| Key | Kiểu/quy tắc |
| --- | --- |
| `product_ids` | `list[str]`; lấy một hoặc nhiều ID. List rỗng có nghĩa không ID nào khớp. |
| `query` | `str`; mọi từ chuẩn hóa phải có trong tên/alias/loại/mô tả/vị. Chưa fuzzy search. |
| `flavor` | `str`; so với flavor nguồn sau chuẩn hóa. |
| `max_price_vnd` | `int`; ngưỡng ngân sách cho một bánh. |
| `price_inclusive` | `bool`; mặc định True. False dùng giá < ngưỡng, True dùng <=. |
| `servings` | Số nguyên dương; biến thể có sức phục vụ >= nhu cầu cho một bánh. |
| `size` | `str`; so khớp chuẩn hóa, bỏ khoảng trắng. |

Điều kiện cấp sản phẩm kết hợp AND, rồi giá/số người/size phải thỏa trên **cùng
một biến thể**. Không có giá hoặc số người thì không xác nhận điều kiện đó.
Search trả bản sao với **chỉ những biến thể thỏa bộ lọc**; get_product trả đầy
đủ biến thể. Không lọc tồn kho khi tư vấn; hiển thị đúng tình trạng mẫu để người
đọc biết còn hàng/hết hàng/cần đặt trước/unknown. Chưa kiểm tra tồn kho số lượng.

## 5. NLU và hội thoại

`analyze_message(text: str, repository: CatalogRepository) -> NLUResult`:

- Giữ `raw_text`, tạo `normalized_text` riêng: chữ thường, bỏ dấu, chuẩn hóa khoảng
  trắng; giữ dấu chấm/phẩy để đọc tiền.
- `intents` là list các giá trị greeting, price, size, flavor, availability,
  recommendation, policy, order_request, fallback. Fallback dùng khi không nhận diện được.
- `product_ids`, `product_terms` lấy từ tên/alias/ID do `search_products({})`
  cung cấp. Với tên chưa nhận diện, giữ cụm sau “bánh” trong query/product_terms,
  không xác nhận đó là sản phẩm có bán.
- `flavors`, `budgets_vnd`, `servings`, `quantity`, `size`, `price_inclusive`
  là thực thể cơ bản. Vocabulary vị phổ thông không phải menu; flavor chuẩn của
  sản phẩm đã nhận diện luôn lấy từ nguồn. Cụm “vị X” giúp ghi nhận nhu cầu mới.
- `catalog_status` là trạng thái lần nạp tên/alias; `requires_clarification`
  báo đa thuộc tính, alias trùng, liên kết nhiều bánh không chắc, số không dương
  hoặc điều kiện loại trừ chưa hỗ trợ. Không tự phân phối thuộc tính cho từng bánh.

`create_state() -> ChatState` gồm `filters`, `quantity`, `product_terms`,
`data_mode`. `respond(message, repository, state=None, *, nlu=None, include_policy_notice=True) -> ChatResponse` trả state
mới; không sửa state người gọi. Nhắc bánh mới thì reset bộ lọc, câu chỉ bổ sung
thuộc tính giữ bộ lọc trước; ambiguity/error không ghi đè nhu cầu. Chỉ lưu trong
RAM của respond; controller có thể lưu lịch sử/draft/đơn demo qua SQLite.
`nlu=None` tự phân tích
rule như giai đoạn 2; `nlu` truyền vào phải là NLUResult nội bộ đã đối chiếu,
không truyền trực tiếp JSON thô của model. Tên/3 tham số cũ được giữ tương thích.
`mới` tạo conversation mới trong main.

`ChatResponse` có `text`, `data_mode`, `is_mock`, `catalog_status`, `intents`,
`nlu`, `products`, `state`, `requires_clarification`, `error`, `policy`. Catalog_status là
trạng thái truy vấn catalog, **không phải kết quả kiểm tra chính sách hoặc nhận đơn**.
Mọi text có mode; mock luôn có nhãn dữ liệu mẫu. `policy=None` từ respond, controller
thêm PolicyResponse khi tra chính sách. Gọi respond trực tiếp vẫn có thông báo
thiếu chính sách; controller đặt include_policy_notice=False để ghép kết quả từ
nguồn kiến thức. Câu chỉ hỏi chính sách giữ nguyên nhu cầu, không lấy phí làm
ngân sách. order_request chỉ ghi nhận ý định/số lượng, không tạo hay xác nhận đơn.

## 6. Ranh giới và nguồn tương lai

NLU/chatbot chỉ import schema/interface/text utils, không đọc JSON, database,
API bên ngoài hoặc cấu hình mode. `main()` tạo repository qua
`create_catalog_repository(CATALOG_MODE)` rồi truyền vào logic. Đây là dependency
injection: đưa phần phụ thuộc vào hàm từ ngoài thay vì để hàm tự chọn nguồn.

`requirements.txt` có Pydantic 2.11.9 và tzdata 2026.4; requirements-dev kế thừa runtime và có
pytest 8.4.2. HTTP dùng urllib trong thư viện chuẩn, không SDK/framework agent.
`.env` chưa tự nạp; `.venv`/cache/bí mật bị khai báo ignore.

Chưa có `JsonCatalogRepository`, `DatabaseCatalogRepository`, `ApiCatalogRepository`
cho dữ liệu thật. KnowledgeRepository empty/sample đã có riêng ở mục 10.
Khi có nguồn catalog thật, triển khai ba phương thức, chuyển về
schema hiện tại và chạy contract test. Phần đặt hàng/API tương lai cũng chỉ gọi
interface, không dùng LLM như nguồn giá/tồn kho và không tạo đơn kinh doanh thật.

## 7. Structured NLU và hợp nhất với rule

`LLMNLU(BaseModel)` có `strict=True`, `extra="forbid"`; tất cả key bắt buộc,
nhưng trường không được nói đến dùng null/[]:

| Key | Kiểu/giới hạn |
| --- | --- |
| `intents` | List Intent đã chốt, 1–9 mục. |
| `product_mentions` | List chuỗi, tối đa 10; cụm khách nói, chưa có product_id. |
| `budget_vnd` | int >=0 hoặc null; ngân sách mỗi bánh, không phải giá bán. |
| `flavor`, `size` | str hoặc null; nhu cầu, không phải thông tin cửa hàng. |
| `servings`, `quantity` | int >=1 hoặc null. |
| `price_inclusive` | bool; dưới dùng false. |

Không chấp nhận số dạng chuỗi/boolean làm số hoặc field ngoài schema như
product_id, price_vnd, stock_status. Pydantic kiểm tra cấu trúc, không chứng minh
model hiểu đúng ý. `merge_llm_nlu(text, proposal, repository, rule_result=None)`
trả NLUResult: ID giữ từ tên/alias nguồn đã đối chiếu bằng rule; mention phải có
trong câu hiện tại sau chuẩn hóa; tự thêm/copy tên từ lịch sử thì từ chối
đề xuất và fallback rule có thông báo. Đại từ chung không
chọn bánh mới. Intent policy/order và cờ mơ hồ rule không bị LLM xóa.
`requires_clarification` thuộc NLUResult nội bộ và do code tính, không thuộc
LLMNLU. LLM không tự bật/tắt quyết định hỏi lại.

`check_llm_proposal(proposal, rule)` trả mã lỗi hoặc None: số trái regex,
mention không có trong câu hiện tại hoặc thuộc tính bổ sung thiếu từ chỉ loại
thông tin tương ứng bị từ chối và fallback rule. Size khác khoảng trắng được
coi tương đương. Flavor bánh đã nhận diện lấy nhãn chuẩn từ nguồn. Nhiều tên + thuộc tính
chưa liên kết chắc thì hỏi lại, kể cả empty. Giá trị LLM bổ sung chỉ là nhu cầu,
không phải xác nhận sản phẩm. Mơ hồ/lỗi nguồn không ghi đè nhu cầu.

## 8. HTTP client Ollama

| Hàm | Kết quả/quy tắc |
| --- | --- |
| `request_json(base_url, path, payload=None, timeout=30)` | GET nếu payload None, POST nếu có; dict ok/data/error/http_status. Kiểm tra 2xx và JSON object. |
| `select_model(base_url, configured_model="", timeout=5)` | dict model/error; chỉ GET /api/tags, timeout tối đa 5s. Tên cấu hình phải có chính xác, không thay bằng model khác. Bỏ cloud/remote. |
| `chat(messages, base_url, model, response_schema, timeout=30)` | LLMCallResult ok/content/error/model/http_status; POST /api/chat, stream=false, think=false, format=JSON schema, temperature=0, num_ctx=4096, num_predict=512. |
| `build_nlu_messages(message, history, needs)` | List ChatMessage: system, lịch sử riêng được truyền vào, user JSON câu hiện tại + nhu cầu. Mỗi message lịch sử gửi tối đa 1000 ký tự; không truyền menu. |
| `extract_nlu(message, history, needs, base_url, model, timeout=30)` | LLMExtractionResult data(LLMNLU hoặc None)/error/attempts/repaired. Sai JSON/validation thử sửa 1 lần (tổng tối đa 2), lỗi transport dừng ngay. |
| `choose_opening(facts, base_url, model, timeout=30)` | dict opening/error; LLMOpening enum 3 câu, lọc lựa chọn theo requires_clarification khi gửi model rồi kiểm tra lại. Không sinh thông tin nghiệp vụ; lỗi giữ mẫu code, không retry. |

Chat yêu cầu packet done=true, model đúng tên và message.content không rỗng.
Mã lỗi: invalid_config, connection_error, timeout, http_error, model_not_found,
invalid_response, invalid_nlu_json, invalid_opening_json, invalid_opening_choice.
Controller còn có invalid_nlu_mentions, nlu_rule_conflict, invalid_nlu_context
khi JSON đúng schema nhưng đề xuất sai kiểm tra nghĩa cơ bản.
HTTP 404 ở /api/chat coi model_not_found; ở tags là http_error. Không đưa nội dung
exception hoặc phản hồi lỗi dịch vụ vào text khách. Không gọi /api/pull.
Nhánh NLU có thể GET chọn model, tối đa 2 POST NLU và 1 POST lời mở đầu;
nhánh RAG thêm tối đa 2 POST nếu có tài liệu (mục 11). Câu chỉ hỏi policy bỏ
NLU/lời mở đầu. Không có deadline chung cho toàn lượt; temperature=0 không
bảo đảm ý nghĩa luôn đúng.

## 9. Conversation và chẩn đoán

`new_conversation(conversation_id=None, max_turns=CONTEXT_MAX_TURNS)` tạo dict:
`{id, history, needs, model, max_turns, order, unknown_streak}`. ID mặc định UUID; history list ChatMessage
role/content; needs là ChatState riêng; model cache tên đã kiểm tra hoặc None.
Người gọi phải giữ đúng object của khách, không dùng chung giữa khách.

`handle_message(message, repository, conversation, *, chat_mode=CHAT_MODE,
base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL, timeout=OLLAMA_TIMEOUT_SECONDS,
knowledge_repository=None, order_tools=None, storage_connection=None)`
trả ConversationTurn có:

- `conversation`: bản sao phiên mới, history tối đa max_turns*2 message, needs
  lưu riêng. Cắt lịch sử không xóa nhu cầu. Không sửa phiên đầu vào.
- `response`: ChatResponse đã chốt, catalog_status độc lập với lỗi LLM.
- `engine`: rule / ollama / rule_fallback / source_error.
- `model`: tên được chọn ở mode ollama hoặc None; có tên không chứng minh đã sinh thành công.
- `llm_error`: mã lỗi hoặc None; `nlu_attempts`: 0/1/2.
- `phrasing_status`: not_used / success / fallback. NLU thành công nhưng lời
  mở đầu lỗi vẫn engine=ollama, giữ phản hồi nghiệp vụ và nêu lỗi diễn đạt.

Rule không gọi client. Nguồn lỗi thì bỏ qua lời mở đầu LLM và trả source_error;
không đổi catalog thành mock hoặc trả sản phẩm từ model. Controller không có
connection thì chỉ RAM; main truyền tool/connection để lưu SQLite (mục 15).
Chưa tự quản lý phiên/phân quyền API hoặc xử lý đồng thời nhiều worker.
Giới hạn lượt/ký tự là giới hạn đơn giản, chưa phải bộ đếm token chính xác.

## 10. Nguồn kiến thức và chunk

`app.knowledge_loader.KnowledgeRepository(Protocol)` chỉ có
`get_knowledge() -> KnowledgeResult`. Hai adapter: EmptyKnowledgeRepository
và SampleKnowledgeRepository(data_path=None). Factory
`create_knowledge_repository(mode, path=None)` chỉ nhận empty/sample; không có
adapter nguồn thật. Logic chat/retrieval gọi Protocol, không biết JSON/path.

`PolicyClause` TypedDict: id/title/content/version là str không rỗng, is_mock
là bool. Sample yêu cầu root `{schema_version:"1.0", is_mock:true, clauses:[...]}`;
mỗi clause có đúng 5 key, ID không trùng, is_mock=true, content <=4000 ký tự.
`load_knowledge(mode, path=None)` kiểm tra dữ liệu tại biên, UTF-8 có/không BOM.

`KnowledgeResult = {status, knowledge_mode, is_mock, clauses, corpus_sha256, error}`:

| Status | Nghĩa |
| --- | --- |
| unconfigured | Empty/chưa truyền nguồn; không mở mẫu, clauses=[], hash=None. |
| no_results | File hợp lệ nhưng clauses rỗng. |
| success | Có điều khoản hợp lệ; hash SHA-256 của byte tài liệu. |
| error | File/JSON/schema lỗi: invalid_knowledge_data; exception nguồn: knowledge_source_error. Không dùng dữ liệu cũ. |

`KnowledgeChunk` có source_id/title/content/version/is_mock/score. Một clause
là một chunk, source_id=clause.id. Không suy dữ liệu catalog từ nội dung chunk.
`RetrievalResult = {status, knowledge_mode, is_mock, chunks, corpus_sha256,
retriever_version, error}`; success là có đoạn khớp từ, **không phải đủ đáp án**.
Nguồn hoạt động nhưng không khớp là no_results; thiếu/lỗi nguồn giữ status tương ứng.

`tokenize(text)` trả set từ chuẩn hóa và cặp âm tiết với từ đơn yếu; alias ngôn
ngữ ship/shipping/refund/payment, không chứa giá trị chính sách. Dấu tiếng Việt
bị bỏ nên còn trùng nghĩa. `build_keyword_index(knowledge)` trả dict tài liệu,
IDF, hash và retriever_version=keyword-v1. IDF=`log((N+1)/(df+1))+1`, df là số
điều khoản có term. Từ chưa có dùng trọng số `log(N+1)+1` trong mẫu số.

`retrieve(question, repository=None, top_k=3, min_score=0.15)` đọc lại nguồn,
dựng index RAM, tính tổng IDF khớp (tiêu đề x2) / tổng trọng số câu hỏi. Điểm
có thể >1 do ưu tiên tiêu đề, không là xác suất/cosine. Lọc >=min_score, sort
điểm giảm/ID tăng để ổn định, lấy <=top_k<=3. Không đọc development gold.
Không lưu index đĩa hoặc có script build_index.py; thay file dựng lại ở lần hỏi sau.

## 11. RAG output và trình bày

`RAGAnswer(BaseModel)` strict/extra forbid: supported:bool, quotes:list[SourceQuote]
tối đa 3; mỗi SourceQuote có source_id:str(1–100 ký tự), quote:str(1–4000).
Cả hai key bắt buộc; supported=false dùng quotes=[]. Không có answer tự do,
product_id, giá/tồn kho/allergen hoặc trường tạo đơn.

`build_policy_messages(question, retrieval)` trả system guard + user JSON có
question/chunks. Nội dung tài liệu **là dữ liệu**, không thêm vào system, không
thực thi như lệnh. Không gửi catalog/history/nhu cầu riêng vào RAG của lượt này.
`extract_policy_answer(question, retrieval, base_url, model, timeout=30)` trả
RAGExtractionResult `{data:RAGAnswer|None, error, attempts}`. Không có success
chunks thì no_policy_context/0 request. JSON/Pydantic sai sửa 1 lần (tổng <=2);
HTTP lỗi dừng; nguồn/quote sai không sửa thêm. Reuse client timeout/local/status.

`validate_rag_answer(answer, retrieval)` trả mã lỗi hoặc None: supported phải
khớp bool(quotes); source_id chỉ từ **các chunk đã gửi**, không chỉ toàn corpus;
quote không rỗng và là substring nguyên văn content. Mã invalid_rag_structure,
invalid_rag_source, invalid_rag_quote; client còn invalid_rag_json/no_policy_context.
Không chấp nhận một ID có thật nhưng chưa được retrieve trong lượt này.

`make_policy_response(retrieval, answer=None, *, engine="rule", llm_error=None,
attempts=0)` kiểm tra lại quote nếu có; output sai thì fallback hiển thị content
thật, không trình bày đoạn model sai. PolicyResponse:

- text/knowledge_mode/is_mock: nhãn nguồn và MÔ PHỎNG khi sample.
- status: unconfigured/no_results/error/insufficient/answered. answered chỉ
  nghĩa đã hiển thị trích đoạn hợp lệ; insufficient khi model nói chưa đủ.
- source_ids: ID unique đã được trích; citations gồm source_id/version/quote.
  Không có căn cứ được chấp nhận thì cả hai rỗng.
- retrieval: đầy đủ kết quả truy xuất; engine: rule/ollama/rule_fallback/not_used.
- error: mã lỗi nguồn; llm_error: lỗi model; attempts: 0/1/2 request RAG.

Rule/fallback hiển thị tối đa 3 đoạn đầy đủ với lời “để đối chiếu”, có thể kèm
đoạn thừa. Qwen chỉ chọn quote, code nối lời/nguồn/version. Một quote ngắn đúng
substring có thể bỏ điều kiện; ID/quote hợp lệ **không chứng minh đúng nghĩa**.
Không dùng chính sách sample để nhận đơn thật hoặc kiến thức LLM làm nguồn sản phẩm.

## 12. Routing, đánh giá và giới hạn hiện tại

Controller retrieve lượt hiện tại qua knowledge_repository. Rule intent policy
hoặc câu không có intent sản phẩm nhưng có chunk khớp sẽ đi nhánh chính sách;
greeting thuần không chuyển thành câu hỏi chính sách. Nếu vừa hỏi sản phẩm và
chính sách thì giữ hai nguồn và ghép kết quả, không dùng chunk làm catalog.
Câu chỉ hỏi chính sách bỏ bước LLM NLU/lời mở đầu, giữ nguyên needs.

`response.policy` lưu chẩn đoán riêng. Top engine có thể là RAG engine với câu
chỉ hỏi chính sách; nlu_attempts vẫn 0. Lỗi knowledge đặt engine=source_error,
catalog_status vẫn trạng thái catalog; cần đọc policy.status/error. Catalog lỗi
không chạy LLM hoặc biến thành thành công dù policy có thể có trích đoạn độc lập.

`scripts.evaluate_retrieval.evaluate(dataset, repository, top_k=3, min_score=0.15)`
trả báo cáo đo thật: 27 development case id/question/answerable/expected_source_ids.
Gold không là input retrieve; phải tham chiếu ID tài liệu hợp lệ. Báo cáo có
phiên bản/hash/thời gian/điểm/nguồn từng câu, Recall/Hit/MRR chỉ trên câu có đáp
án, abstention trên câu không có đáp án, exact-source-set trên tất cả. File đổi
giữa lần đo sẽ dừng để tránh kết quả từ corpus khác nhau.

CLI `python -m scripts.evaluate_retrieval` ghi evaluation/retrieval_report.json;
`python -m scripts.check_rag` thử HTTP thật riêng và ghi rag_smoke_report.json.
Embedding/vector/cosine/index đĩa chưa có; development đã dùng phát triển, chưa
là tập held-out (tập giữ riêng không dùng điều chỉnh thuật toán).

## 13. OrderDraft và FSM

`new_draft(conversation_id)` trả dictionary với id UUID/conversation_id/state,
revision=0, slots, verification={}, issues=[], review=None, submission=None,
tickets={} (reason → ticket). State chỉ BROWSING/COLLECTING/REVIEW/CANCELLED/HANDOFF.
Demo gửi thành công giữ REVIEW kèm submission.confirmed=true bất biến; đây
không là phép cho xác nhận lại bản khác. Empty gửi chờ tư vấn đưa HANDOFF.

| Slot | Kiểu/ý nghĩa |
| --- | --- |
| cake_need | str hoặc None, nhu cầu chưa xác minh. |
| product_id | str hoặc None, mã đề xuất; chỉ hợp lệ khi repo get_product đối chiếu và verification=verified. Empty giữ unverified, không xác nhận có bán. |
| size | str hoặc None, mong muốn; verified khi đúng một Variant.size. |
| toppings | list[str] hoặc None, [] = không topping; từng lựa chọn/giá phải có metadata. |
| quantity | int dương hoặc None, bool/float không hợp lệ. |
| cake_text | str hoặc None, "" = không viết; nguyên văn, len() code point để so giới hạn mock. |
| pickup_at | str ISO có +07:00 hoặc None; từ input YYYY-MM-DD HH:MM, Asia/Ho_Chi_Minh, tương lai. |
| fulfillment | pickup/delivery hoặc None; mong muốn, cần metadata nhận đơn tương ứng. |
| name/phone/address | str giả hoặc None: DEMO prefix tên/địa chỉ, TEST-... phone; giao cần address. Không xác minh contact thật. |

`update_slot(draft, field, value, now=None)` trả bản sao COLLECTING, revision+1,
review=None, reset verification/issues; không sửa input. Invalid input bị từ
chối; handler bỏ REVIEW cũ ngay cả khi nhập sửa sai. CANCELLED/HANDOFF cần
draft mới; đã confirmed không sửa trực tiếp.
`missing_slots` yêu cầu nhu cầu hoặc mã, size/quantity/toppings/cake_text/ngày/
hình thức/name/phone; giao thêm địa chỉ. Đây là điều kiện form thử nghiệm,
không là chính sách cửa hàng. Metadata nghiệp vụ thiếu không cản thu thập.

`create_review(draft, tools, now=None)` chỉ từ COLLECTING/REVIEW chưa gửi,
kiểm tra completeness/format, gọi check_availability/calculate_quote. REVIEW
snapshot có revision/slots_hash/catalog_fingerprint/mode/quote/availability.
Unknown giữ issues/verification unverified, không tự thêm mặc định nghiệp vụ.
Nguồn lỗi/unsupported không tạo REVIEW thành công. Quote chỉ là demo.

`confirm_review(draft, tools, needs)` yêu cầu REVIEW hợp lệ, gọi submit với key
`submit:{draft_id}:{revision}`. Sửa slot/tamper/source đổi → bỏ REVIEW, yêu cầu
xem lại. `xác nhận` là lệnh duy nhất gửi; OK/đồng ý không gửi. Đã gửi thì trả
submission cũ; nhu cầu cần xác minh đi ticket, không gửi staff qua mạng.
`handle_order_message` trả (draft mới, text) hoặc None để nhánh chat cũ xử lý.

## 14. Tool interface và kiểm tra nguồn

`OrderTools` TypedDict bốn callable (hàm có thể gọi), không có class service:

| Key/chữ ký callback | Trả về/ý nghĩa |
| --- | --- |
| check_availability(draft) | ToolResult; available/unavailable/unknown/unsupported/error cho khả dụng. |
| calculate_quote(draft) | available khi có quote đủ nguồn demo; unknown thiếu; unavailable khi thiếu tồn; unsupported nguồn thật chưa nối; error nguồn lỗi. |
| submit_order_request(draft, idempotency_key) | available = đã lưu demo/yêu cầu, không đồng nghĩa có hàng; data.kind/confirmed phân biệt. Lỗi/unknown/unavailable/unsupported không là xác nhận. |
| create_handoff_ticket(reason, summary, idempotency_key) | available = đã lưu ticket pending, không có staff nhận; error nếu lưu lỗi. |

`ToolResult={status, data:dict|None, error:str|None}`. Factory
`create_order_tools(repository, connection, conversation_id, now=None)` bind
repo/SQLite/owner; draft khác owner trả conversation_mismatch. Flow chỉ gọi
callback, không chọn nguồn/read JSON/SQL. Adapter local không tạo đơn thật,
kể cả can_accept_real_orders=true. Adapter thật phải triển khai kiểm tra và
tạo đơn hợp lệ qua nguồn thực tế, chốt schema/tests trước mở mode; chưa có stub.

`inspect_order(repository, draft, now)` tạo verification/issue/availability/
quote từ một lần đọc Product và metadata; không tin cờ draft. Giá/size/stock/
min_lead_hours/customization từ get_product. Source exception/error luôn
order_source_error, không đổi thành available/no_results.
Optional `OrderMetadataRepository.get_order_metadata(product_id)` trả
`{status, metadata, error}`; MockCatalogRepository triển khai thêm, không đổi
interface catalog cũ. Root metadata sample schema_version=1.0/is_mock=true,
products mapping, dữ liệu ở data/mock_order_metadata.json:

- toppings: mapping tên → giá VND mỗi bánh hoặc None; null = chưa biết.
- max_cake_text_length, cake_text_price_vnd, delivery_fee_vnd: int>=0 hoặc None.
- fulfillment_modes: list pickup/delivery hoặc None.
- stock_quantity: mapping variant_id → int>=0 hoặc None.

Writing cần customization có nhãn chuẩn "ghi chữ trên bánh", limit/phí biết;
không writing thì not_applicable. Lead time kiểm tra pickup >= now + metadata
min_lead_hours. Topping/size ngoài nguồn unverified, không xác nhận có lựa chọn.
Stock in_stock + count >=quantity mới available; out_of_stock/count thiếu là
unavailable; preorder/unknown/count null là unknown. Không giữ/trừ stock demo.

Quote đủ điều kiện: unit = base variant price + tổng topping + writing fee;
total=unit*quantity + delivery_fee. Pickup không phí giao, delivery cần fee từ
metadata. Empty quote=None; không suy phí từ sample_policies/LLM. Source hash
Product+metadata giúp submit phát hiện giá/giới hạn/khả dụng đổi sau REVIEW.
Catalog mock đọc JSON lúc tạo repo; restart/nạp phiên sẽ so với repo mới,
metadata mock đọc mỗi lần; không claim price JSON tự reload như knowledge.

## 15. SQLite, ticket và lịch sử

`open_storage(path)` mở file/:memory:, relative root, row_factory/foreign_keys,
schema user_version=1; phiên bản khác từ chối, chưa migration tự động.
`save_conversation/load_conversation/list_records` chỉ ở storage.py; 4 bảng:
conversations(id,payload,updated_at), drafts(id,conversation_id,revision,payload),
submissions(id,conversation_id,draft_id,idempotency_key UNIQUE,payload_hash,
kind,payload,created_at), tickets(id,conversation_id,idempotency_key UNIQUE,
payload_hash,payload,created_at). Không bảng sản phẩm/giá/stock.
submissions.kind chỉ waiting_consultation/demo_order; chỉ demo confirmed=true.

`save_record` chỉ whitelist submissions/tickets, mọi giá trị SQL có placeholder.
Cùng key/cùng hash/owner trả record ID cũ; khác payload/owner là
idempotency_conflict. Bản ghi submission/ticket bất biến. `save_conversation`
cập nhật draft riêng và chống reassign draft ID sang khách khác.
Helper không commit; caller `with connection:` commit/rollback toàn lượt.
Database lỗi ở handler trả storage_error, không tuyên bố đã xác nhận; main
đóng connection trong finally. Mode/nguồn errors đọc riêng catalog/knowledge/tool/storage.

`detect_handoff(message, unknown_streak)` dùng regex cho customer_requested,
severe_allergy, complaint, change_confirmed_order; counter >=2 thêm
two_unknown_turns. Flow unknown metadata thêm needs_verification. Sửa/hủy
request đã gửi dùng ticket thay vì xóa/sửa record cũ. Ticket reason/summary/
status=pending/is_mock=true/note, không gửi email/Slack/nhân viên.
Summary không có name/phone/address, nhưng có nhu cầu/ID mong muốn chưa xác minh.
Slot chữ/contact/topping là dữ liệu, không kích hoạt lệnh handoff từ nội dung;
nhu cầu dị ứng nghiêm trọng vẫn trigger. Câu hỏi policy có từ đổi trả sau
confirmed không tự bị coi là sửa đơn; chỉ trường sửa/đề nghị thay đổi tương ứng.

`finish_turn` giới hạn history như cũ, sanitize contact/email/chuỗi số; slot
contact chỉ chấp nhận DEMO/TEST, lệnh FSM không gọi LLM. Chưa là bộ phát hiện
PII đầy đủ trong mọi câu tự do. `unknown_streak` riêng: fallback không có
policy/error tăng, câu hiểu được reset; lỗi nguồn không tính là không hiểu.
`tiếp tục: ID` main nạp phiên local; chưa có authentication/phân quyền Internet.

## 16. API và phiên web giai đoạn 6

`app.api.create_app(...)` nhận catalog_repository/knowledge_repository,
db_path/chat_mode/knowledge_mode/base_url/model/timeout/session_seconds.
Mặc định lấy app.config; app.api:app là instance Uvicorn. DI (dependency
injection: truyền thành phần phụ thuộc vào) không đổi controller/repos cũ.
Không tự nạp .env. Nguồn cùng cấu hình chọn khi khởi động, không chọn từ body.

| HTTP/đường dẫn | Request | Response thành công |
| --- | --- | --- |
| GET /health | Không cần token | 200: status=ok, data_mode, knowledge_mode, chat_mode, message_max_length=2000. Chỉ báo API sống; không thử sinh model hoặc chứng minh nguồn hoạt động. |
| POST /api/conversations | JSON `{}` | 201: conversation_id, session_token, expires_in_seconds=28800, data_mode, knowledge_mode, chat_mode, state=BROWSING. |
| POST /api/chat | JSON conversation_id/message; Bearer header | 200: ChatView bên dưới. |
| GET /api/order-requests/{id} | Bearer header | 200: OrderRequestView từ submissions, chỉ owner token; dùng được cho waiting_consultation và demo_order. |
| GET /; GET /static/... | Không cần token | index.html và CSS/JS cùng origin. |

Ví dụ body chat (ID do API cấp, không thay thế token):

```json
{"conversation_id": "ID nhận từ POST conversations", "message": "socola dưới 300k"}
```

Header `Authorization: Bearer <session_token nhận lúc tạo phiên>`; không ghi
token vào URL/file nguồn/log hoặc gửi cho dịch vụ khác. Token random 32 byte,
RAM server chỉ giữ hash/owner/expiry/lock. Hết hạn sau 8 giờ, không gia hạn
trượt. UI giữ token RAM, không localStorage/cookie; reload tạo phiên mới.
Registry tối đa 200 phiên chưa hết hạn, đầy trả 503/session_capacity_reached.
Chạy 1 worker; restart mất registry nên token cũ 401, SQLite vẫn giữ bản ghi.
Không có API nạp conversation bằng UUID, lịch sử hoặc ticket của khách khác.

Pydantic strict/extra=forbid: message chuỗi 1–2000 ký tự, không chỉ khoảng
trắng; giữ nguyên input để xử lý chữ trên bánh. Tối đa là giới hạn kỹ thuật,
không giới hạn nghiệp vụ. ID chuỗi 1–100; route không tin state/product_id/
confirmed/giá từ client. Không có endpoint xác nhận trực tiếp; gửi lệnh chat
`xác nhận` và controller kiểm tra REVIEW như cũ.

ChatView luôn có:

| Field | Kiểu/quy tắc |
| --- | --- |
| conversation_id/message | str: phiên đúng owner, văn bản controller. |
| state | BROWSING/COLLECTING/REVIEW/CANCELLED/HANDOFF; không phải needs. |
| products | list ProductView: mirror schema Product/Variant; không tự tạo fallback product. Unknown price/servings là null, stock unknown. |
| sources | list SourceView {source_id,version,quote,is_mock}, từ policy.citations đã kiểm tra; empty/error có thể []. ID không chứng minh đúng nghĩa. |
| data_mode/knowledge_mode | str: hai nguồn độc lập; hiện catalog empty/mock, knowledge empty/sample. Capability lỗi trả unknown, không giả thành empty. |
| catalog_status | unconfigured/no_results/success/error, không suy từ list rỗng. |
| policy_status | null khi không hỏi policy; nếu có đọc status policy riêng. |
| requires_confirmation | Có REVIEW chưa gửi và availability khác unavailable. Không cho phép tự vượt recheck của service. |
| review | null hoặc ReviewView: revision/data_mode/slots/verification/issues/quote/availability. Chỉ khi state REVIEW chưa submission; unknown có summary và chưa có quote. |
| request_id/demo_order_id | str hoặc null; chỉ một ID khi có submission tương ứng. Yêu cầu chờ tư vấn không là demo_order. |
| engine/errors | engine từ controller; errors list mã catalog/storage/LLM/knowledge. Tool nghiệp vụ còn trình bày lỗi trong message; không coi errors=[] là mọi điều kiện đạt. |

OrderRequestView mirror bản ghi: id/conversation_id/draft_id/revision/kind,
slots/verification/issues/quote/data_mode/is_mock/confirmed. Kind chỉ
waiting_consultation hoặc demo_order. confirmed phải đúng kind; waiting có
quote=null, demo có quote mẫu. is_mock=true cho cả record yêu cầu học tập
empty và đơn mock; không phải nguồn thật. API không trả hash idempotency,
registry token hoặc history. SlotsView giữ đúng tên/kết quả FSM hiện có.

Lỗi HTTP: 401 token thiếu/sai/hết hạn; 404 conversation hoặc record không
thuộc owner/không có; 422 sai schema (chỉ loc/type, không echo input); 503
storage_unavailable/capacity; 500 invalid_server_response nếu response sai
Pydantic. HTTP 200 vẫn có thể catalog error/LLM fallback: đọc status/engine/
errors/message. Ticket/error tool không biến thành đơn xác nhận.

GET bản ghi gọi storage.load_order_request(connection, record_id,
conversation_id), SQL có hai điều kiện owner+ID. Route def chạy threadpool;
SQLite mở/dùng/đóng cùng thread, lock riêng conversation giữ thứ tự cập nhật
trong process; khách khác không chung lock/lịch sử. API responses no-store,
nosniff; frontend textContent và tạo DOM, không nội suy HTML. Không CORS hoặc
nguồn asset ngoài. Chưa chống tải lớn/multi-worker, đăng nhập hay triển khai Internet.

## 17. Bổ sung AI mặc định và slot đặt bánh tự nhiên

Mặc định CHAT_MODE=ollama, timeout config=60. run_web.py luôn đặt ollama trước
import app, ghi đè rule còn sót trong terminal, không đổi model/catalog/DB đã
cấu hình hoặc tải model. Rule vẫn dùng khi chọn rõ để thử offline; process
đang chạy giữ cấu hình/code cũ cho đến restart. Không tự tắt server người dùng.

LLMOrderSlots Pydantic strict/extra=forbid gồm product_mentions(list[str]),
cake_need/size/cake_text/pickup_at/name/phone/address(str|null), quantity(int
dương|null), toppings(list[str]|null), fulfillment(pickup/delivery|null),
needs_clarification(bool). Không product_id/price_vnd/confirmed/tool action.
Thông tin không nêu phải null, product_mentions=[]; [] topping chỉ khi nói
không topping, cake_text="" chỉ khi nói không viết chữ.

extract_order_slots(message,draft,base_url,model,timeout=30) gửi câu hiện tại
và context slot của đúng draft, không history/contact cũ/menu. Trả dict
data(LLMOrderSlots|null)/error/attempts. JSON/schema sai sửa một lần (tổng2),
transport lỗi dừng. Code config truyền timeout60; default30 của hàm client
độc lập giữ tương thích. Model không tự REVIEW, submit hoặc gọi tool.

order_nlu.should_extract_order kiểm tra câu đặt có thông tin hoặc câu cập
nhật trong COLLECTING/REVIEW chưa submission. Lệnh thuần/field:value/handoff
không qua LLM. Nguồn catalog error bỏ model; lời chỉ tư vấn/policy vẫn nhánh cũ.
contains_unsafe_contact chặn contact không nhãn giả/số phone/email cơ bản;
guard không là phát hiện PII đầy đủ. Lượt bị guard không gửi model/không lưu
raw input vào history/cake_need; trả fake_contact_required.

check_order_proposal đối chiếu cụm/size/topping/chữ/contact/ngày trong câu
hiện tại. Quantity căn cứ số cạnh bánh/cái/chiếc/hộp hoặc cụm số lượng, hỗ trợ
một–mười cơ bản. Ngày không đoán 'mai'; fulfillment cần marker nhận/giao.
Nhiều bánh/thuộc tính mơ hồ từ rule hoặc model hỏi lại. Đây là grounding cơ
bản (kiểm tra căn cứ), chưa chứng minh đúng nghĩa mọi liên kết/phủ định.

apply_order_proposal gọi update_slot từng field trên bản sao; sai một field
từ chối mọi thay đổi AI của lượt, bỏ REVIEW cũ. Null giữ slot cũ. ID chỉ từ
NLU rule đã đối chiếu tên/alias repository; mention chỉ nhu cầu unverified.
Chọn bánh mới xóa ID cũ nếu chưa đối chiếu được tên mới. Nguồn/giá/stock/metadata
vẫn kiểm tra ở REVIEW/submit. Không sửa record đã confirmed: chuyển ticket.

ConversationTurn engine=ollama khi nhận slot AI hợp lệ, rule_fallback khi lỗi/
mơ hồ/thiếu căn cứ; nlu_attempts là lần trích/sửa OrderSlots ở nhánh này,
phrasing_status=not_used vì code viết câu hỏi/trạng thái. Lệnh code có engine
rule dù mode ollama. ChatView/API routes và schema FSM/SQLite không đổi.

collect_instructions hỏi từng trường thiếu, không in tên cake_need/product_id
cho người dùng. business_command_text che phần ghi chữ có ngoặc khỏi bộ nhận
lệnh; sửa số lượng/size/topping/ngày/chữ sau demo confirmed đi HANDOFF.
