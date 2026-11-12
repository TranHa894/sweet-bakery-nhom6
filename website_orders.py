"""Một service tạo đơn cho giỏ hàng và chatbot; caller quản lý transaction SQLite."""
import json
import re
from copy import deepcopy
from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.storage import utc_now, fingerprint, save_record
from app.order_service import create_order_tools
from website_delivery import DeliveryLocation, estimate_delivery, delivery_message, in_delivery_hours, customer_delivery_window
from automation_alerts import dispatch_new_order_alerts, dispatch_status_change_alert


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Customer(Model):
    fullName: str = Field(min_length=2, max_length=100)
    phone: str = Field(max_length=20)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, value):
        if not re.fullmatch(r"(0[35789]\d{8}|\+84[35789]\d{8})", value):
            raise ValueError("invalid_phone")
        return value

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("invalid_email")
        return value or None


class Address(Model):
    province: str = Field(default="", max_length=100)
    ward: str = Field(default="", max_length=100)
    addressLine: str = Field(default="", max_length=250)
    location: DeliveryLocation | None = None

    @model_validator(mode="after")
    def address_or_pin(self):
        if self.location is None and (not self.province or not self.ward or len(self.addressLine)<5):
            raise ValueError("address_or_location_required")
        return self


class Delivery(Model):
    requestedDate: date | None = None
    requestedSlot: Literal["morning", "afternoon"] | None = None

    @field_validator("requestedDate")
    @classmethod
    def future(cls, value):
        if value and value < datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date():
            raise ValueError("past_date")
        return value


class Item(Model):
    productId: str = Field(min_length=1, max_length=50)
    quantity: int = Field(strict=True, ge=1, le=99)


class Order(Model):
    customer: Customer
    shippingAddress: Address
    delivery: Delivery
    cakeMessage: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=500)
    paymentMethod: Literal["cod"]
    consent: bool = Field(strict=True)
    items: list[Item] = Field(min_length=1, max_length=24)

    @field_validator("consent")
    @classmethod
    def consent_true(cls, value):
        if not value:
            raise ValueError("consent_required")
        return value

    @field_validator("items")
    @classmethod
    def unique(cls, value):
        if len({item.productId for item in value}) != len(value):
            raise ValueError("duplicate_product")
        return value


class OrderError(ValueError):
    def __init__(self, detail, message, status_code=409):
        super().__init__(message)
        self.detail, self.status_code = detail, status_code


def delivery_info(db,row):
    saved=db.execute("SELECT payload,dispatched_at,delivered_at FROM web_delivery_updates WHERE order_id=?",(row["id"],)).fetchone()
    result=json.loads(saved["payload"]) if saved else {}
    status="delivering" if saved and saved["dispatched_at"] and row["status"]=="confirmed" else row["status"]
    estimate=result.get("estimate") or {}
    if status not in {"completed","cancelled"} and estimate.get("available"):
        try:
            valid=all(in_delivery_hours(datetime.fromisoformat(estimate[key])) for key in ("earliestAt","latestAt"))
        except (KeyError,TypeError,ValueError):
            valid=False
        if not valid:
            result={**result,"estimate":{"available":False,"notice":"Lịch dự kiến cũ ngoài khung 08:00–18:00; cửa hàng cần xác nhận lại."},
                    "message":f"Đơn {row['id']}: lịch dự kiến cũ cần được cửa hàng xác nhận lại trong 08:00–18:00."}
    estimate=result.get("estimate")
    if estimate and estimate.get("available"):
        estimate={**estimate,"displayWindow":customer_delivery_window(estimate)}
        result["estimate"]=estimate
    result["message"]=delivery_message(row["id"],status,estimate,result.get("provisional",False),result.get("previousEstimate"))
    return {**result,"status":status,"can_cancel":status=="pending_confirmation","dispatchedAt":saved["dispatched_at"] if saved else None,
            "deliveredAt":saved["deliveredAt"] if saved and "deliveredAt" in saved.keys() else (saved["delivered_at"] if saved else None)}


