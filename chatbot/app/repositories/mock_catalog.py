"""Đọc fixture JSON mock; chỉ module này biết đường dẫn và cách lưu mẫu."""

from copy import deepcopy
import json
from pathlib import Path

from app.schemas import (
    CatalogCapabilities, Product, ProductResult, SearchFilters, SearchResult,
    Variant, validate_product,
)
from app.text_utils import normalize_text


def matching_variants(product: Product, filters: SearchFilters) -> list[Variant]:
    """Giá, số người và size phải cùng thỏa trên một biến thể."""
    matches = []
    for variant in product["variants"]:
        if "max_price_vnd" in filters:
            price = variant["price_vnd"]
            if price is None:
                continue
            limit = filters["max_price_vnd"]
            if price > limit or (price == limit and not filters.get("price_inclusive", True)):
                continue
        if "servings" in filters:
            capacity = variant["servings"]
            if capacity is None or capacity < filters["servings"]:
                continue
        if "size" in filters:
            size = variant["size"]
            if size is None or normalize_text(size).replace(" ", "") != normalize_text(filters["size"]).replace(" ", ""):
                continue
        matches.append(variant)
    return matches


def matches_product(product: Product, filters: SearchFilters) -> bool:
    """So khớp các điều kiện cấp sản phẩm, không suy giá/tồn kho."""
    if "product_ids" in filters and product["id"] not in filters["product_ids"]:
        return False
    if "flavor" in filters and normalize_text(product["flavor"] or "") != normalize_text(filters["flavor"]):
        return False
    if filters.get("query"):
        haystack = normalize_text(" ".join([
            product["name"], *product["aliases"], product["category"],
            product["description"], product["flavor"] or "",
        ])).split()
        terms = normalize_text(filters["query"]).split()
        if not all(term in haystack for term in terms):
            return False
    return True


class MockCatalogRepository:
    def __init__(self, data_path: str | Path | None = None) -> None:
        """Nạp mẫu; lỗi file/schema được giữ để trả error khi truy vấn."""
        path = Path(data_path) if data_path is not None else Path(__file__).resolve().parents[2] / "data" / "mock_catalog.json"
        self._products: list[Product] = []
        self._error: str | None = None
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if document["data_mode"] != "mock" or document["is_mock"] is not True:
                raise ValueError("Fixture phải có nhãn mock.")
            products = document["products"]
            if not isinstance(products, list):
                raise ValueError("products phải là danh sách.")
            seen_ids = set()
            for product in products:
                validate_product(product)
                if product["source"] != "mock" or product["is_mock"] is not True or product["id"] in seen_ids:
                    raise ValueError("Sản phẩm phải có nhãn mock và ID không trùng.")
                seen_ids.add(product["id"])
            self._products = products
        except (OSError, ValueError, TypeError, KeyError):
            self._error = "invalid_mock_data"

    def search_products(self, filters: SearchFilters) -> SearchResult:
        if self._error:
            return {"status": "error", "data_mode": "mock", "products": [], "error": self._error}
        products = []
        for product in self._products:
            if not matches_product(product, filters):
                continue
            variants = matching_variants(product, filters)
            if variants:
                matched = deepcopy(product)
                matched["variants"] = deepcopy(variants)
                products.append(matched)
        return {
            "status": "success" if products else "no_results",
            "data_mode": "mock", "products": products, "error": None,
        }

    def get_product(self, product_id: str) -> ProductResult:
        if self._error:
            return {"status": "error", "data_mode": "mock", "product": None, "error": self._error}
        product = next((item for item in self._products if item["id"] == product_id), None)
        return {
            "status": "success" if product is not None else "no_results",
            "data_mode": "mock", "product": deepcopy(product), "error": None,
        }

    def get_capabilities(self) -> CatalogCapabilities:
        return {
            "data_mode": "mock", "is_mock": True, "configured": True,
            "policy_available": False, "can_accept_real_orders": False,
        }

    def get_order_metadata(self, product_id: str) -> dict:
        """Metadata demo riêng; không thêm trường hoặc sửa Product/Variant."""
        try:
            path = Path(__file__).resolve().parents[2] / "data/mock_order_metadata.json"
            document = json.loads(path.read_text(encoding="utf-8-sig"))
            if document.get("schema_version") != "1.0" or document.get("is_mock") is not True:
                raise ValueError("Metadata cần nhãn mock.")
            metadata = document["products"].get(product_id)
            return {"status": "success" if metadata is not None else "no_results", "metadata": deepcopy(metadata), "error": None}
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return {"status": "error", "metadata": None, "error": "invalid_order_metadata"}
