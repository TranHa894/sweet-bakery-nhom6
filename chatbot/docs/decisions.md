# Quyết định — trạng thái hiện tại 06/10/2026

D74–D96 bên cuối file là quyết định local completion và sửa lỗi hiện hành. D01–D73 giữ lịch sử; D71 (bypass model), D31/D47/D69 (fallback), D57 (SQLv1/catalog riêng), D56 (chỉ ngày tuyệt đối), D50 (state confirmed) được thay theo bảng mới. Không thực hiện stage7 tổng thể; có đánh giá hẹp intent/context theo yêu cầu mới.

# Quyết định kỹ thuật

Ngày cập nhật: 03/10/2026. D01–D13 là lịch sử giai đoạn 1; D14–D26 giai đoạn 2;
D27–D39 áp dụng giai đoạn 3; D40–D49 giai đoạn 4; D50–D60 giai đoạn 5;
D61–D68 áp dụng giai đoạn 6; D69–D73 là bổ sung AI theo yêu cầu sau đó.
Quyết định mới ghi rõ chỗ thay quyết định cũ.

| Mã | Quyết định | Lý do và giới hạn |
| --- | --- | --- |
| D01 | Dùng Python 3.12.x; môi trường hiện có 3.12.10. | Tận dụng Python có sẵn và nhánh còn được hỗ trợ; chưa kiểm tra dependency giai đoạn sau. |
| D02 | Dùng `venv` + `pip` + hai file requirements. | Thư mục ban đầu không có cấu hình; cách này dễ giải thích cho người mới. `uv` có trên máy nhưng chưa cần dùng. |
| D03 | Chỉ dùng thư viện chuẩn `os`; chưa thêm pytest/FastAPI/thư viện AI. | Chương trình tối thiểu chưa cần dependency; kiểm tra bằng lệnh chạy và kiểm tra cấu hình, không tạo test lặp lại `print`. |
| D04 | `config.py` đọc biến môi trường, chưa đọc file `.env`. | `os.getenv` đủ cho bốn biến; tránh tự viết parser hoặc thêm thư viện chỉ để nạp file. README ghi rõ `.env.example` là mẫu. |
| D05 | Mặc định `CATALOG_MODE=empty`, `CHAT_MODE=rule`; model để rỗng. | Chưa có dữ liệu và chưa biết RAM/GPU; không tự giả định có sản phẩm hoặc chọn/tải model. |
| D06 | Chuẩn hóa mode bằng `strip().lower()` và báo `ValueError` khi sai. | Chấp nhận khoảng trắng/chữ hoa nhưng không lặng lẽ chọn nguồn khác khi cấu hình sai. URL/model chưa được xác thực ở giai đoạn này. |
| D07 | `main()` chỉ in trạng thái; dùng guard `if __name__ == "__main__"`. | Import không tự chạy phần thông báo, không gọi mạng hoặc tạo dữ liệu. Guard là điều kiện bảo vệ điểm chạy. |
| D08 | Tách nguồn dữ liệu qua interface repository ở giai đoạn sau. | Logic chat/order/API không phụ thuộc JSON, database hay schema API bên ngoài. Chưa cần class hoặc adapter trong giai đoạn 1. |
| D09 | `mock`/`ollama` được nhận là giá trị cấu hình, chưa triển khai chức năng. | Thông báo phải trung thực; chọn mode không có nghĩa đã nạp dữ liệu hay đã nối model. |
| D10 | `data/` có hướng dẫn, `tests/` để trống; không tạo placeholder adapter. | Chỉ tạo file hữu ích. Git không lưu thư mục trống; thêm test thật sẽ tạo `tests/` khi cần. |
| D11 | `.venv` không thuộc mã nguồn và bị `.gitignore` bỏ qua. | Môi trường có thể tạo lại theo requirements; không chia sẻ bản môi trường của một máy. Chưa chạy `git init`. |
| D12 | Không tạo database sản phẩm hoặc dữ liệu giả ở giai đoạn 1. | Người dùng chưa có nguồn thật. SQLite cho hội thoại/đơn mô phỏng sẽ được cân nhắc riêng sau. |
| D13 | Truyền script kiểm tra có chữ Việt bằng UTF-8 trên PowerShell 5.1. | Pipe mặc định ASCII làm hỏng chuỗi kỳ vọng ở lượt đầu. Chỉ đổi mã hóa trong tiến trình kiểm tra, không thay đổi cấu hình máy hoặc nội dung chương trình. |

## Giả định đã dùng

