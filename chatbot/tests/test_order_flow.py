"""FSM/tool thật trên nguồn demo và SQLite tạm; không gọi model thật."""

from copy import deepcopy
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app import llm_client
from app.conversation import handle_message, new_conversation
from app.handoff import detect_handoff
from app.knowledge_loader import SampleKnowledgeRepository
from app.order_flow import confirm_review, create_review, new_draft, update_slot
from app.order_service import LOCAL_ZONE, calculate_quote, check_availability, create_order_tools, local_now, parse_pickup_at
from app.repositories.empty_catalog import EmptyCatalogRepository
from app.repositories.mock_catalog import MockCatalogRepository
from app.storage import list_records, load_conversation, open_storage, save_conversation

NOW = datetime(2099, 1, 1, 10, 0, tzinfo=LOCAL_ZONE)


@pytest.fixture
def connection(tmp_path):
    conn = open_storage(tmp_path / "chat.sqlite3")
    yield conn
    conn.close()


def ready_draft(conversation_id="A", **changes):
    draft = new_draft(conversation_id)
    values = {
        "cake_need": "bánh thử nghiệm", "product_id": "mock-001", "size": "16 cm", "quantity": 2,
        "toppings": [], "cake_text": "Chúc vui", "pickup_at": "2099-01-04 10:00", "fulfillment": "pickup",
        "name": "DEMO Khách A", "phone": "TEST-0001",
    }
    for field, value in {**values, **changes}.items():
        draft = update_slot(draft, field, value, NOW)
    return draft


def tools_for(connection, repo, draft):
    conversation = new_conversation(draft["conversation_id"])
    conversation["order"] = draft
    with connection:
        save_conversation(connection, conversation)
    return create_order_tools(repo, connection, draft["conversation_id"], NOW)


def test_mock_fsm_review_confirmation_and_double_click(connection):
    draft = ready_draft()
    tools = tools_for(connection, MockCatalogRepository(), draft)
    original = deepcopy(draft)
    review, text = create_review(draft, tools, NOW)
    assert original == draft and draft["state"] == "COLLECTING"
    assert review["state"] == "REVIEW" and "MÔ PHỎNG" in text
    assert review["review"]["quote"]["total_vnd"] == 500000
    with connection:
        submitted, text = confirm_review(review, tools, {})
        retry, _ = confirm_review(submitted, tools, {})
        # Retry từ bản REVIEW cũ cũng phải cùng ID ở database.
        stale_client_retry, _ = confirm_review(review, tools, {})
    assert submitted["submission"]["kind"] == "demo_order" and submitted["submission"]["confirmed"]
    assert retry["submission"]["id"] == stale_client_retry["submission"]["id"] == submitted["submission"]["id"]
    assert "ĐƠN MÔ PHỎNG" in text and len(list_records(connection, "submissions", "A")) == 1


def test_empty_keeps_unverified_saves_request_and_pending_ticket(connection):
    draft = ready_draft()
    tools = tools_for(connection, EmptyCatalogRepository(), draft)
    review, text = create_review(draft, tools, NOW)
    assert review["review"]["quote"] is None and "Chưa đủ nguồn" in text
    assert review["verification"]["product_id"] == review["verification"]["size"] == "unverified"
    with connection:
        result, text = confirm_review(review, tools, {})
    assert result["state"] == "HANDOFF" and not result["submission"]["confirmed"]
    assert result["submission"]["kind"] == "waiting_consultation" and result["submission"]["quote"] is None
    ticket = list_records(connection, "tickets", "A")[0]
    assert ticket["reason"] == "needs_verification" and ticket["status"] == "pending"
    assert "chưa xác nhận đơn" in text and "chưa có nhân viên nhận" in text


