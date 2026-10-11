"""Adapter catalog SQLite DEMO. SQL chỉ nằm ở adapter/lớp lưu trữ/tool."""

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

from app.repositories.mock_catalog import matching_variants, matches_product
from app.schemas import Product, validate_product
from app.storage import open_storage, fingerprint
from app.text_utils import normalize_text


class LocalCatalogRepository:
    def __init__(self, database_path: str | Path, connection: sqlite3.Connection | None = None):
        self.database_path = database_path
        self.connection = connection

    def using_connection(self, connection: sqlite3.Connection):
        """Transaction đặt đơn đọc cùng connection, không dùng snapshot cũ."""
        return LocalCatalogRepository(self.database_path, connection)

    @contextmanager
    def read_connection(self):
        if self.connection is not None:
            yield self.connection
        else:
            connection = open_storage(self.database_path)
            try:
                yield connection
            finally:
                connection.close()

    def get_capabilities(self):
        return {"data_mode": "local_demo", "is_mock": True, "configured": True,
                "policy_available": True, "can_accept_real_orders": False}

    def _read_product(self, connection, row):
        payload = json.loads(row["payload"])
        product = {key: payload[key] for key in Product.__required_keys__ if key != "variants"}
        product.update(id=row["id"], name=row["name"], active=bool(row["active"]), is_demo=True,
                       occasions=payload["occasions"], allergen_info=payload["allergen_info"],
                       storage=payload["storage"], shelf_life_hours=payload["shelf_life_hours"])
        # Trường cũ phục vụ API/bài học cũng lấy từ metadata allergen hiện tại,
        # tránh hai mô tả nguyên liệu khác nhau trong cùng response.
        info = product["allergen_info"]
        product["allergen"] = None if info["status"] == "unknown" else list(info["items"])
        product["variants"] = []
        for variant in connection.execute("SELECT * FROM product_variants WHERE product_id=? ORDER BY id", (row["id"],)):
            status = variant["stock_status"]
            if variant["stock_quantity"] == 0:
                status = "out_of_stock"
            product["variants"].append({key: variant[key] for key in ("id", "size", "price_vnd", "servings")} | {"stock_status": status})
        product["topping_options"] = [dict(t) for t in connection.execute(
            "SELECT t.id,t.name,t.price_vnd,t.allergen FROM toppings t JOIN product_toppings pt ON pt.topping_id=t.id WHERE pt.product_id=? ORDER BY t.id", (row["id"],))]
        for topping in product["topping_options"]:
            topping["allergen"] = json.loads(topping["allergen"])
        validate_product(product)
        return product

    def search_products(self, filters):
        try:
            with self.read_connection() as connection:
                products = []
                for row in connection.execute("SELECT * FROM products WHERE active=1 ORDER BY id"):
                    product = self._read_product(connection, row)
                    if not matches_product(product, filters):
                        continue
                    if filters.get("occasion") and normalize_text(filters["occasion"]) not in [normalize_text(x) for x in product["occasions"]]:
                        continue
                    # Dị ứng là ràng buộc bắt buộc. unknown/not_listed không được coi an toàn.
                    if filters.get("exclude_allergens"):
                        info = product["allergen_info"]
                        if info["status"] in {"unknown", "not_listed", "may_contain"}:
                            continue
                        excluded = {normalize_text(x) for x in filters["exclude_allergens"]}
                        if excluded.intersection(normalize_text(x) for x in info["items"]):
                            continue
                    variants = matching_variants(product, filters)
                    if filters.get("available_only"):
                        variants = [v for v in variants if v["stock_status"] == "in_stock"]
                    if variants:
                        product["variants"] = variants
                        products.append(product)
                products.sort(key=lambda p: min(v["price_vnd"] if v["price_vnd"] is not None else 10**15 for v in p["variants"]))
                return {"status": "success" if products else "no_results", "data_mode": "local_demo", "products": products, "error": None}
        except (sqlite3.Error, ValueError, KeyError, TypeError, OSError):
            return {"status": "error", "data_mode": "local_demo", "products": [], "error": "local_catalog_error"}

    def get_product(self, product_id):
        try:
            with self.read_connection() as connection:
                row = connection.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
                return {"status": "success" if row else "no_results", "data_mode": "local_demo",
                        "product": self._read_product(connection, row) if row else None, "error": None}
        except (sqlite3.Error, ValueError, KeyError, TypeError, OSError):
            return {"status": "error", "data_mode": "local_demo", "product": None, "error": "local_catalog_error"}

    def get_order_metadata(self, product_id):
        try:
            with self.read_connection() as connection:
                row = connection.execute("SELECT payload,active FROM products WHERE id=?", (product_id,)).fetchone()
                settings = connection.execute("SELECT payload,version FROM business_settings WHERE id='store'").fetchone()
                if row is None or settings is None:
                    return {"status": "no_results", "metadata": None, "error": None}
                payload, business = json.loads(row["payload"]), json.loads(settings["payload"])
                toppings = [dict(t) for t in connection.execute("SELECT t.* FROM toppings t JOIN product_toppings pt ON t.id=pt.topping_id WHERE pt.product_id=?", (product_id,))]
                stock = {r["id"]: r["stock_quantity"] for r in connection.execute("SELECT id,stock_quantity FROM product_variants WHERE product_id=?", (product_id,))}
                metadata = {"toppings": {t["name"]: t["price_vnd"] for t in toppings},
                            "stock_quantity": stock, "max_cake_text_length": payload["max_cake_text_length"],
                            "cake_text_price_vnd": payload["cake_text_price_vnd"], "delivery_fee_vnd": None,
                            "fulfillment_modes": business["fulfillment_modes"], "business": business,
                            "active": bool(row["active"]), "writing_supported": payload["writing_supported"],
                            "topping_allergens": {t["name"]: json.loads(t["allergen"]) for t in toppings}}
                return {"status": "success", "metadata": metadata, "error": None}
        except (sqlite3.Error, ValueError, KeyError, TypeError, OSError):
            return {"status": "error", "metadata": None, "error": "local_metadata_error"}

    def get_policy_documents(self):
        try:
            with self.read_connection() as connection:
                clauses = [{"id": row["id"], "title": row["title"], "content": row["content"], "version": row["version"], "is_mock": True}
                           for row in connection.execute("SELECT * FROM policies ORDER BY id")]
            return {"status": "success" if clauses else "no_results", "knowledge_mode": "local_demo", "is_mock": True,
                    "clauses": clauses, "corpus_sha256": fingerprint({"clauses": clauses}), "error": None}
        except (sqlite3.Error, ValueError, OSError):
            return {"status": "error", "knowledge_mode": "local_demo", "is_mock": True,
                    "clauses": [], "corpus_sha256": None, "error": "local_knowledge_error"}

    def get_business_settings(self):
        try:
            with self.read_connection() as connection:
                row = connection.execute("SELECT payload FROM business_settings WHERE id='store'").fetchone()
                return {"status": "success" if row else "no_results", "settings": json.loads(row[0]) if row else None, "error": None}
        except (sqlite3.Error, ValueError, OSError):
            return {"status": "error", "settings": None, "error": "local_business_settings_error"}