- Chạy tại `D:\Chatbot` bằng PowerShell; đường dẫn có thể thay đổi trên máy khác.
- Chưa cần biến môi trường bí mật hoặc file `.env` để chạy mặc định.
- Trạng thái chính sách thật luôn là chưa có ở giai đoạn 1, kể cả khi chọn `mock`.
- Giai đoạn 2 được đề xuất cho hợp đồng catalog và nguồn empty/mock; chỉ thực hiện
  sau yêu cầu tiếp theo của người dùng.

Không có tên hàm/schema cũ phải đổi vì folder ban đầu trống. Mọi thay đổi hợp đồng
sau này phải cập nhật code liên quan, `contracts.md` và thêm lý do vào file này.

## Quyết định giai đoạn 2

| Mã | Quyết định | Lý do và giới hạn |
| --- | --- | --- |
| D14 | Giữ `main()`/config, thay đầu ra 5 dòng bằng vòng chat terminal. | Giai đoạn 2 yêu cầu chat; hợp đồng và README cập nhật, stage_01 giữ làm lịch sử. |
| D15 | Schema TypedDict dạng hàm; runtime vẫn dict, validation bằng hàm. | Không thêm Pydantic trước giai đoạn API; không dùng class cho logic/schema nghiệp vụ. Type hint không tự validate. |
| D16 | CatalogRepository dùng Protocol, ba phương thức; create_catalog_repository chọn nguồn. | Dependency injection giúp đổi mock/empty mà không sửa chatbot/NLU. Chỉ class repo/interface. |
| D17 | Fixture mock JSON 5 sản phẩm, ID ổn định; MockCatalogRepository đọc file. | Tách dữ liệu tên/giá/tình trạng khỏi logic và thực hành JSON; chưa phải JsonCatalogRepository cho nguồn thật. |
| D18 | Bốn status; None cho giá/số người chưa biết, unknown cho stock. | Không gộp chưa có nguồn, không tìm thấy và lỗi thành []; không giả giá 0 hoặc hết hàng. |
| D19 | Search trả chỉ biến thể thỏa đồng thời giá/số người/size, get trả đầy đủ. | Không ghép giá rẻ ở size nhỏ với sức phục vụ của size lớn. Return bản sao để caller không làm hỏng mẫu. |
| D20 | NLU regex/từ khóa nhiều intent; tên/alias/ID luôn từ nguồn. | Dễ đọc và kiểm thử, chưa cần model. Từ vựng vị phổ thông chỉ ghi nhận nhu cầu; vị chuẩn của bánh lấy từ nguồn. |
| D21 | Hỏi lại nhiều giá/thuộc tính, nhiều bánh + giá trị, alias trùng, loại trừ chưa hỗ trợ. | Chưa có thuật toán liên kết thực thể tổng quát; không tự gán thuộc tính cho bánh. Câu chỉ so giá/size nhiều bánh có thể trả chung. |
| D22 | Nhu cầu trong RAM, trả state mới, không mutate state đầu vào. | Đủ hội thoại ngắn, không tạo persistence/SQLite. Nhắc bánh mới reset bộ lọc; chỉ thuộc tính nối tiếp; mới/reset xóa toàn bộ. |
| D23 | Ngân sách và số người hiểu mỗi bánh; quantity chỉ ghi nhận. | Chưa có giỏ hàng/đơn/tồn kho số lượng. Dưới là <, tối đa là <=; tầm/khoảng là ngưỡng tối đa đơn giản. |
| D24 | Chính sách thiếu thì nói thiếu; order_request chưa tạo đơn; ollama thông báo và dừng. | Không giả chức năng giai đoạn sau hoặc tự rơi về một mode khác. |
| D25 | Thêm pytest==8.4.2 vào requirements-dev, runtime giữ thư viện chuẩn. | Đủ test hành vi và source boundary; gói nhỏ phù hợp Python 3.12, không cài AI. |
| D26 | Bắt exception rộng chỉ tại biên adapter, trả mã lỗi chung. | Lỗi nguồn không thành no_results; không đưa chi tiết riêng/bí mật của exception vào response. |

Protocol chỉ khai báo chữ ký, không phải adapter giả hoạt động. Nguồn JSON thật,
database/API và policy sẽ chỉ được tạo khi có yêu cầu và dữ liệu phù hợp.

## Quyết định giai đoạn 3

