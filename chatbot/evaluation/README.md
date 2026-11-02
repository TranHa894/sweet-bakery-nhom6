# Evaluation — dữ liệu kiểm tra chatbot

## V67 — bánh nhỏ/cà phê và vị riêng theo món

Dialogue dev_combo_coffee_preferences_v67 thêm bốn lượt dev-533…536: hai câu gốc 80k/86k, vani + cà phê béo mặn, bánh kem trái cây ít ngọt + trà ngọt vừa. Kiểm tra sản phẩm theo từng thành phần, số lượng, ngân sách, tổng tiền và draft.

Kết quả: 96/96 kiểm tra script; fake 536/536 dev + 60/60 test; 314 few-shot hợp lệ. Qwen thật 4/4 behavior và extraction_exact, một inference/câu, 24,73/12,68/13,27/14,84s. Thêm hai lượt API/Qwen lặp lại câu gốc khi có draft: HTTP 200, tổng 80k, draft không đổi, không ghi đơn, 12,07/11,81s. Không suy độ chính xác toàn chatbot từ các smoke này. Không đổi test cuối, không tạo report, dùng SQLite RAM.

Chạy riêng: `.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --engine ollama --dialogue dev_combo_coffee_preferences_v67`.

## V66 — “trong giá” và độ ngọt theo từng món

Bổ sung dialogue dev_within_price_combo_v66 (dev-527…532): câu gốc 70k, “trong mức giá 70 nghìn”, không dấu 70000, thiếu tiền 55k, đúng trần 60k, trà ngọt nhiều/ít ngọt. Kỳ vọng gồm pool từng món, số lượng, tổng ngân sách và giữ draft. Bộ test cuối không đổi.

Kết quả: 93/93 kiểm tra script; fake 532/532 dev + 60/60 test; 311 few-shot hợp lệ. Qwen thật chạy sáu ca đạt 6/6 behavior, 4/6 extraction_exact, không model/source error; 13,17–14,57s, một inference mỗi câu. Không lấy điểm fake làm độ chính xác model; chưa kiểm tra trực quan GUI. Các lần lỗi trong quá trình chẩn đoán không được tính là đạt. SQLite RAM, không ghi report hoặc DB khách.

Chạy riêng: `.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --engine ollama --dialogue dev_within_price_combo_v66`.

## V65 — nhiều vị/ngân sách trong hội thoại đang đặt hàng

Thêm 26 lượt dev (dev-501…526), hai dialogue dev_combo_budget_collecting_v65 và dev_combo_budget_pending_v65. Mỗi dialogue gồm một lượt đặt trước rồi 12 câu tư vấn mới, có/không ngân sách, viết tắt, vị, nhiều nhóm và số lượng riêng. Tiêu chí mới kiểm tra pool sản phẩm theo từng thành phần, số lượng, tổng tiền/tiền cần thêm và combo không trùng; luôn kiểm tra bản nháp không đổi.

Kết quả chốt: **90/90** kiểm tra scripts/check_checkout.py; fake **526/526 dev + 60/60 test** đạt, 308 few-shot hợp lệ. Hai nhánh retry được kiểm tra lại sau tinh gọn hướng dẫn. Không thay bộ test cuối, không ghi report mặc định, không dùng DB khách hoặc tạo thư mục tests/docs.

Qwen thật trên dev_combo_budget_pending_v65: **13/13 behavior**, **10/13 extraction_exact**, không lỗi model/nguồn. 12 lượt dùng một inference; lượt dev-520 cần sửa JSON, 29,91s. Hai câu gốc dev-515/dev-516: 15,15/16,01s; câu bốn nhóm 22,43s. Lần chạy ngay trước sửa retry đạt 12/13, lỗi thiếu ngân sách chung ở dev-520; lần cuối đã kiểm tra lại, không gộp lượt lỗi thành lượt đạt. Các tiêu chí kiểm tra pool theo thành phần, số lượng, ngân sách, tổng tiền và draft đều đạt.

Thêm hai câu không dấu gọi qua API TestClient/Qwen thật sau một lỗi model giả lập, với REVIEW thiết lập bằng fake: HTTP 200, tổng tiền đúng, không ghi đơn và không thay draft; 14,87/15,23s. SQLite RAM. Đây là kiểm tra phục hồi sau lỗi có chủ đích, không phải hai lần model thực sự lỗi. Chưa đánh giá Qwen toàn bộ 586 lượt hoặc kiểm tra trực quan giao diện/tunnel. Chi tiết xem README gốc.

## V64 — combo chưa có ngân sách và nút đặt

75/75 kiểm tra trong scripts/check_checkout: tối đa ba mức giá có thật, đúng vị từng món, một mức giá không giả thành ba; trả ngân sách sau gợi ý dùng tổng combo; nút đặt không gọi LLM; session riêng, không ghi đè nháp, review/confirm, nhớ liên hệ cho lần sau.

Dev 500/500 + test 60/60 bằng model fake. Mười kỳ vọng dev về số thẻ riêng được cập nhật theo yêu cầu mới: combo thấp/vừa/cao hoặc một combo khi đồng giá; giữ nguyên nhãn NLU và giới hạn pool/loại, bổ sung kiểm tra tổng tiền và mức giá. Không đổi test cuối hoặc lấy nhãn test vào few-shot.

Bốn lượt Qwen thật sau thay đổi đạt một inference/lượt: hai câu gốc 12,11/12,74s; kiểm tra hội thoại ba loại rồi 450k mất 15,49/6,14s. DOM giả/cú pháp JS đạt; chưa kiểm tra trực quan trình duyệt. Tổng 304 few-shot trên đĩa, vẫn chỉ chọn tối đa hai mỗi lượt. Không tạo report mới hoặc dùng DB khách.

## V63 — độ ngọt theo món và nối combo

72/72 kiểm tra trong scripts/check_checkout đạt: chuẩn hóa ngọt chung mà không nới mức rõ ràng; filter không lẫn giữa hai món; không cần retry cho JSON hợp lệ chỉ khác mức ngọt chung; giữ ngân sách khi sửa vị; hỏi chọn món chưa rõ; tìm mới không kế thừa combo; model lỗi giữ state; không tạo đơn. Dev 500/500 + test 60/60 bằng model fake đã chạy, không sửa đáp án.

Qwen thật: 7 lượt sau sửa không lỗi, mỗi lượt một lần gọi (4,62–15,15s), gồm hai cách nói ngân sách, độ ngọt hỗn hợp, câu nối chưa rõ và chọn món, đổi riêng mức của hai loại. Không coi đây là đánh giá toàn bộ model. Tổng 303 few-shot trên đĩa, tối đa hai/lượt, dạng combo sửa vị chỉ chọn một ví dụ phù hợp. Không ghi report mới, không dùng DB khách và chưa kiểm tra trực quan trình duyệt.

## V61 — ngọt chung và thiếu ngân sách (31/10/2026)

68/68 nhóm trong scripts/check_checkout.py đạt. Bổ sung: ngọt chung giữ theo từng món; bánh ngọt=mini; 380k đủ tiền; 350k thiếu 30k; hai tổ hợp rẻ nhất so với duyệt toàn bộ trong test; số lượng và vị/allergen/trần đơn giá không bị nới; số tiền thiếu đúng phép trừ; tải lại và bản nháp được giữ.

Fake dev 500/500 + test 60/60 đạt, không đổi đáp án. Ngân hàng few-shot 300 mẫu, chỉ chọn tối đa hai/lượt. Qwen thật: tái hiện đúng hai mã lỗi ban đầu; hai câu gốc + thiếu ngân sách + tên/vị/số lượng riêng đã đạt; câu vị không có còn lỗi ở lần kiểm tra đầu và đạt sau sửa phạm vi vị. Ba lượt thử cuối với prompt mới đều một inference. Không báo kết quả fake thành độ chính xác toàn bộ của Qwen.

JavaScript/DOM giả đạt kiểm tra dòng Cần thêm; chưa thử bằng mắt trên trình duyệt. Dữ liệu kiểm tra SQLite RAM; không có đơn hoặc thông tin khách thật.


## V60 — nhóm món, ngân sách và vị (31/10/2026)

- scripts/check_checkout.py: 63 nhóm đạt; thêm kiểm tra khung nhóm/tổng tiền, khôi phục lịch sử, quyền phiên, tên món cụ thể và số lượng, vị bắt buộc, sản phẩm inactive, không lặp toàn bộ nhóm khi khác biến thể.
- Fake dev 500/500, test 60/60; không đổi nhãn hai tập để làm đạt.
- Ngân hàng few-shot 297 ví dụ, tối đa hai gửi model. Mẫu mới chỉ thuộc ngân hàng hướng dẫn, không lấy đáp án test cuối.
- Qwen thật: 5/5 câu liên tiếp đạt sau sửa (440k bánh–cà phê; trà ngọt nhiều dưới 30k; 1 bánh sô cô la + 2 cà phê muối; 4 loại trong 500k; vị không có thì không ghép nhóm). Mỗi câu một inference, 6,49–19,82s; tất cả hội thoại RAM, không tạo đơn.
- Bộ kiểm tra frontend bằng DOM giả đạt; kiểm tra trực quan Cốc Cốc chưa hoàn tất do công cụ hết thời gian chờ quyền mở cửa sổ. Không coi DOM giả là đã thử trên trình duyệt.


## Cặp loại và tiền tương đương — v59, 31/10/2026

