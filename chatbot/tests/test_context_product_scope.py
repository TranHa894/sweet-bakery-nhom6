"""Phạm vi câu hỏi, tham chiếu và draft riêng. SQLite test + Qwen fake."""

from copy import deepcopy
import json

import pytest

from app import llm_client
from app.conversation import handle_message, new_conversation
from app.order_flow import create_review, update_slot
from app.order_service import create_order_tools
from app.repositories.empty_catalog import EmptyCatalogRepository
from app.repositories.local_catalog import LocalCatalogRepository
from app.repositories.mock_catalog import MockCatalogRepository
from app.storage import load_conversation, open_storage, save_conversation
from scripts.database import seed_database


@pytest.fixture
def scope_db(tmp_path):
    path = tmp_path / "context.sqlite3"
    connection = open_storage(path)
    seed_database(connection)
    yield connection, LocalCatalogRepository(path)
    connection.close()


def send(message, current, connection, repository):
    return handle_message(message, repository, current, chat_mode="ollama",
                          storage_connection=connection,
                          order_tools=create_order_tools(repository, connection, current["id"]))


def start_order(make_turn, name="socola"):
    return make_turn(intents=["order_request"], action="start_order",
                     product_mentions=["bánh " + name], order_update=True)


def product_ids(turn):
    return [product["id"] for product in turn["response"]["products"]]


@pytest.mark.parametrize("reference", ["none", "last"])
@pytest.mark.parametrize("mode", ["local_demo", "mock"])
def test_A_named_price_excludes_draft_even_if_model_adds_reference(scope_db, make_turn, fake_model, reference, mode):
    connection, local = scope_db
    repository = local if mode == "local_demo" else MockCatalogRepository()
    prefix = "demo" if mode == "local_demo" else "mock"
    fake_model([start_order(make_turn), make_turn(intents=["price"], product_mentions=["bánh dâu"], reference=reference)])
    first = send("Tôi muốn đặt bánh socola", new_conversation(), connection, repository)
    old = deepcopy(first["conversation"])
    second = send("Bánh dâu giá bao nhiêu?", first["conversation"], connection, repository)
    assert product_ids(second) == [prefix + "-002"]
    assert second["conversation"]["order"] == old["order"]
    assert second["conversation"]["order"]["slots"]["product_id"] == prefix + "-001"
    assert "280.000 đ" in second["response"]["text"] and "250.000 đ" not in second["response"]["text"]
    assert second["current_turn"]["product_ids"] == [prefix + "-002"]
    assert second["conversation"]["conversation_context"]["focus_product_ids"] == [prefix + "-002"]
    assert len(second["conversation"]["history"]) == len(old["history"]) + 2
    assert first["conversation"] == old  # Không sửa input hoặc xóa history.
    assert "product_ids" not in second["conversation"]["needs"]["filters"]
    assert "current_turn" not in load_conversation(connection, old["id"])


@pytest.mark.parametrize("question,reference", [("bánh đó giá bao nhiêu?", "last"),
                                               ("loại vừa rồi giá bao nhiêu?", "last"),
                                               ("giá bao nhiêu?", "none")])
def test_B_clear_or_implicit_reference_to_draft(scope_db, make_turn, fake_model, question, reference):
    connection, repository = scope_db
    fake_model([start_order(make_turn), make_turn(intents=["price"], reference=reference)])
    first = send("Tôi muốn đặt bánh socola", new_conversation(), connection, repository)
    second = send(question, first["conversation"], connection, repository)
    assert product_ids(second) == ["demo-001"]
    assert second["conversation"]["order"] == first["conversation"]["order"]


def reviewed_conversation(connection, repository):
    current = new_conversation()
    values = {"product_id": "demo-001", "size": "16 cm", "toppings": [], "quantity": 1,
              "cake_text": "Chúc vui", "pickup_at": "2099-01-04 10:00", "fulfillment": "pickup",
              "name": "DEMO Khách A", "phone": "TEST-0001"}
    for field, value in values.items():
        current["order"] = update_slot(current["order"], field, value)
    with connection:
        save_conversation(connection, current)
    current["order"], _ = create_review(current["order"], create_order_tools(repository, connection, current["id"]))
    assert current["order"]["review"] is not None
    return current


def test_C_explicit_replace_invalidates_review_and_dependent_fields(scope_db, make_turn, fake_model):
    connection, repository = scope_db
    old = reviewed_conversation(connection, repository)
    fake_model([make_turn(intents=["order_request"], product_mentions=["bánh dâu"], reference="last", order_update=True)])
    turn = send("đổi sang bánh dâu", old, connection, repository)
    draft = turn["conversation"]["order"]
    assert draft["slots"]["product_id"] == "demo-002" and draft["review"] is None
    assert draft["revision"] > old["order"]["revision"]
    assert draft["slots"]["size"] is None and draft["slots"]["toppings"] is None
    assert draft["slots"]["quantity"] == 1 and draft["slots"]["cake_text"] == "Chúc vui"
    assert all(value == "unverified" for value in draft["verification"].values())
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 0
    assert old["order"]["review"] is not None  # Input không đổi.


