"""Nhãn tĩnh + LLM fake kiểm tra scope/slot/FSM; không đo model thật."""

from copy import deepcopy
from pathlib import Path
import json

import pytest
from pydantic import ValidationError

from app import llm_client
from app.conversation import handle_message, new_conversation
from app.order_service import create_order_tools
from app.repositories.empty_catalog import EmptyCatalogRepository
from app.repositories.local_catalog import LocalCatalogRepository
from app.repositories.mock_catalog import MockCatalogRepository
from app.schemas import LLMTurn, LLMWireTurn
from app.storage import open_storage
from scripts.database import seed_database
from scripts.evaluate_intent_context import load_dataset, score_turn, summarize

ROOT = Path(__file__).resolve().parents[1]
DEV = load_dataset("dev")[0]
FINAL = load_dataset("test")[0]


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "intent context có dấu.sqlite3"
    connection = open_storage(path)
    seed_database(connection)
    yield path, connection, LocalCatalogRepository(path)
    connection.close()


def send(message, current, connection, repository):
    return handle_message(message, repository, current, chat_mode="ollama", storage_connection=connection,
                          order_tools=create_order_tools(repository, connection, current["id"]))


def test_dataset_counts_ids_and_split_are_disjoint():
    dev = [t for d in DEV["dialogues"] for t in d["turns"]]
    final = [t for d in FINAL["dialogues"] for t in d["turns"]]
    assert len(dev) == 48 and len(final) == 26
    assert not {t["id"] for t in dev} & {t["id"] for t in final}
    assert not {t["message"] for t in dev} & {t["message"] for t in final}
    for item in dev + final:
        LLMTurn.model_validate(item["label"])


@pytest.mark.parametrize("dialogue", DEV["dialogues"] + FINAL["dialogues"], ids=lambda d:d["id"])
def test_labelled_dialogues_with_fake_nlu(dialogue, source, fake_model):
    _, connection, repository = source
    repository = {"empty": EmptyCatalogRepository, "mock": MockCatalogRepository}.get(dialogue["mode"], lambda:repository)()
    fake_model([LLMTurn.model_validate(item["label"]) for item in dialogue["turns"]])
    current = new_conversation()
    for item in dialogue["turns"]:
        previous = deepcopy(current["order"])
        result = send(item["message"], current, connection, repository)
        current = result["conversation"]
        count = connection.execute("SELECT count(*) FROM orders WHERE conversation_id=?", (current["id"],)).fetchone()[0]
        score = score_turn(item, result, item["label"], previous, count)
        assert score["behavior_pass"], (item["id"], score["behavior"], result["response"]["text"])
        assert result["engine"] == "ollama"


def test_intents_bound_to_separate_products(source, make_turn, fake_model):
    _, connection, repository = source
    fake_model([make_turn(intents=["price", "flavor"], product_mentions=["dâu", "socola"], requests=[
        {"intents":["price"], "product_mentions":["dâu"]},
        {"intents":["flavor"], "product_mentions":["socola"]}])])
    result = send("Giá dâu và hương vị socola?", new_conversation(), connection, repository)
    text = result["response"]["text"]
    assert "280.000" in text and "Hương vị: socola" in text
    assert "250.000" not in text and "350.000" not in text
    scopes = result["current_turn"]["requests"]
    assert scopes[0]["product_ids"] == ["demo-002"] and scopes[1]["product_ids"] == ["demo-001"]


def test_query_sizes_do_not_cross_products(source, make_turn, fake_model):
    _, connection, repository = source
    fake_model([make_turn(intents=["price"], product_mentions=["dâu", "socola"], requests=[
        {"intents":["price"], "product_mentions":["dâu"], "size":"16 cm"},
        {"intents":["price"], "product_mentions":["socola"], "size":"20 cm"}])])
    result = send("Giá dâu 16 cm và socola 20 cm?", new_conversation(), connection, repository)
    assert "280.000" in result["response"]["text"] and "350.000" in result["response"]["text"]
    assert "380.000" not in result["response"]["text"] and "250.000" not in result["response"]["text"]


