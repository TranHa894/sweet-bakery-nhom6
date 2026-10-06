"""NLU theo quy tắc: nhiều intent, thực thể và trường hợp cần hỏi lại."""

import re
from copy import deepcopy

from app.repositories.catalog import CatalogRepository, safe_search_products
from app.schemas import Intent, LLMNLU, NLUResult, Product
from app.text_utils import normalize_text, phrase_spans

# Từ vựng hương vị phổ thông, không phải tên/ID sản phẩm hoặc danh sách đang bán.
# Nguồn empty vẫn có thể ghi nhận nhu cầu; hương vị của catalog được bổ sung bên dưới.
FLAVOR_WORDS = {
    "socola": ["socola", "so co la", "chocolate"],
    "dâu": ["dau", "strawberry"], "vani": ["vani", "vanilla"],
    "trà xanh": ["tra xanh", "matcha"], "phô mai": ["pho mai", "cheese"],
}
INTENT_PHRASES: dict[Intent, list[str]] = {
    "greeting": ["xin chao", "chao", "hello", "hi"],
    "price": ["gia", "bao nhieu tien", "bao gia"],
    "size": ["size", "kich thuoc", "co banh", "nguoi", "cm"],
    "flavor": ["vi", "huong vi"],
    "availability": ["con hang", "het hang", "co san", "ton kho", "con khong"],
    "recommendation": ["goi y", "tu van", "tim", "phu hop", "nen chon", "ngan sach"],
    "policy": ["chinh sach", "doi tra", "bao quan", "giao hang", "phi ship", "ship", "thanh toan",
               "cod", "chuyen khoan", "dat truoc", "tuy chinh", "viet chu", "trang tri",
               "phi van chuyen", "duoc doi", "doi y", "tra lai", "ngan mat", "ngan da", "dung trong bao lau"],
    "order_request": ["dat", "mua", "lay", "chot don"],
}
NUMBER = r"\d+(?:[.,]\d+)*"
MONEY_UNIT = r"trieu|tr|nghin|ngan|k|vnd|dong|d"


def find_product_mentions(text: str, products: list[Product]) -> list[tuple[int, int, str, str]]:
    """Lấy tên/alias/ID từ nguồn; ưu tiên cụm dài để tránh khớp tên con."""
    candidates = []
    for product in products:
        for phrase in [product["name"], *product["aliases"], product["id"]]:
            for start, end in phrase_spans(text, phrase):
                candidates.append((start, end, product["id"], text[start:end]))
    selected = []
    for item in sorted(candidates, key=lambda item: -(item[1] - item[0])):
        start, end, product_id, _ = item
        # Alias trùng chính xác giữa hai sản phẩm được giữ để hỏi lại.
        if any(a <= start and end <= b and (a, b) != (start, end) for a, b, _, _ in selected):
            continue
        if item not in selected:
            selected.append(item)
    return sorted(selected)


def extract_flavors(text: str, products: list[Product]) -> list[tuple[str, int, int]]:
    """Nhận hương vị phổ thông và hương vị mới do nguồn cung cấp."""
    vocabulary = {flavor: list(words) for flavor, words in FLAVOR_WORDS.items()}
    for product in products:
        if product["flavor"]:
            vocabulary.setdefault(product["flavor"], []).append(product["flavor"])
    found = []
    for flavor, phrases in vocabulary.items():
        for phrase in phrases:
            for start, end in phrase_spans(text, phrase):
                value = (flavor, start, end)
                if value not in found:
                    found.append(value)
    # Cụm "vị X" cho phép ghi nhận hương vị chưa có trong từ vựng ở empty mode.
    explicit = re.search(r"\b(?:huong vi|vi)\s+(.+?)(?=\s+(?:duoi|cho|va|toi da|ngan sach)\b|[.,]|$)", text)
    if explicit and not any(start >= explicit.start(1) and end <= explicit.end(1) for _, start, end in found):
        found.append((explicit.group(1).strip(), explicit.start(1), explicit.end(1)))
    return found


def parse_money(amount: str, unit: str | None) -> int:
    """Đổi 300k, 1,5 triệu, 300.000 đồng thành số nguyên VND."""
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", amount):
        number = float(amount.replace(".", "").replace(",", ""))
    else:
        number = float(amount.replace(",", "."))
    multiplier = 1_000_000 if unit in {"tr", "trieu"} else 1_000 if unit in {"k", "nghin", "ngan"} else 1
    return round(number * multiplier)


