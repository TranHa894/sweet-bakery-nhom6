# Tiến độ hiện tại — intent/context 06/10/2026

Công việc chạy độc lập sau giai đoạn 6 đã triển khai; **giai đoạn 7 đánh giá tổng thể tạm hoãn**. Các mục phía dưới là lịch sử, không đại diện cấu hình hiện tại.

## Cải thiện intent/context (05–06/10/2026)

- Đọc code/tài liệu và theo dõi toàn luồng. Bản sửa scope trước đã chặn tên dâu rõ kèm reference=last kéo socola. Vẫn thiếu liên kết từng intent/tên/size; guard kiểm tên thiếu bị bỏ qua khi có reference; tên chuẩn bị từ chối quá chặt; hành động thêm/xóa chưa rõ. Không quy tất cả lỗi cho model.
- schemas.py thêm InformationRequest/requests và order_product_mentions/order_operation, kiểm tra bằng Pydantic. resolve_message_scopes tách truy vấn thông tin với mục tiêu đơn; trả đúng thuộc tính của từng request. Tên mới không dùng draft làm sản phẩm dự phòng; nhiều nghĩa hỏi lại. Hỏi thông tin giữ draft và bước đang chờ. Lỗi nguồn không biến thành câu trả lời thành công một phần hoặc ghi đơn.
- Grounding kiểm tên thiếu kể cả khi có reference; tên chuẩn chỉ hợp lệ khi alias xác định duy nhất cùng sản phẩm. Chữ trên bánh không trở thành tên/lệnh xóa. Few-shot dùng bánh A/B/C trừu tượng; Qwen vẫn bộ hiểu chính. Không đổi model, HTTP client/options, fine-tune hoặc thêm dependency. Regex chỉ dùng cho guard hẹp, không tự tạo intent thay Qwen.
- Thêm loại khác phải hỏi lại, không thay draft; REVIEW cũ mất hiệu lực và revision tăng khi chưa giải yêu cầu thêm. Xóa chỉ đúng target draft; sửa/xóa đơn đã confirmed đi hand-off kể cả model thiếu order_update. Giữ các quy tắc empty/mock/unverified, khả năng adapter thật, idempotency và transaction cũ.
- Bộ **74 nhãn viết tay**: dev 48 lượt/11 hội thoại, final 26 lượt/7 hội thoại; không trùng IDs/messages. Nhãn tách few-shot, chỉ chấm sau inference. Model giả chạy đủ 74 lượt qua controller; test riêng kiểm liên kết, alias trùng, lỗi, REVIEW, confirmed và tách phiên. Nhãn dev-044 sửa thành HANDOFF theo contract empty; giữ baseline gốc và ghi annotation_revision=2, chỉ chấm lại tiêu chí state.
- **406 passed, 1 warning, 10.87 giây, exit 0**; compileall exit 0. Model giả/database riêng, chặn Ollama. Helper datetime ban đầu chưa chuẩn UTC được sửa dùng update_slot. Guard recommendation từng gây 4 regression preferences; đã tách bảo vệ draft với cập nhật needs/filter, chạy lại đạt. Không hạ validation. Warning Starlette/HTTPX hiện có, không thay dependency.
- Qwen thật `qwen3.5:4b`, prompt v8: **smoke scope chạy lại trên code bàn giao sau D96 đạt 4/4, exit 0**, draft socola không đổi; hai lượt hỏi giá/bảo quản dâu chỉ demo-002, hỏi cả hai trả demo-001/demo-002. Report context_scope_after.json giữ previous_runs, SQLite riêng. Prompt có schema đọc được và tối đa 3 few-shot; format HTTP/Pydantic đầy đủ. V4 có 12 lỗi/48, behavior 26/48; v5/v6 chưa tốt. V7 smoke scope đạt nhưng dev có 8 lỗi, behavior 29/48 và trace copy tên socola cũ; đã giảm tên trong prompt theo D95. Chọn v8 theo dev trước khi chạy final.
- Lượt v8 đầu full dev: intent 40/48, F1 0,8866, query 20/24, behavior 34/48, errors 5; final đầu 26: intent 20/26, F1 0,8571, query 13/15, behavior 21/26, errors 5. Sau đọc trace **dev-006/dev-018**, bổ sung D96 kế thừa chủ thể trong lượt hiện tại, bỏ scope trùng và hỏi lại tham chiếu chưa rõ cùng 4 tests. Prompt/schema/dataset không đổi, không dùng lỗi final chọn sửa. Mọi lần thử giữ trong previous_runs; retest cùng tập không là bộ kiểm tra độc lập mới.
- **Đã đo xong code bàn giao**: dev trước → sau: intent 33/48 → 39/48; F1 0,7500 → 0,8842; query 16/24 → 17/24; behavior 30/48 → 32/48; extraction 14/48 → 23/48. Draft unchanged giữ 29/29. Action giảm 43/48 → 40/48, state giảm 14/19 → 13/19, lỗi model/grounding tăng 2 → 7; không kết luận mọi mặt đều tốt hơn.
- **Test cuối Qwen thật (26 lượt)**: intent 20/26, F1 0,8571, query 13/15, behavior 21/26, extraction 10/26, draft unchanged 17/17; model errors 5, controller source errors 0. Các hash code/few-shot khớp code cuối. Cả 7 lỗi dev và 5 lỗi test giữ nguyên toàn bộ draft. Requests binding chỉ 1/3; thêm/xóa operation model thật 0/2, vẫn có lỗi viết tắt, phủ định, đổi loại và tham chiếu. Xem evaluation/intent_context_comparison_report.json và intent_context_final_test_report.json. Đo hẹp NLU/controller với knowledge empty, không generation RAG hay stage 7 tổng thể.
- Bài học docs/learning/intent_context_improvement.md và quy trình evaluation/intent_context_protocol.md; cập nhật schema/contracts/decisions/README/integration/spec. Không reset database đang dùng hoặc xóa history; UI chưa kiểm click/render thật trong lần này.

## Sửa môi trường pytest Windows (05/10/2026)

- Traceback người dùng: PermissionError/WinError5 ở tmp_path → getbasetemp → duyệt thư mục đánh số trong AppData/Temp. Fixture autouse block_real_ollama phụ thuộc tmp_path nên nhiều test cùng ERROR trong setup, chưa chạy assertion chatbot. Phiên công cụ vẫn chạy lệnh cũ đạt21/0.74s; chưa xác định vì sao terminal người dùng bị từ chối quyền.
- tests/conftest.py thêm hook pytest_configure(tryfirst=True) đặt basetemp tuyệt đối mới `.pytest_tmp/run-UUID` khi chưa có --basetemp. .gitignore bỏ qua thư mục sinh ra. Giữ lựa chọn explicit của người chạy; không chọn folder chung hoặc database demo làm basetemp.
- Sau sửa: lệnh ngữ cảnh gốc **21 passed/0.67s**; kiểm explicit basetemp **21 passed/1.20s**, giữ đường dẫn đúng. Toàn suite trong phép mô phỏng đúng nhánh duyệt Temp bị từ chối: **356 passed,1 warning,10.59s,exit0**; base nằm trong project, không gọi nhánh duyệt Temp bị chặn.
- Mô phỏng đầu chặn gettempdir quá rộng gây lỗi bộ thu stdout/stderr trước khi nạp conftest; đã điều chỉnh mô phỏng đúng nhánh traceback rồi đạt. Không sửa ACL/xóa AppData, không tăng quyền hoặc chạm database demo. Không sửa logic/Qwen, không gọi model thật hoặc restart API trong lần này. Chưa xác minh chạy lại trong chính terminal người dùng.
- Bài học: docs/fixes/pytest_temp_permissions.md; cập nhật README/contracts/decisions/next_steps và bài sửa scope. Stage7 vẫn hoãn.

