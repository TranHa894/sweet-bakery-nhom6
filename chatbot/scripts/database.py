"""Lệnh quản lý database demo. Không chạy reset khi import hoặc trong test chat."""

import argparse
from contextlib import closing
from contextlib import nullcontext
import json
from pathlib import Path
import sqlite3

from app.config import DATABASE_PATH
from app.schemas import Product, validate_product
from app.storage import PROJECT_ROOT, open_storage, utc_now

SEED_PATH = PROJECT_ROOT / "data" / "local_demo_seed.json"


def seed_database(connection: sqlite3.Connection, seed_path: Path = SEED_PATH, *, manage_transaction: bool = True) -> dict:
    """INSERT ... DO NOTHING: chạy lại không đổi giá/stock đã sửa. Reset là lệnh riêng."""
    document = json.loads(seed_path.read_text(encoding="utf-8"))
    if document.get("is_demo") is not True or document.get("source") != "local_demo":
        raise ValueError("Chỉ seed dữ liệu có nhãn local_demo.")
    for product in document["products"]:
        validate_product({key: product[key] if key != "variants" else [
            {k: v[k] for k in ("id", "size", "price_vnd", "servings", "stock_status")} for v in product[key]
        ] for key in Product.__required_keys__})
        if product.get("is_demo") is not True or product.get("is_mock") is not True:
            raise ValueError("Sản phẩm seed phải là demo.")
    with connection if manage_transaction else nullcontext():
        connection.execute("INSERT INTO database_metadata VALUES('environment','local_demo') ON CONFLICT(key) DO NOTHING")
        connection.execute("INSERT INTO database_metadata VALUES('seed_version',?) ON CONFLICT(key) DO NOTHING", (document["seed_version"],))
        for product in document["products"]:
            payload = {key: value for key, value in product.items() if key not in {"variants", "topping_ids"}}
            connection.execute("INSERT INTO products VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", (
                product["id"], product["name"], int(product["active"]), json.dumps(payload, ensure_ascii=False), "local_demo", 1, utc_now(),
            ))
            for variant in product["variants"]:
                connection.execute("INSERT INTO product_variants VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", (
                    variant["id"], product["id"], variant["size"], variant["price_vnd"], variant["servings"], variant["stock_quantity"], variant["stock_status"],
                ))
        for topping in document["toppings"]:
            connection.execute("INSERT INTO toppings VALUES(?,?,?,?,1) ON CONFLICT(id) DO NOTHING", (
                topping["id"], topping["name"], topping["price_vnd"], json.dumps(topping["allergen"], ensure_ascii=False),
            ))
        for product in document["products"]:
            for topping_id in product["topping_ids"]:
                connection.execute("INSERT INTO product_toppings VALUES(?,?) ON CONFLICT DO NOTHING", (product["id"], topping_id))
        for policy in document["policies"]:
            if policy.get("is_mock") is not True:
                raise ValueError("Chính sách seed phải có nhãn mô phỏng.")
            connection.execute("INSERT INTO policies VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", (
                policy["id"], policy["title"], policy["content"], policy["version"], 1, "local_demo", utc_now(),
            ))
        settings = document["business_settings"]
        connection.execute("INSERT INTO business_settings VALUES(?,?,?,1) ON CONFLICT(id) DO NOTHING", (
            settings["id"], json.dumps(settings, ensure_ascii=False), settings["version"],
        ))
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Seed vi phạm khóa ngoại; đã rollback.")
    return check_database(connection)


def check_database(connection: sqlite3.Connection) -> dict:
    tables = ["products", "product_variants", "toppings", "product_toppings", "policies", "conversations", "messages", "drafts", "orders", "order_items", "tickets"]
    return {"schema_version": connection.execute("PRAGMA user_version").fetchone()[0],
            "foreign_keys_enabled": bool(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
            "foreign_key_errors": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
            "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "counts": {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in tables}}


def validate_reset_target(connection: sqlite3.Connection, database_path: str | Path, *, confirm: bool = False) -> Path:
    """Chỉ đọc để xác minh target; cũng dùng trước open_storage có migration."""
    path = Path(database_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    runtime = (PROJECT_ROOT / "runtime").resolve()
    if not confirm or not path.is_relative_to(runtime) or path.suffix not in {".sqlite3", ".db"}:
        raise ValueError("Reset cần --confirm và database demo nằm trong runtime của dự án.")
    opened_path = Path(connection.execute("PRAGMA database_list").fetchone()[2]).resolve()
    if opened_path != path or connection.in_transaction:
        raise ValueError("Đường dẫn reset phải đúng connection và không có transaction chưa kết thúc.")
    marker = connection.execute("SELECT value FROM database_metadata WHERE key='environment'").fetchone()
    if not marker or marker[0] != "local_demo":
        raise ValueError("Database chưa được xác minh local_demo; từ chối reset.")
    for table in ("products", "policies", "toppings", "orders"):
        if connection.execute(f"SELECT 1 FROM {table} WHERE is_demo<>1 LIMIT 1").fetchone():
            raise ValueError("Có dữ liệu không phải demo; từ chối reset.")
    for table in ("submissions", "tickets"):
        if any(json.loads(row[0]).get("is_mock") is not True for row in connection.execute(f"SELECT payload FROM {table}")):
            raise ValueError("Có bản ghi chưa xác minh mô phỏng; từ chối reset.")
    return path


def reset_demo(connection: sqlite3.Connection, database_path: str | Path, *, confirm: bool = False) -> dict:
    """Chỉ xóa row của DB demo trong runtime; backup trước, không xóa file tùy ý."""
    path = validate_reset_target(connection, database_path, confirm=confirm)
    backup_path = Path(str(path) + ".reset-" + utc_now().replace(":", "-") + ".bak")
    with closing(sqlite3.connect(str(backup_path))) as backup:
        connection.backup(backup)
    with connection:
        for table in ("order_items", "orders", "submissions", "tickets", "messages", "drafts", "conversations", "product_toppings", "product_variants", "products", "toppings", "policies", "business_settings", "database_metadata"):
            connection.execute(f"DELETE FROM {table}")
        result = seed_database(connection, manage_transaction=False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="SQLite LOCAL DEMO; reset xóa hội thoại/đơn demo sau backup.")
    parser.add_argument("command", choices=["init", "seed", "check", "reset"])
    parser.add_argument("--database", default=DATABASE_PATH)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "reset":
            # Không init/migrate một file tùy ý trước khi từ chối reset.
            path = Path(args.database)
            path = (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
            if not args.confirm or not path.is_relative_to((PROJECT_ROOT / "runtime").resolve()) or path.suffix not in {".sqlite3", ".db"} or not path.is_file():
                raise ValueError("Reset cần --confirm và file database demo có sẵn trong runtime.")
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as probe:
                validate_reset_target(probe, path, confirm=True)
        with closing(open_storage(args.database)) as connection:
            if args.command == "seed":
                result = seed_database(connection)
            elif args.command == "reset":
                result = reset_demo(connection, args.database, confirm=args.confirm)
            else:
                result = check_database(connection)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"Không thực hiện: {error}\n")


if __name__ == "__main__":
    main()
