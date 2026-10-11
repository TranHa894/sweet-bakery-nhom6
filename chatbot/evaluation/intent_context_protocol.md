# Bộ đánh giá intent/ngữ cảnh — 05/10/2026

Đây là đánh giá hẹp cho lần cải thiện sau stage 6, không bắt đầu giai đoạn 7 đánh giá tổng thể. Model giữ `qwen3.5:4b` local đang có. Không tải model, fine-tune hoặc cài dependency mới.

## Dữ liệu

- `intent_context_dev.json`: 48 lượt có nhãn, 11 hội thoại; dùng chẩn đoán/điều chỉnh prompt.
- `intent_context_test.json`: 26 lượt có nhãn, 7 hội thoại; đo cuối sau khi cố định prompt/controller.
- Tổng 74 lượt; nhãn viết tay, menu/contacts mô phỏng. ID và message không trùng giữa hai split. Chia theo hội thoại, không tách lượt cùng phiên sang hai tập.
- Bao gồm hỏi giá/size/vị/stock, nhiều intent/nhiều bánh, size riêng, không dấu/viết tắt/phủ định, tham chiếu/thứ tự/rẻ hơn, chuyển chủ đề, điền/sửa/xóa/thêm/hủy, REVIEW/consent+edit, empty/mock/local_demo, mơ hồ và hội thoại nhiều lượt.
- Mỗi turn có `label` (đề xuất NLU chuẩn) và `expected` (hành vi cần đạt). Không phải mọi turn chấm mọi tiêu chí; báo cáo ghi mẫu số riêng.
- `scripts/prepare_intent_dataset.py` tạo lại JSON bằng nhãn tĩnh đã viết, không gọi Qwen. Không cần chạy để test bộ JSON đã có. Không sinh lại bộ final để chiều theo output model.

## Tách prompt và đáp án

`llm_client.build_turn_messages()` chỉ đọc `data/nlu_few_shots.json`, repository và context của hội thoại. Few-shot dùng bánh A/B/C trừu tượng, không đọc evaluation/gold/final. Thư viện17ví dụ, tối đa3ví dụ mỗi lần theo FSM/priority. Promptv8 gửi counts/cờ/ngữ cảnh bước thiếu, không tên/preferences values/historyquestions cũ; Python vẫn giữ IDs/cards/slots thật. Hints từ repository chỉ là alias trong câu hiện tại, không chứa ID/giá/tồn kho và không tự giải intent. Schema rút gọn có trong prompt, formatHTTP/Pydantic vẫn đầy đủ.

Evaluator truyền `item.message` vào service, chấm với nhãn sau khi service trả kết quả. Fake test có thể dùng label làm output giả để kiểm controller; không dùng kết quả fake làm accuracy của Qwen.

## Cách đo

1. Ghi baseline trước thay đổi schema/prompt hiện tại. Baseline này đã có bản sửa A–F trước đó, không đại diện bản lỗi lịch sử gốc.
2. Điều chỉnh bằng dev và lưu cả lần thử lỗi. Giữ model/client HTTP và options hiện có.
3. Cố định code, few-shot và nhãn trước lượt đo dev cuối. Sau đó đo final riêng, không chỉnh prompt từ kết quả final. Trong lần triển khai này, sau lượt v8 đầu đã bổ sung resolver guard từ **dev006/dev018** và đo lại; prompt/schema/nhãn giữ nguyên, không dùng lỗi final để chọn thay đổi. First-final vẫn trong previous_runs. Chỉ lần mới khớp code hash cuối được bàn giao là kết quả hiện tại; không coi các lần lặp là test độc lập.
4. Mỗi lần đo tạo SQLite `runtime/nlu-eval-<random>.sqlite3`; không reset/tạo đơn trong database đang demo. Mỗi dialogue có conversation riêng. Knowledge empty để cô lập NLU/controller, không đo RAG generation.
5. Lưu raw Qwen output, validated proposal, catalog queries, draft trước/sau, answer, error, seconds, code/dataset SHA256. **SHA256** là dấu vân tay nội dung để nhận biết hai lần có dùng cùng file không.
6. Lượt lỗi không bị loại. Checkpoint `completed=false` khi chưa chạy hết; hoàn tất chỉ có nghĩa đã đo hết. Lần chạy lại lưu `previous_runs`.

## Tiêu chí