def test_D_information_about_two_named_cakes_keeps_order(scope_db, make_turn, fake_model):
    connection, repository = scope_db
    current = reviewed_conversation(connection, repository)
    fake_model([make_turn(intents=["price"], product_mentions=["bánh dâu", "socola"], reference="last")])
    turn = send("Giá bánh dâu và socola?", current, connection, repository)
    assert set(product_ids(turn)) == {"demo-001", "demo-002"}
    assert "250.000 đ" in turn["response"]["text"] and "280.000 đ" in turn["response"]["text"]
    assert turn["conversation"]["order"] == current["order"]


def test_E_storage_about_other_cake_preserves_collecting_step(scope_db, make_turn, fake_model):
    connection, repository = scope_db
    fake_model([start_order(make_turn), make_turn(intents=["storage"], product_mentions=["bánh dâu"], reference="last")])
    first = send("Tôi muốn đặt bánh socola", new_conversation(), connection, repository)
    turn = send("Bảo quản bánh dâu thế nào?", first["conversation"], connection, repository)
    assert product_ids(turn) == ["demo-002"]
    assert repository.get_product("demo-002")["product"]["storage"] in turn["response"]["text"]
    assert turn["conversation"]["order"] == first["conversation"]["order"]
    assert turn["conversation"]["order"]["state"] == "COLLECTING"


def test_F_conversations_do_not_share_reference_or_draft(scope_db, make_turn, fake_model):
    connection, repository = scope_db
    fake_model([start_order(make_turn), start_order(make_turn, "dâu"),
                make_turn(intents=["price"], reference="last"), make_turn(intents=["price"], reference="last")])
    a = send("Tôi muốn đặt bánh socola", new_conversation("scope-A"), connection, repository)
    b = send("Tôi muốn đặt bánh dâu", new_conversation("scope-B"), connection, repository)
    a2 = send("bánh đó giá bao nhiêu?", a["conversation"], connection, repository)
    b2 = send("bánh đó giá bao nhiêu?", b["conversation"], connection, repository)
    assert product_ids(a2) == ["demo-001"] and product_ids(b2) == ["demo-002"]
    assert load_conversation(connection, "scope-A")["order"]["slots"]["product_id"] == "demo-001"
    assert load_conversation(connection, "scope-B")["order"]["slots"]["product_id"] == "demo-002"
    a2["current_turn"]["product_ids"].append("demo-025")
    assert a2["conversation"]["conversation_context"]["focus_product_ids"] == ["demo-001"]
    assert b2["conversation"]["conversation_context"]["focus_product_ids"] == ["demo-002"]


def test_ambiguous_reference_between_topic_and_order_asks(scope_db, make_turn, fake_model):
    connection, repository = scope_db
    fake_model([start_order(make_turn), make_turn(intents=["price"], product_mentions=["bánh dâu"]),
                make_turn(intents=["price"], reference="last")])
    first = send("Tôi muốn đặt bánh socola", new_conversation(), connection, repository)
    second = send("Bánh dâu giá bao nhiêu?", first["conversation"], connection, repository)
    turn = send("bánh đó giá bao nhiêu?", second["conversation"], connection, repository)
    assert turn["response"]["requires_clarification"] and not product_ids(turn)
    assert turn["conversation"]["order"] == second["conversation"]["order"]


def test_explicit_order_reference_does_not_choose_other_topic(scope_db, make_turn, fake_model):
    connection, repository = scope_db
    current = reviewed_conversation(connection, repository)
    current["conversation_context"]["focus_product_ids"] = ["demo-002"]
    fake_model([make_turn(intents=["price"], reference="order")])
    turn = send("bánh trong đơn của tôi giá bao nhiêu?", current, connection, repository)
    assert product_ids(turn) == ["demo-001"] and turn["conversation"]["order"] == current["order"]


def test_price_question_cannot_edit_review_even_if_model_sets_edit_flag(scope_db, make_turn, fake_model):
    connection, repository = scope_db
    current = reviewed_conversation(connection, repository)
    fake_model([make_turn(intents=["price"], product_mentions=["bánh dâu"], updates={"size": "20 cm"}, order_update=True)])
    turn = send("Bánh dâu size 20 cm giá bao nhiêu?", current, connection, repository)
    assert product_ids(turn) == ["demo-002"]
    assert turn["response"]["products"][0]["variants"][0]["price_vnd"] == 380000
    assert turn["conversation"]["order"] == current["order"]


