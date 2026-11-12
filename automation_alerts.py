"""Mô-đun Tự động thông báo Đa kênh & Cảnh báo SLA (Event-Driven Alert & SLA Escalation).

Hỗ trợ:
1. Phát thông báo tự động theo sự kiện (Event-Driven):
   - Khi có đơn đặt hàng mới (Website hoặc Chatbot qua `place_order`) -> Báo Quản lý (Telegram/Webhook) + Báo Khách hàng (Email/Log).
   - Khi cập nhật trạng thái đơn (`confirmed`, `delivering`, `completed`, `cancelled`) -> Báo Khách hàng & ghi nhận hoàn kho (nếu hủy).
   - Khi có phiếu yêu cầu tư vấn / hỗ trợ mới từ Chatbot -> Tự động đồng bộ và phát thông báo Lead mới.
   - Khi tồn kho sản phẩm giảm xuống ngưỡng cảnh báo -> Phát cảnh báo Tồn kho thấp.
2. Tự động quét và leo thang cảnh báo SLA (Time-Driven SLA Escalation):
   - Phát hiện các đơn ở trạng thái `pending_confirmation` vượt quá ngưỡng `sla_minutes` (mặc định 15 phút).
   - Tự động gắn cờ quá hạn SLA và phát thông báo nhắc Quản lý xử lý gấp (chống gửi trùng lặp).
3. Chế độ Kép (Real + Simulated Sandbox):
   - Nếu cấu hình Telegram Bot / Webhook / SMTP: gửi thật qua mạng và lưu trạng thái `sent`.
   - Nếu chạy local chưa cấu hình khóa ngoài: tự động chạy chế độ `simulated`, sinh đầy đủ nội dung tin nhắn/email chuẩn để hiển thị trực quan trên Trung tâm Thông báo của trang Admin (rất thuận tiện khi demo báo cáo đồ án).
"""
from __future__ import annotations

import json
import os
import smtplib
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


DEFAULT_SETTINGS: dict[str, Any] = {
    "sla_minutes": 15,
    "low_stock_threshold": 20,
    "enable_telegram": False,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "enable_webhook": False,
    "webhook_url": "",
    "enable_email": False,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_password": "",
    "notify_on_new_order": True,
    "notify_on_status_change": True,
    "notify_on_sla_breach": True,
    "notify_on_low_stock": True,
    "notify_on_chatbot_lead": True,
}

STATUS_LABELS_VI = {
    "pending_confirmation": "Chờ xác nhận",
    "confirmed": "Đã xác nhận (Đang chuẩn bị bánh)",
    "delivering": "Đang giao hàng",
    "completed": "Hoàn tất giao hàng",
    "cancelled": "Đã hủy (Đã hoàn tồn kho)",
}

SLOT_LABELS_VI = {
    "morning": "Sáng (08:00 – 12:00)",
    "afternoon": "Chiều (12:00 – 18:00)",
    "evening": "Tối (17:00 – 20:00)",
}


def format_vnd(amount: int | float | None) -> str:
    if amount is None:
        return "Chờ xác nhận"
    return f"{int(amount):,} ₫".replace(",", ".")


def ensure_automation_schema(db) -> None:
    """Khởi tạo bảng lưu cấu hình và nhật ký sự kiện tự động (an toàn với transaction/savepoint)."""
    has_events = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='automation_events'"
    ).fetchone()
    if not has_events:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS automation_settings (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS automation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dedupe_key TEXT UNIQUE,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'info',
                reference_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                recipient TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                delivery_status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_automation_events_created ON automation_events(created_at DESC, id DESC)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_automation_events_ref ON automation_events(reference_id, event_type)"
        )
    row = db.execute(
        "SELECT payload FROM automation_settings WHERE id = 'default'"
    ).fetchone()
    if not row:
        env_defaults = dict(DEFAULT_SETTINGS)
        if os.environ.get("SWEET_TELEGRAM_BOT_TOKEN") and os.environ.get("SWEET_TELEGRAM_CHAT_ID"):
            env_defaults["enable_telegram"] = True
            env_defaults["telegram_bot_token"] = os.environ["SWEET_TELEGRAM_BOT_TOKEN"].strip()
            env_defaults["telegram_chat_id"] = os.environ["SWEET_TELEGRAM_CHAT_ID"].strip()
        if os.environ.get("SWEET_WEBHOOK_URL"):
            env_defaults["enable_webhook"] = True
            env_defaults["webhook_url"] = os.environ["SWEET_WEBHOOK_URL"].strip()
        db.execute(
            "INSERT OR IGNORE INTO automation_settings(id, payload, updated_at) VALUES ('default', ?, ?)",
            (json.dumps(env_defaults, ensure_ascii=False), utc_now()),
        )


