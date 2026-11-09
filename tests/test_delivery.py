"""GPS/ETA/cập nhật chat; DB riêng, không SMTP, không gọi model."""
from contextlib import closing
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json,sys,tempfile,unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from main import create_app
from database import connect,initialize
from website_delivery import estimate_delivery, in_delivery_hours, fit_delivery_window, delivery_message
POINT={"latitude":21.057,"longitude":105.741,"accuracy":15.0}
FORM={"fullName":"Khách kiểm thử","phone":"0912345678","email":"","province":"","ward":"","addressLine":"",
      "deliveryLocation":POINT,"deliveryDate":"","deliverySlot":"","cakeMessage":"","note":"","consent":True,
      "items":[{"product_id":"SP0014","quantity":1}]}

class DeliveryChecks(unittest.TestCase):
    def setUp(self):
        self.clock=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).replace(hour=10,minute=0,second=0,microsecond=0)
        clock_patch=patch("main.delivery_now",return_value=self.clock)
        clock_patch.start();self.addCleanup(clock_patch.stop)
        self.tmp=tempfile.TemporaryDirectory(prefix="delivery-test-",dir=Path(__file__).resolve().parents[1]/"runtime")
        self.path=Path(self.tmp.name)/"giao hàng.sqlite3"
        self.client=TestClient(create_app(self.path,admin_password="test-only"));self.client.__enter__()
        self.session=self.client.post("/api/conversations",json={}).json()
        self.headers={"Authorization":"Bearer "+self.session["session_token"]}
    def tearDown(self):
        self.client.__exit__(None,None,None);self.tmp.cleanup()
    def place(self):
        start=self.client.post("/api/checkout/start",headers=self.headers,json={"conversation_id":self.session["conversation_id"],"items":FORM["items"]}).json()["checkout"]
        body={"conversation_id":self.session["conversation_id"],"draft_id":start["draft_id"],"revision":start["revision"],"action":"review","form":FORM}
        response=self.client.post("/api/checkout",headers=self.headers,json=body)
        self.assertEqual(response.status_code,200,response.text)
        view=response.json()["checkout"]
        body.update(action="confirm",revision=view["revision"],confirmation_token=view["confirmation_token"]);del body["form"]
        response=self.client.post("/api/checkout",headers=self.headers,json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn("email",response.json()["message"].lower())
        return response.json()["order_id"]
    def login(self):
        self.assertEqual(self.client.post("/api/admin/login",json={"password":"test-only"}).status_code,200)
    def update(self,identifier,status,**kwargs):
        return self.client.patch("/api/admin/orders/"+identifier,json={"status":status,**kwargs})
    def updates(self):
        r=self.client.get("/api/order-updates",headers=self.headers);self.assertEqual(r.status_code,200,r.text)
        return r.json()["orders"]

    def cancel(self, identifier, *, headers=None, prefix="/api", body=None):
        return self.client.post(prefix+"/order-requests/"+identifier+"/cancel",
                                headers=self.headers if headers is None else headers,
                                json={"confirmed":True} if body is None else body)

    def test_customer_cancel_pending_order_updates_admin_history_and_stock(self):
        from app import llm_client
        identifier=self.place()
        with patch.object(llm_client,"chat",side_effect=AssertionError("Hủy bằng nút không gọi LLM")):
            response=self.cancel(identifier)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["status"],"cancelled")
        self.assertFalse(response.json()["can_cancel"])
        self.assertIn(identifier,response.json()["message"])
        self.login()
        self.assertEqual(self.client.get("/api/admin/orders").json()["orders"][0]["status"],"cancelled")
        record=self.client.get("/api/order-requests/"+identifier,headers=self.headers).json()
        self.assertEqual(record["order_status"],"cancelled")
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT stock_quantity FROM product_variants WHERE id='SP0014-std'").fetchone()[0],100)
            notices=db.execute("SELECT content FROM messages WHERE conversation_id=?",(self.session["conversation_id"],)).fetchall()
            self.assertTrue(any(identifier in row[0] and "đã được hủy" in row[0] for row in notices))
        resumed=self.client.get("/api/conversations/"+self.session["conversation_id"],headers=self.headers).json()
        self.assertEqual(resumed["snapshot"]["checkout"]["delivery_tracking"]["status"],"cancelled")

    def test_cancel_requires_own_session_and_hides_other_orders(self):
        identifier=self.place()
        self.assertEqual(self.cancel(identifier,headers={}).status_code,401)
        other=self.client.post("/api/conversations",json={}).json()
        headers={"Authorization":"Bearer "+other["session_token"]}
        denied=self.cancel(identifier,headers=headers)
        missing=self.cancel("SB-missing",headers=headers)
        self.assertEqual(denied.status_code,404)
        self.assertEqual(denied.json(),missing.json())
        self.assertEqual(self.updates()[0]["status"],"pending_confirmation")

    def test_cancel_requires_explicit_strict_confirmation(self):
        identifier=self.place()
        for body in ({},{"confirmed":False},{"confirmed":1},{"confirmed":"true"},{"confirmed":True,"extra":1}):
            with self.subTest(body=body):
                self.assertEqual(self.cancel(identifier,body=body).status_code,422)
        self.assertEqual(self.updates()[0]["status"],"pending_confirmation")
        self.assertTrue(self.updates()[0]["can_cancel"])

    def test_customer_cannot_cancel_after_store_processing(self):
        identifier=self.place();self.login()
        for status in ("confirmed","delivering","completed"):
            self.assertEqual(self.update(identifier,status).status_code,200)
            response=self.cancel(identifier)
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(response.json()["detail"]["code"],"cancellation_requires_staff")
            self.assertEqual(self.updates()[0]["status"],status)
            self.assertFalse(self.updates()[0]["can_cancel"])
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT stock_quantity FROM product_variants WHERE id='SP0014-std'").fetchone()[0],99)

    def test_cancel_retries_and_admin_cancel_do_not_duplicate_restock_or_notice(self):
        identifier=self.place()
        first=self.cancel(identifier).json()
        self.assertEqual(self.cancel(identifier,prefix="/chatbot/api").json(),first)
        self.login();self.assertEqual(self.update(identifier,"cancelled").status_code,200)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT stock_quantity FROM product_variants WHERE id='SP0014-std'").fetchone()[0],100)
            messages=db.execute("SELECT content FROM messages WHERE conversation_id=?",(self.session["conversation_id"],)).fetchall()
            self.assertEqual(sum(identifier in row[0] and "đã được hủy" in row[0] for row in messages),1)

    def test_cancel_failure_rolls_back_all_items_status_tracking_and_message(self):
        with patch.dict(FORM,items=[{"product_id":"SP0014","quantity":2},{"product_id":"SP0025","quantity":1}]):
            identifier=self.place()
        before=self.updates()[0]
        with closing(connect(self.path)) as db:
            db.execute("CREATE TRIGGER qa_cancel_failure BEFORE INSERT ON messages WHEN NEW.content LIKE '%đã được hủy%' BEGIN SELECT RAISE(ABORT,'qa'); END")
        self.assertEqual(self.cancel(identifier).status_code,503)
        self.assertEqual(self.updates()[0],before)
        with closing(connect(self.path)) as db:
            self.assertEqual(tuple(db.execute("SELECT stock_quantity FROM product_variants WHERE id=?",(key,)).fetchone()[0] for key in ("SP0014-std","SP0025-std")),(98,99))
            db.execute("DROP TRIGGER qa_cancel_failure")
        self.assertEqual(self.cancel(identifier).status_code,200)
        with closing(connect(self.path)) as db:
            self.assertEqual(tuple(db.execute("SELECT stock_quantity FROM product_variants WHERE id=?",(key,)).fetchone()[0] for key in ("SP0014-std","SP0025-std")),(100,100))

    def test_concurrent_admin_and_customer_cancel_restore_once(self):
        from concurrent.futures import ThreadPoolExecutor
        identifier=self.place();self.login()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda who:self.cancel(identifier) if who=="customer" else self.update(identifier,"cancelled"),
                                      ("customer","admin")))
        self.assertEqual([result.status_code for result in results],[200,200])
        self.assertEqual(self.updates()[0]["status"],"cancelled")
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT stock_quantity FROM product_variants WHERE id='SP0014-std'").fetchone()[0],100)
            count=db.execute("SELECT COUNT(*) FROM messages WHERE content LIKE '%đã được hủy%'").fetchone()[0]
            self.assertEqual(count,1)

    def test_confirm_racing_customer_cancel_keeps_consistent_status_and_stock(self):
        from concurrent.futures import ThreadPoolExecutor
        identifier=self.place();self.login()
        with ThreadPoolExecutor(max_workers=2) as executor:
            cancellation=executor.submit(self.cancel,identifier)
            confirmation=executor.submit(self.update,identifier,"confirmed")
            codes=(cancellation.result().status_code,confirmation.result().status_code)
        self.assertIn(codes,((200,409),(409,200)))
        status=self.updates()[0]["status"]
        with closing(connect(self.path)) as db:
            stock=db.execute("SELECT stock_quantity FROM product_variants WHERE id='SP0014-std'").fetchone()[0]
            self.assertEqual(stock,100 if status=="cancelled" else 99)
        self.assertIn(status,("cancelled","confirmed"))

    def test_cancel_older_order_preserves_new_draft_and_saved_contact(self):
        from app.storage import load_conversation
        identifier=self.place()
        response=self.client.post("/api/checkout/start",headers=self.headers,
            json={"conversation_id":self.session["conversation_id"],"items":[{"product_id":"SP0022","quantity":2}]})
        self.assertEqual(response.status_code,200,response.text)
        with closing(connect(self.path)) as db:
            before=load_conversation(db,self.session["conversation_id"])
        self.assertEqual(self.cancel(identifier).status_code,200)
        with closing(connect(self.path)) as db:
            after=load_conversation(db,self.session["conversation_id"])
        self.assertEqual(before["order"],after["order"])
        self.assertEqual(before["checkout_contact"],after["checkout_contact"])

    def test_cancel_persists_when_app_restarts(self):
        from website_orders import read_order_updates
        identifier=self.place();self.cancel(identifier)
        with TestClient(create_app(self.path,admin_password="test-only")) as restarted:
            self.assertEqual(restarted.get("/api/order-updates",headers=self.headers).status_code,401)
        with closing(connect(self.path)) as db:
            result=read_order_updates(db,self.session["conversation_id"])[0]
            self.assertEqual(result["order_id"],identifier)
            self.assertEqual(result["status"],"cancelled")
            self.assertFalse(result["can_cancel"])
            self.assertEqual(db.execute("SELECT stock_quantity FROM product_variants WHERE id='SP0014-std'").fetchone()[0],100)

    def test_location_only_checkout_persists_pin_and_provisional_eta(self):
        identifier=self.place();data=self.updates()[0]
        self.assertEqual(data["order_id"],identifier)
        self.assertTrue(data["estimate"]["available"])
        self.assertIn("chưa phải giờ giao",data["message"])
        self.login();row=self.client.get("/api/admin/orders").json()["orders"][0]
        self.assertEqual(row["shippingAddress"]["location"],POINT)
        self.assertEqual(row["subtotal"],35000)
    def test_manual_address_still_supported_and_pin_not_required(self):
        payload={"customer":{"fullName":"Khách thử","phone":"0912345678"},"shippingAddress":{"province":"Hà Nội","ward":"Phường thử","addressLine":"123 Đường thử"},"delivery":{},"paymentMethod":"cod","consent":True,"items":[{"productId":"SP0014","quantity":1}]}
        r=self.client.post("/api/orders",json=payload,headers={"Idempotency-Key":"manual-test-key"})
        self.assertEqual(r.status_code,201,r.text)
        self.assertFalse(r.json()["deliveryTracking"]["estimate"]["available"])
        payload["shippingAddress"]={"province":"","ward":"","addressLine":""}
        self.assertEqual(self.client.post("/api/orders",json=payload,headers={"Idempotency-Key":"missing-address-key"}).status_code,422)
    def test_estimate_validation_and_limits(self):
        for point in ({"latitude":91.0,"longitude":105.0},{"latitude":21.0,"longitude":181.0},{"latitude":True,"longitude":105.0},{"latitude":21.0},{"latitude":21.0,"longitude":105.0,"accuracy":-1.0}):
            with self.subTest(point=point):self.assertEqual(self.client.post("/api/delivery/estimate",json=point).status_code,422)
        self.assertFalse(estimate_delivery({"latitude":0.0,"longitude":0.0})["available"])
        at_store=self.client.get("/api/store").json()["store"]
        r=self.client.post("/api/delivery/estimate",json={"latitude":at_store["latitude"],"longitude":at_store["longitude"]})
        self.assertEqual(r.status_code,200);self.assertGreaterEqual(r.json()["minutesMin"],20)
    def test_confirm_dispatch_arrival_visible_in_owner_chat(self):
        identifier=self.place();self.login()
        for status,phrase in (("confirmed","đã xác nhận"),("delivering","đang được giao"),("completed","đã giao đến")):
            r=self.update(identifier,status);self.assertEqual(r.status_code,200,r.text)
            data=self.updates()[0]
            self.assertEqual(data["status"],status);self.assertIn(phrase,data["message"])
            record=self.client.get("/api/order-requests/"+identifier,headers=self.headers)
            self.assertEqual(record.json()["order_status"],status)
        with closing(connect(self.path)) as db:
            notices=db.execute("SELECT content FROM messages WHERE conversation_id=? AND role='assistant'",(self.session["conversation_id"],)).fetchall()
            self.assertTrue(any("đã giao đến" in n[0] for n in notices))
            self.assertEqual(db.execute("SELECT stock_quantity FROM product_variants WHERE id='SP0014-std'").fetchone()[0],99)
    def test_duplicate_status_does_not_repeat_notification(self):
        identifier=self.place();self.login();self.update(identifier,"confirmed")
        with closing(connect(self.path)) as db:
            before=db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        self.update(identifier,"confirmed")
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM messages").fetchone()[0],before)
    def test_admin_eta_override_timezone_and_auth(self):
        identifier=self.place()
        self.assertEqual(self.update(identifier,"confirmed").status_code,401)
        self.login()
        future=(self.clock+timedelta(hours=1)).isoformat()
        self.assertEqual(self.update(identifier,"confirmed",expectedArrival=future).status_code,200)
        self.assertEqual(self.updates()[0]["estimate"]["method"],"admin_estimate")
        self.assertEqual(self.update(identifier,"delivering",expectedArrival="2099-01-01T10:00").status_code,422)
        self.assertEqual(self.update(identifier,"delivering",expectedArrival="2000-01-01T10:00:00+07:00").status_code,422)
    def test_order_updates_require_session_and_are_isolated(self):
        self.place()
        self.assertEqual(self.client.get("/api/order-updates").status_code,401)
        other=self.client.post("/api/conversations",json={}).json()
        data=self.client.get("/api/order-updates",headers={"Authorization":"Bearer "+other["session_token"]}).json()
        self.assertEqual(data,{"orders":[]})
        raw=json.dumps(self.updates())
        for private in ("0912345678","latitude","longitude","Khách kiểm thử"):
            self.assertNotIn(private,raw)
    def test_delivery_filter_overview_and_cancel_restore_once(self):
        identifier=self.place();self.login();self.update(identifier,"confirmed");self.update(identifier,"delivering")
        rows=self.client.get("/api/admin/orders?status=delivering").json()
        self.assertEqual(rows["total"],1)
        self.assertEqual(rows["orders"][0]["status"],"delivering")
        self.assertEqual(self.client.get("/api/admin/overview").json()["orders"]["delivering"],1)
        self.update(identifier,"cancelled");self.update(identifier,"cancelled")
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT stock_quantity FROM product_variants WHERE id='SP0014-std'").fetchone()[0],100)
    def test_no_email_code_routes_or_database_tables(self):
        self.place()
        with closing(connect(self.path)) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='web_email_outbox'").fetchone())
        self.assertFalse((Path(__file__).resolve().parents[1]/"website_notifications.py").exists())
        self.login()
        self.assertEqual(self.client.get("/api/admin/orders/anything/emails").status_code,404)
        self.assertNotIn("/api/admin/emails/{email_id}/retry",[getattr(route,"path","") for route in self.client.app.routes])
    def test_status_write_failure_rolls_back_delivery_and_chat_history(self):
        identifier=self.place();self.login()
        with closing(connect(self.path)) as db:
            db.execute("CREATE TRIGGER qa_delivery_failure BEFORE INSERT ON messages WHEN NEW.content LIKE 'Cửa hàng đã xác nhận%' BEGIN SELECT RAISE(ABORT,'qa'); END")
        self.assertEqual(self.update(identifier,"confirmed").status_code,503)
        self.assertEqual(self.updates()[0]["status"],"pending_confirmation")
        with closing(connect(self.path)) as db:
            db.execute("DROP TRIGGER qa_delivery_failure")
        self.assertEqual(self.update(identifier,"confirmed").status_code,200)
    def test_legacy_idempotency_without_location_field_stays_compatible(self):
        from app.storage import fingerprint
        payload={"customer":{"fullName":"Khách thử","phone":"0912345678","email":None},"shippingAddress":{"province":"Hà Nội","ward":"Phường thử","addressLine":"123 Đường thử"},"delivery":{"requestedDate":None,"requestedSlot":None},"cakeMessage":"","note":"","paymentMethod":"cod","consent":True,"items":[{"productId":"SP0014","quantity":1}]}
        headers={"Idempotency-Key":"legacy-idempotency"}
        first=self.client.post("/api/orders",json=payload,headers=headers)
        self.assertEqual(first.status_code,201)
        with closing(connect(self.path)) as db,db:
            db.execute("UPDATE web_orders SET payload=?,payload_hash=? WHERE id=?",(json.dumps(payload,ensure_ascii=False),fingerprint(payload),first.json()["orderId"]))
        repeat=self.client.post("/api/orders",json=payload,headers=headers)
        self.assertEqual(repeat.status_code,200,repeat.text)
        self.assertEqual(repeat.json()["orderId"],first.json()["orderId"])

    def test_estimates_stay_inside_08_18_and_roll_to_next_day(self):
        for raw,expected_day in (("2026-11-05T07:00:00+07:00",5),("2026-11-05T10:00:00+07:00",5),("2026-11-05T17:50:00+07:00",6),("2026-11-05T18:00:00+07:00",6),("2026-11-05T23:00:00+07:00",6)):
            with self.subTest(now=raw):
                estimate=estimate_delivery(POINT,now=datetime.fromisoformat(raw))
                start=datetime.fromisoformat(estimate["earliestAt"])
                end=datetime.fromisoformat(estimate["latestAt"])
                self.assertEqual(start.day,expected_day)
                self.assertEqual(start.date(),end.date())
                self.assertTrue(in_delivery_hours(start));self.assertTrue(in_delivery_hours(end))
                if expected_day==6:
                    text=delivery_message("SB-test","pending_confirmation",estimate,True)
                    self.assertIn("Dự kiến nhận",text)
                    self.assertNotIn("phút từ lúc",text)
    def test_eta_window_exact_close_and_too_long_duration(self):
        base=datetime.fromisoformat("2026-11-05T17:25:00+07:00")
        start,end,changed=fit_delivery_window(base,25,10)
        self.assertEqual(end.hour,18);self.assertEqual(end.minute,0)
        self.assertFalse(changed)
        self.assertIsNone(fit_delivery_window(base,600,10))
    def test_admin_rejects_night_arrival_but_accepts_18_boundary(self):
        identifier=self.place();self.login()
        tomorrow=(self.clock+timedelta(days=1)).date().isoformat()
        for stamp in (tomorrow+"T07:59:00+07:00",tomorrow+"T18:01:00+07:00",tomorrow+"T22:00:00+07:00",tomorrow+"T12:00:00Z"):
            with self.subTest(arrival=stamp):
                r=self.update(identifier,"confirmed",expectedArrival=stamp)
                self.assertEqual(r.status_code,422,r.text)
                self.assertTrue(any(f["type"]=="delivery_hours" for f in r.json()["fields"]))
        r=self.update(identifier,"confirmed",expectedArrival=tomorrow+"T18:00:00+07:00")
        self.assertEqual(r.status_code,200,r.text)
        eta=self.updates()[0]["estimate"]
        self.assertEqual(datetime.fromisoformat(eta["latestAt"]).astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).hour,18)
        self.assertEqual(eta["earliestAt"],eta["latestAt"])
    def test_cannot_start_delivery_at_night_or_finish_estimate_after_hours(self):
        identifier=self.place();self.login();self.update(identifier,"confirmed")
        for clock in (self.clock.replace(hour=7),self.clock.replace(hour=18),self.clock.replace(hour=23)):
            with self.subTest(clock=clock),patch("main.delivery_now",return_value=clock):
                r=self.update(identifier,"delivering")
                self.assertEqual(r.status_code,409,r.text)
                self.assertEqual(r.json()["detail"],"delivery_closed")
                self.assertEqual(self.updates()[0]["status"],"confirmed")
        with patch("main.delivery_now",return_value=self.clock.replace(hour=17,minute=59)):
            r=self.update(identifier,"delivering")
            self.assertEqual(r.status_code,409,r.text)
            self.assertEqual(r.json()["detail"],"delivery_exceeds_hours")
    def test_new_checkout_rejects_evening_and_old_orders_are_not_overwritten(self):
        from copy import deepcopy
        start=self.client.post("/api/checkout/start",headers=self.headers,json={"conversation_id":self.session["conversation_id"],"items":FORM["items"]}).json()["checkout"]
        form=deepcopy(FORM);form["deliverySlot"]="evening"
        r=self.client.post("/api/checkout",headers=self.headers,json={"conversation_id":self.session["conversation_id"],"draft_id":start["draft_id"],"revision":start["revision"],"action":"review","form":form})
        self.assertEqual(r.status_code,422)
        identifier=self.place();self.login()
        with closing(connect(self.path)) as db,db:
            payload=json.loads(db.execute("SELECT payload FROM web_orders WHERE id=?",(identifier,)).fetchone()[0])
            payload["delivery"]["requestedSlot"]="evening"
            db.execute("UPDATE web_orders SET payload=? WHERE id=?",(json.dumps(payload),identifier))
        self.assertEqual(self.update(identifier,"confirmed").status_code,409)
        future=(self.clock+timedelta(hours=1)).isoformat()
        self.assertEqual(self.update(identifier,"confirmed",expectedArrival=future).status_code,200)
        with closing(connect(self.path)) as db:
            self.assertIn('"evening"',db.execute("SELECT payload FROM web_orders WHERE id=?",(identifier,)).fetchone()[0])
    def test_store_and_form_only_offer_daytime_hours(self):
        store=self.client.get("/api/store").json()["store"]
        self.assertEqual(store["deliveryHours"]["closesAt"],"18:00")
        html=self.client.get("/thanh-toan.html").text
        self.assertNotIn('value="evening"',html)
        self.assertIn("12:00 – 18:00",html)
        js=self.client.get("/chatbot/static/chat.js").text
        self.assertNotIn('evening: "17:00',js)

    def test_old_night_estimate_is_flagged_without_rewriting_order(self):
        identifier=self.place()
        old={"estimate":{"available":True,"earliestAt":"2099-01-01T21:00:00+07:00","latestAt":"2099-01-01T21:15:00+07:00"},"message":"Giờ cũ 21:00"}
        with closing(connect(self.path)) as db,db:
            db.execute("UPDATE web_delivery_updates SET payload=? WHERE order_id=?",(json.dumps(old),identifier))
        data=self.updates()[0]
        self.assertFalse(data["estimate"]["available"])
        self.assertNotIn("21:00",data["message"])
        with closing(connect(self.path)) as db:
            self.assertEqual(json.loads(db.execute("SELECT payload FROM web_delivery_updates WHERE order_id=?",(identifier,)).fetchone()[0]),old)

    def test_customer_delivery_window_has_weekday_year_and_two_hour_rounding(self):
        from copy import deepcopy
        from website_delivery import customer_delivery_window
        eta={"available":True,"earliestAt":"2026-11-06T10:23:00+07:00","latestAt":"2026-11-06T10:33:00+07:00"}
        original=deepcopy(eta)
        display=customer_delivery_window(eta)
        self.assertEqual(display["text"],"Thứ Sáu, 06/11/2026, khoảng 10:00–12:00 (giờ Việt Nam)")
        self.assertEqual(eta,original)
        self.assertEqual(display["startsAt"],"2026-11-06T10:00:00+07:00")
        self.assertEqual(display["endsAt"],"2026-11-06T12:00:00+07:00")

    def test_customer_rounding_near_closing_keeps_one_hour_inside_service_window(self):
        from website_delivery import customer_delivery_window
        for start,end in (("17:45","17:55"),("17:55","18:00"),("18:00","18:00"),("08:00","08:10")):
            with self.subTest(start=start,end=end):
                display=customer_delivery_window({"available":True,"earliestAt":"2026-11-06T"+start+":00+07:00","latestAt":"2026-11-06T"+end+":00+07:00"})
                begin,finish=map(datetime.fromisoformat,(display["startsAt"],display["endsAt"]))
                self.assertTrue(in_delivery_hours(begin));self.assertTrue(in_delivery_hours(finish))
                self.assertGreaterEqual(finish-begin,timedelta(hours=1))
                self.assertLessEqual(finish-begin,timedelta(hours=2))

    def test_customer_calendar_uses_vietnam_date_across_year_and_sunday(self):
        from website_delivery import customer_delivery_window
        display=customer_delivery_window({"available":True,"earliestAt":"2026-12-31T01:15:00Z","latestAt":"2026-12-31T01:25:00Z"})
        self.assertIn("Thứ Năm, 31/12/2026",display["text"])
        display=customer_delivery_window({"available":True,"earliestAt":"2027-01-03T01:15:00Z","latestAt":"2027-01-03T01:25:00Z"})
        self.assertIn("Chủ Nhật, 03/01/2027",display["text"])
        long_window={"available":True,"earliestAt":"2026-11-06T10:23:00+07:00","latestAt":"2026-11-06T11:23:00+07:00"}
        self.assertIn("10:23–11:23",customer_delivery_window(long_window)["text"])

    def test_delivery_notice_always_has_order_hours_traffic_and_cancellation_help(self):
        identifier="SB-20261105-3841E6C56058"
        eta={"available":True,"earliestAt":"2026-11-06T10:23:00+07:00","latestAt":"2026-11-06T10:33:00+07:00"}
        for status in ("pending_confirmation","confirmed","delivering","completed","cancelled"):
            with self.subTest(status=status):
                text=delivery_message(identifier,status,eta)
                for required in (identifier,"Thứ Sáu","06/11/2026","10:00–12:00","giờ Việt Nam","08:00–18:00","giao thông","nhờ nhân viên","hủy"):
                    self.assertIn(required,text)
        unknown=delivery_message(identifier,"confirmed",None)
        self.assertIn("chưa xác định",unknown)
        self.assertNotIn("06/11/2026",unknown)

    def test_date_change_notice_contains_full_old_and_new_schedules(self):
        from website_delivery import delivery_dates_changed
        old={"available":True,"earliestAt":"2026-12-31T10:23:00+07:00","latestAt":"2026-12-31T10:33:00+07:00"}
        new={"available":True,"earliestAt":"2027-01-01T11:10:00+07:00","latestAt":"2027-01-01T11:20:00+07:00"}
        self.assertTrue(delivery_dates_changed(old,new))
        text=delivery_message("SB-date-change","confirmed",new,previous_estimate=old)
        for required in ("đã cập nhật","cũ Thứ Năm, 31/12/2026","mới Thứ Sáu, 01/01/2027","10:00–12:00","11:00–13:00"):
            self.assertIn(required,text)
        same_day={**new,"earliestAt":"2027-01-01T13:10:00+07:00","latestAt":"2027-01-01T13:20:00+07:00"}
        self.assertFalse(delivery_dates_changed(new,same_day))
        self.assertNotIn("đã cập nhật",delivery_message("SB-same-day","confirmed",same_day,previous_estimate=new))
        self.assertNotIn("đã cập nhật",delivery_message("SB-first","confirmed",new,previous_estimate=None))

    def test_admin_day_change_is_saved_in_chat_and_order_updates(self):
        identifier=self.place();self.login()
        old_date=self.clock.date()
        old={"available":True,"earliestAt":self.clock.replace(hour=11,minute=23).isoformat(),"latestAt":self.clock.replace(hour=11,minute=33).isoformat()}
        with closing(connect(self.path)) as db,db:
            db.execute("UPDATE web_delivery_updates SET payload=? WHERE order_id=?",(json.dumps({"estimate":old,"provisional":True}),identifier))
        new=self.clock+timedelta(days=1,hours=1)
        response=self.update(identifier,"confirmed",expectedArrival=new.isoformat())
        self.assertEqual(response.status_code,200,response.text)
        update=self.updates()[0]
        self.assertIn("đã cập nhật",update["message"])
        self.assertIn(old_date.strftime("%d/%m/%Y"),update["message"])
        self.assertIn(new.strftime("%d/%m/%Y"),update["message"])
        with closing(connect(self.path)) as db:
            notice=db.execute("SELECT content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 1",(self.session["conversation_id"],)).fetchone()[0]
            self.assertEqual(notice,update["message"])
            stored=json.loads(db.execute("SELECT payload FROM web_delivery_updates WHERE order_id=?",(identifier,)).fetchone()[0])
            self.assertEqual(stored["previousEstimate"]["earliestAt"],old["earliestAt"])
        record=self.client.get("/api/order-requests/"+identifier,headers=self.headers).json()
        self.assertEqual(record["delivery_tracking"]["message"],update["message"])

    def test_map_estimate_response_exposes_display_window_but_keeps_raw_eta(self):
        response=self.client.post("/api/delivery/estimate",json=POINT)
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertIn("displayWindow",result)
        display=result["displayWindow"]
        self.assertIn("giờ Việt Nam",display["text"])
        self.assertIn("/"+str(datetime.fromisoformat(display["startsAt"]).year),display["text"])
        self.assertLessEqual(datetime.fromisoformat(display["startsAt"]),datetime.fromisoformat(result["earliestAt"]))
        self.assertGreaterEqual(datetime.fromisoformat(display["endsAt"]),datetime.fromisoformat(result["latestAt"]))

    def test_reschedule_confirmed_order_notifies_old_new_day_without_changing_state(self):
        identifier=self.place();self.login()
        first=self.clock+timedelta(hours=1)
        self.assertEqual(self.update(identifier,"confirmed",expectedArrival=first.isoformat()).status_code,200)
        moved=first+timedelta(days=1)
        response=self.update(identifier,"confirmed",expectedArrival=moved.isoformat())
        self.assertEqual(response.status_code,200,response.text)
        notice=self.updates()[0]
        self.assertEqual(notice["status"],"confirmed")
        self.assertIn("đã cập nhật",notice["message"])
        self.assertIn(first.strftime("%d/%m/%Y"),notice["message"])
        self.assertIn(moved.strftime("%d/%m/%Y"),notice["message"])
        with closing(connect(self.path)) as db:
            before=db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            self.assertEqual(db.execute("SELECT stock_quantity FROM product_variants WHERE id='SP0014-std'").fetchone()[0],99)
        self.assertEqual(self.update(identifier,"confirmed",expectedArrival=moved.isoformat()).status_code,200)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM messages").fetchone()[0],before)

    def test_seed_restart_keeps_pin_and_chat_notice(self):
        identifier=self.place();self.login();self.update(identifier,"confirmed")
        initialize(self.path)
        self.assertEqual(self.updates()[0]["order_id"],identifier)
        self.assertTrue(self.updates()[0]["estimate"]["available"])

if __name__=="__main__":unittest.main()
