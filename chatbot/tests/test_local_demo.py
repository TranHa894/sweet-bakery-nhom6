"""Database test riêng + Qwen fake. Transaction/race chạy SQLite thật."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta
import json
import sqlite3
from threading import Barrier
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from app import llm_client
from app.api import create_app
from app.conversation import handle_message, new_conversation
from app.knowledge_loader import LocalKnowledgeRepository
from app.order_flow import create_review, new_draft, update_slot
from app.order_nlu import resolve_pickup_phrase
from app.order_service import LOCAL_ZONE, create_order_tools, inspect_order, submit_order_request
from app.repositories.local_catalog import LocalCatalogRepository
from app.schemas import RAGAnswer
from app.storage import open_storage, load_conversation, load_order_request, save_conversation, list_records, PROJECT_ROOT, save_record
from scripts.database import seed_database, reset_demo, check_database

NOW = datetime(2030, 1, 1, 10, 0, tzinfo=LOCAL_ZONE)
FULL_MESSAGE = ("Mình muốn đặt hai bánh socola size 16 cm, không topping, ghi chữ 'Chúc vui', "
                "nhận tại cửa hàng 2099-01-04 10:00, tên DEMO Khách A, sđt TEST-0001.")
FULL_UPDATES = {"size": "16 cm", "quantity": 2, "toppings": [], "cake_text": "Chúc vui",
                "pickup_at": "2099-01-04 10:00", "fulfillment": "pickup", "name": "DEMO Khách A", "phone": "TEST-0001"}


@pytest.fixture
def local_db(tmp_path):
    path = tmp_path / "folder có dấu và khoảng trắng" / "demo.sqlite3"
    connection = open_storage(path)
    seed_database(connection)
    yield path, connection, LocalCatalogRepository(path)
    connection.close()


def full_turn(make_turn, **changes):
    return make_turn(intents=["order_request"], action="start_order", product_mentions=["bánh socola"],
                     updates=FULL_UPDATES, order_update=True, **changes)


def run_message(message, repository, connection, conversation, **kwargs):
    return handle_message(message, repository, conversation, chat_mode="ollama",
                          order_tools=create_order_tools(repository, connection, conversation["id"]),
                          storage_connection=connection, **kwargs)


def ready_draft(identifier="A", quantity=2):
    draft = new_draft(identifier)
    for field, value in {"product_id":"demo-001", **FULL_UPDATES, "quantity":quantity}.items():
        draft = update_slot(draft, field, value, NOW)
    return draft


def store_and_review(connection, repository, identifier="A", quantity=2):
    conversation = new_conversation(identifier)
    conversation["order"] = ready_draft(identifier, quantity)
    with connection:
        save_conversation(connection, conversation)
    tools = create_order_tools(repository, connection, identifier, NOW)
    draft, _ = create_review(conversation["order"], tools, NOW)
    return draft


def test_seed_twice_keeps_counts_and_modified_inventory(local_db):
    _, connection, repository = local_db
    with connection:
        connection.execute("UPDATE product_variants SET stock_quantity=7 WHERE id='demo-001-v1'")
    result = seed_database(connection)
    assert result["counts"]["products"] == 25 and result["counts"]["product_variants"] == 35
    assert result["counts"]["policies"] == 13 and result["foreign_key_errors"] == 0 and result["integrity"] == "ok"
    assert repository.get_order_metadata("demo-001")["metadata"]["stock_quantity"]["demo-001-v1"] == 7


def test_foreign_keys_prices_stock_constraints(local_db):
    _, connection, _ = local_db
    for statement in ["UPDATE product_variants SET stock_quantity=-1 WHERE id='demo-001-v1'",
                      "UPDATE product_variants SET price_vnd=1.5 WHERE id='demo-001-v1'",
                      "INSERT INTO product_toppings VALUES('invalid','demo-top-001')"]:
        with pytest.raises(sqlite3.IntegrityError), connection:
            connection.execute(statement)
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_prices_size_and_budget_filter_same_variant(local_db):
    _, _, repository = local_db
    product = repository.get_product("demo-001")["product"]
    assert [(v["size"],v["price_vnd"]) for v in product["variants"]] == [("16 cm",250000),("20 cm",350000)]
    result = repository.search_products({"flavor":"socola","servings":6,"max_price_vnd":300000,"price_inclusive":False})
    assert result["status"] == "success" and len(result["products"]) == 1
    assert result["products"][0]["variants"][0]["id"] == "demo-001-v1"


def test_inactive_products_not_recommended_and_cannot_order(local_db):
    _, connection, repository = local_db
    with connection:
        connection.execute("UPDATE products SET active=0 WHERE id='demo-001'")
    assert repository.search_products({"product_ids":["demo-001"]})["status"] == "no_results"
    inspection = inspect_order(repository,ready_draft(),NOW)
    assert "product_inactive" in inspection["issues"] and inspection["quote"] is None


def test_multiple_intents_in_one_question(local_db, make_turn, fake_model):
    _, connection, repository = local_db
    fake_model([make_turn(intents=["price","size","availability","topping"], product_mentions=["bánh socola"])])
    turn=run_message("giá size bánh socola còn hàng không và topping gì",repository,connection,new_conversation())
    assert turn["response"]["intents"] == ["price","size","availability","topping"]
    assert "250.000 đ" in turn["response"]["text"] and "20 cm" in turn["response"]["text"] and "kẹo cốm" in turn["response"]["text"]


def test_reference_to_last_verified_product(local_db,make_turn,fake_model):
    _, connection, repository=local_db
    fake_model([make_turn(intents=["price"],product_mentions=["bánh socola"]),
                make_turn(intents=["size"],reference="last")])
    a=run_message("giá bánh socola",repository,connection,new_conversation())
    b=run_message("size bánh đó",repository,connection,a["conversation"])
    assert b["response"]["products"][0]["id"]=="demo-001"


@pytest.mark.parametrize("reference,expected",[("second","demo-002"),("cheaper","demo-003")])
def test_ordinal_and_cheaper_references(local_db,make_turn,fake_model,reference,expected):
    _, connection, repository=local_db
    current=new_conversation()
    current["shown_products"]=[repository.get_product(i)["product"] for i in ["demo-001","demo-002","demo-003"]]
    current["order"]["slots"]["product_id"]="demo-001"
    fake_model([make_turn(intents=["price"],reference=reference)])
    turn=run_message("chiếc thứ hai" if reference=="second" else "loại rẻ hơn",repository,connection,current)
    assert turn["response"]["products"][0]["id"]==expected


def test_full_natural_order_then_confirm_and_repeat(local_db,make_turn,fake_model):
    _, connection, repository=local_db
    seen=fake_model([full_turn(make_turn),make_turn(intents=["order_request"],action="confirm"),make_turn(intents=["order_request"],action="confirm")])
    current=new_conversation()
    review=run_message(FULL_MESSAGE,repository,connection,current)
    draft=review["conversation"]["order"]
    assert draft["state"]=="REVIEW" and draft["review"]["quote"]["total_vnd"]==500000
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0]==0
    confirmed=run_message("xác nhận",repository,connection,review["conversation"])
    again=run_message("xác nhận",repository,connection,confirmed["conversation"])
    saved=again["conversation"]["order"]["submission"]
    assert saved["id"]==confirmed["conversation"]["order"]["submission"]["id"]
    assert saved["is_demo"] is True and saved["payment_status"]=="unpaid" and saved["snapshot"]["name"]=="Bánh kem socola"
    assert again["conversation"]["order"]["state"]=="DEMO_CONFIRMED"
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0]==1
    assert connection.execute("SELECT stock_quantity FROM product_variants WHERE id='demo-001-v1'").fetchone()[0]==18
    assert len(seen)==3  # xác nhận cũng qua Qwen


def test_unmentioned_slots_retained_and_review_revision_changes(local_db,make_turn,fake_model):
    _, connection, repository=local_db
    fake_model([full_turn(make_turn),make_turn(intents=["order_request"],updates={"quantity":3},order_update=True)])
    a=run_message(FULL_MESSAGE,repository,connection,new_conversation())
    b=run_message("tăng số lượng lên 3 bánh",repository,connection,a["conversation"])
    old,new=a["conversation"]["order"],b["conversation"]["order"]
    assert new["revision"]>old["revision"] and new["review"]["revision"]==new["revision"]
    assert new["slots"]["cake_text"]=="Chúc vui" and new["slots"]["size"]=="16 cm" and new["review"]["quote"]["total_vnd"]==750000
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0]==0


def test_confirmation_plus_edit_does_not_submit_even_without_edit_flag(local_db,make_turn,fake_model):
    _, connection, repository=local_db
    fake_model([full_turn(make_turn),make_turn(intents=["order_request"],action="confirm",updates={"size":"20 cm"})])
    a=run_message(FULL_MESSAGE,repository,connection,new_conversation())
    b=run_message("đồng ý nhưng đổi sang size 20",repository,connection,a["conversation"])
    assert b["conversation"]["order"]["state"]=="REVIEW"
    assert b["conversation"]["order"]["review"]["quote"]["total_vnd"]==700000
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0]==0


def test_explicit_clear_invalidates_review(local_db,make_turn,fake_model):
    _, connection, repository=local_db
    fake_model([full_turn(make_turn),make_turn(intents=["order_request"],clear_slots=["pickup_at"],order_update=True)])
    a=run_message(FULL_MESSAGE,repository,connection,new_conversation())
    b=run_message("xóa ngày nhận",repository,connection,a["conversation"])
    assert b["conversation"]["order"]["slots"]["pickup_at"] is None
    assert b["conversation"]["order"]["review"] is None


def test_question_during_order_does_not_modify_draft(local_db,make_turn,fake_model):
    _, connection, repository=local_db
    fake_model([full_turn(make_turn),make_turn(intents=["price"],reference="last",updates={"size":"20 cm"})])
    a=run_message(FULL_MESSAGE,repository,connection,new_conversation())
    b=run_message("giá size 20 của bánh đó",repository,connection,a["conversation"])
    assert b["conversation"]["order"]==a["conversation"]["order"] and "350.000 đ" in b["response"]["text"]


@pytest.mark.parametrize("changes,issue",[
    ({"size":"99 cm"},"size_unverified"),({"toppings":["hạnh nhân lát"]},"topping_unverified"),
    ({"cake_text":"x"*21},"cake_text_too_long"),({"pickup_at":"2030-01-01 11:00"},"lead_time_too_short"),
    ({"pickup_at":"2030-01-04 21:00"},"outside_opening_hours"),
    ({"product_id":"demo-017","size":"ổ 400 g","cake_text":"Chúc vui"},"cake_text_too_long"),
])
def test_business_metadata_validation(local_db,changes,issue):
    _, _, repository=local_db
    draft=ready_draft()
    for field,value in changes.items():
        draft=update_slot(draft,field,value,NOW)
    inspection=inspect_order(repository,draft,NOW)
    assert issue in inspection["issues"] and inspection["quote"] is None


@pytest.mark.parametrize("product_id,status",[("demo-004","unavailable"),("demo-008","unknown")])
def test_out_of_stock_and_unknown_are_distinct(local_db,product_id,status):
    _, connection, repository=local_db
    draft=ready_draft()
    draft=update_slot(draft,"product_id",product_id,NOW)
    assert inspect_order(repository,draft,NOW)["availability"]==status
    conversation=new_conversation("A"); conversation["order"]=draft
    with connection: save_conversation(connection,conversation)
    draft,_=create_review(draft,create_order_tools(repository,connection,"A",NOW),NOW)
    with connection:
        result=submit_order_request(connection,repository,draft,"unavailable-test",NOW)
    assert result["status"]!= "available" and connection.execute("SELECT count(*) FROM orders").fetchone()[0]==0


def test_quote_topping_quantity_and_delivery_region(local_db):
    _, _, repository=local_db
    draft=ready_draft()
    for field,value in {"toppings":["kẹo cốm"],"fulfillment":"delivery","address":"DEMO Nội thành, phố A"}.items():
        draft=update_slot(draft,field,value,NOW)
    quote=inspect_order(repository,draft,NOW)["quote"]
    assert quote["total_vnd"]==(250000+10000)*2+25000
    draft=update_slot(draft,"address","DEMO Khu vực khác",NOW)
    assert inspect_order(repository,draft,NOW)["quote"] is None


def test_missing_slots_cannot_create_order(local_db,make_turn,fake_model):
    _, connection, repository=local_db
    fake_model([make_turn(intents=["order_request"],action="start_order",product_mentions=["bánh socola"],updates={"quantity":2},order_update=True),
                make_turn(intents=["order_request"],action="confirm")])
    a=run_message("đặt 2 bánh socola",repository,connection,new_conversation())
    b=run_message("xác nhận",repository,connection,a["conversation"])
    assert b["conversation"]["order"]["submission"] is None
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0]==0


def test_stale_review_or_price_change_cannot_submit(local_db):
    _, connection, repository=local_db
    draft=store_and_review(connection,repository)
    draft["revision"]+=1
    with connection: result=submit_order_request(connection,repository,draft,"stale",NOW)
    assert result["error"]=="stale_review"
    draft=store_and_review(connection,repository)
    with connection: connection.execute("UPDATE product_variants SET price_vnd=270000 WHERE id='demo-001-v1'")
    with connection: result=submit_order_request(connection,repository,draft,"changed",NOW)
    assert result["error"]=="source_changed_review_again"
    assert connection.execute("SELECT stock_quantity FROM product_variants WHERE id='demo-001-v1'").fetchone()[0]==20


def test_transaction_failure_rolls_back_stock_and_order(local_db):
    _, connection, repository=local_db
    draft=store_and_review(connection,repository)
    with connection:
        connection.execute("CREATE TRIGGER fail_item BEFORE INSERT ON order_items BEGIN SELECT RAISE(ABORT,'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError), connection:
        submit_order_request(connection,repository,draft,"failure",NOW)
    assert connection.execute("SELECT stock_quantity FROM product_variants WHERE id='demo-001-v1'").fetchone()[0]==20
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0]==0
    assert connection.execute("SELECT count(*) FROM submissions").fetchone()[0]==0


def test_two_competing_orders_never_oversell(local_db):
    path, connection, repository=local_db
    with connection: connection.execute("UPDATE product_variants SET stock_quantity=2 WHERE id='demo-001-v1'")
    drafts=[store_and_review(connection,repository,"A"),store_and_review(connection,repository,"B")]
    barrier=Barrier(2)
    def submit(draft):
        c=open_storage(path)
        try:
            barrier.wait(timeout=5)
            with c:
                result=submit_order_request(c,LocalCatalogRepository(path),draft,"race:"+draft["conversation_id"],NOW)
            return result["status"]
        finally: c.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(submit,drafts))
    assert statuses.count("available")==1
    assert connection.execute("SELECT stock_quantity FROM product_variants WHERE id='demo-001-v1'").fetchone()[0]==0
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0]==1


@pytest.mark.parametrize("error",["timeout","model_not_found","invalid_turn_json"])
def test_model_error_keeps_valid_review_exactly(local_db,make_turn,fake_model,error):
    _, connection, repository=local_db
    fake_model([full_turn(make_turn),{"data":None,"error":error,"attempts":1}])
    a=run_message(FULL_MESSAGE,repository,connection,new_conversation())
    previous=deepcopy(a["conversation"])
    b=run_message("đổi sang size 20",repository,connection,a["conversation"])
    assert b["conversation"]==previous and load_conversation(connection,previous["id"])==previous
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0]==0


def test_policy_has_versioned_source_and_empty_has_none(local_db,make_turn,fake_model,monkeypatch):
    path, connection, repository=local_db
    fake_model([make_turn(intents=["policy"]),make_turn(intents=["policy"])])
    def answer(message,retrieval,*args):
        chunk=retrieval["chunks"][0]
        return {"data":RAGAnswer(supported=True,quotes=[{"source_id":chunk["source_id"],"quote":chunk["content"]}]),"error":None,"attempts":1}
    monkeypatch.setattr(llm_client,"extract_policy_answer",answer)
    a=run_message("giờ mở cửa",repository,connection,new_conversation(),knowledge_repository=LocalKnowledgeRepository(path))
    assert a["response"]["policy"]["citations"][0]["version"]=="demo-1"
    assert a["response"]["policy"]["source_ids"][0]=="demo-policy-001"
    b=run_message("bảo hành thiết bị",repository,connection,a["conversation"],knowledge_repository=LocalKnowledgeRepository(path))
    assert b["response"]["policy"]["source_ids"]==[]


def test_document_change_is_read_without_logic_changes(local_db):
    path, connection, repository=local_db
    before=repository.get_policy_documents()
    with connection:
        connection.execute("UPDATE policies SET content='MÔ PHỎNG: chỉ tư vấn qua quầy mới.',version='demo-2' WHERE id='demo-policy-001'")
    after=LocalKnowledgeRepository(path).get_knowledge()
    assert before["corpus_sha256"]!=after["corpus_sha256"] and after["clauses"][0]["version"]=="demo-2"


def test_unclear_allergy_handoff_and_no_unsafe_recommendations(local_db,make_turn,fake_model):
    _, connection, repository=local_db
    fake_model([make_turn(intents=["recommendation","allergen"],updates={"allergens":["sữa"]})])
    turn=run_message("mình dị ứng sữa, tư vấn bánh",repository,connection,new_conversation())
    assert turn["response"]["products"]==[] and turn["conversation"]["order"]["state"]=="HANDOFF"
    tickets=list_records(connection,"tickets",turn["conversation"]["id"])
    assert tickets[0]["status"]=="pending" and tickets[0]["priority"]=="high"
    assert repository.get_product("demo-010")["product"]["allergen_info"]["status"]=="not_listed"


def test_context_order_and_messages_survive_restart(local_db,make_turn,fake_model):
    path, connection, repository=local_db
    fake_model([full_turn(make_turn),make_turn(intents=["order_request"],action="confirm")])
    a=run_message(FULL_MESSAGE,repository,connection,new_conversation())
    b=run_message("xác nhận",repository,connection,a["conversation"])
    identifier=b["conversation"]["id"]; order_id=b["conversation"]["order"]["submission"]["id"]
    reopened=open_storage(path)
    try:
        assert load_conversation(reopened,identifier)==b["conversation"]
        assert load_order_request(reopened,order_id,identifier)["confirmed"] is True
        assert load_order_request(reopened,order_id,"B") is None
        assert reopened.execute("SELECT count(*) FROM messages WHERE conversation_id=?",(identifier,)).fetchone()[0]==4
    finally: reopened.close()


def test_multi_product_order_explicitly_requests_selection(local_db,make_turn,fake_model):
    _, connection, repository=local_db
    fake_model([make_turn(intents=["order_request"],action="start_order",product_mentions=["socola","dâu"],order_update=True)])
    turn=run_message("đặt socola và dâu",repository,connection,new_conversation())
    assert "một sản phẩm" in turn["response"]["text"] and turn["conversation"]["order"]["slots"]["product_id"] is None


def test_unicode_nfc_and_emoji_count(local_db):
    _, _, repository=local_db
    draft=update_slot(ready_draft(),"cake_text","Chu\u0301c vui 🎂",NOW)
    assert draft["slots"]["cake_text"]=="Chúc vui 🎂" and len(draft["slots"]["cake_text"])==10
    assert inspect_order(repository,draft,NOW)["quote"] is not None


def test_relative_date_needs_hour_then_resolves_in_shop_timezone():
    exact,pending=resolve_pickup_phrase("chiều mai",NOW)
    assert exact is None and pending=="2030-01-02"
    assert resolve_pickup_phrase("14 giờ",NOW,pending)==("2030-01-02 14:00",None)
    with pytest.raises(ValueError): resolve_pickup_phrase("04/05 lúc 10 giờ",NOW)


def test_api_tokens_and_order_owner_are_kept(local_db,make_turn,fake_model):
    path, connection, repository=local_db
    fake_model([full_turn(make_turn),make_turn(intents=["order_request"],action="confirm")])
    app=create_app(catalog_repository=repository,knowledge_repository=LocalKnowledgeRepository(path),db_path=path,chat_mode="ollama",knowledge_mode="local_demo")
    with TestClient(app) as client:
        a=client.post("/api/conversations",json={}).json(); b=client.post("/api/conversations",json={}).json()
        header_a={"Authorization":"Bearer "+a["session_token"]}; header_b={"Authorization":"Bearer "+b["session_token"]}
        review=client.post("/api/chat",headers=header_a,json={"conversation_id":a["conversation_id"],"message":FULL_MESSAGE})
        assert review.status_code==200 and review.json()["requires_confirmation"] is True
        confirmation=client.post("/api/chat",headers=header_a,json={"conversation_id":a["conversation_id"],"message":"xác nhận"}).json()
        assert confirmation["state"]=="DEMO_CONFIRMED" and confirmation["demo_order_id"]
        endpoint="/api/order-requests/"+confirmation["demo_order_id"]
        assert client.get(endpoint,headers=header_a).status_code==200
        assert client.get(endpoint,headers=header_b).status_code==404
        assert client.get(endpoint).status_code==401
        assert client.post("/api/chat",headers=header_b,json={"conversation_id":a["conversation_id"],"message":"xin chào"}).status_code==404


def test_reset_requires_confirm_and_verified_runtime_path(local_db):
    path, connection, _=local_db
    with pytest.raises(ValueError): reset_demo(connection,path)
    with pytest.raises(ValueError): reset_demo(connection,path,confirm=True)  # ngoài runtime, không xóa
    assert check_database(connection)["counts"]["products"]==25


def test_reset_verified_demo_is_atomic_and_seeded_without_deleting_file(monkeypatch):
    root = (PROJECT_ROOT / "runtime").resolve()
    with TemporaryDirectory(prefix="pytest-reset-", dir=root) as directory:
        path = (Path(directory) / "only-test.sqlite3").resolve()
        assert path.is_relative_to(root)
        connection = open_storage(path)
        try:
            seed_database(connection)
            with connection:
                save_conversation(connection,new_conversation("reset-test"))
                connection.execute("UPDATE product_variants SET stock_quantity=1 WHERE id='demo-001-v1'")
            result = reset_demo(connection,path,confirm=True)
            assert path.exists() and result["counts"]["conversations"]==0 and result["counts"]["products"]==25
            assert connection.execute("SELECT stock_quantity FROM product_variants WHERE id='demo-001-v1'").fetchone()[0]==20
            assert list(path.parent.glob("*.reset-*.bak"))
            # Seed lỗi trong reset phải trả lại dữ liệu trước thao tác DELETE.
            with connection: save_conversation(connection,new_conversation("keep-on-error"))
            monkeypatch.setattr("scripts.database.seed_database",lambda *a,**k: (_ for _ in ()).throw(ValueError("test seed failure")))
            with pytest.raises(ValueError): reset_demo(connection,path,confirm=True)
            assert load_conversation(connection,"keep-on-error") is not None
        finally: connection.close()


def test_legacy_schema_one_migrates_with_backup_and_preserves_order(tmp_path):
    path=tmp_path/"legacy.sqlite3"
    connection=open_storage(path)
    conversation=new_conversation("legacy-A")
    draft=ready_draft("legacy-A")
    conversation["order"]=draft
    with connection:
        save_conversation(connection,conversation)
        saved=save_record(connection,"submissions","legacy-A","legacy-key",{
            "draft_id":draft["id"],"revision":draft["revision"],"kind":"demo_order","slots":draft["slots"],
            "verification":{},"issues":[],"quote":{"variant_id":"mock-v1","total_vnd":500000},
            "data_mode":"mock","is_mock":True,"confirmed":True})
        # Tạo đúng schema v1 bằng cách bỏ các bảng v2 chưa có dữ liệu.
        for table in ("order_items","orders","messages","product_toppings","product_variants","products","toppings","policies","business_settings","database_metadata"):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("PRAGMA user_version=1")
    connection.close()
    upgraded=open_storage(path)
    try:
        assert load_conversation(upgraded,"legacy-A")==conversation
        assert load_order_request(upgraded,saved["data"]["id"],"legacy-A")["payment_status"]=="unpaid"
        assert upgraded.execute("SELECT count(*) FROM orders").fetchone()[0]==1
        assert list(tmp_path.glob("*.schema1-*.bak"))
        assert seed_database(upgraded)["counts"]["orders"]==1
        assert upgraded.execute("PRAGMA foreign_key_check").fetchall()==[]
    finally: upgraded.close()


def test_handoff_after_confirmation_has_own_order_priority_and_outside_hours(local_db,make_turn,fake_model):
    _, connection, repository=local_db
    fake_model([full_turn(make_turn),make_turn(intents=["order_request"],action="confirm"),
                make_turn(intents=["order_request"],handoff_reason="complaint",action="handoff")])
    a=run_message(FULL_MESSAGE,repository,connection,new_conversation())
    b=run_message("xác nhận",repository,connection,a["conversation"])
    c=handle_message("tôi muốn khiếu nại",repository,b["conversation"],chat_mode="ollama",storage_connection=connection,
                     order_tools=create_order_tools(repository,connection,b["conversation"]["id"],NOW.replace(hour=22)))
    ticket=list_records(connection,"tickets",b["conversation"]["id"])[0]
    assert ticket["order_id"]==b["conversation"]["order"]["submission"]["id"]
    assert ticket["priority"]=="high" and ticket["status"]=="pending" and ticket["outside_hours"] is True
    assert "Ngoài giờ" in c["response"]["text"]


def test_cli_same_controller_and_owned_order_commands(local_db,make_turn,fake_model,monkeypatch,capsys):
    import main
    path, connection, repository=local_db
    fake_model([full_turn(make_turn),make_turn(intents=["order_request"],action="confirm")])
    conversation=new_conversation("cli-A")
    phase=iter([FULL_MESSAGE,"xác nhận","/orders","/draft","/new","foreign","resume","own","/exit"])
    def read(prompt):
        step=next(phase)
        if step in {"foreign","own"}:
            identifier=connection.execute("SELECT id FROM orders WHERE conversation_id='cli-A'").fetchone()[0]
            return "/order "+identifier
        return "/resume cli-A" if step=="resume" else step
    monkeypatch.setattr(main,"CHAT_MODE","ollama")
    monkeypatch.setattr("builtins.input",read)
    main.run_terminal(repository,LocalKnowledgeRepository(path),connection,conversation)
    output=capsys.readouterr().out
    assert "500.000 đ" in output and "Không tìm thấy bản ghi thuộc phiên hiện tại" in output
    assert '"order_code": "DEMO-' in output and '"payment_status": "unpaid"' in output
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0]==1


def test_reset_cli_rejects_before_creating_or_migrating_files(tmp_path):
    import subprocess
    import sys
    def run(path):
        return subprocess.run([sys.executable,"-X","utf8","-m","scripts.database","reset","--database",str(path),"--confirm"],
                              cwd=PROJECT_ROOT,capture_output=True,text=True,encoding="utf-8",timeout=15)
    outside=tmp_path/"must-not-create.sqlite3"
    assert run(outside).returncode==1 and not outside.exists()
    with TemporaryDirectory(prefix="test-reset-cli-",dir=PROJECT_ROOT/"runtime") as directory:
        path=Path(directory)/"unverified.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE valuable_note(value TEXT)")
            connection.execute("INSERT INTO valuable_note VALUES('preserve')")
            connection.execute("PRAGMA user_version=1")
        original=path.read_bytes()
        assert run(path).returncode==1
        assert path.read_bytes()==original and not list(Path(directory).glob("*.bak"))