def order_view(db, row, details=False):
    result = {"orderId": row["id"], "status": row["status"], "currency": "VND",
              "subtotal": row["subtotal"], "shippingFee": row["shipping_fee"],
              "total": None if row["shipping_fee"] is None else row["subtotal"] + row["shipping_fee"],
              "createdAt": row["created_at"], "paymentStatus": "unpaid",
              "orderSource": "chatbot" if db.execute("SELECT 1 FROM web_order_links WHERE order_id=?", (row["id"],)).fetchone() else "website"}
    delivery=delivery_info(db,row)
    result["status"]=delivery["status"]
    result["deliveryTracking"]=delivery
    if details:
        result.update(json.loads(row["payload"]))
        result["items"] = []
        for item in db.execute("SELECT i.product_id,i.product_name,i.quantity,i.unit_price,p.payload FROM web_order_items i JOIN products p ON p.id=i.product_id WHERE i.order_id=?", (row["id"],)):
            result["items"].append({key: item[key] for key in ("product_id", "product_name", "quantity", "unit_price")} |
                                   {"image": json.loads(item["payload"]).get("image", "")})
    return result


def place_order(db, body, key, *, conversation_id=None, expected_summary=None):
    """Cùng giá/stock/snapshot/idempotency. Không commit; mọi lỗi phải rollback ở caller."""
    if not db.in_transaction:
        raise RuntimeError("place_order cần transaction ghi trước khi kiểm tra tồn.")
    payload = body.model_dump(mode="json")
    digest = fingerprint(payload)
    existing = db.execute("SELECT * FROM web_orders WHERE idempotency_key=?", (key,)).fetchone()
    if existing:
        owner = db.execute("SELECT conversation_id FROM web_order_links WHERE order_id=?", (existing["id"],)).fetchone()
        old_payload=json.loads(existing["payload"])
        old_payload.get("shippingAddress",{}).setdefault("location",None)
        same_payload=existing["payload_hash"]==digest or fingerprint(old_payload)==digest
        if not same_payload or (owner["conversation_id"] if owner else None) != conversation_id:
            raise OrderError("idempotency_conflict", "Khóa gửi đơn đã được dùng cho thông tin khác.")
        return order_view(db, existing), False
    rows = []
    subtotal = 0
    for item in body.items:
        product = db.execute("SELECT p.id,p.name,p.active,v.id variant_id,v.price_vnd,v.stock_quantity FROM products p JOIN product_variants v ON v.id=p.id||'-std' WHERE p.id=?", (item.productId,)).fetchone()
        if not product or not product["active"]:
            raise OrderError("product_unavailable", "Một món đã ngừng bán. Bạn quay lại form để chọn món khác nhé.")
        if product["price_vnd"] is None or product["stock_quantity"] is None or product["stock_quantity"] < item.quantity:
            raise OrderError("stock_unavailable", "Một món chưa đủ tồn kho hoặc chưa có giá xác định. Bạn quay lại form để kiểm tra món và số lượng nhé.")
        rows.append((product, item.quantity))
        subtotal += product["price_vnd"] * item.quantity
    if expected_summary is not None:
        current = [(p["id"], p["name"], quantity, p["price_vnd"]) for p, quantity in rows]
        reviewed = [(p["product_id"], p["name"], p["quantity"], p["unit_price_vnd"]) for p in expected_summary["items"]]
        if current != reviewed or subtotal != expected_summary["subtotal_vnd"]:
            raise OrderError("source_changed_review_again", "Giá hoặc sản phẩm đã thay đổi. Bạn xem lại đơn trước khi xác nhận nhé.")
    identifier = "SB-" + datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y%m%d") + "-" + uuid4().hex[:12].upper()
    now = utc_now()
    db.execute("INSERT INTO web_orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (identifier, key, digest, body.customer.fullName, body.customer.phone, body.customer.email,
                json.dumps(payload, ensure_ascii=False), subtotal, None, "pending_confirmation", "cod", now, now))
    alert_items = []
    for product, quantity in rows:
        db.execute("INSERT INTO web_order_items(order_id,product_id,variant_id,product_name,quantity,unit_price) VALUES(?,?,?,?,?,?)",
                   (identifier, product["id"], product["variant_id"], product["name"], quantity, product["price_vnd"]))
        changed = db.execute("UPDATE product_variants SET stock_quantity=stock_quantity-? WHERE id=? AND stock_quantity>=?",
                             (quantity, product["variant_id"], quantity))
        if changed.rowcount != 1:
            raise OrderError("stock_unavailable", "Tồn kho vừa thay đổi; chưa tạo được đơn.")
        alert_items.append({
            "product_id": product["id"],
            "variant_id": product["variant_id"],
            "product_name": product["name"],
            "quantity": quantity,
            "unit_price": product["price_vnd"],
        })
    estimate=estimate_delivery(body.shippingAddress.location.model_dump() if body.shippingAddress.location else None)
    tracking={"estimate":estimate,"provisional":True,"message":delivery_message(identifier,"pending_confirmation",estimate,True)}
    db.execute("INSERT INTO web_delivery_updates VALUES(?,?,NULL,NULL,?)",(identifier,json.dumps(tracking,ensure_ascii=False),now))
    addr_parts = [body.shippingAddress.addressLine, body.shippingAddress.ward, body.shippingAddress.province]
    if any(addr_parts):
        address_text = ", ".join(p for p in addr_parts if p)
    elif body.shippingAddress.location:
        address_text = f"Ghim bản đồ ({body.shippingAddress.location.latitude:.5f}, {body.shippingAddress.location.longitude:.5f})"
    else:
        address_text = "Theo thông tin đơn hàng"
    dispatch_new_order_alerts(
        db,
        order_id=identifier,
        customer_name=body.customer.fullName,
        phone=body.customer.phone,
        email=body.customer.email,
        address_text=address_text,
        delivery_date=str(body.delivery.requestedDate) if body.delivery.requestedDate else None,
        delivery_slot=body.delivery.requestedSlot,
        cake_message=body.cakeMessage,
        note=body.note,
        subtotal=subtotal,
        items=alert_items,
    )
    row = db.execute("SELECT * FROM web_orders WHERE id=?", (identifier,)).fetchone()
    return order_view(db, row), True


