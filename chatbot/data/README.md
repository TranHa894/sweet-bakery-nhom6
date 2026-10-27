# Dữ liệu trong chatbot

## Hiện tại — v54, 25/10/2026

nlu_few_shots.json có **267 ví dụ**, thêm năm cách gợi ý bánh chung không tự chọn bánh kem hay bánh nhỏ. Khi chọn ví dụ, câu bánh chung ưu tiên mẫu có product_type=cake; Qwen vẫn tự trả intent/filter và mỗi lượt chỉ nhận tối đa hai mẫu.

Bộ hồi quy riêng có 489 dev + 56 test. Menu/giá/profile giữ nguyên; không fine-tune.


## Lịch sử v53, 25/10/2026

Ngân hàng có **262 ví dụ**. Thêm năm cách hỏi gợi ý chung trong ngữ cảnh đã có nhóm/độ ngọt/vị cũ. Câu gợi ý mới cần search_scope=new; câu chọn loại/vị/slot đang chờ tiếp tục ngữ cảnh tương ứng. Nhóm sản phẩm chung không học từ ví dụ thu hẹp vào bánh kem; ngân hàng vẫn chỉ gửi tối đa hai ví dụ mỗi lần.

Menu, giá và metadata vị giữ nguyên. Bộ hồi quy tách riêng: 480 dev + 53 test; không đưa nhãn test vào prompt. Không fine-tune model.


## Lịch sử v52, 25/10/2026

nlu_few_shots.json có **257 ví dụ**. Thêm 13 mẫu nhiều nhóm với ngân sách độc lập, hướng trên/dưới và biên bao gồm. Mỗi prompt vẫn tối đa hai ví dụ; ưu tiên một mẫu nhiều phần khi phù hợp cấu trúc câu. Không gửi toàn bộ ngân hàng cho Qwen và không fine-tune.

Ví dụ hướng dẫn có question nguyên văn cho từng request để kiểm chứng nhóm/giá độc lập. Giá, menu và profile hương vị giữ nguyên; evaluation riêng có 463 lượt dev và 49 lượt test, không được đọc vào prompt.


## Lịch sử v51 — 25/10/2026

nlu_few_shots.json có **244 ví dụ**, phiên bản v51-guided-audit. Sáu ví dụ mới của đợt v51 gồm ba cách hỏi tư vấn chung và ba câu đổi vị theo ngữ cảnh. Các mẫu tư vấn cũ đã được đồng bộ; mỗi lượt vẫn gửi tối đa hai ví dụ.

recommendation_profiles.json giữ 24 hồ sơ tư vấn do chủ dự án cung cấp, không sao chép giá/tồn kho. Vàng anh và Biển ngọc: vị ngọt, độ ngọt vừa theo menu đã xác nhận; không suy thành phần cụ thể hay an toàn dị ứng.

Bộ đánh giá riêng trong evaluation có 449 lượt dev và 45 lượt test. API không đọc bộ này, prompt không đọc nhãn holdout. Ví dụ hướng dẫn model không phải huấn luyện lại trọng số.

Các ghi chú phiên bản cũ bên dưới là lịch sử.


Mặc định DATA_SOURCE=group_files: menu đọc trực tiếp từ ../static/products.json của website nhóm. Không chép/ghi lại file này; NLU/FSM chỉ gọi repository.

Các file ở data phục vụ chế độ demo cũ và cấu hình AI:
- local_demo_seed.json: 25 bánh/35 biến thể/13 chính sách mô phỏng để seed SQLite local_demo.
- schema_v2.sql: cấu trúc SQLite chatbot, không dùng để tạo database sản phẩm của nhóm.
- mock_catalog.json, mock_order_metadata.json: fixture 5 bánh và metadata mẫu cho mode mock.
- sample_policies.json: điều khoản mô phỏng cho KNOWLEDGE_MODE=sample.
- nlu_few_shots.json: ví dụ trích ý định/slot cho prompt Qwen, không phải menu nguồn.

data là thư mục file. Database lưu hội thoại/bản nháp/yêu cầu/đơn demo nằm ở runtime/chatbot.sqlite3. File menu nhóm chưa có size/tồn kho/allergen/chính sách. Theo yêu cầu hiện tại, adapter group_files mặc định stock_status=in_stock cho mọi sản phẩm mẫu; không tạo số lượng kho hoặc ghi vào file nguồn. Size/allergen/chính sách thiếu vẫn null/unknown; không lấy metadata của bánh demo ghép sang mã SP của nhóm.

Phân nhóm menu: 12 bánh kem (cream_cake), 6 bánh ngọt nhỏ (mini), 3 trà (tea), 3 cà phê (coffee). Category gốc giữ cake/mini/drink. products.js và products.json đã đối chiếu cùng 24 ID/tên/giá/category; Python chỉ đọc JSON.

Nguồn chưa có trường hương vị riêng. Adapter chỉ ghi vị khi tên có từ rõ như vani, socola, dâu hoặc trà xanh, kèm flavor_source=product_name. Hiện 16 sản phẩm có vị ghi trong tên, 8 chưa biết; không suy từ tên trang trí, không dùng tên vị xác nhận nguyên liệu/dị ứng. Lọc qua repository, không hardcode sản phẩm trong prompt.