Đã chạy 56/56 nhóm trong scripts/check_checkout.py; thêm bốn nhóm về phủ sáu cặp, câu 450k sau các ngữ cảnh khác nhau, sửa nhầm coffee thành flavor và kiểm chứng tiền tương đương không retry. Sai số tiền/hướng giá vẫn bị từ chối. Chạy lại fake dev 500/500 + test 60/60, không đổi bộ nhãn.

Qwen thật: năm lượt 450k/450000/không dấu ở các ngữ cảnh dựng trong RAM đều trả đúng ba cặp, tổng 365.000 / 395.000 / 405.000đ; mỗi lượt một lần gọi, khoảng 11–12 giây. Đây là kiểm tra chức năng của lỗi cụ thể, không phải đánh giá toàn bộ dataset bằng model thật. Ngân hàng few-shot 296 mẫu; vẫn tối đa hai mẫu/lượt, không thêm lượt diễn đạt hoặc tăng token/context.

## Kiểm tra tư vấn trà và nhóm món — v58, 30/10/2026

Bộ dev/test giữ nguyên 500/60 lượt; không đổi nhãn để khớp lỗi mới. Đã chạy lại fake, đạt 500/500 + 60/60. Thêm 15 nhóm hồi quy trong scripts/check_checkout.py, tổng 52/52 đạt: trà theo độ ngọt/ngân sách, giữ bản nháp, nhóm 2–4 loại, số lượng, tổng tiền và biên giá, không lặp nhóm, nguồn empty/lỗi, giá unknown/hết hàng, dị ứng, biến thể, JSON sửa một lần và mẫu cũ flavor=ít ngọt không lọt vào câu ngọt nhiều.

Qwen thật chạy chuỗi 9 câu chức năng đạt 9/9; tám câu một lần gọi, một câu số lượng cần sửa JSON một lần. Đây là smoke test có kiểm tra ID sản phẩm, số nhóm, tổng tiền và revision bản nháp; chưa phải exact-match trên toàn bộ dữ liệu nhãn. Trong lúc cải thiện từng gặp bỏ trà, bỏ số lượng và chép độ ngọt từ few-shot; các lượt đó không được tính là đạt. Xem README chính để biết thời gian và nguyên nhân.

Ngân hàng few-shot 291 mẫu, tối đa hai mẫu/lượt. Bộ test cuối không được đưa vào prompt. Kiểm tra chức năng mới bằng .\.venv\Scripts\python.exe -B -X utf8 -m unittest -q scripts.check_checkout; database kiểm tra trong RAM, không gọi Qwen cho lệnh này.

## Bộ hiện tại v57 — phạm vi “món”, 30/10/2026

Dev **500 lượt / 155 hội thoại**, test **60 lượt / 31 hội thoại**; thêm 5 lượt dev và 4 lượt test về yêu cầu món chung sau bánh trà xanh, khoảng tiền không đơn vị và giữ điều kiện rõ. Các nhóm mới: dev_generic_menu_restart, dev_generic_menu_range, test_generic_menu_question, test_generic_menu_keep_explicit. Không đưa câu/nhãn test vào few-shot.

Đã chạy fake 500/500 + 60/60 đạt. scripts/check_checkout.py hiện 37/37 nhóm đạt, gồm sáu nhóm mới: bỏ nhóm/vị cũ khi tìm mới; câu cùng nghĩa; fragment/giữ vị; tham chiếu món đó; model trả phạm vi sai sửa tối đa một lần; context được giảm giá trị thừa mà state thật không đổi. Các nhóm cũ về đặt hàng, phân trang, phiên và nguồn lỗi vẫn đạt; DB RAM, không ghi dữ liệu khách.

Qwen thật: 9 lượt kiểm tra chức năng với mã cuối đều đạt (không phải báo cáo exact-match trên cả bộ dữ liệu). Tám lượt một lần gọi; câu cùng vị cần hai lần. “Gợi ý món dưới 100k” và bản không dấu bỏ đúng loại/vị cũ, xem thêm giữ ngân sách; câu tham chiếu/giữ vị vẫn ra Bánh cuộn trà xanh. Đọc README chính mục v57 để xem chi tiết nguyên nhân, thời gian và giới hạn.

Lệnh: .\.venv\Scripts\python.exe -B -X utf8 -m scripts.check_checkout. Đánh giá fake dùng -m scripts.evaluate_intent_context --split dev --engine fake hoặc --split test --engine fake; không cần ghi report ra file.

## Hồi quy nhánh tìm trực tiếp — 27/10/2026

31/31 nhóm trong scripts/check_checkout.py đã đạt. Thêm 5 nhóm: “tìm bánh dưới 400k” có nút ngay ở lượt đầu 4 món; xem tiếp giữ điều kiện tới hết; nhóm chỉ có 3 món không tạo nút thừa; hỏi giá theo tên vẫn là thông tin; nhiều nhóm ngân sách riêng và nhóm kết quả chồng lấn không bị lặp/mất bộ lọc; xếp hạng rẻ nhất giữ nguyên khi xem thêm. DB RAM, model giả; không sửa dữ liệu đang dùng.

Fake 495/495 dev + 56/56 test đạt, bộ nhãn không đổi trong bản sửa này. Qwen thật/API: 15 bánh dưới 400k, lượt đầu 4 rồi 3/3/3/2 món, mỗi lượt một lần gọi; nút chỉ hiện khi còn kết quả. Browser/model giả đã bấm từ 4/15 đến 15/15, không trùng thẻ, không nút giá, không lỗi JavaScript. Chưa đánh giá Qwen toàn bộ bộ mẫu.

## Hồi quy xem thêm không lặp — 27/10/2026

scripts/check_checkout.py hiện **26 nhóm**, đã chạy 26/26 đạt. Sáu nhóm mới xác nhận xem hết 12 bánh theo trang 3 món không trùng, 3+1 ở nhóm vị hẹp, nhóm ba món ẩn nút ngay, giữ giá/nhóm khi xem tiếp, đổi điều kiện bắt đầu đợt mới, hỏi giá xen ngang và tải lại client cùng session, phiên độc lập, lỗi model/nguồn không tiêu thụ sản phẩm, nâng cấp phiên cũ chưa có lịch sử trang. Tất cả dùng SQLite RAM và model giả.

Bộ dev/test giữ **495 + 56** lượt. Điều chỉnh duy nhất kỳ vọng hành vi của dev-388 (dev_advice_cake_numeric): hết sản phẩm phải trả danh sách rỗng, thay cho phát lại hai món cũ. Nhãn NLU và test cuối không đổi. Đã chạy fake 495/495 + 56/56 đạt.

Qwen thật/API có năm lượt: bốn trang bánh kem 3+3+3+3, không trùng; lượt thứ năm sau khi hết trả rỗng. Mỗi lượt một lần gọi. Browser Chrome headless với model giả bấm nút ba lần, đủ 12 thẻ khác nhau, nút biến mất ở lượt cuối và sau tải lại; không lỗi JavaScript. Đọc README chính mục “Xem thêm sản phẩm không lặp”. Chưa đánh giá toàn bộ bộ mẫu bằng model thật.

## Hồi quy vòng lặp lựa chọn vị — 27/10/2026

scripts/check_checkout.py hiện **20 nhóm**, đã chạy 20/20 đạt. Bốn nhóm mới kiểm tra: model bỏ taste_family/sweetness nhưng nút hợp lệ vẫn ghi nhận đúng; chọn số/nhãn/không dấu; bánh nhỏ vị cà phê/kem không chuyển sang cà phê, chọn số không đổi số lượng đơn; bảng cũ/phiên khác/câu tự nhiên không bị coi là nút; lỗi model hoặc output đặt hàng không tiêu thụ lựa chọn và không tạo đơn. Các nhóm đặt hàng/form cũ vẫn đạt.

Đã chạy lại fake **495/495 dev + 56/56 test** đạt. Không thay nhãn hoặc thêm mẫu few-shot cho bản sửa này. Qwen thật: “gợi ý bánh kem” → “Ngọt vừa” → “Kem/vani/trang trí” đạt, một lần gọi/lượt; code ghi nhận field/value của nút khi JSON model thiếu vị. Đây chưa phải kết quả đánh giá toàn bộ bộ mẫu bằng Qwen. Chỉ dùng DB RAM và dữ liệu liên hệ giả.

## Bộ hiện tại — v56, 27/10/2026

Dev **495 lượt / 153 hội thoại**, test **56 lượt / 29 hội thoại**. Thêm 6 lượt dev: hai cách đặt 3 bánh cuộn vani + 2 cà phê muối, hỏi tư vấn trong lúc đặt, “ngọt” chưa rõ mức và chọn “ngọt nhiều”. Nhóm dev_v56_polite_multi_order, dev_v56_short_order_then_advice, dev_v56_sweet_degree, dev_v56_sweet_paraphrase. Hai mẫu đặt đi qua JSON wire parser thay vì chỉ tiêm object đã hợp lệ. Bộ test cuối không đổi, không đưa nhãn test vào prompt.

