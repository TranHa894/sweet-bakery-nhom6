"""Điểm chạy chatbot terminal: rule hoặc Qwen qua Ollama local."""

import sqlite3
import json

from app.conversation import new_conversation, handle_message
from app.config import CATALOG_MODE, CHAT_MODE, KNOWLEDGE_MODE, CHATBOT_DB_PATH
from app.knowledge_loader import create_knowledge_repository
from app.repositories.catalog import create_catalog_repository
from app.text_utils import normalize_text
from app.storage import open_storage, load_conversation, list_records
from app.order_service import create_order_tools


def main() -> None:
    """Tạo nguồn và phiên một lần; chỉ gọi model khi chọn ollama."""
    print("Chatbot bán bánh tiếng Việt — LOCAL DEMO, không thanh toán/giao thật.")
    print(f"Nguồn dữ liệu: {CATALOG_MODE}.")
    repository = create_catalog_repository(CATALOG_MODE, CHATBOT_DB_PATH)
    knowledge_repository = create_knowledge_repository(KNOWLEDGE_MODE, CHATBOT_DB_PATH if KNOWLEDGE_MODE == "local_demo" else None)
    print(f"Nguồn chính sách: {KNOWLEDGE_MODE}.")
    conversation = new_conversation()
    try:
        connection = open_storage(CHATBOT_DB_PATH)
    except (OSError, ValueError, sqlite3.Error):
        print("Không mở được database chatbot; hãy kiểm tra CHATBOT_DB_PATH/quyền ghi. Chưa khởi động phiên lưu trữ.")
        return
    try:
        run_terminal(repository, knowledge_repository, connection, conversation)
    finally:
        connection.close()


def run_terminal(repository, knowledge_repository, connection, conversation) -> None:
    """Vòng nhập/in; main đóng connection kể cả khi có exception."""
    print(f"Chế độ chat: {CHAT_MODE}; đặt bánh mô phỏng, chỉ dùng liên hệ GIẢ. Gõ 'thoát', 'mới' hoặc 'đặt bánh'.")
    print(f"Phiên: {conversation['id']}. Gõ 'tiếp tục: ID' để nạp phiên thử nghiệm đã lưu; đây không phải cơ chế đăng nhập.")
    print("Lệnh local: /new, /exit, /draft, /orders, /order ID; /resume ID để nạp phiên. Lệnh quản lý CLI không gửi model.")
    while True:
        try:
            message = input("Bạn: ")
        except (EOFError, KeyboardInterrupt):
            print(f"\n[Nguồn: {CATALOG_MODE}] Kết thúc phiên terminal.")
            break
        # normalize_text bỏ dấu câu, gồm '/'; giữ dấu này cho lệnh quản lý.
        command = message.strip().lower() if message.strip().startswith("/") else normalize_text(message)
        if command in {"thoat", "exit", "quit", "/exit"}:
            print(f"[Nguồn: {CATALOG_MODE}] Tạm biệt!")
            break
        if command in {"moi", "reset", "/new"}:
            conversation = new_conversation()
            print(f"[Nguồn: {CATALOG_MODE}] Đã bỏ nhu cầu cũ; phiên mới: {conversation['id']}; dữ liệu đã lưu vẫn giữ.")
            continue
        if command == "/draft":
            print(json.dumps(conversation["order"], ensure_ascii=False, indent=2))
            continue
        if command == "/orders":
            records = list_records(connection, "submissions", conversation["id"])
            print(json.dumps([{k: record[k] for k in ("id", "kind", "confirmed", "data_mode", "quote")} for record in records], ensure_ascii=False, indent=2))
            continue
        if command.startswith("/order "):
            result = create_order_tools(repository, connection, conversation["id"])["get_order"](message.split(" ", 1)[1].strip())
            record = result["data"] if result["status"] == "available" else None
            print(json.dumps(record, ensure_ascii=False, indent=2) if record else "Không tìm thấy bản ghi thuộc phiên hiện tại.")
            continue
        if command.startswith("tiep tuc:") or command.startswith("/resume "):
            identifier = message.split(":" if ":" in message else " ", 1)[1].strip()
            saved = load_conversation(connection, identifier)
            if saved is not None:
                conversation = saved
                print(f"Đã nạp phiên thử nghiệm [{conversation['id']}], bản nháp {conversation['order']['state']}.")
            else:
                print("Không tìm thấy phiên thử nghiệm; chưa đổi phiên hiện tại.")
            continue
        if not message.strip():
            continue
        turn = handle_message(message, repository, conversation, chat_mode=CHAT_MODE, knowledge_repository=knowledge_repository,
                              order_tools=create_order_tools(repository, connection, conversation["id"]), storage_connection=connection)
        conversation = turn["conversation"]
        print("Bot: " + turn["response"]["text"])
        print(f"[Bộ hiểu câu: {turn['engine']}; model: {turn['model'] or 'không dùng'}; NLU: {turn['nlu_attempts']} lần; diễn đạt: {turn['phrasing_status']}]")
        policy = turn["response"]["policy"]
        if policy is not None:
            print(f"[RAG: {policy['engine']}; trạng thái: {policy['status']}; model: {turn['model'] or 'không dùng'}; lần gọi/sửa: {policy['attempts']}; nguồn: {', '.join(policy['source_ids']) or 'không có'}]")


if __name__ == "__main__":
    main()
