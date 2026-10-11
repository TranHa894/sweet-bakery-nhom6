"""So sánh hai lần đo cùng development, không bỏ lượt model lỗi."""

import json
from pathlib import Path
from scripts.evaluate_intent_context import summarize

ROOT = Path(__file__).resolve().parents[1]


def compare(before, after):
    if not before["completed"] or not after["completed"]:
        raise ValueError("Cần hai lần đo hoàn tất")
    if before["split"] != after["split"] or before["dataset_sha256"] != after["dataset_sha256"]:
        raise ValueError("Không so sánh khi split/nhãn khác nhau; cần rescore minh bạch")
    if [s["id"] for s in before["steps"]] != [s["id"] for s in after["steps"]]:
        raise ValueError("Phải đo đúng cùng mẫu, không loại mẫu lỗi")
    first, second = summarize(before["steps"]), summarize(after["steps"])
    metrics = {}
    for name in sorted(set(first["metrics"]) | set(second["metrics"])):
        metrics[name] = {"before":first["metrics"].get(name),"after":second["metrics"].get(name)}
    return {"scope":"Combined prompt/schema/controller change, not isolated prompt effect",
            "samples":first["samples"],"split":before["split"],"dataset_sha256":before["dataset_sha256"],
            "intent_micro_f1":{"before":first["intent_micro_f1"],"after":second["intent_micro_f1"]},
            "extraction_exact":{"before":first["extraction_exact"],"after":second["extraction_exact"]},
            "behavior_exact":{"before":first["behavior_exact"],"after":second["behavior_exact"]},
            "model_errors":{"before":first["model_errors"],"after":second["model_errors"]},
            "metrics":metrics}


def main():
    folder = ROOT / "evaluation"
    before = json.loads((folder / "intent_context_before_dev_report.json").read_text(encoding="utf-8"))
    after = json.loads((folder / "intent_context_after_dev_report.json").read_text(encoding="utf-8"))
    report = compare(before,after)
    path = folder / "intent_context_comparison_report.json"
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in {"metrics","dataset_sha256"}},ensure_ascii=False))
    print(path)


if __name__ == "__main__":
    main()
