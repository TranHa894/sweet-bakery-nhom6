"""Đọc fixture JSON mock; chỉ module này biết đường dẫn và cách lưu mẫu."""

from copy import deepcopy
import json
from pathlib import Path
import re
import unicodedata

from app.schemas import (
    CatalogCapabilities, Product, ProductResult, SearchFilters, SearchResult,
    Variant, validate_product,
)
from app.text_utils import normalize_text


# Từ vựng hương vị chỉ chuẩn hóa tên gọi tương đương, không suy thành phần.
# Ưu tiên cụm dài: "chanh leo" khác "chanh"; "Thái xanh" khác "trà xanh".
_FLAVOR_ALIASES = {
    "socola": ("socola", "sô cô la", "sôcôla", "chocolate", "choco"),
    "vani": ("vani", "va ni", "vanilla"),
    "trà xanh": ("trà xanh", "matcha"),
    "dâu": ("dâu", "dâu tây", "strawberry", "strawberries"),
    "chanh leo": ("chanh leo", "chanh dây", "passion fruit", "passionfruit"),
    "chanh": ("chanh", "lemon"),
    "vải": ("vải", "lychee", "litchi"),
    "hoa hồng": ("hoa hồng", "rose"),
    "quả mọng": ("quả mọng", "berry", "berries"),
    "việt quất": ("việt quất", "blueberry", "blueberries"),
    "đào": ("đào", "peach"),
    "cà phê": ("cà phê", "cafe", "coffee"),
    "trà sữa": ("trà sữa", "milk tea"),
    "sữa": ("sữa", "milk"),
    "muối": ("muối", "salt", "salted"),
    "Thái xanh": ("Thái xanh",),
    "tiramisu": ("tiramisu",),
    "xoài": ("xoài", "mango"),
    "dừa": ("dừa", "coconut"),
    "cam": ("cam", "orange"),
    "chuối": ("chuối", "banana"),
    "nho": ("nho", "grape"),
    "caramel": ("caramel",),
    "cacao": ("cacao", "ca cao", "cocoa"),
    "hạnh nhân": ("hạnh nhân", "almond"),
    "lúa mì": ("lúa mì", "wheat"),
    "hương thảo": ("hương thảo", "rosemary"),
    "ngũ cốc": ("ngũ cốc",),
    "mật ong": ("mật ong", "honey"),
}
_FLAVOR_PATTERNS = [
    (canonical, re.compile(r"(?<!\w)" + re.escape(normalize_text(alias)) + r"(?!\w)"))
    for canonical, aliases in _FLAVOR_ALIASES.items() for alias in aliases
]
# Tên nguồn giữ dấu: "nhỏ" không là "nho", "dầu" không là "dâu".
_NAME_FLAVOR_PATTERNS = [
    (canonical, re.compile(r"(?<!\w)" + re.escape(unicodedata.normalize("NFC", alias.casefold())) + r"(?!\w)"))
    for canonical, aliases in _FLAVOR_ALIASES.items() for alias in aliases
]


def _flavor_matches(normalized: str, patterns=_FLAVOR_PATTERNS) -> list[tuple[int, int, str]]:
    """Chọn các cụm không chồng lấn, không khớp một phần bên trong từ."""
    candidates = [
        (match.start(), match.end(), canonical)
        for canonical, pattern in patterns
        for match in pattern.finditer(normalized)
    ]
    matches = []
    for start, end, canonical in sorted(candidates, key=lambda item: (item[0] - item[1], item[0])):
        if not any(start < old_end and end > old_start for old_start, old_end, _ in matches):
            matches.append((start, end, canonical))
    return sorted(matches)


def flavors_from_name(name: str) -> str | None:
    """Chỉ lấy hương vị được viết rõ trong tên; tên thiết kế không là vị."""
    normalized = " ".join(unicodedata.normalize("NFC", name.casefold()).split())
    flavors = [canonical for _, _, canonical in _flavor_matches(normalized, _NAME_FLAVOR_PATTERNS)]
    return "; ".join(dict.fromkeys(flavors)) or None


# Kiểu pha chế là đặc điểm riêng, không suy ra ngọt/đắng hoặc nguyên liệu.
_STYLE_ALIASES = {"đen": ("đen", "black"), "ủ lạnh": ("ủ lạnh", "cold brew", "coldbrew")}
_STYLE_PATTERNS = [
    (canonical, re.compile(r"(?<!\w)" + re.escape(normalize_text(alias)) + r"(?!\w)"))
    for canonical, aliases in _STYLE_ALIASES.items() for alias in aliases
]
_QUERY_FLAVOR_PATTERNS = [*_FLAVOR_PATTERNS, *_STYLE_PATTERNS]
_NAME_STYLE_PATTERNS = [
    (canonical, re.compile(r"(?<!\w)" + re.escape(unicodedata.normalize("NFC", alias.casefold())) + r"(?!\w)"))
    for canonical, aliases in _STYLE_ALIASES.items() for alias in aliases
]


