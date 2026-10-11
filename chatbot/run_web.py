"""Chạy web luôn bật Qwen; dùng python.exe của .venv, không tải model."""

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy chatbot web với AI qua Ollama.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Cổng phải nằm trong khoảng 1–65535.")
    # Trước khi Uvicorn import app.config: bỏ rule còn sót từ lần thử trước.
    os.environ["CHAT_MODE"] = "ollama"
    import uvicorn
    uvicorn.run("app.api:app", host="127.0.0.1", port=args.port, workers=1, access_log=False)


if __name__ == "__main__":
    main()
