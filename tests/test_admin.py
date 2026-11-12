"""Kiểm thử quản trị bằng DB tạm; không dùng mật khẩu hoặc DB đang chạy."""
import json
from contextlib import closing
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from main import create_app
from database import catalog, connect, initialize
from website_catalog import WebsiteCatalogRepository

class AdminTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="admin-test-", dir=Path(__file__).resolve().parents[1]/"runtime")
        self.db = Path(self.folder.name)/"đơn hàng thử.sqlite3"
        self.client = TestClient(create_app(self.db, admin_password="local-test-only"))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.folder.cleanup()

    def login(self):
        self.assertEqual(self.client.post("/api/admin/login",json={"password":"local-test-only"}).status_code,200)

    def order(self, quantity=2):
        payload={"customer":{"fullName":"Khách Kiểm Thử","phone":"0912345678","email":None},
                 "shippingAddress":{"province":"Hà Nội","ward":"Phường thử","addressLine":"123 Đường thử"},
                 "delivery":{"requestedDate":None,"requestedSlot":"afternoon"},
                 "cakeMessage":"Chúc vui","note":"Dữ liệu kiểm thử","paymentMethod":"cod","consent":True,
                 "items":[{"productId":"SP0014","quantity":quantity}]}
        result=self.client.post("/api/orders",json=payload,headers={"Idempotency-Key":str(uuid4())})
        self.assertEqual(result.status_code,201,result.text)
        return result.json()["orderId"]

    def products(self):
        return self.client.get("/api/admin/products").json()["products"]

    def edit(self,product,**changes):
        payload={"price":product["price"],"stock":product["stock"],"active":product["active"],"expectedRevision":product["revision"]}
        payload.update(changes)
        return self.client.patch("/api/admin/products/"+product["id"],json=payload)

    def test_admin_endpoints_require_session(self):
        for endpoint in ("session","overview","products","requests","orders","automation"):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.get("/api/admin/"+endpoint).status_code,401)
        self.assertEqual(self.client.post("/api/admin/login",json={"password":"mật khẩu không đúng"}).status_code,401)
        self.login()
        self.assertTrue(self.client.get("/api/admin/session").json()["authenticated"])
        self.client.post("/api/admin/logout")
        self.assertEqual(self.client.get("/api/admin/overview").status_code,401)

    def test_empty_dashboard_and_products(self):
        self.login()
        data=self.client.get("/api/admin/overview").json()
        self.assertEqual(data["totalOrders"],0)
        self.assertEqual(len(data["trend"]),7)
        self.assertEqual(data["completedMerchandiseValue"],0)
        self.assertEqual(data["products"]["active"],24)
        self.assertEqual(len(self.products()),24)

    def test_overview_values_are_not_payment_revenue(self):
        self.login()
        completed=self.order(2)
        pending=self.order(1)
        for status in ("confirmed","completed"):
            self.assertEqual(self.client.patch("/api/admin/orders/"+completed,json={"status":status}).status_code,200)
        data=self.client.get("/api/admin/overview").json()
        self.assertEqual(data["totalOrders"],2)
        self.assertEqual(data["todayOrders"],2)
        self.assertEqual(data["orders"]["pending_confirmation"],1)
        self.assertEqual(data["completedMerchandiseValue"],70000)
        self.assertEqual({o["orderId"] for o in data["recentOrders"]},{completed,pending})
        self.assertEqual(data["recentOrders"][0]["paymentStatus"],"unpaid")

    def test_filter_search_pagination_and_dates(self):
        self.login()
        first=self.order(1);self.order(2)
        self.client.patch("/api/admin/orders/"+first,json={"status":"confirmed"})
        data=self.client.get("/api/admin/orders",params={"status":"confirmed","limit":1,"include_requests":False}).json()
        self.assertEqual(data["total"],1);self.assertEqual(data["orders"][0]["orderId"],first)
        data=self.client.get("/api/admin/orders",params={"q":"khach kiem thu","limit":1,"offset":1}).json()
        self.assertEqual(data["total"],2);self.assertEqual(len(data["orders"]),1)
        self.assertEqual(self.client.get("/api/admin/orders",params={"q":"%' OR 1=1 --"}).json()["total"],0)
        for params in ({"limit":0},{"limit":501},{"offset":-1},{"status":"paid"},{"dateFrom":"2026-11-05","dateTo":"2026-11-01"},{"dateFrom":"invalid"},{"dateFrom":"0001-01-01"}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/api/admin/orders",params=params).status_code,422)

    def test_date_filter_uses_store_timezone(self):
        self.login()
        identifier=self.order()
        with closing(connect(self.db)) as db, db:
            db.execute("UPDATE web_orders SET created_at=? WHERE id=?",("2026-11-03T18:00:00+00:00",identifier))
        self.assertEqual(self.client.get("/api/admin/orders",params={"dateFrom":"2026-11-04","dateTo":"2026-11-04"}).json()["total"],1)
        self.assertEqual(self.client.get("/api/admin/orders",params={"dateTo":"2026-11-03"}).json()["total"],0)

    def test_catalog_changes_reach_web_and_chatbot(self):
        self.login()
        p=next(p for p in self.products() if p["id"]=="SP0014")
        result=self.edit(p,price=39000,stock=7)
        self.assertEqual(result.status_code,200,result.text)
        public=next(p for p in self.client.get("/api/products").json() if p["id"]=="SP0014")
        self.assertEqual((public["price"],public["stock"]),(39000,7))
        live=WebsiteCatalogRepository(self.db).get_product("SP0014")["product"]
        self.assertEqual(live["variants"][0]["price_vnd"],39000)
        self.assertEqual(live["variants"][0]["stock_status"],"in_stock")
        initialize(self.db)
        current=next(p for p in self.products() if p["id"]=="SP0014")
        self.assertEqual((current["price"],current["stock"]),(39000,7))
        self.assertIn("SP0014",[p["id"] for p in self.client.get("/api/admin/overview").json()["products"]["lowStock"]])

    def test_hide_and_restore_does_not_delete_product(self):
        self.login();p=self.products()[0]
        result=self.edit(p,active=False)
        self.assertEqual(result.status_code,200)
        self.assertNotIn(p["id"],[p["id"] for p in catalog(self.db)])
        self.assertEqual(WebsiteCatalogRepository(self.db).get_product(p["id"])["status"],"no_results")
        self.assertEqual(self.edit(result.json(),active=True).status_code,200)
        self.assertIn(p["id"],[p["id"] for p in catalog(self.db)])

    def test_stale_inventory_edit_cannot_overwrite_sale(self):
        self.login()
        p=next(p for p in self.products() if p["id"]=="SP0014")
        self.order(2)
        self.assertEqual(self.edit(p,stock=200).status_code,409)
        current=next(p for p in self.products() if p["id"]=="SP0014")
        self.assertEqual(current["stock"],98)

    def test_invalid_product_edit_does_not_mutate(self):
        self.login();p=self.products()[0]
        for changes in ({"stock":-1},{"stock":True},{"price":1.5},{"price":-1},{"active":"true"},{"expectedRevision":"oops"}):
            with self.subTest(changes=changes):
                self.assertEqual(self.edit(p,**changes).status_code,422)
        self.assertEqual(self.products()[0],p)
        self.client.post("/api/admin/logout")
        self.assertEqual(self.edit(p,stock=1).status_code,401)

    def test_price_edit_preserves_order_snapshot_and_cancel_is_idempotent(self):
        self.login();identifier=self.order()
        p=next(p for p in self.products() if p["id"]=="SP0014")
        self.assertEqual(self.edit(p,price=42000).status_code,200)
        order=self.client.get("/api/admin/orders").json()["orders"][0]
        self.assertEqual(order["items"][0]["unit_price"],35000)
        self.assertEqual(order["subtotal"],70000)
        self.assertTrue(order["items"][0]["image"].endswith(".webp"))
        for _ in range(2):
            self.assertEqual(self.client.patch("/api/admin/orders/"+identifier,json={"status":"cancelled"}).status_code,200)
        current=next(p for p in self.products() if p["id"]=="SP0014")
        self.assertEqual((current["stock"],current["price"]),(100,42000))
        self.assertEqual(self.client.patch("/api/admin/orders/"+identifier,json={"status":"confirmed"}).status_code,409)

    def test_requests_include_metadata_without_becoming_web_order(self):
        self.login()
        with closing(connect(self.db)) as db, db:
            db.execute("INSERT INTO conversations VALUES(?,?,?)",("test-conversation","{}","2026-11-04T00:00:00+00:00"))
            payload=json.dumps({"checkout_form":{"fullName":"Khách kiểm thử","phone":"0912345678"}},ensure_ascii=False)
            db.execute("INSERT INTO submissions VALUES(?,?,?,?,?,?,?,?)",("test-request","test-conversation","test-draft","test-key","hash","waiting_consultation",payload,"2026-11-04T00:00:00+00:00"))
            ticket=json.dumps({"reason":"complaint","summary":"Nội dung kiểm thử","priority":"high","status":"pending"})
            db.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?)",("test-ticket","test-conversation","ticket-key","hash",ticket,"2026-11-04T01:00:00+00:00"))
        data=self.client.get("/api/admin/requests").json()
        self.assertEqual(data["total"],2)
        self.assertEqual(data["records"][0]["recordType"],"ticket")
        self.assertEqual(data["records"][1]["id"],"test-request")
        self.assertEqual(self.client.get("/api/admin/orders").json()["orders"],[])
        counts=self.client.get("/api/admin/overview").json()
        self.assertEqual((counts["consultationCount"],counts["ticketCount"]),(1,1))

    def test_admin_assets_are_isolated_and_no_secrets_served(self):
        for url in ("/admin.html","/website/admin.html","/admin.css","/admin.js"):
            response=self.client.get(url)
            self.assertEqual(response.status_code,200,url)
            self.assertEqual(response.headers["cache-control"],"no-store")
        html=self.client.get("/admin.html").text
        self.assertNotIn('href="style.css"',html)
        self.assertNotIn("chatbot-widget.js",html)
        self.assertEqual(self.client.get("/runtime/admin-password.txt").status_code,404)
        self.assertEqual(self.client.post("/api/admin/login",json={"password":"local-test-only"},headers={"Origin":"https://other.example"}).status_code,403)

    def test_automation_alerts_and_sla_escalation(self):
        self.login()
        order_id = self.order(2)
        auto = self.client.get("/api/admin/automation").json()
        self.assertTrue(any(e["reference_id"] == order_id and e["event_type"] == "order_created" for e in auto["events"]))

        # Giảm SLA xuống 5 phút và giả lập đơn đã đặt quá 20 phút
        res = self.client.put("/api/admin/automation/settings", json={"sla_minutes": 5, "low_stock_threshold": 20})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["settings"]["sla_minutes"], 5)

        with closing(connect(self.db)) as db, db:
            db.execute("UPDATE web_orders SET created_at='2026-11-01T00:00:00Z' WHERE id=?", (order_id,))

        scan = self.client.post("/api/admin/automation/scan", json={"test_alert": True}).json()
        self.assertEqual(scan["slaSummary"]["overdueCount"], 1)
        self.assertEqual(scan["slaSummary"]["overdueOrders"][0]["orderId"], order_id)
        self.assertTrue(any(e["reference_id"] == order_id and e["event_type"] == "sla_breach_warning" for e in scan["events"]))
        self.assertTrue(any(e["event_type"] == "system_test" for e in scan["events"]))

        # Xác nhận đơn hàng -> tạo sự kiện order_status_changed và hết quá hạn SLA
        self.assertEqual(self.client.patch("/api/admin/orders/" + order_id, json={"status": "confirmed"}).status_code, 200)
        auto_after = self.client.get("/api/admin/automation").json()
        self.assertEqual(auto_after["slaSummary"]["overdueCount"], 0)
        self.assertTrue(any(e["reference_id"] == order_id and e["event_type"] == "order_status_changed" for e in auto_after["events"]))

if __name__ == "__main__":
    unittest.main()