| Tên | Cách tính và giới hạn |
| --- | --- |
| `schema_grounding_ok` | Có proposal qua validation/grounding và không llm_error; không chứng minh nghĩa đúng |
| `intents_exact` | Tập intent đúng hoàn toàn, không thiếu/thừa |
| `intent_micro_f1` | `2TP/(2TP+FP+FN)` gộp các intent ở tất cả lượt; lỗi model dự đoán rỗng nên vẫn có FN |
| `action_exact`, `reference_exact` | Trùng action/reference có nhãn |
| `updates_exact`, `clear_slots_exact` | Delta khớp nhãn; không được chép slot cũ |
| `request_links_exact` | Chỉ các câu có nhãn requests: intent gắn đúng mention/reference/size; chuẩn hóa tiền tố bánh/kem, không có bộ chấm ngữ nghĩa bên ngoài |
| `order_operation_exact` | Những mẫu có nhãn operation explicit: phân biệt thêm/xóa |
| `query_products_exact` | Cards chứa đúng tập ID yêu cầu sau repository/controller |
| `draft_unchanged`, `draft_target` | Bản nháp giữ nguyên toàn bộ hoặc target đúng theo expected |
| `state`, `slots`, `clarification`, `order_count`, `confirmed` | Hành vi theo expected cho từng turn |
| `extraction_exact` | Tất cả tiêu chí extraction được chấm của một turn đều đúng |
| `behavior_exact` | Tất cả tiêu chí behavior được chấm của một turn đều đúng; không phải đánh giá toàn văn câu trả lời |
| `model_errors` | Engine llm_error; gồm timeout/JSON/grounding; vẫn tính trong mẫu số |

Các exact metric nghiêm hơn “câu trả lời nhìn có vẻ hợp lý”. Proposal có thể không exact nhưng controller vẫn bảo vệ draft. Ngược lại JSON/schema hợp lệ có thể query sai nếu model hiểu sai; báo cáo cần cả hai nhóm.

## Chỉnh nhãn có ghi lịch sử

Trong fake oracle, `dev-044` (empty xác nhận sau REVIEW) ban đầu gán state REVIEW, nhưng contract hiện có lưu waiting_consultation rồi HANDOFF. Đã sửa expected state, giữ nguyên message/nhãn NLU, tăng annotation_revision=2. Baseline gốc giữ ở `intent_context_before_dev_original_report.json`. Bản baseline so sánh có metadata nêu hash cũ/mới/lý do, chỉ rescore expected state của turn đó; không rerun model và không làm thay đổi output. Không có thay đổi nhãn theo các câu trả lời sai của Qwen để tăng điểm.

## Chạy PowerShell

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_intent_context_improvement.py
.\.venv\Scripts\python.exe -X utf8 -m scripts.evaluate_intent_context --split dev --label after
.\.venv\Scripts\python.exe -X utf8 -m scripts.evaluate_intent_context --split test --label final
.\.venv\Scripts\python.exe -X utf8 -m scripts.compare_intent_context
```

Baseline đã được lưu; chạy `--label before` trên code mới không tái tạo baseline lịch sử. Muốn thử nhanh có `--limit 3 --label quick`; không so lần giới hạn với full run. Không chạy hai evaluator Qwen đồng thời vì có thể tranh tài nguyên/timeout. Script không tải model; nếu Ollama/model không có sẽ ghi blocked/completed=false.

## Báo cáo và giới hạn

Các JSON `intent_context_before_dev_report.json`, `intent_context_after_dev_report.json`, `intent_context_final_test_report.json` là bằng chứng chi tiết. `intent_context_comparison_report.json` chỉ so cùng split/dataset hash và cùng danh sách ID theo thứ tự. Mọi turn lỗi vẫn được giữ. Kết quả cuối được tổng hợp trong progress và bài học, sau khi thực sự chạy xong.

Kết quả trên code bàn giao đã hoàn tất ngày 06/10/2026 (giờ cửa hàng): dev 48 lượt và test cuối 26 lượt, `completed=true`, hash core code/few-shot khớp file hiện tại. Dev intent exact 33/48 → 39/48, F1 0,7500 → 0,8842, behavior 30/48 → 32/48, model errors 2 → 7. Test cuối intent 20/26, F1 0,8571, query products 13/15, behavior 21/26, model errors 5. Xem bảng đầy đủ và ví dụ lỗi tại [bài học](../docs/learning/intent_context_improvement.md).

Sau lượt v8 đầu, controller được sửa dựa trên trace **dev-006/dev-018** rồi retest cả hai split; prompt/schema/nhãn không đổi. Báo cáo lần đầu nằm trong previous_runs. Bộ final đã chấm lại cùng dữ liệu, không gọi đây là một bộ final mới độc lập; không tiếp tục tối ưu theo nhãn final. So sánh trước/sau là tác động **kết hợp prompt + schema + controller/grounding**, không tách riêng hiệu quả few-shot. Chưa đo độ dao động có hệ thống hoặc thiết bị khác. Dữ liệu nhỏ do một người triển khai gán nhãn, không đại diện mọi người dùng Việt Nam. Không đo RAG accuracy, UI click/render, khả năng production, multi-item, nguồn thật hay thanh toán/giao hàng.
