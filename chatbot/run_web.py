"""Chạy giao diện chatbot với Ollama local; không cần key."""

import argparse
import os
from threading import Thread


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy chatbot Qwen qua Ollama local.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--chat-mode", choices=["ollama", "rule"], default="ollama")
    parser.add_argument("--prewarm", action=argparse.BooleanOptionalAction, default=True,
                        help="Tự nạp trước model đã cài ở nền (mặc định bật); dùng --no-prewarm để tắt.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port phải từ 1 đến 65535.")
    os.environ["CHAT_MODE"] = args.chat_mode
    try:
        from app import config
    except ValueError as error:
        parser.exit(2, str(error) + "\n")
    import uvicorn
    print(f"Đang khởi động chatbot. Khi server báo sẵn sàng, mở: http://127.0.0.1:{args.port}/", flush=True)
    print(f"Website có khung chat: http://127.0.0.1:{args.port}/website/?site_v=20261024-3", flush=True)
    print("Dừng server: Ctrl+C.", flush=True)
    if args.chat_mode == "ollama":
        def prepare_model():
            from app.llm_client import request_json, select_model
            selected = select_model(config.OLLAMA_BASE_URL, config.OLLAMA_MODEL)
            if selected["error"]:
                print("Ollama chưa sẵn sàng: " + selected["error"] + ". Kiểm tra ollama list/ollama serve.", flush=True)
                return
            print("Model local: " + selected["model"], flush=True)
            if args.prewarm and config.OLLAMA_KEEP_ALIVE_SECONDS > 0:
                result = request_json(config.OLLAMA_BASE_URL, "/api/chat", {
                    "model": selected["model"], "messages": [], "stream": False,
                    "keep_alive": config.OLLAMA_KEEP_ALIVE_SECONDS, "options": {"num_ctx": 4096},
                }, config.OLLAMA_TIMEOUT_SECONDS)
                ready = result["ok"] and result["data"].get("done") is True and result["data"].get("model") == selected["model"]
                if ready:
                    print("Đã nạp trước model local.", flush=True)
                elif result["error"] == "model_runtime_missing":
                    print("Ollama thiếu llama-server.exe: cần sửa/cài lại Ollama. Model đã cài vẫn có trong ollama list; chat AI chưa dùng được.", flush=True)
                else:
                    print("Chưa nạp trước được model (" + (result["error"] or "invalid_response") + "); web đã chạy nhưng chat AI chưa sẵn sàng.", flush=True)
        Thread(target=prepare_model, name="ollama-prepare", daemon=True).start()
    uvicorn.run("app.api:app", host="127.0.0.1", port=args.port, workers=1, access_log=False)


if __name__ == "__main__":
    main()
