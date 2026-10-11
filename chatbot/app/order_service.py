"""Adapter tool local: đọc catalog qua interface, kiểm tra nguồn, lưu demo/yêu cầu."""

from datetime import datetime, timedelta, timezone
import json
import re
import sqlite3
from typing import Protocol
from zoneinfo import ZoneInfo

from app.handoff import create_handoff_ticket
from app.repositories.catalog import CatalogRepository
from app.schemas import OrderTools, ToolResult, validate_product
from app.storage import fingerprint, save_record, load_order_request, utc_now
from app.text_utils import normalize_text

LOCAL_ZONE = ZoneInfo("Asia/Ho_Chi_Minh")


class OrderMetadataRepository(Protocol):
    def get_order_metadata(self, product_id: str) -> dict: ...


def local_now() -> datetime:
    return datetime.now(LOCAL_ZONE)


def parse_pickup_at(value: str) -> str:
    """Chỉ nhận YYYY-MM-DD HH:MM local; không đoán 'mai' hoặc ngày thiếu năm."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", value):
        raise ValueError("Dùng YYYY-MM-DD HH:MM theo Asia/Ho_Chi_Minh.")
    return datetime.strptime(value.replace("T", " "), "%Y-%m-%d %H:%M").replace(tzinfo=LOCAL_ZONE).astimezone(timezone.utc).isoformat()


def validate_slots(slots: dict, now: datetime) -> list[str]:
    errors = []
    if type(slots.get("quantity")) is not int or slots["quantity"] <= 0:
        errors.append("quantity_positive_integer")
    try:
        received = datetime.fromisoformat(slots["pickup_at"])
        if received.tzinfo is None or received <= now:
            errors.append("pickup_at_future_local")
    except (TypeError, ValueError, KeyError):
        errors.append("pickup_at_future_local")
    if not (slots.get("cake_need") or slots.get("product_id")):
        errors.append("cake_need_required")
    if not slots.get("size") or slots.get("toppings") is None or slots.get("cake_text") is None:
        errors.append("choices_required")
    if slots.get("fulfillment") not in {"pickup", "delivery"}:
        errors.append("fulfillment_required")
    if not str(slots.get("name") or "").startswith("DEMO ") or not re.fullmatch(r"TEST-[A-Z0-9-]+", slots.get("phone") or ""):
        errors.append("fake_contact_required")
    if slots.get("fulfillment") == "delivery" and not str(slots.get("address") or "").startswith("DEMO "):
        errors.append("fake_address_required")
    return errors


def validate_metadata(metadata: dict) -> None:
    keys = {"toppings", "max_cake_text_length", "cake_text_price_vnd", "fulfillment_modes", "delivery_fee_vnd", "stock_quantity"}
    optional = {"business", "active", "writing_supported", "topping_allergens"}
    if not isinstance(metadata, dict) or not keys <= set(metadata) or set(metadata) - keys - optional:
        raise ValueError("Metadata sai schema.")
    for key in ("max_cake_text_length", "cake_text_price_vnd", "delivery_fee_vnd"):
        value = metadata[key]
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("Metadata số sai kiểu.")
    for key in ("toppings", "stock_quantity"):
        mapping = metadata[key]
        if mapping is not None and (not isinstance(mapping, dict) or any(not isinstance(k, str) or (v is not None and (type(v) is not int or v < 0)) for k, v in mapping.items())):
            raise ValueError("Metadata mapping sai kiểu.")
    modes = metadata["fulfillment_modes"]
    if modes is not None and (not isinstance(modes, list) or any(mode not in {"pickup", "delivery"} for mode in modes)):
        raise ValueError("Hình thức nhận sai schema.")


def inspect_order(repository: CatalogRepository, draft: dict, now: datetime) -> dict:
    """Một lần đọc nguồn tạo cả verification/khả dụng/quote, không tin cờ từ khách."""
    slots = draft["slots"]
    verification = {key: "unverified" for key in slots}
    issues = validate_slots(slots, now)
    result = {"mode": "unknown", "is_mock": False, "verification": verification, "issues": issues,
              "availability": "unknown", "quote": None, "catalog_fingerprint": None, "error": None}
    try:
        caps = repository.get_capabilities()
        result.update(mode=caps["data_mode"], is_mock=caps["is_mock"])
        if caps["data_mode"] == "empty":
            result["issues"] += ["catalog_unconfigured", "cake_text_limit_unverified", "lead_time_unverified"]
            return result
        if caps["data_mode"] not in {"mock", "local_demo"} or not caps["is_mock"]:
            result.update(availability="unsupported", error="real_order_adapter_not_configured")
            return result
        if not slots["product_id"]:
            result["issues"].append("product_unverified")
            return result
        product_result = repository.get_product(slots["product_id"])
        if product_result["status"] == "error":
            raise ValueError("Nguồn sản phẩm lỗi.")
        if product_result["status"] != "success":
            result["issues"].append("product_unverified")
            return result
        product = product_result["product"]
        validate_product(product)
        result["product_name"] = product["name"]
        if not product["is_mock"] or product["id"] != slots["product_id"]:
            raise ValueError("Nhãn/ID nguồn không khớp.")
        verification["product_id"] = "verified"
        if product.get("active") is False:
            result["issues"].append("product_inactive")
        metadata = None
        method = getattr(repository, "get_order_metadata", None)
        if method is not None:
            meta_result = method(product["id"])
            if meta_result["status"] == "error":
                raise ValueError("Nguồn metadata lỗi.")
            if meta_result["status"] == "success":
                metadata = meta_result["metadata"]
                validate_metadata(metadata)
        result["catalog_fingerprint"] = fingerprint({"product": product, "metadata": metadata})
        variants = [variant for variant in product["variants"] if slots["size"] and normalize_text(variant["size"] or "").replace(" ", "") == normalize_text(slots["size"]).replace(" ", "")]
        variant = variants[0] if len(variants) == 1 else None
        if variant is None:
            result["issues"].append("size_unverified")
        else:
            verification["size"] = "verified"
        requested = datetime.fromisoformat(slots["pickup_at"]) if slots["pickup_at"] else None
        if metadata and "business" in metadata and requested is not None:
            clock = requested.astimezone(LOCAL_ZONE).strftime("%H:%M")
            business = metadata["business"]
            if not business["opens_at"] <= clock < business["closes_at"]:
                result["issues"].append("outside_opening_hours")
            else:
                verification["opening_hours"] = "verified"
        if draft.get("allergies"):
            info = product.get("allergen_info", {"status": "unknown", "items": []})
            excludes = {normalize_text(x) for x in draft["allergies"]}
            if info["status"] in {"unknown", "not_listed", "may_contain"}:
                result["issues"].append("allergen_requires_staff")
            elif excludes.intersection(normalize_text(x) for x in info["items"]):
                result["issues"].append("allergen_conflict")
        if product["min_lead_hours"] is None:
            result["issues"].append("lead_time_unverified")
        elif requested is not None and requested < now + timedelta(hours=product["min_lead_hours"]):
            result["issues"].append("lead_time_too_short")
        else:
            verification["lead_time"] = "verified"
        topping_cost = 0
        if slots["toppings"]:
            options = metadata["toppings"] if metadata else None
            for topping in slots["toppings"]:
                matched = [key for key in (options or {}) if normalize_text(key) == normalize_text(topping)]
                if len(matched) != 1 or options[matched[0]] is None:
                    result["issues"].append("topping_unverified")
                else:
                    topping_cost += options[matched[0]]
                    if draft.get("allergies"):
                        info = (metadata.get("topping_allergens") or {}).get(matched[0], {"status": "unknown", "items": []})
                        if info["status"] in {"unknown", "not_listed", "may_contain"} or excludes.intersection(normalize_text(x) for x in info["items"]):
                            result["issues"].append("topping_allergen_requires_staff")
            verification["toppings"] = "verified" if "topping_unverified" not in result["issues"] else "unverified"
        elif slots["toppings"] == []:
            verification["toppings"] = "not_applicable"
        text_cost = 0
        if slots["cake_text"]:
            limit = metadata["max_cake_text_length"] if metadata else None
            if limit is None:
                result["issues"].append("cake_text_limit_unverified")
            elif len(slots["cake_text"]) > limit:
                result["issues"].append("cake_text_too_long")
            elif "ghi chu tren banh" not in [normalize_text(option) for option in (product["customization"] or [])] or not metadata or metadata["cake_text_price_vnd"] is None:
                result["issues"].append("cake_text_unverified")
            else:
                verification["cake_text"] = "verified"
                text_cost = metadata["cake_text_price_vnd"]
        elif slots["cake_text"] == "":
            verification["cake_text"] = "not_applicable"
        modes = metadata["fulfillment_modes"] if metadata else None
        if modes is None or slots["fulfillment"] not in modes:
            result["issues"].append("fulfillment_unverified")
        else:
            verification["fulfillment"] = "verified"
        delivery_fee = 0 if slots["fulfillment"] == "pickup" else (metadata["delivery_fee_vnd"] if metadata else None)
        if slots["fulfillment"] == "delivery" and metadata and "business" in metadata:
            regions = metadata["business"]["delivery_regions"]
            matched = [fee for region, fee in regions.items() if normalize_text(region) in normalize_text(slots.get("address") or "")]
            delivery_fee = matched[0] if len(matched) == 1 else None
        if delivery_fee is None:
            result["issues"].append("delivery_fee_unverified")
        if variant is not None and type(slots["quantity"]) is int and slots["quantity"] > 0:
            count = (metadata["stock_quantity"] or {}).get(variant["id"]) if metadata else None
            if variant["stock_status"] == "out_of_stock" or (count is not None and count < slots["quantity"]):
                result["availability"] = "unavailable"
            elif variant["stock_status"] == "in_stock" and count is not None:
                result["availability"] = "available"
            else:
                result["issues"].append("availability_unverified")
            if variant["price_vnd"] is None:
                result["issues"].append("price_unverified")
            elif not result["issues"]:
                unit = variant["price_vnd"] + topping_cost + text_cost
                result["quote"] = {"variant_id": variant["id"], "base_price_vnd": variant["price_vnd"],
                    "toppings_vnd": topping_cost, "cake_text_vnd": text_cost, "unit_price_vnd": unit,
                    "quantity": slots["quantity"], "delivery_fee_vnd": delivery_fee,
                    "total_vnd": unit * slots["quantity"] + delivery_fee, "is_mock": True}
        for key in ("quantity", "pickup_at", "name", "phone", "address"):
            verification[key] = "verified" if not issues else "unverified"
        return result
    except Exception:
        result.update(availability="error", error="order_source_error", quote=None)
        return result


def check_availability(repository: CatalogRepository, draft: dict, now: datetime | None = None) -> ToolResult:
    inspection = inspect_order(repository, draft, now or local_now())
    return {"status": inspection["availability"], "data": inspection, "error": inspection["error"]}


def calculate_quote(repository: CatalogRepository, draft: dict, now: datetime | None = None) -> ToolResult:
    inspection = inspect_order(repository, draft, now or local_now())
    status = "error" if inspection["error"] else ("available" if inspection["quote"] else "unknown")
    if inspection["availability"] == "unsupported":
        status = "unsupported"
    elif inspection["availability"] == "unavailable":
        status = "unavailable"
    return {"status": status, "data": inspection, "error": inspection["error"]}


def submit_order_request(connection: sqlite3.Connection, repository: CatalogRepository, draft: dict, idempotency_key: str, now: datetime | None = None) -> ToolResult:
    if repository.get_capabilities()["data_mode"] == "local_demo":
        return submit_local_order(connection, repository, draft, idempotency_key, now)
    review = draft.get("review")
    if draft["state"] != "REVIEW" or not review or review["revision"] != draft["revision"] or review["slots_hash"] != fingerprint(draft["slots"]):
        return {"status": "error", "data": None, "error": "stale_review"}
    inspection = inspect_order(repository, draft, now or local_now())
    if inspection["error"]:
        return {"status": inspection["availability"], "data": None, "error": inspection["error"]}
    if validate_slots(draft["slots"], now or local_now()):
        return {"status": "unknown", "data": None, "error": "invalid_slots"}
    if inspection["catalog_fingerprint"] != review["catalog_fingerprint"] or inspection["quote"] != review["quote"] or inspection["mode"] != review["mode"]:
        return {"status": "error", "data": None, "error": "source_changed_review_again"}
    if inspection["availability"] == "unavailable":
        return {"status": "unavailable", "data": None, "error": "requested_quantity_unavailable"}
    demo = inspection["mode"] == "mock" and inspection["availability"] == "available" and inspection["quote"] is not None and not inspection["issues"]
    return save_record(connection, "submissions", draft["conversation_id"], idempotency_key, {
        "draft_id": draft["id"], "revision": draft["revision"], "kind": "demo_order" if demo else "waiting_consultation",
        "slots": draft["slots"], "verification": inspection["verification"], "issues": inspection["issues"],
        "quote": inspection["quote"] if demo else None, "data_mode": inspection["mode"],
        "is_mock": True, "confirmed": demo,
    })


def create_order_tools(repository: CatalogRepository, connection: sqlite3.Connection, conversation_id: str, now: datetime | None = None) -> OrderTools:
    """Interface gồm năm callable gắn owner; flow không biết JSON hay SQL."""
    def inspect_bound(draft: dict, callback) -> ToolResult:
        if draft["conversation_id"] != conversation_id:
            return {"status": "error", "data": None, "error": "conversation_mismatch"}
        return callback(repository, draft, now)

    def submit_bound(draft: dict, key: str) -> ToolResult:
        if draft["conversation_id"] != conversation_id:
            return {"status": "error", "data": None, "error": "conversation_mismatch"}
        return submit_order_request(connection, repository, draft, key, now)
    def ticket_bound(reason, summary, key):
        outside_hours = None
        method = getattr(repository, "get_business_settings", None)
        if method is not None:
            result = method()
            if result["status"] == "success":
                business = result["settings"]
                clock = (now or local_now()).astimezone(LOCAL_ZONE).strftime("%H:%M")
                outside_hours = not business["opens_at"] <= clock < business["closes_at"]
        return create_handoff_ticket(connection, conversation_id, reason, summary, key, outside_hours=outside_hours)
    return {
        "check_availability": lambda draft: inspect_bound(draft, check_availability),
        "calculate_quote": lambda draft: inspect_bound(draft, calculate_quote),
        "submit_order_request": submit_bound,
        "create_handoff_ticket": ticket_bound,
        "get_order": lambda identifier: get_order(connection, identifier, conversation_id),
    }


def get_order(connection: sqlite3.Connection, identifier: str, conversation_id: str) -> ToolResult:
    record = load_order_request(connection, identifier, conversation_id)
    return {"status": "available" if record else "unavailable", "data": record, "error": None}


def submit_local_order(connection, repository, draft, idempotency_key, now=None) -> ToolResult:
    """SAVEPOINT trong transaction: kiểm tra, trừ stock, ghi snapshot cùng thành công."""
    from app.config import ORDER_PROVIDER
    if ORDER_PROVIDER != "local_demo":
        return {"status": "unsupported", "data": None, "error": "order_provider_unsupported"}
    # Giữ transaction mở cho caller lưu cả conversation; không commit riêng một đơn.
    if not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
    connection.execute("SAVEPOINT create_demo_order")
    try:
        existing = connection.execute("SELECT payload,conversation_id FROM submissions WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if existing:
            record = json.loads(existing["payload"])
            if existing["conversation_id"] != draft["conversation_id"] or record["revision"] != draft["revision"] or record["slots"] != draft["slots"]:
                result = {"status": "error", "data": None, "error": "idempotency_conflict"}
            else:
                result = {"status": "available", "data": load_order_request(connection, record["id"], draft["conversation_id"]), "error": None}
            connection.execute("RELEASE create_demo_order")
            return result
        review = draft.get("review")
        if draft["state"] != "REVIEW" or not review or review["revision"] != draft["revision"] or review["slots_hash"] != fingerprint(draft["slots"]):
            result = {"status": "error", "data": None, "error": "stale_review"}
        else:
            bound_repo = repository.using_connection(connection)
            inspection = inspect_order(bound_repo, draft, now or local_now())
            if inspection["error"]:
                result = {"status": "error", "data": None, "error": inspection["error"]}
            elif inspection["availability"] != "available" or inspection["issues"] or inspection["quote"] is None:
                result = {"status": "unavailable" if inspection["availability"] == "unavailable" else "unknown", "data": None,
                          "error": ",".join(inspection["issues"]) or "requested_quantity_unavailable"}
            elif inspection["catalog_fingerprint"] != review["catalog_fingerprint"] or inspection["quote"] != review["quote"] or inspection["mode"] != review["mode"]:
                result = {"status": "error", "data": None, "error": "source_changed_review_again"}
            else:
                quote, slots = inspection["quote"], draft["slots"]
                changed = connection.execute(
                    "UPDATE product_variants SET stock_quantity=stock_quantity-? WHERE id=? AND product_id=? AND stock_quantity>=? AND stock_status='in_stock'",
                    (slots["quantity"], quote["variant_id"], slots["product_id"], slots["quantity"]),
                ).rowcount
                if changed != 1:
                    result = {"status": "unavailable", "data": None, "error": "stock_changed"}
                else:
                    product = bound_repo.get_product(slots["product_id"])["product"]
                    snapshot = {"name": product["name"], "product_id": product["id"], "variant_id": quote["variant_id"],
                                "size": slots["size"], "toppings": slots["toppings"], "topping_prices": {t["name"]: t["price_vnd"] for t in product["topping_options"] if normalize_text(t["name"]) in [normalize_text(x) for x in slots["toppings"]]},
                                "cake_text": slots["cake_text"], "price": quote, "source": "local_demo", "is_demo": True}
                    result = save_record(connection, "submissions", draft["conversation_id"], idempotency_key, {
                        "draft_id": draft["id"], "revision": draft["revision"], "kind": "demo_order", "slots": slots,
                        "verification": inspection["verification"], "issues": [], "quote": quote,
                        "data_mode": "local_demo", "is_mock": True, "is_demo": True, "source": "local_demo",
                        "confirmed": True, "payment_status": "unpaid", "snapshot": snapshot,
                    })
                    if result["status"] == "available":
                        identifier = result["data"]["id"]
                        code = "DEMO-" + identifier[:8].upper()
                        connection.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
                            identifier, draft["conversation_id"], code, idempotency_key, draft["id"], draft["revision"],
                            quote["total_vnd"], "DEMO_CONFIRMED", "unpaid", 1, "local_demo", utc_now(),
                        ))
                        connection.execute("INSERT INTO order_items(order_id,product_id,variant_id,quantity,snapshot) VALUES(?,?,?,?,?)", (
                            identifier, slots["product_id"], quote["variant_id"], slots["quantity"], json.dumps(snapshot, ensure_ascii=False),
                        ))
                        result["data"] = load_order_request(connection, identifier, draft["conversation_id"])
        if result["status"] != "available":
            connection.execute("ROLLBACK TO create_demo_order")
        connection.execute("RELEASE create_demo_order")
        return result
    except Exception:
        connection.execute("ROLLBACK TO create_demo_order")
        connection.execute("RELEASE create_demo_order")
        raise