def test_mixed_order_change_and_question_have_different_targets(source, make_turn, fake_model):
    _, connection, repository = source
    fake_model([
        make_turn(intents=["order_request"],action="start_order",product_mentions=["socola"],order_update=True),
        make_turn(intents=["order_request","price"],product_mentions=["socola","dâu","vani"],
            order_product_mentions=["dâu"],order_update=True,updates={"size":"16 cm"},
            requests=[{"intents":["price"],"product_mentions":["vani"],"size":"20 cm"}]),
    ])
    initial = send("Tôi đặt socola", new_conversation(), connection, repository)["conversation"]
    result = send("Đổi socola sang dâu size 16 cm và hỏi giá vani 20 cm", initial, connection, repository)
    assert result["conversation"]["order"]["slots"]["product_id"] == "demo-002"
    assert result["conversation"]["order"]["slots"]["size"] == "16 cm"
    assert [p["id"] for p in result["response"]["products"]] == ["demo-003"]
    assert "320.000" in result["response"]["text"] and "220.000" not in result["response"]["text"]
    assert result["current_turn"]["order_product_ids"] == ["demo-002"]


def test_negated_cake_not_added_to_query_or_draft(source, make_turn, fake_model):
    _, connection, repository = source
    fake_model([make_turn(intents=["price"],product_mentions=["socola","vani"],requests=[
        {"intents":["price"],"product_mentions":["vani"]}])])
    original = new_conversation()
    result = send("Không cần socola, xem giá vani", original, connection, repository)
    assert [p["id"] for p in result["response"]["products"]] == ["demo-003"]
    assert result["conversation"]["order"] == original["order"]


def test_bad_reference_does_not_bypass_catalog_mention_guard(monkeypatch, source):
    _, _, repository = source
    from app.order_nlu import check_catalog_grounding
    proposal = LLMTurn(intents=["availability"],action="none",product_mentions=[],reference="last",
                       updates={},clear_slots=[],ambiguous=False,handoff_reason="none")
    assert check_catalog_grounding("Bánh trà xanh còn hàng không?", proposal, repository) == "missing_catalog_mention"


def test_invalid_request_cannot_modify_draft(source, make_turn, fake_model):
    _, connection, repository = source
    fake_model([make_turn(intents=["price"],product_mentions=["dâu"],requests=[
        {"intents":["price"],"product_mentions":["vani"]}])])
    original = new_conversation()
    result = send("Giá dâu?", original, connection, repository)
    assert result["engine"] == "llm_error" and result["conversation"]["order"] == original["order"]
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 0


def test_few_shots_are_valid_abstract_and_do_not_read_final_labels(monkeypatch):
    examples = json.loads((ROOT / "data/nlu_few_shots.json").read_text(encoding="utf-8"))["examples"]
    for example in examples:
        LLMWireTurn.model_validate(example["output"])
    original = Path.read_text
    paths = []
    def tracked(path, *args, **kwargs):
        paths.append(path)
        assert "evaluation" not in path.parts
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,"read_text",tracked)
    messages = llm_client.build_turn_messages("Xin chào",new_conversation(),EmptyCatalogRepository())
    text = json.dumps(messages,ensure_ascii=False)
    final_messages = [t["message"] for d in FINAL["dialogues"] for t in d["turns"]]
    assert all(message not in text for message in final_messages)
    assert paths == [ROOT / "data/nlu_few_shots.json"]


def test_pydantic_rejects_request_ids_and_undeclared_intents(make_turn):
    with pytest.raises(ValidationError):
        make_turn(intents=["price"],requests=[{"intents":["price"],"product_mentions":[],"product_id":"demo-001"}])
    with pytest.raises(ValidationError):
        make_turn(intents=["price"],requests=[{"intents":["flavor"],"product_mentions":["vani"]}])