| Mã | Quyết định | Lý do và giới hạn |
| --- | --- | --- |
| D27 | Pydantic 2.11.9 cho LLMNLU/LLMOpening; giữ TypedDict nghiệp vụ. | Người dùng yêu cầu validate output LLM ngay giai đoạn 3, thay phần trì hoãn Pydantic ở D15. Hai class schema cần để dùng validation/JSON schema, không biến logic thành class. |
| D28 | Client dùng urllib, HTTP local loopback, không SDK. | Giữ ít dependency, dễ giải thích GET/POST/timeout/status; chỉ gọi tags/chat, không tải model/dịch vụ bên ngoài. |
| D29 | Model rỗng chọn Qwen local đã cài nhỏ nhất theo file size; tên chỉ định phải khớp chính xác. | Đã thấy qwen3.5:4b trên máy, không hardcode tên runtime và không tự đổi tên cấu hình sai. Bỏ cloud/remote; size nhỏ không bảo đảm phù hợp RAM/tốc độ. |
| D30 | stream=false, think=false, nhiệt độ 0, context 4096, output tối đa 512 token. | Dễ nhận một JSON; tránh stream/thinking kéo dài. Các giới hạn không bảo đảm nghĩa đúng hay thời gian phản hồi. |
| D31 | JSON schema + strict validation; sửa tối đa một lần, transport không retry. | Không dùng JSON sai cho nghiệp vụ, tránh vòng sửa vô hạn. Lỗi thì rule có nhãn; thay hành vi dừng ollama của D24. Catalog vẫn giữ nguyên. |
| D32 | Mention phải thuộc câu hiện tại; ID chỉ từ đối chiếu tên/alias repository bằng rule. | LLM không biết menu và không phải nguồn xác minh. Giữ policy/order guard; câu gốc nhiều số/bánh/thuộc tính mơ hồ thì hỏi lại. Đề xuất sai bị từ chối theo D39. |
| D33 | LLM chọn 1/3 lời mở đầu, code trình bày toàn bộ thông tin nghiệp vụ. | Structured output đúng kiểu vẫn có thể bịa nội dung. Enum và kiểm tra cờ hỏi lại ngăn tự viết giá/tồn kho/chính sách/đơn. Giới hạn: chưa diễn đạt tự do cả câu trả lời. |
| D34 | Conversation dict mới bằng uuid/deepcopy; lịch sử 6 lượt, nhu cầu lưu riêng. | Mỗi khách cần phiên độc lập; bỏ lịch sử cũ không mất ngân sách/vị/số người. Chưa lưu bền, quản lý API phiên hay đồng thời. |
| D35 | Giữ respond/analyze_message và schema cũ; respond thêm keyword-only nlu tùy chọn. | Tương thích 3 tham số cũ; controller có thể đưa NLU đã kiểm tra. Main chuyển sang handle_message; test CLI cập nhật theo chức năng mới, không bỏ test an toàn. |
| D36 | Lỗi truy vấn cuối không ghi đè nhu cầu hoặc thêm lời mở đầu thành công. | Rà soát phát hiện nhánh lỗi cuối của stage 2 đã cập nhật state trước; sửa nhỏ, giữ error và trạng thái cũ, không viết lại chatbot. |
| D37 | Timeout mặc định 30s mỗi HTTP, cho phép tăng tối đa 60s qua cấu hình. | Thử thật ban đầu 30s có timeout; vẫn chạy rule. Không tự thay default theo một lần đo; latency và hạn chế kiểm tra ghi ở progress. |
| D38 | Cờ requires_clarification chỉ do code tính, không đưa vào LLMNLU. | Thử thật thấy Qwen luôn bật cờ dù câu rõ. Schema LLM chỉ trích thông tin; rule/merge kiểm tra liên kết nhiều bánh, mâu thuẫn số và mention tự thêm để hỏi lại. Giữ tên cờ ở NLUResult cũ. Chưa xử lý mọi mơ hồ ngôn ngữ. |
| D39 | Sau Pydantic có check_llm_proposal; đề xuất sai quay về rule có mã lỗi, không thử sửa tiếp. | Thử thật thấy model copy mention từ lượt cũ. Kiểm tra literal mention, số so với regex và dấu hiệu thuộc tính hiện tại giữ cập nhật 400k đúng; chưa kiểm tra nghĩa tổng quát. Enum lời mở đầu lọc theo cờ code để tránh câu hỏi lại sai. |

Không đổi tên/schema Product/Variant hoặc interface catalog. Chưa thêm FastAPI,
SQLite, embedding, nguồn dữ liệu thật hoặc đơn hàng. Không tải model.

## Quyết định giai đoạn 4

