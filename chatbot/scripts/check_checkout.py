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


if __name__ == "__main__":
    unittest.main(verbosity=2)
