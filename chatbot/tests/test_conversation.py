"""NLU/hội thoại mới dùng LLMTurn fake; không gọi model thật."""

from copy import deepcopy
import json

import pytest

from app import llm_client
from app.conversation import handle_message, new_conversation
from app.repositories.empty_catalog import EmptyCatalogRepository
from app.repositories.mock_catalog import MockCatalogRepository
from app.schemas import LLMTurn


@pytest.mark.parametrize("repo_class,status", [(EmptyCatalogRepository, "unconfigured"), (MockCatalogRepository, "success")])
def test_needs_then_budget_delta_preserves_preferences(make_turn, fake_model, repo_class, status):
    fake_model([make_turn(updates={"flavor":"socola","servings":6,"budget_vnd":300000,"price_inclusive":False}),
                make_turn(updates={"budget_vnd":400000})])
    repo=repo_class(); original=new_conversation()
    first=handle_message("socola cho 6 người dưới 300k",repo,original)
    second=handle_message("tăng ngân sách lên 400k",repo,first["conversation"])
    filters=second["conversation"]["needs"]["filters"]
    assert filters["flavor"]=="socola" and filters["servings"]==6 and filters["max_price_vnd"]==400000
    assert second["engine"]=="ollama" and second["response"]["catalog_status"]==status
    assert original["needs"]["filters"]=={} and original["history"]==[]


def test_histories_are_separate_and_bounded(make_turn,fake_model):
    seen=fake_model([make_turn(updates={"flavor":"socola"}), make_turn(updates={"flavor":"dâu"}),
                     make_turn(updates={"budget_vnd":400000}),make_turn(intents=["greeting"])])
    repo=EmptyCatalogRepository()
    a=handle_message("socola",repo,new_conversation("A",max_turns=1))["conversation"]
    b=handle_message("dâu",repo,new_conversation("B"))["conversation"]
    a2=handle_message("400k",repo,a)["conversation"]
    a3=handle_message("xin chào",repo,a2)["conversation"]
    assert seen[2][1]["id"]=="A" and not any(item["content"]=="dâu" for item in seen[2][1]["history"])
    assert len(a3["history"])==2 and a3["needs"]["filters"]["flavor"]=="socola"
    assert b["needs"]["filters"]["flavor"]=="dâu"
    assert "socola" not in a3["history"][-1]["content"]  # chào không lặp nhu cầu cũ


@pytest.mark.parametrize("error",["timeout","connection_error","model_not_found"])
def test_model_error_has_no_silent_rule_updates(monkeypatch,error):
    monkeypatch.setattr(llm_client,"select_model",lambda *a:{"model":None,"error":error})
    original=new_conversation()
    original["needs"]["filters"]={"flavor":"dâu"}
    turn=handle_message("socola dưới 300k",EmptyCatalogRepository(),original)
    assert turn["engine"]=="llm_error" and turn["llm_error"]==error
    assert turn["conversation"]==original and turn["response"]["products"]==[]


def test_json_repair_only_once(monkeypatch):
    calls=[]
    monkeypatch.setattr(llm_client,"chat",lambda *args: calls.append(args) or {"ok":True,"content":"bad"})
    result=llm_client.extract_turn("đặt bánh",new_conversation(),"http://localhost:11434","fake")
    assert result["error"]=="invalid_turn_json" and result["attempts"]==2 and len(calls)==2


def test_json_repair_can_succeed(monkeypatch,make_turn):
    data=make_turn(intents=["greeting"]).model_dump(); data["updates"]=[]
    outputs=iter(["bad",json.dumps(data)])
    monkeypatch.setattr(llm_client,"chat",lambda *args:{"ok":True,"content":next(outputs)})
    result=llm_client.extract_turn("xin chào",new_conversation(),"http://localhost:11434","fake")
    assert result["error"] is None and result["attempts"]==2


def test_turn_schema_rejects_model_product_id(make_turn):
    data=make_turn().model_dump(); data["product_id"]="invented"
    with pytest.raises(ValueError):
        LLMTurn.model_validate(data)


@pytest.mark.parametrize("updates,message",[
    ({"servings":6},"tăng ngân sách lên 400k"),
    ({"flavor":"socola"},"xin chào"),
    ({"quantity":9},"hai bánh"),
])
def test_ungrounded_attributes_do_not_overwrite_state(make_turn,fake_model,updates,message):
    fake_model([make_turn(updates=updates)])
    original=new_conversation()
    turn=handle_message(message,EmptyCatalogRepository(),original)
    assert turn["engine"]=="llm_error" and turn["conversation"]==original


def test_mentions_must_come_from_message(make_turn,fake_model):
    fake_model([make_turn(product_mentions=["bánh tự bịa"])])
    original=new_conversation()
    turn=handle_message("bánh socola",MockCatalogRepository(),original)
    assert turn["llm_error"]=="invalid_turn_mention" and turn["conversation"]==original


def test_literal_unknown_mention_does_not_become_product_id(make_turn,fake_model):
    fake_model([make_turn(intents=["price"],product_mentions=["bánh sầu riêng"])])
    turn=handle_message("giá bánh sầu riêng",MockCatalogRepository(),new_conversation())
    assert turn["response"]["products"]==[] and turn["response"]["catalog_status"]=="no_results"