def test_edit_invalidates_review_and_needs_new_confirmation(connection):
    draft = ready_draft()
    tools = tools_for(connection, MockCatalogRepository(), draft)
    review, _ = create_review(draft, tools, NOW)
    edited = update_slot(review, "quantity", 3, NOW)
    assert edited["revision"] == review["revision"] + 1 and edited["review"] is None and edited["state"] == "COLLECTING"
    with connection:
        result, _ = confirm_review(edited, tools, {})
    assert result["submission"] is None and list_records(connection, "submissions", "A") == []
    revised, _ = create_review(edited, tools, NOW)
    assert revised["review"]["quote"]["total_vnd"] == 750000


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5, "2"])
def test_quantity_must_be_positive_integer(quantity):
    with pytest.raises(ValueError):
        update_slot(new_draft("A"), "quantity", quantity, NOW)


@pytest.mark.parametrize("date", ["mai", "01/04 10h", "2099-02-30 10:00", "2099-01-01", "2099-01-01 10:00Z"])
def test_date_requires_explicit_local_day_and_time(date):
    with pytest.raises(ValueError):
        parse_pickup_at(date)


def test_local_timezone_and_past_date():
    assert parse_pickup_at("2099-01-04 10:00") == "2099-01-04T03:00:00+00:00"
    with pytest.raises(ValueError):
        update_slot(new_draft("A"), "pickup_at", "2098-12-31 10:00", NOW)


@pytest.mark.parametrize("field,value", [("name", "Khách thật"), ("phone", "0000000000"), ("address", "Địa chỉ chưa nhãn giả")])
def test_contact_only_accepts_synthetic_format(field, value):
    with pytest.raises(ValueError):
        update_slot(new_draft("A"), field, value, NOW)


@pytest.mark.parametrize("changes,issue", [
    ({"size": "99 cm"}, "size_unverified"), ({"toppings": ["topping chưa biết"]}, "topping_unverified"),
    ({"cake_text": "x" * 21}, "cake_text_too_long"), ({"pickup_at": "2099-01-01 11:00"}, "lead_time_too_short"),
    ({"product_id": "invented"}, "product_unverified"),
])
def test_business_requirements_use_metadata_not_guesses(connection, changes, issue):
    draft = ready_draft(**changes)
    tools = tools_for(connection, MockCatalogRepository(), draft)
    review, _ = create_review(draft, tools, NOW)
    assert issue in review["issues"] and review["review"]["quote"] is None
    with connection:
        result, _ = confirm_review(review, tools, {})
    assert result["submission"]["kind"] == "waiting_consultation" and result["state"] == "HANDOFF"


def test_unknown_limits_and_stock_are_not_replaced_by_defaults(connection, monkeypatch):
    draft = ready_draft()
    repo = MockCatalogRepository()
    metadata = repo.get_order_metadata("mock-001")
    metadata["metadata"]["max_cake_text_length"] = None
    monkeypatch.setattr(repo, "get_order_metadata", lambda *args: deepcopy(metadata))
    repo._products[0]["min_lead_hours"] = None
    result = check_availability(repo, draft, NOW)
    assert {"cake_text_limit_unverified", "lead_time_unverified"} <= set(result["data"]["issues"])
    assert calculate_quote(repo, draft, NOW)["status"] == "unknown"


def test_quantity_stock_and_out_of_stock_refuse_confirmation(connection):
    for changes in [{"quantity": 11}, {"product_id": "mock-002", "size": "20 cm"}]:
        draft = ready_draft(**changes)
        tools = tools_for(connection, MockCatalogRepository(), draft)
        review, _ = create_review(draft, tools, NOW)
        assert review["review"]["availability"] == "unavailable"
        with connection:
            result, _ = confirm_review(review, tools, {})
        assert result["submission"] is None
    assert list_records(connection, "submissions", "A") == []


def test_topping_and_delivery_quote_come_from_metadata():
    draft = ready_draft(toppings=["kẹo cốm"], fulfillment="delivery", address="DEMO Địa chỉ A")
    quote = calculate_quote(MockCatalogRepository(), draft, NOW)
    assert quote["status"] == "available"
    assert quote["data"]["quote"]["total_vnd"] == (250000 + 10000) * 2 + 25000