Đã chạy fake **495/495 + 56/56** đạt; scripts/check_checkout.py **16/16** nhóm đạt, gồm phiếu cũ không mở khi tư vấn/lỗi model, giữ bản nháp, ảnh lấy từ nguồn và khả năng resume REVIEW trước phiên bản mới. DB trong RAM, không dùng dữ liệu liên hệ thật.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.check_checkout
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split test --engine fake
```

Qwen thật kiểm tra riêng 6 lượt (3 câu độc lập và 3 lượt qua API có lưu yêu cầu RAM), đều một lần gọi, khoảng 5,16–11,77 giây/lượt. Không gọi đây là độ chính xác của cả 551 mẫu. Browser QA dùng model giả, ảnh 48px tải đúng, khung nhỏ/lớn không tràn, form chưa gửi không mất khi hỏi thông tin; không có lỗi JavaScript. Đọc README chính mục v56 để biết nguyên nhân và giới hạn.

## Lịch sử hồi quy form đặt hàng — 27/10/2026

Lệnh riêng: .\.venv\Scripts\python.exe -B -X utf8 -m scripts.check_checkout

12 nhóm kiểm tra API/form dùng SQLite trong RAM và output model giả, không reset hoặc ghi database đang dùng. Bao phủ form bắt buộc, nhiều món/tổng tiền nguồn, chống trùng, revision, quay lại/hủy, yêu cầu thứ hai, liên hệ riêng conversation, không tái dùng ngày/lời chúc/ghi chú, nguồn thay đổi, lỗi model, rollback SQL, HANDOFF và xác nhận tự nhiên. Đã chạy 12/12 đạt.

Bộ hội thoại vẫn 489 dev + 56 test; đã chạy lại fake đạt toàn bộ. Các test controller cũ không bật cờ web_checkout nên vẫn kiểm tra luồng hội thoại trước form; check_checkout bổ sung phần API web thực tế, không dùng kết quả fake để tuyên bố Qwen hiểu hoàn hảo.

Qwen thật/API và Chrome headless đã thử hai yêu cầu liên tiếp, hỏi giá trà sữa xen ngang, form/xem lại/sửa/xác nhận/resume. UI cuối kiểm tra bằng model giả xác nhận nội dung đang gõ được giữ khi hỏi giá, widget nhỏ/lớn không tràn và không có lỗi JavaScript. Xem README chính mục v55 để biết giới hạn nguồn tham khảo và kết quả cụ thể. Chưa chạy tất cả mẫu bằng Qwen.


## Lịch sử — v54, 25/10/2026

Dev **489 lượt / 149 hội thoại**, test **56 lượt / 29 hội thoại**; tổng 545 lượt. Thêm 12 lượt về bánh chung: gợi ý chưa chọn loại phải có đúng hai nút Bánh kem/Bánh nhỏ, chọn số 1/2 đúng bước, ngữ cảnh cũ và bản nháp không làm lệch loại. Ba câu test mới không nằm trong few-shot.

Nhóm: dev_broad_cake_choice_steps, dev_broad_cake_choice_old_context, dev_broad_cake_choice_order và test_broad_cake_choice_1…3.

Đã chạy fake 489/489 + 56/56 đạt. API với Qwen thật và database RAM: năm lượt đều đúng, một lần model/lượt; thêm kiểm tra Qwen ngữ cảnh cũ và hai câu test tương tự đạt. Chưa chạy Qwen toàn bộ 545 lượt. Dùng các lệnh evaluate_intent_context bên dưới; đổi --dialogue thành dev_broad_cake_choice_steps để thử riêng luồng mới.


## Lịch sử v53, 25/10/2026

Dev: **480 lượt / 146 hội thoại**. Test: **53 lượt / 26 hội thoại**. Thêm 21 lượt so với v52, tổng 533 lượt hồi quy.

Các nhóm dev_advice_restart_old_filters, cake_scope, during_order, fresh, empty, drink_scope kiểm tra yêu cầu gợi ý mới sau bộ lọc cũ; lựa chọn tiếp phải giữ đúng bước hỏi; bản nháp và lượng hai bánh vani không bị thay đổi. Hai hội thoại test_advice_restart_context_* dùng cách hỏi khác, không đưa câu cần kiểm tra vào few-shot.

~~~powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split test --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --dialogue dev_advice_restart_old_filters
~~~

Đã chạy fake 480/480 dev + 53/53 test đạt. Đây là kiểm tra controller bằng nhãn giả, không phải độ chính xác Qwen.

Kiểm tra Qwen thật bổ sung ngoài evaluator: bản sao phiên cũ và phiên mới cùng câu gợi ý đều thành công một NLU/lượt. API/SQLite RAM chủ động gây lỗi model rồi chat tiếp trong cùng session: gợi ý → gợi ý lại → chọn Bánh kem → Ít ngọt đều thành công, 4,02–6,30 giây/lượt. Draft/needs/history/current_request không đổi khi lỗi; draft vẫn giữ sau bốn lượt; resume và quyền phiên đúng. Lỗi chủ động dùng đầu ra giả, bốn lượt phục hồi dùng Qwen thật; không gộp chúng thành phép đo accuracy model. Chưa chạy Qwen trên toàn bộ 533 lượt.

Các mục sau ghi lịch sử.


## Lịch sử v52, 25/10/2026

- Dev: **463 lượt / 140 hội thoại**. Test: **49 lượt / 24 hội thoại**. Tổng 512 lượt kiểm tra chức năng.
- Thêm 14 lượt dev và bốn lượt test; các nhóm mới dev_mixed_budget_* và test_mixed_budget_holdout_*.
- Bao phủ câu gốc/rút gọn/không dấu/đảo thứ tự; hai hướng giá; ba/bốn nhóm; “trên 45k” loại đúng cà phê giá 45k; empty; đang thu thập đơn; JSON giả qua client thật. Mỗi nhóm có filters và pool/count riêng để phát hiện trộn ngân sách hoặc chỉ trả nhóm đầu.
- Bốn câu test mới không có trong prompt/few-shot. Một số lỗi phát hiện khi chạy được dùng để sửa validator và bổ sung quy tắc/ví dụ tổng quát; đây là kiểm thử hồi quy chức năng, không dùng điểm này như đánh giá model độc lập.

Chạy từ chatbot, không tạo report nếu không dùng --output:

~~~powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split test --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --dialogue dev_mixed_budget_user_1
~~~

Thực tế: fake 463/463 + 49/49 đạt sau sửa. Qwen đã chạy câu gốc, rút gọn, không dấu, đảo thứ tự, ba/bốn nhóm, biên nghiêm ngặt; không quá/ít nhất và cách nói cao hơn/thấp hơn từng lỗi, đã sửa và chạy lại thành công một lần model/lượt. Chưa chạy toàn bộ 512 lượt bằng Qwen. API web/RAM kiểm tra thêm câu gốc, chào hỏi, hỏi thông tin lượt sau, lịch sử và token chéo; không tạo đơn.

Guard riêng đã xác minh JSON thiếu question hoặc sai hướng giá bị chặn sau tối đa một lần sửa; draft không đổi. Schema/257 ví dụ hợp lệ, mỗi prompt tối đa hai few-shot. Không bỏ validation để làm câu lỗi thành thành công.

Các mục dưới đây là lịch sử.


## Lịch sử v51, 25/10/2026

- intent_context_dev.json: **449 lượt / 127 hội thoại**.
- intent_context_test.json: **45 lượt / 20 hội thoại**; giữ 33 lượt cũ và thêm 12 câu holdout. Các câu holdout mới không có trong nlu_few_shots.json.
- Thêm **57 lượt so với v50**: 41 dev tình huống, bốn dev JSON giả, 12 holdout. Không xóa các phép thử chức năng cũ còn phù hợp.
- Cập nhật 50 nhãn gợi ý cũ và hai lượt tiếp nối theo yêu cầu tư vấn mới. Danh sách menu trực tiếp vẫn khác tư vấn từng bước. Món thay thế phải ghi rõ khác vị, giữ ngân sách/nhóm/dị ứng; không chấm nó là khớp đúng vị ban đầu.

Nhóm mới bao phủ: câu gợi ý tương đương; chọn độ ngọt; đổi vị nhưng giữ giá; đổi nhóm bỏ điều kiện cũ; chọn bằng số; gì cũng được/xem thêm; biên giá; vị không có và món thay thế; cà phê theo kiểu uống; hỏi giá xen giữa; đang đặt bánh vẫn tư vấn; nguồn empty. Các dialogue bắt đầu bằng dev_advice_ và test_advice_holdout_.

Bốn lượt dev-446…449 trong dev_advice_wire_flavor_aliases có wire_output: JSON giả chạy qua chính llm_client.extract_turn, parser và validator, thay vì chỉ đưa đối tượng đã validate cho controller. Khi dùng engine=ollama, evaluator không đọc wire_output/label để sinh câu trả lời.

Kỳ vọng bổ sung kiểm tra nút chọn, bước đang chờ, không lộ mã, đa dạng nhóm, không lặp món khi xem thêm, giữ/bỏ đúng bộ lọc và số lần NLU. filters_any chỉ chấp nhận các cách biểu diễn vị tương đương đã liệt kê; vẫn cấm giữ đồng thời vị cũ. Điểm extraction_exact giữ so sánh nhãn chặt, tách khỏi behavior_exact.

Chạy từ thư mục chatbot, không tạo report nếu không truyền --output:

~~~powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split test --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake --dialogue dev_advice_wire_flavor_aliases
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --dialogue dev_advice_flavor_replacement
~~~

Đã chạy: fake **449/449 dev + 45/45 test**. Qwen thật, kết quả cuối từng nhóm: đổi vị **5/5 hành vi**, cà phê **3/3 hành vi**, một NLU/lượt, 4,04–6,29 giây. Extraction_exact chỉ 1/8, có khác biệt alias/trường nhóm/advice; không đổi nhãn để nâng điểm. Trước sửa đã có lỗi stale filter, product_type_mismatch và invalid_turn_json; không tính các lượt lỗi đó là đạt. Chưa chạy Qwen toàn bộ 494 lượt hoặc benchmark thống kê. Database kiểm tra nằm trong RAM; không reset database đang dùng.

Các mục sau là lịch sử kiểm tra của các phiên bản trước.


Thư mục giữ dữ liệu có nhãn và hướng dẫn. API không đọc evaluation. Prompt chỉ đọc `data/nlu_few_shots.json`, không đọc label/expected ở đây.



## Tư vấn theo bước v50

Thêm dev-385…404 (20 lượt), tổng 404 dev; bộ test cuối giữ 33 lượt. Các dialogue:
dev_advice_cake_numeric, dev_advice_medium_fruit, dev_advice_tea, dev_advice_coffee,
dev_advice_mini, dev_advice_direct, dev_advice_any, dev_advice_empty.

Evaluator kiểm tra thêm quick_replies, advice_pending và không lộ mã trong lời đáp. Hai kỳ vọng cũ đổi có chủ đích: dev-178 ưu tiên Vàng anh cùng vị ngọt với Biển ngọc; dev-273 nay tìm được bốn bánh kem vani do chủ dự án bổ sung metadata. Không đổi nhãn intent của chúng.

Dùng lệnh evaluate_intent_context bên dưới với --engine fake để chạy toàn bộ hoặc --engine ollama --dialogue dev_advice_cake_numeric để gọi Qwen thật. Không có --output thì không tạo report.

Đã chạy fake 404/404 + 33/33; kiểm tra API/RAM và Chrome: nút, ảnh, reload, quyền phiên, lỗi model. Qwen các chuỗi mới đã được thử từng nhóm; các lần trung gian lỗi được sửa tiếp. Kiểm tra cuối ba câu đủ điều kiện đạt 3/3, một NLU/câu, 12,33–15,33 giây. Chưa chạy toàn bộ dev/test bằng Qwen; không cộng các lần trung gian thành điểm chính xác toàn bộ. Xem README chính để biết giới hạn.

## Bốn phần hỏi và đủ nhóm — v49

Thêm dev-371…384: 14 lượt / 12 hội thoại; tổng **384 lượt / 103 hội thoại**, intent-context-v30, annotation_revision=25. Giữ 370 nhãn cũ và 33 lượt test cuối, không đưa nhãn evaluation vào prompt.

- dev_bounded_groups_pair_1…6: sáu cặp bánh kem/bánh nhỏ/trà/cà phê, gồm câu “giới thiệu…” và không dấu.
- dev_bounded_groups_three/four: ba/bốn nhóm độc lập.
- dev_bounded_groups_budgets: mỗi nhóm có ngân sách riêng.
- dev_bounded_groups_draft: hỏi xen giữa khi đặt hai bánh vani, vượt giới hạn không sửa draft.
- dev_bounded_groups_empty: đủ hai request nhưng không bịa dữ liệu nguồn.
- dev_bounded_groups_overflow: hơn bốn phần/loại intent được báo giới hạn, không thực hiện một phần.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split test --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --dialogue dev_bounded_groups_pair_1
```

