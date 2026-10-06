"""Đo Qwen NLU và controller bằng hội thoại có nhãn; không gửi nhãn cho model."""

import argparse
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from time import perf_counter
from uuid import uuid4

from app import config, llm_client
from app.conversation import handle_message, new_conversation
from app.order_service import create_order_tools
from app.repositories.empty_catalog import EmptyCatalogRepository
from app.repositories.local_catalog import LocalCatalogRepository
from app.repositories.mock_catalog import MockCatalogRepository
from app.storage import open_storage, utc_now
from app.text_utils import normalize_text
from scripts.database import seed_database

ROOT = Path(__file__).resolve().parents[1]


def load_dataset(split):
    """Trả bộ nhãn tĩnh; người gọi chỉ truyền item.message vào chatbot."""
    path = ROOT / "evaluation" / f"intent_context_{split}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    items = [t for d in data["dialogues"] for t in d["turns"]]
    if data["split"] != split or data["sample_count"] != len(items):
        raise ValueError("Dataset count/split sai")
    if len({item["id"] for item in items}) != len(items):
        raise ValueError("Dataset có ID trùng")
    return data, hashlib.sha256(path.read_bytes()).hexdigest()


def request_signature(item):
    """Tên có/không tiền tố bánh vẫn cùng mention, không đo accuracy bằng dấu."""
    names = [re.sub(r"^(?:banh\s+)?(?:kem\s+)?", "", normalize_text(x)) for x in item["product_mentions"]]
    return (tuple(sorted(item["intents"])), tuple(sorted(names)), item["reference"], normalize_text(item.get("size") or ""))


def score_turn(item, result, proposal, previous_draft, order_count):
    """Chấm sau inference: tách extraction với hành vi/đơn, không sửa output."""
    label, expected = item["label"], item["expected"]
    proposal = proposal or {}
    draft, response = result["conversation"]["order"], result["response"]
    extraction = {
        "schema_grounding_ok": bool(proposal) and result["engine"] != "llm_error",
        "intents_exact": set(proposal.get("intents", [])) == set(label["intents"]),
        "action_exact": proposal.get("action") == label["action"],
        "reference_exact": proposal.get("reference") == label["reference"],
        "updates_exact": proposal.get("updates", {}) == label["updates"],
        "clear_slots_exact": set(proposal.get("clear_slots", [])) == set(label["clear_slots"]),
    }
    if label.get("requests"):
        extraction["request_links_exact"] = sorted(request_signature(x) for x in proposal.get("requests", [])) == sorted(request_signature(x) for x in label["requests"])
    if "order_operation" in label:
        extraction["order_operation_exact"] = proposal.get("order_operation", "none") == label["order_operation"]
    behavior = {}
    if "product_ids" in expected:
        behavior["query_products_exact"] = set(p["id"] for p in response["products"]) == set(expected["product_ids"])
    if "order_product_id" in expected:
        behavior["draft_target"] = draft["slots"]["product_id"] == expected["order_product_id"]
    if expected.get("draft_unchanged"):
        behavior["draft_unchanged"] = draft == previous_draft
    for key in ["state", "catalog_status"]:
        if key in expected:
            behavior[key] = (draft[key] if key == "state" else response[key]) == expected[key]
    if "clarification" in expected:
        behavior["clarification"] = response["requires_clarification"] == expected["clarification"]
    if "order_count" in expected:
        behavior["order_count"] = order_count == expected["order_count"]
    if "confirmed" in expected:
        behavior["confirmed"] = bool(draft.get("submission") and draft["submission"]["confirmed"]) == expected["confirmed"]
    for field, value in expected.get("slots", {}).items():
        behavior["slot_" + field] = draft["slots"][field] == value
    return {"extraction": extraction, "behavior": behavior,
            "extraction_pass": all(extraction.values()), "behavior_pass": all(behavior.values())}


def summarize(steps):
    def metric(name):
        values = [s["score"][section][name] for s in steps for section in ["extraction", "behavior"] if name in s["score"][section]]
        return {"passed": sum(values), "total": len(values), "rate": round(sum(values) / len(values), 4) if values else None}
    names = sorted({k for s in steps for section in ["extraction", "behavior"] for k in s["score"][section]})
    tp = fp = fn = 0
    for step in steps:
        predicted, gold = set((step["proposal"] or {}).get("intents", [])), set(step["label"]["intents"])
        tp += len(predicted & gold)
        fp += len(predicted - gold)
        fn += len(gold - predicted)
    return {"samples": len(steps), "metrics": {name: metric(name) for name in names},
            "intent_micro_f1": round(2 * tp / (2 * tp + fp + fn), 4) if 2 * tp + fp + fn else 0,
            "extraction_exact": sum(s["score"]["extraction_pass"] for s in steps),
            "behavior_exact": sum(s["score"]["behavior_pass"] for s in steps),
            "model_errors": sum(s["engine"] == "llm_error" for s in steps),
            "controller_source_errors": sum(s["engine"] == "source_error" for s in steps)}


