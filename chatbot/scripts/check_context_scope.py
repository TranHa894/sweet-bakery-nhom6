"""Smoke Qwen thật cho lỗi phạm vi sản phẩm, dùng SQLite riêng, không reset."""

from contextlib import closing
from copy import deepcopy
import json
from uuid import uuid4

from app import config, llm_client
from app.conversation import handle_message, new_conversation
from app.order_service import create_order_tools
from app.repositories.local_catalog import LocalCatalogRepository
from app.storage import PROJECT_ROOT, open_storage, utc_now
from scripts.database import seed_database


def main() -> None:
    selected = llm_client.select_model(config.OLLAMA_BASE_URL, config.OLLAMA_MODEL)
    if selected["error"]:
        raise SystemExit("Chưa kiểm tra model thật: " + selected["error"])
    path = PROJECT_ROOT / "runtime" / ("context-after-" + uuid4().hex[:8] + ".sqlite3")
    report = {"kind": "real_ollama_context_scope", "model": selected["model"],
              "created_at": utc_now(), "database": str(path.relative_to(PROJECT_ROOT)), "steps": []}
    actual_extract = llm_client.extract_turn
    proposals = []

    def traced_extract(*args):
        result = actual_extract(*args)
        proposals.append(result["data"].model_dump(exclude_none=True) if result["data"] else {"error": result["error"]})
        return result

    # Chỉ ghi các câu thử cố định không có liên hệ/token, trong tiến trình smoke.
    llm_client.extract_turn = traced_extract
    try:
        with closing(open_storage(path)) as connection:
            seed_database(connection)
            repository = LocalCatalogRepository(path)
            current = new_conversation()
            original_draft = None
            for message in ["Tôi muốn đặt bánh socola", "Bánh dâu giá bao nhiêu?",
                            "Bảo quản bánh dâu thế nào?", "Giá bánh dâu và socola?"]:
                turn = handle_message(message, repository, current, chat_mode="ollama", model=selected["model"],
                                      storage_connection=connection,
                                      order_tools=create_order_tools(repository, connection, current["id"]))
                current = turn["conversation"]
                if original_draft is None:
                    original_draft = deepcopy(current["order"])
                step = {"message": message, "proposal": proposals[-1], "engine": turn["engine"],
                        "error": turn["llm_error"], "products": [p["id"] for p in turn["response"]["products"]],
                        "draft_product_id": current["order"]["slots"]["product_id"],
                        "draft_unchanged": current["order"] == original_draft,
                        "scope": turn.get("current_turn"), "text": turn["response"]["text"]}
                report["steps"].append(step)
                print(json.dumps({k: v for k, v in step.items() if k not in {"scope", "text", "proposal"}}, ensure_ascii=False), flush=True)
    finally:
        llm_client.extract_turn = actual_extract
    steps = report["steps"]
    report["passed"] = (all(s["engine"] == "ollama" and s["draft_unchanged"] and s["draft_product_id"] == "demo-001" for s in steps)
                        and steps[1]["products"] == ["demo-002"] and steps[2]["products"] == ["demo-002"]
                        and set(steps[3]["products"]) == {"demo-001", "demo-002"})
    output = PROJECT_ROOT / "evaluation" / "context_scope_after.json"
    if output.exists():
        previous = json.loads(output.read_text(encoding="utf-8"))
        report["previous_runs"] = previous.get("previous_runs", []) + [{k: v for k, v in previous.items() if k != "previous_runs"}]
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Báo cáo: {output}; passed={report['passed']}")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