| Mã | Quyết định | Lý do và giới hạn |
| --- | --- | --- |
| D40 | Làm RAG tài liệu theo yêu cầu mới, chưa làm API đề xuất trước. | next_steps là đề xuất; yêu cầu thực tế của người dùng quyết định phạm vi. Giữ code giai đoạn 3, chỉ bổ sung cần thiết. |
| D41 | KnowledgeRepository độc lập với CatalogRepository, get_knowledge() và empty/sample. | Nguồn chính sách và menu có thể khác trạng thái. Main inject cả hai; không đổi interface catalog hoặc đọc JSON trong hội thoại. policy_available của catalog vẫn false vì catalog không cung cấp chính sách. |
| D42 | KNOWLEDGE_MODE mặc định empty; sample cần root/per-clause is_mock=true. | Chưa có chính sách thật. Empty không mở mẫu. File lỗi là error, clauses rỗng là no_results. Không đổi flag để giả adapter thật. |
| D43 | Một điều khoản = một chunk; từ khóa với IDF/tiêu đề x2, tối đa 3. | Đơn giản, chạy CPU/thư viện chuẩn. Từ ít phổ biến được điểm cao; bỏ dấu dễ trùng nghĩa, từ đơn yếu chỉ dùng theo cặp âm tiết. Vẫn có đoạn thừa và câu ngoài phạm vi khớp từ. |
| D44 | Index RAM keyword-v1 dựng lại mỗi lần đọc, SHA-256 byte tài liệu. | Chỉ 5 điều khoản, chưa cần lưu index hoặc build_index.py. Nội dung đổi được nhận ngay kể cả chỉ đổi version/định dạng; chi phí O(số điều khoản) mỗi lượt, không phù hợp nguồn lớn. |
| D45 | Qwen chọn quote nguyên văn bằng RAGAnswer/SourceQuote strict; code trình bày nguồn. | Đây là RAG trích xuất, mở rộng D33 cho chính sách nhưng chưa sinh lại tự do. Không nhận field answer/order; nguồn phải trong chunk đã gửi. ID/substring đúng vẫn chưa chứng minh đúng ý hoặc đủ điều kiện. |
| D46 | Tài liệu chỉ trong user JSON, system quy định là dữ liệu; không nhận lệnh từ tài liệu. | Giảm rủi ro prompt injection (nội dung cố khiến model bỏ quy tắc). Code không thực thi quote hoặc tạo đơn. Guard không bảo đảm model luôn chọn đoạn đúng. |
| D47 | JSON/schema sai sửa 1 lần; ID/quote sai hoặc HTTP lỗi không sửa tiếp, fallback trích đoạn thật. | Giữ giới hạn client cũ, tránh vòng retry dài. Nguồn lỗi/thiếu không gọi model để bịa. Rule chỉ đưa đoạn đối chiếu, không tuyên bố trả lời đầy đủ. |
| D48 | Câu chỉ hỏi chính sách không cập nhật nhu cầu bánh; thêm response.policy và keyword-only knowledge_repository/include_policy_notice. | Phí giao hàng không thành ngân sách bánh. Giữ tên/tham số cũ, Product/Variant không đổi. Engine/attempts RAG riêng với NLU; lỗi nguồn giữ chẩn đoán. |
| D49 | Đo 27 câu development và smoke HTTP riêng; chưa triển khai embedding. | Gold chỉ chấm, không đưa vào retriever. Báo cáo có corpus/dataset hash và phiên bản; development không là held-out. Không tải model/thêm AI nặng khi chưa có yêu cầu; chuẩn bị pin revision/index manifest rồi mới thử CPU. |

Giả định: chạy local, 5 điều khoản đủ ngắn (content <=4000 ký tự/điều khoản).
Không cache tài liệu; chưa đếm token cả prompt. Thuật toán và ngưỡng 0,15 là
mặc định học tập, không là xác suất đúng hoặc mức chất lượng production.
Lỗi truy vấn bánh chung giữ tên cũ và greeting nhắc nhu cầu cũ do người dùng
báo trước stage 4 chưa được sửa trong giai đoạn này; ghi ở next_steps.

## Quyết định giai đoạn 5

