"""Thử HTTP Qwen thật trên ba câu mô phỏng; không tải model, không tạo đơn."""

from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS
from app.conversation import handle_message, new_conversation
from app.knowledge_loader import EmptyKnowledgeRepository, SampleKnowledgeRepository
from app.llm_client import select_model
from app.repositories.empty_catalog import EmptyCatalogRepository

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    selected = select_model(OLLAMA_BASE_URL, OLLAMA_MODEL, 5)
    cases = [
        ("empty", "Chính sách giao hàng là gì?", "unconfigured", []),
        ("sample", "Phí giao hàng mô phỏng là bao nhiêu?", "answered", ["sample-policy-001"]),
        ("sample", "Có giao hàng quốc tế không?", "insufficient", []),
    ]
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "is_mock": True,
        "test_type": "live_ollama_smoke", "model": selected["model"],
        "selection_error": selected["error"], "timeout_seconds": OLLAMA_TIMEOUT_SECONDS,
        "cases": [],
    }
    for mode, question, expected_status, expected_ids in cases:
        repo = EmptyKnowledgeRepository() if mode == "empty" else SampleKnowledgeRepository()
        start = perf_counter()
        turn = handle_message(
            question, EmptyCatalogRepository(), new_conversation(), chat_mode="ollama",
            base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL, timeout=OLLAMA_TIMEOUT_SECONDS,
            knowledge_repository=repo,
        )
        policy = turn["response"]["policy"]
        checks = {
            "status": policy["status"] == expected_status,
            "sources": policy["source_ids"] == expected_ids,
            "no_products": turn["response"]["products"] == [],
            "mock_label": mode == "empty" or "MÔ PHỎNG" in policy["text"],
            "fee_quote": mode != "sample" or expected_status != "answered" or "25.000 đồng" in policy["text"],
        }
        row = {
            "question": question, "knowledge_mode": mode, "elapsed_seconds": round(perf_counter() - start, 2),
            "engine": policy["engine"], "status": policy["status"], "attempts": policy["attempts"],
            "llm_error": policy["llm_error"], "source_ids": policy["source_ids"],
            "corpus_sha256": policy["retrieval"]["corpus_sha256"], "text": policy["text"],
            "checks": checks, "behavior_checks_passed": all(checks.values()),
        }
        report["cases"].append(row)
        print(json.dumps({key: value for key, value in row.items() if key != "text"}, ensure_ascii=False), flush=True)
    output = ROOT / "evaluation/rag_smoke_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Báo cáo: {output}; kiểm tra hành vi không chứng minh toàn bộ ý nghĩa đúng.")
    if not all(row["behavior_checks_passed"] for row in report["cases"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
