# Sửa PermissionError khi chạy pytest trên Windows

Cập nhật 05/10/2026. Đây là sửa môi trường kiểm thử, không phải giai đoạn mới.
Không sửa logic chatbot, Qwen, database demo hoặc quyền Windows.

## Nguyên nhân từ traceback

Lỗi xảy ra trong `_pytest/tmpdir.py`, ở `tmp_path` → `getbasetemp()` →
`make_numbered_dir_with_cleanup()`, khi pytest duyệt thư mục tạm bên dưới
AppData/Local/Temp. `PermissionError: [WinError 5]` nghĩa là thao tác truy
cập bị từ chối. Chưa xác định được ACL, tiến trình hoặc cấu hình nào gây
chặn trên terminal của người dùng; không khẳng định do antivirus hay SQLite.

**Fixture** là hàm chuẩn bị dữ liệu/môi trường cho test. Fixture chung
`block_real_ollama` trong tests/conftest.py dùng `tmp_path` để tách database
test khỏi database đang demo. Vì fixture này chạy cho mọi test, một lỗi tạo
thư mục gây rất nhiều **ERROR ở setup**. Các assertion kiểm tra ngữ cảnh chưa
chạy; khác **FAILED**, là khi assertion đã chạy nhưng kết quả không đúng.

Trước sửa, trong phiên công cụ vẫn chạy được 21 test. Điều đó không phủ nhận
traceback người dùng: quyền/môi trường terminal khác có thể cho kết quả khác.

## Thay đổi nhỏ trong project

- [tests/conftest.py](../../tests/conftest.py): thêm `pytest_configure()`
  với `@pytest.hookimpl(tryfirst=True)`, chạy trước bước tạo factory thư mục
  tạm của pytest. Nếu người chạy chưa đặt `--basetemp`, chọn đường dẫn tuyệt
  đối `.pytest_tmp/run-<UUID>` từ vị trí file conftest, không từ username hay
  đường dẫn hardcode trên máy. Không thay các fixture fake model/DB riêng.
- [.gitignore](../../.gitignore): bỏ qua `.pytest_tmp/`, là dữ liệu sinh khi
  test, không là mã nguồn.
- README, progress, decisions, contracts, next_steps và bài sửa context:
  cập nhật cách chạy/kết quả và liên kết giải thích này.

**Hook** là hàm pytest gọi tại một thời điểm trong vòng đời chạy test.
`tryfirst=True` yêu cầu chạy hook sớm. **UUID** ở đây chỉ để đặt tên thư mục
riêng mỗi lần chạy, không phải token xác thực. `pathlib.Path` xử lý đường
dẫn Windows có dấu hoặc khoảng trắng.

Luồng mới:

```text
python -m pytest
→ nạp tests/conftest.py
→ đặt basetemp mới trong .pytest_tmp
→ tmp_path tạo thư mục riêng từng test
→ tạo database test và fake model
→ chạy assertion
```

Chọn tên mới vì pytest có thể xóa thư mục `--basetemp` trước khi dùng.
Không chọn `.pytest_tmp` gốc, `runtime`, hoặc nơi chứa database demo làm
basetemp. Nếu tự truyền `--basetemp`, lựa chọn đó vẫn có ưu tiên; chỉ truyền
một thư mục riêng dành cho pytest. Tham khảo
[tài liệu chính thức về thư mục tạm](https://docs.pytest.org/en/stable/how-to/tmp_path.html#temporary-directory-location-and-retention).

Không quét/xóa AppData/Temp, không đổi ACL hoặc yêu cầu Administrator.
Các run trong `.pytest_tmp` được giữ để xem lỗi; không tự dọn các run cũ.
Thư mục project vẫn cần quyền ghi bình thường. Tên riêng tránh dùng lại một
run cũ có quyền khác; không chữa được trường hợp cả project bị cấm ghi.

## Lệnh Windows

Mở PowerShell tại root project, chạy lại lệnh cũ:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_context_product_scope.py
# Khi muốn kiểm tra toàn bộ project:
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
```

Không cần Ollama hoặc API đang chạy cho test logic. Không cần restart API
vì lần này chỉ sửa cấu hình kiểm thử. Không dùng reset database để sửa lỗi.

## Kết quả kiểm tra thực tế

| Kiểm tra | Kết quả ngày 05/10/2026 |
| --- | --- |
| Lệnh gốc trước sửa trong phiên công cụ | 21 passed, 0.74s; chưa tái hiện quyền của terminal người dùng |
| Lệnh gốc sau sửa | 21 passed, 0.67s |
| Tự truyền basetemp riêng để kiểm tra quyền ưu tiên | 21 passed, 1.20s; đường dẫn được giữ đúng |
| Toàn suite khi mô phỏng nhánh duyệt Temp bị PermissionError | 356 passed, 1 warning, 10.59s, exit0; đường dẫn nằm trong .pytest_tmp, nhánh duyệt Temp không bị gọi |

Mô phỏng chỉ thay hàm chọn thư mục đánh số của pytest trong tiến trình
kiểm tra; không thay quyền hoặc nội dung thư mục Temp thật. Lần mô phỏng
đầu chặn quá rộng `tempfile.gettempdir`, làm bộ thu stdout/stderr của pytest
lỗi trước khi nạp conftest; đó không phải nhánh trong traceback người dùng.
Đã sửa phép mô phỏng để chặn đúng nhánh tạo thư mục `tmp_path` và chạy toàn
suite đạt. Không dùng kết quả mô phỏng làm bằng chứng terminal người dùng
đã chạy thành công.

Warning Starlette/HTTPX deprecation đã có trước đây, không là lỗi quyền.
Test dùng fake model và database riêng; không gọi Qwen thật trong lần sửa
môi trường này. Không tạo đơn hoặc reset database demo.

## Câu hỏi để tự trình bày

1. Vì sao một lỗi gây hàng loạt ERROR? Fixture chung dùng tmp_path, nên mọi
   test phụ thuộc đều lỗi trong setup.
2. ERROR khác FAILED thế nào? ERROR thường là chuẩn bị/thu dọn test lỗi;
   FAILED là test chạy rồi kết quả không đạt assertion.
3. Vì sao đặt tên run mới? Tránh đụng run trước và tránh pytest dọn nhầm
   thư mục dùng chung khi khởi tạo basetemp.
4. Vì sao không chạy Administrator? Đặt dữ liệu test trong project có
   quyền ghi đủ; không cần tăng quyền cho chương trình hoặc sửa quyền hệ thống.
5. Vì sao pytest pass không chứng minh Qwen luôn đúng? Suite dùng fake để
   kiểm logic; model thật phải thử riêng và có thể hiểu sai ngôn ngữ.
