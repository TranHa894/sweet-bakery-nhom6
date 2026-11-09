"""Hồi quy form/API bằng SQLite RAM và đầu ra model giả; không sửa DB đang dùng.
Chạy: python -B -X utf8 -m scripts.check_checkout
"""
from contextlib import closing
from copy import deepcopy
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from app import api, llm_client
from app.checkout import CheckoutForm
from app.knowledge_loader import EmptyKnowledgeRepository
from app.repositories.group_catalog import GroupCatalogRepository
from app.schemas import LLMTurn
from app.storage import open_storage, load_conversation, save_conversation

FORM = {"fullName": "Khách kiểm thử", "phone": "0912345678", "email": "customer@example.invalid",
        "province": "Hà Nội", "ward": "Phường thử", "addressLine": "123 Đường thử",
        "deliveryDate": "2099-01-01", "deliverySlot": "afternoon",
        "cakeMessage": "Chúc vui!", "note": "Thông tin thử", "consent": True,
        "items": [{"product_id": "SP0014", "quantity": 2}, {"product_id": "SP0025", "quantity": 1}]}


def proposal(**changes):
    base = {"intents": ["order_request"], "action": "start_order", "order_operation": "select_product",
            "product_mentions": [], "reference": "none", "updates": {}, "clear_slots": [],
            "ambiguous": False, "handoff_reason": "none", "requests": []}
    return LLMTurn.model_validate({**base, **changes})


def advice_proposal(*, advice="guided", search_scope="new", **filters):
    return proposal(intents=["recommendation"], action="none", order_operation="none",
        requests=[{"intents": ["recommendation"], "product_mentions": [], "question": None,
                   "advice": advice, "search_scope": search_scope, "filters": filters}])