@pytest.mark.parametrize("change", ["price", "stock", "limit", "slots"])
def test_source_or_slots_changed_after_review_require_review_again(connection, change):
    draft = ready_draft()
    repo = MockCatalogRepository()
    tools = tools_for(connection, repo, draft)
    review, _ = create_review(draft, tools, NOW)
    if change == "price":
        repo._products[0]["variants"][0]["price_vnd"] += 1
    elif change == "stock":
        repo._products[0]["variants"][0]["stock_status"] = "out_of_stock"
    elif change == "limit":
        repo._products[0]["min_lead_hours"] += 1
    else:
        review["slots"]["quantity"] = 3  # Bỏ qua update_slot vẫn bị hash chặn.
    with connection:
        result, text = confirm_review(review, tools, {})
    assert result["state"] == "COLLECTING" and result["review"] is None and result["submission"] is None
    assert list_records(connection, "submissions", "A") == []


def test_catalog_error_does_not_save_success_and_real_source_is_unsupported(connection, monkeypatch):
    draft = ready_draft()
    repo = MockCatalogRepository()
    monkeypatch.setattr(repo, "get_product", lambda *args: {"status": "error", "product": None})
    assert check_availability(repo, draft, NOW)["status"] == "error"
    monkeypatch.setattr(repo, "get_capabilities", lambda: {"data_mode": "real", "is_mock": False, "can_accept_real_orders": True})
    assert check_availability(repo, draft, NOW)["status"] == "unsupported"


def test_bound_tools_do_not_submit_another_customers_draft(connection):
    draft = ready_draft("A")
    tools = create_order_tools(MockCatalogRepository(), connection, "B", NOW)
    assert tools["submit_order_request"](draft, "key")["error"] == "conversation_mismatch"


@pytest.mark.parametrize("state", ["BROWSING", "CANCELLED", "HANDOFF"])
def test_fsm_forbids_review_without_collecting_even_with_complete_slots(connection, state):
    draft = ready_draft()
    draft["state"] = state
    tools = tools_for(connection, MockCatalogRepository(), draft)
    result, _ = create_review(draft, tools, NOW)
    assert result["state"] == state and result["review"] is None
    if state != "BROWSING":
        with pytest.raises(ValueError):
            update_slot(result, "size", "20 cm", NOW)


def test_written_text_needs_explicit_catalog_customization_capability():
    repo = MockCatalogRepository()
    repo._products[0]["customization"] = ["tùy chỉnh khác"]
    result = calculate_quote(repo, ready_draft(), NOW)
    assert result["status"] == "unknown" and "cake_text_unverified" in result["data"]["issues"]


def test_cancelled_or_handoff_draft_can_start_a_new_draft(connection):
    repo = EmptyCatalogRepository()
    started = run_turn("đặt bánh", repo, new_conversation(), connection)["conversation"]
    cancelled = run_turn("hủy", repo, started, connection)["conversation"]
    restarted = run_turn("đặt bánh", repo, cancelled, connection)["conversation"]
    assert restarted["order"]["id"] != cancelled["order"]["id"] and restarted["order"]["state"] == "COLLECTING"


def test_external_confirmed_order_change_is_a_pending_ticket(connection):
    turn = run_turn("Tôi muốn sửa đơn đã xác nhận", EmptyCatalogRepository(), new_conversation(), connection)
    assert turn["conversation"]["order"]["state"] == "HANDOFF"
    tickets = list_records(connection, "tickets", turn["conversation"]["id"])
    assert tickets[0]["reason"] == "change_confirmed_order" and tickets[0]["status"] == "pending"


@pytest.mark.parametrize("message,field,value", [
    ("chữ: Gặp nhân viên", "cake_text", "Gặp nhân viên"),
    ("tên: DEMO Nhân viên", "name", "DEMO Nhân viên"),
])
def test_slot_content_is_data_not_a_handoff_command(connection, message, field, value):
    repo = EmptyCatalogRepository()
    started = run_turn("đặt bánh", repo, new_conversation(), connection)["conversation"]
    updated = run_turn(message, repo, started, connection)["conversation"]
    assert updated["order"]["state"] == "COLLECTING" and updated["order"]["slots"][field] == value
    assert list_records(connection, "tickets", updated["id"]) == []