## Sửa lỗi phạm vi sản phẩm trong ngữ cảnh (04/10/2026)

- Đọc tài liệu và implementation trước sửa. Tái hiện bằng Qwen thật: hỏi dâu sau khi đặt socola có mention dâu nhưng reference=last; resolve_mentions cộng thêm ID socola trong draft. merge_preferences/product_answer tiếp tục dùng bộ lọc sản phẩm lưu chung, nên trả hai bánh. Bằng chứng: evaluation/context_scope_before.json.
- Tách current_turn (truy vấn hiện tại, không persist), conversation_context (focus/tham chiếu, persist), order_draft (giữ key order cũ). Tên hiện tại ưu tiên hơn reference thừa; tham chiếu nhiều cách hiểu hỏi lại. Hỏi thông tin không sửa draft/bước đang chờ; thay sản phẩm rõ ràng kiểm lại size/topping, tăng revision và bỏ REVIEW cũ. Giữ lịch sử và các quy tắc empty/mock/nguồn thật.
- Prompt Qwen chia order_draft và conversation_context, schema thêm reference=order. Giữ HTTP client/model, không thay bộ hiểu chính bằng regex, không thay schema SQLite hoặc API công khai. Các nguồn giá vẫn qua repository.
- **Toàn suite: 356 passed, 1 warning, 29.78s, exit0.** Có 21 ca regression mới với fake model/DB riêng: A–F, reference mâu thuẫn, REVIEW, alias không tìm thấy, empty/mock, nhiều tên, dị ứng và persistence. Warning Starlette/HTTPX như trước.
- **Qwen thật qwen3.5:4b: 4/4 lượt smoke scope đạt**: đặt socola → giá dâu → bảo quản dâu → giá cả hai. Hai lượt dâu chỉ demo-002; draft socola so sánh toàn bộ không đổi. Script scripts/check_context_scope.py dùng SQLite smoke riêng; report evaluation/context_scope_after.json passed=true, giữ previous_runs.
- Smoke đặt DEMO rộng chạy sau sửa scope: năm bước giá/REVIEW/sửa/xác nhận/xác nhận lặp đạt, vẫn chỉ một đơn; lượt cuối giờ mở cửa bị Qwen hiểu thành availability, nên evaluation/local_demo_smoke_report.json hiện **passed=false**. Đã làm rõ prompt và thử riêng policy trên cùng phiên confirmed: evaluation/context_scope_policy_followup.json passed=true, đúng nguồn, vẫn một đơn. Chưa chạy lại toàn bộ smoke rộng sau câu prompt này; không gọi lần rộng thất bại là 6/6 đạt.
- Không reset database đang dùng, không xóa lịch sử, không tải/đổi model, không thêm dependency. API cần restart để import code mới; token RAM mất hiệu lực, dữ liệu SQLite vẫn giữ. Chưa kiểm thao tác/render browser thật. Bài học: docs/fixes/context_product_scope.md.
- Đã restart đúng tiến trình API local đã khởi động trong phiên trước, để cổng8000 chạy với bản sửa. HTTP thật /health, / và /static/chat.js trả200; tạo phiên trả201/BROWSING, chat_mode=ollama. Chỉ thêm một phiên kiểm kết nối, không gửi chat/tạo đơn/reset vào DB đang dùng, không in token. compileall exit0; kiểm8file tài liệu không có link local hỏng.

## Sửa lỗi giao diện Failed to fetch (04/10/2026)

- Khi kiểm tra ảnh người dùng: GET /health, GET / và POST /api/conversations ở cổng8000 đều WinError10061/refused. Không có API lắng nghe, lỗi xảy ra trước khi gọi Qwen.
- Đã khởi động run_web.py nền, chỉ loopback8000, giữ chạy để người dùng tải lại. /health200 với local_demo/Ollama; createconversation201/BROWSING; HTML và JS200. Không reset/seed lại dữ liệu, không đổi model.
- static/chat.js hiển thị lỗi network bằng tiếng Việt/hướng dẫn kiểm tra server; thất bại tạo phiên cập nhật nhãn nguồn chưa xác định, không giữ trạng thái đang kết nối. README/bài học bổ sung hướng dẫn main.py khác run_web.py.
- Kiểm tra cú pháp JS đạt; tests/test_api.py **31 passed,1 warning,2.16s**. Chưa kiểm thao tác reload/render trong browser thật.

## Kiểm tra trước khi sửa

Đọc README, sáu docs theo dõi, nguồn implementation; không có AGENTS tại root/ancestor/source. Python .venv3.12.10, sqlite3 có sẵn, không ORM, không Git. Baseline **287 passed,1 warning,13.05s**. Nền API/UI/controller/retrieval/FSM/storagev1 dùng được nhưng chưa catalog/policySQL/atomicstock; modeQwen còn lệnh bypass/fallback. Chưa backend/menu/chính sách thật.

## Đã hoàn thành

- sqlite3 schema v2 migrate tại chỗ, backupv1, FK/check; thêm catalog/variant/topping/policy/settings/messages/orders/items, giữ drafts/submissions/tickets cũ và ID.
- Seed25bánh/35biến thể/3topping/13policies, mô phỏng, nguồn active/knownstock/outstock/unknown/allergen/lead/writing/topping. Seed lặp không overwrite stock/price hiện tại; reset riêng verifiedruntime/--confirm/backup/transaction.
- LocalCatalogRepository/LocalKnowledgeRepository SQL, source factory và OrderTools get_order owner, provider unsupported rõ; không adapter future giả thành công.
- Unified Qwen intent/action/typed delta mọi nghiệp vụ, strict Pydantic + grounding + tối đa1repair; không tự rule fallback; lỗi giữ state và không submit. Context riêng/gọn/persist, mentions xác minh nguồn, tham chiếu kết quả, sửa/xóa delta.
- RAG policySQL giữ keywordtop3/version/hash, Qwen chọn quote/citation mô phỏng; no source abstain, lỗi nguồn không success.
- FSM BROWSING/COLLECTING/REVIEW/DEMO_CONFIRMED/CANCELLED/HANDOFF, revision/sourcehash, confirm kèm edit review lại, confirmed immutable; một loại mỗi draft, quantity nhiều.
- Business kiểm active/variant/topping/stock/lead/giờ nhận/NFCchữ/delivery/contactgiả/allergy. Quote từ metadata, integerVND. Submit transaction sameconn/conditionalstock/UNIQUEkey/snapshot, không oversell/lưu nửa đơn.
- Ticket pending local reason/priority/summary/missing/orderowner/outsidehours, không gửi nhân viên ngoài.
- CLI cùng service/API, /new /exit /draft /orders /order /resume, sửa slashcommand bug. API token owner/state richschema; giữUI/textContent, cập nhật nhãn DEMO/UTC→giờVN.
- Bài học local hoàn thiện có kiến trúc/bảng/code/15vấnđáp/5bàitập; README và config/tracking/integration hiện hành.