def styles_from_name(name: str, product_type: str) -> list[str]:
    """Đặc điểm nêu rõ của đồ uống; màu/tên thiết kế bánh không là kiểu pha."""
    if product_type not in {"coffee", "tea"}:
        return []
    text = " ".join(unicodedata.normalize("NFC", name.casefold()).split())
    return list(dict.fromkeys(canonical for _, _, canonical in _flavor_matches(text, _NAME_STYLE_PATTERNS)))


def canonical_flavors(value: str | None) -> set[str]:
    """So alias và nhiều vị; giữ phần chưa biết để không coi nó là đáp ứng."""
    if not value:
        return set()
    normalized = normalize_text(value.replace("_", " "))
    matches = _flavor_matches(normalized, _QUERY_FLAVOR_PATTERNS)
    flavors = {canonical for _, _, canonical in matches}
    if "trà sữa" in flavors:
        flavors.add("sữa")
    remainder = list(normalized)
    for start, end, _ in matches:
        remainder[start:end] = " " * (end - start)
    unknown = re.sub(r"\b(?:huong vi|huong|vi|va)\b", " ", "".join(remainder))
    # Phần dư là nhãn chưa biết, không được âm thầm bỏ điều kiện khách nêu.
    for part in re.split(r"[,;+/&]", unknown):
        part = " ".join(part.split())
        if part:
            flavors.add(part)
    return flavors


def _matches_product_type(product: Product, requested: str) -> bool:
    """Loại chuẩn từ adapter; category cũ chỉ cung cấp thông tin nó đã có."""
    categories = {
        "cake": "cream_cake", "banh kem": "cream_cake", "sinh nhat": "cream_cake",
        "mini": "mini", "banh tart": "cake", "banh ngot": "cake",
        "banh mi thu cong": "cake", "banh an kieng": "cake",
        "drink": "drink", "do uong": "drink", "tea": "tea", "coffee": "coffee",
        "cream_cake": "cream_cake", "tra": "tea", "ca phe": "coffee",
    }
    actual = product.get("product_type") or categories.get(normalize_text(product["category"]))
    groups = {"cake": {"cake", "cream_cake", "mini"}, "drink": {"drink", "tea", "coffee"}}
    return actual in groups.get(requested, {requested})


def matching_variants(product: Product, filters: SearchFilters) -> list[Variant]:
    """Giá, số người và size phải cùng thỏa trên một biến thể."""
    matches = []
    for variant in product["variants"]:
        if "min_price_vnd" in filters:
            price = variant["price_vnd"]
            if price is None:
                continue
            lower = filters["min_price_vnd"]
            if price < lower or (price == lower and not filters.get("min_price_inclusive", True)):
                continue
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
    if product["id"] in filters.get("exclude_product_ids", []):
        return False
    if "product_ids" in filters and product["id"] not in filters["product_ids"]:
        return False
    if filters.get("product_type") and not _matches_product_type(product, filters["product_type"]):
        return False
    if filters.get("flavor"):
        known_taste = canonical_flavors(product["flavor"]) | canonical_flavors("; ".join(product.get("style_tags", [])))
        if not canonical_flavors(filters["flavor"]).issubset(known_taste):
            return False
    profile = product.get("advice_profile", {})
    for key in ("sweetness", "coffee_style"):
        if filters.get(key) and profile.get(key) != filters[key]:
            return False
    if filters.get("taste_family") and filters["taste_family"] not in profile.get("taste_families", []):
        return False
    if filters.get("query"):
        # Tên nhóm tiếng Việt thuộc catalog, không biến nhóm thành ID sản phẩm.
        type_terms = {
            "cake": "bánh", "cream_cake": "bánh kem",
            "mini": "bánh nhỏ bánh ngọt nhỏ bánh mini",
            "drink": "đồ uống", "tea": "trà đồ uống", "coffee": "cà phê đồ uống",
        }
        category_terms = type_terms.get(
            product.get("product_type") or normalize_text(product["category"]), "")
        haystack = normalize_text(" ".join([
            product["name"], *product["aliases"], product["category"], category_terms,
            product["description"], product["flavor"] or "",
            *sorted(canonical_flavors(product["flavor"])),
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