def test_severe_allergy_in_needs_slot_still_requests_verification(connection):
    repo = EmptyCatalogRepository()
    started = run_turn("đặt bánh", repo, new_conversation(), connection)["conversation"]
    updated = run_turn("nhu cầu: dị ứng nghiêm trọng", repo, started, connection)["conversation"]
    assert updated["order"]["state"] == "HANDOFF" and "severe_allergy" in updated["order"]["tickets"]


def test_policy_question_after_demo_is_not_an_order_change(connection):
    repo = MockCatalogRepository()
    reviewed = fill_in_terminal(repo, connection)["conversation"]
    confirmed = run_turn("xác nhận", repo, reviewed, connection)["conversation"]
    turn = run_turn("Chính sách đổi trả là gì?", repo, confirmed, connection, knowledge_repository=SampleKnowledgeRepository())
    assert turn["conversation"]["order"]["state"] == "REVIEW"
    assert turn["response"]["policy"] is not None and "sample-policy-003" in turn["response"]["policy"]["source_ids"]
    assert list_records(connection, "tickets", confirmed["id"]) == []


def run_turn(message, repo, conversation, connection, **kwargs):
    tools = create_order_tools(repo, connection, conversation["id"])
    return handle_message(message, repo, conversation, order_tools=tools, storage_connection=connection, chat_mode="rule", **kwargs)


