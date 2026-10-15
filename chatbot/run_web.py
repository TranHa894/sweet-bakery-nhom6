"""Chạy giao diện chatbot với Ollama local; không cần key."""

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy chatbot Qwen qua Ollama local.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--chat-mode", choices=["ollama", "rule"], default="ollama")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port phải từ 1 đến 65535.")
    os.environ["CHAT_MODE"] = args.chat_mode
    try:
        from app import config
    except ValueError as error:
        parser.exit(2, str(error) + "\n")
    if args.chat_mode == "ollama":
        from app.llm_client import select_model
        selected = select_model(config.OLLAMA_BASE_URL, config.OLLAMA_MODEL)
        if selected["error"]:
            print("Ollama chưa sẵn sàng: " + selected["error"] + ". Kiểm tra ollama list/ollama serve.", flush=True)
        else:
            print("Model local: " + selected["model"], flush=True)
    import uvicorn
    print(f"Đang khởi động chatbot. Khi server báo sẵn sàng, mở: http://127.0.0.1:{args.port}/", flush=True)
    print("Dừng server: Ctrl+C.", flush=True)
    uvicorn.run("app.api:app", host="127.0.0.1", port=args.port, workers=1, access_log=False)


if __name__ == "__main__":
    main()
