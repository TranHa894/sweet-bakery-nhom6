"""Đo NLU Qwen/Ollama và controller bằng hội thoại có nhãn; không gửi nhãn cho model."""

import argparse
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from time import perf_counter

from app import config, llm_client
from app.conversation import handle_message, new_conversation
from app.order_service import create_order_tools
from app.repositories.empty_catalog import EmptyCatalogRepository
from app.repositories.local_catalog import LocalCatalogRepository
from app.repositories.mock_catalog import MockCatalogRepository
from app.storage import open_storage, utc_now
from app.text_utils import normalize_text
from scripts.database import seed_database
from pydantic import ValidationError
from app.schemas import OrderItemSelection

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
    return (tuple(sorted(item["intents"])), tuple(sorted(names)), item.get("reference", "none"), normalize_text(item.get("size") or ""))


def order_item_signature(items):
    """Chuẩn hóa nullable/default bằng schema; giữ thứ tự món và số lượng."""
    if not isinstance(items, list):
        return None
    try:
        return [OrderItemSelection.model_validate(item).model_dump(mode="json") for item in items]
    except ValidationError:
        return None


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
    if "order_negated" in label:
        extraction["order_negated_exact"] = proposal.get("order_negated", False) == label["order_negated"]
    if "continuation" in label:
        extraction["continuation_exact"] = proposal.get("continuation", "none") == label["continuation"]
    if "order_operation" in label:
        extraction["order_operation_exact"] = proposal.get("order_operation", "none") == label["order_operation"]
    if "order_items" in label:
        actual_items = order_item_signature(proposal.get("order_items", []))
        extraction["order_items_exact"] = (actual_items is not None
            and actual_items == order_item_signature(label["order_items"]))
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
    if "items" in expected:
        actual = [{"product_id": draft["slots"]["product_id"], "quantity": draft["slots"]["quantity"]}] + [{"product_id": i["product_id"], "quantity": i["quantity"]} for i in draft.get("extra_items", [])]
        behavior["ordered_items"] = actual == expected["items"]
    body = response["text"]
    for phrase in expected.get("response_contains", []):
        behavior["contains:" + phrase] = phrase in body
    for phrase in expected.get("response_absent", []):
        behavior["absent:" + phrase] = phrase not in body
    for phrase, count in expected.get("response_counts", {}).items():
        behavior["count:" + phrase] = body.count(phrase) == count
    for first, later in expected.get("response_order", []):
        behavior["before:" + first + ":" + later] = first in body and later in body and body.index(first) < body.index(later)
    if "order_reference" in label:
        extraction["order_reference_exact"] = proposal.get("order_reference") == label["order_reference"]
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


