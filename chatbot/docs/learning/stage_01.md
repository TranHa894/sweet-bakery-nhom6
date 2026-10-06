# Bài học giai đoạn 1: nền tảng dự án

Ngày thực hiện: 02/10/2026. Đọc từ đầu đến cuối rồi tự chạy các ví dụ trên Windows.

Bài này ghi lại code/kết quả tại giai đoạn 1. Code hiện đã phát triển thành
chatbot terminal ở giai đoạn 2; lệnh/đầu ra hiện tại xem README và stage_02.md.

## 1. Mục tiêu và chức năng đã hoàn thành

Bạn có một chương trình Python nhỏ chạy được trong môi trường ảo. Nó đọc cấu
hình, kiểm tra hai mode và in trạng thái. **Mode** là chế độ lựa chọn cách hoạt
động. Mặc định `CATALOG_MODE=empty` và `CHAT_MODE=rule`.

Chưa có menu, chính sách chính thức hoặc database sản phẩm. Chọn `mock` chỉ đổi
trạng thái thông báo; chưa có kho dữ liệu mẫu. Chọn `ollama` chưa gọi mô hình.
Chương trình chưa nhận câu hỏi và chưa tạo đơn hàng.

Phân biệt các nhóm kiến thức:

| Nhóm | Nghĩa và việc học ở giai đoạn này |
| --- | --- |
| Python | Ngôn ngữ lập trình: file, import, hàm, chuỗi, điều kiện, lỗi và môi trường ảo. |
| Backend | Phần xử lý phía máy chủ: hiện chỉ chuẩn bị cấu hình và cách chia module, chưa có API máy chủ. |
| AI/NLP | AI là trí tuệ nhân tạo; NLP là xử lý ngôn ngữ tự nhiên. Chưa có chức năng AI/NLP ở giai đoạn 1. |
| Nghiệp vụ | Quy tắc của cửa hàng: thiếu menu thì không xác nhận có bánh bán; mock chỉ phục vụ học và test. |

## 2. File đã tạo và trách nhiệm

**Folder** là thư mục nhóm các file. **Module Python** thường là một file `.py`
chứa code có thể được dùng từ nơi khác. **Package** nhóm các module theo thư mục;
dự án dùng package thông thường có `__init__.py`.

| File/thư mục | Trách nhiệm |
| --- | --- |
| `main.py` | Điểm chạy; hàm `main()` in trạng thái. |
| `app/__init__.py` | Đánh dấu `app` là package thông thường và mô tả mục đích package. |
| `app/config.py` | Đọc bốn biến môi trường, kiểm tra hai mode. |
| `data/README.md` | Nêu rõ chưa có dữ liệu; folder data không phải database. |
| `tests/` | Nơi đặt test chức năng sau này; hiện trống. |
| `.env.example` | Mẫu tên biến và giá trị mặc định; không chứa bí mật. |
| `.gitignore` | Danh sách file/thư mục Git cần bỏ qua, gồm `.venv` và `.env`. |
| `requirements.txt` | Danh sách dependency chạy; hiện chỉ có chú thích. |
| `requirements-dev.txt` | Tham chiếu danh sách chạy; chưa có dependency phát triển. |
| `README.md` | Hướng dẫn chạy, chọn interpreter, cấu hình và đọc tài liệu. |
| `docs/project_spec.md` | Mục tiêu, phạm vi, trạng thái dữ liệu, Python mục tiêu và lộ trình dự kiến. |
| `docs/progress.md` | Việc đã làm/chưa làm và kết quả kiểm tra thực tế. |
| `docs/decisions.md` | Các quyết định kỹ thuật và lý do. |
| `docs/contracts.md` | Tên công khai, kiểu dữ liệu và quy tắc giữa các phần. |
| `docs/data_integration.md` | Cách bổ sung nguồn thật qua interface sau này. |
| `docs/next_steps.md` | Đề xuất giai đoạn 2 và điều kiện bắt đầu. |
| `docs/learning/stage_01.md` | Bài học này, giúp bạn giải thích và tự sửa code. |

