"""Retriever từ khóa và phản hồi trích dẫn; không biết đường dẫn JSON nguồn."""

from collections import Counter
from copy import deepcopy
import math
import re
import json
import logging
from pathlib import Path

from app.config import (RETRIEVAL_MIN_SCORE, RETRIEVAL_TOP_K, RETRIEVAL_MODE,
    EMBEDDING_MODEL, VECTOR_INDEX_PATH, VECTOR_MIN_SCORE, OLLAMA_BASE_URL, OLLAMA_TIMEOUT_SECONDS)
from app.knowledge_loader import KnowledgeRepository
from app.schemas import KnowledgeResult, PolicyResponse, RAGAnswer, RetrievalResult
from app.text_utils import normalize_text

RETRIEVER_VERSION = "keyword-v1"
VECTOR_VERSION = "cosine-policy-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)
# Từ chức năng phổ thông, không chứa nội dung/giá trị của điều khoản.
STOP_WORDS = set("a ai anh ban banh bao cac cai can cho co cua da day de den dieu do duoc e em gi gioi han hay hoi khi khong la lai lam loai lieu minh mo mot nao nay nhu nhung o phai phong se tai the thi toi trong tu va ve voi xin chinh sach hang".split())
# Đồng nghĩa ngôn ngữ, không phải chính sách cửa hàng.
QUERY_ALIASES = {"ship": "giao hang", "shipping": "giao hang", "refund": "doi tra", "payment": "thanh toan"}
# Bỏ dấu làm "quản/quan", "dùng/dụng" giống nhau. Chỉ dùng các âm tiết
# quá chung này khi đi cùng âm tiết liền kề: bảo_quản, áp_dụng, sử_dụng...
WEAK_WORDS = {"quan", "dung", "su", "lien"}
PHRASE_WORDS = WEAK_WORDS | {"bao", "tai", "tu", "can"}


def tokenize(text: str) -> set[str]:
    normalized = normalize_text(text)
    for term, replacement in QUERY_ALIASES.items():
        normalized = re.sub(r"\b" + re.escape(term) + r"\b", replacement, normalized)
    words = re.findall(r"\w+", normalized)
    terms = {word for word in words if len(word) > 1 and word not in STOP_WORDS | WEAK_WORDS and not word.isdigit()}
    for left, right in zip(words, words[1:]):
        if not ({left, right} & PHRASE_WORDS):
            continue
        if all(len(word) > 1 and not word.isdigit() and (word not in STOP_WORDS or word in PHRASE_WORDS) for word in (left, right)):
            terms.add(left + "_" + right)
    return terms


def build_keyword_index(knowledge: KnowledgeResult) -> dict:
    """Mỗi điều khoản là một chunk; index RAM gắn hash nội dung + phiên bản."""
    documents = []
    frequency = Counter()
    for clause in knowledge["clauses"]:
        title_terms = tokenize(clause["title"])
        terms = title_terms | tokenize(clause["content"])
        documents.append({"clause": deepcopy(clause), "terms": terms, "title_terms": title_terms})
        frequency.update(terms)
    count = len(documents)
    return {
        "documents": documents,
        "idf": {term: math.log((count + 1) / (freq + 1)) + 1 for term, freq in frequency.items()},
        "unknown_idf": math.log(count + 1) + 1,
        "corpus_sha256": knowledge["corpus_sha256"], "retriever_version": RETRIEVER_VERSION,
    }