def get_settings(db) -> dict[str, Any]:
    ensure_automation_schema(db)
    row = db.execute(
        "SELECT payload FROM automation_settings WHERE id = 'default'"
    ).fetchone()
    merged = dict(DEFAULT_SETTINGS)
    if row:
        try:
            saved = json.loads(row["payload"])
            if isinstance(saved, dict):
                merged.update(saved)
        except Exception:
            pass
    return merged


def save_settings(db, updates: dict[str, Any]) -> dict[str, Any]:
    current = get_settings(db)
    for k in DEFAULT_SETTINGS:
        if k in updates and updates[k] is not None:
            current[k] = updates[k]
    current["sla_minutes"] = max(1, min(1440, int(current.get("sla_minutes") or 15)))
    current["low_stock_threshold"] = max(1, min(500, int(current.get("low_stock_threshold") or 20)))
    db.execute(
        "INSERT OR REPLACE INTO automation_settings(id, payload, updated_at) VALUES ('default', ?, ?)",
        (json.dumps(current, ensure_ascii=False), utc_now()),
    )
    return current


def _send_telegram(bot_token: str, chat_id: str, text: str) -> tuple[str, str]:
    """Gửi tin nhắn qua Telegram Bot API (nếu được cấu hình)."""
    if not bot_token or not chat_id:
        return "simulated", "Chế độ mô phỏng Local (chưa điền Telegram Token/Chat ID)"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            if 200 <= resp.status < 300:
                return "sent", f"Telegram ({chat_id})"
            return "failed", f"Telegram HTTP {resp.status}"
    except Exception:
        return "simulated", f"Mô phỏng Telegram ({chat_id} - ngoại tuyến)"


def _send_webhook(webhook_url: str, payload: dict[str, Any]) -> tuple[str, str]:
    """Gửi sự kiện JSON tới Discord / Slack / Custom Webhook."""
    if not webhook_url:
        return "simulated", "Chế độ mô phỏng Local (chưa điền Webhook URL)"
    body = json.dumps(
        {"content": f"**{payload['title']}**\n{payload['message']}", "event": payload},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            if 200 <= resp.status < 300:
                return "sent", "Webhook Endpoint"
            return "failed", f"Webhook HTTP {resp.status}"
    except Exception:
        return "simulated", "Mô phỏng Webhook (ngoại tuyến)"


def _send_email_smtp(settings: dict[str, Any], to_email: str, subject: str, body: str) -> tuple[str, str]:
    """Gửi email thông báo cho khách hàng (hoặc mô phỏng nếu chưa cấu hình SMTP)."""
    if not to_email:
        return "simulated", "Khách không để lại email (Lưu bản ghi đối soát)"
    if not settings.get("enable_email") or not settings.get("smtp_user") or not settings.get("smtp_password"):
        return "simulated", f"Hộp thư mô phỏng → {to_email}"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings["smtp_user"]
    msg["To"] = to_email
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.get("smtp_host", "smtp.gmail.com"), int(settings.get("smtp_port", 587)), timeout=4) as server:
            server.starttls()
            server.login(settings["smtp_user"], settings["smtp_password"])
            server.send_message(msg)
        return "sent", to_email
    except Exception:
        return "simulated", f"Mô phỏng Email → {to_email} (ngoại tuyến)"