| Mã | Quyết định | Lý do và giới hạn |
| --- | --- | --- |
| D50 | FSM/slot bằng dictionary và hàm, một sản phẩm/biến thể mỗi draft. | Người học Python cơ bản, không cần framework/class FSM. Quantity >1; chưa giỏ nhiều dòng. REVIEW khác confirmed; gửi empty đưa HANDOFF, demo giữ REVIEW kèm submission bất biến. |
| D51 | Lệnh một trường mỗi dòng và xác nhận chính xác sau REVIEW; không dùng LLM để xác nhận đơn. | Dễ kiểm tra và tránh nhầm OK là consent gửi; tư vấn/RAG cũ vẫn hoạt động. Chưa hiểu slot tự do toàn bộ. |
| D52 | REVIEW có revision, hash slots và fingerprint product/metadata; gửi kiểm tra lại. | Sửa trường, sửa sai hoặc nguồn đổi không dùng lại REVIEW. Không tin verification do caller tự gắn. Đơn đã gửi giữ bản ghi bất biến; sửa/hủy chuyển ticket. |
| D53 | OrderTools là TypedDict bốn callable, factory tạo closure repo/connection/owner. | Dependency injection đơn giản, FSM không đọc JSON/SQL. Optional OrderMetadataRepository không đổi ba phương thức catalog/Product/Variant. Nguồn thật chưa có adapter, unsupported dù bật cờ capability. |
| D54 | Thêm mock_order_metadata.json cho giới hạn/phụ phí/tồn số lượng. | Giá bánh/min_lead_hours vẫn từ Product, metadata chỉ là dữ liệu demo có root is_mock=true. Không đưa giá trị nghiệp vụ vào logic/prompt, không dùng sample_policies để tính đơn. |
| D55 | Unknown không có mặc định nghiệp vụ; cần xác minh và không tạo demo confirmed. | Topping/size mới là mong muốn, limit chữ/lead time/phí/stock thiếu giữ unknown/unverified. Empty lưu yêu cầu chờ tư vấn, không tính quote thật. |
| D56 | ZoneInfo Asia/Ho_Chi_Minh + tzdata==2026.4; chỉ ngày/giờ đầy đủ, tương lai. | Windows thực tế thiếu IANA; cài gói nhỏ 347 kB, không tự dùng timezone giả hoặc đoán 'mai'. Lead time dùng metadata riêng, không giới hạn đặt mặc định. |
| D57 | SQLite schema v1 gồm 4 bảng; SQL tham số; caller transaction/commit. | Lưu/nạp phiên/draft/submission/ticket, tách database sản phẩm. Foreign key/owner guard, rollback khi database lỗi. Không gửi thông báo nhân viên hoặc tạo sản phẩm trong DB. |
| D58 | Unique idempotency_key + payload hash + scope owner. | Cùng key/payload trả ID cũ, khác payload/khách báo conflict. Key draft_id/revision ổn định cho retry, không đổi khi bấm xác nhận lại. Không là kiểm soát mọi đơn trùng nội dung hoặc giữ tồn kho. |
| D59 | Liên hệ thử nghiệm dùng DEMO/TEST prefix, không lưu contact đầu vào thô. | Đây là quy tắc kỹ thuật bảo vệ bài tập, không là chính sách cửa hàng. Lệnh slot không gửi LLM; history che contact/email/chuỗi số. Chưa là hệ thống chống PII đầy đủ cho câu tự do. |
| D60 | Ticket pending local và chưa có nhân viên nhận; giữ counter không hiểu riêng từng phiên. | Handoff theo các trigger user yêu cầu, không gửi email/Slack; mẫu regex còn đơn giản. Caller có thể nạp ID local để test persistence, chưa đăng nhập/phân quyền. |

Tận dụng nền stage 4 (170 test đạt trước sửa); không viết lại NLU/RAG/client
hoặc làm API/UI. Không tải model. Giữ lỗi giữ tên bánh cũ trong backlog, không
claim đã sửa ở stage 5. Tồn số lượng mock chỉ kiểm tra từng đơn, chưa giữ/trừ tồn.

## Quyết định giai đoạn 6

