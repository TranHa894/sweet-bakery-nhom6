"""FSM bằng hàm: thu thập slot, REVIEW có phiên bản, xác nhận qua tool."""

from copy import deepcopy
from datetime import datetime
import re
import sqlite3
import unicodedata
from uuid import uuid4

from app.handoff import detect_handoff, summarize_draft
from app.order_service import local_now, parse_pickup_at, validate_slots
from app.schemas import OrderTools, ToolResult
from app.storage import fingerprint
from app.text_utils import format_vnd, normalize_text

FIELD_NAMES = {
    "nhu cau": "cake_need", "ma banh": "product_id", "product_id": "product_id",
    "size": "size", "so luong": "quantity", "topping": "toppings", "chu": "cake_text",
    "ngay nhan": "pickup_at", "nhan": "fulfillment", "ten": "name", "sdt": "phone",
    "dien thoai": "phone", "dia chi": "address",
}
FIELD_LABELS = {"cake_need": "nhu cầu bánh", "product_id": "mã bánh", "size": "size", "quantity": "số lượng",
                "toppings": "topping", "cake_text": "chữ trên bánh", "pickup_at": "ngày giờ nhận",
                "fulfillment": "hình thức nhận", "name": "tên giả", "phone": "điện thoại giả", "address": "địa chỉ giả"}


def business_command_text(message: str) -> str:
    """Chữ được đặt trong ngoặc sau 'ghi/viết chữ' là dữ liệu, không là lệnh."""
    return re.sub(r"((?:ghi|viết|viet)\s+(?:chữ|chu)\s*)['\"“].*?['\"”]",
                  r"\1[nội dung chữ]", message, flags=re.I | re.S)


def new_draft(conversation_id: str) -> dict:
    return {
        "id": str(uuid4()), "conversation_id": conversation_id, "state": "BROWSING", "revision": 0,
        "slots": {"cake_need": None, "product_id": None, "size": None, "toppings": None,
                  "quantity": None, "cake_text": None, "pickup_at": None, "fulfillment": None,
                  "name": None, "phone": None, "address": None},
        "verification": {}, "issues": [], "review": None, "submission": None, "tickets": {},
    }


def call_tool(tools: OrderTools, name: str, *args) -> ToolResult:
    try:
        result = tools[name](*args)
        if result["status"] not in {"available", "unavailable", "unknown", "unsupported", "error"}:
            raise ValueError("Tool sai contract.")
        return result
    except sqlite3.Error:
        raise  # Caller rollback toàn lượt, không báo đã lưu khi database lỗi.
    except Exception:
        return {"status": "error", "data": None, "error": "tool_error"}


def missing_slots(slots: dict) -> list[str]:
    missing = [field for field in ("size", "quantity", "toppings", "cake_text", "pickup_at", "fulfillment", "name", "phone") if slots[field] is None]
    if not (slots["cake_need"] or slots["product_id"]):
        missing.insert(0, "cake_need hoặc product_id")
    if slots["fulfillment"] == "delivery" and not slots["address"]:
        missing.append("address")
    return missing


def collect_instructions(draft: dict) -> str:
    missing = missing_slots(draft["slots"])
    questions = {
        "cake_need hoặc product_id": "Bạn muốn bánh gì hoặc có nhu cầu hương vị nào?",
        "size": "Bạn muốn size bao nhiêu cm?", "quantity": "Bạn muốn đặt bao nhiêu bánh?",
        "toppings": "Bạn muốn thêm topping gì, hay không topping?",
        "cake_text": "Bạn muốn ghi chữ gì trên bánh, hay không viết chữ?",
        "pickup_at": "Bạn muốn nhận ngày giờ nào? Dùng YYYY-MM-DD HH:MM theo giờ Việt Nam.",
        "fulfillment": "Bạn muốn nhận tại cửa hàng hay giao mô phỏng?",
        "name": "Bạn cho tên giả bắt đầu DEMO, ví dụ tên: DEMO Khách A nhé.",
        "phone": "Nhập điện thoại giả, ví dụ sđt: TEST-0001.",
        "address": "Nhập địa chỉ giả bắt đầu DEMO, ví dụ địa chỉ: DEMO Địa chỉ A.",
    }
    question = questions[missing[0]] if missing else "Đã đủ thông tin để xem lại; gõ 'xem lại' trước khi gửi."
    return "Đang thu thập bản nháp, chưa xác nhận đơn. Chỉ dùng liên hệ GIẢ để thử.\n" + question