Phân loại vị của 24 sản phẩm nhóm hiện được lưu tại database_metadata, key catalog_flavors:group_files:v1 trong runtime/chatbot.sqlite3. Có 16 sản phẩm có vị trong tên, 8 giữ null; bảng products vẫn chứa bộ demo cũ, không dùng nó thay menu nhóm. style_tags tách đen/ủ lạnh khỏi flavor. Không gán vani/dâu/mật ong theo màu hoặc tên trang trí.

Chạy .\.venv\Scripts\python.exe -B -X utf8 -m scripts.database classify-flavors để xây lại phân loại, rồi khởi động lại web. Giá/tồn kho/đơn không bị lệnh này sửa; giá vẫn đọc nguồn nhóm. Adapter chỉ đọc metadata một lần, bỏ nhãn cũ khi tên/nhóm đổi, không gọi Qwen để suy vị. Alias dâu tây, chanh dây, vanilla, matcha và cold brew được chuẩn hóa trong code; nhãn vị không chứng minh sản phẩm an toàn với dị ứng.

202 few-shot/v47 là ví dụ hướng dẫn Qwen, mỗi lượt tối đa 2. Evaluation tách riêng, không đưa đáp án test vào prompt. Luồng yêu cầu đã tắt giao/nhận và địa chỉ; trường database cũ giữ để tương thích, không xóa bản ghi đã lưu.

Bản v26 sửa hai ví dụ tham chiếu thêm/bớt: quantity là lượng thay đổi khách vừa nói, không phải tổng sau khi tự cộng với bản nháp. Số ví dụ vẫn là 129, tối đa hai ví dụ mỗi lượt. Không đổi menu/seed/chính sách hoặc metadata nguồn trong đợt tối ưu tốc độ này.

Bản v30 trước đó đồng bộ ví dụ với context gửi model: chỉ trích ý định/giá trị mới, giữ nguyên câu hỏi và sản phẩm thật trong message; Python giữ nhu cầu/bản nháp cũ. Sửa mẫu hỏi giá kèm đặt, liên hệ, xem lại và ngân sách; bỏ filter trùng trong ba mẫu tư vấn, giữ quantity. Vẫn 129 mẫu và tối đa hai mẫu mỗi lượt. Menu, seed, chính sách và bộ evaluation không bị thay trong lần sửa prompt này.

Hai mẫu tham chiếu v30 phân biệt “bánh này” (last, chủ đề đang xem) và “bánh đang đặt” (order, bản nháp). Dữ liệu A/B vẫn là placeholder; giá và tên sản phẩm thực tế tiếp tục lấy từ repository. Không tăng số mẫu hoặc tải model.

Bản v34 trước đó có 135 mẫu, tối đa hai mẫu mỗi lượt. Bổ sung price_preference riêng cho câu hỏi: rẻ/đắt nhất hoặc tìm lựa chọn khác theo mốc đã đối chiếu. Mẫu ngân sách phân biệt còn khoảng, khoảng dùng chung đơn vị và nhận/loại biên. Mã loại không phải hương vị. Menu, seed, giá và chính sách nguồn giữ nguyên; evaluation không được đọc như đáp án khi chạy chatbot.

Bản v37 trước đó vẫn 135 mẫu, tối đa hai mỗi lượt: chủ đề chính sách chung giữ nguyên câu khách nói; tìm mới dùng requests.search_scope=new, câu nối giữ refine. Ví dụ trên/dưới ngân sách phân biệt bánh chung với bánh kem; ví dụ nối vị/giá không tự đổi nhóm. Giá trị nhóm cũ không gửi lại cho Qwen trong context thật hoặc context ví dụ; Python vẫn giữ nó để lọc tiếp và đối chiếu nguồn. Không huấn luyện lại model, thêm menu giả hoặc lấy đáp án test làm ví dụ.

Bản v40 giữ 135 mẫu, sửa hai mẫu tư vấn ngân sách mâu thuẫn với grounding và dùng mẫu rõ vị/ngân sách. Câu đầy đủ/rút gọn dùng cùng điều kiện tìm. Schema HTTP lượt thông tin chỉ bắt buộc intents/requests; lượt order_request vẫn phải xuất action/product_mentions/order_items/updates, helper không bỏ field rỗng của thao tác đặt. Đây là tối ưu token và ví dụ, không fine-tune hoặc sửa menu/giá. Nhãn development và bộ test vẫn tách khỏi prompt.

Nhánh anyOf thông tin loại order_request; nhánh nghiệp vụ buộc đủ sáu trường ở grammar trước khi validate Python. Cách này giữ JSON thông tin ngắn mà không làm mất trường của câu vừa hỏi vừa đặt. Bản cuối đã thử Qwen thật 9 câu dâu/vani và 7 smoke có đặt/tham chiếu; kết quả chi tiết tại README gốc, không lưu report mới.