| Mã | Quyết định | Lý do và giới hạn |
| --- | --- | --- |
| D61 | FastAPI/Uvicorn + HTML/CSS/JS cùng origin, app factory nhận repo/DB/cấu hình. | Chạy local, không React/CORS/streaming. Route gọi controller và tool cũ; factory cho test thay nguồn mà không sửa chatbot. |
| D62 | Schema Pydantic riêng ở api.py, giữ TypedDict/schema nghiệp vụ cũ. | Validate cả request/response và phát sinh OpenAPI. Class chỉ cho schema thư viện bắt buộc; logic vẫn hàm. State web là FSM, needs giữ nội bộ. |
| D63 | Token secrets.token_urlsafe(32), hash SHA-256 trong RAM; header Bearer và owner guard. | UUID không xác thực. Không token URL/SQLite/log/localStorage; UI giữ RAM tab. TTL 8 giờ, tối đa 200 phiên, restart/reload cần phiên mới; chưa login tài khoản hoặc resume web. |
| D64 | def route dùng threadpool; connection trong từng route, lock riêng phiên. | Client Ollama/SQLite đồng bộ không chặn event loop; không share SQLite connection giữa thread. Registry/lock chỉ một process nên chạy --workers 1; chưa đảm bảo nhiều process/CLI ghi cùng phiên. |
| D65 | load_order_request(record_id, conversation_id) trong storage.py; SELECT có cả owner. | Route không có SQL. Khách khác/ID không tồn tại đều 404; thiếu/sai/hết hạn token 401. Không thay schema SQLite v1 hoặc các helper cũ. |
| D66 | REVIEW có slot/verification/quote riêng; ID yêu cầu và ID demo tách, unavailable không có nút gửi. | Không gọi yêu cầu empty là đơn confirmed. UI sửa bản nháp phải xem lại; confirm/recheck/idempotency luôn do flow/service cũ kiểm soát. |
| D67 | Render bằng textContent; API no-store, không echo validation input. | Văn bản khách/nguồn không thành HTML/script; không cache token/bản ghi nhạy cảm trong HTTP. Lỗi storage/response trả mã chung, lỗi Ollama vẫn fallback rõ. Không tạo hệ thống bảo mật production. |
| D68 | Pin các gói nhỏ đã cài/test, HTTPX stable cho TestClient, ghi cảnh báo deprecation. | fastapi 0.142.2/starlette 1.7.0/uvicorn 0.53.0/httpx 0.28.1 hợp Pydantic hiện có; chưa chuyển HTTPX2. Không cài AI nặng. Browser tool không khả dụng, không gọi HTTP test là UI test. |

Giả định: server chỉ loopback, cùng origin, một worker; database file riêng
cho mỗi test. API production/rate limit/login/chia sẻ session giữa worker
cần phạm vi khác. Không đổi tên Product/Variant/OrderTools hoặc FSM; thêm
contract web và helper storage có owner. Sửa docstring create_state do state
đã được controller lưu SQLite từ stage 5, không đổi hành vi.

## Bổ sung sau yêu cầu AI mặc định và đặt bánh tự nhiên

| Mã | Quyết định | Lý do/giới hạn |
| --- | --- | --- |
| D69 | CHAT_MODE mặc định ollama; run_web.py luôn đặt AI trước import config. | Người dùng muốn chạy luôn AI, kể cả biến rule còn sót. Rule vẫn thử offline có chủ ý/fallback. PowerShell chặn .ps1 trên máy, nên dùng launcher Python thay cho script PowerShell, không đổi execution policy. |
| D70 | LLMOrderSlots + order_nlu, không cho model ID/giá/confirmed/action. | Người dùng chọn Qwen hiểu thông tin đặt bánh tự nhiên; code vẫn kiểm tra/xác nhận. Câu gốc làm căn cứ, chỉ repo nhận diện ID; cập nhật nhiều slot trên bản sao hoặc từ chối. Không để AI tự gọi tool. |
| D71 | Lệnh thuần/field:value/handoff dùng code, chỉ câu chứa thông tin đi AI. | Tránh gửi liên hệ thô hoặc nhờ LLM quyết định consent. Nhãn engine=rule ở lệnh vẫn chính xác; engine=ollama chỉ khi slot AI được chấp nhận. |
| D72 | Hỏi một slot còn thiếu; quote sau ghi chữ là dữ liệu; sửa sau confirmed thành ticket. | Dễ trò chuyện và không in cake_need/product_id cho khách. Không tự suy default size/topping/quantity; vẫn cần REVIEW. |
| D73 | Timeout config60, giữ timeout30 default các hàm client độc lập. | Câu thật nhiều trường mất26,28s sát ngưỡng cũ30; giữ giới hạn tối đa60 đã thống nhất. Không bảo đảm mọi lượt nhanh hoặc model luôn thành công; lỗi vẫn rõ. |

Grounding (đối chiếu căn cứ câu gốc) là kiểm tra cơ bản, không bảo đảm nghĩa
đúng. Hỗ trợ quantity một–mười/số đơn giản, ngày giờ đầy đủ; 'mai'/mơ hồ hỏi
lại. Guard liên hệ không là phát hiện PII đầy đủ. Không đổi Product/FSM/SQL
schema hoặc API routes, không tải model/AI dependency. Kiểm thử model thật
tách khỏi test giả lập; ghi cả lỗi HTTP đầu tiên và lần thành công.


## Hoàn thiện chạy độc lập local (04/10/2026)