class CheckoutChecks(unittest.TestCase):
    def setUp(self):
        self.uri = "file:checkout-" + uuid4().hex + "?mode=memory&cache=shared"
        self.keeper = sqlite3.connect(self.uri, uri=True, check_same_thread=False)
        self.keeper.row_factory = sqlite3.Row
        self.addCleanup(self.keeper.close)
        with closing(open_storage(":memory:")) as seed:
            seed.backup(self.keeper)
        self.repository = GroupCatalogRepository(database_path=":memory:")
        self.patcher = patch.object(api, "open_storage", self.connect)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = TestClient(api.create_app(catalog_repository=self.repository,
            knowledge_repository=EmptyKnowledgeRepository(), db_path=":memory:"))
        self.addCleanup(self.client.close)
        self.session = self.client.post("/api/conversations", json={}).json()
        self.cid = self.session["conversation_id"]
        self.headers = {"Authorization": "Bearer " + self.session["session_token"]}
        with closing(self.connect(None)) as c, c:
            current = load_conversation(c, self.cid)
            current.update(model="qwen3.5:4b", llm_provider="ollama")
            save_conversation(c, current)
        value = proposal(product_mentions=["Bánh cuộn trà xanh", "Cà phê ủ lạnh"],
            order_product_mentions=["Bánh cuộn trà xanh", "Cà phê ủ lạnh"],
            order_items=[{"product_mention": "Bánh cuộn trà xanh", "quantity": 2},
                         {"product_mention": "Cà phê ủ lạnh", "quantity": 1}])
        result = self.chat("đặt cho tôi 2 Bánh cuộn trà xanh và 1 Cà phê ủ lạnh", value)
        self.assertEqual(result["errors"], [])
        self.view = result["checkout"]
        self.assertEqual(self.view["stage"], "form")

    def connect(self, _):
        c = sqlite3.connect(self.uri, uri=True, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        return c

    def chat(self, message, value):
        with patch.object(llm_client, "extract_turn", return_value={"data": value, "error": None, "attempts": 1}):
            result = self.client.post("/api/chat", headers=self.headers,
                json={"conversation_id": self.cid, "message": message})
        self.assertEqual(result.status_code, 200)
        return result.json()

    def action(self, action, form=None, view=None, headers=None):
        view = view or self.view
        body = {"conversation_id": self.cid, "draft_id": view["draft_id"], "revision": view["revision"], "action": action}
        if form is not None:
            body["form"] = form
        if action == "confirm":
            body["confirmation_token"] = view["confirmation_token"]
        return self.client.post("/api/checkout", headers=headers or self.headers, json=body)

    def review(self):
        response = self.action("review", deepcopy(FORM))
        self.assertEqual(response.status_code, 200, response.text)
        self.view = response.json()["checkout"]
        return response.json()

    def count(self):
        return self.keeper.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]

    def test_required_and_invalid_fields(self):
        for key in ("fullName", "phone", "province", "ward", "addressLine"):
            data = deepcopy(FORM); data[key] = ""
            self.assertEqual(self.action("review", data).status_code, 422)
        for changes in ({"phone": "012345678"}, {"email": "bad"}, {"consent": False},
                        {"deliveryDate": "2020-01-01"},
                        {"items": [{"product_id": "SP0014", "quantity": 0}]}):
            self.assertEqual(self.action("review", {**deepcopy(FORM), **changes}).status_code, 422)
        self.assertEqual(self.count(), 0)

    def test_price_snapshot_and_idempotency(self):
        self.review()
        self.assertEqual(self.view["summary"]["subtotal_vnd"], 115000)
        self.assertIsNone(self.view["summary"]["total_vnd"])
        result = self.action("confirm")
        self.assertEqual(result.status_code, 200)
        self.assertIn("Đã lưu yêu cầu", result.json()["message"])
        identifier = result.json()["request_id"]
        self.assertEqual(self.action("confirm").json()["request_id"], identifier)
        self.assertEqual(self.count(), 1)
        record = self.client.get("/api/order-requests/" + identifier, headers=self.headers).json()
        self.assertEqual(record["checkout_summary"]["subtotal_vnd"], 115000)
        self.assertEqual(record["checkout_form"]["cakeMessage"], FORM["cakeMessage"])
        self.assertFalse(record["confirmed"])

    def test_edit_and_stale_review(self):
        self.review(); old = deepcopy(self.view)
        response = self.action("edit")
        self.assertEqual(response.status_code, 200)
        self.view = response.json()["checkout"]
        self.assertEqual(self.view["form"]["note"], FORM["note"])
        self.assertEqual(self.action("confirm", view=old).status_code, 409)
        self.review()
        self.assertEqual(self.count(), 0)

    def test_new_order_contact_only_and_information(self):
        self.review()
        self.assertEqual(self.action("confirm").status_code, 200)
        old_id = self.view["draft_id"]
        value = proposal(action="none", order_operation="add_product", continuation="order",
                         product_mentions=["trà sữa"], order_product_mentions=["trà sữa"], updates={"quantity": 1})
        result = self.chat("đặt thêm cho tôi 1 trà sữa", value)
        self.assertEqual(result["errors"], [])
        new = result["checkout"]
        self.assertNotEqual(new["draft_id"], old_id)
        self.assertEqual([(i["product_id"], i["quantity"]) for i in new["items"]], [("SP0021", 1)])
        for key in ("fullName", "phone", "email", "province", "ward", "addressLine"):
            self.assertEqual(new["form"][key], FORM[key])
        for key in ("deliveryDate", "deliverySlot", "cakeMessage", "note"):
            self.assertEqual(new["form"][key], "")
        self.assertFalse(new["form"]["consent"])
        value = proposal(intents=["price"], action="none", order_operation="none",
                         product_mentions=["cốc trà sữa"],
                         requests=[{"intents": ["price"], "product_mentions": ["cốc trà sữa"]}])
        result = self.chat("giá 1 cốc trà sữa", value)
        self.assertEqual(result["errors"], [])
        self.assertEqual([p["id"] for p in result["products"]], ["SP0021"])
        self.assertEqual(result["checkout"]["items"], new["items"])
        self.assertEqual(result["checkout"]["revision"], new["revision"])
        self.assertEqual(self.count(), 1)
        self.view = new
        data = {**deepcopy(FORM), "items": [{"product_id": "SP0021", "quantity": 1}],
                "cakeMessage": "", "note": "", "deliveryDate": "", "deliverySlot": ""}
        response = self.action("review", data)
        self.assertEqual(response.status_code, 200)
        self.view = response.json()["checkout"]
        self.assertEqual(self.action("confirm").status_code, 200)
        self.assertEqual(self.count(), 2)

    def test_cancel_and_cross_session(self):
        other = self.client.post("/api/conversations", json={}).json()
        headers = {"Authorization": "Bearer " + other["session_token"]}
        self.assertEqual(self.action("review", deepcopy(FORM), headers=headers).status_code, 404)
        self.review()
        self.assertEqual(self.action("cancel").json()["checkout"]["stage"], "cancelled")
        self.assertEqual(self.action("confirm").status_code, 409)
        self.assertEqual(self.count(), 0)

    def test_no_client_price_and_unknown_product(self):
        data = deepcopy(FORM); data["items"][0]["price_vnd"] = 1
        self.assertEqual(self.action("review", data).status_code, 422)
        data = deepcopy(FORM); data["items"][0]["product_id"] = "missing"
        self.assertEqual(self.action("review", data).status_code, 409)
        self.assertEqual(self.count(), 0)

    def test_source_changes_and_model_failure(self):
        self.review()
        original = self.repository.get_product
        def changed(identifier):
            result = original(identifier)
            result["product"]["variants"][0]["price_vnd"] += 1000
            return result
        with patch.object(self.repository, "get_product", side_effect=changed):
            self.assertEqual(self.action("confirm").status_code, 409)
        with patch.object(llm_client, "extract_turn", return_value={"data": None, "error": "timeout", "attempts": 1}):
            data = self.client.post("/api/chat", headers=self.headers,
                json={"conversation_id": self.cid, "message": "sửa yêu cầu"}).json()
        self.assertEqual(data["checkout"], self.view)
        self.assertEqual(self.count(), 0)

    def test_resume_and_no_contact_in_history(self):
        self.review()
        resumed = self.client.get("/api/conversations/" + self.cid, headers=self.headers).json()
        self.assertEqual(resumed["snapshot"]["checkout"], self.view)
        self.assertTrue(resumed["snapshot"]["show_checkout"])
        # Snapshot từ phiên bản trước chưa có cờ trình bày vẫn mở được REVIEW.
        with closing(self.connect(None)) as c, c:
            current = load_conversation(c, self.cid)
            current.pop("checkout_visible", None)
            save_conversation(c, current)
        legacy = self.client.get("/api/conversations/" + self.cid, headers=self.headers).json()
        self.assertTrue(legacy["snapshot"]["show_checkout"])
        text = str(resumed["messages"])
        for key in ("phone", "email", "addressLine"):
            self.assertNotIn(FORM[key], text)
        other = self.client.post("/api/conversations", json={}).json()
        data = self.client.get("/api/conversations/" + other["conversation_id"],
            headers={"Authorization": "Bearer " + other["session_token"]}).json()
        self.assertIsNone(data["snapshot"]["checkout"])

    def test_form_submit_does_not_call_model(self):
        with patch.object(llm_client, "chat", side_effect=AssertionError("Form không gọi LLM")):
            self.review()
            self.assertEqual(self.action("confirm").status_code, 200)

    def test_handoff_cannot_be_bypassed_by_form(self):
        with closing(self.connect(None)) as c, c:
            current = load_conversation(c, self.cid)
            current["order"]["state"] = "HANDOFF"
            save_conversation(c, current)
        self.assertEqual(self.action("review", deepcopy(FORM)).status_code, 409)
        self.assertEqual(self.count(), 0)

    def test_natural_confirm_requires_form_and_preserves_snapshot(self):
        value = proposal(action="confirm", order_operation="none")
        result = self.chat("xác nhận gửi yêu cầu", value)
        self.assertEqual(self.count(), 0)
        self.review()
        result = self.chat("xác nhận gửi yêu cầu", value)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["checkout"]["stage"], "completed")
        self.assertEqual(self.count(), 1)

    def test_information_and_error_hide_completed_panel_without_losing_order(self):
        self.review()
        saved = self.action("confirm").json()
        self.assertTrue(saved["show_checkout"])
        with patch.object(llm_client, "extract_turn", return_value={"data": None, "error": "invalid_turn_json", "attempts": 2}):
            failed = self.client.post("/api/chat", headers=self.headers,
                json={"conversation_id": self.cid, "message": "gợi ý bánh kem ngọt"}).json()
        self.assertFalse(failed["show_checkout"])
        self.assertEqual(failed["checkout"], saved["checkout"])
        value = proposal(intents=["recommendation"], action="none", order_operation="none",
            requests=[{"intents": ["recommendation"], "product_mentions": [], "question": None,
                       "advice": "guided", "search_scope": "new",
                       "filters": {"product_type": "cream_cake", "flavor": None}}])
        result = self.chat("gợi ý bánh kem ngọt", value)
        self.assertEqual(result["errors"], [])
        self.assertIn("Bạn thích độ ngọt nào", result["message"])
        self.assertFalse(result["show_checkout"])
        self.assertEqual(result["checkout"], saved["checkout"])
        resumed = self.client.get("/api/conversations/" + self.cid, headers=self.headers).json()
        self.assertFalse(resumed["snapshot"]["show_checkout"])
        self.assertEqual(resumed["snapshot"]["checkout"], saved["checkout"])
        self.assertEqual(self.count(), 1)

    def test_information_hides_active_form_and_review_reopens_it(self):
        original = deepcopy(self.view)
        value = proposal(intents=["price"], action="none", order_operation="none",
            product_mentions=["Cà phê muối"],
            requests=[{"intents": ["price"], "product_mentions": ["Cà phê muối"]}])
        result = self.chat("giá cà phê muối", value)
        self.assertFalse(result["show_checkout"])
        self.assertEqual(result["checkout"], original)
        result = self.chat("xem lại yêu cầu", proposal(action="review", order_operation="none"))
        self.assertTrue(result["show_checkout"])
        self.assertEqual(result["checkout"], original)
        self.assertEqual(self.count(), 0)

    def test_order_images_are_from_catalog_and_saved_in_summary(self):
        result = self.review()
        self.assertTrue(result["show_checkout"])
        for row in result["checkout"]["summary"]["items"]:
            product = self.repository.get_product(row["product_id"])["product"]
            self.assertEqual(row["image_url"], product["image_url"])
            self.assertTrue(row["image_url"].startswith("/website/images/"))
            self.assertEqual(self.client.get(row["image_url"]).status_code, 200)
        saved = self.action("confirm").json()
        self.assertEqual(saved["checkout"]["summary"], result["checkout"]["summary"])

    def test_pure_order_examples_do_not_teach_price_or_negation(self):
        import json
        with closing(self.connect(None)) as connection:
            current = load_conversation(connection, self.cid)
        for text in ["Hãy đặt cho tôi 3 cái bánh cuộn vani và 2 cà phê muối",
                     "đặt 3 bánh cuộn vani và 2 cà phê muối"]:
            messages = llm_client.build_turn_messages(text, current, self.repository)
            examples = [json.loads(m["content"]) for m in messages[1:-1] if m["role"] == "assistant"]
            self.assertTrue(examples)
            self.assertLessEqual(len(examples), 2)
            for example in examples:
                self.assertEqual(example["intents"], ["order_request"])
                self.assertFalse(example["requests"])
                self.assertFalse(example.get("order_negated"))
                self.assertIn(example["order_operation"], {"select_product", "add_product"})

    def test_advice_taste_choice_is_not_lost_when_model_omits_it(self):
        self.chat("gợi ý bánh kem", advice_proposal(product_type="cream_cake"))
        second = self.chat("Ngọt vừa", advice_proposal(product_type="cream_cake"))
        self.assertEqual(second["quick_replies"], ["Trái cây", "Sô cô la", "Kem/vani/trang trí"])
        with closing(self.connect(None)) as c:
            waiting = load_conversation(c, self.cid)
        for text in ("Kem/vani/trang trí", "3", "kem/vani/trang tri"):
            with self.subTest(text=text):
                with closing(self.connect(None)) as c, c:
                    save_conversation(c, deepcopy(waiting))
                # Tái hiện đúng JSON lỗi: có loại/độ ngọt nhưng thiếu taste_family.
                result = self.chat(text, advice_proposal(product_type="cream_cake", sweetness="medium"))
                self.assertEqual(result["errors"], [])
                self.assertNotIn("Bạn thích vị nào", result["message"])
                self.assertGreaterEqual(len(result["products"]), 1)
                self.assertLessEqual(len(result["products"]), 3)
                self.assertTrue(all(p["id"] in {"SP0005", "SP0007", "SP0008", "SP0009"} for p in result["products"]))
                self.assertEqual(result["checkout"], self.view)
                self.assertFalse(result["show_checkout"])
                with closing(self.connect(None)) as c:
                    current = load_conversation(c, self.cid)
                self.assertEqual(current["needs"]["filters"]["sweetness"], "medium")
                self.assertEqual(current["needs"]["filters"]["taste_family"], "cream")
                self.assertIsNone(current["advice_pending"])
                self.assertEqual(self.count(), 0)

    def test_other_advice_choices_preserve_group_and_order_quantity(self):
        cases = [
            ("gợi ý bánh nhỏ", "mini", "Cà phê/kem", {"SP0018"}),
            ("gợi ý cà phê", "coffee", "2", {"SP0023"}),
            ("gợi ý trà", "tea", "Ngọt vừa", {"SP0021"}),
        ]
        for first, group, choice, products in cases:
            with self.subTest(group=group):
                self.chat(first, advice_proposal(product_type=group))
                result = self.chat(choice, advice_proposal(product_type=group))
                self.assertEqual(result["errors"], [])
                self.assertEqual({p["id"] for p in result["products"]}, products)
                self.assertEqual(result["checkout"], self.view)
                self.assertEqual(self.count(), 0)

    def test_advice_choice_requires_current_menu_and_keeps_free_text(self):
        from app.advice import resolve_advice_selection, expand_advice_selection
        self.chat("gợi ý bánh kem", advice_proposal(product_type="cream_cake"))
        self.chat("Ngọt vừa", advice_proposal(product_type="cream_cake"))
        with closing(self.connect(None)) as c:
            current = load_conversation(c, self.cid)
        self.assertEqual(resolve_advice_selection(current, "3")["value"], "cream")
        for message in ("4", "gợi ý trà", "mình thích vani", "đặt 3 bánh cuộn vani"):
            self.assertIsNone(resolve_advice_selection(current, message))
            self.assertEqual(expand_advice_selection(current, message), message)
        # Không lấy bảng chờ của phiên khác hoặc bảng cũ sau khi đã đổi việc.
        other = self.client.post("/api/conversations", json={}).json()
        with closing(self.connect(None)) as c:
            other_current = load_conversation(c, other["conversation_id"])
        self.assertIsNone(resolve_advice_selection(other_current, "3"))
        self.chat("giá cà phê muối", proposal(intents=["price"], action="none", order_operation="none",
            product_mentions=["Cà phê muối"], requests=[{"intents": ["price"], "product_mentions": ["Cà phê muối"]}]))
        with closing(self.connect(None)) as c:
            current = load_conversation(c, self.cid)
        self.assertIsNone(resolve_advice_selection(current, "3"))

    def test_advice_model_error_or_order_action_does_not_consume_choice(self):
        self.chat("gợi ý bánh kem", advice_proposal(product_type="cream_cake"))
        self.chat("Ngọt vừa", advice_proposal(product_type="cream_cake"))
        with closing(self.connect(None)) as c:
            waiting = load_conversation(c, self.cid)
        for output in ({"data": None, "error": "timeout", "attempts": 1},
                       {"data": proposal(), "error": None, "attempts": 1}):
            with self.subTest(error=output["error"]):
                with patch.object(llm_client, "extract_turn", return_value=output):
                    result = self.client.post("/api/chat", headers=self.headers,
                        json={"conversation_id": self.cid, "message": "Kem/vani/trang trí"}).json()
                self.assertTrue(result["errors"])
                self.assertEqual(result["checkout"], self.view)
                with closing(self.connect(None)) as c:
                    current = load_conversation(c, self.cid)
                self.assertEqual(current["advice_pending"], waiting["advice_pending"])
                self.assertEqual(current["needs"], waiting["needs"])
                self.assertEqual(self.count(), 0)
        result = self.chat("Kem/vani/trang trí", advice_proposal(product_type="cream_cake", sweetness="medium"))
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["products"])

    def test_more_advice_exhausts_all_products_without_repetition(self):
        more = "Xem thêm lựa chọn khác"
        pool = {p["id"] for p in self.repository.search_products({"product_type": "cream_cake"})["products"]}
        result = self.chat("gợi ý bánh kem, gì cũng được", advice_proposal(advice="any", product_type="cream_cake"))
        seen = set()
        for _ in range(len(pool) + 1):
            ids = {p["id"] for p in result["products"]}
            self.assertEqual(len(ids), min(3, len(pool - seen)))
            self.assertFalse(ids & seen)
            self.assertTrue(ids <= pool)
            seen.update(ids)
            self.assertEqual(more in result["quick_replies"], seen != pool)
            self.assertEqual(result["checkout"], self.view)
            if seen == pool:
                break
            # Nút vẫn đúng dù model trả guided/new thay vì more/refine.
            result = self.chat(more, advice_proposal(product_type="cream_cake"))
        self.assertEqual(seen, pool)
        self.assertNotIn("hay xem thêm lựa chọn khác?", result["message"])
        result = self.chat(more, advice_proposal(advice="more", search_scope="refine"))
        self.assertEqual(result["products"], [])
        self.assertNotIn(more, result["quick_replies"])
        self.assertIn("đã giới thiệu hết", result["message"])
        self.assertEqual(self.count(), 0)

    def test_more_advice_short_last_page_and_three_product_group(self):
        more = "Xem thêm lựa chọn khác"
        first = self.chat("gợi ý bánh kem ngọt vừa vị kem/vani/trang trí",
            advice_proposal(product_type="cream_cake", sweetness="medium", taste_family="cream"))
        self.assertEqual(len(first["products"]), 3)
        self.assertIn(more, first["quick_replies"])
        last = self.chat(more, advice_proposal(advice="more", search_scope="refine"))
        self.assertEqual(len(last["products"]), 1)
        self.assertFalse({p["id"] for p in first["products"]} & {p["id"] for p in last["products"]})
        self.assertNotIn(more, last["quick_replies"])
        self.assertTrue(all(p["advice_profile"]["sweetness"] == "medium" for p in last["products"]))
        tea = self.chat("gợi ý trà, gì cũng được", advice_proposal(advice="any", product_type="tea"))
        self.assertEqual(len(tea["products"]), 3)
        self.assertNotIn(more, tea["quick_replies"])
        self.assertEqual(tea["checkout"], self.view)

    def test_more_advice_survives_information_and_page_reload(self):
        more = "Xem thêm lựa chọn khác"
        first = self.chat("gợi ý bánh kem, gì cũng được", advice_proposal(advice="any", product_type="cream_cake"))
        first_ids = {p["id"] for p in first["products"]}
        name = first["products"][0]["name"]
        self.chat("giá " + name, proposal(intents=["price"], action="none", order_operation="none",
            product_mentions=[name], requests=[{"intents": ["price"], "product_mentions": [name]}]))
        # Client mới trong cùng phiên hợp lệ; bộ lọc/ID đã xem được đọc lại từ SQLite.
        self.client = TestClient(self.client.app)
        self.addCleanup(self.client.close)
        resumed = self.client.get("/api/conversations/" + self.cid, headers=self.headers)
        self.assertEqual(resumed.status_code, 200)
        result = self.chat(more, advice_proposal(advice="more", search_scope="refine"))
        self.assertEqual(len(result["products"]), 3)
        self.assertFalse(first_ids & {p["id"] for p in result["products"]})
        with closing(self.connect(None)) as c:
            current = load_conversation(c, self.cid)
        self.assertEqual(len(current["advice_page"]["seen_ids"]), 6)
        self.assertEqual(result["checkout"], self.view)

    def test_more_advice_new_conditions_reset_only_the_current_search(self):
        more = "Xem thêm lựa chọn khác"
        self.chat("gợi ý bánh kem, gì cũng được", advice_proposal(advice="any", product_type="cream_cake"))
        self.chat(more, advice_proposal(advice="more", search_scope="refine"))
        new = self.chat("gợi ý bánh kem dưới 400k, gì cũng được",
            advice_proposal(advice="any", product_type="cream_cake", budget_vnd=400000, price_inclusive=False))
        seen = set()
        for _ in range(10):
            self.assertEqual(new["errors"], [])
            ids = {p["id"] for p in new["products"]}
            self.assertFalse(ids & seen)
            seen.update(ids)
            self.assertTrue(all(v["price_vnd"] < 400000 for p in new["products"] for v in p["variants"]))
            if more not in new["quick_replies"]:
                break
            new = self.chat(more, advice_proposal(advice="more", search_scope="refine"))
        expected = {p["id"] for p in self.repository.search_products(
            {"product_type": "cream_cake", "max_price_vnd": 400000, "price_inclusive": False})["products"]}
        self.assertEqual(seen, expected)
        with closing(self.connect(None)) as c:
            current = load_conversation(c, self.cid)
        self.assertEqual(set(current["advice_page"]["seen_ids"]), expected)
        other = self.client.post("/api/conversations", json={}).json()
        with closing(self.connect(None)) as c:
            other_current = load_conversation(c, other["conversation_id"])
        self.assertIsNone(other_current.get("advice_page"))
        fresh = self.chat("gợi ý bánh kem, gì cũng được", advice_proposal(advice="any", product_type="cream_cake"))
        with closing(self.connect(None)) as c:
            current = load_conversation(c, self.cid)
        self.assertEqual(len(current["advice_page"]["seen_ids"]), 3)
        self.assertNotIn("max_price_vnd", current["advice_page"]["filters"])
        self.assertEqual(fresh["checkout"], self.view)

    def test_more_advice_failures_do_not_consume_results(self):
        more = "Xem thêm lựa chọn khác"
        first = self.chat("gợi ý bánh kem, gì cũng được", advice_proposal(advice="any", product_type="cream_cake"))
        with closing(self.connect(None)) as c:
            before = load_conversation(c, self.cid)["advice_page"]
        with patch.object(llm_client, "extract_turn", return_value={"data": None, "error": "timeout", "attempts": 1}):
            result = self.client.post("/api/chat", headers=self.headers,
                json={"conversation_id": self.cid, "message": more}).json()
        self.assertTrue(result["errors"])
        with patch.object(self.repository, "search_products", side_effect=RuntimeError("source unavailable")):
            result = self.chat(more, advice_proposal(advice="more", search_scope="refine"))
        self.assertTrue(result["errors"])
        with closing(self.connect(None)) as c:
            self.assertEqual(load_conversation(c, self.cid)["advice_page"], before)
        retry = self.chat(more, advice_proposal(advice="more", search_scope="refine"))
        self.assertEqual(retry["errors"], [])
        self.assertEqual(len(retry["products"]), 3)
        self.assertFalse({p["id"] for p in retry["products"]} & {p["id"] for p in first["products"]})
        self.assertEqual(self.count(), 0)

    def test_more_advice_legacy_session_skips_its_last_visible_products(self):
        more = "Xem thêm lựa chọn khác"
        first = self.chat("gợi ý bánh kem, gì cũng được", advice_proposal(advice="any", product_type="cream_cake"))
        with closing(self.connect(None)) as c, c:
            current = load_conversation(c, self.cid)
            current.pop("advice_page", None)
            save_conversation(c, current)
        result = self.chat(more, advice_proposal(advice="more", search_scope="refine"))
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["products"]), 3)
        self.assertFalse({p["id"] for p in result["products"]} & {p["id"] for p in first["products"]})
        self.assertEqual(result["checkout"], self.view)

    def check_direct_pages(self, message, value, pool):
        more = "Xem thêm lựa chọn khác"
        result = self.chat(message, value)
        first_count = len(result["products"])
        seen = set()
        for _ in range(len(pool) + 1):
            self.assertEqual(result["errors"], [])
            ids = {p["id"] for p in result["products"]}
            self.assertTrue(ids)
            self.assertFalse(ids & seen)
            self.assertTrue(ids <= pool)
            seen.update(ids)
            self.assertEqual(result["quick_replies"], [more] if seen != pool else [])
            self.assertEqual(result["checkout"], self.view)
            if seen == pool:
                break
            result = self.chat(more, advice_proposal(advice="more", search_scope="refine"))
            self.assertLessEqual(len(result["products"]), 3)
        self.assertEqual(seen, pool)
        self.assertEqual(self.count(), 0)
        return first_count, result

    def test_direct_budget_search_has_more_for_every_matching_product(self):
        pool = {p["id"] for p in self.repository.search_products(
            {"product_type": "cake", "max_price_vnd": 400000, "price_inclusive": False})["products"]}
        count, last = self.check_direct_pages("tìm bánh dưới 400k",
            advice_proposal(advice="none", product_type="cake", budget_vnd=400000, price_inclusive=False), pool)
        self.assertEqual(count, 4)
        self.assertTrue(all(p["product_type"] in {"cream_cake", "mini"} for p in last["products"]))
        self.assertTrue(all(v["price_vnd"] < 400000 for p in last["products"] for v in p["variants"]))

    def test_direct_small_result_and_named_price_do_not_offer_more(self):
        result = self.chat("tìm cà phê dưới 50k", advice_proposal(advice="none",
            product_type="coffee", budget_vnd=50000, price_inclusive=False))
        self.assertEqual(len(result["products"]), 3)
        self.assertEqual(result["quick_replies"], [])
        with closing(self.connect(None)) as c:
            page = load_conversation(c, self.cid)["advice_page"]
        result = self.chat("giá bánh cuộn vani", proposal(intents=["price"], action="none", order_operation="none",
            product_mentions=["Bánh cuộn vani"], requests=[{"intents": ["price"], "product_mentions": ["Bánh cuộn vani"]}]))
        self.assertEqual([p["id"] for p in result["products"]], ["SP0015"])
        self.assertEqual(result["quick_replies"], [])
        with closing(self.connect(None)) as c:
            self.assertEqual(load_conversation(c, self.cid)["advice_page"], page)
        self.assertEqual(result["checkout"], self.view)

    def test_direct_multi_group_pages_keep_each_budget(self):
        self.check_multiple_direct_groups("cream_cake", "bánh kem")

    def test_direct_overlapping_groups_do_not_repeat_or_keep_an_empty_more_button(self):
        self.check_multiple_direct_groups("cake", "bánh")

    def check_multiple_direct_groups(self, first_type, first_label):
        first = "tìm " + first_label + " dưới 400k"
        second = "bánh nhỏ dưới 50k"
        value = proposal(intents=["recommendation"], action="none", order_operation="none", requests=[
            {"intents": ["recommendation"], "product_mentions": [], "question": first,
             "filters": {"product_type": first_type, "budget_vnd": 400000, "price_inclusive": False}},
            {"intents": ["recommendation"], "product_mentions": [], "question": second,
             "filters": {"product_type": "mini", "budget_vnd": 50000, "price_inclusive": False}},
        ])
        pool = {p["id"] for p in self.repository.search_products(
            {"product_type": first_type, "max_price_vnd": 400000, "price_inclusive": False})["products"]}
        pool.update(p["id"] for p in self.repository.search_products(
            {"product_type": "mini", "max_price_vnd": 50000, "price_inclusive": False})["products"])
        self.check_direct_pages(first + " và " + second, value, pool)

    def test_direct_cheapest_ranking_is_preserved_when_showing_more(self):
        value = proposal(intents=["recommendation"], action="none", order_operation="none", requests=[
            {"intents": ["recommendation"], "product_mentions": [], "price_preference": "lowest",
             "filters": {"product_type": "mini"}}])
        first = self.chat("tìm bánh nhỏ rẻ nhất", value)
        self.assertEqual(len(first["products"]), 4)
        self.assertEqual(first["quick_replies"], ["Xem thêm lựa chọn khác"])
        last = self.chat("Xem thêm lựa chọn khác", advice_proposal(advice="more", search_scope="refine"))
        self.assertEqual(last["errors"], [])
        self.assertEqual(len(last["products"]), 2)
        self.assertFalse({p["id"] for p in first["products"]} & {p["id"] for p in last["products"]})
        self.assertIn("rẻ nhất", last["message"])
        self.assertTrue(all(v["price_vnd"] == 35000 for p in last["products"] for v in p["variants"]))
        self.assertEqual(last["quick_replies"], [])
        self.assertEqual(last["checkout"], self.view)

    def select_small_matcha(self):
        self.chat("gợi ý bánh ngọt nhỏ", advice_proposal(product_type="mini"))
        result = self.chat("Trà xanh", advice_proposal(product_type="mini", flavor="trà xanh"))
        self.assertEqual([p["id"] for p in result["products"]], ["SP0014"])
        with closing(self.connect(None)) as c:
            return load_conversation(c, self.cid)

    def test_generic_menu_new_budget_drops_old_type_and_taste(self):
        self.select_small_matcha()
        result = self.chat("gợi ý món dưới 100k nhé",
            advice_proposal(budget_vnd=100000, price_inclusive=False))
        pool = {p["id"] for p in self.repository.search_products(
            {"max_price_vnd": 100000, "price_inclusive": False})["products"]}
        seen = set()
        for _ in range(len(pool) + 1):
            ids = {p["id"] for p in result["products"]}
            self.assertFalse(ids & seen)
            self.assertTrue(ids <= pool)
            seen.update(ids)
            self.assertEqual(result["checkout"], self.view)
            with closing(self.connect(None)) as c:
                current = load_conversation(c, self.cid)
            self.assertEqual(current["needs"]["filters"],
                {"max_price_vnd": 100000, "price_inclusive": False})
            if seen == pool:
                self.assertEqual(result["quick_replies"], [])
                break
            self.assertIn("Xem thêm lựa chọn khác", result["quick_replies"])
            result = self.chat("Xem thêm lựa chọn khác", advice_proposal(advice="more", search_scope="refine"))
        self.assertEqual(seen, pool)
        self.assertGreater(len(seen), 1)
        self.assertEqual(self.count(), 0)

    def test_generic_menu_synonyms_start_the_same_search(self):
        waiting = self.select_small_matcha()
        expected = None
        for message in ("gợi ý món dưới 100k nhé", "goi y mon duoi 100 nghin",
                        "gợi ý món ăn dưới 100000", "gợi ý mặt hàng dưới 100 ngàn",
                        "gợi ý sản phẩm dưới 100k"):
            with self.subTest(message=message):
                with closing(self.connect(None)) as c, c:
                    save_conversation(c, deepcopy(waiting))
                result = self.chat(message, advice_proposal(budget_vnd=100000, price_inclusive=False))
                self.assertEqual(result["errors"], [])
                ids = [p["id"] for p in result["products"]]
                expected = ids if expected is None else expected
                self.assertEqual(ids, expected)
                self.assertEqual(result["checkout"], self.view)

    def test_generic_menu_fragments_and_same_flavor_still_refine(self):
        waiting = self.select_small_matcha()
        for message in ("dưới 100k thôi", "vẫn vị trà xanh, dưới 100k",
                        "gợi ý món cùng vị dưới 100k"):
            with self.subTest(message=message):
                with closing(self.connect(None)) as c, c:
                    save_conversation(c, deepcopy(waiting))
                result = self.chat(message, advice_proposal(search_scope="refine",
                    budget_vnd=100000, price_inclusive=False))
                self.assertEqual(result["errors"], [])
                self.assertEqual([p["id"] for p in result["products"]], ["SP0014"])
                with closing(self.connect(None)) as c:
                    current = load_conversation(c, self.cid)
                self.assertEqual(current["needs"]["filters"]["product_type"], "mini")
                self.assertEqual(current["needs"]["filters"]["taste_family"], "matcha")
                self.assertEqual(result["checkout"], self.view)

    def test_generic_menu_product_reference_stays_an_information_question(self):
        waiting = self.select_small_matcha()
        result = self.chat("món đó giá bao nhiêu?", proposal(intents=["price"], action="none",
            order_operation="none", requests=[{"intents": ["price"], "product_mentions": [], "reference": "last"}]))
        self.assertEqual(result["errors"], [])
        self.assertEqual([p["id"] for p in result["products"]], ["SP0014"])
        with closing(self.connect(None)) as c:
            current = load_conversation(c, self.cid)
        self.assertEqual(current["needs"], waiting["needs"])
        self.assertEqual(result["checkout"], self.view)

    def test_generic_menu_new_scope_does_not_need_model(self):
        import json
        waiting = self.select_small_matcha()
        for previous_type in ("mini", None):
            with self.subTest(previous_type=previous_type):
                current = deepcopy(waiting)
                if previous_type is None:
                    current["needs"]["filters"].pop("product_type")
                    current["discussion_context"]["product_type"] = None
                with closing(self.connect(None)) as c, c:
                    save_conversation(c, current)
                def wire(scope, kind):
                    return {"ok": True, "error": None, "http_status": 200,
                        "content": json.dumps({"intents": ["recommendation"], "requests": [
                            {"intents": ["recommendation"], "product_mentions": [], "question": None,
                             "advice": "guided", "search_scope": scope,
                             "filters": {"product_type": kind, "flavor": None,
                                         "budget_vnd": 100000, "price_inclusive": False}}]})}
                with patch.object(llm_client, "chat", side_effect=[
                        wire("refine", previous_type), wire("new", None)]) as calls:
                    result = self.client.post("/api/chat", headers=self.headers,
                        json={"conversation_id": self.cid, "message": "gợi ý món dưới 100k nhé"}).json()
                self.assertEqual(calls.call_count, 0)
                self.assertEqual(result["errors"], [])
                self.assertGreater(len(result["products"]), 1)
                with closing(self.connect(None)) as c:
                    current = load_conversation(c, self.cid)
                self.assertEqual(current["needs"]["filters"],
                    {"max_price_vnd": 100000, "price_inclusive": False})
                self.assertEqual(result["checkout"], self.view)

    def test_generic_menu_prompt_does_not_copy_stale_values_or_change_state(self):
        import json
        waiting = self.select_small_matcha()
        before = deepcopy(waiting)
        for message in ("gợi ý món dưới 100k nhé", "goi y mon duoi 100 nghin",
                        "gợi ý mặt hàng dưới 100000"):
            messages = llm_client.build_turn_messages(message, waiting, self.repository)
            payload = json.loads(messages[-1]["content"])
            self.assertNotIn("product_type", payload["context"]["known_preferences"])
            self.assertIsNone(payload["context"]["advice_pending"])
            examples = [json.loads(m["content"]) for m in messages[1:-1] if m["role"] == "user"]
            self.assertLessEqual(len(examples), 2)
            self.assertTrue(all("product_type" not in e["context"].get("known_preferences", {}) for e in examples))
        for message in ("dưới 100k thôi", "gợi ý món cùng vị dưới 100k", "món đó giá bao nhiêu?"):
            payload = json.loads(llm_client.build_turn_messages(message, waiting, self.repository)[-1]["content"])
            self.assertEqual(payload["context"]["known_preferences"]["product_type"], "mini")
        self.assertEqual(waiting, before)

    def test_transaction_rolls_back(self):
        self.review()
        from app import order_service
        original = order_service.save_record
        def fail_after_insert(*args, **kwargs):
            original(*args, **kwargs)
            raise sqlite3.OperationalError("test rollback")
        with patch.object(order_service, "save_record", side_effect=fail_after_insert):
            response = self.action("confirm")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.action("confirm").status_code, 200)
        self.assertEqual(self.count(), 1)


    def test_tea_sweetness_budget_resets_old_cake_scope(self):
        before = load_conversation(self.keeper, self.cid)["order"]
        for message in ("hãy đề xuất cho tôi trà ngọt nhiều dưới 30k nhé",
                        "gợi ý trà ngọt nhiều dưới 30000", "tu van tra ngot nhieu duoi 30 nghin"):
            value = advice_proposal(product_type="tea", sweetness="high",
                                    budget_vnd=30000, price_inclusive=False)
            result = self.chat(message, value)
            self.assertEqual(result["errors"], [])
            self.assertEqual([p["id"] for p in result["products"]], ["SP0019"])
            self.assertFalse(result["show_checkout"])
        self.assertEqual(load_conversation(self.keeper, self.cid)["order"], before)
        self.assertEqual(self.count(), 0)

    def bundle_value(self, budget=400000, *, inclusive=True, filters=None, quantities=None, questions=None):
        groups = filters or [{"product_type": "cream_cake"}, {"product_type": "tea"}]
        questions = questions or ["bánh kem", "trà"]
        quantities = quantities or [1] * len(groups)
        return proposal(intents=["recommendation"], action="none", order_operation="none",
            bundle_budget={"question": ("không quá " if inclusive else "dưới ") + str(budget),
                           "budget_vnd": budget, "price_inclusive": inclusive},
            requests=[{"intents": ["recommendation"], "product_mentions": [], "question": q,
                       "quantity": n, "search_scope": "new", "filters": f}
                      for q, n, f in zip(questions, quantities, groups)])

    def test_bundle_api_shared_budget_and_draft_unchanged(self):
        before = load_conversation(self.keeper, self.cid)["order"]
        value = self.bundle_value()
        result = self.chat("ngân sách không quá 400000 gợi ý bánh kem với trà", value)
        self.assertEqual(result["errors"], [])
        self.assertEqual([g["total_vnd"] for g in result["recommendation_groups"]], [345000, 375000, 385000])
        self.assertNotIn("Tổng tiền hàng:", result["message"])
        self.assertFalse(result["show_checkout"])
        self.assertEqual(len({p["id"] for p in result["products"]}), len(result["products"]))
        self.assertNotIn("SP0003", {p["id"] for p in result["products"]})
        self.assertEqual(load_conversation(self.keeper, self.cid)["order"], before)
        self.assertEqual(self.count(), 0)

    def test_bundle_quantities_flavor_and_three_types(self):
        value = self.bundle_value(500000,
            filters=[{"product_type": "cream_cake", "flavor": "sô cô la"},
                     {"product_type": "tea", "sweetness": "high"}, {"product_type": "coffee"}],
            quantities=[1, 2, 1], questions=["1 bánh kem vị sô cô la", "2 trà ngọt nhiều", "1 cà phê"])
        result = self.chat("không quá 500000 gợi ý 1 bánh kem vị sô cô la, 2 trà ngọt nhiều và 1 cà phê", value)
        self.assertEqual(result["errors"], [])
        self.assertEqual([g["total_vnd"] for g in result["recommendation_groups"]], [455000] * 3)
        self.assertTrue(all(g["items"][1]["quantity"] == 2 and
                            g["items"][1]["line_total_vnd"] == 50000 for g in result["recommendation_groups"]))
        self.assertEqual({p["id"] for p in result["products"]}, {"SP0012", "SP0019", "SP0022", "SP0023", "SP0025"})
        self.assertEqual(self.count(), 0)

    def test_combo_sweetness_followups_preserve_budget_and_draft(self):
        from app.conversation import new_conversation, handle_message
        from app.order_nlu import normalize_bundle_preferences, check_turn_grounding
        from app.schemas import LLMTurn
        initial = self.bundle_value(400000,
            filters=[{"product_type": "cream_cake", "sweetness": "high"},
                     {"product_type": "tea", "sweetness": "low"}],
            questions=["bánh kem ngọt", "trà ít ngọt"])
        message = "không quá 400000 đề xuất bánh kem ngọt, trà ít ngọt"
        normalized = normalize_bundle_preferences(message, initial)
        self.assertEqual(normalized.requests[0].filters.sweetness, "sweet")
        self.assertEqual(normalized.requests[1].filters.sweetness, "low")
        self.assertIsNone(check_turn_grounding(message, normalized, self.repository))
        result = self.chat(message, initial)
        self.assertEqual(result["errors"], [])
        for combo in result["recommendation_groups"]:
            self.assertIn(combo["items"][0]["sweetness"], {"ngọt vừa", "ngọt nhiều"})
            self.assertEqual(combo["items"][1]["sweetness"], "ít ngọt")
            self.assertLessEqual(combo["total_vnd"], 400000)
        before = deepcopy(load_conversation(self.keeper, self.cid)["order"])
        ambiguous = advice_proposal(product_type="cream_cake", sweetness="low", search_scope="refine")
        answer = self.chat("cho tôi món ít ngọt hơn nhé", ambiguous)
        self.assertEqual(answer["errors"], [])
        self.assertIn("món nào", answer["message"])
        self.assertEqual(answer["recommendation_groups"], [])
        self.assertEqual(len(answer["quick_replies"]), 2)
        self.assertIsNotNone(load_conversation(self.keeper, self.cid).get("bundle_context"))
        value = proposal(intents=["recommendation"], action="none", order_operation="none", requests=[
            {"intents":["recommendation"],"product_mentions":[],"question":"bánh kem ít ngọt",
             "search_scope":"refine","filters":{"product_type":"cream_cake","sweetness":"low"}},
            {"intents":["recommendation"],"product_mentions":[],"question":"trà ngọt vừa",
             "search_scope":"refine","filters":{"product_type":"tea","sweetness":"medium"}}])
        result = self.chat("cho tôi bánh kem ít ngọt và trà ngọt vừa nhé", value)
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["recommendation_groups"])
        for combo in result["recommendation_groups"]:
            self.assertEqual(combo["items"][0]["sweetness"], "ít ngọt")
            self.assertEqual(combo["items"][1]["sweetness"], "ngọt vừa")
            self.assertEqual(combo["budget_vnd"], 400000)
        self.assertEqual(load_conversation(self.keeper, self.cid)["order"], before)
        # Lỗi model không làm mất bộ lọc combo/bản nháp; không lây sang phiên khác.
        current = load_conversation(self.keeper, self.cid)
        with patch.object(llm_client, "extract_turn", return_value={"data":None,"error":"timeout","attempts":1}):
            failed = handle_message("đổi vị", self.repository, current, chat_mode="ollama")
        self.assertEqual(failed["conversation"], current)
        self.assertNotIn("bundle_context", new_conversation())
        fresh = self.chat("gợi ý cà phê dưới 50k", advice_proposal(
            product_type="coffee", budget_vnd=50000, price_inclusive=False))
        self.assertEqual(fresh["errors"], [])
        self.assertNotIn("bundle_context", load_conversation(self.keeper, self.cid))
        self.assertEqual(self.count(), 0)

    def test_combo_wire_normalization_avoids_second_inference(self):
        import json
        from app.conversation import new_conversation
        from app.order_nlu import normalize_bundle_preferences
        value = self.bundle_value(400000,
            filters=[{"product_type":"cream_cake","sweetness":"high"},{"product_type":"tea","sweetness":"low"}],
            questions=["bánh kem ngọt","trà ít ngọt"])
        wire = value.model_dump()
        wire["updates"] = []
        with patch.object(llm_client, "chat", return_value={"ok":True,"content":json.dumps(wire),
                          "error":None,"model":"qwen3.5:4b","http_status":200}) as call:
            result = llm_client.extract_turn_legacy("không quá 400000 gợi ý bánh kem ngọt, trà ít ngọt",
                new_conversation(), "http://127.0.0.1:11434", "qwen3.5:4b", repository=self.repository)
        self.assertIsNone(result["error"])
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["data"].requests[0].filters.sweetness, "sweet")
        # Một yêu cầu tìm mới rõ ràng không bị đổi thành sửa combo.
        fresh = advice_proposal(product_type=None, sweetness="low", search_scope="new")
        current = {"bundle_context":{"components":[{"filters":{"product_type":"tea"}}]}}
        normalized = normalize_bundle_preferences("gợi ý món ít ngọt", fresh, current)
        self.assertEqual(normalized.requests[0].search_scope, "new")

    def test_combo_explicit_degrees_cannot_leak_between_clauses(self):
        from app.order_nlu import normalize_bundle_preferences, check_turn_grounding
        value = self.bundle_value(400000,
            filters=[{"product_type":"cream_cake","sweetness":"high"},{"product_type":"tea","sweetness":"medium"}],
            questions=["bánh kem ít ngọt","trà ngọt vừa"])
        text = "không quá 400000 bánh kem ít ngọt và trà ngọt vừa"
        normalized = normalize_bundle_preferences(text, value)
        self.assertEqual(normalized.requests[0].filters.sweetness, "high")
        self.assertIsNotNone(check_turn_grounding(text, normalized, self.repository))

    def test_no_budget_combo_tiers_and_local_taste(self):
        value = proposal(intents=["recommendation"], action="none", order_operation="none", requests=[
            {"intents":["recommendation"],"product_mentions":[],"question":"bánh kem ngọt vừa",
             "search_scope":"new","filters":{"product_type":"cream_cake","sweetness":"medium"}},
            {"intents":["recommendation"],"product_mentions":[],"question":"cà phê đắng",
             "search_scope":"new","filters":{"product_type":"coffee","coffee_style":"strong"}}])
        before = deepcopy(load_conversation(self.keeper, self.cid)["order"])
        result = self.chat("cho tôi bánh kem ngọt vừa và cà phê đắng nhé", value)
        self.assertEqual(result["errors"], [])
        groups = result["recommendation_groups"]
        self.assertEqual([g["price_tier"] for g in groups], ["low","medium","high"])
        totals = [g["total_vnd"] for g in groups]
        self.assertEqual(totals, sorted(set(totals)))
        self.assertEqual(totals[0], 365000)
        self.assertEqual(totals[-1], 495000)
        self.assertIn("bao nhiêu", result["message"])
        self.assertTrue(result["message"].rstrip().endswith("?"))
        for group in groups:
            self.assertEqual(group["items"][0]["sweetness"], "ngọt vừa")
            self.assertEqual(group["items"][1]["product_id"], "SP0022")
            self.assertIsNone(group["budget_vnd"])
            self.assertIsNone(group["remaining_budget_vnd"])
        self.assertEqual(load_conversation(self.keeper, self.cid)["order"], before)
        # Trả ngân sách sau khi đã xem combo dùng tổng giá, giữ loại và khẩu vị.
        result = self.chat("tôi có 400k", advice_proposal(advice="none", search_scope="refine",
                                                       budget_vnd=400000, price_inclusive=True))
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["recommendation_groups"])
        self.assertTrue(all(g["total_vnd"] <= 400000 for g in result["recommendation_groups"]))
        self.assertEqual(self.count(), 0)

    def test_no_budget_three_components_and_only_one_combination(self):
        from app.advice import recommend_bundles
        components = [{"filters":{"product_type":kind}, "quantity":1}
                      for kind in ["cream_cake","tea","coffee"]]
        result = recommend_bundles(self.repository, components, None, "mock")
        self.assertEqual(len(result["groups"]), 3)
        self.assertTrue(all(len(g["items"]) == 3 for g in result["groups"]))
        self.assertEqual(len({g["total_vnd"] for g in result["groups"]}), 3)
        components = [{"filters":{"product_type":"cream_cake","sweetness":"high","flavor":"sô cô la"}, "quantity":1},
                      {"filters":{"product_type":"coffee","coffee_style":"strong"}, "quantity":1}]
        result = recommend_bundles(self.repository, components, None, "mock")
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(result["groups"][0]["price_tier"], "single")
        components[0]["filters"]["flavor"] = "vị không tồn tại"
        self.assertEqual(recommend_bundles(self.repository, components, None, "mock")["status"], "no_results")

    def test_card_order_starts_form_without_model_and_checks_session(self):
        from app.order_flow import new_draft
        with self.keeper:
            current = load_conversation(self.keeper, self.cid)
            current["order"] = new_draft(self.cid)
            save_conversation(self.keeper, current)
        body = {"conversation_id":self.cid,"items":[{"product_id":"SP0001","quantity":1},
                                                  {"product_id":"SP0019","quantity":2}]}
        with patch.object(llm_client, "extract_turn", side_effect=AssertionError("Nút không được gọi model")):
            response = self.client.post("/api/checkout/start", headers=self.headers, json=body)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["show_checkout"])
        self.assertEqual(result["checkout"]["stage"], "form")
        self.assertEqual([(i["product_id"],i["quantity"]) for i in result["checkout"]["items"]],
                         [("SP0001",1),("SP0019",2)])
        self.assertEqual(self.count(), 0)
        # Bấm lại không tạo nháp khác; chọn món khác không được ghi đè nháp đang có.
        again = self.client.post("/api/checkout/start",headers=self.headers,json=body).json()
        self.assertEqual(again["checkout"]["draft_id"], result["checkout"]["draft_id"])
        bad = {**body,"items":[{"product_id":"SP0022","quantity":1}]}
        self.assertEqual(self.client.post("/api/checkout/start",headers=self.headers,json=bad).status_code,409)
        other = self.client.post("/api/conversations",json={}).json()
        foreign = {"Authorization":"Bearer " + other["session_token"]}
        self.assertEqual(self.client.post("/api/checkout/start",headers=foreign,json=body).status_code,404)
        self.assertEqual(self.client.post("/api/checkout/start",json=body).status_code,401)
        self.assertEqual(self.client.post("/api/checkout/start",headers=self.headers,
            json={**body,"items":[{"product_id":"SP0001","quantity":0}]}).status_code,422)
        # Form vẫn phải review + xác nhận; nút đặt không tự gửi yêu cầu.
        view = result["checkout"]
        review = self.action("review", {**FORM,"items":body["items"]}, view=view).json()
        self.assertEqual(review["checkout"]["stage"], "review")
        self.assertEqual(review["checkout"]["summary"]["subtotal_vnd"],370000)
        confirmed = self.action("confirm",view=review["checkout"]).json()
        self.assertEqual(confirmed["checkout"]["stage"], "completed")
        self.assertIsNotNone(confirmed["request_id"])
        # Yêu cầu kế tiếp dùng liên hệ đã nhớ, không sao chép ngày/lời chúc/ghi chú.
        next_order = self.client.post("/api/checkout/start",headers=self.headers,json=bad).json()
        self.assertEqual(next_order["checkout"]["stage"], "form")
        self.assertEqual(next_order["checkout"]["form"]["fullName"],FORM["fullName"])
        self.assertFalse(next_order["checkout"]["form"]["deliveryDate"])
        self.assertFalse(next_order["checkout"]["form"]["cakeMessage"])

    def test_combo_copy_balance_and_legacy_cards(self):
        from pydantic import ValidationError
        from app.advice import bundle_reason
        value = self.bundle_value(360000, filters=[{"product_type": "cream_cake"}, {"product_type": "tea"}],
                                  questions=["bánh kem", "trà"])
        value.response_opening = "Mình kiểm tra thông tin cho bạn nhé."
        result = self.chat("không quá 360000 gợi ý bánh kem với trà", value)
        self.assertEqual(result["errors"], [])
        self.assertIn("combo", result["message"])
        self.assertNotIn("nhóm", result["message"].split("\n", 1)[-1])
        self.assertNotIn("Mình kiểm tra", result["message"])
        self.assertTrue(result["message"].rstrip().endswith("?"))
        self.assertEqual(result["message"].count("?"), 1)
        self.assertLess(len(result["message"]), 200)
        for group in result["recommendation_groups"]:
            self.assertEqual(group["remaining_budget_vnd"], 360000 - group["total_vnd"])
            self.assertIsNone(group["extra_needed_vnd"])
            self.assertTrue(group["reason"].endswith("."))
            self.assertNotIn("giảm độ ngọt", group["reason"])
        group = deepcopy(result["recommendation_groups"][0])
        self.assertEqual(group["total_vnd"], 345000)
        self.assertEqual(group["remaining_budget_vnd"], 15000)
        with self.assertRaises(ValidationError):
            api.BundleView.model_validate({**group, "remaining_budget_vnd": 1})
        with self.assertRaises(ValidationError):
            api.BundleView.model_validate({**group, "extra_needed_vnd": 1})
        exact = api.BundleView.model_validate({**group, "budget_vnd": 345000, "remaining_budget_vnd": 0})
        self.assertEqual(exact.remaining_budget_vnd, 0)
        legacy = {k: v for k, v in group.items() if k not in {
            "budget_vnd", "remaining_budget_vnd", "extra_needed_vnd", "reason"}}
        self.assertEqual(api.BundleView.model_validate(legacy).reason, "")
        unknown = bundle_reason({"items": [{"product": {"name": "A"}}, {"product": {"name": "B"}}]})
        self.assertNotIn("ngọt", unknown)
        self.assertNotIn("vị", unknown)
        self.assertEqual(self.count(), 0)

    def test_bundle_cards_resume_clear_and_session_isolation(self):
        value = self.bundle_value(440000, filters=[{"product_type": "cream_cake"}, {"product_type": "coffee"}],
                                  questions=["bánh kem", "cà phê"])
        result = self.chat("không quá 440000 gợi ý bánh kem với cà phê", value)
        groups = result["recommendation_groups"]
        self.assertEqual([g["total_vnd"] for g in groups], [365000, 395000, 405000])
        self.assertLess(len(result["message"]), 200)
        for group in groups:
            self.assertEqual(group["total_vnd"], sum(i["quantity"] * i["unit_price_vnd"] for i in group["items"]))
            for item in group["items"]:
                self.assertTrue(item["image_url"].startswith("/website/images/"))
                self.assertEqual(item["name"], self.repository.get_product(item["product_id"])["product"]["name"])
        resumed = self.client.get("/api/conversations/" + self.cid, headers=self.headers)
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["snapshot"]["recommendation_groups"], groups)
        other = self.client.post("/api/conversations", json={}).json()
        other_headers = {"Authorization": "Bearer " + other["session_token"]}
        self.assertEqual(self.client.get("/api/conversations/" + self.cid, headers=other_headers).status_code, 404)
        self.assertEqual(self.client.get("/api/conversations/" + other["conversation_id"],
                                       headers=other_headers).json()["snapshot"]["recommendation_groups"], [])
        fresh = self.chat("trà ngọt nhiều dưới 30k", advice_proposal(
            product_type="tea", sweetness="high", budget_vnd=30000, price_inclusive=False))
        self.assertEqual(fresh["recommendation_groups"], [])
        self.assertEqual(self.client.get("/api/conversations/" + self.cid,
            headers=self.headers).json()["snapshot"]["recommendation_groups"], [])
        self.assertEqual(self.count(), 0)

    def test_bundle_named_components_and_flavored_cakes_are_distinct(self):
        from app.order_nlu import catalog_group_evidence, check_catalog_grounding
        import json
        products = self.repository.search_products({})["products"]
        text = "tôi có 500k gợi ý 1 bánh kem vị sô cô la và 2 cà phê muối"
        self.assertEqual(catalog_group_evidence(text, products), {"cream_cake", "coffee"})
        self.assertEqual(catalog_group_evidence("bánh cuộn trà xanh dưới 50k", products), {"mini"})
        self.assertEqual(catalog_group_evidence("bánh kem vị trà xanh dưới 400k", products), {"cream_cake"})
        bad = advice_proposal(product_type="cream_cake", flavor="sô cô la", budget_vnd=500000)
        self.assertEqual(check_catalog_grounding(text, bad, self.repository), "missing_bundle_budget")
        value = self.bundle_value(500000, quantities=[1, 2],
            filters=[{"product_type": "cream_cake", "flavor": "sô cô la"}, {"product_type": "coffee"}],
            questions=["1 bánh kem vị sô cô la", "2 cà phê muối"])
        value.bundle_budget.question = "tôi có 500k"
        value.requests[1].product_mentions = ["cà phê muối"]
        result = self.chat(text, value)
        self.assertEqual(result["errors"], [])
        self.assertEqual([g["total_vnd"] for g in result["recommendation_groups"]], [450000])
        messages = llm_client.build_turn_messages(text, load_conversation(self.keeper, self.cid), self.repository)
        examples = [json.loads(m["content"]) for m in messages[1:-1] if m["role"] == "assistant"]
        self.assertTrue(any(e.get("bundle_budget") and any(r.get("quantity") == 2
            for r in e["requests"]) for e in examples))
        self.assertLessEqual(len(examples), 2)

    def test_bundle_older_groups_survive_resume_without_duplicating_latest(self):
        first = self.chat("không quá 400000 gợi ý bánh kem và trà", self.bundle_value())
        self.chat("trà ngọt nhiều dưới 30k", advice_proposal(
            product_type="tea", sweetness="high", budget_vnd=30000, price_inclusive=False))
        second = self.chat("không quá 450000 gợi ý bánh kem và cà phê",
            self.bundle_value(450000, filters=[{"product_type": "cream_cake"}, {"product_type": "coffee"}],
                              questions=["bánh kem", "cà phê"]))
        resumed = self.client.get("/api/conversations/" + self.cid, headers=self.headers).json()
        groups = [m["recommendation_groups"] for m in resumed["messages"] if m["recommendation_groups"]]
        self.assertEqual(groups, [first["recommendation_groups"], second["recommendation_groups"]])
        self.assertEqual(resumed["snapshot"]["recommendation_groups"], second["recommendation_groups"])
        current = load_conversation(self.keeper, self.cid)
        prompt = llm_client.build_turn_messages("trà dưới 30k", current, self.repository)
        self.assertNotIn("recommendation_history", str(prompt))
        self.assertNotIn("image_url", str(prompt))

    def test_bundle_bare_sweet_is_broad_and_local_to_each_item(self):
        from app.order_nlu import check_turn_grounding
        value = self.bundle_value(440000,
            filters=[{"product_type": "cream_cake", "sweetness": "sweet"},
                     {"product_type": "tea", "sweetness": "sweet"}, {"product_type": "coffee"}],
            questions=["bánh kem ngọt", "trà ngọt", "cà phê"])
        message = "không quá 440000 đề xuất bánh kem ngọt, trà ngọt, cà phê"
        self.assertIsNone(check_turn_grounding(message, value, self.repository))
        result = self.chat(message, value)
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["recommendation_groups"]), 3)
        for group in result["recommendation_groups"]:
            self.assertLessEqual(group["total_vnd"], 440000)
            self.assertIsNone(group["extra_needed_vnd"])
            for item in group["items"][:2]:
                self.assertIn(item["sweetness"], ("ngọt vừa", "ngọt nhiều"))
        bad = value.model_copy(deep=True)
        bad.requests[2].filters.sweetness = "sweet"
        self.assertEqual(check_turn_grounding(message, bad, self.repository), "ungrounded_advice_preference")
        bad = value.model_copy(deep=True)
        bad.requests[0].filters.sweetness = "high"
        self.assertEqual(check_turn_grounding(message, bad, self.repository), "missing_advice_preference")

    def test_bundle_pastry_alias_and_exact_budget_are_not_insufficient(self):
        from app.order_nlu import catalog_group_evidence
        products = self.repository.search_products({})["products"]
        message = "tôi có 380k hãy đề xuất cho tôi bánh kem, trà, bánh ngọt"
        self.assertEqual(catalog_group_evidence(message, products), {"cream_cake", "tea", "mini"})
        value = self.bundle_value(380000,
            filters=[{"product_type": "cream_cake"}, {"product_type": "tea"}, {"product_type": "mini"}],
            questions=["bánh kem", "trà", "bánh ngọt"])
        value.bundle_budget.question = "tôi có 380k"
        result = self.chat(message, value)
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["recommendation_groups"])
        self.assertTrue(all(g["total_vnd"] == 380000 and g["extra_needed_vnd"] is None
                            for g in result["recommendation_groups"]))
        self.assertNotIn("chưa đủ", result["message"])
        self.assertEqual(self.count(), 0)

    def test_bundle_shortfall_returns_two_cheapest_complete_groups(self):
        from app.advice import recommend_bundles
        from app.schemas import BundleBudget
        from itertools import product
        components = [{"filters": {"product_type": t}, "quantity": q}
                      for t, q in (("cream_cake", 1), ("tea", 2), ("mini", 1))]
        budget = BundleBudget(question="300k", budget_vnd=300000)
        result = recommend_bundles(self.repository, components, budget, "mock")
        groups = result["groups"]
        options = [self.repository.search_products(c["filters"])["products"] for c in components]
        all_totals = sorted(sum(min(v["price_vnd"] for v in p["variants"]) * c["quantity"]
                               for p, c in zip(items, components)) for items in product(*options))
        self.assertEqual([g["total_vnd"] for g in groups], all_totals[:2])
        self.assertEqual(len({tuple(i["product"]["id"] for i in g["items"]) for g in groups}), 2)
        for group in groups:
            self.assertEqual(group["extra_needed_vnd"], group["total_vnd"] - 300000)
            self.assertEqual(len(group["items"]), 3)
            self.assertEqual(group["items"][1]["quantity"], 2)

    def test_bundle_shortfall_api_and_resume_keep_draft(self):
        before = deepcopy(load_conversation(self.keeper, self.cid)["order"])
        value = self.bundle_value(350000,
            filters=[{"product_type": "cream_cake"}, {"product_type": "tea"}, {"product_type": "mini"}],
            questions=["bánh kem", "trà", "bánh ngọt"])
        result = self.chat("không quá 350000 gợi ý bánh kem, trà, bánh ngọt", value)
        self.assertEqual(result["errors"], [])
        self.assertIn("chưa đủ", result["message"])
        self.assertEqual(len(result["recommendation_groups"]), 2)
        self.assertEqual([g["extra_needed_vnd"] for g in result["recommendation_groups"]], [30000, 30000])
        self.assertFalse(result["show_checkout"])
        self.assertEqual(load_conversation(self.keeper, self.cid)["order"], before)
        self.assertEqual(self.count(), 0)
        resumed = self.client.get("/api/conversations/" + self.cid, headers=self.headers).json()
        self.assertEqual(resumed["snapshot"]["recommendation_groups"], result["recommendation_groups"])
        bad = deepcopy(result["recommendation_groups"][0]); bad["extra_needed_vnd"] = 1
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            api.BundleView.model_validate(bad)

    def test_bundle_shortfall_never_relaxes_taste_allergy_or_unit_cap(self):
        from app.advice import recommend_bundles
        from app.schemas import BundleBudget
        budget = BundleBudget(question="100k", budget_vnd=100000)
        components = [{"filters": {"product_type": "cream_cake", "flavor": "sô cô la", "sweetness": "high"}, "quantity": 1},
                      {"filters": {"product_type": "coffee", "coffee_style": "creamy"}, "quantity": 2}]
        result = recommend_bundles(self.repository, components, budget, "mock")
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual([i["product"]["id"] for i in result["groups"][0]["items"]], ["SP0012", "SP0023"])
        self.assertEqual(result["groups"][0]["extra_needed_vnd"], 350000)
        for extra in ({"flavor": "trà xanh"}, {"exclude_allergens": ["sữa"]}, {"max_price_vnd": 100000}):
            constrained = deepcopy(components)
            constrained[0]["filters"].update(extra)
            self.assertEqual(recommend_bundles(self.repository, constrained, budget, "mock")["groups"], [])

    def test_bundle_response_rejects_inconsistent_totals(self):
        from pydantic import ValidationError
        value = self.bundle_value()
        result = self.chat("không quá 400000 gợi ý bánh kem với trà", value)
        group = result["recommendation_groups"][0]
        api.BundleView.model_validate(group)
        with self.assertRaises(ValidationError):
            api.BundleView.model_validate({**group, "total_vnd": group["total_vnd"] + 1})
        bad = deepcopy(group)
        bad["items"][0]["quantity"] += 1
        with self.assertRaises(ValidationError):
            api.BundleView.model_validate(bad)

    def test_bundle_flavors_are_hard_constraints_and_never_relaxed(self):
        from app.advice import recommend_bundles
        from app.schemas import BundleBudget
        budget = BundleBudget(question="500k", budget_vnd=500000)
        components = [{"filters": {"product_type": "cream_cake", "flavor": "sô cô la",
                                   "sweetness": "high"}, "quantity": 1},
                      {"filters": {"product_type": "coffee", "coffee_style": "creamy"}, "quantity": 2}]
        result = recommend_bundles(self.repository, components, budget, "mock")
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual([i["product"]["id"] for i in result["groups"][0]["items"]], ["SP0012", "SP0023"])
        self.assertEqual(result["groups"][0]["total_vnd"], 450000)
        components[0]["filters"]["flavor"] = "trà xanh"
        result = recommend_bundles(self.repository, components, budget, "mock")
        self.assertEqual(result["status"], "no_results")
        self.assertEqual(result["groups"], [])

    def test_bundle_excludes_inactive_products(self):
        from unittest.mock import Mock
        from app.advice import recommend_bundles
        from app.schemas import BundleBudget
        product = deepcopy(self.repository.search_products({})["products"][0])
        product["active"] = False
        source = Mock()
        source.search_products.return_value = {"status": "success", "products": [product], "error": None}
        result = recommend_bundles(source, [{"filters": {}, "quantity": 1}] * 2,
                                   BundleBudget(question="500k", budget_vnd=500000), "mock")
        self.assertEqual(result["groups"], [])

    def test_bundle_unique_groups_and_partial_repeats(self):
        from app.advice import recommend_bundles
        from app.schemas import BundleBudget
        value = BundleBudget(question="400k", budget_vnd=400000)
        components = [{"filters": {"product_type": "cream_cake"}, "quantity": 1},
                      {"filters": {"product_type": "tea"}, "quantity": 1}]
        result = recommend_bundles(self.repository, components, value, "mock")
        signatures = [tuple(i["product"]["id"] for i in g["items"]) for g in result["groups"]]
        self.assertEqual(len(signatures), 3)
        self.assertEqual(len(set(signatures)), 3)
        self.assertEqual(len({s[0] for s in signatures}), 3)
        self.assertEqual(len({s[1] for s in signatures}), 3)
        components[0]["filters"]["sweetness"] = "high"
        result = recommend_bundles(self.repository, components, value, "mock")
        self.assertEqual(len(result["groups"]), 3)
        self.assertTrue(all(g["items"][0]["product"]["id"] == "SP0012" for g in result["groups"]))
        components[1]["filters"]["sweetness"] = "high"
        self.assertEqual(len(recommend_bundles(self.repository, components, value, "mock")["groups"]), 1)

    def test_bundle_strict_total_and_range_bounds(self):
        from app.advice import recommend_bundles
        from app.schemas import BundleBudget
        components = [{"filters": {"product_type": "cream_cake"}, "quantity": 1},
                      {"filters": {"product_type": "tea"}, "quantity": 1}]
        for inclusive, count in ((True, 3), (False, 0)):
            value = BundleBudget(question="345k", budget_vnd=345000, price_inclusive=inclusive)
            result = recommend_bundles(self.repository, components, value, "mock")
            self.assertEqual(len(result["groups"]), count)
            self.assertTrue(all(g["total_vnd"] == 345000 for g in result["groups"]))
        value = BundleBudget(question="375k-400k", budget_vnd=400000, min_budget_vnd=375000)
        result = recommend_bundles(self.repository, components, value, "mock")
        self.assertTrue(all(375000 <= g["total_vnd"] <= 400000 for g in result["groups"]))

    def test_bundle_insufficient_budget_does_not_offer_partial_group(self):
        value = self.bundle_value(345000, inclusive=False)
        result = self.chat("gợi ý bánh kem và trà tổng dưới 345000", value)
        self.assertEqual(result["errors"], [])
        self.assertFalse(result["products"])
        self.assertIn("chưa tìm được combo phù hợp", result["message"])
        self.assertNotIn("Nhóm 1", result["message"])
        self.assertEqual(self.count(), 0)

    def test_bundle_empty_and_failed_sources(self):
        from app.advice import recommend_bundles
        from app.repositories.empty_catalog import EmptyCatalogRepository
        from app.schemas import BundleBudget
        from unittest.mock import Mock
        components = [{"filters": {"product_type": "cream_cake"}, "quantity": 1},
                      {"filters": {"product_type": "tea"}, "quantity": 1}]
        budget = BundleBudget(question="400k", budget_vnd=400000)
        self.assertEqual(recommend_bundles(EmptyCatalogRepository(), components, budget, "empty")["status"], "unconfigured")
        broken = Mock()
        broken.search_products.side_effect = [self.repository.search_products(components[0]["filters"]), RuntimeError("source failed")]
        result = recommend_bundles(broken, components, budget, "mock")
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["groups"])

    def test_bundle_unknown_prices_stock_and_allergens(self):
        from app.advice import recommend_bundles
        from app.schemas import BundleBudget
        from unittest.mock import Mock
        budget = BundleBudget(question="500k", budget_vnd=500000)
        components = [{"filters": {"product_type": "cream_cake"}, "quantity": 1},
                      {"filters": {"product_type": "tea"}, "quantity": 1}]
        for modification in ({"price_vnd": None}, {"stock_status": "out_of_stock"}):
            product = deepcopy(self.repository.search_products({"product_type": "cream_cake"})["products"][0])
            product["variants"][0].update(modification)
            source = Mock()
            source.search_products.return_value = {"status": "success", "products": [product], "error": None, "data_mode": "mock"}
            result = recommend_bundles(source, components, budget, "mock")
            self.assertFalse(result["groups"])
        components[0]["filters"]["exclude_allergens"] = ["sữa"]
        with patch.object(self.repository, "search_products", wraps=self.repository.search_products) as search:
            result = recommend_bundles(self.repository, components, budget, "mock")
        self.assertFalse(result["groups"])  # Nguồn không đủ dữ liệu dị ứng: không nới ràng buộc.
        self.assertEqual(search.call_args_list[0].args[0]["exclude_allergens"], ["sữa"])

    def test_bundle_quantity_grounding_does_not_use_money(self):
        from app.order_nlu import check_turn_grounding, bundle_quantity_evidence
        self.assertEqual(bundle_quantity_evidence("hai cốc trà và một bánh kem", "trà"), {2})
        self.assertEqual(bundle_quantity_evidence("trà dưới 35 nghìn", "trà dưới 35 nghìn"), set())
        self.assertEqual(bundle_quantity_evidence("trà tầm 30k", "trà tầm 30k"), set())
        value = self.bundle_value(500000, quantities=[1, 1], questions=["bánh kem", "trà"])
        message = "không quá 500000 gợi ý 1 bánh kem và 2 trà"
        self.assertEqual(check_turn_grounding(message, value, self.repository), "missing_bundle_quantity")
        value.requests[1].quantity = 2
        self.assertIsNone(check_turn_grounding(message, value, self.repository))

    def test_bundle_wire_grammar_and_repair_missing_quantity(self):
        import json
        schema = llm_client.turn_output_schema()
        self.assertIn("quantity", schema["$defs"]["BundleInformationRequest"]["required"])
        self.assertNotIn("quantity", schema["$defs"]["InformationRequest"]["required"])
        value = self.bundle_value(500000, quantities=[1, 2], questions=["1 bánh kem", "2 trà"])
        wire = value.model_dump()
        wire["updates"] = []
        good = llm_client.example_for_schema(wire, schema)
        self.assertEqual([r["quantity"] for r in good["requests"]], [1, 2])
        bad = deepcopy(good); bad["requests"][1]["quantity"] = 1
        responses = [{"ok": True, "content": json.dumps(output), "error": None, "model": "qwen3.5:4b"}
                     for output in (bad, good)]
        current = load_conversation(self.keeper, self.cid)
        with patch.object(llm_client, "chat", side_effect=responses) as chat:
            result = llm_client.extract_turn_legacy("không quá 500000 gợi ý 1 bánh kem và 2 trà", current,
                                             "http://127.0.0.1:11434", "qwen3.5:4b", repository=self.repository)
        self.assertIsNone(result["error"])
        self.assertEqual(result["data"].requests[1].quantity, 2)
        self.assertEqual(chat.call_count, 2)

    def test_bundle_and_tea_choose_relevant_few_shots(self):
        import json
        current = load_conversation(self.keeper, self.cid)
        for message, marker in (
                ("ngân sách của tôi chỉ có 400k hãy đề xuất cho tôi bánh kem với trà đi", "bundle_budget"),
                ("hãy đề xuất cho tôi trà ngọt nhiều dưới 30k nhé", "sweetness")):
            messages = llm_client.build_turn_messages(message, current, self.repository)
            examples = [json.loads(m["content"]) for m in messages if m["role"] == "assistant"]
            self.assertLessEqual(len(examples), 2)
            if marker == "bundle_budget":
                self.assertTrue(any(e.get("bundle_budget") for e in examples))
            else:
                self.assertTrue(any(r["filters"].get("product_type") == "tea" and r["filters"].get("sweetness") == "high"
                                    for e in examples for r in e["requests"]))

    def test_legacy_sweetness_alias_does_not_pollute_prompt(self):
        import json
        from app.schemas import LLMWireTurn
        current = load_conversation(self.keeper, self.cid)
        for message in ("bánh kem ngọt nhiều dưới 400k",
                        "ngân sách không quá 400000 gợi ý bánh kem và trà"):
            messages = llm_client.build_turn_messages(message, current, self.repository)
            for item in messages:
                if item["role"] != "assistant":
                    continue
                output = LLMWireTurn.model_validate(json.loads(item["content"]))
                degrees = {r.filters.sweetness for r in output.requests} - {None}
                self.assertNotIn("low", degrees)
                self.assertNotIn("medium", degrees)
                if "ngân sách" in message:
                    self.assertFalse(degrees)

    def test_bundle_api_four_types_keeps_every_component(self):
        value = self.bundle_value(500000, filters=[{"product_type": t}
            for t in ("cream_cake", "mini", "tea", "coffee")],
            questions=["bánh kem", "bánh nhỏ", "trà", "cà phê"])
        result = self.chat("không quá 500000 gợi ý bánh kem, bánh nhỏ, trà và cà phê", value)
        self.assertEqual(result["errors"], [])
        self.assertEqual([g["total_vnd"] for g in result["recommendation_groups"]], [425000, 455000, 465000])
        self.assertTrue(all(len(g["items"]) == 4 for g in result["recommendation_groups"]))
        self.assertEqual({p["product_type"] for p in result["products"]}, {"cream_cake", "mini", "tea", "coffee"})
        self.assertEqual(self.count(), 0)

    def test_bundle_different_variants_do_not_repeat_whole_group(self):
        from unittest.mock import Mock
        from app.advice import recommend_bundles
        from app.schemas import BundleBudget
        cake = deepcopy(self.repository.get_product("SP0012")["product"])
        cake["variants"].append({**cake["variants"][0], "id": "other-variant", "size": "khác",
                                 "price_vnd": 370000})
        coffee = self.repository.get_product("SP0023")["product"]
        source = Mock()
        source.search_products.side_effect = [
            {"status": "success", "products": [cake], "error": None},
            {"status": "success", "products": [coffee], "error": None}]
        result = recommend_bundles(source, [{"filters": {}, "quantity": 1}] * 2,
                                  BundleBudget(question="500k", budget_vnd=500000), "mock")
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(result["groups"][0]["total_vnd"], 405000)

    def test_bundle_total_lower_bound_keeps_valid_variants(self):
        from app.advice import recommend_bundles
        from app.schemas import BundleBudget
        from unittest.mock import Mock
        cake = deepcopy(self.repository.search_products({"product_type": "cream_cake"})["products"][0])
        cake["variants"] = [
            {**cake["variants"][0], "id": "v-small", "size": "nhỏ", "price_vnd": 100000},
            {**cake["variants"][0], "id": "v-large", "size": "lớn", "price_vnd": 200000}]
        tea = self.repository.search_products({"product_type": "tea"})["products"][0]
        source = Mock()
        source.search_products.side_effect = [
            {"status": "success", "products": [cake], "error": None},
            {"status": "success", "products": [tea], "error": None}]
        result = recommend_bundles(source,
            [{"filters": {"product_type": "cream_cake"}, "quantity": 1},
             {"filters": {"product_type": "tea"}, "quantity": 1}],
            BundleBudget(question="200k-300k", budget_vnd=300000, min_budget_vnd=200000), "mock")
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(result["groups"][0]["items"][0]["variant"]["id"], "v-large")
        self.assertEqual(result["groups"][0]["total_vnd"], 225000)

    def test_bundle_missing_global_budget_and_sweetness_are_rejected(self):
        from app.order_nlu import check_catalog_grounding, check_turn_grounding
        value = self.bundle_value()
        value.bundle_budget = None
        self.assertEqual(check_catalog_grounding("ngân sách không quá 400000 gợi ý bánh kem với trà", value,
                                                 self.repository), "missing_bundle_budget")
        tea = advice_proposal(product_type="tea", budget_vnd=30000, price_inclusive=False)
        self.assertEqual(check_turn_grounding("trà ngọt nhiều dưới 30k", tea, self.repository),
                         "missing_advice_preference")


    def test_bundle_all_category_pairs_have_compatible_examples(self):
        import json
        from itertools import combinations
        groups = {"cream_cake": "bánh kem", "mini": "bánh nhỏ", "tea": "trà", "coffee": "cà phê"}
        current = load_conversation(self.keeper, self.cid)
        for pair in combinations(groups, 2):
            message = "tôi có 500k hãy đề xuất " + " với ".join(groups[t] for t in pair)
            messages = llm_client.build_turn_messages(message, current, self.repository)
            examples = [json.loads(m["content"]) for m in messages if m["role"] == "assistant"]
            self.assertLessEqual(len(examples), 2)
            self.assertTrue(any(e.get("bundle_budget") and
                {r["filters"]["product_type"] for r in e["requests"]} == set(pair) for e in examples), pair)

    def test_bundle_450_coffee_drops_old_category_and_preserves_order(self):
        for previous in ("none", "cake_sweet", "cake_tea"):
            if previous == "cake_sweet":
                result = self.chat("bánh kem ngọt nhiều dưới 400k", advice_proposal(
                    product_type="cream_cake", sweetness="high", budget_vnd=400000, price_inclusive=False))
                self.assertEqual(result["errors"], [])
            elif previous == "cake_tea":
                result = self.chat("ngân sách không quá 400000 gợi ý bánh kem với trà", self.bundle_value())
                self.assertEqual(result["errors"], [])
            before = load_conversation(self.keeper, self.cid)["order"]
            value = self.bundle_value(450000,
                filters=[{"product_type": "cream_cake"}, {"product_type": "coffee"}],
                questions=["bánh kem", "cà phê"])
            value.bundle_budget.question = "tôi có 450k"
            result = self.chat("tôi có 450k hãy đề xuất cho tôi bánh kem với cà phê", value)
            self.assertEqual(result["errors"], [])
            self.assertEqual(len(result["recommendation_groups"]), 3)
            self.assertEqual({p["product_type"] for p in result["products"]}, {"cream_cake", "coffee"})
            self.assertEqual([g["total_vnd"] for g in result["recommendation_groups"]], [365000, 395000, 405000])
            self.assertEqual(load_conversation(self.keeper, self.cid)["order"], before)
            self.assertEqual(self.count(), 0)

    def test_bundle_coffee_flavor_confusion_repairs_to_two_components(self):
        import json
        bad = {"intents": ["recommendation"], "requests": [{
            "intents": ["recommendation"], "question": None, "product_mentions": [],
            "advice": "guided", "search_scope": "new",
            "filters": {"product_type": "cream_cake", "flavor": "coffee",
                        "budget_vnd": 450000, "price_inclusive": True}}]}
        value = self.bundle_value(450000,
            filters=[{"product_type": "cream_cake"}, {"product_type": "coffee"}],
            questions=["bánh kem", "cà phê"])
        value.bundle_budget.question = "tôi có 450k"
        wire = value.model_dump(); wire["updates"] = []
        good = llm_client.example_for_schema(wire, llm_client.turn_output_schema())
        replies = [{"ok": True, "content": json.dumps(item), "error": None, "model": "qwen3.5:4b"}
                   for item in (bad, good)]
        current = load_conversation(self.keeper, self.cid)
        with patch.object(llm_client, "chat", side_effect=replies) as chat:
            result = llm_client.extract_turn_legacy("tôi có 450k hãy đề xuất cho tôi bánh kem với cà phê", current,
                "http://127.0.0.1:11434", "qwen3.5:4b", repository=self.repository)
        self.assertIsNone(result["error"])
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(result["data"].bundle_budget.budget_vnd, 450000)
        self.assertEqual({r.filters.product_type for r in result["data"].requests}, {"cream_cake", "coffee"})
        repair = chat.call_args_list[-1].args[0][-1]["content"]
        self.assertIn("bundle_budget", repair)
        self.assertIn("question", repair)


    def test_bundle_money_unit_paraphrase_is_valid_without_retry(self):
        import json
        from app.order_nlu import check_turn_grounding
        from app.text_utils import normalize_money_evidence
        self.assertEqual(normalize_money_evidence("tôi có 450k"),
                         normalize_money_evidence("Tôi có 450 nghìn"))
        self.assertEqual(normalize_money_evidence("tôi có 450k"),
                         normalize_money_evidence("tôi có 450.000đ"))
        value = self.bundle_value(450000,
            filters=[{"product_type": "cream_cake"}, {"product_type": "coffee"}],
            questions=["bánh kem", "cà phê"])
        value.bundle_budget.question = "Tôi có 450 nghìn"
        message = "tôi có 450k hãy đề xuất cho tôi bánh kem với cà phê"
        self.assertIsNone(check_turn_grounding(message, value, self.repository))
        current = load_conversation(self.keeper, self.cid)
        wire = value.model_dump(); wire["updates"] = []
        reply = {"ok": True, "content": json.dumps(llm_client.example_for_schema(wire, llm_client.turn_output_schema())),
                 "error": None, "model": "qwen3.5:4b"}
        with patch.object(llm_client, "chat", return_value=reply) as chat:
            result = llm_client.extract_turn_legacy(message, current, "http://127.0.0.1:11434",
                                            "qwen3.5:4b", repository=self.repository)
        self.assertIsNone(result["error"])
        self.assertEqual(chat.call_count, 1)
        for question, amount in (("Tôi có 480 nghìn", 480000), ("tôi có 45 nghìn", 45000),
                                 ("dưới 450 nghìn", 450000), ("Tôi có 2đ", 2)):
            changed = value.model_copy(deep=True)
            changed.bundle_budget.question, changed.bundle_budget.budget_vnd = question, amount
            self.assertEqual(check_turn_grounding(message, changed, self.repository), "ungrounded_bundle_budget")


    def test_approximate_budget_phrases_are_caps_not_exact_prices(self):
        from app.text_utils import budget_evidence
        for phrase in ("tầm giá 400k", "trong tầm giá 400 nghìn", "khoảng giá 400000",
                       "trong khoảng giá 400.000đ", "tầm khoảng 400 ngàn",
                       "tầm giá khoảng 0,4 triệu", "còn khoảng 400k"):
            with self.subTest(phrase=phrase):
                expected = budget_evidence(phrase)["expected"]
                self.assertEqual(expected, {"budget_vnd":400000, "price_inclusive":True})
        for phrase in ("giá 35000", "cùng giá 35k", "đúng 35 nghìn"):
            expected = budget_evidence(phrase)["expected"]
            self.assertEqual(expected["budget_vnd"], 35000)
            self.assertEqual(expected["min_budget_vnd"], 35000)
        self.assertEqual(budget_evidence("2 bánh và 1 trà")["expected"], {})

    def test_approximate_combo_uses_shared_budget_and_rejects_item_caps(self):
        from app.order_nlu import check_turn_grounding, check_catalog_grounding
        message = "cho tôi bánh kem ngọt nhiều, trà ngọt vừa trong tầm giá 400k"
        value = self.bundle_value(filters=[{"product_type":"cream_cake","sweetness":"high"},
                                         {"product_type":"tea","sweetness":"medium"}],
                                  questions=["bánh kem ngọt nhiều","trà ngọt vừa"])
        value.bundle_budget.question = "trong tầm giá 400k"
        self.assertIsNone(check_turn_grounding(message, value, self.repository))
        self.assertIsNone(check_catalog_grounding(message, value, self.repository))
        wrong = value.model_copy(deep=True); wrong.bundle_budget = None
        for request in wrong.requests:
            request.filters.budget_vnd = 400000
        self.assertEqual(check_catalog_grounding(message, wrong, self.repository), "missing_bundle_budget")
        before = load_conversation(self.keeper, self.cid)["order"]
        result = self.chat(message, value)
        self.assertEqual(result["errors"], [])
        self.assertEqual([g["total_vnd"] for g in result["recommendation_groups"]], [385000])
        self.assertEqual(load_conversation(self.keeper, self.cid)["order"], before)
        self.assertFalse(result["show_checkout"])

    def test_combo_after_failed_model_keeps_review_and_can_confirm_original(self):
        self.review()
        before = deepcopy(load_conversation(self.keeper, self.cid)["order"])
        with patch.object(llm_client, "extract_turn", return_value={
                "data":None,"error":"invalid_turn_json","attempts":2}):
            failed = self.client.post("/api/chat", headers=self.headers,
                json={"conversation_id":self.cid,"message":"gợi ý bánh với trà"}).json()
        self.assertTrue(failed["errors"])
        value = self.bundle_value(filters=[{"product_type":"cream_cake"},
                                         {"product_type":"tea","sweetness":"medium"},
                                         {"product_type":"coffee"}],
                                  questions=["bánh kem","trà ngọt vừa","cà phê"])
        value.bundle_budget = None
        result = self.chat("cho tôi bánh kem, trà ngọt vừa và cà phê nhé bạn", value)
        self.assertEqual(result["errors"], [])
        self.assertEqual([g["total_vnd"] for g in result["recommendation_groups"]], [390000,450000,520000])
        self.assertEqual(load_conversation(self.keeper, self.cid)["order"], before)
        self.assertFalse(result["show_checkout"])
        self.assertEqual(self.count(), 0)
        confirmed = self.action("confirm").json()
        self.assertEqual(confirmed["checkout"]["stage"], "completed")
        self.assertEqual(self.count(), 1)

    def test_fresh_combo_prompt_does_not_teach_old_refinement(self):
        import json
        current = load_conversation(self.keeper, self.cid)
        current["bundle_context"] = {"budget":{"question":"400k","budget_vnd":400000},
            "components":[{"filters":{"product_type":"cream_cake"},"quantity":1},
                          {"filters":{"product_type":"tea"},"quantity":1}]}
        messages = llm_client.build_turn_messages(
            "gợi ý bánh nhỏ vị vani, trà ít ngọt nhé", current, self.repository)
        outputs = [json.loads(m["content"]) for m in messages if m["role"]=="assistant"]
        self.assertLessEqual(len(outputs), 2)
        self.assertTrue(outputs)
        self.assertTrue(all(r.get("search_scope") != "refine" for o in outputs for r in o["requests"]))


    def test_new_combo_does_not_inherit_old_budget_or_types_even_if_model_says_refine(self):
        # Tạo combo cũ rồi mô phỏng lỗi Qwen trích đúng món/vị nhưng nhầm refine.
        old = self.chat("ngân sách không quá 400000 gợi ý bánh kem và trà", self.bundle_value())
        self.assertEqual(old["errors"], [])
        before = deepcopy(load_conversation(self.keeper, self.cid)["order"])
        for text, filters, questions, ids in [
            ("goi y banh nho vi tra xanh va cf dang nhe",
             [{"product_type":"mini","flavor":"matcha"},{"product_type":"coffee","coffee_style":"strong"}],
             ["bánh nhỏ vị trà xanh","cà phê đắng"], ["SP0014","SP0022"]),
            ("gợi ý bánh nhỏ vị dâu với cà phê dịu mát ít đắng",
             [{"product_type":"mini","flavor":"strawberry"},{"product_type":"coffee","coffee_style":"mild"}],
             ["bánh nhỏ vị dâu","cà phê dịu mát ít đắng"], ["SP0017","SP0025"]),
            ("gợi ý bánh nhỏ vani và trà ngọt vừa",
             [{"product_type":"mini","flavor":"vani"},{"product_type":"tea","sweetness":"medium"}],
             ["bánh nhỏ vani","trà ngọt vừa"], ["SP0015","SP0021"]),
        ]:
            value = self.bundle_value(filters=filters,questions=questions);value.bundle_budget=None
            for request in value.requests:request.search_scope="refine"
            result = self.chat(text, value)
            self.assertEqual(result["errors"], [])
            self.assertTrue(result["recommendation_groups"])
            self.assertEqual([i["product_id"] for i in result["recommendation_groups"][0]["items"]], ids)
            self.assertTrue(all(g["budget_vnd"] is None for g in result["recommendation_groups"]))
            self.assertFalse(result["show_checkout"])
            self.assertEqual(load_conversation(self.keeper, self.cid)["order"], before)

    def test_explicit_keep_previous_combo_still_refines(self):
        from app.order_nlu import normalize_bundle_preferences
        value = self.bundle_value(questions=["bánh kem","trà"]);value.bundle_budget=None
        for request in value.requests:request.search_scope="refine"
        current = load_conversation(self.keeper, self.cid)
        for message in ("gợi ý bánh kem và trà giữ ngân sách cũ", "gợi ý bánh kem và trà cùng vị như trước"):
            normalized = normalize_bundle_preferences(message, value, current)
            self.assertTrue(all(r.search_scope=="refine" for r in normalized.requests))


    def test_budget_coffee_prompt_is_not_overridden_by_tea_example(self):
        import json
        current = load_conversation(self.keeper, self.cid)
        messages = llm_client.build_turn_messages(
            "gợi ý bánh kem ít ngọt và cà phê đắng, khoảng giá 450 nghìn", current, self.repository)
        outputs = [json.loads(m["content"]) for m in messages if m["role"]=="assistant"]
        self.assertTrue(outputs)
        self.assertLessEqual(len(outputs), 2)
        self.assertTrue(any(o.get("bundle_budget") for o in outputs))
        self.assertTrue(all(r.get("filters",{}).get("product_type") != "tea"
                            for o in outputs for r in o["requests"]))


    def test_shared_budget_prompt_has_no_conflicting_single_item_example(self):
        import json
        current = load_conversation(self.keeper, self.cid)
        current["request_memory"] = [{"sequence":1,"intents":["recommendation"],
            "questions":[{"intents":["recommendation"],"filters":{"product_type":"mini"}}]}]
        original = deepcopy(current)
        messages = llm_client.build_turn_messages(
            "tôi có 400000 đồng, gợi ý bánh kem trái cây ngọt vừa và trà ít ngọt",
            current, self.repository)
        samples = [json.loads(m["content"]) for m in messages if m["role"]=="assistant"]
        self.assertEqual(len(samples), 1)
        self.assertIsNotNone(samples[0].get("bundle_budget"))
        self.assertEqual(len(samples[0]["requests"]), 2)
        self.assertTrue(all(r.get("question") for r in samples[0]["requests"]))
        self.assertNotIn("ordered_request_memory", json.loads(messages[-1]["content"])["context"])
        self.assertEqual(current, original)


    def test_http_information_schema_allows_total_budget_after_requests(self):
        import json
        schema = llm_client.turn_output_schema()
        budget_schema = schema["anyOf"][0]["properties"]["bundle_budget"]
        self.assertNotEqual(budget_schema, {"type":"null"})
        self.assertIn("BundleBudget", json.dumps(budget_schema))
        self.assertEqual(list(schema["anyOf"][0]["properties"])[-1], "bundle_budget")
        self.assertEqual(list(schema["anyOf"][2]["properties"])[0], "bundle_budget")
        value = self.bundle_value(filters=[{"product_type":"cream_cake","sweetness":"low"},
                                         {"product_type":"coffee","coffee_style":"strong"}],
                                  questions=["bánh kem ít ngọt","cà phê đắng"], budget=450000)
        value.bundle_budget.question = "khoảng giá 450 nghìn"
        wire = value.model_dump();wire["updates"]=[]
        wire = {**{k:v for k,v in wire.items() if k!="bundle_budget"},
                "bundle_budget":wire["bundle_budget"]}
        current = load_conversation(self.keeper,self.cid)
        with patch.object(llm_client,"chat",return_value={"ok":True,"content":json.dumps(wire),"error":None,"model":"qwen3.5:4b"}) as chat:
            parsed = llm_client.extract_turn_legacy(
                "gợi ý bánh kem ít ngọt và cà phê đắng, khoảng giá 450 nghìn",current,
                "http://127.0.0.1:11434","qwen3.5:4b",repository=self.repository)
        self.assertIsNone(parsed["error"])
        self.assertEqual(chat.call_count,1)
        self.assertEqual(parsed["data"].bundle_budget.budget_vnd,450000)


    def test_short_model_clauses_are_grounded_without_another_inference(self):
        import json
        from app.order_nlu import normalize_bundle_preferences, check_turn_grounding
        value = self.bundle_value(300000, filters=[{"product_type":"cream_cake","sweetness":"high"},
                                                 {"product_type":"tea","sweetness":"low"}],
                                  questions=["bánh kem","trà"])
        value.bundle_budget.question="với 300k"
        text="với 300k gợi ý bánh kem ngọt nhiều và trà ít ngọt"
        fixed=normalize_bundle_preferences(text,value)
        self.assertIn("ngot nhieu",fixed.requests[0].question)
        self.assertNotIn("it ngot",fixed.requests[0].question)
        self.assertIn("it ngot",fixed.requests[1].question)
        self.assertEqual([r.filters for r in fixed.requests],[r.filters for r in value.requests])
        self.assertIsNone(check_turn_grounding(text,fixed,self.repository))
        bad=fixed.model_copy(deep=True)
        bad.requests[0].filters.sweetness="low"
        self.assertIsNotNone(check_turn_grounding(text,bad,self.repository))
        wire=value.model_dump();wire["updates"]=[]
        with patch.object(llm_client,"chat",return_value={"ok":True,"content":json.dumps(wire),"error":None,"model":"qwen3.5:4b"}) as chat:
            parsed=llm_client.extract_turn_legacy(text,load_conversation(self.keeper,self.cid),
                "http://127.0.0.1:11434","qwen3.5:4b",repository=self.repository)
        self.assertIsNone(parsed["error"]);self.assertEqual(chat.call_count,1)

    def test_clause_binding_keeps_quantities_and_repeated_prefix_local(self):
        from app.order_nlu import normalize_bundle_preferences,check_turn_grounding
        value=self.bundle_value(500000,filters=[{"product_type":"cream_cake"},{"product_type":"coffee"}],
                                 quantities=[1,2],questions=["bánh kem","cà phê"])
        value.bundle_budget.question="ngân sách 500k"
        message="ngân sách 500k gợi ý 1 bánh kem và 2 cà phê"
        fixed=normalize_bundle_preferences(message,value)
        self.assertIn("1 banh kem",fixed.requests[0].question)
        self.assertNotIn("2",fixed.requests[0].question)
        self.assertIn("2 ca phe",fixed.requests[1].question)
        self.assertIsNone(check_turn_grounding(message,fixed,self.repository))
        value=self.bundle_value(filters=[{"product_type":"mini","flavor":"dâu"},{"product_type":"coffee","coffee_style":"mild"}],
                               questions=["gợi ý bánh nhỏ vị dâu","gợi ý cà phê dịu mát ít đắng"])
        value.bundle_budget=None
        text="gợi ý bánh nhỏ vị dâu với cà phê dịu mát ít đắng"
        fixed=normalize_bundle_preferences(text,value)
        self.assertIsNone(check_turn_grounding(text,fixed,self.repository))
        # Đoạn trùng "trà" không đủ bằng chứng để ghép mù vào nhóm.
        value.requests[0].question="trà";value.requests[1].question="trà"
        original=value.model_dump()
        self.assertEqual(normalize_bundle_preferences("trà xanh và trà sữa",value).model_dump(),original)

    def test_explicit_fruit_is_not_silently_dropped(self):
        from app.order_nlu import normalize_bundle_preferences,check_turn_grounding
        value=self.bundle_value(filters=[{"product_type":"cream_cake","sweetness":"medium"},
                                         {"product_type":"tea","sweetness":"low"}],
                               questions=["bánh kem trái cây ngọt vừa","trà ít ngọt"])
        value.bundle_budget.question="tôi có 400000 đồng"
        text="tôi có 400000 đồng, gợi ý bánh kem trái cây ngọt vừa và trà ít ngọt"
        self.assertEqual(check_turn_grounding(text,normalize_bundle_preferences(text,value),self.repository),
                         "missing_taste_preference")
        value.requests[0].filters.taste_family="fruit"
        self.assertIsNone(check_turn_grounding(text,normalize_bundle_preferences(text,value),self.repository))


    def test_combo_coffee_preference_cannot_be_omitted_or_confused(self):
        from app.order_nlu import check_turn_grounding,normalize_bundle_preferences
        for text, expected in [("béo mặn nhẹ","creamy"),("dịu mát ít đắng","mild"),("đắng","strong")]:
            value=self.bundle_value(filters=[{"product_type":"cream_cake"},{"product_type":"coffee"}],
                                   questions=["bánh kem","cà phê "+text])
            value.bundle_budget=None
            message="gợi ý bánh kem và cà phê "+text
            normalized=normalize_bundle_preferences(message,value)
            self.assertEqual(check_turn_grounding(message,normalized,self.repository),"missing_coffee_preference")
            normalized.requests[1].filters.coffee_style=expected
            self.assertIsNone(check_turn_grounding(message,normalized,self.repository))
        normalized.requests[1].question="ca phe diu mat it dang"
        normalized.requests[1].filters.coffee_style="strong"
        self.assertEqual(check_turn_grounding("gợi ý bánh kem và cà phê dịu mát ít đắng",normalized,self.repository),
                         "missing_coffee_preference")


    def test_retry_retains_previous_json_and_drops_conflicting_fewshots(self):
        import json
        value=self.bundle_value(500000,
            filters=[{"product_type":"cream_cake","sweetness":"high","flavor":"socola"},
                     {"product_type":"coffee","coffee_style":"creamy"}],
            questions=["bánh kem sô cô la ngọt nhiều","cà phê béo mặn nhẹ"])
        value.bundle_budget.question="trong khoảng giá 500k"
        good=value.model_dump();good["updates"]=[]
        bad=deepcopy(good);bad["bundle_budget"]=None
        text="giới thiệu bánh kem sô cô la ngọt nhiều với cà phê béo mặn nhẹ trong khoảng giá 500k"
        replies=[{"ok":True,"content":json.dumps(v),"error":None,"model":"qwen3.5:4b"} for v in (bad,good)]
        with patch.object(llm_client,"chat",side_effect=replies) as chat:
            parsed=llm_client.extract_turn_legacy(text,load_conversation(self.keeper,self.cid),
                "http://127.0.0.1:11434","qwen3.5:4b",repository=self.repository)
        self.assertIsNone(parsed["error"])
        self.assertEqual(chat.call_count,2)
        repair_schema=chat.call_args_list[1].args[3]
        self.assertNotIn("anyOf",repair_schema)
        self.assertIn("bundle_budget",repair_schema["required"])
        self.assertEqual(repair_schema["properties"]["bundle_budget"],
                         {"$ref":"#/$defs/BundleBudget"})
        repair_messages=chat.call_args_list[1].args[0]
        self.assertEqual(len(repair_messages),4)
        self.assertEqual(repair_messages[-2]["role"],"assistant")
        self.assertEqual(json.loads(repair_messages[-2]["content"]),bad)
        self.assertEqual(parsed["data"].requests[1].filters.coffee_style,"creamy")


    def test_retry_independent_price_limits_does_not_force_shared_budget(self):
        import json
        value=self.bundle_value(
            filters=[{"product_type":"cream_cake","budget_vnd":400000,"price_inclusive":False},
                     {"product_type":"coffee","min_budget_vnd":40000,"min_price_inclusive":False}],
            questions=["bánh kem dưới 400k","cà phê trên 40k"])
        value.bundle_budget=None
        good=value.model_dump();good["updates"]=[]
        bad=deepcopy(good)
        for r in bad["requests"]:
            for key in ("budget_vnd","min_budget_vnd","price_inclusive","min_price_inclusive"):
                r["filters"].pop(key,None)
        replies=[{"ok":True,"content":json.dumps(v),"error":None,"model":"qwen3.5:4b"}
                 for v in (bad,good)]
        with patch.object(llm_client,"chat",side_effect=replies) as chat:
            parsed=llm_client.extract_turn_legacy("gợi ý bánh kem dưới 400k và cà phê trên 40k",
                load_conversation(self.keeper,self.cid),"http://127.0.0.1:11434",
                "qwen3.5:4b",repository=self.repository)
        self.assertIsNone(parsed["error"])
        self.assertEqual(chat.call_count,2)
        self.assertIn("anyOf",chat.call_args_list[1].args[3])
        self.assertIsNone(parsed["data"].bundle_budget)
        self.assertEqual(parsed["data"].requests[0].filters.budget_vnd,400000)
        self.assertEqual(parsed["data"].requests[1].filters.min_budget_vnd,40000)



    def test_within_price_budget_is_not_exact_or_quantity(self):
        from app.text_utils import budget_evidence
        for text in ("trong giá 70k","trong mức giá 70000","trong gia 70 nghin"):
            expected=budget_evidence(text)["expected"]
            self.assertEqual(expected,{"budget_vnd":70000,"price_inclusive":True})
        self.assertEqual(budget_evidence("đúng giá 70k")["expected"]["min_budget_vnd"],70000)
        self.assertEqual(budget_evidence("giá 35000")["expected"]["min_budget_vnd"],35000)
        self.assertEqual(budget_evidence("trong giá 60k đến 70k")["expected"]["min_budget_vnd"],60000)
        self.assertEqual(budget_evidence("2 bánh nhỏ")["values"],set())

    def test_mini_sweet_tea_within_budget_has_local_sweetness_and_keeps_draft(self):
        import json
        text="cho tôi combo bánh nhỏ và trà ngọt trong giá 70k nhé"
        current=load_conversation(self.keeper,self.cid)
        value=self.bundle_value(70000,filters=[{"product_type":"mini"},{"product_type":"tea","sweetness":"sweet"}],
                                questions=["bánh nhỏ","trà ngọt"])
        value.bundle_budget.question="trong giá 70k"
        wire=value.model_dump();wire["updates"]=[]
        with patch.object(llm_client,"chat",return_value={"ok":True,"content":json.dumps(wire),"error":None,"model":"qwen3.5:4b"}) as call:
            parsed=llm_client.extract_turn_legacy(text,current,"http://127.0.0.1:11434","qwen3.5:4b",repository=self.repository)
        self.assertIsNone(parsed["error"]);self.assertEqual(call.call_count,1)
        result=self.chat(text,parsed["data"])
        self.assertEqual(result["errors"],[])
        groups=result["recommendation_groups"]
        self.assertTrue(groups)
        for group in groups:
            self.assertEqual(group["total_vnd"],60000)
            self.assertIn(group["items"][0]["product_id"],{f"SP{i:04}" for i in range(13,19)})
            self.assertIn(group["items"][1]["product_id"],{"SP0019","SP0021"})
        self.assertEqual(load_conversation(self.keeper,self.cid)["order"],current["order"])
        self.assertEqual(self.count(),0)
        messages=llm_client.build_turn_messages(text,current,self.repository)
        samples=[json.loads(m["content"]) for m in messages if m["role"]=="assistant"]
        self.assertLessEqual(len(samples),2)
        sample=next(x for x in samples if x.get("bundle_budget"))
        self.assertEqual([r["filters"]["product_type"] for r in sample["requests"]],["mini","tea"])
        self.assertIsNone(sample["requests"][0]["filters"].get("sweetness"))
        self.assertEqual(sample["requests"][1]["filters"]["sweetness"],"sweet")


    def test_combo_sample_preserves_sweetness_in_fresh_and_existing_sessions(self):
        import json
        from app.conversation import new_conversation
        for current in (new_conversation(),load_conversation(self.keeper,self.cid)):
            for phrase,degree in (("ngọt","sweet"),("ngọt nhiều","high"),("ít ngọt","low")):
                messages=llm_client.build_turn_messages(
                    "gợi ý combo bánh nhỏ và trà "+phrase+" trong giá 70k",current,self.repository)
                samples=[json.loads(m["content"]) for m in messages if m["role"]=="assistant"]
                self.assertLessEqual(len(samples),2)
                sample=next(e for e in samples if e.get("bundle_budget"))
                self.assertEqual([r["filters"]["product_type"] for r in sample["requests"]],["mini","tea"])
                self.assertIsNone(sample["requests"][0]["filters"].get("sweetness"))
                self.assertEqual(sample["requests"][1]["filters"]["sweetness"],degree)


    def test_coffee_style_in_flavor_is_normalized_but_still_grounded(self):
        import json
        from pydantic import ValidationError
        from app.schemas import QueryConstraints
        from app.order_nlu import normalize_bundle_preferences,check_turn_grounding
        for alias,style,words in [("strong","strong","đắng"),("đắng","strong","đắng"),
                                  ("creamy","creamy","béo mặn nhẹ"),("mild","mild","dịu mát ít đắng")]:
            value=self.bundle_value(86000,filters=[{"product_type":"mini"},{"product_type":"coffee","flavor":alias}],
                                    questions=["bánh nhỏ","cà phê "+words])
            value.bundle_budget.question="trong giá 86k"
            self.assertEqual(value.requests[1].filters.coffee_style,style)
            self.assertIsNone(value.requests[1].filters.flavor)
            text="đề xuất bánh nhỏ và cà phê "+words+" trong giá 86k"
            self.assertIsNone(check_turn_grounding(text,normalize_bundle_preferences(text,value),self.repository))
        with self.assertRaises(ValidationError):
            QueryConstraints(product_type="coffee",flavor="strong",coffee_style="mild")
        self.assertIsNone(QueryConstraints(product_type="mini",flavor="strong").coffee_style)
        wrong=self.bundle_value(86000,filters=[{"product_type":"mini"},{"product_type":"coffee","flavor":"strong"}],
                                questions=["bánh nhỏ","cà phê ít đắng"])
        wrong.bundle_budget.question="trong giá 86k"
        self.assertIsNotNone(check_turn_grounding(
            "bánh nhỏ và cà phê ít đắng trong giá 86k",wrong,self.repository))

    def test_coffee_bundle_examples_keep_style_in_both_order_and_browsing(self):
        import json
        from app.conversation import new_conversation
        for current in (new_conversation(),load_conversation(self.keeper,self.cid)):
            for phrase,style in [("đắng","strong"),("béo mặn nhẹ","creamy"),("dịu mát ít đắng","mild")]:
                messages=llm_client.build_turn_messages(
                    "đề xuất bánh nhỏ và cà phê "+phrase+" trong giá 86k",current,self.repository)
                samples=[json.loads(m["content"]) for m in messages if m["role"]=="assistant"]
                self.assertLessEqual(len(samples),2)
                sample=next(e for e in samples if e.get("bundle_budget"))
                self.assertEqual([r["filters"]["product_type"] for r in sample["requests"]],["mini","coffee"])
                self.assertEqual(sample["requests"][1]["filters"].get("coffee_style"),style)

    def test_coffee_bundle_repairs_field_name_without_extra_inference(self):
        import json
        value=self.bundle_value(80000,filters=[{"product_type":"mini"},{"product_type":"coffee","coffee_style":"strong"}],
                                questions=["bánh nhỏ","cà phê đắng"])
        value.bundle_budget.question="trong giá 80k"
        wire=value.model_dump();wire["updates"]=[]
        wire["requests"][1]["filters"].pop("coffee_style")
        wire["requests"][1]["filters"]["flavor"]="strong"
        before=load_conversation(self.keeper,self.cid)["order"]
        with patch.object(llm_client,"chat",return_value={"ok":True,"content":json.dumps(wire),"error":None,"model":"qwen3.5:4b"}) as call:
            result=self.client.post("/api/chat",headers=self.headers,json={
                "conversation_id":self.cid,"message":"đề xuất cho tôi bánh nhỏ và cà phê đắng trong giá 80k nhé"}).json()
        self.assertEqual(result["errors"],[])
        self.assertEqual(call.call_count,0)
        self.assertTrue(result["recommendation_groups"])
        for group in result["recommendation_groups"]:
            self.assertEqual(group["total_vnd"],80000)
            self.assertEqual(group["items"][1]["product_id"],"SP0022")
        self.assertEqual(load_conversation(self.keeper,self.cid)["order"],before)
        self.assertEqual(self.count(),0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
