"""Đo retrieval thật trên development set; không gọi LLM hoặc tải model."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter

from app.config import RETRIEVAL_MIN_SCORE, RETRIEVAL_TOP_K
from app.knowledge_loader import KnowledgeRepository, SampleKnowledgeRepository
from app.retrieval import RETRIEVER_VERSION, retrieve

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def evaluate(dataset: dict, repository: KnowledgeRepository, top_k: int = 3, min_score: float = 0.15) -> dict:
    """Gold nguồn chỉ dùng để chấm, không đưa vào retriever khi chạy câu hỏi."""
    knowledge = repository.get_knowledge()
    if knowledge["status"] != "success":
        raise ValueError("Cần nguồn điều khoản hợp lệ để đo retrieval.")
    if dataset.get("schema_version") != "1.0" or dataset.get("is_mock") is not True:
        raise ValueError("Development set cần schema_version và nhãn mô phỏng.")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Development set cần cases không rỗng.")
    valid_ids = {clause["id"] for clause in knowledge["clauses"]}
    seen = set()
    rows = []
    for case in cases:
        if set(case) != {"id", "question", "answerable", "expected_source_ids"}:
            raise ValueError("Case sai schema.")
        if not isinstance(case["id"], str) or not case["id"] or case["id"] in seen or not isinstance(case["question"], str) or not case["question"].strip():
            raise ValueError("ID/question thiếu hoặc trùng.")
        seen.add(case["id"])
        gold = case["expected_source_ids"]
        if not isinstance(gold, list) or any(not isinstance(value, str) for value in gold) or not set(gold) <= valid_ids or len(gold) != len(set(gold)):
            raise ValueError("Nguồn chuẩn không hợp lệ; cập nhật gold khi đổi corpus.")
        if type(case["answerable"]) is not bool or case["answerable"] != bool(gold):
            raise ValueError("answerable phải khớp danh sách nguồn chuẩn.")
        start = perf_counter()
        result = retrieve(case["question"], repository, top_k, min_score)
        elapsed = (perf_counter() - start) * 1000
        if result["status"] not in {"success", "no_results"} or result["corpus_sha256"] != knowledge["corpus_sha256"]:
            raise ValueError("Nguồn lỗi/thay đổi giữa lần đo; chạy lại với bộ dữ liệu nhất quán.")
        retrieved = [chunk["source_id"] for chunk in result["chunks"]]
        hit_ranks = [rank for rank, source_id in enumerate(retrieved, 1) if source_id in gold]
        rows.append({
            **case, "retrieved_source_ids": retrieved, "scores": [chunk["score"] for chunk in result["chunks"]],
            "recall": len(set(retrieved) & set(gold)) / len(gold) if gold else None,
            "reciprocal_rank": 1 / hit_ranks[0] if hit_ranks else 0,
            "exact_source_set": set(retrieved) == set(gold), "elapsed_ms": round(elapsed, 3),
        })
    positives = [row for row in rows if row["answerable"]]
    negatives = [row for row in rows if not row["answerable"]]
    def mean(values):
        return round(sum(values) / len(values), 6) if values else None
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "retriever_version": RETRIEVER_VERSION, "corpus_sha256": knowledge["corpus_sha256"],
        "top_k": top_k, "min_score": min_score,
        "counts": {"total": len(rows), "answerable": len(positives), "unanswerable": len(negatives)},
        "metrics": {
            "recall_at_k": mean([row["recall"] for row in positives]),
            "hit_at_1": mean([float(bool(row["retrieved_source_ids"]) and row["retrieved_source_ids"][0] in row["expected_source_ids"]) for row in positives]),
            "mrr_at_k": mean([row["reciprocal_rank"] for row in positives]),
            "unanswerable_abstention_rate": mean([float(not row["retrieved_source_ids"]) for row in negatives]),
            "exact_source_set_accuracy": mean([float(row["exact_source_set"]) for row in rows]),
            "mean_elapsed_ms": mean([row["elapsed_ms"] for row in rows]),
        },
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "evaluation/retrieval_dev.json")
    parser.add_argument("--policies", type=Path, default=PROJECT_ROOT / "data/sample_policies.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "evaluation/retrieval_report.json")
    parser.add_argument("--top-k", type=int, default=RETRIEVAL_TOP_K)
    parser.add_argument("--min-score", type=float, default=RETRIEVAL_MIN_SCORE)
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    report = evaluate(json.loads(raw.decode("utf-8")), SampleKnowledgeRepository(args.policies), args.top_k, args.min_score)
    report["dataset_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": report["counts"], "metrics": report["metrics"], "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