def retrieve(
    question: str, repository: KnowledgeRepository | None = None,
    top_k: int = RETRIEVAL_TOP_K, min_score: float = RETRIEVAL_MIN_SCORE,
) -> RetrievalResult:
    """Đọc qua interface, tái sử dụng index theo hash, xếp hạng tối đa 3 điều khoản."""
    if type(top_k) is not int or not 1 <= top_k <= 3 or not 0 < min_score <= 1:
        raise ValueError("top_k cần 1–3; min_score cần >0 và <=1.")
    knowledge: KnowledgeResult = {
        "status": "unconfigured", "knowledge_mode": "empty", "is_mock": False,
        "clauses": [], "corpus_sha256": None, "error": None,
    }
    if repository is not None:
        try:
            knowledge = repository.get_knowledge()
        except Exception:
            knowledge.update(status="error", knowledge_mode="unknown", error="knowledge_source_error")
    result: RetrievalResult = {
        "status": knowledge["status"], "knowledge_mode": knowledge["knowledge_mode"],
        "is_mock": knowledge["is_mock"], "chunks": [], "corpus_sha256": knowledge["corpus_sha256"],
        "retriever_version": RETRIEVER_VERSION, "error": knowledge["error"],
    }
    if knowledge["status"] != "success":
        return result
    if RETRIEVAL_MODE == "vector":
        vector_result, vector_error = retrieve_vector(question, repository, knowledge, result, top_k)
        if vector_result is not None:
            return vector_result
        # Báo rõ dự phòng; không gọi keyword là vector. Không log câu hỏi/liên hệ.
        logger.warning("Vector RAG unavailable (%s); using keyword-v1", vector_error)
        result["fallback_reason"] = vector_error
    index = getattr(repository, "_keyword_index", None)
    if index is None or index["corpus_sha256"] != knowledge["corpus_sha256"]:
        index = build_keyword_index(knowledge)
        if repository is not None:
            repository._keyword_index = index
    query_terms = tokenize(question)
    denominator = sum(index["idf"].get(term, index["unknown_idf"]) for term in query_terms)
    ranked = []
    for document in index["documents"]:
        overlap = query_terms & document["terms"]
        score = sum(index["idf"][term] * (2 if term in document["title_terms"] else 1) for term in overlap)
        score = score / denominator if denominator else 0
        if overlap and score >= min_score:
            clause = document["clause"]
            ranked.append({
                "source_id": clause["id"], "title": clause["title"], "content": clause["content"],
                "version": clause["version"], "is_mock": clause["is_mock"], "score": round(score, 6),
            })
    result["chunks"] = sorted(ranked, key=lambda chunk: (-chunk["score"], chunk["source_id"]))[:top_k]
    result["status"] = "success" if result["chunks"] else "no_results"
    return result


def index_path(path=VECTOR_INDEX_PATH) -> Path:
    """Chỉ mục chỉ ghi vào runtime của chatbot, không chấp nhận path ngoài dự án."""
    target = Path(path)
    target = (target if target.is_absolute() else PROJECT_ROOT / target).resolve()
    if not target.is_relative_to(PROJECT_ROOT / "runtime") or target.suffix != ".json":
        raise ValueError("Vector index phải là file .json bên trong runtime của chatbot.")
    return target


def embedding_identity(base_url=OLLAMA_BASE_URL, model=EMBEDDING_MODEL) -> dict:
    from app.llm_client import request_json
    if not model:
        raise ValueError("embedding_model_not_configured")
    tags = request_json(base_url, "/api/tags", timeout=5)
    if not tags["ok"]:
        raise ValueError(tags["error"])
    entry = next((m for m in tags["data"].get("models", []) if m.get("name") == model), None)
    if entry is None or entry.get("remote_host") or entry.get("remote_model"):
        raise ValueError("embedding_model_not_installed_locally")
    if "embedding" not in entry.get("capabilities", []):
        # /api/tags của một số phiên bản chưa có capabilities: kiểm qua /api/show.
        shown = request_json(base_url, "/api/show", {"model": model}, timeout=5)
        if not shown["ok"] or "embedding" not in shown["data"].get("capabilities", []):
            raise ValueError("model_has_no_embedding_capability")
    if not entry.get("digest"):
        raise ValueError("embedding_digest_missing")
    return {"model": model, "digest": entry["digest"]}