| Mã | Quyết định | Lý do/giới hạn |
| --- | --- | --- |
| D74 | sqlite3 duy nhất, schema v2 migrate tại chỗ/backup v1 | Tận dụng storage cũ, không ORM/lớp lưu trùng. drafts/tickets giữ tên; orders extension cùngID submission, không hai đơn. Legacy không retro-stock |
| D75 | local_demo default, catalog/policy + metadata SQL, factory chọn source/provider | Chạy đầy đủ khi chưa backend; is_demo/is_mock/source rõ. Empty/mock/sample giữ bài học, can_accept_real_orders=false |
| D76 | Seed25/35/3/13 stableIDs, ONCONFLICT DONOTHING, reset separate verified/confirm/backup | Seed lặp giữ tồn kho đã trừ; CLI reset kiểm tra chỉ đọc trước migration, cần cờ confirm và backup; lỗi seed rollback cả reset |
| D77 | Qwen unified LLMTurn cho mọi nghiệp vụ; rule chỉ explicit | Theo yêu cầu luônAI; không keywordsilentfallback. Modelerror giữdraft/state, khôngsubmit |
| D78 | Wireupdates typed field/value list → internaldelta; strictschema + literalgrounding +1repair | Thực tế nested17null/genericunion gâycopy/qtystring; kiểu hẹp và contextgọn đã smokeđạt. Mentionchỉliteral, omission chỉ yêu cầu model sửa, không chènrule |
| D79 | Contextprompt filled/missing + needkeys/cards +2botquestions; đầy đủslots/history ởcodeSQL | ModelthậtcopyREVIEW cũ làmguardreject. Tradeoff chưa hiểu chắc arithmeticrelative, giới hạncontext6turns khôngfulltokenaccounting |
| D80 | Một loại mỗi draft, quantity nhiều, localDEMOCONFIRMED/revision/sourcehash | Không mở giỏ multiitem lúc này, phải nói rõkhôngbỏloại2. Consent+edit rereview; confirmedimmutable/handoff |
| D81 | SQL BEGINIMMEDIATE/sameconnfinalrecheck/conditionalstockUPDATE/SAVEPOINT/uniqueidempotency/snapshot | Chốngoversell/partialstock/confirmrepeat; transaction ngoài lưuorder/context/messages cùngcommit. Khôngglobalmultipleworkerownerlocks |
| D82 | BusinessmetadataSQL, UTC↔shopTZ, NFCcodepoint, allergenconservative/ticket | Khônginventbusinesslimits; unknownkhông0/khôngsafe. Toppingpercake/feeorder, fakecontactrestrictiontechnicaldemo |
| D83 | CLI/API cùngcontroller/toolowner; CLIlocalresume khác webtokenRAM; giữUItextContent | Chạystandalone/khôngwebsite2, defroute threadpool. Browser unavailable nênchỉHTTP/TestClient; login/multiworkerngoàiphạmvi |
| D84 | Functionaltests fakeDB riêng/mạngOllamablocked + realmodelsmoke riêng/giữfailedruns | Phân biệtlogicvớiaccuracy; smoke6lượtđạt nhưngcònmodelunreliable/RAGsourcesextra. Khôngdownload/embedding/deploy/stage7 |


## Sửa lỗi kết nối giao diện (04/10/2026)

D85: Kiểm tra ảnh Failed to fetch cho thấy cổng8000 không có listener (WinError10061), không phải lỗi Qwen. Khởi động API local; frontend bắt lỗi network với hướng dẫn tiếng Việt và cập nhật nhãn chưa tạo phiên thay vì giữ “Đang kết nối”. Không retry POST tự động, không đổi session contract, không thêm CORS hay reset dữ liệu.

## Sửa phạm vi sản phẩm theo lượt (04/10/2026)

D86: Tách CurrentTurn, ConversationContext và order draft bằng dict/TypedDict trong controller hiện có. Giữ key order để tương thích storage/API. Tên hiện tại ưu tiên tham chiếu, tham chiếu không rõ hỏi lại, truy vấn dùng filters của lượt thay vì IDs lưu trong needs. Lỗi thật do resolve_mentions cộng selected_id socola khi Qwen vừa nêu dâu vừa reference=last. Không xóa lịch sử; không tạo chatbot/controller mới.

D87: Prompt Qwen phân nhóm order_draft và conversation_context; schema thêm reference=order. Guard thông tin thuần giữ draft bất kể order_update nhầm, chỉ sửa rõ mới tăng revision/bỏ REVIEW. Khi đổi bánh, bỏ size/topping/cake_need cũ và kiểm lại slot giữ. Đây là kiểm soát phạm vi và nghiệp vụ sau Qwen, không regex sinh intent thay model. HTTP client/model/source/tool contracts giữ nguyên; không migration SQL. Dị ứng tiếp tục là ràng buộc an toàn, không bị bỏ chỉ vì câu hỏi thông tin.