def evaluate(split, label, limit=None):
    dataset, dataset_hash = load_dataset(split)
    selected = llm_client.select_model(config.OLLAMA_BASE_URL, config.OLLAMA_MODEL)
    output = ROOT / "evaluation" / f"intent_context_{label}_{split}_report.json"
    sources = ["app/schemas.py", "app/llm_client.py", "app/conversation.py", "app/order_nlu.py"]
    if (ROOT / "data/nlu_few_shots.json").exists():
        sources.append("data/nlu_few_shots.json")
    report = {"run_type": "real_ollama_nlu_controller", "label": label, "split": split,
        "created_at": utc_now(), "model": selected["model"], "dataset_sha256": dataset_hash,
        "dataset_samples": dataset["sample_count"], "limit": limit,
        "code_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
        "scope": "Real Qwen extract_turn + controller/FSM/tools; knowledge empty, no RAG generation accuracy",
        "completed": False, "steps": []}
    if output.exists():
        previous = json.loads(output.read_text(encoding="utf-8"))
        report["previous_runs"] = previous.get("previous_runs", []) + [{k:v for k,v in previous.items() if k != "previous_runs"}]
    def write_report():
        report["summary"] = summarize(report["steps"])
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if selected["error"]:
        report["blocked"] = selected["error"]
        write_report()
        print("Chưa chạy model thật:", selected["error"], flush=True)
        return report
    path = ROOT / "runtime" / ("nlu-eval-" + uuid4().hex[:12] + ".sqlite3")
    report["database"] = str(path.relative_to(ROOT))
    original_extract, original_chat, original_http = llm_client.extract_turn, llm_client.chat, llm_client.request_json
    trace = {}
    def traced_extract(*args, **kwargs):
        result = original_extract(*args, **kwargs)
        trace["proposal"] = result["data"].model_dump(exclude_none=True) if result["data"] else None
        return result
    def traced_chat(messages, *args, **kwargs):
        if "context_sent" not in trace:
            trace["context_sent"] = json.loads(messages[-1]["content"]).get("context")
        result = original_chat(messages, *args, **kwargs)
        trace.setdefault("raw_outputs", []).append(result.get("content"))
        return result
    def traced_http(*args, **kwargs):
        result = original_http(*args, **kwargs)
        packet = result.get("data") or {}
        if "prompt_eval_count" in packet:
            trace.setdefault("ollama_metrics", []).append({k:packet.get(k) for k in ["prompt_eval_count", "eval_count", "done_reason"]})
        return result
    llm_client.extract_turn, llm_client.chat, llm_client.request_json = traced_extract, traced_chat, traced_http
    try:
        with closing(open_storage(path)) as connection:
            seed_database(connection)
            for dialogue in dataset["dialogues"]:
                current = new_conversation()
                current["model"] = selected["model"]
                repository = {"empty": EmptyCatalogRepository, "mock": MockCatalogRepository}.get(dialogue["mode"])
                repository = repository() if repository else LocalCatalogRepository(path)
                original_search = repository.search_products
                def traced_search(filters):
                    result = original_search(filters)
                    trace.setdefault("catalog_queries", []).append({"filters":deepcopy(filters), "status":result["status"], "ids":[p["id"] for p in result["products"]]})
                    return result
                repository.search_products = traced_search
                for item in dialogue["turns"]:
                    if limit and len(report["steps"]) >= limit:
                        break
                    trace.clear()
                    previous_draft = deepcopy(current["order"])
                    started = perf_counter()
                    result = handle_message(item["message"], repository, current, chat_mode="ollama", model=selected["model"],
                        storage_connection=connection, order_tools=create_order_tools(repository, connection, current["id"]))
                    current = result["conversation"]
                    count = connection.execute("SELECT count(*) FROM orders WHERE conversation_id=?", (current["id"],)).fetchone()[0]
                    score = score_turn(item, result, trace.get("proposal"), previous_draft, count)
                    step = {"id":item["id"], "dialogue_id":dialogue["id"], "mode":dialogue["mode"],
                        "message":item["message"], "label":item["label"], "expected":item["expected"],
                        **deepcopy(trace), "engine":result["engine"], "error":result["llm_error"], "score":score,
                        "seconds":round(perf_counter()-started, 2), "current_turn":result.get("current_turn"),
                        "draft_before":previous_draft, "draft_after":deepcopy(current["order"]), "answer":result["response"]["text"]}
                    report["steps"].append(step)
                    write_report()
                    print(item["id"], "NLU", score["extraction_pass"], "behavior", score["behavior_pass"], "error", result["llm_error"], "seconds", step["seconds"], flush=True)
                if limit and len(report["steps"]) >= limit:
                    break
        report["completed"] = True
    finally:
        llm_client.extract_turn, llm_client.chat, llm_client.request_json = original_extract, original_chat, original_http
        write_report()
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
    print("Report:", output, flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--label", default="manual")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9_-]+", args.label) or (args.limit is not None and args.limit < 1):
        parser.error("label cần a-z/0-9/_/- và limit cần nguyên dương")
    report = evaluate(args.split, args.label, args.limit)
    raise SystemExit(0 if report["completed"] else 2)


if __name__ == "__main__":
    main()