`.venv/` cũng được tạo để chạy thử, nhưng **không phải mã nguồn**. Không đặt
`main.py` hoặc dữ liệu dự án bên trong `.venv`. Git không lưu thư mục trống;
`tests/` sẽ có file và được lưu khi viết test thực sự.

## 3. Luồng đầu vào → xử lý → đầu ra

```text
Lệnh PowerShell + biến môi trường
    → Python chạy main.py
    → import app.config
    → đọc biến hoặc giá trị mặc định
    → chuẩn hóa và kiểm tra mode
    → guard gọi main()
    → in 5 dòng trạng thái ra terminal
```

Đầu vào hiện là **cấu hình**, chưa phải câu hỏi khách hàng. Đầu ra là văn bản
terminal, chưa phải response API. **API** là giao diện để các chương trình gọi
nhau; dự án sẽ xây sau.

Nếu mode sai, `config.py` phát sinh `ValueError` (lỗi giá trị không hợp lệ).
Việc import dừng lại, `main()` không được gọi; Python in lỗi và trả mã thoát
khác 0. Mã thoát là số báo trạng thái kết thúc của tiến trình: 0 thường là thành
công. **Tiến trình** là một lần chương trình đang chạy trên máy.

Về sau, luồng chatbot sẽ là câu hỏi → logic → interface dữ liệu → repository
→ kết quả có trạng thái dữ liệu → phản hồi. Đây mới là thiết kế, chưa phải code
đang chạy. **Interface** là hợp đồng cách gọi/kết quả; **repository** cung cấp
dữ liệu và che cách lưu trữ; **adapter** triển khai hợp đồng cho một nguồn cụ thể.

## 4. Hàm chính, tham số, giá trị trả về và nơi gọi

**Tham số** là tên biến ở khai báo hàm; **đối số** là giá trị cụ thể truyền vào
khi gọi. **Giá trị trả về** được chuyển cho code gọi bằng `return`; nó khác với
văn bản được `print` in ra.

| Hàm/phương thức | Tham số/đối số dùng trong dự án | Trả về | Nơi gọi |
| --- | --- | --- | --- |
| `main()` | Không có | `None` | Guard cuối `main.py`, hoặc tự gọi sau `import main`. |
| `os.getenv(key, default)` | Tên biến và mặc định, ví dụ `"CATALOG_MODE", "empty"` | Chuỗi `str` trong các lời gọi hiện tại | Bốn dòng khai báo cấu hình trong `app/config.py`. |
| `str.strip()` | Không truyền đối số | Chuỗi mới bỏ khoảng trắng đầu/cuối | Sau mỗi `os.getenv`. |
| `str.lower()` | Không có đối số | Chuỗi mới ở dạng chữ thường | Hai biến mode trong `app/config.py`. |
| `print(...)` | Một chuỗi thông báo; dùng mặc định xuống dòng | `None`, đồng thời in ra terminal | Trong `main()`. |

Chỉ `main()` do dự án tự định nghĩa. Các hàm còn lại có sẵn trong Python.
`strip`/`lower` là **phương thức**: hàm được gọi qua một đối tượng, ở đây là chuỗi.
`config.py` chưa cần hàm riêng hoặc class; các hằng cấu hình được đọc lúc import.

## 5. Giải thích code then chốt và kiến thức mới

### Module, package, import và `__init__.py` — Python

```python
from app.config import CATALOG_MODE, CHAT_MODE
```

**Import** cho phép dùng tên đã khai báo ở module khác. `app.config` là module
`config.py` trong package `app`. Dòng trên đưa hai tên cấu hình vào `main.py`.
Khi chạy `python main.py`, thư mục chứa file này giúp Python tìm package `app`.
Không cần `pip install app` vì `app` là code trong dự án.