def record_event(
    db,
    *,
    event_type: str,
    severity: str,
    reference_id: str,
    channel: str,
    recipient: str,
    title: str,
    message: str,
    delivery_status: str = "simulated",
    dedupe_key: str | None = None,
) -> dict[str, Any] | None:
    """Lưu sự kiện vào bảng automation_events (chống trùng theo dedupe_key, an toàn đa luồng)."""
    ensure_automation_schema(db)
    now = utc_now()
    cur = db.execute(
        """
        INSERT OR IGNORE INTO automation_events(
            dedupe_key, event_type, severity, reference_id,
            channel, recipient, title, message, delivery_status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dedupe_key,
            event_type,
            severity,
            reference_id,
            channel,
            recipient,
            title,
            message,
            delivery_status,
            now,
        ),
    )
    if cur.rowcount == 0:
        return None
    row = db.execute(
        "SELECT * FROM automation_events WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return dict(row) if row else None


def dispatch_new_order_alerts(
    db,
    *,
    order_id: str,
    customer_name: str,
    phone: str,
    email: str | None,
    address_text: str,
    delivery_date: str | None,
    delivery_slot: str | None,
    cake_message: str,
    note: str,
    subtotal: int,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Phát chuỗi thông báo tự động ngay khi đơn hàng mới được tạo (từ Website hoặc Chatbot)."""
    settings = get_settings(db)
    created_events: list[dict[str, Any]] = []
    if not settings.get("notify_on_new_order", True):
        return created_events

    items_lines = "\n".join(
        f"  • {it['product_name']} × {it['quantity']} ({format_vnd(it['unit_price'] * it['quantity'])})"
        for it in items
    )
    slot_str = SLOT_LABELS_VI.get(delivery_slot or "", "Chờ cửa hàng xác nhận")
    date_str = str(delivery_date) if delivery_date else "Chưa chọn ngày"
    clean_addr = address_text.strip(" ,") if address_text else "Theo vị trí ghim trên bản đồ"

    manager_title = f"[ĐƠN MỚI] {order_id} · {customer_name} ({format_vnd(subtotal)})"
    manager_msg = (
        f"🎂 ĐƠN ĐẶT BÁNH MỚI TẠI SWEET BAKERY\n"
        f"• Mã đơn: {order_id}\n"
        f"• Khách hàng: {customer_name} · SĐT: {phone}\n"
        f"• Địa chỉ giao: {clean_addr}\n"
        f"• Lịch giao mong muốn: {date_str} | {slot_str}\n"
        f"• Lời chúc trên bánh: {cake_message or 'Không có'}\n"
        f"• Ghi chú: {note or 'Không có'}\n"
        f"• Danh sách món:\n{items_lines}\n"
        f"• Tạm tính: {format_vnd(subtotal)} (COD - Đã tự động giữ tồn kho)\n"
        f"👉 SLA: Vui lòng gọi xác nhận khách trong vòng {settings['sla_minutes']} phút."
    )

    channel = "telegram" if settings.get("enable_telegram") else ("webhook" if settings.get("enable_webhook") else "admin_alert")
    if settings.get("enable_telegram"):
        status_code, recipient = _send_telegram(
            settings.get("telegram_bot_token", ""),
            settings.get("telegram_chat_id", ""),
            f"{manager_title}\n\n{manager_msg}",
        )
    elif settings.get("enable_webhook"):
        status_code, recipient = _send_webhook(
            settings.get("webhook_url", ""),
            {"title": manager_title, "message": manager_msg, "orderId": order_id},
        )
    else:
        status_code, recipient = "simulated", "Quản lý Cửa hàng (Telegram / Trung tâm Admin)"

    ev1 = record_event(
        db,
        event_type="order_created",
        severity="high",
        reference_id=order_id,
        channel=channel,
        recipient=recipient,
        title=manager_title,
        message=manager_msg,
        delivery_status=status_code,
        dedupe_key=f"order_created:manager:{order_id}",
    )
    if ev1:
        created_events.append(ev1)

    cust_title = f"Sweet Bakery — Đã tiếp nhận yêu cầu đặt bánh #{order_id}"
    cust_msg = (
        f"Xin chào {customer_name},\n\n"
        f"Cảm ơn bạn đã đặt bánh tại Sweet Bakery! Hệ thống đã tự động ghi nhận đơn hàng {order_id} và giữ sản phẩm cho bạn:\n"
        f"{items_lines}\n\n"
        f"• Tạm tính tiền bánh: {format_vnd(subtotal)} (Thanh toán khi nhận hàng - COD)\n"
        f"• Thời gian nhận mong muốn: {date_str} ({slot_str})\n"
        f"• Địa chỉ nhận: {clean_addr}\n"
        f"• Lời chúc viết trên bánh: {cake_message or 'Không ghi'}\n\n"
        f"Nhân viên Sweet Bakery sẽ liên hệ qua số {phone} trong vòng {settings['sla_minutes']} phút để xác nhận phí giao hàng và chốt giờ giao chính xác.\n"
        f"Trân trọng,\nSweet Bakery — Baked With Love"
    )
    mail_status, mail_recipient = _send_email_smtp(settings, email or "", cust_title, cust_msg)
    ev2 = record_event(
        db,
        event_type="order_created",
        severity="info",
        reference_id=order_id,
        channel="email",
        recipient=mail_recipient,
        title=cust_title,
        message=cust_msg,
        delivery_status=mail_status,
        dedupe_key=f"order_created:customer:{order_id}",
    )
    if ev2:
        created_events.append(ev2)

    if settings.get("notify_on_low_stock", True):
        threshold = int(settings.get("low_stock_threshold", 20))
        for it in items:
            row = db.execute(
                "SELECT stock_quantity FROM product_variants WHERE id = ?",
                (it.get("variant_id") or f"{it['product_id']}-std",),
            ).fetchone()
            if row and row["stock_quantity"] is not None and int(row["stock_quantity"]) <= threshold:
                stock_left = int(row["stock_quantity"])
                low_title = f"[CẢNH BÁO TỒN KHO] {it['product_name']} chỉ còn {stock_left} sản phẩm"
                low_msg = (
                    f"📦 Hệ thống phát hiện sản phẩm {it['product_name']} ({it['product_id']}) "
                    f"vừa giảm xuống còn {stock_left} chiếc (ngưỡng cảnh báo: ≤ {threshold} chiếc) "
                    f"sau đơn hàng {order_id}. Bếp bánh cần chuẩn bị mẻ mới hoặc cập nhật tồn kho."
                )
                ev_stock = record_event(
                    db,
                    event_type="low_stock_alert",
                    severity="warning",
                    reference_id=it["product_id"],
                    channel="inventory_monitor",
                    recipient="Bếp bánh & Quản lý kho",
                    title=low_title,
                    message=low_msg,
                    delivery_status="simulated",
                    dedupe_key=f"low_stock:{it['product_id']}:{stock_left}",
                )
                if ev_stock:
                    created_events.append(ev_stock)

    return created_events


def dispatch_status_change_alert(
    db,
    *,
    order_id: str,
    old_status: str,
    new_status: str,
    customer_name: str,
    phone: str,
    email: str | None,
    subtotal: int,
) -> list[dict[str, Any]]:
    """Phát thông báo tự động khi Quản lý hoặc Khách hàng cập nhật trạng thái đơn hàng."""
    settings = get_settings(db)
    created: list[dict[str, Any]] = []
    if not settings.get("notify_on_status_change", True):
        return created

    new_label = STATUS_LABELS_VI.get(new_status, new_status)
    old_label = STATUS_LABELS_VI.get(old_status, old_status)

    if new_status == "confirmed":
        title = f"[ĐÃ XÁC NHẬN] Đơn {order_id} đã được duyệt & chuyển xuống bếp bánh"
        body = (
            f"Xin chào {customer_name},\n"
            f"Đơn hàng {order_id} ({format_vnd(subtotal)}) của bạn tại Sweet Bakery đã được XÁC NHẬN. "
            f"Thợ làm bánh đang chuẩn bị bánh tươi và ghi lời chúc theo yêu cầu của bạn."
        )
        sev = "info"
    elif new_status == "delivering":
        title = f"[ĐANG GIAO] Đơn {order_id} đang trên đường giao đến bạn"
        body = (
            f"Xin chào {customer_name},\n"
            f"Đơn hàng {order_id} ({format_vnd(subtotal)}) đã xuất phát từ cửa hàng Sweet Bakery "
            f"và đang trên đường giao đến địa chỉ của bạn. Vui lòng giữ liên lạc qua số {phone} nhé!"
        )
        sev = "info"
    elif new_status == "completed":
        title = f"[HOÀN TẤT] Đơn {order_id} đã giao thành công & đối soát COD"
        body = (
            f"Xin chào {customer_name},\n"
            f"Đơn hàng {order_id} ({format_vnd(subtotal)}) đã được giao hoàn tất. "
            f"Cảm ơn bạn đã tin chọn Sweet Bakery và chúc bạn có những khoảnh khắc ngọt ngào!"
        )
        sev = "info"
    elif new_status == "cancelled":
        title = f"[ĐÃ HỦY & HOÀN KHO] Đơn {order_id} đã hủy tự động hoàn trả tồn kho"
        body = (
            f"Thông báo hệ thống: Đơn hàng {order_id} của khách {customer_name} ({phone}) "
            f"đã chuyển từ '{old_label}' sang '{new_label}'. "
            f"Hệ thống đã tự động cộng trả lại toàn bộ số lượng sản phẩm vào bảng tồn kho."
        )
        sev = "warning"
    else:
        title = f"[CẬP NHẬT] Đơn {order_id}: {old_label} → {new_label}"
        body = f"Đơn hàng {order_id} đã chuyển trạng thái sang {new_label}."
        sev = "info"

    mail_status, recipient = _send_email_smtp(settings, email or "", title, body)
    if settings.get("enable_telegram"):
        tg_status, tg_rec = _send_telegram(
            settings.get("telegram_bot_token", ""),
            settings.get("telegram_chat_id", ""),
            f"{title}\n{body}",
        )
        mail_status = tg_status
        recipient = f"{recipient} | {tg_rec}"

    ev = record_event(
        db,
        event_type="order_status_changed",
        severity=sev,
        reference_id=order_id,
        channel="email_and_log",
        recipient=recipient or f"Khách hàng ({phone})",
        title=title,
        message=body,
        delivery_status=mail_status,
        dedupe_key=f"status_change:{order_id}:{new_status}",
    )
    if ev:
        created.append(ev)
    return created


def _parse_iso_utc(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        cleaned = ts.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def scan_and_escalate_sla(db) -> dict[str, Any]:
    """Quét tự động các đơn Chờ xác nhận quá hạn SLA và phiếu tư vấn / hỗ trợ Chatbot mới."""
    ensure_automation_schema(db)
    settings = get_settings(db)
    sla_minutes = int(settings.get("sla_minutes", 15))
    now_utc = datetime.now(timezone.utc)

    overdue_orders: list[dict[str, Any]] = []
    new_sla_alerts: list[dict[str, Any]] = []
    new_chatbot_alerts: list[dict[str, Any]] = []

    rows = db.execute(
        "SELECT id, customer_name, phone, subtotal, created_at, payload FROM web_orders WHERE status = 'pending_confirmation' ORDER BY created_at ASC"
    ).fetchall()

    for r in rows:
        created_dt = _parse_iso_utc(r["created_at"])
        if not created_dt:
            continue
        elapsed_min = max(0, int((now_utc - created_dt).total_seconds() // 60))
        if elapsed_min >= sla_minutes:
            overdue_info = {
                "orderId": r["id"],
                "customerName": r["customer_name"],
                "phone": r["phone"],
                "subtotal": r["subtotal"],
                "createdAt": r["created_at"],
                "elapsedMinutes": elapsed_min,
                "slaMinutes": sla_minutes,
            }
            overdue_orders.append(overdue_info)

            if settings.get("notify_on_sla_breach", True):
                dedupe = f"sla_breach:{r['id']}"
                title = f"[CẢNH BÁO SLA] Đơn {r['id']} đã chờ {elapsed_min} phút chưa xác nhận!"
                msg = (
                    f"⚠️ VI PHẠM CAM KẾT THỜI GIAN PHẢN HỒI (SLA > {sla_minutes} phút)\n"
                    f"• Mã đơn: {r['id']}\n"
                    f"• Khách hàng: {r['customer_name']} · SĐT: {r['phone']}\n"
                    f"• Giá trị đơn: {format_vnd(r['subtotal'])}\n"
                    f"• Đã chờ: {elapsed_min} phút kể từ lúc đặt ({r['created_at']}).\n"
                    f"👉 Hành động khuyến nghị: Gọi ngay cho khách để xác nhận khung giờ giao bánh hoặc giải phóng tồn kho."
                )
                channel = "telegram" if settings.get("enable_telegram") else "sla_monitor"
                status_code = "simulated"
                recipient = "Quản lý Ca trực & CSKH"
                if settings.get("enable_telegram"):
                    status_code, recipient = _send_telegram(
                        settings.get("telegram_bot_token", ""),
                        settings.get("telegram_chat_id", ""),
                        f"{title}\n\n{msg}",
                    )
                ev = record_event(
                    db,
                    event_type="sla_breach_warning",
                    severity="critical",
                    reference_id=r["id"],
                    channel=channel,
                    recipient=recipient,
                    title=title,
                    message=msg,
                    delivery_status=status_code,
                    dedupe_key=dedupe,
                )
                if ev:
                    new_sla_alerts.append(ev)

    if settings.get("notify_on_chatbot_lead", True):
        try:
            sub_rows = db.execute(
                "SELECT id, payload, created_at FROM submissions ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            for sr in sub_rows:
                try:
                    p = json.loads(sr["payload"])
                except Exception:
                    continue
                ref_code = p.get("order_code") or p.get("id") or sr["id"]
                dedupe = f"chatbot_lead:{ref_code}"
                exists = db.execute(
                    "SELECT id FROM automation_events WHERE dedupe_key = ?", (dedupe,)
                ).fetchone()
                if exists:
                    continue
                form = p.get("checkout_form") or {}
                slots = p.get("slots") or {}
                cname = form.get("fullName") or slots.get("name") or "Khách tư vấn Chatbot"
                cphone = form.get("phone") or slots.get("phone") or "Chưa cung cấp"
                items = (p.get("checkout_summary") or {}).get("items") or p.get("items") or []
                items_str = ", ".join(
                    f"{i.get('name') or i.get('product_id')} ×{i.get('quantity', 1)}"
                    for i in items
                ) or "Đang cần tư vấn chọn bánh"

                title = f"[LEAD CHATBOT MỚI] {ref_code} · {cname} ({cphone})"
                msg = (
                    f"💬 KHÁCH HÀNG GỬI YÊU CẦU TƯ VẤN QUA CHATBOT\n"
                    f"• Mã phiếu: {ref_code}\n"
                    f"• Khách hàng: {cname} · SĐT: {cphone}\n"
                    f"• Sản phẩm quan tâm: {items_str}\n"
                    f"• Ngày nhận mong muốn: {form.get('deliveryDate') or 'Chưa chọn'}\n"
                    f"• Lời chúc trên bánh: {form.get('cakeMessage') or '—'}\n"
                    f"👉 Lưu ý: Phiếu tư vấn chưa trừ tồn kho. Hãy liên hệ khách để chốt mẫu bánh."
                )
                ev_lead = record_event(
                    db,
                    event_type="chatbot_lead_created",
                    severity="high",
                    reference_id=str(ref_code),
                    channel="chatbot_webhook",
                    recipient="Tư vấn viên & Quản lý",
                    title=title,
                    message=msg,
                    delivery_status="simulated",
                    dedupe_key=dedupe,
                )
                if ev_lead:
                    new_chatbot_alerts.append(ev_lead)
        except Exception:
            pass

        try:
            ticket_rows = db.execute(
                "SELECT id, payload, created_at FROM tickets ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            for tr in ticket_rows:
                try:
                    tp = json.loads(tr["payload"])
                except Exception:
                    continue
                ref_code = tr["id"]
                dedupe = f"chatbot_ticket:{ref_code}"
                exists = db.execute(
                    "SELECT id FROM automation_events WHERE dedupe_key = ?", (dedupe,)
                ).fetchone()
                if exists:
                    continue
                reason = tp.get("reason") or "customer_requested"
                summary = tp.get("summary") or "Khách hàng yêu cầu nhân viên hỗ trợ."
                priority = tp.get("priority") or "normal"
                title = f"[PHIẾU HỖ TRỢ CHATBOT] {ref_code} · Ưu tiên: {'Cao' if priority == 'high' else 'Thường'}"
                msg = (
                    f"🛎️ KHÁCH HÀNG YÊU CẦU HỖ TRỢ TRỰC TIẾP TỪ CHATBOT\n"
                    f"• Mã phiếu: {ref_code}\n"
                    f"• Lý do chuyển tiếp: {reason}\n"
                    f"• Tóm tắt nội dung: {summary}\n"
                    f"• Đơn hàng liên quan: {tp.get('order_id') or 'Chưa gắn đơn'}\n"
                    f"👉 Hãy kiểm tra mục Tư vấn & Hỗ trợ để phản hồi khách hàng."
                )
                ev_ticket = record_event(
                    db,
                    event_type="chatbot_lead_created",
                    severity="high" if priority == "high" else "info",
                    reference_id=str(ref_code),
                    channel="chatbot_webhook",
                    recipient="Tư vấn viên & CSKH",
                    title=title,
                    message=msg,
                    delivery_status="simulated",
                    dedupe_key=dedupe,
                )
                if ev_ticket:
                    new_chatbot_alerts.append(ev_ticket)
        except Exception:
            pass

    return {
        "slaMinutes": sla_minutes,
        "overdueCount": len(overdue_orders),
        "overdueOrders": overdue_orders,
        "newSlaAlerts": len(new_sla_alerts),
        "newChatbotAlerts": len(new_chatbot_alerts),
    }


def list_events(db, limit: int = 100) -> list[dict[str, Any]]:
    ensure_automation_schema(db)
    rows = db.execute(
        "SELECT * FROM automation_events ORDER BY id DESC LIMIT ?",
        (max(1, min(500, limit)),),
    ).fetchall()
    return [dict(r) for r in rows]