## Kiểm thử thực tế

| Kiểm tra | Kết quả |
| --- | --- |
| Suite local completion trước sửa context, sau thêm wire regression | **335 passed,1 warning,11.62s**, exit0; suite hiện tại xem mục sửa context ở trên |
| pip check | No broken requirements found, exit0 |
| compileall app/main/run_web/scripts/tests | exit0 |
| JS parse bằng new Function V8 | Đạt cú pháp, không DOM/browser test |
| init/seed/check DB mặc định | v2, FKenabled true, FKerrors0, integrity ok;25/35/3/13 giữ nguyên sau seed lặp |
| Test logic | DB riêng, fake model, urlopen Ollama bị chặn; không dùng độ chính xác model thật |
| Migration/testbackup/reset | v1 giữdata/ID, no retrostock; reset từ chối path/marker/cờ sai, CLI probe chỉ đọc trước init/migrate, file không được xác minh giữ nguyên bytes và không tạo file ngoài runtime; own temporary demo test positive; lỗi reseed rollback |
| Stock transaction | trigger insert lỗi không trừ một phần; hai yêu cầu cạnh tranh chỉ1tạo đơn, stockkhôngâm; repeatconfirmkhôngtạothêm |
| API owner/validation/errors | TestClient dùng fake, token thiếu/sai/khácphiên chặn, richresponse/review/order và modelerror giữstate |
| CLI thật + Qwen | main.py trả demo-001/16&20cm/250.000&350.000, engineollama; /orders [] và /exit exit0 |
| HTTP/Uvicorn thật + Qwen | /health/assets200; chat200/engineollama/demo-001; token thiếu401, khácphiên404; report local_api_smoke_report.json passed=true |
| Qwen thật controller trước sửa context | **6/6 bước smoke đạt ở lần local completion**, qwen3.5:4b local; kết quả mới xem mục sửa context |

Lần real smoke local completion trước sửa context (nay nằm trong previous_runs tại evaluation/local_demo_smoke_report.json): price/size demo-001 đúng; natural9slot → REVIEW500.000; đồng ý+đổi20cm → REVIEW700.000,0đơn; confirm → DEMO_CONFIRMED1đơn/unpaid; repeat → vẫn1; openinghours policy có demo-policy-001 và demo-policy-010. 10,56–34,08 giây/lượt, tổng khoảng124giây, không phải benchmark. Nguồn ngoài giờ có thể thừa, chưa chứng minh semanticpolicyaccuracy.

DB smoke riêng runtime/model-smoke-0aff76f4.sqlite3; conversation ee05620e-cd18-41b7-bab4-7afc5ccfe808; order ID 0ddfa15a-5fd8-4bc2-87b3-2c1c9b8f4ce2, mã DEMO-0DDFA15A, tổng700.000. Không tạo đơn smoke vào DB đang dùng. Report giữ8lần thử trước (timeout, JSONtype sai, missingmention, copyoldslots, omitcontact, wrongintent, policyabstain), không chỉ ghi lần thành công. Các lần đó thúc đẩy typedwire/contextgọn/prompt; không chứng minh Qwen luôn đúng.

Ở lần check trước CLI thủ công: DB mặc định có124conversations/124drafts/20messages/0orders/0tickets. CLI smoke thủ công thêm một phiên hỏi giá, check cuối có125conversations/125drafts/22messages, vẫn0orders/0tickets; menu/stock giữ nguyên. Trước sửa114phiên v1; khi chạy test CLI kế thừa ban đầu, test chưa cô lập nên ghi10phiên giả vào defaultDB. Đã sửa test dùng tempDB, **không xóa dữ liệu** để che việc này. Backup trước migration runtime/chatbot.sqlite3.schema1-20261004T120531344626.bak có114phiên/v1. Không reset DB đang dùng, không xóa file data/model, không cài package AI mới.

Test reset CLI bổ sung ban đầu lỗi cleanup Windows vì with sqlite3.connect chỉ quản lý transaction, chưa đóng file; sửa test dùng contextlib.closing, chạy lại toàn suite đạt335. Không phải lỗi mất dữ liệu hay lỗi reset. Server kiểm tra riêng cổng8768 đã dừng; không dừng server cũ của người dùng.

## Phần chưa kiểm tra và giới hạn

Browser API không có surface, mở iab báo unavailable. HTTP health/assets và API không thay kiểm UIclick/render/responsive/XSSDOM thật. NLU/RAG tập rộng/held-out, multiworker/performance, PII hoàn chỉnh, multi-item, embedding, backendauth/realorders/paymentdelivery chưa làm. Contacts chỉ fake DEMO/TEST, ticket localpending. Warning Starlette TestClient dùng HTTPX deprecated; chưa chuyển dependency. Stage7 vẫn hoãn.

---

# Lịch sử tiến độ stage_01–06

# Tiến độ dự án

Cập nhật: 03/10/2026, Asia/Saigon. Giai đoạn được yêu cầu: **6 — API và giao diện chat local**.

## Kiểm tra ban đầu giai đoạn 1 — lịch sử

- `D:\Chatbot` trống; không có code, cấu hình dependency hoặc Git repository.
- Không có `AGENTS.md` tại folder hoặc `D:\AGENTS.md`; các file theo dõi chưa có.
- Python mặc định: 3.12.10; `py` còn có Python 3.13.7 và mặc định chọn nhánh 3.13.
  Vì vậy dùng rõ `py -3.12` để tạo môi trường.
- Có `pip` 26.2.1 ngoài môi trường, `uv` 0.12.13, Git và VS Code CLI. Phiên bản
  `pip` bên trong `.venv` là 25.0.1; không đồng nhất hai môi trường.
- Chưa có menu, chính sách thật, database sản phẩm; chưa xác định RAM/GPU/model.

## Đã tạo trong giai đoạn 1

- `main.py`, `app/__init__.py`, `app/config.py`: in trạng thái, cấu hình tối thiểu
  và kiểm tra hai mode; chưa chatbot/gọi model.
- `.gitignore`, `.env.example`, hai file requirements và README hướng dẫn Windows/VS Code.
- `data/README.md`, thư mục `tests/` trống.
- Đặc tả, quyết định, hợp đồng, hướng dẫn tích hợp dữ liệu, bước tiếp theo và
  `docs/learning/stage_01.md`.
- Mặc định nguồn `empty`, chat `rule`; model chưa chọn. `mock`/`ollama` hiện chỉ
  là giá trị cấu hình, không phải chức năng đã triển khai.

## Kiểm tra thực tế giai đoạn 1 — lịch sử

