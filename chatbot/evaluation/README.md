# Evaluation — kiểm tra chatbot hiện tại

Thư mục chỉ giữ dữ liệu có nhãn và hướng dẫn. CLI/API không đọc evaluation; prompt chỉ đọc data/nlu_few_shots.json. Các báo cáo cũ trước/after/final/comparison và retrieval đã bỏ vì khác phiên bản code hiện tại.

| File | Công dụng |
| --- | --- |
| intent_context_dev.json | 86 lượt phát triển trong 24 hội thoại: giữ 73 lượt trước, thêm 13 lượt về hỏi Donut, both/all, thứ tự, đặt nhiều loại, số lượng riêng, tham chiếu mơ hồ và phủ định. |
| intent_context_test.json | 33 lượt kiểm tra riêng; không đưa nhãn vào prompt. |
| retrieval_dev.json | 27 câu kiểm tra tìm nguồn: 21 có nguồn, 6 không thể trả lời. Dùng 5 điều khoản mô phỏng trong data/sample_policies.json, không phải chính sách nhóm. |
| README.md | Hướng dẫn này, thay file intent_context_protocol.md bị lỗi dấu. |

Intent là ý định; slot là thông tin được trích. Mỗi turn có message (đầu vào), label (kết quả hiểu mong đợi), expected (hành vi code), id và turn_index. Mỗi dialogue có mode để chọn repository. expected.items giữ các món theo đúng thứ tự. product_id chỉ xuất hiện ở nhãn hành vi, không được gửi cho model như đáp án.

Đã cập nhật nhãn nhờ nhân viên sang handoff và nhãn thêm/bỏ món theo hành vi mới. Giữ các câu cũ và phần chỉnh sửa thủ công; scripts.prepare_intent_dataset hiện chỉ kiểm tra schema/ID/số mẫu, không dựng lại rồi ghi đè hai bộ dữ liệu.

Lượt dev-056 của menu nhóm đã bỏ ngày nhận ở message/label để phù hợp luồng không thu thập lịch nhận. Giữ các ví dụ ngày giờ của local_demo và bộ test riêng; các nguồn đó vẫn có kiểm tra đơn demo. Không dùng nhãn này làm few-shot.

## Lệnh Windows

Đứng tại thư mục chatbot:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.prepare_intent_dataset
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split test --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_retrieval
```

Fake chủ động đưa nhãn vào controller để kiểm tra logic ổn định: không đo khả năng hiểu của model. Lần kiểm tra hiện tại: hành vi **86/86 dev và 33/33 test đạt** với engine=fake. Đây là kiểm tra controller bằng nhãn giả, không đo khả năng hiểu của Qwen. Dữ liệu test đã được dùng kiểm tra code, nên không gọi đó là bộ chưa từng được xem.

Muốn đánh giá Qwen thật: chạy Ollama và chọn OLLAMA_MODEL đúng tên đã cài theo README gốc. Lệnh --engine ollama gọi model local, có thể chậm; không tải model hoặc chuyển sang dịch vụ bên ngoài.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --dialogue dev_group_order_reference
```

Không truyền label/expected cho model khi engine=ollama. Tình huống model lỗi vẫn được tính, không bỏ để tăng điểm. Hội thoại local_demo bật tool provider demo chỉ trong tiến trình evaluator, rồi khôi phục cấu hình; không đổi cấu hình web/file môi trường. Fake và Ollama dùng SQLite RAM riêng từng hội thoại; không đọc/seed/reset database đang dùng. Không tự tải hoặc đổi model.