Viết chính xác `__init__.py`: hai dấu gạch dưới trước và sau `init`. Trong dự
án, file chỉ có **docstring** (chuỗi mô tả code), không khởi động chương trình.
Python chạy nội dung package/module khi import lần đầu trong tiến trình; các
lần import bình thường sau đó dùng module đã nạp. Vì vậy không để việc gọi model
hoặc tạo đơn trong `__init__.py`.

### Đọc cấu hình và xử lý chuỗi — Python và backend

```python
CATALOG_MODE = os.getenv("CATALOG_MODE", "empty").strip().lower()
```

`os` là **thư viện chuẩn** đi kèm Python. **Biến môi trường** là cặp tên–giá trị
môi trường chạy đưa cho chương trình. `os.getenv` lấy giá trị theo tên; nếu tên
không tồn tại thì dùng `"empty"`. `str` là kiểu chuỗi ký tự.

Ví dụ `" MOCK "` qua `strip()` thành `"MOCK"`, rồi qua `lower()` thành `"mock"`.
Biến được đặt thành chuỗi rỗng vẫn tồn tại; vì vậy không dùng giá trị mặc định,
và kiểm tra mode sẽ từ chối nó.

Tên viết hoa là quy ước **hằng cấu hình**: người đọc hiểu rằng không nên thay
đổi tùy tiện khi chương trình đang chạy. Python không khóa những biến này.
Đổi biến ở PowerShell rồi chạy chương trình mới để nhận cấu hình mới.

`.env.example` là file văn bản mẫu, **không phải biến môi trường đang hoạt động**.
Code hiện chưa đọc `.env`, nên chỉ copy/đổi tên file không làm đổi mode.

### Kiểm tra mode — Python và backend

```python
if CATALOG_MODE not in {"empty", "mock"}:
    raise ValueError("CATALOG_MODE phải là 'empty' hoặc 'mock'.")
```

`if` chỉ chạy nhánh khi điều kiện đúng. `{...}` ở đây là **set** (tập hợp các
giá trị). `not in` hỏi giá trị có nằm ngoài tập cho phép không. `raise` chủ động
phát sinh lỗi; báo lỗi sớm tránh vô tình chọn nguồn khác khi cấu hình sai.

`OLLAMA_MODEL` để chuỗi rỗng vì chưa chọn model; URL/model chưa được kiểm tra
hoặc gọi. Đó là trạng thái chuẩn bị, không phải kết nối đã hoàn thành.

### Hàm, f-string và điểm chạy — Python

```python
def main() -> None:
    print(f"Nguồn dữ liệu: {CATALOG_MODE}.")

if __name__ == "__main__":
    main()
```

`def` định nghĩa hàm. `-> None` là **type hint** (chú thích kiểu): hàm không trả
dữ liệu hữu ích cho nơi gọi; đây không phải cơ chế tự kiểm tra kiểu lúc chạy.
Không có `return` tường minh thì Python trả `None`, giá trị biểu thị không có
kết quả. Hàm vẫn có tác động in văn bản ra màn hình.

Chuỗi có tiền tố `f` là **f-string**: Python thay `{CATALOG_MODE}` bằng giá trị
biến. Ví dụ mode empty thì dòng in là `Nguồn dữ liệu: empty.`.

`__name__` là tên module do Python đặt. Chạy trực tiếp file thì nó bằng
`"__main__"`; import file thì tên là `"main"`. Điều kiện cuối là **guard**
(điều kiện bảo vệ điểm chạy), giúp import không tự in thông báo. Import vẫn
đọc và kiểm tra cấu hình, nên cấu hình sai vẫn có thể gây lỗi khi import.

### Môi trường ảo và dependency — công cụ Python