| Kiểm tra | Kết quả |
| --- | --- |
| Tạo `.venv` bằng `py -3.12 -m venv .venv` | Thành công; Python 3.12.10, pip 25.0.1. |
| `.\.venv\Scripts\python.exe main.py` | Mã thoát 0; in đúng 5 dòng, nguồn empty, chat rule, thiếu menu/chính sách. |
| Cài `requirements.txt` và `requirements-dev.txt` với `--no-index` | Cả hai mã thoát 0; không cài gói bên ngoài hoặc dùng kho gói trực tuyến. |
| `.\.venv\Scripts\python.exe -m pip check` | Mã thoát 0, `No broken requirements found.` |
| `.\.venv\Scripts\python.exe -m compileall -q main.py app` | Mã thoát 0; cú pháp hợp lệ. |
| Bộ kiểm tra cấu hình/chạy/import bằng subprocess | **13/13 đạt**; không dùng pytest. |
| `pip list --format=freeze` trong `.venv` | Chỉ có `pip==25.0.1`; không có thư viện AI. |
| Rà soát file và tài liệu cuối giai đoạn | 16 file bắt buộc có nội dung, đọc được UTF-8; bài học đủ 12 mục; 8 link nội bộ hợp lệ; đúng 3 file Python của ứng dụng. |

13 lượt gồm môi trường/Python, bốn mặc định, bốn tổ hợp mode, chuẩn hóa chữ
hoa/khoảng trắng, bốn trường hợp mode sai/rỗng, URL/model từ môi trường và
import không in thông báo. Các biến cấu hình của từng lượt chỉ đặt trong tiến
trình con, không lưu thành cấu hình model thật.

Bộ kiểm tra lần đầu dừng ở tình huống empty/rule vì PowerShell 5.1 dùng ASCII
khi truyền script tiếng Việt qua pipe. Chẩn đoán xác nhận `main.py` vẫn mã thoát
0 và đủ 5 dòng. Sau khi đổi pipe sang UTF-8, bộ kiểm tra đạt 13/13. Đây là lỗi
mã hóa của lệnh kiểm tra, không phải thay đổi code để bỏ qua kết quả lỗi.

**Nghiệm thu nền tảng đạt:** chương trình chạy trong `.venv`, có tài liệu Windows,
bài học và các file theo dõi. Không tạo database, gọi Ollama hoặc tải model.

## Kiểm tra trước giai đoạn 2

- Đã đọc các file theo dõi, README và code; không có AGENTS.md tại root/ancestor
  hoặc trong source. Giai đoạn 1 chạy lại trong `.venv`: Python 3.12.10, mã thoát 0.
- Đã tận dụng `main()`, `app/config.py`, requirements, `.venv` và cấu trúc tài liệu.
- Hợp đồng in 5 dòng và trạng thái “chưa có repository” thuộc giai đoạn 1;
  cập nhật tài liệu hiện tại cho chatbot terminal, giữ bài học stage_01 làm lịch sử.

## Đã hoàn thành giai đoạn 2

- Product/Variant và schema trạng thái bằng TypedDict; kiểm tra dữ liệu mock tại biên nguồn.
- Protocol ba phương thức; hai repository empty/mock, factory chọn nguồn bên ngoài chatbot.
- `data/mock_catalog.json`: 5 mẫu, ID ổn định, nhãn mock; mẫu unknown dùng null/unknown.
- Chuẩn hóa giữ nguyên văn gốc; nhiều intent; tên/alias từ nguồn; ngân sách, vị,
  số người, số lượng, size; hỏi lại khi liên kết không chắc.
- Chatbot terminal, nhu cầu trong RAM; empty không bịa sản phẩm, mock nêu nhãn;
  phân biệt thiếu nguồn/no_results/success/error; policy thiếu và order chỉ ghi nhận.
- Lệnh mới/reset, thoát/exit/quit, EOF/Ctrl+C; ollama chưa triển khai được thông báo rõ.
- Ba file test pytest; cập nhật toàn bộ tài liệu theo dõi/README, bài học stage_02.

## Kiểm thử thực tế giai đoạn 2

| Kiểm tra | Kết quả |
| --- | --- |
| `python -m pytest -q` trong `.venv` | **63 passed in 0.52s**, mã thoát 0. |
| CLI subprocess cho empty/mock | Cả hai mã thoát 0; câu hỏi, reset và thoát đúng; nằm trong 63 test. |
| `socola dưới 300k` trong mock | Chỉ biến thể 16 cm, 250.000 đ; không trả giá 350.000 đ. |
| `giá và size bánh socola` | Trả cả 16/20 cm, 250.000/350.000 đ từ mẫu. |
| Source rỗng, no_results, lỗi file/exception, schema sai, unknown, đa ý định/liên kết | Đạt trong các test contract/NLU/chatbot. |
| Nguồn thêm tên/alias mới bằng fixture test | NLU nhận diện mà không sửa logic; nhãn vị chuẩn lấy từ nguồn. |
| `compileall -q main.py app tests` | Mã thoát 0, không lỗi cú pháp. |
| `pip check` | Mã thoát 0, `No broken requirements found.` |
| Rà soát cuối giai đoạn 2 | 20 file mục tiêu có nội dung UTF-8, bài học đủ 12 mục, 9 link nội bộ hợp lệ, 5 mẫu có nhãn; NLU/chatbot không đọc JSON hoặc phụ thuộc hai repository cụ thể. |

Lần chạy test đầu đạt 60/60. Rà soát bổ sung hai regression (giữ flavor nguồn,
không trả giá bánh cho câu hỏi giá giao hàng); sau đó thêm kiểm tra main giữ
nguyên đầu vào cho NLU; kết quả cuối **63/63**.
Regression là kiểm tra ngăn lỗi cũ quay lại khi sửa code.

Lệnh cài pytest đầu bị sandbox chặn mạng với WinError 10013. Lệnh cài cùng
gói sau được cấp quyền mạng và thành công: pytest 8.4.2, colorama 0.4.6,
iniconfig 2.3.0, packaging 26.3, pluggy 1.6.0, Pygments 2.21.0. pip trong môi
trường vẫn 25.0.1. Không cài thư viện AI, tải model hoặc đăng ký dịch vụ.

## Kiểm tra trước giai đoạn 3

- Đã đọc tài liệu theo dõi, README/code và kiểm tra AGENTS.md root/ancestor/source;
  không tìm thấy AGENTS.md, không ghi đè file này.
- Chạy lại stage 2: **63 passed in 0.60s** bằng Python 3.12.10 trong .venv.
- Ollama local GET /api/tags hoạt động, có đúng `qwen3.5:4b`, file model
  3.389.983.735 byte, Q4_K_M; không tải model mới.
- Pydantic chưa có. Cài pydantic 2.11.9 và dependency nhỏ trong .venv sau khi
  lệnh mạng sandbox thất bại; lệnh được cấp quyền mạng cài thành công. Không cài AI nặng.
- nvidia-smi đọc GPU RTX 2050, 4096 MiB VRAM. Đọc RAM bằng CIM bị Access denied;
  chưa xác định RAM, không suy máy đủ mạnh từ dung lượng GPU.

## Đã triển khai giai đoạn 3

