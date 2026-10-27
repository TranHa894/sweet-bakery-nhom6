```pip install -r requirements.txt``` to install all required Python packages.
run
## Website có khung chatbot

Chạy trong thư mục gốc sweet-bakery-nhom6:

```powershell
.\chatbot\.venv\Scripts\python.exe -B -X utf8 chatbot/run_web.py
```

Mở **http://127.0.0.1:8000/website/?site_v=20261024-3**. Chatbot có nút tròn, cửa sổ nhỏ và chế độ toàn màn hình; giữ phiên/lịch sử trong cùng tab khi chuyển trang. Ollama và model đã cấu hình cần sẵn sàng để trả lời bằng Qwen. Không phải chạy Flask chỉ để thử website mẫu cùng chatbot.

Đọc [hướng dẫn chatbot](chatbot/README.md) và [hướng dẫn website](static/README.md) để cài dependency/cấu hình URL và biết giới hạn phiên. Cấu trúc backend/checkout cũ được giữ nguyên.