def test_summary_does_not_drop_model_failures():
    step = {"score":{"extraction":{"schema_grounding_ok":False},"behavior":{"draft_unchanged":True},
                     "extraction_pass":False,"behavior_pass":True},"label":{"intents":["price"]},
            "proposal":None,"engine":"llm_error"}
    summary = summarize([step])
    assert summary["model_errors"] == 1 and summary["intent_micro_f1"] == 0
    assert summary["metrics"]["schema_grounding_ok"]["rate"] == 0


def test_stock_question_does_not_filter_out_sold_out_product(source, make_turn, fake_model):
    _, connection, repository = source
    fake_model([make_turn(intents=["availability"],product_mentions=["trà xanh"],updates={"available_only":True},
        requests=[{"intents":["availability"],"product_mentions":["trà xanh"]}])])
    result = send("Bánh trà xanh còn hàng không?",new_conversation(),connection,repository)
    assert "hết hàng" in result["response"]["text"]
    assert [p["id"] for p in result["response"]["products"]] == ["demo-004"]


def test_topic_change_does_not_clear_known_allergy(source, make_turn, fake_model):
    _, connection, repository = source
    fake_model([make_turn(intents=["recommendation"],product_mentions=["socola"] )])
    current = new_conversation()
    current["needs"]["filters"]["exclude_allergens"] = ["sữa"]
    result = send("Tư vấn bánh socola", current, connection, repository)
    assert result["conversation"]["needs"]["filters"]["exclude_allergens"] == ["sữa"]
    assert result["response"]["products"] == []


def test_second_query_source_error_keeps_draft_and_does_not_return_partial_success(source, make_turn, fake_model):
    _, connection, repository = source
    fake_model([make_turn(intents=["price"],product_mentions=["dâu","vani"],requests=[
        {"intents":["price"],"product_mentions":["dâu"]},{"intents":["price"],"product_mentions":["vani"]}])])
    original_search = repository.search_products
    def search(filters):
        if filters.get("product_ids") == ["demo-003"]:
            return {"status":"error","products":[],"data_mode":"local_demo","error":"upstream_down"}
        return original_search(filters)
    repository.search_products = search
    current = new_conversation()
    result = send("Giá dâu và vani",current,connection,repository)
    assert result["engine"] == "source_error"
    assert result["conversation"]["order"] == current["order"] and result["response"]["products"] == []


def test_mixed_start_without_declared_order_target_asks_instead_of_guessing(source, make_turn, fake_model):
    _, connection, repository = source
    fake_model([make_turn(intents=["order_request","price"],action="start_order",order_update=True,
        product_mentions=["dâu","vani"],requests=[{"intents":["price"],"product_mentions":["vani"]}])])
    current = new_conversation()
    result = send("Đặt dâu và hỏi giá vani",current,connection,repository)
    assert result["response"]["requires_clarification"] and result["conversation"]["order"] == current["order"]


def test_invalid_few_shot_file_returns_error_without_draft_write(monkeypatch, source):
    _, connection, repository = source
    monkeypatch.setattr(llm_client,"select_model",lambda *args:{"model":"fake","error":None})
    def broken(*args):
        raise OSError("Cannot read examples")
    monkeypatch.setattr(llm_client,"build_turn_messages",broken)
    current = new_conversation()
    result = send("Tôi đặt socola",current,connection,repository)
    assert result["llm_error"] == "invalid_prompt_examples" and result["conversation"]["order"] == current["order"]


def test_canonical_mention_requires_alias_of_same_catalog_product_in_current_message(source, make_turn, fake_model):
    _, connection, repository = source
    fake_model([make_turn(intents=["price"],product_mentions=["Bánh kem socola"],requests=[
        {"intents":["price"],"product_mentions":["Bánh kem socola"]}])])
    result = send("Giá chocolate?",new_conversation(),connection,repository)
    assert [p["id"] for p in result["response"]["products"]] == ["demo-001"]
    from app.order_nlu import check_catalog_grounding, check_turn_grounding
    proposal=make_turn(intents=["price"],product_mentions=["Bánh kem socola"])
    assert check_catalog_grounding("Giá chocolate?",proposal,repository) is None
    assert check_turn_grounding("Giá dâu?",proposal,repository) == "invalid_turn_mention"


