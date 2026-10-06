"""pytest luôn offline. Smoke model thật là script riêng, không chạy trong suite."""

from pathlib import Path
from uuid import uuid4

import pytest

from app import llm_client
from app.schemas import LLMTurn


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Đặt thư mục tạm trước khi pytest tạo tmp_path_factory trên Windows."""
    # --basetemp do người chạy chỉ định vẫn có ưu tiên như pytest thông thường.
    if config.getoption("basetemp") is not None:
        return
    temp_root = Path(__file__).resolve().parents[1] / ".pytest_tmp"
    temp_root.mkdir(exist_ok=True)
    # pytest có thể xóa basetemp trước khi dùng: chọn tên mới cho mỗi lần chạy,
    # không dùng chung .pytest_tmp, runtime hoặc database demo làm basetemp.
    config.option.basetemp = str(temp_root / ("run-" + uuid4().hex))


@pytest.fixture(autouse=True)
def block_real_ollama(monkeypatch, tmp_path):
    def blocked(*args, **kwargs):
        raise AssertionError("Test logic không được gọi Ollama thật; hãy truyền model fake.")
    monkeypatch.setattr(llm_client, "urlopen", blocked)
    # Các subprocess CLI cũ cũng phải dùng DB riêng, không chạm runtime đang demo.
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("DATA_SOURCE", raising=False)
    monkeypatch.setenv("CHATBOT_DB_PATH", str(tmp_path / "isolated_cli.sqlite3"))


@pytest.fixture
def make_turn():
    def factory(**changes):
        data = {"intents": ["recommendation"], "action": "none", "product_mentions": [],
                "reference": "none", "updates": {}, "clear_slots": [], "ambiguous": False,
                "handoff_reason": "none", "order_update": False}
        return LLMTurn(**{**data, **changes})
    return factory


@pytest.fixture
def fake_model(monkeypatch):
    def install(proposals):
        values = iter(proposals)
        seen = []
        monkeypatch.setattr(llm_client, "select_model", lambda *args: {"model": "qwen-fake", "error": None})
        def extract(message, conversation, *args):
            seen.append((message, conversation))
            value = next(values)
            return {"data": value, "error": None, "attempts": 1} if isinstance(value, LLMTurn) else value
        monkeypatch.setattr(llm_client, "extract_turn", extract)
        return seen
    return install