def test_named_product_is_resolved_by_repository(make_turn,fake_model):
    fake_model([make_turn(intents=["price","size"],product_mentions=["bánh socola"])])
    turn=handle_message("giá và size bánh socola",MockCatalogRepository(),new_conversation())
    assert turn["response"]["products"][0]["id"]=="mock-001"
    assert "250.000 đ" in turn["response"]["text"] and "350.000 đ" in turn["response"]["text"]


def test_repository_error_remains_error_after_model_understands(monkeypatch,make_turn,fake_model):
    fake_model([make_turn(intents=["price"])])
    repo=MockCatalogRepository()
    monkeypatch.setattr(repo,"search_products",lambda *a:{"status":"error","products":[],"error":"source_error"})
    turn=handle_message("giá bánh",repo,new_conversation())
    assert turn["engine"]=="source_error" and turn["response"]["catalog_status"]=="error"
    assert turn["response"]["products"]==[]


def test_ambiguous_proposal_does_not_change_needs(make_turn,fake_model):
    fake_model([make_turn(ambiguous=True,product_mentions=["socola","dâu"],updates={"servings":6})])
    original=new_conversation()
    turn=handle_message("socola dâu cho 6 người",MockCatalogRepository(),original)
    assert turn["response"]["requires_clarification"] and turn["conversation"]["needs"]==original["needs"]


def test_explicit_clear_is_different_from_unmentioned(make_turn,fake_model):
    fake_model([make_turn(updates={"flavor":"socola","budget_vnd":300000}),
                make_turn(clear_slots=["budget_vnd"])])
    first=handle_message("socola dưới 300k",EmptyCatalogRepository(),new_conversation())
    second=handle_message("bỏ ngân sách",EmptyCatalogRepository(),first["conversation"])
    assert "max_price_vnd" not in second["conversation"]["needs"]["filters"]
    assert second["conversation"]["needs"]["filters"]["flavor"]=="socola"


def test_browsing_new_budget_drops_old_named_query(make_turn,fake_model):
    fake_model([make_turn(intents=["price"],product_mentions=["bánh sầu riêng"]),
                make_turn(updates={"budget_vnd":300000})])
    repo=MockCatalogRepository()
    first=handle_message("giá bánh sầu riêng",repo,new_conversation())
    second=handle_message("các loại bánh dưới 300k",repo,first["conversation"])
    assert "query" not in second["conversation"]["needs"]["filters"]
    assert second["response"]["products"]


def test_rule_is_explicit_offline_and_never_calls_model(monkeypatch):
    monkeypatch.setattr(llm_client,"select_model",lambda *a:pytest.fail("rule không gọi model"))
    turn=handle_message("socola dưới 300k",MockCatalogRepository(),new_conversation(),chat_mode="rule")
    assert turn["engine"]=="rule" and turn["response"]["products"]


@pytest.mark.parametrize("limit",[0,21,True,1.5])
def test_invalid_history_limit(limit):
    with pytest.raises(ValueError):
        new_conversation(max_turns=limit)


def test_reset_factory_has_no_shared_mutables():
    a,b=new_conversation(),new_conversation()
    a["needs"]["filters"]["flavor"]="socola"
    assert b["needs"]["filters"]=={} and a["id"]!=b["id"]


def test_context_does_not_send_contact_or_catalog_ids(monkeypatch,make_turn):
    calls=[]
    data=make_turn(intents=["greeting"]).model_dump(); data["updates"]=[]
    monkeypatch.setattr(llm_client,"chat",lambda *args:calls.append(args) or {"ok":True,"content":json.dumps(data)})
    conversation=new_conversation()
    conversation["order"]["slots"].update(name="DEMO TÊN RIÊNG",phone="TEST-SECRET",address="DEMO ĐỊA CHỈ",product_id="some-product-id")
    llm_client.extract_turn("xin chào",conversation,"http://localhost:11434","fake")
    context=json.loads(calls[0][0][-1]["content"])["context"]
    assert all(key not in context["order_draft"]["slots"] for key in ["name","phone","address","product_id"])


@pytest.mark.parametrize("field,value,message", [
    ("quantity", "2", "hai bánh"), ("toppings", "không topping", "không topping"),
])
def test_wire_rejects_wrong_slot_types_without_coercing(monkeypatch,make_turn,field,value,message):
    data=make_turn(intents=["order_request"]).model_dump()
    data["updates"]=[{"field":field,"value":value}]
    calls=[]
    monkeypatch.setattr(llm_client,"chat",lambda *args:calls.append(args) or {"ok":True,"content":json.dumps(data)})
    result=llm_client.extract_turn(message,new_conversation(),"http://localhost:11434","fake")
    assert result["error"]=="invalid_turn_json" and len(calls)==2


def test_omitted_catalog_mention_requires_model_repair(monkeypatch,make_turn):
    missing=make_turn(intents=["price","size"]).model_dump(); missing["updates"]=[]
    repaired=dict(missing,product_mentions=["bánh socola"])
    outputs=iter([json.dumps(missing),json.dumps(repaired)])
    monkeypatch.setattr(llm_client,"chat",lambda *args:{"ok":True,"content":next(outputs)})
    result=llm_client.extract_turn("giá và size bánh socola",new_conversation(),"http://localhost:11434","fake",repository=MockCatalogRepository())
    assert result["attempts"]==2 and result["data"].product_mentions==["bánh socola"]