def build_vector_index(repository, *, path=VECTOR_INDEX_PATH, model=EMBEDDING_MODEL,
                       base_url=OLLAMA_BASE_URL, force=False) -> dict:
    """Lệnh tường minh: mỗi điều khoản một vector; corpus/model/version xác định cache."""
    from app.llm_client import embed_texts
    knowledge = repository.get_knowledge()
    if knowledge["status"] != "success":
        raise ValueError("no_policy_documents")
    identity = embedding_identity(base_url, model)
    target = index_path(path)
    metadata = {"version": VECTOR_VERSION, "corpus_sha256": knowledge["corpus_sha256"], **identity}
    if target.exists() and not force:
        stored = json.loads(target.read_text(encoding="utf-8"))
        if stored.get("metadata") == metadata:
            validate_vector_index(stored, knowledge)
            return {"status": "reused", "chunks": len(stored["documents"]), **metadata}
    clauses = knowledge["clauses"]
    embedded = embed_texts([c["title"] + "\n" + c["content"] for c in clauses], base_url, model, OLLAMA_TIMEOUT_SECONDS)
    if embedded["error"]:
        raise ValueError(embedded["error"])
    document = {"metadata": metadata, "documents": [
        {"source_id": c["id"], "version": c["version"], "vector": v}
        for c, v in zip(clauses, embedded["vectors"])]}
    validate_vector_index(document, knowledge)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    temporary.replace(target)
    return {"status": "built", "chunks": len(clauses), **metadata}


def validate_vector_index(index, knowledge) -> None:
    documents = index["documents"]
    clauses = {(c["id"], c["version"]) for c in knowledge["clauses"]}
    if len(documents) != len(clauses) or {(d["source_id"], d["version"]) for d in documents} != clauses:
        raise ValueError("invalid_vector_sources")
    dimension = len(documents[0]["vector"]) if documents else 0
    if not dimension or not all(isinstance(d["vector"], list) and len(d["vector"]) == dimension
        and all(type(v) in {int, float} and math.isfinite(v) for v in d["vector"]) and any(d["vector"])
        for d in documents):
        raise ValueError("invalid_vector_index")


def cosine_similarity(left, right) -> float:
    if len(left) != len(right):
        raise ValueError("embedding_dimension_changed")
    divisor = math.sqrt(sum(x*x for x in left) * sum(x*x for x in right))
    if not divisor:
        raise ValueError("zero_embedding")
    return sum(x*y for x, y in zip(left, right)) / divisor


def retrieve_vector(question, repository, knowledge, result, top_k):
    """Không xây lại corpus trong request; thiếu/cũ/lỗi -> keyword có lý do rõ ràng."""
    from app.llm_client import embed_texts
    try:
        target = index_path()
        stat = target.stat()
        key = (str(target), stat.st_mtime_ns, stat.st_size, knowledge["corpus_sha256"], EMBEDDING_MODEL)
        cached = getattr(repository, "_vector_index", None)
        if cached is None or cached["key"] != key:
            identity = embedding_identity()
            index = json.loads(target.read_text(encoding="utf-8"))
            if index["metadata"] != {"version": VECTOR_VERSION, "corpus_sha256": knowledge["corpus_sha256"], **identity}:
                raise ValueError("vector_index_stale_build_again")
            validate_vector_index(index, knowledge)
            cached = {"key": key, "index": index}
            repository._vector_index = cached
        embedded = embed_texts([question], OLLAMA_BASE_URL, EMBEDDING_MODEL, OLLAMA_TIMEOUT_SECONDS)
        if embedded["error"]:
            raise ValueError(embedded["error"])
        clauses = {c["id"]: c for c in knowledge["clauses"]}
        ranked = []
        for document in cached["index"]["documents"]:
            score = cosine_similarity(embedded["vectors"][0], document["vector"])
            if score >= VECTOR_MIN_SCORE:
                clause = clauses[document["source_id"]]
                ranked.append({"source_id": clause["id"], "version": clause["version"],
                    "title": clause["title"], "content": clause["content"], "is_mock": clause["is_mock"], "score": round(score, 6)})
        answer = deepcopy(result)
        answer.update(retriever_version=VECTOR_VERSION, chunks=sorted(ranked, key=lambda c: (-c["score"], c["source_id"]))[:top_k])
        answer["status"] = "success" if answer["chunks"] else "no_results"
        return answer, None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None, "vector_index_or_model_unavailable"


