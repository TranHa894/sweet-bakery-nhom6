"""Qwen trích slot giả lập; SQLite/API thật trong process, không gọi model thật."""

from contextlib import closing
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import llm_client
from app.api import create_app
from app.nlu import analyze_message
from app.order_flow import new_draft
from app.order_nlu import apply_order_proposal, check_order_proposal
from app.repositories.empty_catalog import EmptyCatalogRepository
from app.repositories.mock_catalog import MockCatalogRepository
from app.schemas import LLMOrderSlots, LLMTurn
from app.storage import load_conversation, open_storage

MESSAGE = ("Mình muốn đặt hai bánh socola size 16 cm, không topping, ghi chữ 'Chúc vui', "
           "nhận tại cửa hàng lúc 2099-01-04 10:00, tên DEMO Khách A, sđt TEST-0001.")


def proposal(**changes):
    data = {"product_mentions": [], "cake_need": None, "size": None, "quantity": None,
        "toppings": None, "cake_text": None, "pickup_at": None, "fulfillment": None,
        "name": None, "phone": None, "address": None, "needs_clarification": False}
    return LLMOrderSlots(**{**data, **changes})


def full_proposal():
    return proposal(product_mentions=["bánh socola"], cake_need="bánh socola", size="16 cm", quantity=2,
        toppings=[], cake_text="Chúc vui", pickup_at="2099-01-04 10:00", fulfillment="pickup",
        name="DEMO Khách A", phone="TEST-0001")


def mock_model(monkeypatch, responses):
    outputs = iter(responses)
    calls = []
    monkeypatch.setattr(llm_client, "select_model", lambda *args: {"model":"qwen-test", "error":None})
    def extract(message, draft, *args):
        calls.append(message)
        controls = {"đặt bánh":"start_order", "xem lại":"review", "xác nhận":"confirm"}
        if message in controls:
            value = LLMTurn(intents=["order_request"],action=controls[message],product_mentions=[],reference="none",updates={},clear_slots=[],ambiguous=False,handoff_reason="none")
        else:
            value = next(outputs, proposal(quantity=3))
            if isinstance(value, LLMOrderSlots):
                raw=value.model_dump(exclude_none=True)
                mentions=raw.pop("product_mentions")
                ambiguous=raw.pop("needs_clarification")
                value=LLMTurn(intents=["order_request"] if raw or mentions else ["fallback"],
                    action="start_order" if "đặt" in message.lower() else "none",product_mentions=mentions,
                    reference="none",updates=raw,clear_slots=[],ambiguous=ambiguous,handoff_reason="none",order_update=bool(raw or mentions))
        return {"data":value,"error":None,"attempts":1} if isinstance(value,LLMTurn) else value
    monkeypatch.setattr(llm_client, "extract_turn", extract)
    return calls


def start(client):
    session = client.post("/api/conversations", json={}).json()
    return session, {"Authorization":"Bearer " + session["session_token"]}


def send(client, session, headers, message):
    response = client.post("/api/chat", headers=headers, json={"conversation_id":session["conversation_id"],"message":message})
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("mode", ["empty", "mock"])
def test_natural_full_order_requires_review_then_explicit_confirmation(tmp_path, monkeypatch, mode):
    mock_model(monkeypatch, [full_proposal()])
    repo = EmptyCatalogRepository() if mode == "empty" else MockCatalogRepository()
    app = create_app(catalog_repository=repo, chat_mode="ollama", db_path=tmp_path / "chat.sqlite3")
    with TestClient(app) as client:
        session, headers = start(client)
        turn = send(client, session, headers, MESSAGE)
        assert turn["engine"] == "ollama" and turn["state"] == "REVIEW"
        assert turn["requires_confirmation"] and turn["demo_order_id"] is None
        review = send(client, session, headers, "xem lại")
        assert review["requires_confirmation"] and review["review"]["slots"]["quantity"] == 2
        assert review["review"]["slots"]["cake_text"] == "Chúc vui"
        assert review["review"]["slots"]["product_id"] == ("mock-001" if mode == "mock" else None)
        # Xác nhận qua cùng extract_turn fake; model đã được chọn ở lượt trước.
        result = send(client, session, headers, "xác nhận")
        assert bool(result["request_id"]) is (mode == "empty")
        assert bool(result["demo_order_id"]) is (mode == "mock")