def test_unknown_named_cake_never_falls_back_to_order(scope_db, make_turn, fake_model):
    connection, repository = scope_db
    current = reviewed_conversation(connection, repository)
    fake_model([make_turn(intents=["price"], product_mentions=["bánh sầu riêng"], reference="last")])
    turn = send("bánh sầu riêng giá bao nhiêu?", current, connection, repository)
    assert not product_ids(turn) and turn["response"]["catalog_status"] == "no_results"
    assert turn["conversation"]["order"] == current["order"]


def test_empty_mode_preserves_unverified_need_without_inventing_price(scope_db, make_turn, fake_model):
    connection, _ = scope_db
    repository = EmptyCatalogRepository()
    fake_model([start_order(make_turn), make_turn(intents=["price"], product_mentions=["bánh dâu"], reference="last")])
    first = send("Tôi muốn đặt bánh socola", new_conversation(), connection, repository)
    turn = send("Bánh dâu giá bao nhiêu?", first["conversation"], connection, repository)
    assert turn["conversation"]["order"] == first["conversation"]["order"]
    assert turn["conversation"]["order"]["slots"]["product_id"] is None
    assert turn["conversation"]["order"]["slots"]["cake_need"] == "bánh socola"
    assert not product_ids(turn) and turn["response"]["catalog_status"] == "unconfigured"
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 0


def test_bare_price_without_referent_asks_instead_of_listing_menu(scope_db, make_turn, fake_model):
    connection, repository = scope_db
    fake_model([make_turn(intents=["price"])])
    turn = send("giá bao nhiêu?", new_conversation(), connection, repository)
    assert turn["response"]["requires_clarification"] and not product_ids(turn)


def test_prompt_separates_current_mentions_topic_and_draft(scope_db, make_turn, monkeypatch):
    connection, repository = scope_db
    current = reviewed_conversation(connection, repository)
    current["conversation_context"]["focus_product_ids"] = ["demo-002"]
    calls = []
    data = make_turn(intents=["price"], product_mentions=["bánh dâu"]).model_dump()
    data["updates"] = []
    monkeypatch.setattr(llm_client, "chat", lambda *args: calls.append(args) or {"ok": True, "content": json.dumps(data)})
    result = llm_client.extract_turn("Bánh dâu giá bao nhiêu?", current, "http://localhost:11434", "fake", repository=repository)
    context = json.loads(calls[0][0][-1]["content"])["context"]
    assert context["order_draft"]["product_selected"] is True
    assert context["conversation_context"]["focused_product_count"] == 1
    assert context["conversation_context"]["focus_is_order_product"] is False
    assert "socola" not in json.dumps(context,ensure_ascii=False)
    assert result["data"].product_mentions == ["bánh dâu"]
    assert "TEST-0001" not in json.dumps(context, ensure_ascii=False)


def test_all_six_explicitly_named_cakes_are_returned(scope_db, make_turn, fake_model):
    connection, repository = scope_db
    identifiers = ["demo-001", "demo-002", "demo-003", "demo-005", "demo-006", "demo-007"]
    names = [repository.get_product(identifier)["product"]["name"] for identifier in identifiers]
    fake_model([make_turn(intents=["price"], product_mentions=names)])
    turn = send("Giá " + " và ".join(names) + "?", new_conversation(), connection, repository)
    assert set(product_ids(turn)) == set(identifiers)


def test_known_and_unknown_named_cakes_report_missing_one(scope_db, make_turn, fake_model):
    connection, repository = scope_db
    fake_model([make_turn(intents=["price"], product_mentions=["bánh dâu", "bánh sầu riêng"], reference="last")])
    turn = send("Giá bánh dâu và bánh sầu riêng?", new_conversation(), connection, repository)
    assert product_ids(turn) == ["demo-002"]
    assert "Chưa tìm thấy dữ liệu cho: bánh sầu riêng" in turn["response"]["text"]


def test_explicit_allergy_in_information_turn_remains_a_safety_constraint(scope_db, make_turn, fake_model):
    connection, repository = scope_db
    fake_model([make_turn(intents=["allergen"], product_mentions=["bánh dâu"], updates={"allergens": ["sữa"]}),
                make_turn(intents=["recommendation"], updates={"budget_vnd": 400000})])
    first = send("Tôi dị ứng sữa, bánh dâu có gì gây dị ứng?", new_conversation(), connection, repository)
    assert first["conversation"]["needs"]["filters"]["exclude_allergens"] == ["sữa"]
    second = send("Tư vấn bánh dưới 400k", first["conversation"], connection, repository)
    assert not product_ids(second)
    assert second["conversation"]["needs"]["filters"]["exclude_allergens"] == ["sữa"]