D88: Test đúng kết quả model mâu thuẫn thay vì giả định model luôn hiểu đúng. 21 regression mới A–F/empty/mock/reference/REVIEW/persistence; suite356 đạt. Smoke Qwen scope4/4 đạt trong DB riêng; smoke rộng có một policyintent sai vẫn ghi passed=false, rồi có policy followup đạt sau làm rõ prompt. Một smoke không là accuracy, không tuyên bố lượt rộng đạt toàn bộ hoặc stage7 đã làm.

D89 (05/10/2026): Đặt tmp_path của pytest trong `.pytest_tmp/run-UUID` riêng mỗi lần chạy bằng hook cấu hình sớm. Traceback WinError5 ở nhánh duyệt AppData/Temp, chưa phải assertion chatbot sai. Tránh dùng thư mục basetemp cố định vì pytest có thể dọn nội dung cũ; không sửa ACL/chạy Admin/xóa Temp. --basetemp explicit giữ ưu tiên. Test ngữ cảnh21 đạt; toàn suite356 đạt khi nhánh cũ được mô phỏng bị từ chối. Chưa xác minh quyền terminal người dùng; không thay Qwen/database demo.

## Cải thiện intent/context (05/10/2026)

| Mã | Quyết định | Lý do và giới hạn |
| --- | --- | --- |
| D90 | Bổ sung InformationRequest/requests, order_product_mentions và order_operation trong schema hiện có | Intent/tên chung không gắn được giá A với vị B hoặc hai size. Default giữ output cũ; API/storage không đổi schema. Mention vẫn phải repository xác minh, không ID do model sinh. |
| D91 | resolve_message_scopes tạo query tasks và mục tiêu draft độc lập; thông tin không edit; source error chặn kết quả thành công một phần | Tránh kéo draft vào query hoặc query vào đơn. Named thắng reference, ambiguity hỏi lại, giữ context/history/slot không đề cập. Giá/size/stock/vị hiển thị theo đúng request. |
| D92 | Grounding không bypass khi reference; canonical chỉ qua alias duy nhất cùng sản phẩm; source hints chỉ từ vựng | Model có thể bỏ tên mới rồi trả last. Literal quá chặt từ chối canonical hợp lệ. Guard chỉ reject/repair, không sinh intent hoặc chọn IDs thay Qwen. Mask lettering cho tên/delete, không tuyên bố chống mọi prompt injection. |
| D93 | Thư viện17 few-shot bánh A/B/C, prompt v8 English kèm schema rút gọn và tối đa3ví dụ theo FSM/priority; HTTP client/model/options giữ nguyên | Dev v4 có12lỗi model/48, behavior26/48; v5/v6pilot chưa tốt. Nạp schema vào prompt theo hướng dẫn Ollama, giữ format/validation đầy đủ. Không keywordrouting/nhãn final/hardcode menu/giá/fine-tune. Thêm hỏi lại/invalidate REVIEW, remove đúng target; confirmed edit đi ticket. |
| D94 | 74 nhãn dev48/final26; fake logic tách real eval; giữ lỗi/hash/previous_runs và sửa nhãn minh bạch | Baseline đã có scope fix trước; so thay đổi kết hợp không quy hết cho prompt. Empty dev044 annotation sửa theo contract và giữ report gốc. Đánh giá hẹp NLU/controller, knowledge empty, không RAG/production accuracy hay stage7 tổng thể. |
| D95 | Extractor nhận counts/selection flags/next missing field, không tên bánh/preferences values/botquestions cũ; controller giữ context đầy đủ | Trace dev v7 cho thấy dù namedDâu, model copy Bánh kem socola từ order_draft vào output, bị guard chặn. Tên cũ không cần để model chọn reference=order/last/first/second; Python giải ID nguồn. Thay phần prompt D79/D87, không xóa lịch sử hoặc thay API/storage/repository. Tham chiếu mơ hồ vẫn hỏi lại, preference/slots giữ ở code, số liệu đo v8 riêng. |
| D96 | Request thiếu chủ thể ưu tiên CURRENT turn khi không có cue tham chiếu; dedupe scope; unknown reference phrase hỏi lại | Trace dev006 cho thấy request dâu đúng + request rỗng last có thể kéo bánh cũ trở lại, dù top-level scope đã tách. Dev018 phrase bánh đó bị lookup như tên thật. Resolver sửa theo dữ liệu dev, guard cue chỉ kiểm quyền dùng history, không sinh intent/slot. Prompt/schema/labels final giữ nguyên; chạy đo lại và giữ first-final trong previous_runs, không dùng lỗi final điều chỉnh model. |