Mặc định chỉ in kết quả, không tạo file. Muốn lưu rõ ràng:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --output runtime/intent_dev_result.json
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_retrieval --output runtime/retrieval_result.json
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.compare_intent_context --before runtime/intent_dev_before.json --after runtime/intent_dev_result.json
```

Compare yêu cầu hai báo cáo thực sự đã đo cùng bộ nhãn và cùng danh sách lượt; không tạo số liệu trước/sau giả. Báo cáo mới chỉ ghi JSON trong runtime, không thêm file vào evaluation. Không lấy kết quả fake so sánh với model thật như cải thiện khả năng hiểu.

## Đọc kết quả

- behavior_exact: đạt toàn bộ hành vi được gắn nhãn; chưa chứng minh mọi câu chữ của bot đều đúng.
- extraction_exact/intent_micro_f1: có ý nghĩa về model khi engine=ollama. 1.0 ở fake chỉ cho biết nhãn được đưa đúng vào code.
- schema_grounding_ok: output hợp lệ và có căn cứ; không đồng nghĩa đơn đủ điều kiện xác nhận.
- dataset_sha256/code_sha256: dấu vân tay để biết dữ liệu hoặc code có thay đổi.
- completed=true: chạy hết số lượt được chọn; vẫn phải xem số đạt và lỗi.
- Retrieval đã chạy lại trong lần sửa này trên 27 câu: recall@3=1.0, hit@1=0.952381, MRR=0.976190, không tìm nguồn ở câu không thể trả lời=0.5. Retriever còn trả nguồn ở 3/6 câu không thể trả lời; Qwen vẫn phải kiểm tra tài liệu có đủ để trả lời. Đây không phải độ đúng câu trả lời RAG.

**Chưa đánh giá Qwen thật toàn bộ 119 lượt hiện tại (86 dev + 33 test).** Xem README gốc chatbot cho kết quả smoke riêng với model thật và giới hạn nhiều món chỉ lưu yêu cầu chờ tư vấn.

## Kiểm tra nhiều yêu cầu — 11/10/2026 (lịch sử)

Bổ sung các hội thoại dev_multi_questions_order (5 lượt), dev_partial_order_ambiguity (2), dev_partial_information_ambiguity (1), dev_multi_unaccented (1), dev_reuse_known_quantity (2). Bộ test riêng 33 lượt không sửa. Few-shot dùng ví dụ A/B ở data/nlu_few_shots.json, không đọc đáp án ở evaluation.

expected.response_contains/response_absent kiểm tra nội dung cần có/cần tránh; response_counts kiểm tra không trả giá lặp; response_order kiểm tra câu trả lời thông tin trước phần thu thập/REVIEW. Câu rõ phải trả lời dù phần đặt còn mơ hồ; câu hỏi khác không đổi món trong bản nháp. update_slots cho liên hệ/hình thức nhận không chọn lại món theo sản phẩm trong câu hỏi.

Chạy logic hoặc hai hội thoại Qwen có nhãn:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split test --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --dialogue dev_multi_questions_order
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --dialogue dev_reuse_known_quantity
```

73/73 lượt dev và 33/33 lượt test đạt với NLU giả; 63 điều kiện logic riêng, 18 kiểm tra HTTP, 35 file Python kiểm tra cú pháp, 45 ví dụ JSON hợp lệ, 6 module import và CLI khởi động/thoát đạt. SQLite thử nghiệm là RAM. Với Qwen qwen3.5:4b/prompt cuối: hội thoại nhiều câu hỏi + đặt đạt hành vi 5/5 lượt sau lần sửa controller cuối; hội thoại tư vấn rồi đặt giữ số lượng đạt 2/2 lượt. Intent và schema hợp lệ 7/7, không có lỗi model ở hai lần đo này. Đầu ra NLU trùng hoàn toàn nhãn chỉ 1/7 (0/5 và 1/2): còn request lặp, khác cách ghi none/null, continuation và order_operation; controller xử lý các khác biệt đã kiểm tra mà không trả lặp hoặc đổi nhầm bánh. Không gọi đây là độ chính xác toàn chatbot. Chưa đánh giá Qwen toàn bộ 106 lượt, chưa kiểm tra click/render trình duyệt hay RAG Qwen với nhiều chính sách thật. Nhóm chưa có chính sách nên các lượt model kiểm tra thông báo thiếu nguồn; nhiều nguồn mô phỏng chỉ kiểm tra bằng model giả. Các lần đo cuối khoảng 22–33 giây/lượt; chưa tối ưu độ trễ.

