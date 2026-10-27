"""Đọc danh mục mẫu của website nhóm; không ghi JSON/DB bên ngoài chatbot."""

from contextlib import closing
from copy import deepcopy
import json
import sqlite3
from pathlib import Path
import re
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from typing import Literal

from app.repositories.mock_catalog import flavors_from_name, styles_from_name, matching_variants, matches_product
from app.schemas import validate_product
from app.text_utils import normalize_text

MAX_CATALOG_BYTES = 2_000_000  # Giới hạn đọc file kỹ thuật, không là quy tắc bán hàng.


FLAVOR_PROFILE_KEY = "catalog_flavors:group_files:v1"


class FlavorProfile(BaseModel):
    """Metadata riêng trong SQLite chatbot; đối chiếu tên/nhóm để tránh dùng nhãn cũ."""
    model_config = ConfigDict(strict=True, extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    category: Literal["cake", "mini", "drink"]
    product_type: Literal["cream_cake", "mini", "tea", "coffee", "drink"]
    flavor: str | None = Field(max_length=300)
    style_tags: list[str] = Field(max_length=10)


def load_flavor_profiles(database_path: str | Path) -> dict[str, FlavorProfile]:
    """Chỉ đọc SQLite. Cache trong repository; không tạo DB hay ghi khi khách chat."""
    if str(database_path) == ":memory:":
        return {}
    from app.config import PROJECT_ROOT
    path = Path(database_path)
    path = (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
    if not path.is_file():
        return {}
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='database_metadata'").fetchone():
            return {}
        row = connection.execute("SELECT value FROM database_metadata WHERE key=?", (FLAVOR_PROFILE_KEY,)).fetchone()
    if row is None:
        return {}
    document = json.loads(row[0])
    if not isinstance(document, dict) or document.get("version") != 1 or document.get("source") != "group_files":
        raise ValueError("Phân loại hương vị sai phiên bản/nguồn.")
    profiles = TypeAdapter(dict[str, FlavorProfile]).validate_python(document["products"])
    if any(not re.fullmatch(r"SP\d{4}", identifier) for identifier in profiles):
        raise ValueError("ID phân loại hương vị không hợp lệ.")
    return profiles


class AdviceProfile(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    name: str
    category: Literal["cake", "mini", "drink"]
    sweetness: Literal["high", "medium", "low"] | None
    taste_families: list[Literal["fruit", "chocolate", "cream", "milk_tea", "fruit_tea", "matcha", "vanilla", "coffee_cream"]]
    coffee_style: Literal["strong", "creamy", "mild"] | None
    note: str = Field(max_length=300)
    flavor: str | None = None


@lru_cache(maxsize=1)
def load_advice_profiles(path: str, modified_ns: int):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("version") != 1 or document.get("source") != "group_files" or document.get("is_mock") is not True:
        raise ValueError("Sai nguồn metadata tư vấn.")
    return TypeAdapter(dict[str, AdviceProfile]).validate_python(document["products"])


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
    product_type = {"cake": "cream_cake", "mini": "mini", "drink": "drink"}[record.category]
    if record.category == "drink":
        normalized_name = normalize_text(name)
        if re.match(r"^tra(?:\s|$)", normalized_name):
            product_type = "tea"
        elif re.match(r"^(?:ca\s*phe|cafe)(?:\s|$)", normalized_name):
            product_type = "coffee"
    # Alias sinh từ tên nguồn, không chứa danh sách bánh/giá cố định trong NLU.
    aliases = [record.id, short_name]
    prefix, forms = (r"^bánh\s+kem\s+", ("bánh sinh nhật", "gato", "ga tô", "gateau"))
    if product_type == "coffee":
        prefix, forms = r"^(?:cà\s*phê|cafe)\s+", ("cf", "cafe", "coffee", "caphe")
    if product_type in {"cream_cake", "coffee"}:
        suffix = re.sub(prefix, "", name, flags=re.IGNORECASE)
        if suffix != name and suffix:
            aliases.extend(form + " " + suffix for form in forms)
    flavor = flavors_from_name(name)
    product = {
        "id": record.id, "name": name,
        "aliases": list(dict.fromkeys(aliases)),
        "category": record.category, "product_type": product_type,
        "description": "Sản phẩm trong danh mục mẫu của website nhóm; thông tin chi tiết chưa được cung cấp.",
        "flavor": flavor, "style_tags": styles_from_name(name, product_type),
        "variants": [{"id": record.id + ":listed", "size": None,
                      # Menu nhóm là mẫu: theo yêu cầu, luôn cho trạng thái có hàng.
                      # Không suy số lượng kho hoặc bật tạo đơn kinh doanh.
                      "price_vnd": record.price, "servings": None, "stock_status": "in_stock"}],
        "allergen": None, "customization": None, "min_lead_hours": None,
        "source": "group_files", "is_mock": True, "is_demo": True,
    }
    if flavor:
        product["flavor_source"] = "product_name"
    validate_product(product)
    return product


class GroupCatalogRepository:
    """Adapter chỉ đọc. Nạp lại file để cập nhật danh mục không cần sửa NLU."""

    def __init__(self, data_path: str | Path | None = None, database_path: str | Path | None = None):
        from app.config import DATABASE_PATH, GROUP_CATALOG_PATH, PROJECT_ROOT
        path = Path(data_path) if data_path is not None else GROUP_CATALOG_PATH
        self.data_path = (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
        self.database_path = DATABASE_PATH if database_path is None else database_path
        self._flavor_profiles = None

    def _read(self) -> dict:
        result = {"status": "unconfigured", "data_mode": "mock", "products": [], "error": None}
        try:
            if self.data_path.stat().st_size > MAX_CATALOG_BYTES:
                raise ValueError("Danh mục quá lớn.")
            raw = json.loads(self.data_path.read_text(encoding="utf-8-sig"))
            records = TypeAdapter(list[GroupProductRecord]).validate_python(raw)
            if len({record.id for record in records}) != len(records):
                raise ValueError("ID sản phẩm trùng.")
            if self._flavor_profiles is None:
                self._flavor_profiles = load_flavor_profiles(self.database_path)
            profile_path = Path(__file__).resolve().parents[2] / "data/recommendation_profiles.json"
            advice_profiles = load_advice_profiles(str(profile_path), profile_path.stat().st_mtime_ns)
            products = []
            for record in records:
                product = map_group_product(record)
                profile = self._flavor_profiles.get(record.id)
                # Đổi tên/nhóm hoặc tái sử dụng ID không mang nhầm vị đã lưu.
                if profile and profile.name == product["name"] and profile.category == record.category:
                    if profile.product_type != product["product_type"]:
                        raise ValueError("Nhóm sản phẩm trong phân loại không khớp nguồn.")
                    product.update(flavor=profile.flavor, style_tags=list(profile.style_tags))
                advice = advice_profiles.get(record.id)
                if advice and advice.name == record.name and advice.category == record.category:
                    product["advice_profile"] = advice.model_dump(exclude={"name", "category", "flavor"})
                    if advice.flavor is not None:
                        product["flavor"] = advice.flavor
                        product["flavor_source"] = "owner_menu"
                # Ảnh local trong website, không cho đường dẫn tùy ý hoặc URL bên ngoài.
                if re.fullmatch(r"images/[A-Za-z0-9_.-]+", record.image):
                    product["image_url"] = "/website/" + record.image
                validate_product(product)
                products.append(product)
            result.update(status="success" if products else "no_results", products=products)
        except FileNotFoundError:
            pass  # Thiếu nguồn khác với danh mục hợp lệ nhưng không có kết quả.
        except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
            result.update(status="error", error="group_catalog_invalid_or_unreadable")
        return result

    def search_products(self, filters) -> dict:
        result = self._read()
        if result["status"] not in {"success", "no_results"}:
            return result
        # Dị ứng/dịp vẫn chưa có dữ liệu; trạng thái hàng của menu mẫu luôn in_stock.
        if filters.get("exclude_allergens") or filters.get("occasion"):
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
                "disabled_order_fields": ["pickup_at", "fulfillment", "address"],
                "unsupported_search_filters": ["size", "servings", "occasion", "exclude_allergens"]}
