"""Smoke Qwen thật, tách khỏi pytest. Không tải model/không dùng DB đang demo."""

import argparse
from contextlib import closing
import json
from pathlib import Path
import time
from uuid import uuid4

from app import config, llm_client
from app.conversation import handle_message, new_conversation
from app.knowledge_loader import LocalKnowledgeRepository
from app.order_service import create_order_tools
from app.repositories.local_catalog import LocalCatalogRepository
from app.storage import PROJECT_ROOT, open_storage, load_order_request, utc_now
from scripts.database import seed_database, check_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke riêng bằng Qwen đã cài; có thể chậm, không tải model.")
    parser.add_argument("--skip-policy", action="store_true")
    args = parser.parse_args()
    selected = llm_client.select_model(config.OLLAMA_BASE_URL, config.OLLAMA_MODEL)
    if selected["error"]:
        parser.exit(1, f"Chưa thử model thật: {selected['error']}\n")
    database_path = PROJECT_ROOT / "runtime" / ("model-smoke-" + uuid4().hex[:8] + ".sqlite3")
    report = {"kind": "real_ollama_smoke", "model": selected["model"], "created_at": utc_now(),
              "database_path": str(database_path.relative_to(PROJECT_ROOT)), "steps": [], "passed": False}
    actual_extract = llm_client.extract_turn
    last_extraction = {}
    def traced_extract(*args):
        value = actual_extract(*args)
        last_extraction["proposal"] = value["data"].model_dump(exclude_none=True) if value["data"] else None
        return value
    llm_client.extract_turn = traced_extract  # Chỉ script smoke với đầu vào GIẢ cố định.
    actual_chat = llm_client.chat
    wire_responses = []
    def traced_chat(*args):
        value = actual_chat(*args)
        if args[3].get("title") == "LLMWireTurn":
            wire_responses.append(value)
        return value
    llm_client.chat = traced_chat
    questions = [
        "Giá và size bánh socola?",
        "Mình muốn đặt hai bánh socola size 16 cm, không topping, ghi chữ 'Chúc vui', nhận tại cửa hàng 2099-01-04 10:00, tên DEMO Khách A, sđt TEST-0001.",
        "Đồng ý nhưng đổi sang size 20 cm.",
        "Xác nhận",
        "Xác nhận",
    ]
    if not args.skip_policy:
        questions.append("Giờ mở cửa của cửa hàng?")
    with closing(open_storage(database_path)) as connection:
        seed_database(connection)
        repository = LocalCatalogRepository(database_path)
        knowledge = LocalKnowledgeRepository(database_path)
        current = new_conversation()
        current["model"] = selected["model"]
        report["conversation_id"] = current["id"]
        for index, question in enumerate(questions):
            started = time.monotonic()
            turn = handle_message(question, repository, current, model=selected["model"], chat_mode="ollama",
                                  knowledge_repository=knowledge, storage_connection=connection,
                                  order_tools=create_order_tools(repository, connection, current["id"]))
            current = turn["conversation"]
            step = {"question": question, "engine": turn["engine"], "llm_error": turn["llm_error"],
                    "source_error": turn["response"]["error"], "attempts": turn["nlu_attempts"],
                    "seconds": round(time.monotonic()-started, 2), "state": current["order"]["state"],
                    "revision": current["order"]["revision"], "products": [p["id"] for p in turn["response"]["products"]],
                    "policy_sources": turn["response"]["policy"]["source_ids"] if turn["response"]["policy"] else [],
                    "orders_count": connection.execute("SELECT count(*) FROM orders").fetchone()[0],
                    "proposal": last_extraction.get("proposal"),
                    "response": turn["response"]["text"]}
            report["steps"].append(step)
            print(json.dumps({key:value for key,value in step.items() if key not in {"response","question","proposal"}}, ensure_ascii=False), flush=True)
            # Không gửi tiếp câu xác nhận nếu model chưa hiểu được REVIEW.
            if turn["engine"] != "ollama":
                break
        submission = current["order"].get("submission")
        if submission:
            report["order"] = load_order_request(connection, submission["id"], current["id"])
        report["database_check"] = check_database(connection)
        report["passed"] = (len(report["steps"]) == len(questions)
                            and report["steps"][0]["products"] == ["demo-001"]
                            and report["steps"][1]["state"] == "REVIEW"
                            and report["steps"][2]["orders_count"] == 0
                            and report["steps"][3]["orders_count"] == 1
                            and report["steps"][4]["orders_count"] == 1
                            and bool(submission and submission["quote"]["total_vnd"] == 700000)
                            and (args.skip_policy or bool(report["steps"][-1]["policy_sources"])))
    output = PROJECT_ROOT / "evaluation" / "local_demo_smoke_report.json"
    report["wire_responses"] = wire_responses
    if output.exists():
        previous = json.loads(output.read_text(encoding="utf-8"))
        report["previous_runs"] = previous.get("previous_runs", []) + [{key: value for key, value in previous.items() if key != "previous_runs"}]
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Báo cáo: {output}; passed={report['passed']}")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
