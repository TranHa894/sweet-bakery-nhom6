"""Tư vấn có bước chờ riêng; chỉ chọn/lọc dữ liệu, không sửa bản nháp đặt hàng."""
from copy import deepcopy
from app.text_utils import normalize_text, format_vnd

GROUP_LABELS = {"cream_cake": "bánh kem", "tea": "trà", "coffee": "cà phê", "mini": "bánh nhỏ"}
SWEET_LABELS = {"high": "ngọt nhiều", "medium": "ngọt vừa", "low": "ít ngọt"}
TASTE_LABELS = {"fruit": "trái cây", "chocolate": "sô cô la", "cream": "kem/vani/trang trí",
    "milk_tea": "trà sữa", "fruit_tea": "trà trái cây", "matcha": "trà xanh",
    "vanilla": "vani", "coffee_cream": "cà phê/kem"}
COFFEE_LABELS = {"strong": "đậm, đắng", "creamy": "béo, mặn nhẹ, dễ uống", "mild": "dịu, mát, ít đắng"}
PROFILE_FIELDS = ("sweetness", "taste_family", "coffee_style")
MORE_ADVICE_LABEL = "Xem thêm lựa chọn khác"


def selection_sentence(filters):
    """Nội dung nút gồm lựa chọn đã biết; Qwen vẫn hiểu và validate một lần."""
    parts = ["Gợi ý " + GROUP_LABELS.get(filters.get("product_type"), "sản phẩm")]
    for key, labels in (("sweetness", SWEET_LABELS), ("taste_family", TASTE_LABELS), ("coffee_style", COFFEE_LABELS)):
        if filters.get(key) in labels:
            parts.append(("vị " if key == "taste_family" else "") + labels[filters[key]])
    if filters.get("flavor"):
        parts.append("vị " + filters["flavor"])
    if "max_price_vnd" in filters:
        parts.append(("không quá " if filters.get("price_inclusive", True) else "dưới ") + str(filters["max_price_vnd"]) + " đồng")
    if "min_price_vnd" in filters:
        parts.append(("từ " if filters.get("min_price_inclusive", True) else "trên ") + str(filters["min_price_vnd"]) + " đồng")
    return " ".join(parts)


def advice_pages(current):
    """Một trang tìm đơn hoặc tối đa bốn nhóm trong cùng lượt hỏi."""
    saved = current.get("advice_page")
    return saved.get("queries", [saved]) if saved else []


def more_advice_selection(current):
    page = next((page for page in advice_pages(current) if page.get("has_more", True)), None)
    return {"advice": "more", "message": MORE_ADVICE_LABEL, "page": page}


def resolve_advice_selection(current, message):
    """Giải mã đúng nút/số của bước đang chờ, không phân loại câu tự nhiên."""
    pending = current.get("advice_pending") or {}
    field = pending.get("field")
    labels = {"product_type": GROUP_LABELS, "sweetness": SWEET_LABELS,
              "taste_family": TASTE_LABELS, "coffee_style": COFFEE_LABELS}.get(field, {})
    active = {normalize_text(label) for label in current.get("quick_replies", [])}
    normalized = normalize_text(message).strip()
    if normalized == normalize_text(MORE_ADVICE_LABEL) and normalized in active:
        return more_advice_selection(current)
    for number, option in enumerate(pending.get("options", []), 1):
        label = normalize_text(option["label"])
        if label in active and normalized in {str(number), label}:
            value = next((key for key, text in labels.items() if normalize_text(text) == label), None)
            if value is not None:
                return {"field": field, "value": value, "message": option["message"]}
    return None


def expand_advice_selection(current, message):
    """Giữ cách gọi hiện có; nội dung câu gửi Qwen không thay đổi."""
    selection = resolve_advice_selection(current, message)
    return selection["message"] if selection else message


def apply_advice_selection(proposal, selection, *, filter_map=None):
    """Sau khi model hợp lệ: chốt delta từ nút, giữ nhu cầu cũ bằng refine."""
    if selection is None:
        return proposal
    if (proposal.intents != ["recommendation"] or len(proposal.requests) != 1
            or proposal.requests[0].intents != ["recommendation"]
            or proposal.action != "none" or proposal.order_operation != "none"
            or proposal.order_update or proposal.order_items or proposal.order_product_mentions
            or proposal.product_mentions or proposal.reference != "none"
            or proposal.requests[0].product_mentions or proposal.requests[0].reference != "none"
            or proposal.updates.model_dump(exclude_none=True) or proposal.clear_slots):
        raise ValueError("invalid_advice_selection")
    # Lựa chọn bảng tư vấn là một delta đã xác định, không phải yêu cầu mới.
    # Chỉ ghi field vừa chọn; bộ lọc trước đó được merge_preferences giữ lại.
    request = proposal.requests[0].model_dump()
    advice = selection.get("advice", "guided")
    page = selection.get("page") or {}
    filters = {field: page["filters"][target] for field, target in (filter_map or {}).items()
               if target in page.get("filters", {})} if advice == "more" else {
                   selection["field"]: selection["value"]}
    request.update(advice=advice, search_scope="refine", price_preference="none",
                   filters=filters,
                   excluded_product_mentions=[], ambiguous=False)
    return type(proposal).model_validate({**proposal.model_dump(), "requests": [request]})