def order_update(db, row):
    """Metadata cho khách; không trả liên hệ, địa chỉ hoặc vị trí."""
    tracking = delivery_info(db, row)
    return {"order_id": row["id"], "status": tracking["status"], "message": tracking["message"],
            "updated_at": row["updated_at"], "estimate": tracking.get("estimate"),
            "can_cancel": tracking["can_cancel"]}


def cancel_order(db, identifier, *, conversation_id=None):
    """Caller giữ BEGIN IMMEDIATE; hủy, hoàn tồn và thông báo cùng transaction."""
    if not db.in_transaction:
        raise RuntimeError("cancel_order cần transaction ghi trước khi đọc trạng thái.")
    row = db.execute("SELECT * FROM web_orders WHERE id=?", (identifier,)).fetchone()
    owner = db.execute("SELECT conversation_id FROM web_order_links WHERE order_id=?", (identifier,)).fetchone()
    if row is None or (conversation_id is not None and (not owner or owner["conversation_id"] != conversation_id)):
        raise OrderError("order_not_found", "Không tìm thấy đơn thuộc phiên hiện tại.", 404)
    tracking = delivery_info(db, row)
    status = tracking["status"]
    if status == "cancelled":
        return order_update(db, row)  # Gửi lại không hoàn tồn hoặc ghi tin lần nữa.
    if conversation_id is not None and status != "pending_confirmation":
        raise OrderError("cancellation_requires_staff",
                         "Đơn đã được cửa hàng xử lý, mình chưa tự hủy. Bạn nhắn nhờ nhân viên hủy đơn kèm mã " + identifier + " nhé.")
    if status not in {"pending_confirmation", "confirmed", "delivering"}:
        raise OrderError("invalid_transition", "Đơn đã giao không thể hủy bằng thao tác này.")
    now = utc_now()
    for item in db.execute("SELECT variant_id,quantity FROM web_order_items WHERE order_id=?", (identifier,)).fetchall():
        db.execute("UPDATE product_variants SET stock_quantity=stock_quantity+? WHERE id=?",
                   (item["quantity"], item["variant_id"]))
    tracking.update(provisional=False, cancelledBy="customer" if conversation_id is not None else "store")
    notice = delivery_message(identifier, "cancelled", tracking.get("estimate"),
                              previous_estimate=tracking.get("previousEstimate"))
    tracking["message"] = notice
    db.execute("""INSERT INTO web_delivery_updates VALUES(?,?,?,?,?)
        ON CONFLICT(order_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at""",
        (identifier, json.dumps(tracking, ensure_ascii=False), tracking.get("dispatchedAt"), tracking.get("deliveredAt"), now))
    db.execute("UPDATE web_orders SET status='cancelled',updated_at=? WHERE id=?", (now, identifier))
    dispatch_status_change_alert(
        db,
        order_id=identifier,
        old_status=status,
        new_status="cancelled",
        customer_name=row["customer_name"],
        phone=row["phone"],
        email=row["email"],
        subtotal=row["subtotal"],
    )
    if owner:
        db.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,'assistant',?,?)",
                   (owner["conversation_id"], notice, now))
        # Cập nhật snapshot của đơn vừa hủy; không đụng bản nháp mới của khách.
        from app.storage import load_conversation, save_conversation
        conversation = load_conversation(db, owner["conversation_id"])
        submission = (conversation or {}).get("order", {}).get("submission")
        if submission and submission.get("id") == identifier:
            fresh = delivery_info(db, db.execute("SELECT * FROM web_orders WHERE id=?", (identifier,)).fetchone())
            submission.update(order_status="cancelled", delivery_tracking=fresh)
            save_conversation(db, conversation)
    return order_update(db, db.execute("SELECT * FROM web_orders WHERE id=?", (identifier,)).fetchone())