- Client HTTP local urllib, chọn đúng tên từ tags, timeout/status/error, không tải model.
- LLMNLU/LLMOpening Pydantic strict; NLU JSON sai sửa tối đa 1 lần, transport không retry.
- Kiểm tra nghĩa cơ bản sau schema; ID chỉ từ nguồn, mention sai/copy từ lịch sử
  hoặc số trái rule bị từ chối; fallback có mã lỗi và giữ nguồn empty/mock.
- Conversation có ID/history/needs riêng, trả bản sao, giới hạn 6 lượt mặc định;
  nhu cầu cấu trúc giữ riêng, reset xóa cả history/needs.
- Qwen chọn lời mở đầu có giới hạn; code trình bày nghiệp vụ. Lỗi nguồn luôn
  error, không thêm câu thành công và không ghi đè nhu cầu khi truy vấn cuối lỗi.
- Main chạy rule/ollama, in engine/model/attempts/phrasing để phân biệt fallback.
- Thêm hai file test, cập nhật test CLI stage 2 cho controller mới; không đổi
  Product/Variant hoặc interface repository. Tài liệu/README/bài stage_03 cập nhật.

## Kiểm thử giai đoạn 3: giả lập và gọi thật là hai loại khác nhau

| Kiểm tra | Kết quả thực tế |
| --- | --- |
| pytest sau thay đổi kiểm tra nghĩa | **120 passed in 1.63s**, mã thoát 0; không gọi model thật. |
| Hai nguồn, câu nối tiếp 400k, lịch sử riêng/giới hạn/reset | Đạt trong test hội thoại với rule/LLM giả lập. |
| JSON sai, strict type, ID/giá/tồn kho ngoài schema, sửa tối đa 1 lần | Đạt trong test client, không dùng JSON thô cho nghiệp vụ. |
| Timeout, connection_error, HTTP 404/503, model thiếu, cloud/remote, HTTP JSON lỗi | Đạt bằng giả lập; fallback nêu mã và giữ catalog. |
| Repository lỗi ban đầu/sau NLU, lỗi capabilities | Đạt; không thành no_results/success, không lộ exception. |
| Model tự thêm/copy mention, số mâu thuẫn, thuộc tính không có ở lượt hiện tại | Đạt; đề xuất bị từ chối, rule dùng câu hiện tại. |
| pip check | Mã thoát 0, No broken requirements found. |
| compileall bản cuối main/app/tests | Mã thoát 0, không lỗi cú pháp. |
| Rà soát tài liệu/ràng buộc | 10 file docs/config hiện tại có nội dung UTF-8; stage_03 đủ 12 mục; 14 link nội bộ hợp lệ; NLU/chatbot/conversation không đọc file hoặc import nguồn cụ thể. |
| GET tags thật / model hiện có | Thành công, chọn qwen3.5:4b, không tải. |
| Ba lượt HTTP chat đầu với timeout 30s | Cả ba timeout, rule_fallback; empty vẫn giữ vị/6 người và tăng 300k→400k, mock giá/size đúng mẫu. |
| Trích xuất riêng với timeout 60s, phiên bản thử ban đầu | JSON validate được sau 18.00s; lời mở đầu trả sau 4.42s. Cờ hỏi lại sai được phát hiện và chuyển sang code tính ở bản cuối. |

Thử thật sau đó phát hiện model copy mention cũ và chọn lời mở đầu hỏi lại sai.
Đã thêm kiểm tra nghĩa/fallback và lọc enum; kết quả bản cuối ở bảng dưới.
Số test không là độ đúng NLU/LLM tổng thể.
Timeout đo là mỗi HTTP, thời gian toàn lượt còn có nhiều request/chọn model.

### Gọi thật bản cuối, timeout 60s, qwen3.5:4b

| Lượt | Kết quả thực tế | Thời gian toàn lượt |
| --- | --- | --- |
| Empty: bánh socola/6 người/dưới 300k | engine=ollama, NLU 1 lần, phrasing=success; ghi đủ nhu cầu, unconfigured, products=[], nói thiếu menu. | 33.20s |
| Cùng phiên: tăng ngân sách 400k | engine=rule_fallback, invalid_nlu_mentions; model copy cụm bánh cũ. Code từ chối, rule tăng 400k, giữ socola/6 người và thiếu menu. | 11.08s |
| Mock: giá và size bánh socola | engine=ollama, NLU 1 lần, phrasing=success; hai size/giá từ nguồn, nhãn mock. | 16.34s |

Script kiểm tra hành vi thật có assert, **3/3 đạt**, mã thoát 0. Không gọi cả
ba là LLM thành công: lượt cập nhật dùng rule. Chưa bảo đảm ổn định/độ đúng
tổng quát hoặc tốc độ ở lượt khác; không biết chắc nguyên nhân timeout ban đầu.

CLI `main.py` cũng đã chạy thật với tên cố ý không có
`qwen-stage3-not-installed`: GET tags, báo model_not_found và rule_fallback,
NLU attempts=0. Hai câu nhu cầu/400k vẫn đúng, thoát mã 0; không POST để tải
hoặc gọi model thiếu. Đây là kiểm tra lỗi model thiếu trên dịch vụ local thật,
khác các test HTTP giả lập trong pytest.

## Kiểm tra trước giai đoạn 4

- Đọc AGENTS.md nếu có và tài liệu/code thực tế: không tìm thấy AGENTS.md ở
  root/ancestor/source; không ghi đè. Nền giai đoạn 3 chạy lại **120 passed in 1.58s**.
- Python 3.12.10/.venv, Pydantic/pytest có sẵn; không cài thêm dependency.
- next_steps cũ đề xuất API, nhưng người dùng yêu cầu RAG: cập nhật phạm vi theo
  yêu cầu, giữ API/SQLite/UI/đơn cho giai đoạn sau.
- Vấn đề tên bánh cũ/greeting mà người dùng báo mới được chẩn đoán trước khi
  chuyển stage 4, chưa sửa; không coi đó là phần đã hoàn thành.

## Đã hoàn thành giai đoạn 4

- 5 điều khoản JSON giả lập, ID/phiên bản/nhãn rõ; nguồn kiến thức empty/sample
  riêng với catalog. Empty không mở tài liệu mẫu; lỗi schema/file vẫn là error.
- Loader qua KnowledgeRepository Protocol; retrieve không biết file JSON/path.
- Một điều khoản một chunk, từ khóa/IDF/tiêu đề x2, mặc định <=3 chunk; index RAM
  dựng lại mỗi lần, keyword-v1 + corpus SHA-256. Không cần build_index.py.
- Qwen nhận chunk dạng user JSON, chọn trích đoạn nguyên văn; Pydantic strict,
  kiểm tra ID trong các đoạn đã gửi/quote có trong content. Sửa JSON tối đa 1 lần.
- Rule/fallback trình bày đoạn thực từ nguồn; nhãn MÔ PHỎNG/ID/version; lỗi nguồn
  không thành câu trả lời thành công. Không tạo đơn, suy giá/tồn kho/allergen.
- Controller/main có routing policy, response.policy và chẩn đoán RAG riêng;
  phí policy không ghi đè ngân sách/vị/số người của nhu cầu bánh.
