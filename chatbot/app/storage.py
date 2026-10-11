"""Một lớp sqlite3 cho chatbot và dữ liệu demo; nâng schema không xóa dữ liệu."""

from copy import deepcopy
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from app.schemas import ToolResult

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def fingerprint(value: dict) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def safe_history_text(text: str) -> str:
    """Không lưu giá trị contact nhập thô; che email/chuỗi giống số điện thoại."""
    if re.match(r"\s*(?:tên|ten|sđt|sdt|điện thoại|dien thoai|địa chỉ|dia chi)\s*:", text, re.I):
        return "[Đã xử lý trường liên hệ thử nghiệm; không lưu đầu vào thô.]"
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[email đã che]", text)
    return re.sub(r"(?<!\w)\+?\d[\d .-]{7,}\d(?!\w)", "[chuỗi số đã che]", text)


def open_storage(path: str | Path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        path = Path(path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in {0, 1, 2}:
        connection.close()
        raise ValueError("Phiên bản database chatbot chưa được hỗ trợ.")
    if version == 1 and str(path) != ":memory:":
        backup_path = Path(str(path) + ".schema1-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + ".bak")
        with closing(sqlite3.connect(str(backup_path))) as backup:
            connection.backup(backup)
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
            revision INTEGER NOT NULL, payload TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        );
        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, draft_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE, payload_hash TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('waiting_consultation', 'demo_order')),
            payload TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE, payload_hash TEXT NOT NULL,
            payload TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        );
    """)
    if version < 2:
        try:
            schema = (PROJECT_ROOT / "data" / "schema_v2.sql").read_text(encoding="utf-8")
            connection.executescript("BEGIN IMMEDIATE;\n" + schema)
            migrate_legacy_orders(connection)
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Database cũ vi phạm khóa ngoại; giữ backup, chưa nâng schema.")
            connection.execute("PRAGMA user_version = 2")
            connection.commit()
        except Exception:
            connection.rollback()
            connection.close()
            raise
    return connection


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def migrate_legacy_orders(connection: sqlite3.Connection) -> None:
    """Đơn v1 giữ ID/snapshot cũ; không trừ tồn kho hồi tố cho đơn lịch sử."""
    rows = connection.execute("SELECT * FROM submissions WHERE kind='demo_order'").fetchall()
    for row in rows:
        record = json.loads(row["payload"])
        draft = connection.execute("SELECT id FROM drafts WHERE id=?", (row["draft_id"],)).fetchone()
        if draft is None:
            raise ValueError("Đơn cũ thiếu bản nháp; không tự suy bản nháp.")
        connection.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
            row["id"], row["conversation_id"], "DEMO-" + row["id"][:8].upper(), row["idempotency_key"],
            row["draft_id"], record["revision"], record["quote"]["total_vnd"], "DEMO_CONFIRMED", "unpaid", 1,
            record["data_mode"], row["created_at"],
        ))
        connection.execute("INSERT INTO order_items(order_id,product_id,variant_id,quantity,snapshot) VALUES(?,?,?,?,?)", (
            row["id"], record["slots"]["product_id"], record["quote"]["variant_id"], record["slots"]["quantity"],
            json.dumps({"legacy": True, "slots": record["slots"], "quote": record["quote"], "name": None}, ensure_ascii=False),
        ))


def record_messages(connection: sqlite3.Connection, conversation_id: str, message: str, answer: str) -> None:
    connection.executemany("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)", [
        (conversation_id, "user", safe_history_text(message), utc_now()),
        (conversation_id, "assistant", safe_history_text(answer), utc_now()),
    ])


def save_conversation(connection: sqlite3.Connection, conversation: dict) -> None:
    stored = deepcopy(conversation)
    draft = stored.get("order")
    if draft:
        owner = connection.execute("SELECT conversation_id FROM drafts WHERE id=?", (draft["id"],)).fetchone()
        if draft["conversation_id"] != stored["id"] or (owner and owner["conversation_id"] != stored["id"]):
            raise ValueError("Bản nháp không thuộc conversation này.")
    for message in stored["history"]:
        message["content"] = safe_history_text(message["content"])
    connection.execute(
        "INSERT INTO conversations VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
        (stored["id"], json.dumps(stored, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
    )
    draft = stored.get("order")
    if draft:
        connection.execute(
            "INSERT INTO drafts VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision, payload=excluded.payload",
            (draft["id"], stored["id"], draft["revision"], json.dumps(draft, ensure_ascii=False)),
        )


def load_conversation(connection: sqlite3.Connection, conversation_id: str) -> dict | None:
    row = connection.execute("SELECT payload FROM conversations WHERE id=?", (conversation_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def load_order_request(connection: sqlite3.Connection, record_id: str, conversation_id: str) -> dict | None:
    """Tra submission trong phạm vi owner; ID của khách khác cũng trả None."""
    row = connection.execute(
        "SELECT payload FROM submissions WHERE id=? AND conversation_id=?",
        (record_id, conversation_id),
    ).fetchone()
    if row is None:
        return None
    record = json.loads(row["payload"])
    order = connection.execute("SELECT code,payment_status,created_at,is_demo,source FROM orders WHERE id=? AND conversation_id=?", (record_id, conversation_id)).fetchone()
    if order:
        record.update(order_code=order["code"], payment_status=order["payment_status"], created_at=order["created_at"], is_demo=bool(order["is_demo"]), source=order["source"])
    return record


def save_record(connection: sqlite3.Connection, table: str, conversation_id: str, key: str, payload: dict) -> ToolResult:
    """UNIQUE + hash: cùng key/cùng payload trả cùng ID; khác payload báo lỗi."""
    if table not in {"submissions", "tickets"} or not key:
        return {"status": "error", "data": None, "error": "invalid_storage_request"}
    digest = fingerprint(payload)
    record_id = str(uuid4())
    record = {**deepcopy(payload), "id": record_id, "conversation_id": conversation_id}
    created = datetime.now(timezone.utc).isoformat()
    if table == "submissions":
        connection.execute(
            "INSERT INTO submissions VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(idempotency_key) DO NOTHING",
            (record_id, conversation_id, payload["draft_id"], key, digest, payload["kind"], json.dumps(record, ensure_ascii=False), created),
        )
    else:
        connection.execute(
            "INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(idempotency_key) DO NOTHING",
            (record_id, conversation_id, key, digest, json.dumps(record, ensure_ascii=False), created),
        )
    # table là whitelist ở trên; mọi giá trị khách đều truyền bằng placeholder.
    row = connection.execute(f"SELECT conversation_id, payload_hash, payload FROM {table} WHERE idempotency_key=?", (key,)).fetchone()
    if row["conversation_id"] != conversation_id or row["payload_hash"] != digest:
        return {"status": "error", "data": None, "error": "idempotency_conflict"}
    return {"status": "available", "data": json.loads(row["payload"]), "error": None}


def list_records(connection: sqlite3.Connection, table: str, conversation_id: str) -> list[dict]:
    if table not in {"drafts", "submissions", "tickets"}:
        raise ValueError("Tên bảng không được hỗ trợ.")
    rows = connection.execute(f"SELECT payload FROM {table} WHERE conversation_id=? ORDER BY rowid", (conversation_id,)).fetchall()
    return [json.loads(row["payload"]) for row in rows]
