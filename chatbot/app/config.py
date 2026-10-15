"""Cấu hình tối thiểu: biến môi trường ưu tiên hơn file .env riêng của chatbot."""

import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"


def parse_env_text(text: str) -> dict[str, str]:
    """Đọc KEY=value; hỗ trợ dòng trống, chú thích và dấu nháy, không chạy lệnh."""
    values = {}
    for line_number, line in enumerate(text.lstrip("\ufeff").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        name, separator, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f".env: dòng {line_number} phải có dạng KEY=value.")
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f".env: dấu nháy chưa đóng ở dòng {line_number}.")
            value = value[1:-1]
        values[name] = value
    return values


def load_local_env() -> None:
    """Chỉ nạp chatbot/.env, không tìm ở thư mục cha; không in giá trị cấu hình."""
    if ENV_FILE.is_symlink():
        raise ValueError(".env phải là file trong chatbot, không phải liên kết tới file khác.")
    try:
        text = ENV_FILE.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return
    except (OSError, UnicodeError):
        raise ValueError("Không đọc được chatbot/.env; kiểm tra quyền truy cập và UTF-8.") from None
    for name, value in parse_env_text(text).items():
        os.environ.setdefault(name, value)



load_local_env()
GROUP_PROJECT_ROOT = PROJECT_ROOT.parent
GROUP_CATALOG_PATH = Path(os.getenv("GROUP_CATALOG_PATH", "../static/products.json"))
if not GROUP_CATALOG_PATH.is_absolute():
    GROUP_CATALOG_PATH = PROJECT_ROOT / GROUP_CATALOG_PATH
GROUP_CATALOG_PATH = GROUP_CATALOG_PATH.resolve()

DATA_SOURCE = os.getenv("DATA_SOURCE", os.getenv("CATALOG_MODE", "group_files")).strip().lower()
CATALOG_MODE = DATA_SOURCE
ORDER_PROVIDER = os.getenv("ORDER_PROVIDER", "local_demo").strip().lower()
TIMEZONE = os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh").strip()
CHAT_MODE = os.getenv("CHAT_MODE", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "").strip()
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))

def get_llm_settings(chat_mode=None):
    """Endpoint/model/timeout local dùng chung CLI, API và script."""
    return OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS


CONTEXT_MAX_TURNS = int(os.getenv("CONTEXT_MAX_TURNS", "6"))
KNOWLEDGE_MODE = os.getenv("KNOWLEDGE_MODE", "local_demo" if DATA_SOURCE == "local_demo" else "empty").strip().lower()
KNOWLEDGE_PATH = os.getenv("KNOWLEDGE_PATH", "data/sample_policies.json").strip()
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "3"))
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.15"))
DATABASE_PATH = os.getenv("DATABASE_PATH", os.getenv("CHATBOT_DB_PATH", "runtime/chatbot.sqlite3")).strip()
CHATBOT_DB_PATH = DATABASE_PATH
CHAT_DEBUG = os.getenv("CHAT_DEBUG", "false").strip().lower() == "true"
RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "keyword").strip().lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "").strip()
VECTOR_INDEX_PATH = os.getenv("VECTOR_INDEX_PATH", "runtime/policy_vectors.json").strip()
VECTOR_MIN_SCORE = float(os.getenv("VECTOR_MIN_SCORE", "0.5"))
if RETRIEVAL_MODE not in {"keyword", "vector"}:
    raise ValueError("RETRIEVAL_MODE phải là keyword hoặc vector.")
if not 0 < VECTOR_MIN_SCORE <= 1:
    raise ValueError("VECTOR_MIN_SCORE cần >0 và <=1.")

if CATALOG_MODE == "backend" or ORDER_PROVIDER == "backend":
    raise ValueError("Backend chưa có adapter/cấu hình API. Chưa thể truy cập menu hoặc tạo đơn thật; không tự dùng demo.")
if CATALOG_MODE not in {"empty", "mock", "local_demo", "group_files"}:
    raise ValueError("DATA_SOURCE/CATALOG_MODE phải là empty, mock, local_demo hoặc group_files.")
if ORDER_PROVIDER not in {"local_demo", "unsupported"}:
    raise ValueError("ORDER_PROVIDER phải là local_demo hoặc unsupported.")
if TIMEZONE != "Asia/Ho_Chi_Minh":
    raise ValueError("Demo hiện chỉ hỗ trợ TIMEZONE=Asia/Ho_Chi_Minh.")

if CHAT_MODE not in {"rule", "ollama"}:
    raise ValueError("CHAT_MODE phải là rule hoặc ollama.")


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