def test_adding_product_does_not_replace_existing_draft(source, make_turn, fake_model):
    _, connection, repository = source
    fake_model([make_turn(intents=["order_request"],action="start_order",product_mentions=["socola"],order_update=True),
        make_turn(intents=["order_request"],product_mentions=["dâu"],order_product_mentions=["dâu"],order_operation="add_product",order_update=True)])
    current=send("Tôi đặt socola",new_conversation(),connection,repository)["conversation"]
    result=send("Thêm bánh dâu",current,connection,repository)
    assert result["response"]["requires_clarification"]
    assert result["conversation"]["order"] == current["order"]


def test_remove_only_the_matching_draft_product(source, make_turn, fake_model):
    _, connection, repository = source
    fake_model([make_turn(intents=["order_request"],action="start_order",product_mentions=["socola"],order_update=True),
        make_turn(intents=["order_request"],product_mentions=["dâu"],order_product_mentions=["dâu"],order_operation="remove_product"),
        make_turn(intents=["order_request"],product_mentions=["socola"],order_product_mentions=["socola"],order_operation="remove_product")])
    current=send("Tôi đặt socola",new_conversation(),connection,repository)["conversation"]
    wrong=send("Bỏ bánh dâu",current,connection,repository)
    assert wrong["response"]["requires_clarification"] and wrong["conversation"]["order"] == current["order"]
    right=send("Bỏ bánh socola",current,connection,repository)
    assert right["conversation"]["order"]["slots"]["product_id"] is None
    assert right["conversation"]["order"]["revision"] > current["order"]["revision"]


def test_lettering_is_not_a_product_delete_command(source, make_turn, fake_model):
    _, connection, repository = source
    fake_model([make_turn(intents=["order_request"],reference="order",order_operation="remove_product",clear_slots=["product"])])
    current = new_conversation()
    current["order"]["slots"]["product_id"] = "demo-002"
    result = send("Ghi chữ 'bỏ bánh dâu'",current,connection,repository)
    assert result["engine"] == "llm_error" and result["conversation"]["order"] == current["order"]


def test_canonical_expansion_does_not_resolve_an_ambiguous_alias(source, make_turn, fake_model):
    _, connection, repository = source
    original_search = repository.search_products
    def search(filters):
        result = original_search(filters)
        for product in result["products"][:2]:
            product["aliases"].append("bánh chung")
        return result
    repository.search_products = search
    fake_model([make_turn(intents=["price"],product_mentions=["Bánh kem socola"]),
                make_turn(intents=["price"],product_mentions=["bánh chung"])])
    unsafe = send("Giá bánh chung",new_conversation(),connection,repository)
    assert unsafe["engine"] == "llm_error" and unsafe["response"]["products"] == []
    clear = send("Giá bánh chung",new_conversation(),connection,repository)
    assert clear["response"]["requires_clarification"] and clear["response"]["products"] == []


def test_optional_cake_prefix_in_conjoined_mentions(source,make_turn,fake_model):
    _,connection,repository = source
    fake_model([make_turn(intents=["price"],product_mentions=["bánh dâu","bánh socola"],requests=[
        {"intents":["price"],"product_mentions":["bánh dâu","bánh socola"]}])])
    result=send("Giá bánh dâu và socola?",new_conversation(),connection,repository)
    assert {p["id"] for p in result["response"]["products"]} == {"demo-001","demo-002"}
    assert result["engine"] == "ollama"