Các prompt thử trong quá trình sửa từng có lỗi JSON hoặc bỏ/thêm intent. Số liệu trên là các lần đo gần nhất của prompt cuối, không gộp các lần thử đó như lượt thành công. extraction_exact vẫn chấm output thô, không tự bỏ request lặp/đổi nhãn để tăng điểm. behavior_exact chấm hành vi sau controller và chỉ những điều kiện có nhãn; cần xem cả hai chỉ số.

## Qwen/Ollama local — 14/10/2026

CLI, API và evaluator đã quay lại Qwen qua Ollama. Evaluator chỉ có engine fake hoặc ollama; fake đưa nhãn vào controller ở mode ollama để kiểm tra logic, không gọi model. Không còn API key hay engine dịch vụ bên ngoài trong luồng đánh giá.

Kết quả fake mới nhất: **86/86 lượt dev và 33/33 lượt test đạt**. Bộ test riêng 33 lượt không sửa; bộ dev giữ các hội thoại cũ và bổ sung 13 lượt sau. Prompt chỉ đọc data/nlu_few_shots.json, không đọc label/expected của evaluation. Các số liệu Qwen/HTTP và retrieval ghi ngày trước ở trên là lịch sử, không tự coi là kết quả model hiện tại. Chưa đánh giá Qwen thật toàn bộ 119 lượt. Lệnh chỉ ghi báo cáo khi chọn --output.

Năm hội thoại development mới (13 lượt, dev-074 đến dev-086):

| Hội thoại | Số lượt | Điều cần kiểm tra |
| --- | --- | --- |
| dev_group_catalog_many | 3 | Hỏi Donut trả cả hai kết quả đã đối chiếu; ca2banh nhe tiếp tục hỏi tình trạng, không đặt; bánh thứ nhất hỏi giá. |
| dev_group_both_order | 3 | Hỏi giá rộng; đặt cả hai loại với mỗi loại 1c; phủ định đặt thêm giữ nguyên bản nháp. |
| dev_group_genuine_reference | 2 | Có hai ứng viên nhưng nói bánh đó vẫn cần hỏi rõ, không tự chọn. |
| dev_mock_all_information | 3 | Tham chiếu all và thứ tự first trong mock mode; không tạo đơn. |
| dev_group_negated_both | 2 | k dat ca2banh, chi hoi gia thoi chỉ hỏi giá hai bánh, không thêm số lượng hoặc sản phẩm vào bản nháp. |

Lượt dev-070 đổi nhãn hành vi theo contract thông tin rộng: Mousse vị gì trả thông tin cho cả bốn sản phẩm Mousse đã đối chiếu khi request.ambiguous=False; dữ liệu hương vị chưa có phải nói chưa xác định. Nhãn NLU, sản phẩm đặt Mousse Hawaii và slot đặt hàng giữ nguyên. annotation_note của lượt ghi rõ lý do thay đổi.

**order_items_exact** chỉ được chấm khi label có order_items. Evaluator dùng schema Pydantic để chuẩn hóa trường nullable (có thể null/chưa biết) và giá trị mặc định, rồi so đúng thứ tự món, mention/reference và số lượng từng món. Bỏ hoặc đổi số lượng, tham chiếu hay thứ tự phải không đạt; nhãn cũ không có field này không bị thêm phép chấm. order_items của model vẫn chỉ là đề xuất, repository mới xác minh product_id.

ca2banh nhe sau câu hỏi thông tin không có nghĩa tạo đơn hay quantity=2. dat ca2loai, moi1c có ý đặt rõ và số lượng mỗi loại riêng. Thông tin giá/tồn kho vẫn lấy từ repository; model lỗi giữ bản nháp và không ghi đơn. Xem README gốc cho kiểm tra model hiện tại và cách chạy web/CLI.
