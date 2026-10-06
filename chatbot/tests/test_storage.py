"""SQLite thật trong file tạm; test transaction/idempotency/phiên riêng."""

from copy import deepcopy
import sqlite3

import pytest

from app.conversation import new_conversation
from app.storage import list_records, load_conversation, open_storage, save_conversation, save_record


def test_persistence_across_reopening_and_schema_v2(tmp_path):
    path = tmp_path / "chat.sqlite3"
    connection = open_storage(path)
    conversation = new_conversation("customer-A")
    conversation["order"]["slots"]["cake_need"] = "nhu cầu giả"
    conversation["history"] = [{"role": "user", "content": "xin chào"}]
    with connection:
        save_conversation(connection, conversation)
    connection.close()
    connection = open_storage(path)
    assert load_conversation(connection, "customer-A") == conversation
    assert list_records(connection, "drafts", "customer-A")[0]["slots"]["cake_need"] == "nhu cầu giả"
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"conversations", "drafts", "submissions", "tickets", "products", "product_variants", "policies", "orders", "order_items", "messages"} <= tables
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    connection.close()


def test_two_customers_and_detached_loaded_objects(tmp_path):
    connection = open_storage(tmp_path / "chat.sqlite3")
    first, second = new_conversation("A"), new_conversation("B")
    first["needs"]["product_terms"] = ["nhu cầu A"]
    with connection:
        save_conversation(connection, first)
        save_conversation(connection, second)
    loaded = load_conversation(connection, "A")
    loaded["needs"]["product_terms"].append("changed in memory")
    assert load_conversation(connection, "A")["needs"] == first["needs"]
    assert load_conversation(connection, "B")["needs"]["product_terms"] == []
    assert load_conversation(connection, "unknown") is None


@pytest.mark.parametrize("table", ["submissions", "tickets"])
def test_idempotency_and_cross_customer_conflict(tmp_path, table):
    connection = open_storage(tmp_path / "chat.sqlite3")
    a, b = new_conversation("A"), new_conversation("B")
    payload = {"draft_id": a["order"]["id"], "kind": "waiting_consultation", "note": "fake"}
    with connection:
        save_conversation(connection, a)
        save_conversation(connection, b)
        first = save_record(connection, table, "A", "same-key", payload)
        retry = save_record(connection, table, "A", "same-key", payload)
        conflict = save_record(connection, table, "A", "same-key", {**payload, "note": "changed"})
        different_owner = save_record(connection, table, "B", "same-key", payload)
    assert first["data"]["id"] == retry["data"]["id"]
    assert conflict["error"] == different_owner["error"] == "idempotency_conflict"
    assert len(list_records(connection, table, "A")) == 1
    assert list_records(connection, table, "B") == []


def test_sql_parameters_and_history_redaction(tmp_path):
    connection = open_storage(tmp_path / "chat.sqlite3")
    identifier = "fake'; DROP TABLE conversations; --"
    conversation = new_conversation(identifier)
    # Chuỗi ký tự được tạo trong test, không là liên hệ một người thật.
    conversation["history"] = [{"role": "user", "content": "sđt: 0000000000"}]
    with connection:
        save_conversation(connection, conversation)
    assert load_conversation(connection, identifier)["id"] == identifier
    assert "0000000000" not in load_conversation(connection, identifier)["history"][0]["content"]
    assert "0000000000" in conversation["history"][0]["content"]  # Không mutate đầu vào.


def test_transaction_rolls_back_both_ticket_and_conversation(tmp_path):
    connection = open_storage(tmp_path / "chat.sqlite3")
    with pytest.raises(RuntimeError):
        with connection:
            save_conversation(connection, new_conversation("A"))
            save_record(connection, "tickets", "A", "ticket", {"reason": "test"})
            raise RuntimeError("simulated failure")
    assert load_conversation(connection, "A") is None
    assert list_records(connection, "tickets", "A") == []


def test_draft_cannot_be_reassigned_to_another_customer(tmp_path):
    connection = open_storage(tmp_path / "chat.sqlite3")
    a, b = new_conversation("A"), new_conversation("B")
    with connection:
        save_conversation(connection, a)
    b["order"] = deepcopy(a["order"])
    b["order"]["conversation_id"] = "B"
    with pytest.raises(ValueError):
        with connection:
            save_conversation(connection, b)
    assert load_conversation(connection, "B") is None
    assert list_records(connection, "drafts", "A")[0]["conversation_id"] == "A"


def test_foreign_key_and_schema_version_are_checked(tmp_path):
    path = tmp_path / "chat.sqlite3"
    connection = open_storage(path)
    with pytest.raises(sqlite3.IntegrityError):
        with connection:
            save_record(connection, "tickets", "unknown-parent", "key", {})
    connection.execute("PRAGMA user_version = 99")
    connection.close()
    with pytest.raises(ValueError):
        open_storage(path)