Không truyền --output thì không tạo file. Đổi --dialogue để thử trường hợp khác. Các test fake legacy năm phần vẫn đo tương thích controller; output model hiện qua Wire tối đa bốn phần và bốn loại intent thông tin.

Đã chạy cuối: fake 384/384 dev + 33/33 test; fake-wire 14/14; 217 ví dụ hợp schema. Qwen thật lần trung gian 11/14 hành vi (ba lỗi được giữ trong kết quả, không coi đạt); sau sửa alias và giới hạn đã chạy lại tám lượt trọng điểm, đạt 8/8 hành vi, 7/8 extraction_exact, 8 lần NLU, 183,03 giây tổng, 16,86–43,02 giây/lượt. Không tự công bố 14/14 model sau sửa vì không chạy lại toàn bộ 14 lượt; sáu cặp và ba nhóm đã được thử trong lượt trước. Không fine-tune.

Guard kiểm tra đủ nhóm, alias/clause không bịa, không nhầm vị trà xanh hoặc tên bánh thành nhóm trà; Wire quá bốn trả neutral overflow và không sửa slot. API/RAM đã xác minh đủ hai nhóm, lịch sử/REVIEW, overflow và JSON sai không sửa draft, cách ly token; không tạo đơn. Giữ model/context/output budget, không tăng số ví dụ gửi mỗi lượt. Chưa chạy Qwen toàn bộ bộ dev/test, chưa benchmark thống kê.

## Gợi ý nhóm mới và ngân sách cũ — v48

Thêm dev-351…370: 20 lượt / 4 hội thoại, tổng 370 lượt / 91 hội thoại (intent-context-v29, annotation_revision=24). Giữ nguyên 350 lượt cũ và bộ test cuối 33 lượt. Few-shot hiện tại v48 có 209 mẫu; chỉ gửi tối đa hai mỗi lượt, không đưa nhãn evaluation vào prompt.

- dev_new_group_resets_old_budget: đúng chuỗi người dùng trên 400k → trà → cà phê → bánh kem → bánh nhỏ → lặp bánh kem.
- dev_new_group_vs_budget_continuation: phân biệt tìm mới với “trên 350k thì sao” và “vẫn trong ngân sách đó”.
- dev_new_group_keeps_draft_and_scopes: hỏi nhóm/giá trong lúc có hai bánh vani; nhiều nhóm có bộ lọc riêng, bản nháp không đổi.
- dev_new_group_empty_no_facts: bỏ giá cũ khi đổi nhóm dù chưa có nguồn, không bịa sản phẩm.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split test --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --dialogue dev_new_group_resets_old_budget
```

Đổi --dialogue sang một trong ba tên còn lại để thử đủ 20 lượt mới. Không truyền --output thì không tạo file báo cáo. Evaluator có thể exit 2 khi extraction_exact chưa khớp nhãn hoàn toàn, dù behavior đúng; cần đọc hai số riêng.

Đã chạy sau sửa cuối: fake 370/370 dev + 33/33 test; fake JSON/schema/grounding 20/20; 209 ví dụ hợp schema. Qwen thật 20/20 hành vi, 14/20 extraction_exact, 20 lần NLU/102,01 giây tổng, 3,65–7,86 giây/lượt. Lần trung gian 17/20 còn lỗi không được tính đạt. Không fine-tune, không suy độ chính xác toàn chatbot từ bộ nhỏ.

API model giả/RAM: 13 lượt chat 200, 5 tài nguyên GET 200, hai phiên 201; draft, timeout, isolation và 401/404/422 đúng. Giá/refine, dị ứng giữ nguyên, REVIEW khi timeout và cờ biên rời đã kiểm tra. Không ghi/reset DB thật hay tạo report; chưa click/render trình duyệt hoặc chạy model trên toàn bộ 370 lượt. Các mục v47 trở về trước bên dưới là kết quả lịch sử.

## Cách ghi tiền và câu nối — v47

Thêm dev-322…350: **29 lượt / 8 hội thoại**, tổng **350 lượt / 87 hội thoại**, intent-context-v28, annotation_revision=23. Bộ test cuối 33 lượt giữ nguyên. Bốn kỳ vọng tồn kho dev-063/065/071/309 đổi chữ “chưa biết” thành “còn hàng” vì người dùng yêu cầu mặc định mới cho group_files; nhãn intent không đổi. Kho mock/local_demo vẫn giữ dữ liệu riêng.

Các dialogue mới:
- dev_price_point_to_new_budget: cùng giá → trên một mức giá → giá nguyên VNĐ → sp.
- dev_price_point_notation_equivalence: k/nghìn/ngàn/dấu phân cách/đ/VNĐ có cùng giá trị.
- dev_price_new_catalog_vs_group: tìm toàn menu khác với tinh chỉnh nhóm cũ.
- dev_price_keeps_draft_and_quantity: đổi câu hỏi giá không thay món/số lượng đang đặt.
- dev_price_quantity_and_assumed_stock: hai bánh giá 35000; hỏi còn hàng và lọc available_only.
- dev_price_empty_mode_money: không có nguồn không bịa sản phẩm.
- dev_price_bare_product_after_search: chuỗi sát ví dụ người dùng, tên bánh đứng riêng không mang lại cận giá cũ.
- dev_price_unitless_ranges: hai cận nguyên VNĐ; kiểm tra cả hai cận và tập sản phẩm.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split test --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --dialogue dev_price_point_to_new_budget
```

Đổi dialogue để chạy nhóm khác. Không truyền --output thì không tạo report. Prompt không đọc label/expected evaluation.

Đã chạy: fake 350/350 dev + 33/33 test; fake wire/client/schema/grounding 29/29; 202 ví dụ hợp schema. Qwen thật bản sau sửa: 29/29 hành vi, 26/29 extraction_exact, 30 lần NLU/195,51 giây tổng, 3,74–13,89 giây/lượt. Có một lượt sửa lại JSON/bằng chứng trước khi đạt. Lần trung gian 23/27 không được báo thành đạt hoặc cộng vào điểm cuối. Không đưa đáp án test cuối vào prompt, không fine-tune hay thay model để tăng điểm.

API model giả/SQLite RAM: 9 lượt chat, hai phiên tách biệt, mặc định 24 sản phẩm in_stock, giữ bản nháp, số lượng và xử lý timeout/401/404/422 đúng. Các kiểm tra tiền/tham chiếu/kho/REVIEW dùng RAM. Không ghi DB thực, source website hoặc report; chưa click/render trình duyệt hoặc đánh giá Qwen toàn bộ 350 lượt.

## Ba đến năm yêu cầu — v46

Thêm dev-308…321: **14 lượt / 5 hội thoại**, tổng **321 lượt / 79 hội thoại**, version intent-context-v27, annotation_revision=22. Giữ nguyên 307 lượt trước và bộ test cuối 33 lượt.