def test_natural_edit_invalidates_review_and_keeps_other_slots(tmp_path, monkeypatch):
    mock_model(monkeypatch, [full_proposal(), proposal(quantity=3)])
    app = create_app(catalog_repository=MockCatalogRepository(), chat_mode="ollama", db_path=tmp_path / "chat.sqlite3")
    with TestClient(app) as client:
        session, headers = start(client)
        send(client, session, headers, MESSAGE)
        send(client, session, headers, "xem lại")
        edited = send(client, session, headers, "Tăng số lượng lên 3 bánh.")
        assert edited["state"] == "REVIEW" and edited["requires_confirmation"]
        assert edited["demo_order_id"] is None
        review = send(client, session, headers, "xem lại")["review"]
        assert review["quote"]["total_vnd"] == 750000 and review["slots"]["cake_text"] == "Chúc vui"


@pytest.mark.parametrize("changes", [
    {"product_mentions":["bánh tự bịa"]}, {"quantity":9}, {"size":"99 cm"},
    {"toppings":["topping tự bịa"]}, {"cake_text":"CHÚC VUI"},
    {"pickup_at":"2099-01-05 10:00"}, {"fulfillment":"delivery"},
    {"phone":"TEST-9999"}, {"name":"DEMO Người khác"}, {"needs_clarification":True},
])
def test_hallucinated_or_ambiguous_slots_rejected(changes):
    data = full_proposal().model_dump()
    data.update(changes)
    rule = analyze_message(MESSAGE, MockCatalogRepository())
    assert check_order_proposal(MESSAGE, rule, LLMOrderSlots(**data)) is not None


def test_unclear_date_and_multiple_names_do_not_apply_partially():
    draft = new_draft("A")
    draft["state"] = "COLLECTING"
    draft["slots"]["size"] = "16 cm"
    original = deepcopy(draft)
    message = "Nhận ngày mai 10h, số lượng 2 bánh."
    updated, text, error = apply_order_proposal(message, draft, analyze_message(message, EmptyCatalogRepository()),
        proposal(quantity=2, pickup_at="mai 10h"))
    assert error == "invalid_order_slots" and updated["slots"]["quantity"] is None
    assert "YYYY-MM-DD" in text and draft == original
    message = "Đặt hai bánh socola và dâu size 16 cm."
    rule = analyze_message(message, MockCatalogRepository())
    assert check_order_proposal(message, rule, proposal(product_mentions=["socola","dâu"],size="16 cm",quantity=2)) == "ambiguous_order_slots"


@pytest.mark.parametrize("error", ["timeout", "model_not_found", "invalid_order_json"])
def test_extraction_failure_preserves_review_without_submitting(tmp_path, monkeypatch, error):
    mock_model(monkeypatch, [full_proposal(), {"data":None,"error":error,"attempts":1}])
    app = create_app(catalog_repository=MockCatalogRepository(), chat_mode="ollama", db_path=tmp_path / "chat.sqlite3")
    with TestClient(app) as client:
        session, headers = start(client)
        send(client, session, headers, MESSAGE)
        send(client, session, headers, "xem lại")
        failed = send(client, session, headers, "Tăng số lượng lên 3 bánh.")
        assert error in failed["errors"] and failed["engine"] == "llm_error"
        assert failed["review"]["quote"]["total_vnd"] == 500000 and failed["demo_order_id"] is None


def test_contacts_without_fake_label_not_sent_to_model_or_stored(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_client, "select_model", lambda *args: pytest.fail("Không gửi contact không nhãn giả"))
    app = create_app(catalog_repository=EmptyCatalogRepository(), chat_mode="ollama", db_path=tmp_path / "chat.sqlite3")
    with TestClient(app) as client:
        session, headers = start(client)
        result = send(client, session, headers, "Mình muốn đặt bánh socola, tên Khách Thử, sđt 0000000000.")
        assert "fake_contact_required" in result["errors"]
        with closing(open_storage(tmp_path / "chat.sqlite3")) as connection:
            stored = json.dumps(load_conversation(connection, session["conversation_id"]), ensure_ascii=False)
        assert "Khách Thử" not in stored and "0000000000" not in stored