def fill_in_terminal(repo, connection, conversation=None):
    current = conversation or new_conversation()
    date = (local_now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    messages = ["đặt bánh", "nhu cầu: bánh học tập", "mã bánh: mock-001", "size: 16 cm", "số lượng: 2",
                "topping: không", "chữ: Chúc vui", f"ngày nhận: {date}", "nhận: cửa hàng", "tên: DEMO Khách A", "sđt: TEST-0001", "xem lại"]
    for message in messages:
        turn = run_turn(message, repo, current, connection)
        current = turn["conversation"]
    return turn


@pytest.mark.parametrize("repo_class", [EmptyCatalogRepository, MockCatalogRepository])
def test_full_controller_persistence_and_separate_customers(connection, repo_class):
    repo = repo_class()
    untouched = new_conversation("B")
    turn = fill_in_terminal(repo, connection)
    a = turn["conversation"]
    assert a["order"]["state"] == "REVIEW"
    submitted = run_turn("xác nhận", repo, a, connection)
    loaded = load_conversation(connection, a["id"])
    assert loaded == submitted["conversation"]
    assert loaded["order"]["submission"]["confirmed"] == (repo_class is MockCatalogRepository)
    assert untouched["history"] == [] and untouched["order"]["state"] == "BROWSING"
    assert list_records(connection, "submissions", "B") == []


def test_invalid_edit_and_confirm_without_review_do_not_submit(connection):
    repo = MockCatalogRepository()
    review = fill_in_terminal(repo, connection)["conversation"]
    invalid = run_turn("số lượng: 2.5", repo, review, connection)["conversation"]
    assert invalid["order"]["state"] == "COLLECTING" and invalid["order"]["review"] is None
    result = run_turn("xác nhận", repo, invalid, connection)
    assert result["conversation"]["order"]["submission"] is None


@pytest.mark.parametrize("message,reason", [
    ("Tôi muốn gặp nhân viên", "customer_requested"), ("dị ứng nghiêm trọng", "severe_allergy"),
    ("tôi muốn khiếu nại", "complaint"),
])
def test_handoff_reasons_and_duplicate_ticket(connection, message, reason):
    repo = EmptyCatalogRepository()
    turn = run_turn(message, repo, new_conversation(), connection)
    assert turn["conversation"]["order"]["state"] == "HANDOFF" and "chưa có nhân viên nhận" in turn["response"]["text"]
    again = run_turn(message, repo, turn["conversation"], connection)
    tickets = list_records(connection, "tickets", again["conversation"]["id"])
    assert len(tickets) == 1 and tickets[0]["reason"] == reason


def test_two_unknowns_are_consecutive_and_isolated(connection):
    repo = EmptyCatalogRepository()
    a = run_turn("xyz abc", repo, new_conversation(), connection)["conversation"]
    assert a["unknown_streak"] == 1
    b = run_turn("xyz abc", repo, new_conversation(), connection)["conversation"]
    assert b["unknown_streak"] == 1 and b["order"]["state"] == "BROWSING"
    a = run_turn("qrs def", repo, a, connection)["conversation"]
    assert a["order"]["state"] == "HANDOFF" and list_records(connection, "tickets", a["id"])[0]["reason"] == "two_unknown_turns"
    c = run_turn("xyz abc", repo, new_conversation(), connection)["conversation"]
    c = run_turn("xin chào", repo, c, connection)["conversation"]
    assert c["unknown_streak"] == 0


def test_cancel_and_changes_to_confirmed_demo_go_to_handoff(connection):
    repo = MockCatalogRepository()
    started = run_turn("đặt bánh", repo, new_conversation(), connection)["conversation"]
    cancelled = run_turn("hủy", repo, started, connection)["conversation"]
    assert cancelled["order"]["state"] == "CANCELLED"
    review = fill_in_terminal(repo, connection)["conversation"]
    submitted = run_turn("xác nhận", repo, review, connection)["conversation"]
    changed = run_turn("size: 20 cm", repo, submitted, connection)["conversation"]
    assert changed["order"]["state"] == "HANDOFF" and changed["order"]["slots"]["size"] == "16 cm"
    assert changed["order"]["tickets"]["change_confirmed_order"]["status"] == "pending"
    assert len(list_records(connection, "submissions", changed["id"])) == 1


def test_explicit_rule_commands_do_not_call_llm_or_save_raw_contact(connection, monkeypatch):
    monkeypatch.setattr(llm_client, "select_model", lambda *args: pytest.fail("Lệnh nghiệp vụ không gọi model"))
    repo = EmptyCatalogRepository()
    current = new_conversation()
    for message in ["đặt bánh", "sđt: 0000000000", "tên: DEMO Khách A"]:
        turn = handle_message(message, repo, current, chat_mode="rule", order_tools=create_order_tools(repo, connection, current["id"]), storage_connection=connection)
        current = turn["conversation"]
    stored = json.dumps(load_conversation(connection, current["id"]), ensure_ascii=False)
    assert "0000000000" not in stored and "DEMO Khách A" in stored


def test_sqlite_write_failure_does_not_claim_success(connection, monkeypatch):
    repo = EmptyCatalogRepository()
    current = new_conversation()
    def fail(*args):
        raise sqlite3.OperationalError("private database details")
    monkeypatch.setattr("app.conversation.save_conversation", fail)
    turn = run_turn("đặt bánh", repo, current, connection)
    assert turn["conversation"] == current and turn["response"]["error"] == "storage_error"
    assert "private" not in turn["response"]["text"]


@pytest.mark.parametrize("mode,expected", [("empty", "YÊU CẦU CHỜ TƯ VẤN"), ("mock", "ĐƠN MÔ PHỎNG DEMO")])
def test_terminal_full_flow_uses_real_sqlite(tmp_path, mode, expected):
    date = (local_now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    commands = ["đặt bánh", "nhu cầu: bánh học tập", "mã bánh: mock-001", "size: 16 cm", "số lượng: 2",
                "topping: không", "chữ: Chúc vui", f"ngày nhận: {date}", "nhận: cửa hàng", "tên: DEMO Khách A", "sđt: TEST-0001", "xem lại", "xác nhận", "xác nhận", "thoát"]
    env = os.environ.copy()
    path = tmp_path / "cli.sqlite3"
    env.update(CATALOG_MODE=mode, CHAT_MODE="rule", KNOWLEDGE_MODE="empty", CHATBOT_DB_PATH=str(path))
    root = Path(__file__).resolve().parents[1]
    process = subprocess.run([sys.executable, "-X", "utf8", "main.py"], cwd=root, env=env, input="\n".join(commands) + "\n", capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert process.returncode == 0 and expected in process.stdout, process.stdout
    connection = open_storage(path)
    assert connection.execute("SELECT COUNT(*) FROM submissions").fetchone()[0] == 1
    assert "chưa có nhân viên nhận" in process.stdout if mode == "empty" else "500.000 đ" in process.stdout
    connection.close()