def validate_rag_answer(answer: RAGAnswer, retrieval: RetrievalResult) -> str | None:
    """Nguồn phải trong top chunks, quote phải nguyên văn; chưa chứng minh đúng ý."""
    if answer.supported != bool(answer.quotes):
        return "invalid_rag_structure"
    sources = {chunk["source_id"]: chunk for chunk in retrieval["chunks"]}
    for citation in answer.quotes:
        if citation.source_id not in sources:
            return "invalid_rag_source"
        if not citation.quote.strip() or citation.quote not in sources[citation.source_id]["content"]:
            return "invalid_rag_quote"
    return None


def make_policy_response(
    retrieval: RetrievalResult, answer: RAGAnswer | None = None,
    *, engine: str = "rule", llm_error: str | None = None, attempts: int = 0,
) -> PolicyResponse:
    """Rule hiển thị điều khoản liên quan; LLM chỉ chọn đoạn để code trích dẫn."""
    if answer is not None:
        validation_error = validate_rag_answer(answer, retrieval)
        if validation_error:
            answer, engine, llm_error = None, "rule_fallback", validation_error
    label = f"[Kiến thức: {retrieval['knowledge_mode']}]"
    if retrieval["is_mock"]:
        label += " [ĐIỀU KHOẢN MÔ PHỎNG — không áp dụng cho đơn thật]"
    response: PolicyResponse = {
        "text": "", "knowledge_mode": retrieval["knowledge_mode"], "is_mock": retrieval["is_mock"],
        "status": retrieval["status"], "source_ids": [], "citations": [], "retrieval": retrieval,
        "engine": "not_used" if retrieval["status"] != "success" else engine,
        "error": retrieval["error"], "llm_error": llm_error, "attempts": attempts,
    }
    if retrieval["status"] == "unconfigured":
        body = "Chưa có tài liệu chính sách để đối chiếu; mình chưa đủ thông tin để trả lời. Không dùng điều khoản mẫu khi KNOWLEDGE_MODE=empty."
    elif retrieval["status"] == "error":
        body = "Không đọc được nguồn chính sách; chưa đủ thông tin để xác nhận câu trả lời. Hãy kiểm tra nguồn tài liệu."
    elif retrieval["status"] == "no_results":
        body = "Chưa đủ thông tin để trả lời: không tìm thấy điều khoản liên quan trong nguồn đang chọn."
    elif answer is not None and not answer.supported:
        response["status"] = "insufficient"
        body = "Các đoạn truy xuất chưa đủ thông tin để trả lời câu hỏi này; mình chưa thể xác nhận nội dung bạn hỏi."
    else:
        response["status"] = "answered"
        chunks = {chunk["source_id"]: chunk for chunk in retrieval["chunks"]}
        quotes = answer.quotes if answer is not None else []
        selected = [(quote.source_id, quote.quote) for quote in quotes] if answer is not None else [(chunk["source_id"], chunk["content"]) for chunk in retrieval["chunks"]]
        lines = ["Trích đoạn tài liệu liên quan để đối chiếu (không phải xác nhận đơn):"]
        for source_id, quote in selected:
            chunk = chunks[source_id]
            response["citations"].append({"source_id": source_id, "version": chunk["version"], "quote": quote})
            if source_id not in response["source_ids"]:
                response["source_ids"].append(source_id)
            lines.extend([f"Nguồn [{source_id}] — {chunk['title']} — phiên bản {chunk['version']}:", "> " + quote.replace("\n", "\n> ")])
        body = "\n".join(lines)
    response["text"] = label + "\n" + body
    if llm_error:
        response["text"] += f"\n[RAG dùng trích đoạn từ code vì model lỗi: {llm_error}.]"
    return response