`.venv` dùng bản Python nền đã chọn và có thư mục cài thư viện riêng cho dự án.
**Dependency** là thư viện ngoài mà code cần. **pip** cài các thư viện này;
`python -m pip` gọi pip của đúng Python, tránh nhầm pip toàn máy.

**Interpreter** là chương trình thực thi mã Python. Dùng
`.venv\Scripts\python.exe` đảm bảo chạy đúng môi trường dù terminal chưa kích hoạt.
Kích hoạt chỉ giúp lệnh `python` tìm môi trường này trước trên đường tìm chương trình.

`requirements.txt` liệt kê dependency khi chạy; `requirements-dev.txt` dành
cho công cụ phát triển/kiểm thử. Dòng `-r requirements.txt` yêu cầu pip đọc cả
danh sách chạy. Hiện hai danh sách không có thư viện ngoài; chưa cần cài pytest.

`.gitignore` quy định file Git bỏ qua khi theo dõi file mới. `.venv` được tạo
lại theo hướng dẫn, không commit. **Git** theo dõi thay đổi mã nguồn; **commit**
là lưu một mốc thay đổi. Giai đoạn này chưa khởi tạo Git repository. Quy tắc
ignore cũng không tự bỏ một file đã được Git theo dõi từ trước.

### Ranh giới dữ liệu và nghiệp vụ — backend, AI/NLP, nghiệp vụ

**Mock** là dữ liệu/nguồn mô phỏng để học và kiểm thử, chưa phải dữ liệu cửa hàng.
**Database** quản lý lưu trữ và truy vấn; `data/` chỉ chứa file tài liệu lúc này.

Trong tương lai, `EmptyCatalogRepository` và `MockCatalogRepository` sẽ thực
hiện cùng interface. Logic chatbot hỏi nguồn qua interface thay vì tự mở file.
Đó là kiến thức thiết kế backend, chưa phải một kỹ thuật huấn luyện AI.

`rule` dự kiến là xử lý bằng quy tắc viết trong code, **không phải mô hình đã
huấn luyện**. **LLM** là mô hình ngôn ngữ lớn; Qwen sẽ hỗ trợ hiểu và diễn đạt
qua Ollama ở giai đoạn sau. Code nghiệp vụ vẫn phải kiểm tra giá/tồn kho và
yêu cầu xác nhận. Thiếu dữ liệu thì nói thiếu thông tin, không đoán.

## 6. Vì sao chọn cách này, giới hạn và phương án khác

- `os.getenv` và hằng cấu hình đủ cho bốn biến; chưa cần class cấu hình hoặc
  thư viện nạp `.env`. Sau này có thể thêm loader khi thật sự cần, kèm quy tắc ưu tiên.
- Một hàm `main()` giữ điểm chạy dễ đọc và dễ import. Chưa cần web framework
  (bộ công cụ xây ứng dụng web), vì chưa cung cấp API.
- Python 3.12 đã có trên máy; dùng `py -3.12` tránh launcher chọn mặc định 3.13.
  Hỗ trợ nhánh không có nghĩa mọi thư viện tương lai đã được kiểm tra.
- `empty` là mặc định phù hợp thực tế chưa có nguồn. Tự chọn mock mặc định có
  thể khiến người đọc hiểu nhầm dữ liệu mô phỏng là dữ liệu thật.
- Chưa xây repository để giữ đúng giai đoạn. Khi thêm nhiều nguồn, class triển
  khai interface có thể phù hợp; không cần tạo trước các adapter chưa có nguồn.
- Thư viện chuẩn giúp chạy mà không cần tải gói. `uv` hoặc công cụ khác có thể
  hữu ích ở dự án lớn hơn; hiện `pip`/requirements dễ học.

Giới hạn: chưa có chat, nguồn dữ liệu hoạt động, API, database, UI hoặc đo chất
lượng trả lời. Không thử Ollama, không chọn model, không tự đọc `.env` và không
thực hiện giao dịch. Các mode là lựa chọn cấu hình, không xác nhận chức năng đã có.