- dev_multi_named_binding: ba món có thuộc tính riêng; bốn thuộc tính một món; năm món cùng hỏi giá; năm món với năm loại câu hỏi.
- dev_multi_independent_filters: ba/bốn nhóm với cận giá/vị riêng; năm yêu cầu gồm tư vấn, giá và chính sách chưa có nguồn.
- dev_multi_questions_before_order: trả câu hỏi trước, chọn hai bánh vani, hỏi thêm giữ draft, thêm một bánh khác mà không đặt các món chỉ hỏi.
- dev_multi_reference_memory: ghi nhớ đủ năm câu hỏi đã xử lý; giữ thứ tự lựa chọn và hiểu thứ nhất/thứ hai qua các lượt, gộp thuộc tính cùng món.
- dev_multi_empty_no_fabrication: năm câu hỏi khi chưa có menu, không bịa thông tin hoặc đơn.

score_turn chấm thêm expected.request_scopes: đúng intent của từng ID, đúng filters từng nhóm, đúng result_product_ids/tập và số kết quả mỗi yêu cầu. Không chỉ chấm union sản phẩm cả lượt. expected.remembered_questions kiểm tra số câu trong bản tóm tắt bộ nhớ; nhãn này không được gửi model.

Chạy trong chatbot (không truyền --output thì không tạo report):
```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split test --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --dialogue dev_multi_named_binding
```
Đổi dialogue để thử bốn nhóm còn lại. Model thật dùng Ollama local, không đọc đáp án test trong prompt. Exit code 2 cần đọc riêng extraction_exact, behavior_exact và lỗi, không tự coi là tất cả thất bại hay tất cả đạt.

Đã chạy: fake 321/321 dev + 33/33 test; fake wire/schema/grounding 14/14; 185 few-shot hợp schema; 13 guard/gộp/lỗi/phủ định đạt. Qwen thật trước sửa đầu đợt một trong bốn câu chọn lọc đạt; sau sửa cuối 14/14 hành vi và extraction_exact, một lần NLU/lượt, 171,89 giây tổng, 5,19–30,28 giây/lượt. Lần chạy trung gian 13/14 có lỗi thêm món lặp 37,43 giây không được tính đạt; sau sửa trường hợp đó đạt ở 15,27 giây.

API TestClient dùng model giả: 9 lượt chat, hai phiên riêng, nhóm giá riêng và thứ tự hỏi-trước-đặt, lỗi timeout giữ draft; 401/404/422 đúng. Mọi SQLite thử trong RAM; không ghi/reset database đang dùng hoặc report. Chưa click/render trình duyệt, chưa đánh giá toàn bộ 321 lượt bằng model thật hoặc benchmark thống kê. Không đổi nhãn để nâng điểm Qwen.

## Ngân sách và câu đồng nghĩa — v45

Thêm dev-274…307, tổng **307 lượt / 74 hội thoại**, version intent-context-v26, annotation_revision=21; bộ test cuối 33 lượt / 8 hội thoại giữ nguyên.

8 hội thoại mới:
- dev_money_paraphrase_window: khoảng hai số, dùng chung đơn vị, dấu gạch/nghìn/triệu/VNĐ, nhóm bánh kem và cách gọi tương đương.
- dev_money_paraphrase_directions: dưới/trên/không vượt/không dưới/trở lên/đổ xuống.
- dev_money_paraphrase_groups: mini/ăn vặt, cf/coffee, trà đúng giá.
- dev_money_named_price_aliases: tên rút gọn, hỏi nhiều thuộc tính, hỏi tiếp và phủ định đặt.
- dev_money_window_new_vs_keep: tìm nhóm với khoảng giá mới bỏ vị cũ; vẫn vị đó giữ điều kiện.
- dev_money_window_refinements: bổ sung khoảng sau khi hỏi nhóm rồi thay trần.
- dev_money_window_keeps_order: có bản nháp vẫn hỏi danh mục riêng; tham chiếu số ít vào nhiều bánh phải hỏi lại.
- dev_money_window_empty: chưa có nguồn không bịa sản phẩm.

Chạy từ thư mục chatbot, không truyền --output để tránh tạo report:
```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split test --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --dialogue dev_money_paraphrase_window
```

Đổi dialogue để thử nhóm khác. Exit code 2 có thể do extraction_exact không trùng đủ nhãn dù behavior đạt; xem cả hai điểm và model_errors, không chỉ một điểm tổng.

Kết quả đã chạy: fake 307/307 dev + 33/33 test; fake JSON qua client/schema/grounding trên 34 lượt mới đạt 34/34. Qwen thật trên cả 8 hội thoại: 34/34 hành vi, 27/34 extraction_exact, 36 lần NLU/214,94 giây, 3,18–10,62 giây/lượt, hai lượt cần sửa một lần. 175 few-shot hợp schema; 25 kiểm tra tiền/alias và 6 kiểm tra guard/retry/timeout đạt. API TestClient dùng RAM: 7 lượt chat, giữ draft, 401/404/422 và lỗi nguồn/model đều đúng. Không ghi database thực hay report. Chưa đánh giá Qwen trên toàn bộ 307 lượt hoặc render trình duyệt.

Trước sửa đã tái hiện câu chính bị thiếu/đảo cận, hai lần gọi rồi lỗi; sau sửa câu chính và các cách nói trong bộ trên được truy vấn đúng. Không đưa nhãn evaluation vào prompt và không gọi đây là huấn luyện model.

## Hương vị và kiểu pha — v44

Thêm dev-262…273 trong dev_flavor_catalog_groups và dev_flavor_catalog_styles_unknown. Gồm alias vị Việt/Anh, nhóm bánh kem/bánh nhỏ/trà/cà phê, giá, sữa/muối, kiểu đen/cold brew, Thái xanh khác matcha, và không gán vani cho bánh kem có tên trang trí. Bộ test cuối không đổi. Evaluation dùng GroupCatalogRepository(database_path=":memory:") để không phụ thuộc metadata SQLite đang dùng; lớp lưu trữ phân loại được kiểm tra riêng trên DB tạm.

Kết quả: fake 273/273 dev + 33/33 test, 159 few-shot đi qua schema. Qwen thực trên 12 lượt: trước sửa 10/12 hành vi, sau sửa 12/12, extraction_exact 9/12; 14 lần NLU, 5,42–14,02 giây/lượt. Hai lượt còn cần sửa một lần; không coi hành vi đạt là mọi field đều trùng nhãn. Thêm hai smoke Qwen về khoảng giá cà phê/“trà dưới 50k” đều đạt một lần gọi. Không dùng kết quả này làm số đo toàn bộ NLU/production.

22 trường hợp repository/lưu trữ đạt, gồm cache đọc một lần, không đổi 25 sản phẩm demo và 13 bảng ngoài metadata, chạy lặp không ghi lại, alias/chưa có vị/dị ứng, nguồn đổi tên/giá, metadata lỗi và đường dẫn có dấu/khoảng trắng. API TestClient đọc profile SQLite thực bằng kết nối chỉ đọc; tin nhắn thử lưu RAM, 12 lượt trả đúng sản phẩm, không tạo đơn. Chưa kiểm tra render/click trình duyệt.

Chạy riêng:
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --dialogue dev_flavor_catalog_groups

Đổi dialogue sang dev_flavor_catalog_styles_unknown để thử nhóm thứ hai; --engine fake kiểm tra logic. Không truyền --output thì không tạo report. Prompt chỉ đọc few-shot, không đọc nhãn evaluation.


## Liên hệ thông thường — v43

Các ví dụ và nhãn liên hệ cũ đã đổi sang tên bình thường và số tổng hợp dạng chuỗi; chỉ thay hợp đồng nhập liên hệ, không sửa nhãn nguồn hoặc biến đơn mẫu thành đơn thật. Bộ test 33 lượt giữ nguyên.

Thêm dev-252…261 trong dev_ordinary_contact_checkout và dev_ordinary_contact_eight_digits: nhập tên/số không tiền tố, giữ bản nháp khi hỏi giá bánh khác, phản hồi số quá ngắn, chuẩn hóa dấu phân cách, đổi số kèm đồng ý cần xem lại, xác nhận lặp và gửi yêu cầu chờ tư vấn. Phone 8–15 chữ số là kiểm tra cú pháp, không kiểm tra khả năng liên lạc. Toàn bộ liên hệ trong dataset là tổng hợp.

Chạy riêng bằng .\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake --dialogue dev_ordinary_contact_checkout. Đổi --engine ollama để gọi Qwen thật. Không dùng --output thì không tạo báo cáo. Prompt không đọc evaluation.

Kiểm tra thực tế trên bản v43:
- Fake model/SQLite RAM: 261/261 lượt dev, 33/33 lượt test đạt hành vi; 156 ví dụ đi qua schema hợp lệ.
- Qwen thật: 10/10 lượt chọn lọc đạt hành vi, không lỗi model cuối; thời gian 3,26–12,21 giây/lượt, tổng 59,31 giây. Gồm luồng tám lượt và câu cung cấp món/tên/số trong một lần.
- So khớp toàn bộ nhãn NLU chỉ đạt 1/10 ở mười lượt đó, khác với điểm hành vi: còn khác biểu diễn null/none, vị trí số lượng và chuẩn hóa số. Chưa đánh giá mọi câu hoặc công bố model hiểu hoàn hảo.
- API TestClient tải trang/JS/CSS/health/catalog trả 200, tạo phiên 201, tám lượt chat trả 200; một yêu cầu chờ tư vấn, một ticket, không có đơn kinh doanh. Xác nhận lặp giữ cùng mã. Token thiếu 401; truy cập chéo phiên 404; model timeout giữ nguyên bản nháp.
- 33 file Python hợp cú pháp, import API/run_web và run_web.py --help hoạt động. Kiểm tra số có dấu phân cách, số sai, bản nháp cũ, snapshot đã gửi, giữ revision khi số không đổi, che liên hệ trong lịch sử và không gửi lại liên hệ cũ trong prompt đều đạt.
- Chỉ dùng SQLite RAM cho các kiểm tra, không ghi/reset database đang dùng. Chưa click/render trên trình duyệt hay kiểm tra số điện thoại thực sự liên lạc được; chưa nối backend xác nhận đơn.

