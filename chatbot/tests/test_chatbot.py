"""Kiểm tra hành vi nghiệp vụ, hội thoại và CLI với hai nguồn."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.chatbot import create_state, respond
from app.repositories.empty_catalog import EmptyCatalogRepository
from app.repositories.mock_catalog import MockCatalogRepository


def test_socola_under_300k_returns_only_matching_mock_variant():
    result = respond("socola dưới 300k", MockCatalogRepository())
    assert result["catalog_status"] == "success" and result["is_mock"]
    assert "DỮ LIỆU MẪU" in result["text"] and "250.000 đ" in result["text"]
    assert len(result["products"]) == 1 and len(result["products"][0]["variants"]) == 1
    assert "350.000 đ" not in result["text"]


def test_price_and_size_are_answered_together():
    result = respond("giá và size bánh socola", MockCatalogRepository())
    assert {"price", "size"} <= set(result["intents"])
    assert "16 cm" in result["text"] and "20 cm" in result["text"]
    assert "250.000 đ" in result["text"] and "350.000 đ" in result["text"]


def test_unknown_price_stock_and_servings_are_not_invented():
    result = respond("giá và size bánh tart chanh còn hàng không", MockCatalogRepository())
    assert "chưa có giá" in result["text"]
    assert "chưa biết số người ăn" in result["text"]
    assert "chưa biết tình trạng còn hàng" in result["text"]
    assert result["products"][0]["variants"][0]["price_vnd"] is None


def test_empty_and_no_results_are_distinct():
    empty = respond("socola dưới 300k", EmptyCatalogRepository())
    missing = respond("giá bánh sầu riêng", MockCatalogRepository())
    assert empty["catalog_status"] == "unconfigured" and empty["products"] == []
    assert "Chưa có menu để đối chiếu" in empty["text"]
    assert missing["catalog_status"] == "no_results"
    assert "Nguồn hoạt động" in missing["text"]


def test_empty_mode_remembers_preferences_in_ram():
    repo = EmptyCatalogRepository()
    first = respond("socola", repo)
    second = respond("dưới 300k cho 6 người, 2 bánh", repo, first["state"])
    assert second["state"]["filters"]["flavor"] == "socola"
    assert second["state"]["filters"]["max_price_vnd"] == 300000
    assert second["state"]["filters"]["servings"] == 6 and second["state"]["quantity"] == 2
    assert second["products"] == [] and "chưa đủ thông tin" in second["text"]
    assert first["state"]["filters"] == {"flavor": "socola"}


def test_mock_followup_uses_previous_product_but_new_product_resets_filters():
    repo = MockCatalogRepository()
    first = respond("socola dưới 300k", repo)
    second = respond("size 16cm", repo, first["state"])
    assert second["products"][0]["id"] == "mock-001"
    third = respond("giá bánh dâu", repo, second["state"])
    assert third["products"][0]["id"] == "mock-002"
    assert "max_price_vnd" not in third["state"]["filters"]


def test_ambiguity_does_not_change_state_or_choose_products():
    state = create_state()
    result = respond("socola 300k và dâu 200k", MockCatalogRepository(), state)
    assert result["requires_clarification"] and result["products"] == []
    assert result["state"] == state


def test_policy_and_order_never_invent_policy_or_create_order():
    result = respond("đặt 2 bánh socola và hỏi chính sách giao hàng", MockCatalogRepository())
    assert {"policy", "order_request"} <= set(result["intents"])
    assert "Chưa có tài liệu chính sách" in result["text"]
    assert "chưa tạo hoặc xác nhận đơn" in result["text"]
    assert result["state"]["quantity"] == 2
    assert not MockCatalogRepository().get_capabilities()["can_accept_real_orders"]


def test_policy_only_does_not_list_products():
    result = respond("chính sách giao hàng", MockCatalogRepository())
    assert result["products"] == [] and "Chưa có tài liệu" in result["text"]


def test_policy_price_does_not_become_cake_price_even_after_product_question():
    repo = MockCatalogRepository()
    first = respond("giá bánh socola", repo)
    result = respond("giá giao hàng bao nhiêu", repo, first["state"])
    assert result["products"] == [] and "Chưa có tài liệu" in result["text"]
    assert "250.000 đ" not in result["text"]


@pytest.mark.parametrize("message", ["Xin chào", "abcdef", "giá bánh dâu", "chính sách giao hàng"])
def test_every_response_has_data_mode_and_mock_label(message):
    for repo in (EmptyCatalogRepository(), MockCatalogRepository()):
        result = respond(message, repo)
        mode = repo.get_capabilities()["data_mode"]
        assert f"[Nguồn: {mode}]" in result["text"] and result["data_mode"] == mode
        if mode == "mock":
            assert "DỮ LIỆU MẪU" in result["text"]


def test_source_exception_does_not_become_no_results_or_leak_details(monkeypatch):
    repo = MockCatalogRepository()
    def fail(filters):
        raise RuntimeError("private-source-details")
    monkeypatch.setattr(repo, "search_products", fail)
    result = respond("giá bánh socola", repo)
    assert result["catalog_status"] == "error"
    assert "Không truy vấn được" in result["text"] and "private-source-details" not in result["text"]


def test_capability_error_has_unknown_mode(monkeypatch):
    repo = MockCatalogRepository()
    def fail():
        raise RuntimeError("private-source-details")
    monkeypatch.setattr(repo, "get_capabilities", fail)
    result = respond("xin chào", repo)
    assert result["catalog_status"] == "error" and result["data_mode"] == "unknown"


@pytest.mark.parametrize("mode", ["empty", "mock"])
def test_terminal_modes_and_reset(mode, tmp_path):
    env = os.environ.copy()
    env.update(CATALOG_MODE=mode, CHAT_MODE="rule", CHATBOT_DB_PATH=str(tmp_path / "cli.sqlite3"))
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "main.py"], cwd=root, env=env,
        input="socola dưới 300k\nmới\ngiá và size bánh socola\nthoát\n",
        text=True, encoding="utf-8", capture_output=True, timeout=10,
    )
    assert result.returncode == 0 and f"[Nguồn: {mode}]" in result.stdout
    assert "Đã bỏ nhu cầu cũ" in result.stdout and "Tạm biệt" in result.stdout
    if mode == "mock":
        assert "250.000 đ" in result.stdout and "350.000 đ" in result.stdout
    else:
        assert "Chưa có menu" in result.stdout


def test_import_has_no_terminal_side_effect_and_eof_exits():
    env = os.environ.copy()
    env.update(CATALOG_MODE="empty", CHAT_MODE="rule")
    imported = subprocess.run([sys.executable, "-c", "import main"], env=env, text=True, capture_output=True, timeout=10)
    assert imported.returncode == 0 and imported.stdout == ""
    ended = subprocess.run([sys.executable, "-X", "utf8", "main.py"], env=env, input="", text=True, encoding="utf-8", capture_output=True, timeout=10)
    assert ended.returncode == 0 and "Kết thúc phiên" in ended.stdout


def test_main_preserves_original_input_for_nlu(monkeypatch, capsys, tmp_path):
    import main
    from app.conversation import handle_message
    inputs = iter(["  Xin CHÀO  ", "thoát"])
    seen = []
    def record(message, repository, conversation, **kwargs):
        result = handle_message(message, repository, conversation, **kwargs)
        seen.append(result["response"]["nlu"]["raw_text"])
        return result
    monkeypatch.setattr(main, "CATALOG_MODE", "empty")
    monkeypatch.setattr(main, "CHAT_MODE", "rule")
    monkeypatch.setattr(main, "CHATBOT_DB_PATH", str(tmp_path / "main.sqlite3"))
    monkeypatch.setattr(main, "handle_message", record)
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    main.main()
    assert seen == ["  Xin CHÀO  "]


def test_ollama_terminal_can_exit_without_loading_model():
    env = os.environ.copy()
    env.update(CATALOG_MODE="empty", CHAT_MODE="ollama")
    result = subprocess.run([sys.executable, "-X", "utf8", "main.py"], env=env, input="", text=True, encoding="utf-8", capture_output=True, timeout=10)
    assert result.returncode == 0 and "Chế độ chat: ollama" in result.stdout
    assert "Kết thúc phiên" in result.stdout