- Bộ 27 câu development, script đo retrieval và script smoke Qwen thật; báo cáo
  đã ghi trong evaluation/. Test retrieval/RAG/CLI, bài học stage_04 và tracking/README.

## Kiểm thử thực tế giai đoạn 4

| Kiểm tra | Kết quả |
| --- | --- |
| Pytest bản cuối | **170 passed in 2.60s**, mã thoát 0; HTTP/model giả lập, không gọi Qwen thật. |
| Empty/sample, catalog empty/mock, giới hạn 3 nguồn, thay nội dung/version | Đạt trong pytest; có CLI subprocess rule cả hai nguồn kiến thức. |
| Rà soát controller trên 21 câu policy development | Sau bổ sung NLU: empty **21/21** trả unconfigured; sample **21/21** route policy và chứa gold nguồn; rule, không gọi model. Không là đánh giá nghĩa câu trả lời. |
| JSON sai sửa <=1, source ngoài top chunk, quote bịa, injection/field tạo đơn | Đạt bằng giả lập; schema/code từ chối, không thực thi lệnh trong tài liệu. Không chứng minh model luôn chống injection. |
| Timeout, lỗi nguồn, thiếu context, model unsupported | Đạt bằng giả lập; nguồn lỗi không thành success; thiếu context không gọi model. Model thiếu/HTTP status có test client giai đoạn 3 vẫn đạt. |
| Đo `python -m scripts.evaluate_retrieval` | Mã 0, **27 câu đã chạy thật qua retriever**; không gọi model; keyword-v1/top_k=3/min_score=0,15. |
| compileall main/app/scripts/tests | Mã 0, không lỗi cú pháp. |
| pip check | Mã 0, No broken requirements found. Không cài thêm thư viện/model. |
| Rà soát tài liệu và báo cáo | 9 file tài liệu UTF-8 có nội dung, 25 link local hợp lệ; stage_04 đủ 12 mục; corpus/dataset SHA-256 trong báo cáo khớp file hiện tại. |

Lần pytest đầu sau thêm test: **157 đạt, 2 lỗi**. Câu “xyz không liên quan” và
“tái sử dụng hộp” khớp nhầm từ đơn quan/dung sau bỏ dấu. Sửa cách tách từ yếu
thành cặp âm tiết (bảo_quản/áp_dụng/sử_dụng), giữ nguyên yêu cầu test; chạy lại
159/159 đạt. Chưa đánh giá tách từ/ngữ nghĩa tổng quát.

Rà soát thêm các câu development qua controller (khác đo retriever trực tiếp):
5/21 câu policy trong empty và 3/21 trong sample chưa route policy, ví dụ
“phí vận chuyển”, “ngăn mát/ngăn đá”. Bổ sung cụm từ nhận diện nghiệp vụ chung
trong NLU, không chèn source ID/nội dung/giá trị chính sách vào logic. Thêm
10 regression cho hai mode giữ needs và 1 test mixed catalog/policy, kết quả
bản cuối **170/170 đạt**. Thuật toán retrieval không đổi sau lần đo 27 câu.

### Kết quả retrieval development đã đo

Corpus 5 điều khoản sample; 21 câu có đáp án, 6 câu không có đáp án. File
evaluation/retrieval_report.json có hash corpus/dataset, thời gian và nguồn từng câu.

| Chỉ số | Kết quả thực tế |
| --- | --- |
| Recall@3 trung bình trên 21 câu có đáp án | 1,0 (100%). |
| Hit@1 | 20/21 = 0,952381. |
| MRR@3 | 0,97619. |
| Từ chối truy xuất đúng trên câu không có đáp án | 3/6 = 50%. |
| Đúng toàn bộ tập nguồn | 10/27 = 37,037%. |
| Thời gian retrieval trung bình, gồm đọc JSON/index | 0,680889 ms trong lần đo; không gồm LLM, không phải benchmark tải. |

False positive: câu giá bánh (gia/giả bị bỏ dấu), giờ mở cửa, giao quốc tế vẫn
khớp từ trong tài liệu. Câu “Bánh dùng trong bao lâu sau khi nhận?” lấy đúng
nguồn ở vị trí 2. Nhiều câu lấy thêm đoạn không liên quan. Đây là development
dùng phát triển, **không phải held-out hoặc độ đúng RAG/chatbot**. Chưa đặt
ngưỡng nghiệm thu chất lượng tổng thể hoặc đánh giá nghĩa tất cả câu model.

### Qwen thật giai đoạn 4, tách khỏi pytest

GET /api/tags chọn đúng qwen3.5:4b đã cài; không tải. Chạy
`python -m scripts.check_rag`, timeout mỗi HTTP 60s, mã thoát 0:

| Câu/nguồn | Kết quả thực tế | Thời gian toàn lượt |
| --- | --- | --- |
| Empty: chính sách giao hàng | unconfigured, engine=not_used, 0 lần sinh, source_ids=[]; nói thiếu tài liệu. | 0,01s |
| Sample: phí giao hàng mô phỏng | ollama, 1 lần, answered; quote nguyên văn 25.000 đồng, source_id=sample-policy-001, nhãn mô phỏng. | 25,82s |
| Sample: giao hàng quốc tế | Retriever có đoạn khớp; Qwen trả supported=false, insufficient, source_ids=[]; không khẳng định có giao quốc tế. | 5,74s |

**3/3 kiểm tra hành vi đạt**, nhưng chỉ **2 lượt có sinh Qwen thật**, không gọi
empty là model thành công. evaluation/rag_smoke_report.json giữ output, error,
hash và thời gian. Chưa chứng minh ổn định/độ đúng model trên 27 câu, dưới tải,
với mọi nội dung gây injection hoặc câu hỏi nhiều ý.

## Kiểm tra trước giai đoạn 5

- Đọc tài liệu theo dõi/code, tìm AGENTS.md root/ancestor/source không có;
  không ghi đè AGENTS.md. Python .venv 3.12.10; nền stage 4 **170 passed in 2.19s**.
- Có SQLite 3.49.1 trong thư viện chuẩn. ZoneInfo Asia/Ho_Chi_Minh ban đầu
  lỗi ZoneInfoNotFoundError vì Windows thiếu IANA/tzdata.
- Cài tzdata==2026.4 vào .venv (wheel 347 kB). Lệnh trong sandbox báo không
  tìm được distribution; cùng lệnh được cấp quyền mạng cài thành công. Không
  cài AI nặng hoặc tải Qwen/embedding.
- Thay đề xuất API bằng phạm vi stage 5 người dùng yêu cầu: FSM/đơn demo,
  không xây database sản phẩm, API web hoặc UI.

## Đã hoàn thành giai đoạn 5

- order_flow/order_service/handoff/storage: FSM/slot, bốn tool qua interface,
  REVIEW revision/hash, kiểm tra lại source, lưu yêu cầu/demo/ticket.
- Metadata mock riêng; size/topping/chữ/lead/stock/giá từ nguồn. Unknown luôn
  cần xác minh; không đặt giới hạn nghiệp vụ giả rồi gọi chính sách thật.
