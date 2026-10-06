"""HTTP in-process, SQLite file tạm; model lỗi là giả lập, không gọi Qwen thật."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from app import api, llm_client
from app.knowledge_loader import EmptyKnowledgeRepository, SampleKnowledgeRepository
from app.repositories.empty_catalog import EmptyCatalogRepository
from app.repositories.mock_catalog import MockCatalogRepository
from app.storage import list_records, load_conversation, open_storage


def client_for(tmp_path, mode="empty", **options):
    # Unit tests không gọi model thật; từng test Ollama truyền mode riêng.
    options.setdefault("chat_mode", "rule")
    repository = MockCatalogRepository() if mode == "mock" else EmptyCatalogRepository()
    application = api.create_app(catalog_repository=repository,
        knowledge_repository=EmptyKnowledgeRepository(), db_path=tmp_path / "chat.sqlite3", **options)
    return TestClient(application)


def start(client):
    response = client.post("/api/conversations", json={})
    assert response.status_code == 201
    return response.json()


def headers(session):
    return {"Authorization": "Bearer " + session["session_token"]}


def chat(client, session, message):
    return client.post("/api/chat", headers=headers(session),
        json={"conversation_id": session["conversation_id"], "message": message})


def fill_order(client, session, mode):
    commands = ["đặt bánh", "nhu cầu: bánh học tập"]
    if mode == "mock":
        commands.append("mã bánh: mock-001")
    commands += ["size: 16 cm", "số lượng: 2", "topping: không", "chữ: Chúc vui",
        "ngày nhận: 2099-01-04 10:00", "nhận: cửa hàng", "tên: DEMO Khách A", "sđt: TEST-0001"]
    for command in commands:
        assert chat(client, session, command).status_code == 200
    return chat(client, session, "xem lại").json()


@pytest.mark.parametrize("mode", ["empty", "mock"])
def test_health_static_and_creation(tmp_path, mode):
    with client_for(tmp_path, mode) as client:
        health = client.get("/health").json()
        assert health["status"] == "ok" and health["data_mode"] == mode
        assert health["message_max_length"] == 2000
        assert client.get("/").status_code == 200
        assert client.get("/static/chat.js").status_code == 200
        assert client.get("/static/style.css").status_code == 200
        a, b = start(client), start(client)
        assert a["conversation_id"] != b["conversation_id"]
        assert a["session_token"] != b["session_token"]
        assert len(a["session_token"]) >= 43
        assert a["session_token"] != a["conversation_id"]
        assert client.post("/api/conversations", json={}).headers["cache-control"] == "no-store"


@pytest.mark.parametrize("mode", ["empty", "mock"])
def test_product_modes_and_unknown_price(tmp_path, mode):
    with client_for(tmp_path, mode) as client:
        session = start(client)
        data = chat(client, session, "socola dưới 300k").json()
        assert data["data_mode"] == mode and not data["requires_confirmation"]
        assert data["sources"] == [] and data["request_id"] is None
        if mode == "empty":
            assert data["products"] == [] and data["catalog_status"] == "unconfigured"
            assert "Chưa có menu" in data["message"]
        else:
            assert data["catalog_status"] == "success"
            assert data["products"][0]["is_mock"] is True
            assert data["products"][0]["variants"][0]["price_vnd"] == 250000
            unknown = chat(client, start(client), "giá bánh tart chanh").json()
            assert unknown["products"][0]["variants"][0]["price_vnd"] is None
            missing = chat(client, start(client), "giá bánh sầu riêng").json()
            assert missing["catalog_status"] == "no_results" and missing["products"] == []


def test_separate_history_and_needs(tmp_path):
    with client_for(tmp_path) as client:
        a, b = start(client), start(client)
        chat(client, a, "Mình cần bánh socola cho 6 người dưới 300k.")
        chat(client, a, "Tăng ngân sách lên 400k.")
        chat(client, b, "xin chào")
        with closing(open_storage(tmp_path / "chat.sqlite3")) as connection:
            first = load_conversation(connection, a["conversation_id"])
            second = load_conversation(connection, b["conversation_id"])
        assert first["needs"]["filters"]["max_price_vnd"] == 400000
        assert first["needs"]["filters"]["servings"] == 6
        assert "max_price_vnd" not in second["needs"]["filters"]
        assert all("400k" not in item["content"] for item in second["history"])


def test_session_authorization_and_uuid_is_not_auth(tmp_path):
    with client_for(tmp_path) as client:
        a, b = start(client), start(client)
        body = {"conversation_id": a["conversation_id"], "message": "xin chào"}
        assert client.post("/api/chat", json=body).status_code == 401
        assert client.post("/api/chat", json=body, headers={"Authorization":"Bearer " + a["conversation_id"]}).status_code == 401
        assert client.post("/api/chat", json=body, headers=headers(b)).status_code == 404
        assert client.get("/api/order-requests/unknown").status_code == 401
        assert client.get("/api/order-requests/unknown", headers=headers(a)).status_code == 404
        assert chat(client, a, "xin chào").status_code == 200


@pytest.mark.parametrize("message", ["", "   ", "a" * 2001, 12, True, None])
def test_invalid_messages_do_not_echo_input(tmp_path, message):
    with client_for(tmp_path) as client:
        session = start(client)
        response = chat(client, session, message)
        assert response.status_code == 422
        assert response.json()["detail"] == "invalid_request"
        assert all("input" not in item for item in response.json()["fields"])


def test_extra_fields_and_max_length(tmp_path):
    with client_for(tmp_path) as client:
        assert client.post("/api/conversations", json={"conversation_id":"chosen"}).status_code == 422
        session = start(client)
        assert client.post("/api/chat", headers=headers(session), json={
            "conversation_id":session["conversation_id"], "message":"xin chào", "state":"REVIEW"}).status_code == 422
        assert chat(client, session, "x" * 2000).status_code == 200


def test_expired_session(tmp_path, monkeypatch):
    with client_for(tmp_path, session_seconds=10) as client:
        monkeypatch.setattr(api.time, "monotonic", lambda: 100.0)
        session = start(client)
        monkeypatch.setattr(api.time, "monotonic", lambda: 111.0)
        assert chat(client, session, "xin chào").status_code == 401


def test_restart_revokes_tokens(tmp_path):
    with client_for(tmp_path) as first:
        session = start(first)
    with client_for(tmp_path) as restarted:
        assert chat(restarted, session, "xin chào").status_code == 401


@pytest.mark.parametrize("mode", ["empty", "mock"])
def test_review_submission_idempotency_and_record_owner(tmp_path, mode):
    with client_for(tmp_path, mode) as client:
        a, b = start(client), start(client)
        premature = chat(client, a, "xác nhận").json()
        assert premature["request_id"] is None and premature["demo_order_id"] is None
        review = fill_order(client, a, mode)
        assert review["state"] == "REVIEW" and review["requires_confirmation"]
        assert review["review"]["slots"]["phone"] == "TEST-0001"
        assert review["request_id"] is None and review["demo_order_id"] is None
        data = chat(client, a, "xác nhận").json()
        key = "request_id" if mode == "empty" else "demo_order_id"
        other = "demo_order_id" if mode == "empty" else "request_id"
        assert data[key] and data[other] is None and not data["requires_confirmation"]
        assert chat(client, a, "xác nhận").json()[key] == data[key]
        record = client.get("/api/order-requests/" + data[key], headers=headers(a)).json()
        assert record["confirmed"] is (mode == "mock")
        assert record["is_mock"] is True
        if mode == "empty":
            assert record["kind"] == "waiting_consultation" and record["quote"] is None
            assert data["state"] == "HANDOFF"
        else:
            assert record["kind"] == "demo_order" and record["quote"]["total_vnd"] == 500000
        assert client.get("/api/order-requests/" + data[key], headers=headers(b)).status_code == 404
        with closing(open_storage(tmp_path / "chat.sqlite3")) as connection:
            assert len(list_records(connection, "submissions", a["conversation_id"])) == 1
            assert list_records(connection, "submissions", b["conversation_id"]) == []


def test_edit_invalidates_review(tmp_path):
    with client_for(tmp_path, "mock") as client:
        session = start(client)
        fill_order(client, session, "mock")
        edited = chat(client, session, "số lượng: 3").json()
        assert edited["state"] == "COLLECTING" and edited["review"] is None
        assert not edited["requires_confirmation"]
        assert chat(client, session, "xác nhận").json()["demo_order_id"] is None
        new_review = chat(client, session, "xem lại").json()
        assert new_review["review"]["quote"]["total_vnd"] == 750000


def test_unavailable_review_cannot_submit(tmp_path):
    with client_for(tmp_path, "mock") as client:
        session = start(client)
        fill_order(client, session, "mock")
        chat(client, session, "số lượng: 11")
        review = chat(client, session, "xem lại").json()
        assert review["review"]["availability"] == "unavailable"
        assert review["requires_confirmation"] is False
        result = chat(client, session, "xác nhận").json()
        assert result["demo_order_id"] is None and result["request_id"] is None


@pytest.mark.parametrize("knowledge_mode", ["empty", "sample"])
def test_policy_sources(tmp_path, knowledge_mode):
    knowledge = SampleKnowledgeRepository() if knowledge_mode == "sample" else EmptyKnowledgeRepository()
    application = api.create_app(catalog_repository=EmptyCatalogRepository(), knowledge_repository=knowledge,
        knowledge_mode=knowledge_mode, chat_mode="rule", db_path=tmp_path / "chat.sqlite3")
    with TestClient(application) as client:
        data = chat(client, start(client), "chính sách giao hàng").json()
        assert data["products"] == []
        if knowledge_mode == "empty":
            assert data["sources"] == [] and data["policy_status"] == "unconfigured"
        else:
            assert data["sources"] and all(source["is_mock"] for source in data["sources"])
            assert all(source["source_id"].startswith("sample-") for source in data["sources"])


@pytest.mark.parametrize("error", ["timeout", "model_not_found", "connection_error"])
def test_ollama_failure_is_visible_without_rule_updates(tmp_path, monkeypatch, error):
    monkeypatch.setattr(llm_client, "select_model", lambda *args: {"model":None, "error":error})
    with client_for(tmp_path, chat_mode="ollama") as client:
        data = chat(client, start(client), "socola dưới 300k").json()
        assert data["engine"] == "llm_error" and error in data["errors"]
        assert data["products"] == [] and data["catalog_status"] == "unconfigured"


@pytest.mark.parametrize("fault", ["search_products", "get_capabilities"])
def test_repository_error_is_not_success(tmp_path, monkeypatch, fault):
    repository = MockCatalogRepository()
    def broken(*args):
        raise OSError("DEMO private source detail")
    monkeypatch.setattr(repository, fault, broken)
    application = api.create_app(catalog_repository=repository, chat_mode="rule", db_path=tmp_path / "chat.sqlite3")
    with TestClient(application) as client:
        data = chat(client, start(client), "giá bánh socola").json()
        assert data["catalog_status"] == "error" and data["engine"] == "source_error"
        assert data["products"] == [] and "source_error" in data["errors"]
        assert "private" not in data["message"]


def test_knowledge_error_is_visible(tmp_path):
    application = api.create_app(catalog_repository=EmptyCatalogRepository(),
        knowledge_repository=SampleKnowledgeRepository(tmp_path / "missing.json"),
        knowledge_mode="sample", chat_mode="rule", db_path=tmp_path / "chat.sqlite3")
    with TestClient(application) as client:
        data = chat(client, start(client), "chính sách giao hàng").json()
        assert data["policy_status"] == "error" and data["sources"] == []
        assert "invalid_knowledge_data" in data["errors"]


def test_storage_failure_does_not_claim_success(tmp_path, monkeypatch):
    with client_for(tmp_path) as client:
        session = start(client)
        def broken(path):
            raise sqlite3.OperationalError("DEMO private database path")
        monkeypatch.setattr(api, "open_storage", broken)
        response = chat(client, session, "xin chào")
        assert response.status_code == 503
        assert response.json() == {"detail":"storage_unavailable"}


def test_response_is_validated(tmp_path, monkeypatch):
    original = api.make_chat_view
    def invalid(turn, mode):
        return {**original(turn, mode), "state":"INVALID", "message":"DEMO private detail"}
    monkeypatch.setattr(api, "make_chat_view", invalid)
    with client_for(tmp_path) as client:
        response = chat(client, start(client), "xin chào")
        assert response.status_code == 500
        assert response.json() == {"detail":"invalid_server_response"}


def test_parallel_edits_same_session_are_not_lost(tmp_path):
    with client_for(tmp_path) as client:
        session = start(client)
        chat(client, session, "đặt bánh")
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda message: chat(client, session, message), ["size: 16 cm", "số lượng: 2"]))
        assert all(result.status_code == 200 for result in results)
        with closing(open_storage(tmp_path / "chat.sqlite3")) as connection:
            slots = load_conversation(connection, session["conversation_id"])["order"]["slots"]
        assert slots["size"] == "16 cm" and slots["quantity"] == 2


def test_blocking_controller_does_not_block_event_loop(tmp_path, monkeypatch):
    started, release = Event(), Event()
    original = api.handle_message
    def slow(*args, **kwargs):
        started.set()
        assert release.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(api, "handle_message", slow)
    application = api.create_app(catalog_repository=EmptyCatalogRepository(), chat_mode="rule", db_path=tmp_path / "chat.sqlite3")
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://testserver") as client:
            session = (await client.post("/api/conversations", json={})).json()
            pending = asyncio.create_task(client.post("/api/chat", headers=headers(session), json={"conversation_id":session["conversation_id"], "message":"xin chào"}))
            try:
                assert await asyncio.to_thread(started.wait, 2)
                health = await asyncio.wait_for(client.get("/health"), timeout=1)
                assert health.status_code == 200 and not pending.done()
            finally:
                release.set()
            assert (await pending).status_code == 200
    asyncio.run(scenario())