## 7. Cách chạy trên Windows và ví dụ thử

Tại PowerShell trong folder dự án, tạo môi trường nếu chưa có:

```powershell
cd D:\Chatbot
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe main.py
```

Trong VS Code: mở folder → `Ctrl+Shift+P` → **Python: Select Interpreter** →
chọn `D:\Chatbot\.venv\Scripts\python.exe`. Nếu chưa có lệnh này, cài extension
Python của Microsoft. Không bắt buộc dùng `Activate.ps1` để chạy.

Kết quả mặc định:

```text
Dự án chatbot bán bánh tiếng Việt đã sẵn sàng (giai đoạn 1).
Nguồn dữ liệu: empty.
Menu: chưa có dữ liệu; chưa đủ thông tin để xác nhận sản phẩm.
Chính sách: chưa có tài liệu chính thức.
Chế độ chat: rule (chưa triển khai chatbot).
```

Thử cấu hình mock rồi trở lại mặc định:

```powershell
$env:CATALOG_MODE = "mock"
.\.venv\Scripts\python.exe main.py
Remove-Item Env:CATALOG_MODE
```

Phải có `Nguồn dữ liệu: mock.` và thông báo kho mẫu chưa triển khai. Không có
giá hoặc danh sách bánh. Thử lỗi cấu hình:

```powershell
$env:CATALOG_MODE = "database"
.\.venv\Scripts\python.exe main.py
Remove-Item Env:CATALOG_MODE
```

Phải báo `ValueError: CATALOG_MODE phải là 'empty' hoặc 'mock'.` Mode database
chưa được hỗ trợ. Đây là lỗi đầu vào có chủ ý, không phải tính năng bị mất.

Kiểm tra import không tự in:

```powershell
.\.venv\Scripts\python.exe -c "import main"
.\.venv\Scripts\python.exe -m compileall -q main.py app
.\.venv\Scripts\python.exe -m pip check
```

Hai lệnh đầu thành công sẽ không in gì; lệnh cuối phải báo
`No broken requirements found.` nếu dependency không lỗi.

Các câu hỏi mẫu như “Có bánh nào dưới 200 nghìn?” hoặc “Phí giao hàng bao
nhiêu?” **chưa nhập được vào chương trình này**. Chưa có vòng lặp chat. Yêu cầu
nghiệp vụ sau này là trả thiếu thông tin khi nguồn empty, không đoán sản phẩm
hoặc chính sách. Không ghi đây là câu trả lời chatbot đã được kiểm thử.

## 8. Kiểm thử đã chạy, kết quả thật và phần chưa kiểm tra

Thực hiện ngày 02/10/2026 tại `D:\Chatbot`:

| Kiểm tra | Kết quả thực tế |
| --- | --- |
| Tạo `.venv` bằng `py -3.12 -m venv .venv` | Thành công; Python 3.12.10. |
| `pip --version` trong `.venv` | pip 25.0.1; khác pip 26.2.1 ngoài môi trường. |
| Chạy `main.py` mặc định | Mã thoát 0; đúng 5 dòng ở mục 7. |
| Cài hai file requirements với `--no-index` | Cả hai lệnh mã thoát 0; không cài dependency bên ngoài. |
| `pip check` | `No broken requirements found.`, mã thoát 0. |
| `compileall -q main.py app` | Mã thoát 0; không báo lỗi cú pháp. |
| 13 lượt kiểm tra cấu hình/chạy/import qua tiến trình Python con | 13/13 đạt sau khi sửa mã hóa của lệnh kiểm tra. |
| `pip list --format=freeze` trong `.venv` | Chỉ có `pip==25.0.1`; không có thư viện AI. |
| Rà soát cấu trúc/tài liệu | 16 file bắt buộc có nội dung UTF-8; đủ 12 mục học; 8 link nội bộ hợp lệ; chỉ có 3 file Python ứng dụng. |

