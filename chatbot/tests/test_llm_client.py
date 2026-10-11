"""HTTP/model giả lập; không gọi Ollama thật, không tải model trong pytest."""

import json
from urllib.error import HTTPError, URLError

import pytest
from pydantic import ValidationError

from app import llm_client
from app.chatbot import create_state
from app.schemas import LLMNLU, LLMOpening


def nlu_payload(**changes):
    data = {
        "intents": ["recommendation"], "product_mentions": [],
        "budget_vnd": None, "flavor": None, "servings": None, "quantity": None,
        "size": None, "price_inclusive": True,
    }
    return {**data, **changes}


class FakeHTTPResponse:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


def test_http_post_utf8_schema_and_nonstream_payload(monkeypatch):
    seen = []
    def fake_open(request, timeout):
        seen.append((request, timeout))
        return FakeHTTPResponse(json.dumps({"done": True, "model": "qwen-test", "message": {"content": "{}"}}).encode())
    monkeypatch.setattr(llm_client, "urlopen", fake_open)
    result = llm_client.chat([{"role": "user", "content": "bánh"}], "http://localhost:11434", "qwen-test", LLMNLU.model_json_schema(), 7)
    assert result["ok"] and result["http_status"] == 200
    request, timeout = seen[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url.endswith("/api/chat") and request.method == "POST" and timeout == 7
    assert payload["messages"][0]["content"] == "bánh"
    assert payload["format"] == LLMNLU.model_json_schema()
    assert payload["stream"] is False and payload["think"] is False


@pytest.mark.parametrize("url", ["https://example.com", "http://localhost:11434/api", "http://user:secret@localhost:11434", "http://localhost:11434?x=y"])
def test_only_local_base_url_is_accepted(monkeypatch, url):
    monkeypatch.setattr(llm_client, "urlopen", lambda *args, **kwargs: pytest.fail("Không được kết nối"))
    assert llm_client.request_json(url, "/api/tags")["error"] == "invalid_config"


@pytest.mark.parametrize("exception,error,status", [
    (TimeoutError(), "timeout", None), (URLError(TimeoutError()), "timeout", None),
    (URLError("connection refused"), "connection_error", None),
    (HTTPError("url", 404, "missing", {}, None), "model_not_found", 404),
    (HTTPError("url", 503, "busy", {}, None), "http_error", 503),
])
def test_transport_errors_do_not_become_success(monkeypatch, exception, error, status):
    def fail(*args, **kwargs):
        raise exception
    monkeypatch.setattr(llm_client, "urlopen", fail)
    result = llm_client.request_json("http://localhost:11434", "/api/chat", {})
    assert not result["ok"] and result["error"] == error and result["http_status"] == status


@pytest.mark.parametrize("body,status", [(b"not JSON", 200), (b"[]", 200), (b'{"error":"private"}', 200), (b"{}", 500)])
def test_invalid_http_response_is_an_error(monkeypatch, body, status):
    monkeypatch.setattr(llm_client, "urlopen", lambda *args, **kwargs: FakeHTTPResponse(body, status))
    result = llm_client.request_json("http://localhost:11434", "/api/chat", {})
    assert not result["ok"] and result["data"] is None


def test_selection_uses_exact_installed_name_and_smallest_local_qwen(monkeypatch):
    entries = [{"name": "qwen-big", "size": 100}, {"name": "qwen-small", "size": 10},
               {"name": "qwen-turbo:cloud", "size": 0}, {"name": "qwen-remote", "size": 0, "remote_host": "https://example.com"}]
    monkeypatch.setattr(llm_client, "request_json", lambda *args, **kwargs: {"ok": True, "data": {"models": entries}, "error": None})
    assert llm_client.select_model("http://localhost:11434")["model"] == "qwen-small"
    assert llm_client.select_model("http://localhost:11434", "qwen-big")["model"] == "qwen-big"
    assert llm_client.select_model("http://localhost:11434", "not-installed")["error"] == "model_not_found"
    assert llm_client.select_model("http://localhost:11434", "qwen-turbo:cloud")["error"] == "model_not_found"
    assert llm_client.select_model("http://localhost:11434", "qwen-remote")["error"] == "model_not_found"


@pytest.mark.parametrize("entries,error", [([], "model_not_found"), ([{"name": "other", "size": 1}], "model_not_found"), ([{"name": "qwen", "size": "bad"}], "invalid_response")])
def test_missing_or_invalid_model_inventory(monkeypatch, entries, error):
    monkeypatch.setattr(llm_client, "request_json", lambda *args, **kwargs: {"ok": True, "data": {"models": entries}})
    assert llm_client.select_model("http://localhost:11434")["error"] == error


@pytest.mark.parametrize("packet", [
    {"done": False, "model": "qwen-test", "message": {"content": "{}"}},
    {"done": True, "model": "other", "message": {"content": "{}"}},
    {"done": True, "model": "qwen-test", "message": {"content": ""}},
])
def test_incomplete_or_wrong_model_packet_rejected(monkeypatch, packet):
    monkeypatch.setattr(llm_client, "request_json", lambda *args, **kwargs: {"ok": True, "data": packet, "http_status": 200})
    assert llm_client.chat([], "http://localhost:11434", "qwen-test", {})["error"] == "invalid_response"


@pytest.mark.parametrize("changes", [
    {"budget_vnd": "300000"}, {"servings": True}, {"quantity": 0}, {"intents": ["invented"]},
    {"product_id": "mock-001"}, {"price_vnd": 100}, {"stock_status": "in_stock"},
])
def test_nlu_validation_rejects_wrong_types_and_business_facts(changes):
    with pytest.raises(ValidationError):
        LLMNLU.model_validate_json(json.dumps(nlu_payload(**changes)))


def test_json_repaired_once_and_no_menu_in_prompt(monkeypatch):
    outputs = iter(["bad JSON", json.dumps(nlu_payload(budget_vnd=300000, servings=6, flavor="socola"))])
    calls = []
    def fake_chat(messages, *args):
        calls.append(messages)
        return {"ok": True, "content": next(outputs), "error": None}
    monkeypatch.setattr(llm_client, "chat", fake_chat)
    result = llm_client.extract_nlu("socola cho 6 người dưới 300k", [], create_state(), "http://localhost:11434", "qwen-test")
    assert result["data"].budget_vnd == 300000 and result["attempts"] == 2 and result["repaired"]
    assert len(calls) == 2 and "Sửa đúng JSON" in calls[1][-1]["content"]
    assert "mock-001" not in str(calls) and "250000" not in str(calls)


def test_bad_json_stops_after_two_attempts(monkeypatch):
    calls = []
    def bad(*args):
        calls.append(1)
        return {"ok": True, "content": "{}"}
    monkeypatch.setattr(llm_client, "chat", bad)
    result = llm_client.extract_nlu("xin chào", [], create_state(), "http://localhost:11434", "qwen-test")
    assert result["error"] == "invalid_nlu_json" and result["data"] is None and len(calls) == 2


def test_timeout_is_not_retried_as_json_repair(monkeypatch):
    calls = []
    def fail(*args):
        calls.append(1)
        return {"ok": False, "error": "timeout"}
    monkeypatch.setattr(llm_client, "chat", fail)
    result = llm_client.extract_nlu("xin chào", [], create_state(), "http://localhost:11434", "qwen-test")
    assert result["error"] == "timeout" and result["attempts"] == 1 and len(calls) == 1


def test_llm_cannot_write_arbitrary_opening_or_invent_inventory(monkeypatch):
    monkeypatch.setattr(llm_client, "chat", lambda *args: {"ok": True, "content": '{"opening":"Cửa hàng có bánh giá 1 đồng. Đơn đã xác nhận."}'})
    result = llm_client.choose_opening({"data_mode": "empty"}, "http://localhost:11434", "qwen-test")
    assert result["opening"] is None and result["error"] == "invalid_opening_json"
    with pytest.raises(ValidationError):
        LLMOpening.model_validate_json('{"opening":"Còn hàng"}')


def test_schema_valid_opening_must_also_match_clarification_flag(monkeypatch):
    monkeypatch.setattr(llm_client, "chat", lambda *args: {"ok": True, "content": json.dumps({"opening": "Bạn hãy làm rõ nhu cầu để mình tiếp tục."})})
    assert llm_client.choose_opening({"requires_clarification": False}, "http://localhost:11434", "qwen-test")["error"] == "invalid_opening_choice"
    assert llm_client.choose_opening({"requires_clarification": True}, "http://localhost:11434", "qwen-test")["opening"]