def update_slot(draft: dict, field: str, value, now: datetime | None = None) -> dict:
    updated = deepcopy(draft)
    if updated["state"] not in {"BROWSING", "COLLECTING", "REVIEW"}:
        raise ValueError("Không sửa bản nháp đã hủy/chuyển tư vấn; bắt đầu bản nháp mới.")
    if updated["submission"] and updated["submission"]["confirmed"]:
        raise ValueError("Đơn demo đã xác nhận: phải chuyển ticket, không sửa đơn trực tiếp.")
    if field not in updated["slots"]:
        raise ValueError("Trường chưa hỗ trợ.")
    if field == "quantity" and (type(value) is not int or value <= 0):
        raise ValueError("Số lượng phải là số nguyên dương.")
    if field == "pickup_at":
        value = parse_pickup_at(value)
        if datetime.fromisoformat(value) <= (now or local_now()):
            raise ValueError("Ngày giờ nhận phải ở tương lai, theo Asia/Ho_Chi_Minh.")
    if field == "cake_text" and isinstance(value, str):
        value = unicodedata.normalize("NFC", value)
    if field == "name" and (not isinstance(value, str) or not value.startswith("DEMO ") or not value[5:].strip()):
        raise ValueError("Chỉ dùng tên giả bắt đầu bằng DEMO, ví dụ DEMO Khách A.")
    if field == "phone" and (not isinstance(value, str) or not re.fullmatch(r"TEST-[A-Z0-9-]+", value)):
        raise ValueError("Chỉ dùng mã điện thoại giả TEST-0001; không nhập số thật.")
    if field == "address" and (not isinstance(value, str) or not value.startswith("DEMO ") or not value[5:].strip()):
        raise ValueError("Chỉ dùng địa chỉ giả bắt đầu bằng DEMO.")
    if field == "fulfillment" and value not in {"pickup", "delivery"}:
        raise ValueError("Nhận: cửa hàng hoặc giao.")
    if field == "toppings" and (not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value)):
        raise ValueError("Topping cần danh sách chuỗi; chưa đối chiếu nguồn.")
    if field not in {"quantity", "toppings"} and not isinstance(value, str):
        raise ValueError("Trường cần chuỗi.")
    if field not in {"cake_text", "toppings"} and isinstance(value, str) and not value.strip():
        raise ValueError("Trường không được để trống.")
    updated["slots"][field] = value
    updated["revision"] += 1
    updated.update(state="COLLECTING", review=None, verification={}, issues=[], submission=None)
    updated["verification"][field] = "unverified"
    return updated


def create_review(draft: dict, tools: OrderTools, now: datetime | None = None) -> tuple[dict, str]:
    updated = deepcopy(draft)
    if updated["state"] not in {"COLLECTING", "REVIEW"}:
        return updated, "Bản nháp hiện không thể REVIEW; bắt đầu thu thập trước."
    if updated["submission"]:
        return updated, "Bản này đã được gửi; sửa yêu cầu đã xác nhận cần ticket, không tạo REVIEW mới cho đơn cũ."
    missing = missing_slots(updated["slots"])
    errors = validate_slots(updated["slots"], now or local_now()) if not missing else []
    if missing or errors:
        return updated, "Chưa thể REVIEW: " + ", ".join(missing or errors) + ". " + collect_instructions(updated)
    availability = call_tool(tools, "check_availability", updated)
    quote = call_tool(tools, "calculate_quote", updated)
    if availability["status"] in {"error", "unsupported"} or quote["status"] in {"error", "unsupported"}:
        return updated, "Chưa kiểm tra được nguồn: " + str(availability["error"] or quote["error"]) + ". Không xác nhận đơn."
    source = availability["data"]
    if not isinstance(source, dict) or not isinstance(quote["data"], dict):
        return updated, "Tool chưa trả dữ liệu kiểm tra hợp lệ; không xác nhận đơn."
    if source["catalog_fingerprint"] != quote["data"]["catalog_fingerprint"]:
        return updated, "Nguồn đổi trong lúc kiểm tra; hãy xem lại lần nữa."
    updated.update(state="REVIEW", verification=source["verification"], issues=source["issues"])
    updated["review"] = {
        "revision": updated["revision"], "slots_hash": fingerprint(updated["slots"]),
        "catalog_fingerprint": source["catalog_fingerprint"], "mode": source["mode"],
        "quote": quote["data"]["quote"], "availability": availability["status"],
        "product_name": source.get("product_name"),
    }
    return updated, render_review(updated)