13 lượt gồm: xác minh Python/môi trường ảo; bốn mặc định; bốn tổ hợp
empty/mock × rule/ollama; chuẩn hóa mode; bốn trường hợp mode sai hoặc rỗng;
URL/model lấy từ biến môi trường; import `main` không in. **Subprocess** là
tiến trình con: bộ kiểm tra chạy Python mới cho từng cấu hình để chúng không
ảnh hưởng lẫn nhau.

Lượt đầu của bộ kiểm tra bổ sung bị lỗi do PowerShell 5.1 truyền chữ Việt qua
pipe bằng ASCII. Chẩn đoán cho thấy chương trình vẫn chạy mã thoát 0 và đủ 5
dòng, nhưng chuỗi kỳ vọng trong bộ kiểm tra bị đổi dấu thành `?`. Chạy lại với
UTF-8 đã đạt 13/13; không phải sửa code nghiệp vụ để bỏ qua lỗi.

Chưa dùng pytest và chưa lưu bộ test chức năng vào `tests/`. Đây là kiểm tra
khởi động/cấu hình bằng lệnh, không phải đánh giá chất lượng chatbot. Chưa kiểm
tra UI VS Code, Git ignore trong repository, Ollama/Qwen, RAM/GPU, dữ liệu thật,
repository, API hoặc đơn hàng. Không có chức năng nào trong số đó đã triển khai.

## 9. Lỗi thường gặp và cách xử lý

| Lỗi/hiện tượng | Cách xử lý |
| --- | --- |
| Không nhận lệnh `py` hoặc thiếu Python 3.12 | Kiểm tra `py -0p`; nếu có đường dẫn Python 3.12 thì dùng trực tiếp đường dẫn đó để tạo `.venv`. Chỉ cài Python khi máy chưa có bản phù hợp. |
| Không tìm thấy `.venv\Scripts\python.exe` | Kiểm tra đang ở `D:\Chatbot`, tạo môi trường bằng `py -3.12 -m venv .venv`. |
| `Activate.ps1` bị chặn | Chạy trực tiếp `.\.venv\Scripts\python.exe main.py`, không cần đổi chính sách máy. |
| `ModuleNotFoundError: app` | Chạy đúng `main.py` ở root dự án, giữ tên folder `app` và file `__init__.py`; không cần cài gói tên app từ Internet. |
| `ValueError` cho mode | Dùng `empty`/`mock` và `rule`/`ollama`; bỏ biến sai ở terminal nếu muốn mặc định. |
| Copy `.env.example` thành `.env` nhưng mode không đổi | Chưa có loader `.env`; đặt `$env:CATALOG_MODE` trong PowerShell rồi chạy tiến trình mới. |
| Chọn `mock` nhưng không thấy bánh | Đúng giới hạn giai đoạn 1; repository và mẫu sẽ xây ở giai đoạn 2. |
| Dấu tiếng Việt sai hoặc `UnicodeEncodeError` | Lưu file UTF-8; thử `.\.venv\Scripts\python.exe -X utf8 main.py` và terminal hỗ trợ UTF-8. |
| Script tiếng Việt truyền qua pipe bị thành `?` trên PowerShell 5.1 | Với lệnh pipe kiểm tra, đặt `$OutputEncoding = [System.Text.UTF8Encoding]::new($false)` trong terminal đó trước khi truyền. Cách chạy file trực tiếp không cần pipe. |
| Lỡ dùng pip toàn máy | Dùng đầy đủ `.\.venv\Scripts\python.exe -m pip ...`; kiểm tra đường dẫn bằng `-m pip --version`. |
| `pytest` chưa có hoặc thư mục tests trống | Chưa cần pytest trong giai đoạn này; không chạy test chatbot chưa tồn tại. |

## 10. Năm câu hỏi vấn đáp/phỏng vấn