def extract_budgets(text: str) -> list[int]:
    """Số có đơn vị tiền hoặc đứng sau từ chỉ ngân sách; không lấy số người."""
    matches = list(re.finditer(rf"\b({NUMBER})\s*({MONEY_UNIT})\b", text))
    values = [parse_money(match.group(1), match.group(2)) for match in matches]
    context = rf"\b(?:duoi|toi da|khong qua|ngan sach(?: la)?|tam|khoang)\s+({NUMBER})(?:\s*({MONEY_UNIT})\b)?"
    for match in re.finditer(context, text):
        if not any(a.start() <= match.start(1) < a.end() for a in matches):
            values.append(parse_money(match.group(1), match.group(2)))
    return list(dict.fromkeys(values))


def extract_query(text: str) -> str | None:
    """Giữ cụm bánh chưa nhận diện để hỏi nguồn; không gán tên sản phẩm thật."""
    match = re.search(
        r"\bbanh\s+(.+?)(?=\s+(?:duoi|toi da|khong qua|cho|gia|size|kich thuoc|ngan sach|va|con hang|co san|bao nhieu)\b|[.,]|$)",
        text,
    )
    if not match:
        return None
    phrase = match.group(1).strip()
    phrase = re.sub(r"\s+(?:khong|nhe|a)$", "", phrase)
    # "bánh cho 6 người", "bánh dưới 300k" là điều kiện, không phải tên bánh.
    if re.match(r"^(?:duoi|cho|toi da|khong qua|ngan sach|gia|size|kich thuoc)\b", phrase):
        return None
    phrase = re.sub(rf"\b{NUMBER}\s*(?:{MONEY_UNIT}|nguoi|cai|chiec|cm)\b", "", phrase).strip()
    return phrase or None


def analyze_message(text: str, repository: CatalogRepository) -> NLUResult:
    """Phân tích một câu; chỉ gọi interface catalog, không mở file dữ liệu."""
    normalized = normalize_text(text)
    catalog = safe_search_products(repository, {})
    products = catalog["products"] if catalog["status"] == "success" else []
    mentions = find_product_mentions(normalized, products)
    product_ids = list(dict.fromkeys(item[2] for item in mentions))
    product_terms = list(dict.fromkeys(item[3] for item in mentions))
    flavor_mentions = extract_flavors(normalized, products)
    explicit_flavors = list(dict.fromkeys(
        flavor for flavor, start, end in flavor_mentions
        if not any(a <= start and end <= b for a, b, _, _ in mentions)
    ))
    # Khi alias đã xác định bánh, hương vị chuẩn phải lấy từ sản phẩm của nguồn,
    # không lấy nhãn suy ra từ từ vựng chung (ví dụ chocolate/socola).
    named_flavors = [product["flavor"] for product in products if product["id"] in product_ids and product["flavor"]]
    flavors = list(dict.fromkeys([*explicit_flavors, *named_flavors]))
    budgets = extract_budgets(normalized)
    servings = [int(value) for value in re.findall(r"\b(\d+)\s*(?:nguoi|khach|suat|phan)\b", normalized)]
    quantities = [int(value) for value in re.findall(r"\b(\d+)\s*(?:banh|cai|chiec|hop)\b", normalized)]
    sizes = re.findall(r"\b(\d+)\s*cm\b", normalized)
    query = None if product_ids else extract_query(normalized)
    if not product_terms and query:
        product_terms = ["banh " + query]

    intents: list[Intent] = []
    for intent, phrases in INTENT_PHRASES.items():
        if any(phrase_spans(normalized, phrase) for phrase in phrases):
            intents.append(intent)
    if re.search(r"\bbao nhieu\b(?!\s+(?:nguoi|cm))", normalized) and "price" not in intents:
        intents.append("price")
    if re.search(r"\bco\b.*\bbanh\b.*\bkhong\b", normalized) and "availability" not in intents:
        intents.append("availability")
    if flavors and "flavor" not in intents:
        intents.append("flavor")
    if (budgets or servings or (not intents and (product_ids or query))) and "recommendation" not in intents:
        intents.append("recommendation")
    if not intents:
        intents = ["fallback"]

    has_attributes = bool(budgets or servings or quantities or sizes or explicit_flavors)
    shared_alias = any(
        (a, b) == (c, d) and first_id != second_id
        for a, b, first_id, _ in mentions for c, d, second_id, _ in mentions
    )
    ambiguous = (
        shared_alias or (len(product_ids) > 1 and has_attributes)
        or len(budgets) > 1 or len(set(servings)) > 1
        or len(set(quantities)) > 1 or len(set(sizes)) > 1
        or (len(flavors) > 1 and len(product_ids) <= 1)
        or any(value <= 0 for value in [*servings, *quantities])
        or any(int(value) <= 0 for value in sizes)
    )
    # Chưa triển khai bộ lọc loại trừ: hỏi lại thay vì đảo ý người dùng.
    if re.search(r"\b(?:khong thich|khong muon|khong lay|khong chon|tru)\b", normalized):
        ambiguous = True
    return {
        "raw_text": text, "normalized_text": normalized, "intents": intents,
        "product_ids": product_ids, "product_terms": product_terms, "query": query,
        "flavors": flavors, "budgets_vnd": budgets,
        "price_inclusive": not bool(phrase_spans(normalized, "duoi")),
        "servings": servings[0] if servings else None,
        "quantity": quantities[0] if quantities else None,
        "size": f"{sizes[0]} cm" if sizes else None,
        "requires_clarification": ambiguous, "catalog_status": catalog["status"],
    }