def test_prompt_examples_are_bounded_by_fsm():
    for state in ["BROWSING","COLLECTING","REVIEW","HANDOFF"]:
        current=new_conversation()
        current["order"]["state"]=state
        messages=llm_client.build_turn_messages("Thử",current,EmptyCatalogRepository())
        assert sum(item["role"] == "assistant" for item in messages) <= 3


def test_prompt_schema_keeps_constraints_and_actual_property_names():
    schema={"type":"object","title":"Outer","properties":{"description":{"type":"string","maxLength":7,"description":"Doc"}}}
    original=deepcopy(schema)
    compact=llm_client.schema_for_prompt(schema)
    assert compact["properties"]["description"] == {"type":"string","maxLength":7}
    assert schema == original


def test_old_names_preferences_and_bot_questions_do_not_leak_to_model_context(source):
    _,_,repository=source
    current=new_conversation()
    current["order"]["slots"]["product_id"]="demo-001"
    current["conversation_context"]["focus_product_ids"]=["demo-001"]
    current["shown_products"]=[repository.get_product("demo-001")["product"]]
    current["needs"]["filters"]={"flavor":"socola","max_price_vnd":400000}
    current["history"]=[{"role":"assistant","content":"Bạn muốn size bánh socola?"}]
    original=deepcopy(current)
    context=json.loads(llm_client.build_turn_messages("Bánh dâu giá bao nhiêu?",current,repository)[-1]["content"])["context"]
    assert context["current_message_catalog_aliases"] == ["dau"]
    assert context["conversation_context"]["focus_is_order_product"] is True
    assert context["conversation_context"]["shown_product_count"] == 1
    assert "socola" not in json.dumps(context,ensure_ascii=False)
    assert "400000" not in json.dumps(context,ensure_ascii=False)
    assert "recent_bot_questions" not in context
    assert current == original


def test_empty_duplicate_request_cannot_add_a_historical_product(source,make_turn,fake_model):
    _,connection,repository=source
    fake_model([make_turn(intents=["price","size"],requests=[
        {"intents":["price","size"],"product_mentions":["dâu"]},
        {"intents":["price","size"],"product_mentions":[],"reference":"last"}])])
    current=new_conversation()
    current["order"]["slots"]["product_id"]="demo-001"
    current["order"]["state"]="COLLECTING"
    current["conversation_context"]["focus_product_ids"]=["demo-003"]
    result=send("Giá và size bánh dâu?",current,connection,repository)
    assert [p["id"] for p in result["response"]["products"]] == ["demo-002"]
    assert len(result["current_turn"]["requests"]) == 1
    assert result["conversation"]["order"] == current["order"]


def test_explicit_order_reference_can_query_another_cake_and_the_draft(source,make_turn,fake_model):
    _,connection,repository=source
    fake_model([make_turn(intents=["price"],product_mentions=["dâu"],requests=[
        {"intents":["price"],"product_mentions":["dâu"]},
        {"intents":["price"],"product_mentions":[],"reference":"order"}])])
    current=new_conversation()
    current["order"]["slots"]["product_id"]="demo-001"
    current["order"]["state"]="COLLECTING"
    result=send("Giá bánh dâu và bánh trong đơn?",current,connection,repository)
    assert {p["id"] for p in result["response"]["products"]} == {"demo-001","demo-002"}
    assert result["conversation"]["order"] == current["order"]


def test_unlinked_request_with_multiple_current_subjects_asks_instead_of_using_history(source,make_turn,fake_model):
    _,connection,repository=source
    fake_model([make_turn(intents=["price","flavor"],product_mentions=["dâu","vani"],requests=[
        {"intents":["price"],"product_mentions":["dâu","vani"]},
        {"intents":["flavor"],"product_mentions":[],"reference":"last"}])])
    current=new_conversation()
    current["conversation_context"]["focus_product_ids"]=["demo-001"]
    result=send("Giá dâu và vani, hương vị thế nào?",current,connection,repository)
    assert result["response"]["requires_clarification"] and result["response"]["products"] == []
    assert result["conversation"]["order"] == current["order"]


