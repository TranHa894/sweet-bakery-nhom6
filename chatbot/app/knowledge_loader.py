"""Biên nguồn tài liệu: đọc/validate JSON ở đây, logic chat chỉ gọi Protocol."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Protocol

from app.config import KNOWLEDGE_PATH
from app.schemas import KnowledgeResult, PolicyClause

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class KnowledgeRepository(Protocol):
    def get_knowledge(self) -> KnowledgeResult: ...


def load_knowledge(mode: str, path: str | Path | None = None) -> KnowledgeResult:
    """Empty không mở file; sample đọc lại mỗi lần để không dùng tài liệu cũ."""
    result: KnowledgeResult = {
        "status": "unconfigured", "knowledge_mode": mode, "is_mock": mode == "sample",
        "clauses": [], "corpus_sha256": None, "error": None,
    }
    if mode == "empty":
        return result
    if mode != "sample":
        raise ValueError("Nguồn kiến thức chỉ hỗ trợ empty/sample.")
    try:
        data_path = Path(path if path is not None else KNOWLEDGE_PATH)
        if not data_path.is_absolute():
            data_path = PROJECT_ROOT / data_path
        raw = data_path.read_bytes()
        document = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(document, dict) or document.get("schema_version") != "1.0" or document.get("is_mock") is not True:
            raise ValueError("Tài liệu sample cần schema_version và nhãn mock.")
        clauses = document.get("clauses")
        if not isinstance(clauses, list):
            raise ValueError("clauses phải là list.")
        seen = set()
        for clause in clauses:
            if not isinstance(clause, dict) or set(clause) != set(PolicyClause.__annotations__):
                raise ValueError("Điều khoản sai schema.")
            if clause["is_mock"] is not True:
                raise ValueError("Không dùng chính sách thật dưới mode sample.")
            for key in ("id", "title", "content", "version"):
                if not isinstance(clause[key], str) or not clause[key].strip():
                    raise ValueError("Trường văn bản cần có nội dung.")
            if len(clause["content"]) > 4000 or clause["id"] in seen:
                raise ValueError("Điều khoản quá dài hoặc ID trùng.")
            seen.add(clause["id"])
        result.update(
            status="success" if clauses else "no_results", clauses=deepcopy(clauses),
            corpus_sha256=hashlib.sha256(raw).hexdigest(),
        )
    except (OSError, ValueError, TypeError):
        result.update(status="error", error="invalid_knowledge_data")
    return result


class EmptyKnowledgeRepository:
    def get_knowledge(self) -> KnowledgeResult:
        return load_knowledge("empty")


class SampleKnowledgeRepository:
    def __init__(self, data_path: str | Path | None = None):
        self.data_path = data_path

    def get_knowledge(self) -> KnowledgeResult:
        return load_knowledge("sample", self.data_path)


def create_knowledge_repository(mode: str, path: str | Path | None = None) -> KnowledgeRepository:
    if mode == "empty":
        return EmptyKnowledgeRepository()
    if mode == "sample":
        return SampleKnowledgeRepository(path)
    if mode == "local_demo":
        return LocalKnowledgeRepository(path)
    raise ValueError("Nguồn kiến thức chỉ hỗ trợ empty/sample.")


class LocalKnowledgeRepository:
    def __init__(self, database_path=None):
        from app.config import DATABASE_PATH
        from app.repositories.local_catalog import LocalCatalogRepository
        self.catalog = LocalCatalogRepository(database_path if database_path is not None else DATABASE_PATH)

    def get_knowledge(self):
        return self.catalog.get_policy_documents()