- Empty ghi nhận nhu cầu, REVIEW không quote thật, gửi waiting_consultation
  confirmed=false + ticket pending. Mock đủ điều kiện mới demo_order/confirmed=true,
  nhãn DEMO và total nguồn; retry trả cùng ID.
- Lệnh sửa trước gửi bỏ REVIEW; sửa/hủy demo đã xác nhận chuyển HANDOFF. Ticket
  có lý do/summary và không nói nhân viên đã nhận.
- SQLite chatbot 4 bảng, schema v1/foreign key/unique key/hash, SQL tham số,
  transaction rollback, phiên/history/needs/order/counter riêng. Nạp lại từ file.
- Terminal tích hợp, lệnh tiếp tục ID local; contact chỉ DEMO/TEST, không lưu
  đầu vào contact thô; lệnh FSM không gọi LLM.
- Thêm test_order_flow/test_storage, cập nhật requirements/config/README/toàn
  tracking và bài học stage_05. Giữ Product/Variant và interface catalog ba method.

## Kết quả kiểm thử thực tế giai đoạn 5

| Kiểm tra | Kết quả |
| --- | --- |
| Nền 170 test sau tích hợp | 170 passed in 2.40s, không làm hỏng code giai đoạn trước. |
| Bộ mới lần đầu | 221 passed in 3.70s. |
| Bản cuối sau guard FSM/capability/slot data và test bổ sung | **231 passed in 4.10s**, exit 0, 61 test mới; không gọi Qwen thật. |
| Hai CLI full-flow empty/mock | Subprocess main.py + SQLite file tạm thật, exit 0; empty yêu cầu/ticket, mock demo total 500.000 đ; hai xác nhận chỉ một submission. Nằm trong pytest. |
| Persistence/phiên riêng/SQL/owner/rollback | Đạt trên SQLite thật; đóng/mở lại file nạp được phiên; không có bảng sản phẩm. |
| FSM/quantity/ngày giờ/metadata/unknown/source đổi/tamper REVIEW | Đạt; chưa được xác nhận khi thiếu hoặc nguồn lỗi/thay đổi. |
| Handoff/2 fallback liên tiếp/đơn đã xác nhận/ticket retry | Đạt; ticket pending, cùng lý do không thêm ticket thứ hai. |
| Slot ở CHAT_MODE=ollama | Client bị monkeypatch để fail nếu gọi: các lệnh vẫn chạy, không gửi slot/contact vào LLM. Đây là test bypass, không gọi model thật. |
| compileall main/app/scripts/tests | Không báo lỗi cú pháp. |
| pip check | No broken requirements found. |
| Rà soát tài liệu/timezone/schema | 9 file tài liệu UTF-8, 21 link local hợp lệ, stage_05 đủ 12 mục; ZoneInfo đã có, schema v1 đúng 4 bảng chatbot. |

Sau lượt 227 test, thêm regression: chữ/contact có từ “nhân viên” là dữ liệu
slot, không kích hoạt ticket; dị ứng nghiêm trọng ở nhu cầu vẫn handoff; hỏi
chính sách đổi trả sau demo không bị hiểu thành sửa đơn. Kết quả cuối 231 đạt.

Không gọi Qwen thật mới ở stage 5: các hành động nghiệp vụ do code chạy;
HTTP/LLM regression giai đoạn 3–4 vẫn dùng giả lập. Các báo cáo model/retrieval
stage 4 giữ nguyên, không coi là đo lại chất lượng stage 5. Chưa test UI nhập
bàn phím/VS Code hoặc đọc/ghi đồng thời nhiều tiến trình. DB runtime sinh khi
chạy thử CLI cũ; không thuộc mã nguồn, không có dữ liệu cá nhân thật.

## Kiểm tra trước giai đoạn 6

- Đọc code thực tế, sáu file theo dõi/README; không có AGENTS.md để áp dụng.
- Nền Python 3.12.10/.venv, **231 passed in 3.92s**. FastAPI/Uvicorn/HTTPX
  chưa cài; tận dụng Pydantic/tzdata/pytest và toàn bộ logic stage 2–5.
- Không có database sản phẩm/menu/chính sách thật; giữ empty/mock và empty/sample.
- Nhận thấy docstring create_state vẫn nói không lưu file trong khi controller
  đã lưu SQLite: sửa docstring cho đúng, không đổi thuật toán.

## Đã triển khai giai đoạn 6

- app/api.py: health/tạo phiên/chat/đọc request-demo của owner, schema Pydantic
  request/response, lỗi sạch và message 1–2000 ký tự; bọc handle_message cũ.
- Token random 32 byte, RAM server giữ hash/owner/expiry/lock, TTL 8 giờ,
  capacity 200 phiên. UUID không xác thực; UI giữ RAM, restart/reload phiên mới.
- def routes chạy threadpool, connection trong thread, lock từng phiên;
  thêm load_order_request có cả owner+ID ở storage, schema SQLite v1 không đổi.
- static HTML/CSS/JS cùng origin: chat/status/errors, thẻ từ products, sources,
  nhãn nguồn, REVIEW/verification trước gửi, nút phiên mới, textContent.
- Empty lưu waiting_consultation, confirmed=false; mock đủ nguồn mới demo_order
  confirmed=true có nhãn. Source unavailable không có nút gửi; service vẫn recheck.
- Thêm tests/test_api.py, dependency nhỏ và bài học stage_06 đủ 12 mục;
  cập nhật README/spec/contracts/decisions/data_integration/next_steps.
- Không tải model, cài AI nặng, deploy, thêm adapter thật hoặc làm giai đoạn sau.

## Kết quả thực tế giai đoạn 6

| Kiểm tra | Kết quả |
| --- | --- |
| Suite cuối | **262 passed, 1 warning in 6.60s**, exit 0; 31 API test mới. |
| Hai mode/nguồn/REVIEW/idempotency/owner | TestClient HTTP in-process, SQLite file tạm thật; empty/mock, source IDs/sample label, unknown giá null, request khác demo. |
| Session | Token khác ID và giữa khách; thiếu/UUID/sai/expired/restart 401; ID khách khác 404; history/needs riêng. |
| Validation/lỗi | Input 422 không echo input; response 500 không lộ payload; DB 503; catalog search/capability và knowledge error giữ lỗi; Ollama timeout/notfound/connection giả lập fallback rõ. |
| Concurrency | Hai edit cùng phiên không mất slot; controller chờ giả lập, health vẫn đáp ứng trong cùng event loop. Chưa nhiều process/worker. |
| HTTP Uvicorn thật empty/empty/rule, cổng 8765 | /health + HTML/CSS/JS 200; câu thử 0 products/0 sources; REVIEW lưu waiting_consultation/confirmed=false; retry cùng ID, token B GET A=404. |
| HTTP Uvicorn thật mock/sample/rule, cổng 8766 | Câu thử 1 product/1 source; REVIEW tạo demo_order/confirmed=true/500.000 đ, retry cùng ID, B GET A=404; no-store API. |
| pip check | No broken requirements found. FastAPI 0.142.2/Starlette 1.7.0/Uvicorn 0.53.0/HTTPX 0.28.1 đã cài vào .venv. |
| compileall | Không lỗi cú pháp Python. |
| JavaScript | Parser V8 chấp nhận chat.js; không thực thi DOM. Node không có PATH, không chạy node --check. |
| Browser tool | iab không khả dụng; listBrowsers trả []; **chưa kiểm tra UI trình duyệt**. |
| Rà soát tài liệu cuối | 8 tài liệu UTF-8, 19 link nội bộ hợp lệ; stage_06 đủ 12 mục, 5 file yêu cầu có nội dung. |