def test_unverified_reference_phrase_is_not_reported_as_a_missing_catalog_product(source,make_turn,fake_model):
    _,connection,repository=source
    fake_model([make_turn(intents=["price"],product_mentions=["bánh đó"],reference="last",requests=[
        {"intents":["price"],"product_mentions":["bánh đó"],"reference":"last"}])])
    current=new_conversation()
    current["conversation_context"]["focus_product_ids"]=["demo-001","demo-002"]
    result=send("Bánh đó giá bao nhiêu?",current,connection,repository)
    assert result["response"]["requires_clarification"] and result["response"]["products"] == []
    assert result["conversation"]["order"] == current["order"]


def test_recommendation_flag_cannot_change_order_draft(source,make_turn,fake_model):
    _,connection,repository = source
    fake_model([make_turn(intents=["recommendation"],product_mentions=["dâu"],order_update=True,updates={"cake_need":"dâu"})])
    current=new_conversation()
    current["order"]["slots"]["product_id"]="demo-001"
    current["order"]["state"]="COLLECTING"
    result=send("Tư vấn bánh dâu",current,connection,repository)
    assert result["conversation"]["order"] == current["order"]
    assert result["current_turn"]["order_product_ids"] == []


def test_general_recommendation_does_not_use_draft_as_an_implicit_reference(source,make_turn,fake_model):
    _,connection,repository = source
    fake_model([make_turn(intents=["recommendation"],updates={"budget_vnd":300000,"price_inclusive":False})])
    current=new_conversation()
    current["order"]["slots"]["product_id"]="demo-001"
    current["order"]["state"]="COLLECTING"
    result=send("Tư vấn các bánh dưới 300k",current,connection,repository)
    assert len(result["response"]["products"]) > 1
    assert result["current_turn"]["product_ids"] == []
    assert result["conversation"]["order"] == current["order"]


def reviewed_conversation(connection, repository):
    from app.order_flow import create_review, update_slot
    from app.storage import save_conversation
    current = new_conversation()
    values = dict(product_id="demo-001",size="16 cm",quantity=1,toppings=[],cake_text="",
        pickup_at="2099-02-01 10:00",fulfillment="pickup",name="DEMO Khách Z",phone="TEST-Z1")
    for field, value in values.items():
        current["order"] = update_slot(current["order"], field, value)
    save_conversation(connection,current)
    connection.commit()
    current["order"], _ = create_review(current["order"],create_order_tools(repository,connection,current["id"]))
    assert current["order"]["review"]
    return current


def test_unresolved_addition_invalidates_previous_review(source, make_turn, fake_model):
    _, connection, repository = source
    current = reviewed_conversation(connection,repository)
    fake_model([make_turn(intents=["order_request"],product_mentions=["dâu"],order_product_mentions=["dâu"],order_operation="add_product")])
    result = send("Thêm bánh dâu",current,connection,repository)
    assert result["response"]["requires_clarification"]
    assert result["conversation"]["order"]["slots"] == current["order"]["slots"]
    assert result["conversation"]["order"]["review"] is None
    assert result["conversation"]["order"]["revision"] > current["order"]["revision"]
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 0


def test_operation_on_confirmed_order_goes_to_handoff_even_without_update_flag(source,make_turn,fake_model):
    from app.order_flow import confirm_review
    _,connection,repository = source
    current = reviewed_conversation(connection,repository)
    tools = create_order_tools(repository,connection,current["id"])
    current["order"],_ = confirm_review(current["order"],tools,current["needs"])
    connection.commit()
    assert current["order"]["submission"]["confirmed"]
    fake_model([make_turn(intents=["order_request"],product_mentions=["socola"],order_product_mentions=["socola"],order_operation="remove_product")])
    result = send("Bỏ bánh socola",current,connection,repository)
    assert result["conversation"]["order"]["state"] == "HANDOFF"
    assert result["conversation"]["order"]["slots"] == current["order"]["slots"]
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 1