def form_to_order(form, items):
    """Ánh xạ form chatbot sang đúng schema của giỏ hàng, không lấy giá từ trình duyệt."""
    return Order.model_validate({
        "customer": {"fullName": form["fullName"], "phone": form["phone"], "email": form.get("email") or None},
        "shippingAddress": {**{key: form[key] for key in ("province", "ward", "addressLine")}, "location":form.get("deliveryLocation")},
        "delivery": {"requestedDate": form.get("deliveryDate") or None, "requestedSlot": form.get("deliverySlot") or None},
        "cakeMessage": form.get("cakeMessage", ""), "note": form.get("note", ""), "paymentMethod": "cod",
        "consent": form["consent"], "items": [{"productId": item["product_id"], "quantity": item["quantity"]} for item in items]
    })


def create_website_order_tools(repository, connection, conversation_id):
    """Adapter của website, truyền vào API chatbot; standalone giữ tools mặc định."""
    tools = create_order_tools(repository, connection, conversation_id)
    legacy_get_order = tools["get_order"]
    legacy_handoff = tools["create_handoff_ticket"]

    def submit(draft, key):
        from app.checkout import verify_checkout
        from app.order_flow import order_items
        if draft["conversation_id"] != conversation_id:
            return {"status": "unavailable", "data": None, "error": "conversation_mismatch"}
        if not draft.get("checkout_form"):
            return {"status": "unavailable", "data": None, "error": "invalid_slots",
                    "message": "Bạn điền form thông tin và xem lại trước khi đặt hàng nhé."}
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")
        connection.execute("SAVEPOINT website_order")
        try:
            prior = connection.execute("SELECT payload FROM web_order_links WHERE conversation_id=? AND draft_id=? AND revision=?",
                                       (conversation_id, draft["id"], draft["revision"])).fetchone()
            if prior:
                record = json.loads(prior["payload"])
            else:
                summary = verify_checkout(draft, repository)
                body = form_to_order(draft["checkout_form"], order_items(draft))
                result, _ = place_order(connection, body, "chat:" + key,
                                        conversation_id=conversation_id, expected_summary=summary)
                record = {"id": result["orderId"], "order_code": result["orderId"],
                          "conversation_id": conversation_id, "draft_id": draft["id"], "revision": draft["revision"],
                          "kind": "website_order", "slots": deepcopy(draft["slots"]),
                          "items": order_items(draft), "verification": deepcopy(draft["verification"]),
                          "issues": deepcopy(draft["issues"]), "quote": None, "data_mode": draft["review"]["mode"],
                          "is_mock": True, "is_demo": True, "source": "website", "confirmed": True,
                          "payment_status": "unpaid", "created_at": result["createdAt"],
                          "checkout_form": deepcopy(draft["checkout_form"]), "checkout_summary": summary,
                          "order_status": result["status"], "delivery_tracking":result["deliveryTracking"]}
                connection.execute("INSERT INTO web_order_links(order_id,conversation_id,draft_id,revision,payload) VALUES(?,?,?,?,?)",
                                   (record["id"], conversation_id, draft["id"], draft["revision"], json.dumps(record, ensure_ascii=False)))
        except (OrderError, ValueError) as error:
            connection.execute("ROLLBACK TO website_order")
            connection.execute("RELEASE website_order")
            return {"status": "unavailable", "data": None, "error": "source_changed_review_again",
                    "message": str(error) if isinstance(error, OrderError) else "Thông tin hoặc giá đã thay đổi. Bạn quay lại form và xem lại nhé."}
        except Exception:
            connection.execute("ROLLBACK TO website_order")
            connection.execute("RELEASE website_order")
            raise
        connection.execute("RELEASE website_order")
        return {"status": "available", "data": record, "error": None}

    def get_order(identifier):
        row = connection.execute("SELECT l.payload,o.status,o.id FROM web_order_links l JOIN web_orders o ON o.id=l.order_id WHERE l.order_id=? AND l.conversation_id=?",
                                 (identifier, conversation_id)).fetchone()
        if row:
            return {"status": "available", "data": {**json.loads(row["payload"]), "order_status": delivery_info(connection,row)["status"], "delivery_tracking":delivery_info(connection,row)}, "error": None}
        return legacy_get_order(identifier)

    def ticket(reason, summary, key):
        # Đơn website không nằm trong submissions. Kiểm tra owner ở bảng liên kết.
        from app.storage import load_conversation
        conversation = load_conversation(connection, conversation_id)
        submission = conversation.get("order", {}).get("submission") if conversation else None
        if not submission or submission.get("kind") != "website_order":
            return legacy_handoff(reason, summary, key)
        owner = connection.execute("SELECT 1 FROM web_order_links WHERE order_id=? AND conversation_id=?",
                                   (submission["id"], conversation_id)).fetchone()
        if not owner:
            return {"status": "unavailable", "data": None, "error": "order_owner_mismatch"}
        from app.storage import safe_history_text
        return save_record(connection, "tickets", conversation_id, key, {
            "reason": reason, "summary": safe_history_text(summary), "status": "pending", "order_id": submission["id"],
            "priority": "high" if reason in {"severe_allergy", "allergen_requires_staff", "complaint"} else "normal",
            "missing_information": [], "outside_hours": None, "is_mock": True, "is_demo": True, "source": "local_ticket",
            "note": "Đã ghi nhận yêu cầu hỗ trợ cho đơn hàng; chưa tự sửa hoặc hủy đơn."
        })

    def cancel(identifier):
        try:
            return {"status": "available", "data": cancel_order(connection, identifier, conversation_id=conversation_id),
                    "error": None}
        except OrderError as error:
            return {"status": "unavailable", "data": None, "error": error.detail, "message": str(error)}

    tools.update(submit_order_request=submit, get_order=get_order, create_handoff_ticket=ticket, cancel_order=cancel)
    return tools

def read_order_updates(connection,conversation_id):
    """Chỉ metadata giao của đơn thuộc phiên; không trả email/địa chỉ/toạ độ."""
    rows=connection.execute("SELECT o.id,o.status,o.updated_at FROM web_orders o JOIN web_order_links l ON l.order_id=o.id WHERE l.conversation_id=? ORDER BY o.created_at DESC LIMIT 30",(conversation_id,)).fetchall()
    return [order_update(connection,row) for row in rows]