def render_review(draft: dict) -> str:
    review = draft["review"]
    lines = [f"REVIEW bản {draft['revision']} — nguồn {review['mode']}; CHƯA xác nhận đơn."]
    if review.get("product_name"):
        lines.append("Bánh đã đối chiếu: " + review["product_name"])
    for field, value in draft["slots"].items():
        if value is not None:
            shown = {"pickup": "nhận tại cửa hàng (mô phỏng)", "delivery": "giao (mô phỏng)"}.get(value, value) if isinstance(value, str) else value
            if field == "pickup_at":
                from app.order_service import LOCAL_ZONE
                shown = datetime.fromisoformat(value).astimezone(LOCAL_ZONE).strftime("%Y-%m-%d %H:%M") + " (giờ Việt Nam)"
            lines.append(f"- {FIELD_LABELS[field]}: {shown if value != '' else '(không viết chữ)'} [{draft['verification'].get(field, 'unverified')}]")
    if review["quote"] is not None:
        quote = review["quote"]
        lines.append(f"Giá/chiếc: {format_vnd(quote['base_price_vnd'])}; topping/chiếc: {format_vnd(quote['toppings_vnd'])}; viết chữ/chiếc: {format_vnd(quote['cake_text_vnd'])}; số lượng: {quote['quantity']}; giao demo: {format_vnd(quote['delivery_fee_vnd'])}.")
        lines.append("Báo giá MÔ PHỎNG: " + format_vnd(review["quote"]["total_vnd"]) + "; không thanh toán thật.")
    else:
        lines.append("Chưa đủ nguồn để báo giá/khẳng định nhận được yêu cầu.")
    lines.append("Khả dụng: " + review["availability"] + "; cần xác minh: " + (", ".join(draft["issues"]) or "không có mục thiếu trong dữ liệu demo"))
    lines.append("Gõ 'xác nhận' để gửi bản REVIEW này. Empty chỉ lưu yêu cầu chờ tư vấn; mock đủ điều kiện mới tạo đơn DEMO. Sửa trường bất kỳ phải xem lại.")
    return "\n".join(lines)


def request_handoff(draft: dict, tools: OrderTools, reason: str, needs: dict) -> tuple[dict, str]:
    updated = deepcopy(draft)
    ticket = updated["tickets"].get(reason)
    if ticket is None:
        result = call_tool(tools, "create_handoff_ticket", reason, summarize_draft(updated, needs), f"ticket:{updated['id']}:{reason}:{updated['revision']}")
        if result["status"] != "available":
            return updated, "Chưa lưu được ticket: " + str(result["error"]) + ". Không có thông báo nhân viên đã nhận."
        ticket = result["data"]
        updated["tickets"][reason] = ticket
    updated["state"] = "HANDOFF"
    return updated, f"Đã lưu ticket thử nghiệm [{ticket['id']}], lý do: {reason}. Ticket đang chờ xử lý; chưa có nhân viên nhận hoặc được thông báo." + (" Ngoài giờ mở cửa mô phỏng; yêu cầu vẫn chờ xử lý." if ticket.get("outside_hours") else "")


def confirm_review(draft: dict, tools: OrderTools, needs: dict) -> tuple[dict, str]:
    updated = deepcopy(draft)
    if updated["submission"]:
        submission = updated["submission"]
        return updated, f"Bản này đã lưu trước đó [{submission['id']}]: {submission['kind']}. Không tạo bản ghi thứ hai; mọi dữ liệu đều là thử nghiệm."
    if updated["state"] != "REVIEW" or not updated["review"]:
        return updated, "Chưa có REVIEW hợp lệ. Hoàn thành thông tin rồi gõ 'xem lại'; không xác nhận từ 'OK'."
    key = f"submit:{updated['id']}:{updated['revision']}"
    result = call_tool(tools, "submit_order_request", updated, key)
    if result["status"] != "available":
        if result["error"] in {"source_changed_review_again", "stale_review", "invalid_slots"}:
            updated.update(state="COLLECTING", review=None)
        return updated, "Chưa gửi/xác nhận đơn: " + str(result["error"] or result["status"]) + ". Hãy sửa thông tin hoặc xem lại."
    updated["submission"] = result["data"]
    if result["data"]["kind"] == "demo_order":
        if result["data"]["data_mode"] == "local_demo":
            updated["state"] = "DEMO_CONFIRMED"
        return updated, f"Đã lưu ĐƠN MÔ PHỎNG {result['data'].get('order_code', 'DEMO')} [{result['data']['id']}]. Tổng mẫu {format_vnd(result['data']['quote']['total_vnd'])}; payment_status=unpaid. Không thanh toán/giao hàng thật."
    updated, text = request_handoff(updated, tools, "needs_verification", needs)
    return updated, f"Đã lưu YÊU CẦU CHỜ TƯ VẤN [{result['data']['id']}]; chưa xác nhận đơn và chưa có báo giá thật.\n" + text


