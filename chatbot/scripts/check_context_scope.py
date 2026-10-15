"""Kiểm tra model thật với database tạm; không reset/lưu báo cáo vào dữ liệu đang dùng."""

from contextlib import closing
from copy import deepcopy
import json
import time
from pathlib import Path
from uuid import uuid4

from app import config, llm_client
from app.conversation import handle_message, new_conversation
from app.knowledge_loader import LocalKnowledgeRepository
from app.order_service import create_order_tools
from app.repositories.local_catalog import LocalCatalogRepository
from app.storage import PROJECT_ROOT, open_storage
from scripts.database import seed_database


def main() -> None:
    base_url, model, timeout = config.get_llm_settings("ollama")
    selected = llm_client.select_model(base_url, model, timeout)
    if selected["error"]:
        raise SystemExit("Chưa kiểm tra model thật: " + selected["error"])
    path = PROJECT_ROOT / "runtime" / (".context-check-" + uuid4().hex + ".sqlite3")
    assert path.resolve().is_relative_to((PROJECT_ROOT / "runtime").resolve())
    results = []
    try:
        with closing(open_storage(path)) as connection:
            seed_database(connection)
            repository = LocalCatalogRepository(path)
            knowledge = LocalKnowledgeRepository(path)

            def run(current, message, verify):
                old_draft = deepcopy(current["order"])
                tick = time.monotonic()
                turn = handle_message(message, repository, current, chat_mode="ollama", base_url=base_url, timeout=timeout, model=selected["model"],
                    knowledge_repository=knowledge, storage_connection=connection,
                    order_tools=create_order_tools(repository, connection, current["id"]))
                passed = turn["engine"] == "ollama" and bool(verify(turn, old_draft))
                results.append(passed)
                print(json.dumps({"message": message, "passed": passed, "seconds": round(time.monotonic()-tick, 2),
                    "error": turn["llm_error"], "intents": turn["response"]["intents"],
                    "products": [p["id"] for p in turn["response"]["products"]],
                    "state": turn["conversation"]["order"]["state"], "answer": turn["response"]["text"]}, ensure_ascii=False), flush=True)
                return turn["conversation"]

            def products(turn, identifiers):
                return [p["id"] for p in turn["response"]["products"]] == identifiers

            current = run(new_conversation(), "Tôi muốn đặt bánh socola",
                lambda t, old: t["conversation"]["order"]["slots"]["product_id"] == "demo-001")
            current = run(current, "Bánh dâu giá bao nhiêu?",
                lambda t, old: products(t, ["demo-002"]) and t["conversation"]["order"] == old and "size bao nhiêu" not in t["response"]["text"])
            run(current, "Bánh đó giá bao nhiêu?", lambda t, old: products(t, ["demo-002"]) and t["conversation"]["order"] == old)
            current = run(new_conversation(), "Bánh dâu có giá như thế nào?", lambda t, old: products(t, ["demo-002"]))
            run(current, "Bánh kem dâu", lambda t, old: products(t, ["demo-002"]) and "price" in t["response"]["intents"] and t["conversation"]["order"] == old)
            run(new_conversation(), "Bánh kem dâu", lambda t, old: products(t, ["demo-002"]) and t["conversation"]["order"]["state"] == "BROWSING")
            run(new_conversation(), "Giá bánh dâu size 16 cm và bánh socola có sữa không?",
                lambda t, old: [(r["intents"], r["product_ids"]) for r in (t.get("current_turn") or {}).get("requests", [])] == [(["price"], ["demo-002"]), (["allergen"], ["demo-001"])] and "280.000" in t["response"]["text"] and "250.000" not in t["response"]["text"])
            current = run(new_conversation(), "Đặt bánh socola size 16 cm",
                lambda t, old: t["conversation"]["order"]["slots"]["size"] == "16 cm")
            run(current, "Hai cái", lambda t, old: t["conversation"]["order"]["slots"]["quantity"] == 2 and t["conversation"]["order"]["slots"]["size"] == "16 cm")
            run(new_conversation(), "Giờ mở cửa của cửa hàng?",
                lambda t, old: bool(t["response"]["policy"] and t["response"]["policy"]["source_ids"]))
            run(new_conversation(), "khong hoi gia banh dau, chi hoi gia banh socola",
                lambda t, old: products(t, ["demo-001"]))
    finally:
        # Chỉ xóa file tạm do chính lần chạy này tạo; không dùng DATABASE_PATH.
        for suffix in ("", "-journal", "-wal", "-shm"):
            temporary = Path(str(path) + suffix)
            assert temporary.resolve().parent == (PROJECT_ROOT / "runtime").resolve()
            if temporary.exists():
                temporary.unlink()
    print(f"model thật: {sum(results)}/{len(results)} lượt đạt; không phải kiểm tra toàn bộ chất lượng chatbot.")
    raise SystemExit(0 if results and all(results) else 1)


if __name__ == "__main__":
    main()
