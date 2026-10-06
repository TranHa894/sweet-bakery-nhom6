"""Lưu ticket chờ xử lý; không gửi email/tin nhắn hoặc giả nhân viên đã nhận."""

import re
import sqlite3

from app.schemas import ToolResult
from app.storage import safe_history_text, save_record, load_conversation
from app.text_utils import normalize_text


def detect_handoff(message: str, unknown_streak: int = 0) -> str | None:
    text = normalize_text(message)
    rules = [
        ("severe_allergy", r"\b(?:di ung (?:nghiem trong|nang)|phan ve)\b"),
        ("complaint", r"\b(?:khieu nai|phan nan)\b"),
        ("change_confirmed_order", r"\b(?:sua|doi|huy)\b.*\bdon (?:da )?xac nhan\b"),
        ("customer_requested", r"\b(?:nhan vien|nguoi that|tu van vien)\b"),
    ]
    for reason, pattern in rules:
        if re.search(pattern, text):
            return reason
    return "two_unknown_turns" if unknown_streak >= 2 else None


def summarize_draft(draft: dict, needs: dict) -> str:
    # Chỉ tóm tắt nhu cầu; không đưa tên/phone/địa chỉ vào summary ticket.
    slots = draft["slots"]
    from app.order_flow import missing_slots
    missing = missing_slots(slots)
    return safe_history_text(
        f"Nhu cầu: {slots['cake_need'] or needs.get('product_terms') or 'chưa rõ'}; "
        f"product_id: {slots['product_id'] or 'chưa đối chiếu'}; size: {slots['size'] or 'chưa rõ'}; "
        f"số lượng: {slots['quantity']}; nhận: {slots['pickup_at'] or 'chưa rõ'}; "
        f"hình thức: {slots['fulfillment'] or 'chưa rõ'}; còn thiếu: {', '.join(missing) or 'không thiếu trường nhập'}; cần kiểm tra: {', '.join(draft.get('issues', [])) or 'theo lý do ticket'}."
    )


def create_handoff_ticket(connection: sqlite3.Connection, conversation_id: str, reason: str, summary: str, idempotency_key: str, *, outside_hours=None) -> ToolResult:
    conversation = load_conversation(connection, conversation_id)
    submission = conversation.get("order", {}).get("submission") if conversation else None
    order_id = submission["id"] if submission and submission["confirmed"] else None
    if order_id and not connection.execute("SELECT id FROM submissions WHERE id=? AND conversation_id=?", (order_id, conversation_id)).fetchone():
        return {"status": "error", "data": None, "error": "order_owner_mismatch"}
    from app.order_flow import missing_slots
    missing = missing_slots(conversation["order"]["slots"]) if conversation else []
    return save_record(connection, "tickets", conversation_id, idempotency_key, {
        "reason": reason, "summary": safe_history_text(summary), "status": "pending",
        "order_id": order_id, "priority": "high" if reason in {"severe_allergy", "allergen_requires_staff", "complaint"} else "normal",
        "missing_information": missing, "outside_hours": outside_hours,
        "is_mock": True, "is_demo": True, "source": "local_ticket",
        "note": "Ticket thử nghiệm mới được lưu; chưa có nhân viên nhận hoặc được thông báo." + (
            " Ngoài giờ mở cửa mô phỏng; yêu cầu vẫn pending, chờ xử lý." if outside_hours else ""),
    })