def advice_question(current, scope, products):
    """Hỏi một bước còn thiếu; None nghĩa là đủ dữ liệu để gợi ý ngay."""
    mode = scope.get("advice", "none")
    filters = scope["filters"]
    group = filters.get("product_type")
    if mode not in {"guided", "any", "more"}:
        return None
    if mode in {"any", "more"} or scope.get("price_preference", "none") != "none":
        current["advice_pending"] = None
        return None
    # Ràng buộc giá/vị đã rõ thì trả ngay, không ép khách đi hết bảng hỏi.
    known_taste = any(filters.get(key) for key in ("flavor", "taste_family", "coffee_style"))
    if known_taste or any(key in filters for key in ("max_price_vnd", "min_price_vnd")):
        current["advice_pending"] = None
        return None
    field, labels, question = None, {}, ""
    if group not in GROUP_LABELS:
        field, labels = "product_type", GROUP_LABELS
        if group in {"cake", "drink"}:
            kinds = ("cream_cake", "mini") if group == "cake" else ("tea", "coffee")
            labels = {kind: GROUP_LABELS[kind] for kind in kinds}
        question = "Bạn muốn xem loại nào ạ?"
    elif group in {"cream_cake", "tea"} and not filters.get("sweetness"):
        field, labels = "sweetness", SWEET_LABELS
        question = "Bạn thích độ ngọt nào ạ?"
    elif group in {"cream_cake", "tea"} and len(products) > 3:
        field = "taste_family"
        keys = ("fruit", "chocolate", "cream") if group == "cream_cake" else ("milk_tea", "fruit_tea")
        labels = {key: TASTE_LABELS[key] for key in keys}
        question = "Bạn thích vị nào ạ?"
    elif group == "coffee":
        field, labels = "coffee_style", COFFEE_LABELS
        question = "Bạn thích cà phê kiểu nào ạ?"
    elif group == "mini":
        field = "taste_family"
        labels = {key: TASTE_LABELS[key] for key in ("chocolate", "matcha", "vanilla", "coffee_cream")}
        question = "Bạn thích vị nào ạ?"
    if field is None:
        current["advice_pending"] = None
        return None
    # Không hỏi độ ngọt khi adapter không có metadata đó.
    if field != "product_type" and not any(p.get("advice_profile") for p in products):
        current["advice_pending"] = None
        return None
    options = []
    for value, label in labels.items():
        chosen = deepcopy(filters)
        chosen[field] = value
        options.append({"label": label[0].upper() + label[1:], "message": selection_sentence(chosen)})
    current["advice_pending"] = {"field": field, "filters": deepcopy(filters), "options": options}
    return question + "\n" + "\n".join(f"{i}. {o['label']}" for i, o in enumerate(options, 1))


def diverse_products(products, limit=3):
    """Đa dạng nhóm trước; không gọi là bán chạy vì chưa có số liệu bán."""
    chosen, groups = [], set()
    for product in products:
        group = product.get("product_type", product["category"])
        if group not in groups:
            chosen.append(product)
            groups.add(group)
            if len(chosen) == limit:
                return chosen
    return (chosen + [p for p in products if p not in chosen])[:limit]


def next_advice_page(current, scope, products, source, *, limit=3, pages=None):
    """Lưu bộ lọc/ID đã xem, dùng chung cho tìm trực tiếp và tư vấn theo bước."""
    filters = scope["filters"]
    saved = advice_pages(current)
    previous = next((page for page in saved
                     if page["source"] == source and page["filters"] == filters), None)
    continuing = scope.get("advice") == "more"
    if continuing and previous:
        seen = list(dict.fromkeys(identifier for page in saved if page["source"] == source
                                  for identifier in page["seen_ids"]))
    elif continuing and not saved:
        seen = [product["id"] for product in current.get("shown_products", [])]
    else:
        seen = []
    seen_ids = set(seen)
    remaining = [product for product in products if product["id"] not in seen_ids]
    shown = diverse_products(remaining, limit) if scope.get("advice") == "any" else remaining[:limit]
    has_more = len(remaining) > len(shown)
    page = {"source": source, "filters": deepcopy(filters),
            "seen_ids": list(dict.fromkeys([*seen, *(p["id"] for p in shown)])),
            "has_more": has_more,
            "remaining_ids": [p["id"] for p in remaining if p["id"] not in {x["id"] for x in shown}],
            "ranking": {key: deepcopy(scope[key]) for key in ("price_preference", "comparison_product_ids")
                        if key in scope}}
    if pages is None:
        current["advice_page"] = page
    else:
        pages.append(page)
    return shown, has_more


def save_advice_pages(current, pages, selection):
    """Khi xem thêm, cập nhật nhóm đang xem và giữ các nhóm chưa xem hết."""
    previous = advice_pages(current)
    selected = (selection or {}).get("page")
    if selected is not None and selected in previous:
        previous = list(previous)
        index = previous.index(selected)
        previous[index:index + 1] = pages
        pages = previous
    for page in pages:
        seen = {identifier for other in pages if other["source"] == page["source"]
                for identifier in other["seen_ids"]}
        page["remaining_ids"] = [identifier for identifier in page.get("remaining_ids", []) if identifier not in seen]
        page["has_more"] = bool(page["remaining_ids"])
    current["advice_page"] = pages[0] if len(pages) == 1 else {"queries": pages}
    return any(page["has_more"] for page in pages)


def advice_summary(products, *, has_more=False):
    lines = []
    for product in products:
        prices = sorted({v["price_vnd"] for v in product["variants"] if v["price_vnd"] is not None})
        price = " / ".join(format_vnd(p) for p in prices) if prices else "chưa có giá"
        note = product.get("advice_profile", {}).get("note") or (
            "Vị " + product["flavor"] + "." if product.get("flavor") else "Hương vị cần nhân viên xác nhận.")
        lines.append(f"- {product['name']} — {price}: {note}")
    ending = "Bạn muốn chọn món nào, hay xem thêm lựa chọn khác?" if has_more else "Bạn muốn chọn món nào ạ?"
    return "Mình gợi ý:\n" + "\n".join(lines) + "\n" + ending
