"""Cấu hình tối thiểu, đọc từ biến môi trường của tiến trình."""

import os

DATA_SOURCE = os.getenv("DATA_SOURCE", os.getenv("CATALOG_MODE", "local_demo")).strip().lower()
CATALOG_MODE = DATA_SOURCE
ORDER_PROVIDER = os.getenv("ORDER_PROVIDER", "local_demo").strip().lower()
TIMEZONE = os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh").strip()
CHAT_MODE = os.getenv("CHAT_MODE", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "").strip()
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
CONTEXT_MAX_TURNS = int(os.getenv("CONTEXT_MAX_TURNS", "6"))
KNOWLEDGE_MODE = os.getenv("KNOWLEDGE_MODE", "local_demo" if DATA_SOURCE == "local_demo" else "empty").strip().lower()
KNOWLEDGE_PATH = os.getenv("KNOWLEDGE_PATH", "data/sample_policies.json").strip()
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "3"))
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.15"))
DATABASE_PATH = os.getenv("DATABASE_PATH", os.getenv("CHATBOT_DB_PATH", "runtime/chatbot.sqlite3")).strip()
CHATBOT_DB_PATH = DATABASE_PATH

if CATALOG_MODE not in {"empty", "mock", "local_demo"}:
    raise ValueError("DATA_SOURCE/CATALOG_MODE phải là empty, mock hoặc local_demo.")
if ORDER_PROVIDER not in {"local_demo", "unsupported"}:
    raise ValueError("ORDER_PROVIDER phải là local_demo hoặc unsupported.")
if TIMEZONE != "Asia/Ho_Chi_Minh":
    raise ValueError("Demo hiện chỉ hỗ trợ TIMEZONE=Asia/Ho_Chi_Minh.")

if CHAT_MODE not in {"rule", "ollama"}:
    raise ValueError("CHAT_MODE phải là 'rule' hoặc 'ollama'.")

if not 0 < OLLAMA_TIMEOUT_SECONDS <= 60:
    raise ValueError("OLLAMA_TIMEOUT_SECONDS phải lớn hơn 0 và không quá 60.")

if not 1 <= CONTEXT_MAX_TURNS <= 20:
    raise ValueError("CONTEXT_MAX_TURNS phải từ 1 đến 20.")

if KNOWLEDGE_MODE not in {"empty", "sample", "local_demo"}:
    raise ValueError("KNOWLEDGE_MODE phải là empty, sample hoặc local_demo.")
if not 1 <= RETRIEVAL_TOP_K <= 3:
    raise ValueError("RETRIEVAL_TOP_K phải từ 1 đến 3.")
if not 0 < RETRIEVAL_MIN_SCORE <= 1:
    raise ValueError("RETRIEVAL_MIN_SCORE phải lớn hơn 0 và không quá 1.")