## Dữ liệu hiện tại

- `intent_context_dev.json`: **350 lượt / 87 hội thoại**, version v28, annotation_revision=23.
- `intent_context_test.json`: **33 lượt / 8 hội thoại**, giữ nguyên nội dung trong lần bổ sung này.
- `retrieval_dev.json`: **27 câu** cho 5 điều khoản giả lập trong `data/sample_policies.json`: 21 câu có nguồn, 6 câu không thể trả lời.
- `README.md`: hướng dẫn đọc nhãn và chạy đánh giá.

Dev/test là hai bộ riêng. Bộ test đã từng được dùng kiểm tra code nên không gọi là bộ chưa từng được xem. Không đưa đáp án test vào prompt.

Mỗi dialogue có id, mode và danh sách turns. Mỗi turn có message (câu khách), label (cách hiểu mong đợi), expected (hành vi code), id và turn_index. ID sản phẩm trong expected chỉ dùng chấm sau inference, không gửi như đáp án cho model.

## Ngân sách trà v42

Thêm 11 lượt dev-241…251:
- dev_tea_budget_reproduction: trà dưới 50k, đổi sang cà phê rồi hỏi lại trà.
- dev_tea_budget_boundaries: câu hỏi có/ko, dưới/không quá/trên/từ và khoảng giá 20–30k; biên 25k đối chiếu menu thật sự đang đọc.
- dev_tea_budget_keeps_draft: đang đặt hai bánh vani, hỏi trà không đổi bản nháp.

Fake: 251/251 dev + 33/33 test đạt; 155/155 roundtrip ví dụ đạt. Qwen thật: bốn lượt tái hiện sau sửa đạt, sáu lượt biên và hai lượt giữ đơn đạt, hai câu vani/dâu cũ đạt; tổng 14 lượt hành vi chọn lọc. Trong tám lượt evaluator mới, extraction_exact 4/8; không đổi nhãn để nâng điểm. Ba lượt trà lỗi trước sửa không tính đạt. Câu “trà dưới 50k” ở phiên mới từ 11,67 giây/hai lần gọi/lỗi xuống 5,52 giây/một lần gọi/đúng nguồn trong phép đo local này.

Mọi SQLite thử nằm trong RAM; không tạo report mặc định hoặc gọi nhãn test trong prompt. Dùng --dialogue các ID trên với engine fake/ollama theo hướng dẫn bên dưới.

## Hỏi lựa chọn trước khi mua v41

Thêm 23 lượt dev-218 đến dev-240, giữ nguyên 217 lượt cũ và bộ test 33 lượt:
- dev_shopping_exploration_mini: câu trong ảnh, không dấu, dưới/không quá/còn khoảng và không có kết quả.
- dev_shopping_named_then_order: muốn mua nhưng hỏi giá/còn hàng; chọn mua rõ rồi hỏi bánh khác và thêm số lượng.
- dev_shopping_groups_and_slots: bánh kem, trà, cà phê, đổi vị, phủ định mua và hai nhóm trong một câu.
- dev_shopping_empty_mode: chưa có nguồn vẫn ghi nhận đúng ngân sách, không bịa sản phẩm.
- dev_shopping_reset_old_flavor: tìm vị vani rồi hỏi lại nhóm bánh nhỏ phải bỏ vị cũ.

Fake/RAM: 240/240 dev + 33/33 test đạt; 151/151 ví dụ roundtrip, 25 guard nhóm đạt. Qwen thật bản cuối: bốn nhóm đầu 21/21 hành vi đạt, 15/21 extraction_exact, 22 lần gọi, 139,21 giây (4,26–13,14 giây/lượt). Nhóm cuối 2/2 hành vi và extraction đạt, hai lần gọi, 13,12 giây. Cộng 23/23 hành vi, 17/23 extraction_exact; không đổi nhãn để nâng điểm. Một lượt trà còn retry. Alias/cách mã hóa action/reference, search_scope và cờ biên giá còn có khác biệt. Không suy từ số lượt chọn lọc này ra độ chính xác toàn chatbot.

Đợt chạy trước bản sửa cận giá có ba lỗi/21 lượt. Các lỗi đó được giữ trong mô tả kết quả, không tính là thành công. Câu đầu ảnh ở phiên mới trước sửa đã trả đúng nhưng chọn mẫu hủy không phù hợp; lỗi ngân sách và vị cũ được tái hiện ở chuỗi mở rộng. Không dùng lượt đầu 52,70 giây để so tốc độ vì chưa tách thời gian nạp model.

Chạy lại bằng lệnh đánh giá bên dưới với --dialogue một ID trên; không truyền --output thì không ghi report. Engine fake kiểm tra code, engine ollama gọi Qwen thật. Model có thể sinh cách mã hóa khác hoặc kết quả khác ở lần chạy sau; giữ tách hai loại số đo.

## Câu tư vấn đồng nghĩa v40

Thêm dev-206 đến dev-217, giữ nguyên 205 câu cũ và bộ test 33 câu:
- dev_flavor_budget_paraphrases_vanilla: sáu lượt cùng vị vani, câu đầy đủ/lặp lại/khoảng trắng cuối/câu rút gọn, kiểm tra SP0015 và cận trên loại trừ.
- dev_flavor_budget_paraphrases_strawberry: sáu lượt tương tự cho dâu, kiểm tra SP0017; không tự bắt đầu đặt hoặc đổi bản nháp.

Kết quả fake cuối 217/217 dev + 33/33 test đạt, mọi kết nối SQLite RAM. Có thêm 135 roundtrip schema wire, giữ đủ field cho 53 ví dụ đặt hàng, 23 kiểm tra schema/an toàn cùng probe thiếu field/timeout và kiểm tra ngữ cảnh; không tạo báo cáo mặc định.

Qwen thật bản cuối v40 trên đúng chuỗi 9 câu người dùng: 9/9 hành vi đạt, mỗi lượt một lần gọi, tổng 48,08 giây, 5,19–5,74 giây/lượt. Câu vani đầy đủ ở phiên mới v37 bị lỗi sau hai lần/14,67 giây; v40 trả đúng sau một lần/5,41 giây, token sinh 76 xuống 55. Thêm 7/7 smoke thực tế đạt trong 37,64 giây, gồm câu vừa hỏi giá vừa đặt, tham chiếu thêm một món, giữ bản nháp khi hỏi bánh khác, cà phê, phiên mới và không dấu. Nhánh JSON thông tin gọn không nhận order_request; nhánh nghiệp vụ vẫn buộc đủ sáu trường. Không đổi model/options, không công bố extraction_exact/độ chính xác toàn bộ 250 câu từ smoke này. Bản thử bỏ field toàn cục từng timeout ở mixed order; đã sửa và không tính lần lỗi đó là đạt.

Chạy bằng các lệnh bên dưới; muốn chọn một nhóm, thêm --dialogue dev_flavor_budget_paraphrases_vanilla hoặc dev_flavor_budget_paraphrases_strawberry. Engine fake kiểm tra code theo nhãn; engine ollama chấm model thật chặt hơn, có thể khác nhãn search_scope/cách viết filter dù sản phẩm trả đúng. Không đọc nhãn evaluation làm đáp án trong prompt.

## Tìm mới và lọc tiếp v37

Thêm 20 lượt dev-186 đến dev-205 trong 6 hội thoại, giữ nguyên 185 lượt cũ và 33 lượt test:
- dev_search_scope_strawberry_chain: đúng chuỗi chính sách → dâu trên/dưới 200k → bánh kem/bánh trên 300k.
- dev_search_scope_same_group_and_budget: tìm mới cùng nhóm bỏ vị cũ, câu chỉ đổi giá giữ vị.
- dev_search_scope_explicit_flavor_and_multiquery: vị mới rõ và nhiều câu hỏi có phạm vi độc lập.
- dev_search_scope_allergy_preserved: đổi nhóm vẫn giữ điều kiện dị ứng.
- dev_search_scope_draft_separation: hỏi thông tin giữ nguyên món/số lượng của bản nháp.
- dev_search_scope_second_session: không lấy nhu cầu của phiên khác.

Scorer chấm requests.search_scope (nhãn cũ mặc định refine). Fake/RAM: 205/205 dev + 33/33 test đạt. Thêm kiểm tra schema từ chối new cùng tham chiếu cũ và guard từ chối tự đổi nhóm trong câu nối. Fake kiểm tra code, không đo khả năng hiểu Qwen.

Qwen thật trên bản v37 đạt 7/7 lượt được chọn (nguyên chuỗi 5 câu + 2 lượt có bản nháp): 8 lần NLU/85,28 giây; một lượt sửa JSON/căn cứ mất 43,56 giây. Còn sáu lượt 5,84–7,88 giây. Không tính lỗi các bản thử trước vào kết quả đạt; chưa chạy toàn bộ 238 lượt với Qwen. Xem README gốc cho kết quả và giới hạn.