def handle_order_message(message: str, draft: dict, nlu: dict, tools: OrderTools, needs: dict, now: datetime | None = None) -> tuple[dict, str] | None:
    command_message = business_command_text(message)
    text = normalize_text(command_message)
    field_match = re.match(r"\s*(?:sửa\s+|sua\s+)?([^:]+):\s*(.*)\Z", message, re.I | re.S)
    field = FIELD_NAMES.get(normalize_text(field_match.group(1))) if field_match else None
    # Chữ trên bánh/contact/topping là dữ liệu slot, không phải lệnh gặp staff.
    reason = detect_handoff(command_message) if field in {None, "cake_need"} else None
    if reason:
        return request_handoff(draft, tools, reason, needs)
    change_request = re.match(r"^(?:(?:toi|minh)\s+)?(?:(?:muon|can)\s+)?(?:huy(?:\s+don)?|sua\s+(?:don|thong tin)|(?:doi|tang|giam|them|bo|sua)\s+(?:size|ngay|gio|topping|so luong|chu))\b", text)
    if draft["submission"] and draft["submission"]["confirmed"] and (field or change_request):
        return request_handoff(draft, tools, "change_confirmed_order", needs)
    if text in {"huy", "huy don", "huy dat banh"}:
        updated = deepcopy(draft)
        if updated["submission"]:
            return request_handoff(updated, tools, "cancel_submitted_request", needs)
        updated.update(state="CANCELLED", review=None)
        return updated, "Đã hủy bản nháp; không tạo đơn hoặc yêu cầu mới."
    start = text in {"dat banh", "dat hang", "bat dau dat banh"} or (
        "order_request" in nlu["intents"] and re.match(r"^(?:(?:toi|minh)\s+)?(?:(?:muon|can)\s+)?(?:dat|mua|lay)\b", text)
        and ("banh" in text or bool(nlu["product_ids"]))
    )
    if start:
        updated = new_draft(draft["conversation_id"]) if draft["state"] in {"CANCELLED", "HANDOFF"} or draft["submission"] else deepcopy(draft)
        updated["state"] = "COLLECTING"
        if not nlu["requires_clarification"]:
            if len(nlu["product_ids"]) == 1:
                updated = update_slot(updated, "product_id", nlu["product_ids"][0], now)
            elif nlu["query"]:
                updated = update_slot(updated, "cake_need", message.strip(), now)
            if nlu["quantity"] is not None:
                updated = update_slot(updated, "quantity", nlu["quantity"], now)
            if nlu["size"] is not None:
                updated = update_slot(updated, "size", nlu["size"], now)
        return updated, collect_instructions(updated)
    if field and draft["state"] in {"COLLECTING", "REVIEW"}:
        value = field_match.group(2).strip()
        updated = deepcopy(draft)
        try:
            if field == "quantity":
                if not re.fullmatch(r"[1-9]\d*", value):
                    raise ValueError("Số lượng phải là số nguyên dương.")
                value = int(value)
            elif field == "toppings":
                value = [] if normalize_text(value) in {"khong", "khong topping"} else list(dict.fromkeys(item.strip() for item in value.split(",")))
            elif field == "cake_text" and normalize_text(value) in {"khong", "khong viet chu"}:
                value = ""
            elif field == "fulfillment":
                value = {"cua hang": "pickup", "tai cua hang": "pickup", "giao": "delivery", "giao hang": "delivery"}.get(normalize_text(value), value)
            updated = update_slot(updated, field, value, now)
            return updated, "Đã ghi nhận trường; lựa chọn nghiệp vụ vẫn cần đối chiếu. " + collect_instructions(updated)
        except ValueError as error:
            updated.update(state="COLLECTING", review=None)
            return updated, str(error) + " REVIEW cũ không còn dùng để xác nhận."
    if field:
        return deepcopy(draft), "Chưa ở bước thu thập. Gõ 'đặt bánh' để tạo bản nháp mới; chỉ nhập liên hệ giả."
    if text == "xem lai" and draft["state"] in {"COLLECTING", "REVIEW"}:
        return create_review(draft, tools, now)
    if text == "xac nhan":
        return confirm_review(draft, tools, needs)
    if draft["state"] == "COLLECTING" and text in {"ok", "dong y"}:
        return deepcopy(draft), "Chưa có REVIEW. " + collect_instructions(draft)
    return None