def check_llm_proposal(proposal: LLMNLU, rule: NLUResult) -> str | None:
    """Kiểm tra nghĩa cơ bản sau Pydantic; lỗi đề xuất cho phép quay về rule."""
    text = rule["normalized_text"]
    for term in proposal.product_mentions:
        value = normalize_text(term)
        if value not in {"banh", "banh do", "loai do", "no"} and (not value or not phrase_spans(text, value)):
            return "invalid_nlu_mentions"
    if proposal.budget_vnd is not None:
        if rule["budgets_vnd"] and rule["budgets_vnd"] != [proposal.budget_vnd]:
            return "nlu_rule_conflict"
        if not rule["budgets_vnd"] and not re.search(r"\b(?:ngan sach|nghin|ngan|trieu|dong|vnd|k|tr)\b", text):
            return "invalid_nlu_context"
    for field, indicator in [
        ("servings", r"\b(?:nguoi|khach|suat|phan)\b"),
        ("quantity", r"\b(?:banh|cai|chiec|hop)\b"),
        ("size", r"\b(?:size|kich thuoc|co|cm)\b"),
    ]:
        value = getattr(proposal, field)
        if value is not None:
            if rule[field] is not None and normalize_text(str(rule[field])).replace(" ", "") != normalize_text(str(value)).replace(" ", ""):
                return "nlu_rule_conflict"
            if rule[field] is None and not re.search(indicator, text):
                return "invalid_nlu_context"
    if proposal.flavor and not rule["flavors"] and not phrase_spans(text, proposal.flavor):
        return "invalid_nlu_context"
    return None


def merge_llm_nlu(
    text: str, proposal: LLMNLU, repository: CatalogRepository,
    rule_result: NLUResult | None = None,
) -> NLUResult:
    """Đề xuất LLM bổ sung rule; ID chỉ giữ từ tên/alias repository đã đối chiếu."""
    result = deepcopy(rule_result if rule_result is not None else analyze_message(text, repository))
    normalized = result["normalized_text"]
    ambiguous = result["requires_clarification"]
    terms = []
    for term in proposal.product_mentions:
        value = normalize_text(term)
        if value in {"banh", "banh do", "loai do", "no"}:
            continue  # Đại từ nối tiếp không phải yêu cầu chọn bánh mới.
        if not value or not phrase_spans(normalized, value):
            ambiguous = True  # Cụm model tự thêm không được biến thành sản phẩm.
        else:
            terms.append(term)
    if not result["product_ids"] and terms:
        result["product_terms"] = list(dict.fromkeys(terms))
        if not result["query"] and len(terms) == 1:
            result["query"] = re.sub(r"^banh\s+", "", normalize_text(terms[0]))

    intents = list(dict.fromkeys([*result["intents"], *proposal.intents]))
    result["intents"] = [intent for intent in intents if intent != "fallback"] or ["fallback"]
    if proposal.budget_vnd is not None:
        if result["budgets_vnd"] and result["budgets_vnd"] != [proposal.budget_vnd]:
            ambiguous = True
        elif not result["budgets_vnd"]:
            result["budgets_vnd"] = [proposal.budget_vnd]
            result["price_inclusive"] = proposal.price_inclusive
    for field in ("servings", "quantity", "size"):
        value = getattr(proposal, field)
        if value is not None:
            old_value = normalize_text(str(result[field])).replace(" ", "")
            new_value = normalize_text(str(value)).replace(" ", "")
            if result[field] is not None and old_value != new_value:
                ambiguous = True
            elif result[field] is None:
                result[field] = value
    if proposal.flavor:
        flavor = proposal.flavor
        for canonical, aliases in FLAVOR_WORDS.items():
            if normalize_text(flavor) in [normalize_text(canonical), *aliases]:
                flavor = canonical
                break
        if result["flavors"] and result["product_ids"]:
            pass  # Nhãn vị của bánh đã nhận diện luôn thuộc quyền xác định của nguồn.
        elif result["flavors"]:
            if normalize_text(flavor) not in [normalize_text(item) for item in result["flavors"]]:
                ambiguous = True
        else:
            result["flavors"] = [flavor]
    has_attributes = bool(result["budgets_vnd"] or result["servings"] or result["quantity"] or result["size"] or proposal.flavor)
    if (len(terms) > 1 or len(result["product_ids"]) > 1) and has_attributes:
        ambiguous = True
    result["requires_clarification"] = ambiguous
    return result
