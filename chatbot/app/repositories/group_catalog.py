"""Đọc danh mục mẫu của website nhóm; không ghi JSON/DB bên ngoài chatbot."""

from copy import deepcopy
import json
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from typing import Literal

from app.repositories.mock_catalog import matching_variants, matches_product
from app.schemas import validate_product

MAX_CATALOG_BYTES = 2_000_000  # Giới hạn đọc file kỹ thuật, không là quy tắc bán hàng.


class GroupProductRecord(BaseModel):
    """Schema thực tế của static/products.json; giá chưa biết giữ None."""

    model_config = ConfigDict(strict=True, extra="forbid")
    id: str = Field(pattern=r"^SP\d{4}$")
    name: str = Field(min_length=1, max_length=200)
    price: int | None = Field(default=None, ge=0)
    category: Literal["cake", "mini", "drink"]
    image: str = Field(default="", max_length=1000)
    sourceImage: str = Field(default="", max_length=2000)


def map_group_product(record: GroupProductRecord) -> dict:
    """ID/tên/giá giữ từ nguồn. Biến thể listed chỉ biểu diễn giá niêm yết."""
    name = record.name.strip()
    if not name:
        raise ValueError("Tên sản phẩm trống.")
    short_name = re.sub(r"^bánh\s+(?:kem\s+)?", "", name, flags=re.IGNORECASE)
    product = {
        "id": record.id, "name": name,
        "aliases": list(dict.fromkeys([record.id, short_name])),
        "category": record.category,
        "description": "Sản phẩm trong danh mục mẫu của website nhóm; thông tin chi tiết chưa được cung cấp.",
        "flavor": None,
        "variants": [{"id": record.id + ":listed", "size": None,
                      "price_vnd": record.price, "servings": None, "stock_status": "unknown"}],
        "allergen": None, "customization": None, "min_lead_hours": None,
        "source": "group_files", "is_mock": True, "is_demo": True,
    }
    validate_product(product)
    return product


class GroupCatalogRepository:
    """Adapter chỉ đọc. Nạp lại file để cập nhật danh mục không cần sửa NLU."""

    def __init__(self, data_path: str | Path | None = None):
        from app.config import GROUP_CATALOG_PATH, PROJECT_ROOT
        path = Path(data_path) if data_path is not None else GROUP_CATALOG_PATH
        self.data_path = (path if path.is_absolute() else PROJECT_ROOT / path).resolve()

    def _read(self) -> dict:
        result = {"status": "unconfigured", "data_mode": "mock", "products": [], "error": None}
        try:
            if self.data_path.stat().st_size > MAX_CATALOG_BYTES:
                raise ValueError("Danh mục quá lớn.")
            raw = json.loads(self.data_path.read_text(encoding="utf-8-sig"))
            records = TypeAdapter(list[GroupProductRecord]).validate_python(raw)
            if len({record.id for record in records}) != len(records):
                raise ValueError("ID sản phẩm trùng.")
            products = [map_group_product(record) for record in records]
            result.update(status="success" if products else "no_results", products=products)
        except FileNotFoundError:
            pass  # Thiếu nguồn khác với danh mục hợp lệ nhưng không có kết quả.
        except (OSError, ValueError, TypeError):
            result.update(status="error", error="group_catalog_invalid_or_unreadable")
        return result

    def search_products(self, filters) -> dict:
        result = self._read()
        if result["status"] not in {"success", "no_results"}:
            return result
        # File nhóm chưa có dữ liệu dị ứng/dịp/tồn kho: không xác nhận đáp ứng.
        if filters.get("exclude_allergens") or filters.get("occasion") or filters.get("available_only"):
            return {**result, "status": "no_results", "products": []}
        matches = []
        for product in result["products"]:
            if not matches_product(product, filters):
                continue
            variants = matching_variants(product, filters)
            if variants:
                matched = deepcopy(product)
                matched["variants"] = variants
                matches.append(matched)
        matches.sort(key=lambda product: min(
            variant["price_vnd"] if variant["price_vnd"] is not None else 10**15
            for variant in product["variants"]))
        return {**result, "status": "success" if matches else "no_results", "products": matches}

    def get_product(self, product_id) -> dict:
        result = self._read()
        product = next((item for item in result["products"] if item["id"] == product_id), None)
        status = result["status"]
        if status in {"success", "no_results"}:
            status = "success" if product else "no_results"
        return {"status": status, "data_mode": "mock", "product": deepcopy(product), "error": result["error"]}

    def get_capabilities(self) -> dict:
        result = self._read()
        return {"data_mode": "mock", "catalog_source": "group_files", "is_mock": True,
                "configured": result["status"] in {"success", "no_results"},
                "policy_available": False, "can_accept_real_orders": False,
                "can_create_demo_orders": False,
                "optional_order_fields": ["size", "toppings", "cake_text"],
                "disabled_order_fields": ["pickup_at"],
                "unsupported_search_filters": ["size", "servings", "flavor", "occasion", "available_only", "exclude_allergens"]}