Thêm 3/3 lượt Qwen về tìm mới → câu chỉ đổi giá → câu chỉ đổi vị, bản nháp hai Vani không đổi; mỗi câu một lần NLU, 14,03 / 8,19 / 6,06 giây. Tổng smoke cuối v37: 10/10 hành vi, 11 lần NLU/113,56 giây. Không phải extraction_exact trên toàn bộ bộ nhãn.

Để thử riêng chuỗi này, thêm --dialogue dev_search_scope_strawberry_chain vào lệnh evaluate_intent_context --split dev --engine ollama ở dưới. Không dùng --output nếu chỉ muốn xem kết quả trên terminal.

## Ngân sách và so giá v34

Thêm 23 lượt dev-163 đến dev-185 trong 7 hội thoại: khoảng/cận giá, rẻ/đắt nhất theo vị, gợi ý đúng nhóm, so giá với bánh đang xem, loại thứ hai, empty, dùng chung đơn vị và giữ trần ngân sách khi tìm loại đắt hơn. Bộ test 33 lượt giữ nguyên.

11 kỳ vọng top 5 cũ đổi thành tối đa 4. Tìm theo ngân sách vẫn kiểm tra ID/biến thể cụ thể; trường hợp ngẫu nhiên dùng recommendation_pool và recommendation_count kiểm tra đủ số, không trùng và thuộc danh mục hợp lệ. Scorer chấm thêm requests.price_preference để phân biệt chọn trong danh sách và tìm catalog khác.

Kết quả: 185/185 dev + 33/33 test fake; 38/38 kiểm tra biên fake/RAM; 135 mẫu prompt hợp lệ. Qwen thật chọn lọc đạt 14/14 lượt chính và 4/4 lượt bổ sung sau sửa lỗi tìm thấy; không tính lượt lỗi trước sửa thành đạt. Một số lượt còn 12–15 giây hoặc cần sửa JSON. Đây không phải độ chính xác Qwen trên toàn bộ 218 lượt. Chưa click/render web. Các phép thử dùng SQLite RAM, không tạo report/tests/docs mới.

## 50 lượt development bổ sung

Giữ nguyên 86 lượt cũ, thêm dev-087 đến dev-136:

- `dev_expanded_budget_windows` — 8 lượt: dưới/trên/ít nhất/tối đa/khoảng giá, thay khoảng cũ, bỏ giới hạn.
- `dev_expanded_product_types` — 6 lượt: bánh và đồ uống, đổi loại, bỏ lọc loại, không lẫn đồ uống vào yêu cầu tìm bánh.
- `dev_expanded_multiple_requests` — 6 lượt: nhiều câu hỏi, hỏi trước đặt, nhập liên hệ trong lúc hỏi bánh khác.
- `dev_expanded_references` — 6 lượt: cả hai, loại thứ hai, bánh đó và tham chiếu thật sự mơ hồ.
- `dev_expanded_cart_quantities` — 8 lượt: số lượng riêng từng món, thêm/bớt/bỏ/đổi, hỏi bánh khác giữ bản nháp.
- `dev_expanded_review_safety` — 5 lượt: sửa khi đồng ý, chưa gửi, REVIEW lại và xác nhận lặp.
- `dev_expanded_empty` — 3 lượt: chưa có nguồn không bịa bánh/giá, thu nhu cầu và hủy.
- `dev_expanded_allergy_handoff` — 3 lượt: hỏi thành phần khác với khai dị ứng, dị ứng nghiêm trọng và khiếu nại.
- `dev_expanded_language_policy` — 5 lượt: viết tắt/lỗi gõ, chính sách chưa có nguồn, câu tư vấn thiếu dữ liệu và đồng ý chưa rõ.

Hiện có **202 few-shot / version v47** trong data, gồm nhóm/vị, yêu cầu đang chờ và ngân sách/so giá. Few-shot là ví dụ đưa vào prompt, không phải fine-tuning (cập nhật trọng số model). Mỗi lượt vẫn chọn tối đa 2 ví dụ liên quan để tránh kéo dài prompt.

Các điều kiện tư vấn mới chỉ nằm trong requests.filters; updates để trống nếu không sửa slot đặt hàng. Không lặp cùng điều kiện trong cả hai nơi.


## 20 lượt bổ sung về nhóm/vị và bộ nhớ yêu cầu

Thêm dev-137 đến dev-156, không đưa các đáp án này vào prompt:

- `dev_group_types_flavors`: 7 lượt phân biệt bánh kem, bánh nhỏ, trà, cà phê; tìm trà xanh/vani/socola/dâu từ tên nguồn; không lấy bánh trà xanh làm trà uống.
- `dev_group_pending_donut_memory`: 5 lượt đặt hai Donut chưa rõ loại, nhắc lại, hỏi giá bánh khác, chọn ứng viên thứ hai; vẫn giữ đúng số lượng hai, không lấy bánh vừa hỏi giá thay cho Donut.
- `dev_group_pending_flavor_selection`: 2 lượt chọn Donut bằng “loại dâu”, không lặp tên và vẫn giữ số lượng đã có.
- `dev_group_pending_reference_information`: 3 lượt đặt Donut, hỏi Hawaii rồi hỏi giá loại thứ hai; chỉ hỏi giá Donut tương ứng, giữ yêu cầu đặt đang chờ.
- `dev_group_no_receiving`: 3 lượt thu món/số lượng, hỏi giá tham chiếu rồi sửa số lượng; không hỏi hình thức giao/nhận hoặc địa chỉ.

Nhãn `pending_quantity` và `pending_candidate_ids` kiểm tra trực tiếp yêu cầu chọn món đang chờ. Khách hỏi thêm không xóa yêu cầu này; chỉ tiếp tục khi khách thực sự chọn hoặc sửa yêu cầu. Dữ liệu cũ vẫn giữ nguyên câu khách từng nhắc giao/nhận, nhưng nhãn cập nhật không thu `fulfillment/address` nữa. Bộ test 33 lượt giữ nguyên file; cả dev/test hiện không có nhãn hoặc expected cho fulfillment/address. Scorer so sánh trực tiếp các slot còn được khai báo, không chuyển đổi ngầm đáp án cũ. Không gọi đây là test chưa từng xem.

Các ví dụ hướng dẫn mới vẫn dùng tên trừu tượng A/B/C và không xác nhận sản phẩm có bán. Không tăng giới hạn hai ví dụ trong prompt, không fine-tune trọng số.

## 6 lượt hồi quy vị nói ngắn

dev-157 đến dev-162 trong dev_group_short_flavor_followups: bánh kem socola → bánh nhỏ trà xanh → “vani thì sao” → cà phê → trà dâu không có → “đào thì sao”. Kiểm tra đúng sản phẩm, bộ lọc, trạng thái và giữ bản nháp. Hai câu ngắn chỉ nêu flavor mới; không tự xóa nhóm còn phù hợp. Lượt không có kết quả vẫn giữ nhóm khách hỏi rõ, tránh quay về nhóm cũ.

## Quy ước nhãn

- `budget_vnd` là cận trên; `price_inclusive` cho biết có nhận giá bằng cận không.
- `min_budget_vnd` là cận dưới; `min_price_inclusive` tương ứng.
- “Dưới/trên” loại biên; “không quá/ít nhất” nhận biên; “từ X đến Y” nhận cả hai biên.
- `product_type=cake` gồm mọi bánh; `cream_cake` là nhóm cake trong dữ liệu nhóm; `mini` là bánh ngọt nhỏ; `drink` gồm mọi đồ uống; `tea` và `coffee` chỉ phân loại trong nhóm drink theo tên nguồn. Bánh cuộn trà xanh không phải trà uống.
- `flavor` là vị khách muốn tìm. Nguồn nhóm chỉ đối chiếu từ tên đã công bố, không suy đoán thành phần hoặc độ an toàn dị ứng. Không có vị tương ứng thì trả không tìm thấy, không bịa.
- Điều kiện giá mới thay khoảng giá trước; clear_slots=["budget_vnd"] bỏ cả hai cận và các cờ biên.
- `order_items` có tên/tham chiếu và số lượng riêng; “cả hai” không có nghĩa hai chiếc mỗi loại.
- `expected.filters` so đúng toàn bộ conversation.needs.filters theo tên nội bộ max_price_vnd/min_price_vnd.
- `expected.variant_ids` là danh sách phẳng ID biến thể thực tế trả về, giúp bắt trường hợp đúng bánh nhưng sai size/giá.
- `expected.items` kiểm tra món và số lượng theo thứ tự trong bản nháp.
- Tư vấn chung hiển thị tối đa 4 kết quả: có ngân sách thì theo giá, không có thì lấy ngẫu nhiên trong tập hợp lệ; rẻ/đắt nhất và so giá có thứ tự riêng. Nhãn kiểm tra số lượng/tập sản phẩm; các bánh được hỏi rõ vẫn trả đủ.
- dev-119 kiểm tra giới hạn đổi trực tiếp trong bản nháp nhiều món: phải hỏi rõ, giữ bản nháp và hướng dẫn bỏ/thêm; dev-120 không tự phát lại thao tác đổi khi khách cung cấp liên hệ.
- `response_contains/response_absent/response_counts/response_order` kiểm tra nội dung, lặp thông tin và thứ tự trả lời trước phần đặt.

dev-135 giữ sở thích ít ngọt trong flavor (sở thích vị), không biến thành dị ứng; nguồn phải xác minh metadata trước khi tư vấn.

## Lệnh Windows