Test API đầu 1 assertion sai đường dẫn needs.filters; sửa test khớp schema
đã có, không thay nghiệp vụ. Starlette cảnh báo HTTPX TestClient deprecated,
đề nghị HTTPX2; một warning được ghi rõ, không ẩn hoặc coi là test thất bại.
HTTP smoke lần kiểm tra header đầu đọc key sai case; đổi script kiểm tra
header case-insensitive rồi smoke đạt; middleware no-store không có lỗi đó.

HTTP model trong pytest là giả lập; các server smoke dùng rule. **Không gọi
Qwen thật mới ở stage 6**, không đo lại retrieval hoặc chất lượng chatbot;
báo cáo stage 3–4 vẫn là lịch sử. UI CSS/DOM/Enter/lỗi/bố cục hai mode cần
người dùng thử theo README/stage_06. Chưa hoàn tất nghiệm thu qua trình duyệt.

## Bổ sung theo yêu cầu AI mặc định và đặt bánh tự nhiên

Người dùng chọn Qwen hiểu slot câu tự nhiên, code vẫn kiểm tra/xác nhận.
Đã đọc lại tracking/code, không có AGENTS.md; API8000 của người dùng đã ở
mode ollama, engine rule trong lệnh đặt thuần là do FSM bypass có chủ ý.

- CHAT_MODE default ollama, timeout config60; .env.example/README/contracts
  đã cập nhật. run_web.py đặt ollama trước import app, ghi đè rule còn sót,
  không tự tải model hoặc đổi nguồn/model/DB đã cấu hình.
- LLMOrderSlots/extract_order_slots và order_nlu: grounding/type/JSON repair
  một lần, nhiều slot hoặc từ chối phần AI khi không rõ/không có căn cứ.
- Conversation xử lý slot rồi lưu qua flow cũ, không transaction khi chờ
  model. ID vẫn từ nguồn; không tự REVIEW/submit. Sửa cần review mới, sau
  confirmed chuyển ticket. Hai no_order_slots liên tiếp đi HANDOFF đúng phiên.
- Bot hỏi từng trường còn thiếu; UI có mode AI/rule và ví dụ tự nhiên. Lệnh
  thuần/field:value vẫn engine rule chính xác, code giữ kiểm soát nghiệp vụ.
- Guard contact không nhãn giả không gửi model/không lưu raw; quote sau ghi
  chữ là dữ liệu. Không coi grounding/guard là hiểu ngữ nghĩa/PII hoàn chỉnh.
- Bài học stage_06 và cả sáu tracking cập nhật; không triển khai stage7.

| Kiểm tra bổ sung | Kết quả thực tế |
| --- | --- |
| Suite sau bổ sung | **287 passed, 1 warning in 9.75s**, exit 0; 25 order NLU test mới, không gọi model thật trong pytest. |
| Empty Qwen thật qua TestClient + HTTP Ollama | Default ollama; lần đầu http_error sau28,59s; thử nhỏ HTTP200/OK21,80s; thử lại câu đầy đủ thành công26,28s, engine ollama, attempts1; REVIEW unverified/quote=null. |
| Launcher Python/Uvicorn + HTTP Qwen/mock thật | Cố ý env CHAT_MODE=rule trước chạy, /health trả ollama/mock. Full-flow44,59s, engine ollama/errors=[], REVIEW tổng500.000đ; xác nhận mới có demo_order_id, request_id=null. |
| PowerShell launcher thử đầu | .ps1 bị execution policy chặn, không có server8767 nên smoke kết nối bị từ chối. Đã bỏ file .ps1 mới tạo, dùng Python launcher hoạt động; không sửa execution policy. |
| Safety/grounding tests | JSON invalid tối đa2 call, field bịa/mơ hồ/ngày tương đối từ chối, no auto-confirm, review bị bỏ khi sửa/lỗi, contact guard, context không contact cũ, source lỗi skip model, chữ không kích hoạt staff và confirmed edit handoff. |
| compileall/pip check | Không lỗi Python; No broken requirements found. |

Thử thật dùng đúng model qwen3.5:4b đã cài, không tải model. Chỉ vài câu, không
đánh giá độ ổn định/tải/NLP tổng thể; ghi lỗi HTTP đầu tiên, không che lỗi.
Lần empty thành công dùng timeout30 trước khi tăng mặc định60; lần mock HTTP
dùng launcher/cấu hình60. Server8000 của người dùng không bị tắt/restart;
cần Ctrl+C/chạy lại/reload/phiên mới để nạp code mới. UI vẫn cần thử thủ công.

## Chưa làm hoặc chưa kiểm tra hiện tại

- Chưa có menu/chính sách thật hoặc adapter nguồn thật; policy empty/sample đã có.
- Chưa có adapter nguồn JSON thật/database/API bên ngoài; mock JSON chỉ là fixture.
- RAM chưa xác minh; chưa benchmark hoặc đánh giá độ ổn định Qwen trên tập rộng.
- Đã có demo một dòng/total/SQLite và API/UI local với token/owner. Chưa giỏ
  nhiều dòng, giữ/trừ tồn kho, đăng nhập tài khoản, nhiều worker hoặc đơn thật.
- Chưa hiểu ngôn ngữ tự do cho mọi slot; dùng lệnh field:value. Handoff regex
  chưa xử lý mọi phủ định/liên kết; chưa đánh giá tổng thể hoặc kiểm thử nhiều tiến trình.
- Embedding CPU/vector/cosine/index đĩa chưa tải/triển khai/chạy; có bước chuẩn
  bị trong stage_04. RAM chưa xác minh, chưa chọn revision/model embedding cuối cùng.
- Chưa sửa lỗi generic browse giữ tên bánh cũ/greeting nhắc lại nhu cầu cũ;
  gõ mới/reset để thử phiên mới. Chưa xử lý tham chiếu chủ đề policy từ lịch sử.
- Chưa đánh giá chất lượng NLP tổng thể trên bộ câu hỏi độc lập. Test xác nhận
  các hành vi trong phạm vi đã triển khai, không thay thế bộ đánh giá chatbot.
- Chưa thao tác chọn interpreter/kích hoạt trong UI VS Code, kiểm tra Ctrl+C
  bằng bàn phím thật hoặc Git ignore trong repository. Chưa khởi tạo Git.
- Chưa thử UI trực tiếp vì không có browser kết nối; không gọi HTTP/parser
  tests là browser test. UI có nhãn/bảng REVIEW trong code, cần thao tác thực.
- Session/lock ở RAM một worker; chưa resume web bằng token bền, tài khoản,
  multi-worker/rate limit/HTTPS hoặc triển khai Internet. Registry hết hạn/
  restart cần phiên mới, bản ghi SQLite cũ vẫn giữ.