Bản v41 thêm 16 pattern hỏi lựa chọn trước khi mua, tên bánh kèm câu hỏi và hành động chọn mua rõ; có mẫu ngân sách bao gồm biên, khoảng một số và câu nối. Lưu ví dụ dưới dạng gọn bỏ default rỗng, giữ đủ trường đặt hàng; 151/151 roundtrip schema giữ nguyên nghĩa. Bộ chọn mẫu xét nhóm và kiểu cận giá, vẫn tối đa hai mẫu. Mẫu tìm mới có context vị cũ để dạy không giữ nhầm vị; không đổi dữ liệu sản phẩm hoặc dùng nhãn test làm prompt.

Bản v42 thêm bốn mẫu ngân sách trà (dưới/trên/từ/khoảng), chỉnh mẫu trà không quá để không tự thêm vị. Câu tìm có ngân sách không dùng mẫu tư vấn thiếu cận giá; vẫn tối đa hai ví dụ và không thay Qwen bằng luật trích ý định. Tổng 155 ví dụ; không hardcode menu/giá để trả lời.

Bản v45 thêm 16 ví dụ về khoảng tiền không cần từ/khoảng, tên nhóm đồng nghĩa, cách ghi VNĐ/triệu, cận giá, hỏi giá rút gọn và giữ/bỏ vị cũ theo scope. Bộ chọn mẫu và bộ kiểm chứng dùng chung budget_evidence; mẫu gửi Qwen vẫn tối đa hai, không đưa cả ngân hàng ví dụ vào context. Alias tên thật sinh từ tên sản phẩm qua repository; không đổi tên/giá trong file nguồn nhóm. Không dùng dữ liệu này như trọng số đã huấn luyện.

Bản v46 thêm 10 mẫu nhiều yêu cầu: thuộc tính đứng trước/sau tên, năm món chung giá, ba/bốn nhóm có bộ lọc riêng, câu có chính sách và hỏi trước khi đặt/thêm món. Tổng 185 mẫu; runtime vẫn chỉ gửi tối đa hai. Mẫu nhiều món không bị mẫu nhập tên/điện thoại chiếm chỗ; ngữ cảnh thiếu liên hệ vẫn giữ. Clause nguyên văn giúp code kiểm tra từng ngân sách, không phải câu trả lời dựa trên keyword. Menu/seed/tồn kho không thay đổi; không fine-tune model.

Bản v47 thêm 17 ví dụ tập trung giá nguyên VNĐ, cùng/đúng giá, từng nhóm, câu nối cận giá, tên bánh đứng riêng và tồn kho khi đang thu liên hệ. 202 mẫu vẫn chọn tối đa hai mỗi lượt; số tiền là tiền, không phải số lượng. Nguồn menu nhóm luôn có hàng theo mặc định được yêu cầu, nhưng không thêm quyền tạo đơn và không sửa stock_quantity của database demo hoặc nguồn thật. Bộ test cuối giữ nguyên; chỉ bốn kỳ vọng chữ tồn kho của dev được cập nhật đúng hợp đồng mới.

Bản v48 có 209 ví dụ: thêm bảy mẫu đối chiếu tìm nhóm mới bỏ giá cũ, giữ ngân sách có chủ ý và hai nhóm độc lập không kèm giá. Runtime vẫn tối đa hai mẫu; không tăng giới hạn context/output hoặc gọi thêm model cho tìm mới. apply_query_updates bỏ giá cũ chỉ khi Qwen chọn new, giữ giá cho refine, không xóa dị ứng hoặc bản nháp. Đây là prompt/ví dụ/kiểm chứng, không huấn luyện lại trọng số model. Kết quả kiểm tra hiện tại ở README và evaluation/README.

Bản v49 có 217 ví dụ: thêm nhóm đôi/ba/bốn và overflow; hai mẫu năm request cũ được thu còn bốn. Tối đa hai mẫu gửi mỗi lượt. LLMWireTurn kiểm tra tối đa bốn phần hoặc bốn loại intent thông tin từ JSON Qwen; vượt giới hạn thành thông báo trung tính, không tạo/sửa đơn một phần. Đây là cải thiện prompt/schema/kiểm chứng, không fine-tune; menu và giá không thay đổi.

## Metadata tư vấn v50

recommendation_profiles.json: 24 hồ sơ có ID/tên/nhóm, sweetness, taste_families, coffee_style, note và flavor khi được xác nhận. Không có giá/tồn kho. Adapter đối chiếu nguồn website rồi thêm metadata; hồ sơ được cung cấp này ưu tiên hơn suy vị từ tên hoặc phân loại SQLite cũ. Vàng anh/Biển ngọc chỉ ghi vị ngọt, ngọt vừa. Muốn cập nhật vị thực tế, sửa hồ sơ tương ứng và giữ tên/nhóm đúng nguồn. Không suy dị ứng/dinh dưỡng từ độ ngọt.

Few-shot v50 có 238 ví dụ; mỗi lượt tối đa hai. evaluation không được đọc trong prompt. Bảng chọn thuộc app/advice.py, không chứa danh sách sản phẩm/giá.