def evaluate(split, label="manual", limit=None, output=None, engine="ollama", dialogue_id=None):
    """RAM riêng từng hội thoại. Fake đo code; ollama đo model local thật."""
    if engine not in {"fake", "ollama"}:
        raise ValueError("engine chỉ nhận fake hoặc ollama.")
    dataset, dataset_hash = load_dataset(split)
    chat_mode = "ollama"
    base_url, model, timeout = config.get_llm_settings(chat_mode)
    selected = ({"model": "fake-evaluation", "error": None} if engine == "fake"
                else llm_client.select_model(base_url, model, timeout))
    report = {"run_type": "fake_logic" if engine == "fake" else f"real_{engine}_nlu_controller",
        "label": label, "split": split, "created_at": utc_now(), "model": selected["model"],
        "dataset_sha256": dataset_hash, "dataset_samples": dataset["sample_count"],
        "limit": limit, "scope": "Intent/context/order behavior; knowledge empty, no RAG generation score",
        "database": ":memory:", "completed": False, "steps": [],
        "code_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
            ["app/schemas.py", "app/llm_client.py", "app/conversation.py", "app/order_nlu.py", "data/nlu_few_shots.json"]}}
    target = None
    if output is not None:
        target = Path(output)
        if not target.is_absolute():
            target = ROOT / target
        target = target.resolve()
        if not target.is_relative_to((ROOT / "runtime").resolve()) or target.suffix != ".json":
            raise ValueError("Báo cáo chỉ được ghi file .json trong runtime của chatbot.")
    def write_report():
        report["summary"] = summarize(report["steps"])
        if target is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if selected["error"]:
        report["blocked"] = selected["error"]
        write_report()
        print("Chưa chạy model thật:", selected["error"], flush=True)
        return report
    original_extract = llm_client.extract_turn
    original_provider = config.ORDER_PROVIDER
    trace = {}
    def traced_extract(*args, **kwargs):
        result = original_extract(*args, **kwargs)
        trace["proposal"] = result["data"].model_dump(exclude_none=True) if result["data"] else None
        return result
    try:
        dialogues = [d for d in dataset["dialogues"] if dialogue_id is None or d["id"] == dialogue_id]
        if not dialogues:
            raise ValueError("Không tìm thấy dialogue_id.")
        for dialogue in dialogues:
            with closing(open_storage(":memory:")) as connection:
                mode = dialogue["mode"]
                config.ORDER_PROVIDER = "local_demo" if mode == "local_demo" else original_provider
                if mode == "local_demo":
                    seed_database(connection)
                    repository = LocalCatalogRepository(":memory:").using_connection(connection)
                elif mode == "group_files":
                    from app.repositories.group_catalog import GroupCatalogRepository
                    repository = GroupCatalogRepository(config.GROUP_CATALOG_PATH)
                elif mode in {"empty", "mock"}:
                    repository = {"empty": EmptyCatalogRepository, "mock": MockCatalogRepository}[mode]()
                else:
                    raise ValueError("Mode không có adapter: " + mode)
                current = new_conversation()
                from app.order_flow import configure_order_fields
                capabilities = repository.get_capabilities()
                current["order"] = configure_order_fields(current["order"], capabilities.get("optional_order_fields", []), capabilities.get("disabled_order_fields", []))
                current["model"] = selected["model"]
                if engine == "fake":
                    # Metadata giả phải khớp cache provider, tránh gọi /api/tags.
                    current["llm_provider"] = "ollama"
                for item in dialogue["turns"]:
                    if limit is not None and len(report["steps"]) >= limit:
                        break
                    trace.clear()
                    if engine == "fake":
                        from app.schemas import LLMTurn
                        # Đây là injection nhãn để kiểm tra controller, không phải inference.
                        gold = LLMTurn.model_validate(item["label"])
                        def fake_extract(*args, **kwargs):
                            trace["proposal"] = gold.model_dump(exclude_none=True)
                            return {"data": gold, "error": None, "attempts": 0}
                        llm_client.extract_turn = fake_extract
                    else:
                        llm_client.extract_turn = traced_extract
                    previous = deepcopy(current["order"])
                    started = perf_counter()
                    result = handle_message(item["message"], repository, current, chat_mode=chat_mode, base_url=base_url,
                        model=selected["model"], timeout=timeout, storage_connection=connection,
                        order_tools=create_order_tools(repository, connection, current["id"]))
                    current = result["conversation"]
                    count = connection.execute("SELECT count(*) FROM orders WHERE conversation_id=?", (current["id"],)).fetchone()[0]
                    score = score_turn(item, result, trace.get("proposal"), previous, count)
                    row = {"id": item["id"], "dialogue_id": dialogue["id"], "mode": mode,
                        "label": item["label"], "proposal": trace.get("proposal"), "score": score,
                        "engine": result["engine"], "error": result["llm_error"],
                        "seconds": round(perf_counter() - started, 2)}
                    report["steps"].append(row)
                    print(item["id"], "logic" if engine == "fake" else engine,
                        "NLU", score["extraction_pass"], "behavior", score["behavior_pass"],
                        "error", result["llm_error"], flush=True)
            if limit is not None and len(report["steps"]) >= limit:
                break
        report["completed"] = True
    finally:
        llm_client.extract_turn = original_extract
        config.ORDER_PROVIDER = original_provider
        write_report()
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
    if target is not None:
        print("Report:", target, flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--engine", choices=["fake", "ollama"], default="ollama")
    parser.add_argument("--label", default="manual")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dialogue")
    parser.add_argument("--output", type=Path, help="Không ghi mặc định; chỉ cho phép runtime/*.json")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9_-]+", args.label) or (args.limit is not None and args.limit < 1):
        parser.error("label cần a-z/0-9/_/- và limit cần nguyên dương")
    report = evaluate(args.split, args.label, args.limit, args.output, args.engine, args.dialogue)
    passed = (report["completed"] and report["summary"]["behavior_exact"] == report["summary"]["samples"]
              and report["summary"]["extraction_exact"] == report["summary"]["samples"])
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
