"""Đặt qua chat/giỏ cùng service; chỉ dùng DB tạm, không gọi model thật."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from main import create_app, chat_config
from database import connect, initialize
from app import llm_client
from app.schemas import LLMTurn
from app.storage import load_conversation

FORM={"fullName":"Khách kiểm thử","phone":"0912345678","email":"customer@example.invalid",
      "province":"Hà Nội","ward":"Phường thử","addressLine":"123 Đường thử","deliveryDate":"",
      "deliverySlot":"afternoon","cakeMessage":"Chúc vui","note":"Ghi chú thử","consent":True}
ITEMS=[{"product_id":"SP0014","quantity":2},{"product_id":"SP0025","quantity":1}]

class UnifiedOrderTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(prefix="unified-orders-",dir=Path(__file__).resolve().parents[1]/"runtime")
        self.db=Path(self.folder.name)/"đơn chung.sqlite3"
        self.client=TestClient(create_app(self.db,admin_password="test-only-password"))
        self.client.__enter__()
        self.session=self.new_session()
        self.headers={"Authorization":"Bearer "+self.session["session_token"]}

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.folder.cleanup()

    def new_session(self):
        response=self.client.post("/api/conversations",json={})
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def start(self,items=None,session=None):
        session=session or self.session
        response=self.client.post("/api/checkout/start",headers={"Authorization":"Bearer "+session["session_token"]},
            json={"conversation_id":session["conversation_id"],"items":items or deepcopy(ITEMS)})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()["checkout"]

    def action(self,view,action,*,session=None,form=None,prefix="/api"):
        session=session or self.session
        body={"conversation_id":session["conversation_id"],"draft_id":view["draft_id"],"revision":view["revision"],"action":action}
        if form is not None:body["form"]=form
        if action=="confirm":body["confirmation_token"]=view["confirmation_token"]
        return self.client.post(prefix+"/checkout",headers={"Authorization":"Bearer "+session["session_token"]},json=body)

    def review(self,items=None,session=None):
        items=items or deepcopy(ITEMS)
        view=self.start(items,session)
        response=self.action(view,"review",session=session,form={**FORM,"items":items})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["errors"],[],response.text)
        self.assertEqual(response.json()["checkout"]["stage"],"review",response.text)
        self.assertEqual(self.count("web_orders"),0)
        return response.json()["checkout"]

    def count(self,table):
        assert table in {"web_orders","web_order_links","submissions","tickets"}
        with closing(connect(self.db)) as db:
            return db.execute("SELECT COUNT(*) FROM "+table).fetchone()[0]

    def stock(self,product="SP0014"):
        with closing(connect(self.db)) as db:
            return db.execute("SELECT stock_quantity FROM product_variants WHERE id=?",(product+"-std",)).fetchone()[0]

    def admin_orders(self):
        self.assertEqual(self.client.post("/api/admin/login",json={"password":"test-only-password"}).status_code,200)
        return self.client.get("/api/admin/orders").json()

    def test_chat_creates_same_order_type_and_stock_as_website(self):
        with patch.object(llm_client,"chat",side_effect=AssertionError("Form không được gọi LLM")):
            view=self.review()
            response=self.action(view,"confirm")
        self.assertEqual(response.status_code,200,response.text)
        data=response.json()
        self.assertEqual(data["errors"],[],response.text)
        self.assertEqual(data["state"],"ORDER_SUBMITTED")
        self.assertEqual(data["checkout_mode"],"order")
        self.assertTrue(data["order_id"].startswith("SB-"))
        self.assertEqual(data["checkout"]["order_id"],data["order_id"])
        self.assertIsNone(data["request_id"])
        self.assertIsNone(data["demo_order_id"])
        self.assertEqual((self.stock(),self.stock("SP0025")),(98,99))
        self.assertEqual((self.count("web_orders"),self.count("web_order_links"),self.count("submissions"),self.count("tickets")),(1,1,0,0))
        rows=self.admin_orders()
        self.assertEqual(len(rows["orders"]),1)
        self.assertEqual(rows["orders"][0]["orderId"],data["order_id"])
        self.assertEqual(rows["orders"][0]["orderSource"],"chatbot")
        self.assertEqual(rows["orders"][0]["status"],"pending_confirmation")
        self.assertEqual(rows["orders"][0]["subtotal"],115000)
        self.assertEqual(rows["orders"][0]["customer"]["fullName"],FORM["fullName"])
        self.assertEqual(len(rows["orders"][0]["items"]),2)
        self.assertEqual(rows["chatbotRequests"],[])

    def test_both_channels_share_one_admin_list(self):
        view=self.review();self.action(view,"confirm")
        payload={"customer":{"fullName":FORM["fullName"],"phone":FORM["phone"],"email":None},
            "shippingAddress":{key:FORM[key] for key in ("province","ward","addressLine")},
            "delivery":{},"paymentMethod":"cod","consent":True,"items":[{"productId":"SP0015","quantity":1}]}
        response=self.client.post("/api/orders",json=payload,headers={"Idempotency-Key":str(uuid4())})
        self.assertEqual(response.status_code,201,response.text)
        rows=self.admin_orders()["orders"]
        self.assertEqual(len(rows),2)
        self.assertEqual({o["orderSource"] for o in rows},{"chatbot","website"})

    def test_confirmation_retry_and_alias_do_not_duplicate(self):
        view=self.review()
        first=self.action(view,"confirm").json()
        second=self.action(view,"confirm",prefix="/chatbot/api")
        self.assertEqual(second.status_code,200,second.text)
        self.assertEqual(second.json()["order_id"],first["order_id"])
        self.assertEqual(self.count("web_orders"),1)
        self.assertEqual(self.stock(),98)

    def test_order_access_is_bound_to_conversation(self):
        view=self.review();identifier=self.action(view,"confirm").json()["order_id"]
        response=self.client.get("/api/order-requests/"+identifier,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["kind"],"website_order")
        self.assertEqual(response.json()["order_status"],"pending_confirmation")
        other=self.new_session()
        self.assertEqual(self.client.get("/api/order-requests/"+identifier,headers={"Authorization":"Bearer "+other["session_token"]}).status_code,404)
        self.assertEqual(self.client.get("/api/order-requests/"+identifier).status_code,401)
        other_body={"conversation_id":self.session["conversation_id"],"draft_id":view["draft_id"],"revision":view["revision"],"action":"confirm","confirmation_token":view["confirmation_token"]}
        self.assertEqual(self.client.post("/api/checkout",json=other_body,headers={"Authorization":"Bearer "+other["session_token"]}).status_code,404)

    def test_edit_invalidates_review_and_requires_new_confirmation(self):
        view=self.review()
        edited=self.action(view,"edit").json()["checkout"]
        self.assertEqual(self.action(view,"confirm").status_code,409)
        self.assertEqual(self.count("web_orders"),0)
        response=self.action(edited,"review",form={**FORM,"items":[{"product_id":"SP0015","quantity":3}]})
        latest=response.json()["checkout"]
        self.assertEqual(self.count("web_orders"),0)
        self.assertEqual(self.action(latest,"confirm").status_code,200)
        self.assertEqual(self.stock("SP0015"),97)
        self.assertEqual(self.stock(),100)

    def test_price_change_requires_another_review(self):
        view=self.review()
        with closing(connect(self.db)) as db,db:
            db.execute("UPDATE product_variants SET price_vnd=39000 WHERE id='SP0014-std'")
        self.assertEqual(self.action(view,"confirm").status_code,409)
        self.assertEqual((self.count("web_orders"),self.stock()),(0,100))

    def test_insufficient_stock_never_partially_subtracts(self):
        view=self.review()
        with closing(connect(self.db)) as db,db:
            db.execute("UPDATE product_variants SET stock_quantity=1 WHERE id='SP0025-std'")
        # SP0014 vẫn đủ; SP0025 được yêu cầu thêm 2 nên không đủ.
        edited=self.action(view,"edit").json()["checkout"]
        items=[{"product_id":"SP0014","quantity":2},{"product_id":"SP0025","quantity":2}]
        reviewed=self.action(edited,"review",form={**FORM,"items":items})
        self.assertEqual(reviewed.status_code,200,reviewed.text)
        response=self.action(reviewed.json()["checkout"],"confirm")
        self.assertEqual(response.status_code,200,response.text)
        self.assertIsNone(response.json()["order_id"])
        self.assertEqual((self.count("web_orders"),self.stock(),self.stock("SP0025")),(0,100,1))

    def test_sql_error_rolls_back_order_stock_link_and_context(self):
        view=self.review()
        with closing(connect(self.db)) as db:
            db.execute("CREATE TRIGGER qa_fail_item BEFORE INSERT ON web_order_items BEGIN SELECT RAISE(ABORT,'qa failure'); END")
        response=self.action(view,"confirm")
        self.assertEqual(response.status_code,503,response.text)
        self.assertEqual((self.count("web_orders"),self.count("web_order_links"),self.stock()),(0,0,100))
        with closing(connect(self.db)) as db:
            stored=load_conversation(db,self.session["conversation_id"])
            self.assertIsNone(stored["order"]["submission"])
            db.execute("DROP TRIGGER qa_fail_item")
        self.assertEqual(self.action(view,"confirm").status_code,200)
        self.assertEqual(self.count("web_orders"),1)

    def test_admin_can_cancel_chat_order_and_restore_stock_once(self):
        view=self.review();identifier=self.action(view,"confirm").json()["order_id"]
        self.admin_orders()
        for _ in range(2):
            self.assertEqual(self.client.patch("/api/admin/orders/"+identifier,json={"status":"cancelled"}).status_code,200)
        self.assertEqual((self.stock(),self.stock("SP0025")),(100,100))
        response=self.client.get("/api/order-requests/"+identifier,headers=self.headers)
        self.assertEqual(response.json()["order_status"],"cancelled")
        self.assertEqual(self.action(view,"confirm").json()["order_id"],identifier)
        self.assertEqual(self.count("web_orders"),1)

    def test_order_again_keeps_contact_but_not_message_date_note(self):
        view=self.review();self.action(view,"confirm")
        next_view=self.start([{"product_id":"SP0015","quantity":1}])
        self.assertNotEqual(next_view["draft_id"],view["draft_id"])
        for key in ("fullName","phone","email","province","ward","addressLine"):
            self.assertEqual(next_view["form"][key],FORM[key])
        for key in ("deliveryDate","deliverySlot","cakeMessage","note"):
            self.assertEqual(next_view["form"][key],"")
        response=self.action(next_view,"review",form={**FORM,"items":[{"product_id":"SP0015","quantity":1}]})
        self.assertEqual(response.status_code,200,response.text)
        response=self.action(response.json()["checkout"],"confirm")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.count("web_orders"),2)

    def test_concurrent_conversations_cannot_oversell(self):
        items=[{"product_id":"SP0014","quantity":1}]
        first=self.review(items)
        second_session=self.new_session()
        second=self.review(items,second_session)
        with closing(connect(self.db)) as db,db:
            db.execute("UPDATE product_variants SET stock_quantity=1 WHERE id='SP0014-std'")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(self.action,first,"confirm"),pool.submit(self.action,second,"confirm",session=second_session)]
            responses=[f.result() for f in futures]
        self.assertEqual(sum(bool(r.json().get("order_id")) for r in responses),1)
        self.assertEqual((self.count("web_orders"),self.stock()),(1,0))

    def test_natural_confirmation_uses_shared_tool_and_changes_go_to_support(self):
        self.review()
        base={"intents":["order_request"],"product_mentions":[],"reference":"none","updates":{},
              "clear_slots":[],"ambiguous":False,"handoff_reason":"none","requests":[],"order_operation":"none"}
        value=LLMTurn.model_validate({**base,"action":"confirm"})
        with patch.object(llm_client,"select_model",return_value={"model":"qwen3.5:4b","error":None}), patch.object(llm_client,"extract_turn",return_value={"data":value,"error":None,"attempts":1}):
            response=self.client.post("/api/chat",headers=self.headers,json={"conversation_id":self.session["conversation_id"],"message":"xác nhận đặt hàng"})
        self.assertEqual(response.status_code,200,response.text)
        identifier=response.json()["order_id"]
        self.assertTrue(identifier,response.text)
        self.assertEqual(self.stock(),98)
        value=LLMTurn.model_validate({**base,"action":"cancel"})
        with patch.object(llm_client,"select_model",return_value={"model":"qwen3.5:4b","error":None}), patch.object(llm_client,"extract_turn",return_value={"data":value,"error":None,"attempts":1}):
            response=self.client.post("/api/chat",headers=self.headers,json={"conversation_id":self.session["conversation_id"],"message":"hủy đơn vừa đặt"})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.count("tickets"),1)
        self.assertEqual(self.stock(),98)
        with closing(connect(self.db)) as db:
            self.assertIn(identifier,db.execute("SELECT payload FROM tickets").fetchone()[0])
            self.assertEqual(db.execute("SELECT status FROM web_orders WHERE id=?",(identifier,)).fetchone()[0],"pending_confirmation")

    def test_cancelled_draft_cannot_create_order(self):
        view=self.start()
        self.assertEqual(self.count("web_orders"),0)
        response=self.action(view,"cancel")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["checkout"]["stage"],"cancelled")
        body={"conversation_id":self.session["conversation_id"],"draft_id":view["draft_id"],"revision":view["revision"],"action":"confirm","confirmation_token":"not-a-review"}
        self.assertEqual(self.client.post("/api/checkout",headers=self.headers,json=body).status_code,409)
        self.assertEqual((self.count("web_orders"),self.stock()),(0,100))

    def test_restart_seed_preserves_order_and_legacy_requests_are_not_converted(self):
        view=self.review();identifier=self.action(view,"confirm").json()["order_id"]
        with closing(connect(self.db)) as db,db:
            db.execute("INSERT INTO submissions VALUES(?,?,?,?,?,?,?,?)",("legacy-request",self.session["conversation_id"],"old-draft","old-key","hash","waiting_consultation",'{"id":"legacy-request"}',"2026-11-03T00:00:00+00:00"))
        initialize(self.db)
        with TestClient(create_app(self.db,admin_password="test-only-password")) as restarted:
            restarted.post("/api/admin/login",json={"password":"test-only-password"})
            data=restarted.get("/api/admin/orders").json()
            self.assertEqual(data["orders"][0]["orderId"],identifier)
            self.assertEqual(len(data["orders"]),1)
            self.assertEqual(len(data["chatbotRequests"]),1)
        self.assertEqual(self.stock(),98)

if __name__=="__main__":
    unittest.main()