Đứng trong thư mục chatbot, dùng đúng Python của .venv:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.prepare_intent_dataset
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split test --engine fake
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_retrieval
```

prepare_intent_dataset chỉ kiểm tra schema/ID/số lượt, không dựng lại rồi ghi đè bộ nhãn. fake đưa nhãn vào controller để kiểm tra logic; **không đo khả năng hiểu Qwen**. Evaluator dùng SQLite RAM riêng, không đọc/reset database đang dùng.

Muốn đo Qwen thật với một hội thoại khi Ollama/model đã sẵn sàng:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m scripts.evaluate_intent_context --split dev --engine ollama --dialogue dev_expanded_budget_windows
```

Không truyền label/expected cho Qwen. Model/JSON lỗi vẫn tính là lỗi, không loại khỏi thống kê. Không tự tải/đổi model. Evaluator chỉ có engine fake/ollama; không cần API key.

Mặc định chỉ in kết quả. Chỉ khi chủ động chọn --output mới ghi báo cáo .json trong runtime; không tạo thêm report trong evaluation. Lệnh compare_intent_context cần --before/--after của hai báo cáo thực sự đo cùng bộ nhãn/danh sách lượt.

## Đọc kết quả và giới hạn

- `behavior_exact`: đạt các hành vi có nhãn và processing_ok; lượt model/nguồn lỗi không được tính đạt chỉ vì draft giữ nguyên. Chưa chứng minh mọi câu trả lời tự nhiên đều đúng.
- `extraction_exact/intent_micro_f1`: chỉ đánh giá model khi engine=ollama; điểm fake không phải độ chính xác Qwen.
- `request_links_exact`: so intent, đối tượng, tham chiếu, size, điều kiện lọc và danh sách loại trừ của từng câu hỏi.
- `order_items_exact`: chỉ chấm khi label có order_items; Pydantic chuẩn hóa nullable/default rồi so thứ tự, tham chiếu và số lượng riêng.
- `schema_grounding_ok`: JSON hợp lệ và có căn cứ; chưa chứng minh đơn đủ điều kiện xác nhận.
- `dataset_sha256/code_sha256`: dấu vân tay dữ liệu/code; `completed=true` chỉ nói đã chạy hết lượt được chọn.

Kết quả chạy lại 15/10/2026: **129/129 few-shot**, **162/162 dev và 33/33 test fake** đạt extraction/behavior/processing, không model/source error. Fake đưa nhãn vào controller để kiểm tra logic, không đo độ chính xác Qwen. SQLite RAM, không ghi báo cáo mặc định.

Qwen thật qwen3.5:4b đã thử **15 lượt/3 phiên**: hai bánh cuộn, bỏ câu nhận tại cửa hàng, Donut nhắc lại/hỏi xen ngang/chọn vị, bánh kem/bánh nhỏ/trà/cà phê. Không lỗi model/nguồn; mỗi lượt một lần gọi, 3,77–7,05 giây/lượt lúc đo. Đây là smoke kiểm tra hành vi, không phải extraction_exact toàn bộ nhãn. Lần thử riêng “thêm 1 bánh này” trước đó cần sửa JSON một lần, mất 11,47 giây.

Bản cuối đã thử lại chuỗi sáu câu trên bằng Qwen thật: **6/6** hành vi đạt, giữ bản nháp, không lỗi model/nguồn, 5,03–11,23 giây/lượt; câu cà phê sửa JSON một lần. Lần trước cùng chuỗi đạt **4/6**, đã sửa clear nhầm và nhóm tư vấn sau noresult. Không gọi điểm này là độ chính xác toàn bộ dataset.

Chuỗi Donut bản cuối cũng đạt **6/6**: đặt hai → nhắc lại → hỏi Hawaii → chọn dâu → thêm một → hỏi giá bánh đó. Giữ đúng số lượng, không sửa bản nháp khi chỉ hỏi giá; 4,42–11,16 giây/lượt, câu thêm một cần một lần sửa JSON. Không cộng các smoke có thể chồng lấn thành độ chính xác chatbot.

Các lần trong quá trình sửa từng gặp JSON sai khi nhắc lại Donut, không khớp bánh nhỏ vani và bộ lọc nhóm cũ còn lưu sau câu hỏi con. Đã sửa ở prompt/selector/repository/controller và kiểm tra lại; không tính các lần lỗi thành lượt đạt hoặc suy chất lượng model từ fake.

Kết quả retrieval đã đo trước đây trên 27 câu: Recall@3=1.0, hit@1=0.952381, MRR=0.976190; tỷ lệ không lấy nguồn cho câu không thể trả lời=0.5 (3/6). Retriever còn lấy nguồn ở 3/6 câu thiếu đáp án. Đây là chất lượng truy xuất, không phải độ đúng câu trả lời RAG.

Ở lần đo lịch sử 15/10, chưa đánh giá Qwen thật toàn bộ **195 lượt khi đó (162 dev + 33 test)**. Không công bố độ chính xác toàn chatbot từ nhãn giả hoặc một vài smoke test. Xem README gốc để biết luồng model thực tế đã đo và giới hạn nguồn menu nhóm.

## Rà soát phần kiểm thử — 16/10/2026

Đã bỏ scripts/check_local_demo.py: script smoke cũ phụ thuộc ORDER_PROVIDER của môi trường, gắn cứng luồng demo và tự giữ database/báo cáo qua mỗi lần chạy. Các ca REVIEW, sửa yêu cầu và xác nhận lặp đã có trong bộ intent/context dùng SQLite RAM; dùng evaluate_intent_context để kiểm tra các ca này.

Đã bỏ nhánh chấm tương thích fulfillment/address không còn được bộ nhãn sử dụng và biến ROOT không dùng trong script so sánh. Giữ nguyên ba bộ dữ liệu, script kiểm tra nguồn nhóm, kiểm tra ngữ cảnh và RAG. Không xóa dữ liệu hội thoại/đơn, không đổi logic chatbot hoặc dependency.

Kiểm tra sau khi dọn: 162/162 dev và 33/33 test dùng model giả đạt; 34 file Python hợp cú pháp, 13 module import được, không còn import script đã xóa. API /health, trang chủ và /api/catalog trả HTTP 200 trong TestClient dùng RAM. Bộ retrieval chạy đủ 27 câu, kết quả nguồn như trước (Recall@3=1, MRR=0,97619; từ chối đúng 3/6 câu thiếu đáp án). Chưa gọi lại Qwen thật hoặc click trình duyệt trong lần dọn này; không công bố điểm fake là chất lượng model.

## Kiểm tra tối ưu tốc độ — 16/10/2026

Bản cuối giữ schema sáu field bắt buộc, 129 few-shot v26 và dataset hiện có. Chạy lại fake: 162/162 dev + 33/33 test đạt; 129 ví dụ hợp lệ, 1.548 lần dựng prompt và kiểm tra cách ly cache schema đạt. Không đưa nhãn test vào prompt.

Qwen thật: bộ đo 12 lượt không lỗi, mỗi lượt NLU một lần; hai câu chính sách thêm bước RAG. Thêm một bánh theo tham chiếu giảm 11,41 → 6,27 giây; phí mẫu giảm 14,05 → 7,20 giây. Kiểm tra mở rộng 11/11 lượt về nhiều ý định/REVIEW/xác nhận lặp/empty đạt; một câu hỏi giá kèm đặt vẫn sửa JSON, 19,98 giây. Không gọi đây là độ chính xác toàn bộ 195 lượt.

RAG nội bộ chọn số câu, Python mở rộng thành quote nguyên văn với source_id/version cũ. 112 kiểm tra RAG và kiểm tra API/import đã chạy bằng fake; mọi thử nghiệm dùng RAM, không tạo báo cáo. Xem README gốc cho số đo/cấu hình/giới hạn đầy đủ. Nội dung bộ dev/test/retrieval không đổi trong đợt tối ưu này.

## Kiểm tra prompt/ngữ cảnh — 17/10/2026

Giữ nguyên nội dung các bộ dev/test/retrieval. Prompt dùng 129 few-shot v30, tối đa hai ví dụ và sáu field bắt buộc. Bộ test không được đưa vào prompt.

Bản cuối fake: 162/162 dev + 33/33 test đạt; 129 ví dụ/268 wire assertions, 1.548 prompt builds, 34 cache/API guards và 90 kiểm tra projection đạt. Không gọi điểm fake là độ chính xác model.

Cùng 16 lượt Qwen thật: bản cuối đạt các hành vi kiểm tra, 20 → 16 lần gọi NLU và 116,82 → 88,30 giây. Bao gồm nhiều ý định, liên kết từng bánh, phủ định, chuyển vị, hỏi giá trước đặt, REVIEW sửa/xác nhận lặp và empty đổi ngân sách giữ nhu cầu cũ. Không phải mọi câu nhanh hơn; xem README gốc cho số đo và giới hạn. Không tạo artifact/report mặc định; hội thoại thử chỉ dùng RAM.

Bản chốt v30 thêm 22 kiểm tra bảo vệ tham chiếu bản nháp và chạy **13/13 lượt Qwen mở rộng** đạt hành vi sau khi sửa hai lỗi quan sát được (lần trước 11/13). Các ca bao gồm tham chiếu bảo quản, thêm vào draft khi đang xem bánh khác, Donut pending, viết tắt, hai món mỗi loại một và giá kèm policy có nguồn. Một lượt chọn dâu sửa JSON, 14,14 giây. Bộ 16 lượt so sánh được chạy lại trên đúng v30: 16/16 đạt, 88,30 giây/16 lần NLU. Không xem tổng 29 lượt được chọn là độ chính xác toàn chatbot.