def test_order_schema_never_accepts_product_id_quote_or_confirmed():
    for extra in [{"product_id":"mock-001"}, {"confirmed":True}, {"price_vnd":250000}]:
        with pytest.raises(ValidationError):
            LLMOrderSlots(**{**proposal().model_dump(), **extra})


def test_cake_text_is_data_and_confirmed_order_edit_hands_off(tmp_path, monkeypatch):
    value = full_proposal().model_dump()
    value["cake_text"] = "nhân viên"
    mock_model(monkeypatch, [LLMOrderSlots(**value)])
    message = MESSAGE.replace("Chúc vui", "nhân viên")
    app = create_app(catalog_repository=MockCatalogRepository(), chat_mode="ollama", db_path=tmp_path / "chat.sqlite3")
    with TestClient(app) as client:
        session, headers = start(client)
        turn = send(client, session, headers, message)
        assert turn["state"] == "REVIEW" and turn["engine"] == "ollama"
        send(client, session, headers, "xem lại")
        confirmed = send(client, session, headers, "xác nhận")
        assert confirmed["demo_order_id"]
        edited = send(client, session, headers, "Tăng số lượng lên 3 bánh.")
        assert edited["state"] == "HANDOFF" and edited["demo_order_id"] == confirmed["demo_order_id"]


def test_repository_failure_after_model_does_not_confirm(tmp_path, monkeypatch):
    repo = MockCatalogRepository()
    monkeypatch.setattr(repo, "search_products", lambda filters: {"status":"error","data_mode":"mock","products":[],"error":"source_error"})
    mock_model(monkeypatch, [proposal(product_mentions=["bánh socola"],quantity=2,size="16 cm")])
    app = create_app(catalog_repository=repo, chat_mode="ollama", db_path=tmp_path / "chat.sqlite3")
    with TestClient(app) as client:
        session, headers = start(client)
        data = send(client, session, headers, "Mình muốn đặt 2 bánh socola size 16 cm.")
        assert data["engine"] == "source_error" and data["demo_order_id"] is None


def test_missing_fields_never_copy_contacts_from_context(monkeypatch):
    draft = new_draft("A")
    draft["slots"]["name"] = "DEMO Bí mật A"
    draft["slots"]["phone"] = "TEST-SECRET"
    def chat(messages, *args):
        payload = json.loads(messages[1]["content"])
        assert "name" not in payload["context"] and "phone" not in payload["context"]
        assert payload["message"] == "Tăng số lượng lên 3 bánh."
        return {"ok":True,"content":proposal(quantity=3).model_dump_json()}
    monkeypatch.setattr(llm_client, "chat", chat)
    result = llm_client.extract_order_slots("Tăng số lượng lên 3 bánh.", draft, "http://localhost:11434", "qwen-test")
    assert result["data"].name is None and result["data"].quantity == 3


def test_two_unrecognized_order_turns_handoff_only_their_session(tmp_path, monkeypatch):
    mock_model(monkeypatch, [proposal(), proposal(), proposal()])
    app = create_app(catalog_repository=EmptyCatalogRepository(), chat_mode="ollama", db_path=tmp_path / "chat.sqlite3")
    with TestClient(app) as client:
        a, ah = start(client)
        b, bh = start(client)
        send(client, a, ah, "đặt bánh")
        send(client, b, bh, "đặt bánh")
        assert send(client, a, ah, "abcxyz")["state"] == "COLLECTING"
        assert send(client, b, bh, "abcxyz")["state"] == "COLLECTING"
        result = send(client, a, ah, "defuvw")
        assert result["state"] == "HANDOFF" and "chưa có nhân viên nhận" in result["message"]


@pytest.mark.parametrize("second_valid", [True, False])
def test_order_json_repair_only_once(monkeypatch, second_valid):
    calls = []
    def chat(*args):
        calls.append(args)
        content = full_proposal().model_dump_json() if len(calls) == 2 and second_valid else 'invalid JSON'
        return {"ok":True,"content":content}
    monkeypatch.setattr(llm_client, "chat", chat)
    result = llm_client.extract_order_slots(MESSAGE, new_draft("A"), "http://localhost:11434", "qwen-test")
    assert len(calls) == 2 and result["attempts"] == 2
    assert (result["data"] is not None) is second_valid
    assert result["error"] == (None if second_valid else "invalid_order_json")