1. **Folder, module và package khác nhau thế nào?** Gợi ý: folder nhóm file;
   module thường là file `.py`; package nhóm module. `app` dùng `__init__.py`
   để là package thông thường; `data/` chỉ là folder tài liệu lúc này.
2. **Vì sao `import main` không in thông báo?** Gợi ý: guard kiểm tra `__name__`;
   khi import nó là `main`, nên không gọi `main()`. Cấu hình vẫn được import và kiểm tra.
3. **`.venv` và requirements có vai trò gì?** Gợi ý: `.venv` là môi trường chạy
   riêng; requirements mô tả dependency để tạo lại, không cần đưa môi trường vào Git.
4. **Vì sao chỉnh `.env.example` không làm code đổi mode?** Gợi ý: code chỉ gọi
   `os.getenv`, chưa có bộ đọc file `.env`; đặt biến trong PowerShell mới là đầu vào hiện tại.
5. **Nguồn empty/mock liên quan thế nào tới AI và nghiệp vụ?** Gợi ý: đây là
   trạng thái dữ liệu. Empty không được xác nhận sản phẩm; mock phải có nhãn mô
   phỏng. LLM sau này diễn đạt nhưng code kiểm soát nghiệp vụ qua interface nguồn.

## 11. Ba bài tập nhỏ

1. **Thêm thông báo học tập:** sửa `main()` để in thêm “Mục tiêu hôm nay: hiểu
   import”. Chạy file và giải thích vì sao import vẫn không in. Sau đó có thể
   trả về 5 dòng ban đầu; nếu giữ thay đổi, cập nhật mô tả đầu ra trong tài liệu.
2. **Thử chuỗi và cấu hình:** đặt `$env:CATALOG_MODE = " MOCK "`, chạy rồi bỏ biến.
   Dự đoán kết quả `strip().lower()` trước khi chạy. Thử chuỗi rỗng để thấy sự
   khác nhau giữa biến không có và biến có giá trị rỗng. Không mở rộng mode mới.
3. **Tách hàm đơn giản:** tự viết `show_catalog_status(mode: str) -> None` trong
   `main.py`, chuyển phần in nguồn/menu vào hàm đó và gọi từ `main()`. Giữ thông
   báo và quy tắc hiện có; tự giải thích tham số/đối số và cập nhật bảng hàm nếu giữ bài làm.

Các bài tập là phần để bạn tự làm, chưa được triển khai tự động và không thêm
chatbot hoặc nguồn dữ liệu. Không đưa tên bánh, giá hoặc tồn kho vào bài tập logic.

## 12. Kiến thức cần học trước giai đoạn tiếp theo

- Python: `list`, `dict`, `set`, `None`, vòng lặp, hàm trả dữ liệu, import và exception.
- Kiểu dữ liệu/type hint; phân biệt dữ liệu thiếu với giá trị bằng 0.
- Class cơ bản nếu dùng repository: đối tượng giữ trách nhiệm và cách các nguồn
  cùng thực hiện interface; chưa cần thiết kế hướng đối tượng phức tạp.
- Backend: chia trách nhiệm giữa logic và nguồn; schema thống nhất, xử lý lỗi nguồn.
- Kiểm thử: `assert`, cách đặt tình huống và pytest ở giai đoạn có chức năng thật.
- Nghiệp vụ: mock phải có nhãn, empty không tạo sản phẩm; chính sách cần nguồn riêng.
- AI/NLP: chưa cần tải/học huấn luyện model. Nắm ranh giới LLM hỗ trợ diễn đạt
  và code kiểm soát nghiệp vụ trước khi tích hợp Qwen/Ollama.

Bạn có thể bắt đầu giai đoạn 2 sau khi chạy được chương trình, hiểu các mục
trên và yêu cầu thực hiện phần interface catalog/empty/mock. Không cần database,
menu thật hoặc Ollama để bắt đầu phần đó.
