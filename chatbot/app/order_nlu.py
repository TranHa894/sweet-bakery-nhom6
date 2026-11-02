"""Cầu nối đề xuất AI → slot: kiểm tra câu gốc, không xác nhận/gọi tool."""

from copy import deepcopy
import re
import unicodedata

from app.order_flow import business_command_text, update_slot
from app.order_service import normalize_contact_value
from app.repositories.catalog import safe_search_products
from app.repositories.mock_catalog import canonical_flavors, styles_from_name
from app.text_utils import ADVICE_PREFERENCE_CUES, normalize_text, normalize_business_evidence, normalize_shopping_terms, numeric_evidence_text, budget_evidence, parse_money, mentioned_catalog_groups, normalize_money_evidence

NUMBER_WORDS = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5,
                "sau": 6, "bay": 7, "tam": 8, "chin": 9, "muoi": 10}

# Chỉ kiểm chứng quyền dùng tham chiếu của Qwen; "trên 100k" không phải "ở trên".
_QUERY_REFERENCE_CUES = (r"\b(?:nay|do|ay|vua|truoc|trong so|giu|van|nhu cu|re hon|dat hon|"
                         r"thu\s*(?:nhat|hai|1|2)|dau tien|ca\s*(?:hai|2)|tat ca|toan bo|ben tren|o tren|"
                         r"cung\s+(?:vi|loai|nhom|huong\s+vi))\b")


def resolve_mentions(mentions: list[str], repository, shown: list[dict], reference: str, selected_id=None, focus_ids=None, choice_ids=None) -> dict:
    """ID từ nguồn/thẻ đã đối chiếu; both/all chỉ chọn tập bánh đã giới thiệu."""
    result = safe_search_products(repository, {})
    if result["status"] != "success":
        return {"status": result["status"], "ids": [], "ambiguous": False, "error": result["error"]}
    products = result["products"]
    by_id = {p["id"]: p for p in products}
    ids = []
    unresolved = []
    candidates = []
    ambiguous = False
    for mention in mentions:
        text = normalize_text(mention)
        # Đơn vị đếm không phải một phần tên món; vẫn đối chiếu alias trong nguồn.
        text = re.sub(r"^(?:[0-9]+\s+)?(?:coc|ly|cai|chiec)\s+", "", text)
        short = re.sub(r"^(?:banh\s+)?(?:kem\s+)?", "", text)
        exact = [p["id"] for p in products if text == normalize_text(p["id"]) or
                 any(text == normalize_text(x) or short == normalize_text(x) for x in [p["name"], *p["aliases"]])]
        if not exact:
            matches = safe_search_products(repository, {"query": text})
            if matches["status"] == "error":
                return {"status": "error", "ids": [], "ambiguous": False, "error": matches["error"]}
            exact = [p["id"] for p in matches["products"]]
        if len(exact) > 1:
            candidates.extend(by_id[i] for i in exact if i in by_id)
            ambiguous = True
        elif exact:
            ids.append(exact[0])
        else:
            unresolved.append(mention)
    # Tên rõ trong lượt này là phạm vi truy vấn. Không cộng thêm draft chỉ vì
    # model đồng thời trả reference=last (lỗi đã tái hiện với Qwen thật).
    if not mentions and reference != "none":
        # choice_ids=[] là chưa có lựa chọn: không tự mượn draft hay topic cũ.
        offered = list(dict.fromkeys(choice_ids if choice_ids is not None else
                                     [p["id"] for p in shown]))
        valid = [by_id[identifier] for identifier in offered if identifier in by_id]
        target = None
        if reference in {"both", "all"}:
            stale_choices = any(identifier not in by_id for identifier in offered)
            ambiguous = (not valid or stale_choices
                         or reference == "both" and len(offered) != 2)
            if ambiguous:
                candidates.extend(valid)
            else:
                ids.extend(offered)
        elif reference == "last":
            reference_ids = list(focus_ids) if focus_ids is not None else [p["id"] for p in valid]
            # Đối tượng đang thảo luận ưu tiên hơn bánh trong đơn. Chỉ dùng
            # draft khi chưa có đối tượng thảo luận; reference=order chọn riêng.
            if not reference_ids and selected_id:
                reference_ids.append(selected_id)
            reference_ids = list(dict.fromkeys(identifier for identifier in reference_ids if identifier in by_id))
            target = by_id[reference_ids[0]] if len(reference_ids) == 1 else None
            if target is None:
                candidates.extend(by_id[i] for i in reference_ids)
        elif reference == "order":
            target = by_id.get(selected_id)
        elif reference in {"first", "second"}:
            # Bánh cũ mất khỏi nguồn không được làm dịch vị trí món kế tiếp.
            if any(identifier not in by_id for identifier in offered):
                candidates.extend(valid)
            else:
                index = 0 if reference == "first" else 1
                target = valid[index] if len(valid) > index else None
        elif reference == "cheaper":
            def price(p):
                return min((v["price_vnd"] for v in p["variants"] if v["price_vnd"] is not None), default=10**15)
            selected = by_id.get(selected_id)
            cheaper = [p for p in valid if selected is None or price(p) < price(selected)]
            target = min(cheaper, key=price) if cheaper else None
        if reference not in {"both", "all"}:
            if target is None:
                ambiguous = True
            else:
                ids.append(target["id"])
    return {"status": "success" if ids else "no_results", "ids": list(dict.fromkeys(ids)),
            "ambiguous": ambiguous, "unresolved_mentions": unresolved,
            "candidates": [{"id": p["id"], "name": p["name"]} for p in candidates], "error": None}


def catalog_alias_hints(message: str, repository) -> list[str]:
    """Gợi ý từ vựng nguồn cho Qwen; không tạo intent, ID hoặc chọn đơn."""
    if repository is None:
        return []
    try:
        result = safe_search_products(repository, {})
    except Exception:
        return []
    raw = normalize_text(business_command_text(message))
    return list(dict.fromkeys(normalize_text(term) for product in result["products"]
        for term in [product["name"], *product["aliases"]]
        if re.search(r"(?<!\w)" + re.escape(normalize_text(term)) + r"(?!\w)", raw)))


def catalog_grounded_names(raw: str, repository):
    """Alias thật có trong câu cho phép tên chuẩn cùng ID; không trích intent."""
    try:
        result = safe_search_products(repository, {})
    except Exception:
        return None
    if result["status"] == "error":
        return None  # Controller sẽ báo lỗi nguồn trước khi thực hiện nghiệp vụ.
    names = set()
    owners = {}
    for product in result["products"]:
        for term in [product["name"], *product["aliases"]]:
            owners.setdefault(normalize_text(term), set()).add(product["id"])
    for product in result["products"]:
        terms = [product["name"], *product["aliases"]]
        if any(len(owners[normalize_text(term)]) == 1 and re.search(r"(?<!\w)" + re.escape(normalize_text(term)) + r"(?!\w)", raw) for term in terms):
            names.update(normalize_text(term) for term in terms)
    return names


def plural_reference_evidence(text: str, reference: str, offered_count=None) -> bool:
    """Chỉ kiểm chứng tham chiếu AI đã chọn, không trích ý định hay số lượng."""
    text = normalize_text(text)
    suffix = r"(?:\s*(?:loai\s*banh|banh|loai|cai|chiec))?"
    both_phrase = r"(?:ca\s*(?:hai|2)|tat\s*ca\s*(?:hai|2)|both)"
    all_phrase = r"(?:tat\s*ca|toan\s*bo|all)"
    if reference == "both":
        phrase = both_phrase
    elif reference == "all":
        phrase = all_phrase
    else:
        return False
    if type(offered_count) is int and offered_count == 2:
        phrase = "(?:" + both_phrase + "|" + all_phrase + ")"
    prefix = r"(?<!\w)(?:(?:dat|mua|lay|them|doi)\s*)?"
    return bool(re.search(prefix + phrase + suffix + r"(?!\w)", text))


def reference_only_phrase(text: str) -> bool:
    """Nhận dạng tên giả chỉ gồm tham chiếu để bác đề xuất AI, không chọn ID."""
    phrase = normalize_text(text)
    noun = r"(?:banh|loai(?:\s*banh)?|chiec|mon|cai)"
    plural = (r"(?:ca\s*(?:2|hai)|tat\s*ca|toan\s*bo|both|all)"
              r"(?:\s*(?:loai\s*banh|banh|loai|cai|chiec))?")
    singular = (r"(?:" + noun + r"\s*)?"
                r"(?:thu\s*(?:hai|2|mot|nhat|1)|dau\s*tien|"
                r"re\s*(?:hon|nhat)|vua\s*(?:roi|nhac)|do|nay)")
    return bool(re.fullmatch(r"(?:" + plural + "|" + singular
                             + r")(?:\s*(?:do|nay))?", phrase))


def each_quantity_values(text: str) -> set[int]:
    """Kiểm chứng số đi cùng mỗi/từng, kể cả 'moi1c'; không chọn món/intent."""
    number = r"\d+|mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi"
    pattern = (r"(?<!\w)(?:moi|tung)\s*"
               r"(?:(?:loai(?:\s*banh)?|banh|cai|chiec)\s*)?"
               r"(" + number + r")(?:\s*(?:banh|cai|chiec|c))?(?!\w)")
    values = re.findall(pattern, normalize_text(text))
    return {int(value) if value.isdigit() else NUMBER_WORDS[value] for value in values}


def bundle_quantity_evidence(message, clause):
    """Chỉ kiểm chứng số lượng trong đúng cụm món; tiền không phải số lượng."""
    value = normalize_shopping_terms(clause or "")
    words = "|".join(NUMBER_WORDS)
    counts = {NUMBER_WORDS[m[1]] for m in re.finditer(
        r"(?<!\w)(" + words + r")\s+(?:(?:cai|coc|ly|phan|chiec)\s+)?(?:banh|tra|ca phe)\b", value)}
    leading = re.match(r"(" + words + r")\s+(?!\d|nghin\b|ngan\b|trieu\b)\w+", value)
    if leading:
        counts.add(NUMBER_WORDS[leading[1]])
    for match in re.finditer(r"(?<![\w.,])(\d+)(?![\w.,])", value):
        if not re.match(r"\s*(?:nghin|ngan|trieu|tr|k|vnd|dong|d|₫)\b", value[match.end():]):
            counts.add(int(match[1]))
    current = normalize_shopping_terms(message)
    position = current.find(value) if value else -1
    if position >= 0:
        words = "|".join(NUMBER_WORDS)
        prefix = re.search(r"(?<!\w)(\d+|" + words + r")\s*(?:(?:cai|coc|ly|phan|chiec)\s*)?$", current[:position])
        if prefix:
            counts.add(int(prefix[1]) if prefix[1].isdigit() else NUMBER_WORDS[prefix[1]])
    return counts | each_quantity_values(message)


def ground_bundle_questions(message, proposal):
    """Gắn lại đoạn nguồn duy nhất cho các nhóm Qwen đã chọn, không trích intent/filter."""
    if (proposal.intents != ["recommendation"] or not 2 <= len(proposal.requests) <= 4
            or proposal.action != "none" or proposal.order_operation != "none"
            or any(r.product_mentions or r.reference != "none" or not r.filters.product_type
                   for r in proposal.requests)):
        return
    text = normalize_shopping_terms(message)
    budget_start = None
    if proposal.bundle_budget:
        budget = normalize_shopping_terms(proposal.bundle_budget.question)
        positions = list(re.finditer(re.escape(budget), text))
        if len(positions) != 1:
            return
        budget_start = positions[0].start()
    anchors = []
    for request in proposal.requests:
        clause = normalize_shopping_terms(request.question or "")
        # Model hay lặp "gợi ý" ở mọi mục. Chỉ bỏ tiền tố chung, không đổi tên/vị.
        if clause not in text and text.startswith("goi y "):
            clause = clause.removeprefix("goi y ")
        if not clause:
            return
        positions = list(re.finditer(r"(?<!\w)" + re.escape(clause) + r"(?!\w)", text))
        if len(positions) != 1 or request.filters.product_type not in mentioned_catalog_groups(clause):
            return  # Trùng/mơ hồ thì giữ nguyên để validator bác, không đoán liên kết.
        start = positions[0].start()
        count_prefix = re.search(r"(?<!\w)(\d+|" + "|".join(NUMBER_WORDS)
            + r")\s*(?:(?:cai|coc|ly|phan|chiec)\s*)?$", text[:start])
        if count_prefix:
            count = int(count_prefix[1]) if count_prefix[1].isdigit() else NUMBER_WORDS[count_prefix[1]]
            if 1 <= count <= 1000:
                start = count_prefix.start()
        anchors.append((start, positions[0].end(), request))
    anchors.sort(key=lambda item: item[0])
    if any(left[1] > right[0] for left, right in zip(anchors, anchors[1:])):
        return
    for index, (start, end, request) in enumerate(anchors):
        boundary = anchors[index + 1][0] if index + 1 < len(anchors) else len(text)
        if budget_start is not None and end <= budget_start < boundary:
            boundary = budget_start
        # Phần mở rộng chỉ là đoạn nguồn giữa hai đối tượng riêng biệt.
        request.question = re.sub(r"(?:\s+|[,.;]|\bva\b|\bvoi\b)+$", "", text[start:boundary]).strip()


def normalize_bundle_preferences(message, proposal, conversation=None):
    """Chuẩn hóa mô tả AI và quyền kế thừa bộ lọc; không tạo intent/giá/sản phẩm."""
    current = proposal.model_copy(deep=True)
    ground_bundle_questions(message, current)
    active = (conversation or {}).get("bundle_context")
    text = normalize_shopping_terms(message)
    # Qwen vẫn trích intent/loại/vị. Code chỉ quyết định quyền kế thừa bộ lọc:
    # yêu cầu tìm mới rõ ràng không được trộn vào combo cũ.
    fresh_groups = (current.intents == ["recommendation"] and len(current.requests) >= 2
        and current.action == "none" and current.order_operation == "none"
        and re.search(r"\b(?:goi y|tim)\b", text)
        and not re.search(_QUERY_REFERENCE_CUES, re.sub(r"\bngot vua\b", "", text))
        and all(r.intents == ["recommendation"] and r.reference == "none"
                and r.price_preference == "none" and r.advice != "more"
                and r.filters.product_type is not None for r in current.requests))
    for request in current.requests:
        if request.intents != ["recommendation"] or request.product_mentions:
            continue
        clause = normalize_shopping_terms(request.question or message)
        if clause not in text:
            continue
        if fresh_groups and request.filters.product_type in mentioned_catalog_groups(clause):
            request.search_scope = "new"
        if current.bundle_budget is not None or active or len(current.requests) > 1:
            bare = re.search(r"(?<!it )(?<!khong )\bngot\b(?!\s+(?:nhieu|dam|vua|hon)\b)", clause)
            if bare and not re.search(r"\b(?:it ngot|ngot (?:nhieu|vua|dam)|khong ngot)\b", clause):
                if request.filters.sweetness in {"high", "medium"}:
                    request.filters.sweetness = "sweet"
            # "món ít ngọt hơn" không cho phép AI tự chọn bánh thay cho trà.
            if (active and request.search_scope == "refine" and not mentioned_catalog_groups(message)
                    and request.filters.sweetness is not None
                    and request.reference == "none"):
                request.filters.product_type = None
                request.search_scope = "refine"
    return current


def check_turn_grounding(message: str, proposal, repository=None, conversation=None, *, _check_omissions=True) -> str | None:
    """Kiểm chứng tên literal/nguồn và viết tắt; không thay intent của AI."""
    raw = normalize_text(message)
    numeric_raw = numeric_evidence_text(message)
    business_raw = normalize_text(business_command_text(message))
    evidence = normalize_business_evidence(message)
    business_evidence = normalize_business_evidence(business_command_text(message))
    if proposal.order_negated and not re.search(r"\b(?:(?:khong|chua|dung)\b[^.!?]*\b(?:dat|mua|lay)\b|chi\s+(?:hoi|xem|tham khao))", business_evidence):
        return "ungrounded_order_negation"
    context = conversation or {}
    offered = (context.get("product_choices") or {}).get("product_ids") or []
    offered_count = len(set(offered)) if isinstance(offered, list) else None
    active_order = (not proposal.order_negated and "order_request" in proposal.intents
                    and (proposal.action == "start_order" or proposal.order_operation != "none"
                         or bool(proposal.order_items)))
    # Chỉ kiểm chứng yêu cầu đặt thuần: "bánh đang đặt" phải dùng namespace của draft.
    # Không áp lên câu hỏi thông tin xen trong một tin nhắn nhiều ý định.
    if (active_order and not proposal.requests
            and re.search(r"\b(?:banh|mon|loai|cai|chiec)\s+dang\s+dat\b", business_evidence)):
        if proposal.order_items:
            if not any(item.reference == "order" for item in proposal.order_items):
                return "ungrounded_order_reference"
        elif proposal.order_product_mentions or (proposal.order_reference or proposal.reference) != "order":
            return "ungrounded_order_reference"
    references = [proposal.reference,
                  *(request.reference for request in proposal.requests),
                  *(item.reference for item in proposal.order_items)]
    if active_order:
        references.append(proposal.order_reference)
    if any(reference in {"both", "all"} and not plural_reference_evidence(message, reference, offered_count)
           for reference in references):
        return "ungrounded_plural_reference"
    for reference, pattern in (
        ("first", r"\b(?:thu\s*(?:nhat|mot|1)|dau\s*tien|(?:banh|loai|cai|chiec)\s*(?:dau|so\s*1|1))\b"),
        ("second", r"\b(?:thu\s*(?:hai|2)|(?:banh|loai|cai|chiec)\s*(?:so\s*)?2)\b"),
    ):
        if reference in references and not re.search(pattern, business_evidence):
            return "ungrounded_ordinal_reference"
    order_plural = (proposal.order_reference in {"both", "all"}
                    or proposal.reference in {"both", "all"}
                    or any(item.reference in {"both", "all"} for item in proposal.order_items))
    selecting_order = (proposal.action == "start_order"
                       or proposal.order_operation in {"select_product", "add_product"})
    information_choice = bool(context.get("pending_information_request"))
    information_choice = (information_choice
                          or bool((context.get("product_choices") or {}).get("intents")))
    pending_order = context.get("pending_order_request")
    order_continuation = proposal.continuation == "order" or bool(pending_order)
    explicit_order = re.search(
        r"(?<!\w)(?:dat|mua|lay|them|doi|tao\s+(?:don|yeu\s*cau))(?=\s|ca(?:2|hai)|tat\s*ca|toan\s*bo|banh|$)|"
        r"(?<!\w)cho\s+(?:toi|minh|em)\s+(?!(?:biet|xem|hoi)\b)",
        business_evidence,
    )
    if (information_choice and order_plural and selecting_order
            and not order_continuation and not explicit_order):
        return "information_choice_is_not_order"
    recommendation_active = ("recommendation" in proposal.intents
                             or any("recommendation" in request.intents for request in proposal.requests))
    money = budget_evidence(message)
    has_budget = (proposal.bundle_budget is not None or proposal.updates.budget_vnd is not None or proposal.updates.min_budget_vnd is not None
                  or any("recommendation" in request.intents
                         and (request.filters.budget_vnd is not None or request.filters.min_budget_vnd is not None)
                         for request in proposal.requests))
    # Một câu có "sản phẩm" + cận tiền tuyệt đối là tìm menu, không phải
    # chọn thẻ trước đó. Chỉ bác output trái bằng chứng; không tự trích intent.
    shopping_clause = normalize_shopping_terms(message)
    generic_money_search = (money["expected"] and re.search(r"\bsan pham\b", shopping_clause)
                            and not re.search(_QUERY_REFERENCE_CUES, shopping_clause)
                            and not proposal.product_mentions
                            and not any(request.product_mentions for request in proposal.requests))
    if _check_omissions and generic_money_search and not recommendation_active:
        return "missing_catalog_budget_query"
    if _check_omissions and generic_money_search and any(
            request.reference != "none" for request in proposal.requests if "recommendation" in request.intents):
        return "unrequested_budget_reference"
    if _check_omissions and recommendation_active and money["expected"] and not has_budget:
        return "missing_budget_constraint"
    if _check_omissions and recommendation_active:
        candidates = [(request.question or (message if len(proposal.requests) == 1 else ""), request.filters)
                      for request in proposal.requests if "recommendation" in request.intents]
        if not proposal.requests:
            candidates = [(message, proposal.updates)]
        if proposal.bundle_budget is not None:
            total = proposal.bundle_budget
            if (normalize_money_evidence(total.question) not in normalize_money_evidence(message)
                    or total.budget_vnd not in money["values"]
                    or total.budget_vnd not in budget_evidence(total.question)["values"]):
                return "ungrounded_bundle_budget"
            candidates.append((total.question, total))
        for clause, constraints in candidates:
            expected = budget_evidence(clause)["expected"]
            if expected:
                for field, value in expected.items():
                    actual = getattr(constraints, field)
                    if field.endswith("inclusive"):
                        actual = True if actual is None else actual
                    if actual != value:
                        return "budget_direction_mismatch"
                # Không được biến trần ngân sách thành mức giá chính xác/range tự bịa.
                for bound in ("budget_vnd", "min_budget_vnd"):
                    if bound not in expected and getattr(constraints, bound) is not None:
                        return "budget_direction_mismatch"
    available_filter = (proposal.updates.available_only is True
                        or any(request.filters.available_only is True for request in proposal.requests))
    if available_filter and not re.search(
            r"\b(?:con\s+(?:hang|banh|loai|san|khong|ko|kh|k)|con$|ton\s*kho|"
            r"co\s*san|het\s*hang|in\s*stock)\b", business_evidence):
        return "ungrounded_availability_filter"
    clearing_allergens = (proposal.updates.allergens == []
                          or "allergens" in proposal.clear_slots
                          or any(request.filters.allergens == [] for request in proposal.requests))
    allergen_clear_evidence = re.search(
        r"\b(?:khong(?:\s+(?:co|bi))?\s+di\s*ung(?:\s+(?:gi|nua))?|"
        r"(?:bo|xoa|huy)\s+(?:(?:tat ca|toan bo)\s+)?(?:dieu kien\s+(?:ve\s+)?)?di\s*ung)"
        r"(?=$|[.,])",
        business_evidence,
    )
    if clearing_allergens and not allergen_clear_evidence:
        return "ungrounded_allergen_clear"
    avoiding_allergens = (bool(proposal.updates.allergens)
                         or any(bool(request.filters.allergens) for request in proposal.requests))
    if avoiding_allergens:
        # allergens là ràng buộc TRÁNH, không phải mọi nguyên liệu khách hỏi tới.
        avoidance_evidence = False
        for cue in re.finditer(r"\b(?:di\s*ung|tranh|kieng|khong\s+(?:an|dung|co|chua))\b",
                               business_evidence):
            before = re.split(r"[.,]", business_evidence[:cue.start()])[-1]
            after = business_evidence[cue.end():].lstrip()
            if cue[0].replace(" ", "") == "diung":
                if re.search(r"\b(?:khong|chua)(?:\s+(?:co|bi))?\s*$", before):
                    continue
            elif cue[0] in {"tranh", "kieng"}:
                if re.search(r"\b(?:khong|chua|dung)(?:\s+(?:can|muon))?\s*$", before):
                    continue
            elif re.match(r"di\s*ung\b", after):
                # "không có dị ứng" không có nghĩa muốn bánh không chứa nguyên liệu.
                continue
            avoidance_evidence = True
            break
        if not avoidance_evidence:
            return "ungrounded_allergen_constraint"
    each_quantities = each_quantity_values(message)
    if _check_omissions and active_order and selecting_order and order_plural and each_quantities:
        if ((proposal.updates.quantity is not None and proposal.updates.quantity not in each_quantities)
                or any(item.quantity is not None and item.quantity not in each_quantities
                       for item in proposal.order_items)):
            return "plural_reference_is_not_quantity"
        global_each = proposal.updates.quantity in each_quantities
        group_each = (bool(proposal.order_items)
                      and all(item.quantity in each_quantities for item in proposal.order_items)
                      and any(item.reference in {"both", "all"} for item in proposal.order_items))
        individual_each = (bool(offered_count)
                           and len(proposal.order_items) == offered_count
                           and all(item.quantity in each_quantities for item in proposal.order_items))
        if not (global_each or group_each or individual_each):
            return "missing_each_quantity"
    pickup_pattern = r"\b(?:cua hang|pickup|tu lay|den lay|(?:lay|nhan)\s+(?:tai\s+|o\s+)?(?:tiem|shop))\b"
    delivery_pattern = r"\b(?:giao|ship|delivery)\b"
    updating_order = (active_order and (proposal.action == "start_order"
                      or proposal.order_operation in {"select_product", "add_product", "update_slots"}))
    disabled_fields = context.get("order", {}).get("disabled_fields", [])
    if _check_omissions and updating_order and "fulfillment" not in disabled_fields:
        # Kiểm chứng phần AI bỏ sót, không tự chọn/ghi slot. Phủ định hoặc
        # câu hỏi policy rõ được tách khỏi bằng chứng hình thức nhận.
        def has_fulfillment_evidence(pattern):
            for match in re.finditer(pattern, business_evidence):
                before = re.split(r"[.,;?!]", business_evidence[:match.start()])[-1]
                if re.search(r"\b(?:khong|chua|dung)(?:\s+(?:muon|can|chon|su dung))*\s*$", before):
                    continue
                informational_clause = any(
                    clause.start() <= match.start() and match.end() <= clause.end()
                    for request in proposal.requests
                    if request.question and "policy" in request.intents
                    for clause in re.finditer(re.escape(normalize_business_evidence(request.question)),
                                              business_evidence)
                )
                if not informational_clause:
                    return True
            return False
        pickup_cue = has_fulfillment_evidence(pickup_pattern)
        delivery_cue = has_fulfillment_evidence(delivery_pattern)
        if pickup_cue != delivery_cue and proposal.updates.fulfillment is None:
            return "missing_fulfillment_update"
        if (pickup_cue and delivery_cue and proposal.updates.fulfillment is not None
                and not proposal.ambiguous):
            return "conflicting_fulfillment_cues"
    mentions = [*proposal.product_mentions, *proposal.order_product_mentions,
                *(item.product_mention for item in proposal.order_items if item.product_mention)]
    for request in proposal.requests:
        # Kiểm chứng yêu cầu xếp/so giá của AI, không tự phân loại hoặc chọn sản phẩm.
        clause = normalize_shopping_terms(request.question or (message if len(proposal.requests) == 1 else ""))
        if "recommendation" in request.intents and not request.product_mentions:
            # Chỉ từ chối loại trái cụm nhóm rõ; không gán type hoặc suy từ tên bánh.
            type_cues = {"cream_cake": r"\bbanh\s+kem\b",
                         "mini": r"\b(?:banh\s+(?:ngot\s+)?nho|banh\s+mini)\b"}
            explicit_types = {kind for kind, pattern in type_cues.items() if re.search(pattern, clause)}
            full_catalog = (re.search(r"\bsan pham\b", clause)
                and not re.search(r"\b(?:banh|tra|ca phe|do uong)\b", clause)
                and not re.search(_QUERY_REFERENCE_CUES, clause)
                and request.price_preference not in {"cheaper_than", "more_expensive_than"})
            if full_catalog and request.filters.product_type is not None:
                return "product_type_mismatch"
            inherited_scope = any(
                context.get("needs", {}).get("filters", {}).get(field) is not None
                and field not in proposal.clear_slots
                for field in ("product_type", "flavor", "servings", "size", "occasion",
                              "sweetness", "taste_family", "coffee_style"))
            if (full_catalog and budget_evidence(clause)["expected"]
                    and request.search_scope != "new" and inherited_scope):
                return "missing_new_search_scope"
            generic_cake = (re.search(r"\bbanh\b", clause)
                            and not explicit_types and request.reference == "none"
                            and request.price_preference not in {"cheaper_than", "more_expensive_than"}
                            and not re.search(r"\bbanh\s+(?:do|nay|vua|dang)\b", clause))
            if generic_cake:
                # "Bánh" gồm cả bánh kem và bánh nhỏ. Không chấp nhận AI tự
                # thu hẹp thành bánh kem; câu rút gọn/tham chiếu vẫn dùng context.
                explicit_types.add("cake")
            if not re.search(r"\bbanh\b", clause):
                beverage_clause = clause
                if request.filters.flavor:
                    # Model có thể nói matcha trong khi khách nói trà xanh.
                    # So cả tên tương đương trước khi kiểm tra nhóm đồ uống.
                    flavor_names = {request.filters.flavor, *canonical_flavors(request.filters.flavor)}
                    for flavor_name in flavor_names:
                        beverage_clause = re.sub(r"(?<!\w)" + re.escape(normalize_text(flavor_name)) +
                                                 r"(?!\w)", "", beverage_clause)
                if request.filters.taste_family in {"matcha", "coffee_cream"}:
                    # Đây là vị của bánh đang hỏi, không phải đổi sang đồ uống.
                    # Enum và bằng chứng vị vẫn được validate riêng bên dưới.
                    beverage_clause = re.sub(r"\b(?:tra xanh|ca phe(?: va)? kem)\b", "", beverage_clause)
                # "Vẫn vị trà xanh" có thể chỉ bổ sung ngân sách, không lặp
                # delta vị đã biết. Từ sau "vị/hương" không phải tên nhóm mới.
                for kind, pattern in {"tea": r"(?<!vi )(?<!huong )\btra\b",
                                      "coffee": r"(?<!vi )(?<!huong )\bca\s+phe\b"}.items():
                    if re.search(pattern, beverage_clause):
                        explicit_types.add(kind)
            negated_type = re.search(r"\b(?:khong(?:\s+(?:can|muon|lay|chon|xem|tim))?|bo|xoa)\s+"
                                     r"(?:loai\s+)?(?:banh\s+(?:kem|nho)|tra|ca\s+phe)\b", clause)
            effective_type = request.filters.product_type
            if len(explicit_types) == 1 and effective_type is None and request.search_scope == "refine":
                # None ở refine là giữ nhóm thật (bánh chung/nhỏ/kem/trà/cà phê).
                # Chỉ chấp nhận nếu khớp đúng nhóm đã lưu; không sửa proposal/draft.
                effective_type = (proposal.updates.product_type
                                  or context.get("needs", {}).get("filters", {}).get("product_type"))
            if len(explicit_types) == 1 and not negated_type and effective_type not in explicit_types:
                return "product_type_mismatch"
            # Hỏi gợi ý nhóm đầy đủ là tìm mới; không vô tình kế thừa giá/vị cũ.
            # Câu nối giữ/vẫn/như cũ được refine. Chỉ bác output sai để Qwen sửa.
            old_filters = context.get("needs", {}).get("filters", {})
            price_is_replaced = (bool(budget_evidence(clause)["expected"])
                or bool({"budget_vnd", "min_budget_vnd"}.intersection(proposal.clear_slots))
                or request.filters.budget_vnd is not None or request.filters.min_budget_vnd is not None)
            inherited_price = not price_is_replaced and any(
                old_filters.get(key) is not None for key in ("min_price_vnd", "max_price_vnd"))
            inherited_flavor = (old_filters.get("flavor") and request.filters.flavor is None
                and "flavor" not in proposal.clear_slots and budget_evidence(clause)["expected"])
            if (_check_omissions and explicit_types and not negated_type
                    and request.reference == "none" and request.price_preference == "none"
                    and request.search_scope != "new" and (inherited_price or inherited_flavor)
                    and not re.search(_QUERY_REFERENCE_CUES, clause)):
                return "missing_new_search_scope"
            known_group = (context.get("needs", {}).get("filters", {}).get("product_type")
                           or context.get("discussion_context", {}).get("product_type"))
            group_clause = clause
            for flavor in (request.filters.flavor, proposal.updates.flavor):
                if flavor:
                    group_clause = re.sub(r"(?<!\w)" + re.escape(normalize_text(flavor))
                                          + r"(?!\w)", "", group_clause)
            changed_groups = {kind for kind in (request.filters.product_type, proposal.updates.product_type)
                              if kind and kind != known_group}
            if (clause and known_group and changed_groups
                    and not re.search(r"\b(?:banh|tra|ca\s+phe|cafe|do\s+uong|san\s+pham)\b", group_clause)):
                return "unmentioned_query_group"
        price_cues = {
            "lowest": r"\b(?:re\s*nhat|gia\s*(?:thap|be)\s*nhat)\b",
            "highest": r"\b(?:(?:dat|mac)\s*nhat|gia\s*cao\s*nhat)\b",
            "cheaper_than": r"\b(?:re\s*hon|gia\s*thap\s*hon|it\s*tien\s*hon)\b",
            "more_expensive_than": r"\b(?:(?:dat|mac)\s*hon|gia\s*cao\s*hon|nhieu\s*tien\s*hon)\b",
        }
        price_clause = re.sub(r"\b(?:khong|chua|dung)(?:\s+(?:can|muon|chon))*\s+"
                              r"(?:loai\s+)?(?:re|dat|mac)\s+(?:nhat|hon)\b", "", clause)
        # "Giá cao hơn 40000đ" là ngưỡng tiền, không phải so với bánh cũ.
        # Chỉ bỏ cụm so sánh khi theo ngay bằng số; trường hợp "đắt hơn
        # loại vừa xem, dưới 400k" vẫn phải giữ yêu cầu so sánh sản phẩm.
        price_clause = re.sub(r"\b(?:(?:re|dat|mac)\s*hon|gia\s*(?:cao|thap)\s*hon|(?:nhieu|it)\s*tien\s*hon)(?=\s*\d)",
                              "", price_clause)
        detected = {mode for mode, pattern in price_cues.items() if re.search(pattern, price_clause)}
        # Từ chối hướng trái bằng chứng rõ; cách nói đồng nghĩa khác vẫn do Qwen hiểu.
        if request.price_preference != "none" and detected and request.price_preference not in detected:
            return "ungrounded_price_preference"
        if (_check_omissions and "recommendation" in request.intents
                and request.price_preference == "none" and request.reference != "cheaper" and detected):
            return "missing_price_preference"
        if (request.question and normalize_text(request.question) not in raw
                and normalize_shopping_terms(request.question) not in normalize_shopping_terms(message)):
            return "ungrounded_question_clause"
        mentions.extend(request.product_mentions)
        mentions.extend(request.excluded_product_mentions)
        constraints = request.filters.model_dump(exclude_none=True)
        if proposal.bundle_budget is not None or (
                len(proposal.requests) > 1 and "recommendation" in request.intents
                and len({r.filters.product_type for r in proposal.requests}) > 1
                and all(r.intents == ["recommendation"] and r.filters.product_type
                        and r.filters.budget_vnd is None and r.filters.min_budget_vnd is None
                        for r in proposal.requests)):
            if not request.product_mentions and not mentioned_catalog_groups(request.question or ""):
                return "invalid_bundle_component"
            if (_check_omissions and not request.product_mentions
                    and re.search(r"(?<!it )(?<!khong )\bngot\b(?!\s+(?:nhieu|dam|vua)\b)", normalize_shopping_terms(request.question or ""))
                    and request.filters.sweetness != "sweet"):
                return "missing_advice_preference"
            quantities = bundle_quantity_evidence(message, request.question)
            if len(quantities) == 1 and request.quantity not in quantities:
                return "missing_bundle_quantity"
            if request.quantity != 1 and request.quantity not in quantities:
                return "ungrounded_bundle_quantity"
        # Không để Qwen bỏ mức ngọt đã nói trong một câu tìm nhóm đầy đủ.
        # Nút/fragment vẫn do FSM tư vấn xử lý như trước.
        if (_check_omissions and "recommendation" in request.intents and not request.product_mentions
                and mentioned_catalog_groups(clause)
                and (len(proposal.requests) > 1 or budget_evidence(clause)["expected"])
                and not re.search(r"\b(?:khong|tranh|bo|ngoai tru)\b", clause)):
            for degree, pattern in {"high": r"\bngot (?:nhieu|dam)\b", "medium": r"\bngot vua\b", "low": r"\bit ngot\b"}.items():
                if re.search(pattern, clause) and (request.filters.sweetness or proposal.updates.sweetness) != degree:
                    return "missing_advice_preference"
        if (_check_omissions and len(proposal.requests) > 1
                and "recommendation" in request.intents and not request.product_mentions
                and mentioned_catalog_groups(clause)
                and not re.search(r"\b(?:khong|tranh|bo|ngoai tru)\b", clause)):
            if request.filters.product_type == "coffee":
                styles = {style for style, pattern in ADVICE_PREFERENCE_CUES["coffee_style"].items() if re.search(pattern, clause)}
                if len(styles) == 1 and request.filters.coffee_style not in styles:
                    return "missing_coffee_preference"
            required_tastes = {
                "fruit": (r"\btrai cay\b", set()),
                "chocolate": (r"\b(?:socola|so co la|chocolate|choco)\b", canonical_flavors("sô cô la")),
                "matcha": (r"\b(?:tra xanh|matcha)\b", canonical_flavors("trà xanh")),
                "vanilla": (r"\b(?:vani|vanilla)\b", canonical_flavors("vani")),
            }
            for family, (pattern, flavors) in required_tastes.items():
                if not re.search(pattern, clause):
                    continue
                accepted = {family}
                if family == "fruit" and request.filters.product_type == "tea":
                    accepted.add("fruit_tea")
                if family == "vanilla" and request.filters.product_type in {"cake", "cream_cake"}:
                    accepted.add("cream")
                if (request.filters.taste_family not in accepted
                        and not (flavors and flavors.issubset(canonical_flavors(request.filters.flavor)))):
                    return "missing_taste_preference"
        if (_check_omissions and len(proposal.requests) == 1
                and "recommendation" in request.intents and not request.product_mentions
                and request.filters.product_type == "coffee"):
            # Kiểm tra thiếu điều kiện, không tự phân loại intent hay gán filter.
            # Giữ dấu khi kiểm chứng: "đến 50k" không phải kiểu "đen".
            styles = set(styles_from_name(message, "coffee"))
            negated_style = re.search(r"\b(?:khong|tranh|bo|ngoai tru)\b[^,.;?!]*\b(?:den|u lanh|cold brew|coldbrew)\b", business_evidence)
            if len(styles) == 1 and not negated_style and not styles.issubset(canonical_flavors(request.filters.flavor)):
                return "missing_beverage_style"
        if constraints:
            query = proposal.model_copy(deep=True)
            query.requests = []
            query.action, query.order_operation, query.clear_slots = "none", "none", []
            query.product_mentions, query.order_product_mentions = [], []
            from app.schemas import TurnUpdates
            query.updates = TurnUpdates(**constraints)
            # Chỉ kiểm chứng filter cục bộ; omission đã kiểm tra toàn lượt ở trên.
            grounding_message = (request.question or message) if len(proposal.requests) > 1 else message
            error = check_turn_grounding(grounding_message, query, repository, conversation,
                                         _check_omissions=False)
            if error:
                return error
        if request.size:
            compact = normalize_text(request.size).replace(" ", "")
            digits = re.match(r"^(\d+)cm$", compact)
            if compact not in raw.replace(" ", "") and not (digits and re.search(r"\b" + digits[1] + r"\b", raw)):
                return "ungrounded_query_size"
    grounded_names = catalog_grounded_names(business_raw, repository) if repository is not None else set()
    for mention in mentions:
        normalized_mention = normalize_text(mention)
        # A catalog can legitimately use an unusual name such as "Bánh Đầu Tiên".
        # Allow it only when an exact verified source alias occurs in THIS turn.
        exact_source_name = (grounded_names is not None
                             and normalized_mention in grounded_names
                             and bool(re.search(r"(?<!\w)" + re.escape(normalized_mention)
                                                + r"(?!\w)", business_raw)))
        if reference_only_phrase(mention) and not exact_source_name:
            return "reference_phrase_is_not_product_name"
        if normalize_text(mention) not in business_raw:
            # Prefix bánh/kem is optional in the resolver too. A conjunction may
            # say 'bánh dâu và socola' while Qwen emits 'bánh socola'.
            short = re.sub(r"^(?:banh\s+)?(?:kem\s+)?", "", normalize_text(mention))
            literal_short = bool(short and re.search(r"(?<!\w)" + re.escape(short) + r"(?!\w)", business_raw))
            if not literal_short and grounded_names is not None and normalize_text(mention) not in grounded_names:
                return "invalid_turn_mention"
    updates = proposal.updates.model_dump(exclude_none=True)
    preference_evidence = ADVICE_PREFERENCE_CUES
    for field, patterns in preference_evidence.items():
        evidence_text = normalize_shopping_terms(message) if field == "sweetness" and updates.get(field) == "sweet" else raw
        if updates.get(field) and not re.search(patterns[updates[field]], evidence_text):
            return "ungrounded_advice_preference"
    for field in ("cake_need", "flavor", "occasion", "name", "phone", "address"):
        if field in updates and normalize_text(updates[field]) not in business_raw:
            # Chấp nhận tên vị tương đương (vanilla/vani, chanh dây/chanh leo);
            # đây là kiểm chứng delta của Qwen, không tự gán intent hoặc sản phẩm.
            if field == "flavor" and canonical_flavors(updates[field]).issubset(canonical_flavors(message)):
                continue
            # Model được bỏ dấu phân cách số, không được đổi mã quốc gia/chữ số.
            candidates = re.findall(r"(?<!\w)\+?[0-9](?:[ .-]*[0-9]){7,14}(?!\w)", message) if field == "phone" else []
            if not any(normalize_contact_value("phone", candidate) == updates[field] for candidate in candidates):
                return "ungrounded_slot"
    if updates.get("cake_text") and any(normalize_text(updates["cake_text"]) == normalize_text(m) for m in mentions) and business_command_text(message) == message:
        pending = (conversation or {}).get("pending_order_question") or {}
        if pending.get("field") != "cake_text":
            return "cake_name_is_not_requested_lettering"
    if updates.get("cake_text") and updates["cake_text"] not in message:
        # Chỉ cho phép khác dạng Unicode tổ hợp/tách dấu, không sửa nội dung.
        import unicodedata
        if unicodedata.normalize("NFC", updates["cake_text"]) not in unicodedata.normalize("NFC", message):
            return "ungrounded_cake_text"
    if updates.get("size"):
        compact = normalize_text(updates["size"]).replace(" ", "")
        digits = re.match(r"^(\d+)cm$", compact)
        if compact not in raw.replace(" ", "") and not (digits and re.search(r"\b" + digits[1] + r"\b", raw)):
            return "ungrounded_size"
    numbers = set(NUMBER_WORDS[word] for word in raw.split() if word in NUMBER_WORDS)
    for match in re.finditer(r"(?<!\w)(\d+(?:[.,]\d+)*)(?:\s*(k|nghin|ngan|trieu|tr)(?!\w))?", numeric_raw):
        value = match[1]
        unit = match[2]
        numbers.add(parse_money(value, unit))
    numbers.update(each_quantities)
    budget_numbers = set(numbers)
    budget_numbers.update(money["values"])
    for field in ("quantity", "servings", "budget_vnd", "min_budget_vnd"):
        evidence_numbers = budget_numbers if field in {"budget_vnd", "min_budget_vnd"} else numbers
        if field in updates and updates[field] not in evidence_numbers:
            return "ungrounded_number"
    for item in proposal.order_items:
        if item.quantity is not None:
            if item.quantity not in numbers:
                return "ungrounded_item_quantity"
            if item.reference in {"both", "all"} and item.quantity not in each_quantities:
                return "plural_reference_is_not_quantity"
    order_reference = proposal.order_reference
    if order_reference is None and not proposal.order_product_mentions and proposal.order_operation != "none":
        order_reference = proposal.reference
    if (order_reference in {"both", "all"} and "quantity" in updates
            and updates["quantity"] not in each_quantities):
        return "plural_reference_is_not_quantity"
    for topping in updates.get("toppings", []):
        if normalize_text(topping) not in raw:
            return "ungrounded_topping"
    if "toppings" in updates and not updates["toppings"] and not re.search(r"\b(?:khong topping|khong them topping|bo topping|topping\s*:\s*khong)\b", evidence):
        return "ungrounded_topping_clear"
    if "cake_text" in updates and updates["cake_text"] == "" and not re.search(r"\b(?:khong (?:viet|ghi) chu|bo chu|chu\s*:\s*khong)\b", evidence):
        return "ungrounded_cake_text_clear"
    if updates.get("pickup_at"):
        phrase = normalize_text(updates["pickup_at"])
        phrase = re.sub(r"(\d{4}-\d{2}-\d{2})t", r"\1 ", phrase)
        if phrase not in raw:
            return "ungrounded_pickup_at"
    if updates.get("fulfillment"):
        pattern = pickup_pattern if updates["fulfillment"] == "pickup" else delivery_pattern
        if not re.search(pattern, evidence):
            return "ungrounded_fulfillment"
    for allergen in updates.get("allergens", []):
        if normalize_text(allergen) not in raw:
            return "ungrounded_allergen"
    if proposal.action == "confirm":
        text = business_evidence
        if "?" in business_command_text(message) or re.search(r"\b(?:khong|chua|dung)\b.*\b(?:xac nhan|dong y|chot don|gui yeu cau)\b", text) or not re.match(r"^(?:(?:toi|minh|em)\s+)?(?:xac nhan|dong y|chot don|ok|gui yeu cau)\b", text):
            return "confirmation_not_explicit"
    if proposal.action == "cancel":
        # Model chọn hành động; code chỉ kiểm chứng căn cứ trước khi bỏ bản nháp.
        negated_cancel = re.search(r"\b(?:khong|chua|dung)\s+(?:(?:muon|can|dong y)\s+)?(?:huy|cancel)\b", business_evidence)
        cancel_evidence = re.search(
            r"\b(?:huy|cancel|bo het|xoa het|xoa toan bo)\b|"
            r"\b(?:khong(?:\s+(?:muon|can))?|dung)\s+(?:dat|mua|lay)\s+nua\b",
            business_evidence,
        )
        if negated_cancel or not cancel_evidence:
            return "cancellation_not_explicit"
    if proposal.clear_slots and not re.search(r"\b(?:xoa|bo|khong can|khong muon|huy)\b", business_evidence):
        return "ungrounded_clear"
    pending_remove = bool(conversation and conversation.get("pending_order_request")
        and conversation["pending_order_request"]["operation"] == "remove_product"
        and conversation["pending_order_request"]["revision"] == conversation["order"]["revision"]
        and proposal.continuation == "order")
    if proposal.order_operation == "remove_product" and not pending_remove and not re.search(r"\b(?:xoa|bo|bot|giam|khong can|khong muon|huy)\b", business_evidence):
        return "ungrounded_remove"
    return None


def catalog_group_evidence(message, products):
    """Đối chiếu loại từ tên nguồn, không làm mất cà phê muối khi kiểm chứng nhóm."""
    aliases = {alias: product.get("product_type") for product in products
               for alias in [product["name"], *product["aliases"]]}
    return mentioned_catalog_groups(message, named_groups=aliases)


def check_catalog_grounding(message: str, proposal, repository) -> str | None:
    """Phát hiện model bỏ tên nguồn trong câu; chỉ từ chối/sửa, không thay intent."""
    all_mentions = [*proposal.product_mentions, *proposal.order_product_mentions,
                    *(item.product_mention for item in proposal.order_items if item.product_mention)]
    for request in proposal.requests:
        all_mentions.extend(request.product_mentions)
        all_mentions.extend(request.excluded_product_mentions)
    excluded = {}
    for request in proposal.requests:
        for intent in request.intents:
            excluded.setdefault(intent, set()).update(normalize_text(m) for m in request.excluded_product_mentions)
    for request in proposal.requests:
        if any(set(normalize_text(m) for m in request.product_mentions) & excluded.get(intent, set()) for intent in request.intents):
            return "contradictory_included_and_excluded_query_targets"
    result = safe_search_products(repository, {})
    if result["status"] == "error":
        return None  # Controller xử lý lỗi nguồn riêng, không gọi là lỗi model.
    expected_groups = catalog_group_evidence(message, result["products"])
    if len(expected_groups) >= 2 and "recommendation" in proposal.intents:
        # Chỉ bác bỏ thiếu ngân sách tổng rõ ràng, không tự gán intent/budget.
        money = budget_evidence(message)
        from app.text_utils import APPROXIMATE_BUDGET_CUE
        shared_budget = (len(money["values"]) == 1 and re.search(
            r"\b(?:ngan sach|tong(?: cong| tien)?|chi co|(?:toi|minh|t) (?:co|con)|"
            + APPROXIMATE_BUDGET_CUE + r")\b", normalize_shopping_terms(message)))
        if shared_budget and proposal.bundle_budget is None:
            return "missing_bundle_budget"
        covered = {request.filters.product_type for request in proposal.requests
                   if "recommendation" in request.intents}
        if not expected_groups.issubset(covered):
            return "missing_catalog_group_request"
    if result["status"] != "success":
        return None  # Empty vẫn kiểm tra đủ nhóm, không tự xác nhận sản phẩm.
    raw = normalize_text(business_command_text(message))
    mentions = [normalize_text(x) for x in all_mentions]
    if "order_request" in proposal.intents and proposal.updates.cake_need:
        mentions.append(normalize_text(proposal.updates.cake_need))
    if proposal.intents == ["recommendation"] and proposal.updates.flavor:
        mentions.append(normalize_text(proposal.updates.flavor))
    relevant = {"price", "size", "flavor", "availability", "recommendation", "order_request", "allergen", "topping", "storage", "description"}
    if not relevant.intersection(proposal.intents):
        return None
    for product in result["products"]:
        product_terms = {normalize_text(x) for x in [product["name"], *product["aliases"]]}
        for term in [product["name"], *product["aliases"]]:
            normalized = normalize_text(term)
            represented = any(normalized in mention or mention in product_terms for mention in mentions)
            if normalized == "tra sua" and any(
                    r.intents == ["recommendation"] and r.filters.taste_family == "milk_tea"
                    and r.filters.product_type == "tea" and not r.product_mentions for r in proposal.requests):
                represented = True
            matched = re.search(r"(?<!\w)" + re.escape(normalized) + r"(?!\w)", raw)
            if matched and not represented:
                for request in proposal.requests:
                    # Tên dạng "cà phê đen"/"trà đào" có thể được AI biểu diễn
                    # đầy đủ bằng nhóm + vị tương đương (black = đen).
                    # Chỉ chấp nhận khi toàn bộ phần tên còn lại khớp, không
                    # bỏ qua tên riêng hoặc làm việc này cho yêu cầu đặt món.
                    if (request.intents == ["recommendation"] and not request.product_mentions
                            and request.filters.product_type in {"tea", "coffee"} and request.filters.flavor):
                        base = "cà phê" if request.filters.product_type == "coffee" else "trà"
                        remaining_name = canonical_flavors(term) - canonical_flavors(base)
                        if remaining_name and remaining_name == canonical_flavors(request.filters.flavor):
                            represented = True
            if matched and not represented:
                return "missing_catalog_mention"
            # Bác bỏ thiếu/gán sai câu hỏi vị có liên kết tên rõ ràng.
            # Đây là kiểm chứng output Qwen, không tự tạo intent/slot hay câu trả lời.
            if matched and proposal.requests:
                before, after = raw[:matched.start()], raw[matched.end():]
                clause_before = re.split(r"[,.;]", before)[-1].strip()
                preposed = re.fullmatch(
                    r"(?:huong vi|(?:hoi|xem|cho (?:toi|minh|em) biet) (?:huong )?vi)(?:\s+cua)?",
                    clause_before)
                negated = re.search(r"\b(?:khong|chua|dung)(?:\s+(?:can|muon))?\s+hoi\s*$", before)
                explicit_flavor_question = (not negated and (
                    preposed or re.match(r"\s+(?:(?:co|la)\s+)?(?:huong\s+)?vi\s+(?:gi|nao)\b", after)))
                linked = any("flavor" in request.intents
                             and any(normalize_text(name) in product_terms for name in request.product_mentions)
                             for request in proposal.requests)
                if explicit_flavor_question and not linked:
                    return "missing_catalog_flavor_question"
                explicit_stock_question = (not negated and re.match(
                    r"\s+con(?:\s+(?:hang|ban|banh))?\s+(?:khong|ko|k)\b", after))
                stock_linked = any("availability" in request.intents
                                   and any(normalize_text(name) in product_terms for name in request.product_mentions)
                                   for request in proposal.requests)
                if explicit_stock_question and not stock_linked:
                    return "missing_catalog_availability_question"
    return None


def resolve_pickup_phrase(phrase: str, now=None, pending_date: str | None = None) -> tuple[str | None, str | None]:
    """Trả (YYYY-MM-DD HH:MM, ngày chờ giờ). 'Chiều mai' không tự chọn giờ."""
    from datetime import datetime, timedelta
    from app.order_service import LOCAL_ZONE, local_now
    now = (now or local_now()).astimezone(LOCAL_ZONE)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", phrase.strip()):
        return phrase.strip(), None
    text = normalize_text(phrase)
    day = None
    if re.search(r"\bngay kia\b", text):
        day = (now.date() + timedelta(days=2)).isoformat()
    elif re.search(r"\bmai\b", text):
        day = (now.date() + timedelta(days=1)).isoformat()
    elif re.search(r"\bhom nay\b", text):
        day = now.date().isoformat()
    elif re.search(r"\d{4}-\d{2}-\d{2}", text):
        day = re.search(r"\d{4}-\d{2}-\d{2}", text)[0]
        datetime.strptime(day, "%Y-%m-%d")
    elif pending_date:
        day = pending_date
    clock = re.search(r"\b(\d{1,2})(?::(\d{2})|\s*(?:h|gio)(?:\s*(\d{2}))?)\b", text)
    if day and clock:
        hour, minute = int(clock[1]), int(clock[2] or clock[3] or 0)
        if 1 <= hour <= 11 and re.search(r"\b(?:chieu|toi)\b", text):
            hour += 12
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("Giờ nhận không hợp lệ.")
        return f"{day} {hour:02d}:{minute:02d}", None
    if day:
        return None, day
    raise ValueError("Ngày chưa rõ: dùng YYYY-MM-DD HH:MM, hoặc nói rõ ngày và giờ.")


def apply_cart_operation(message, draft, proposal, product_ids, repository, pending=None):
    """Áp dụng thêm/bỏ/cập nhật một món trên bản sao; không thực hiện tool."""
    from app.order_flow import ITEM_FIELDS, order_items
    from app.schemas import TurnUpdates
    updated = deepcopy(draft)
    updated.setdefault("extra_items", [])
    slots = updated["slots"]
    changes = proposal.updates.model_dump(exclude_none=True)
    operation = proposal.order_operation
    all_items = order_items(updated)
    target = product_ids[0] if len(product_ids) == 1 else None
    matches = [i for i, item in enumerate(all_items) if target and item["product_id"] == target]
    if len(product_ids) > 1:
        raise ValueError("Hãy thêm từng loại bánh để mình hỏi đúng số lượng cho từng món.")
    index = matches[0] if len(matches) == 1 else None
    if operation == "add_product" and (slots["product_id"] or slots["cake_need"]):
        quantity = changes.get("quantity")
        if quantity is not None and (type(quantity) is not int or quantity <= 0):
            raise ValueError("Số lượng thêm phải là số nguyên dương.")
        if index is not None:
            item = slots if index == 0 else updated["extra_items"][index - 1]
            if quantity is None or item["quantity"] is None:
                raise ValueError("Bạn muốn thêm bao nhiêu bánh? Mình chưa tự cộng số lượng.")
            if any(k in changes for k in ("size", "toppings", "cake_text")):
                raise ValueError("Thêm cùng loại với lựa chọn khác cần tư vấn; chưa tự gộp món.")
            item["quantity"] += quantity
        else:
            name = None
            if target:
                result = repository.get_product(target)
                if result["status"] != "success":
                    raise ValueError("Chưa đối chiếu được sản phẩm cần thêm.")
                name = result["product"]["name"]
            if not target and not proposal.product_mentions:
                raise ValueError("Bạn muốn thêm loại bánh nào?")
            item = {k: deepcopy(changes.get(k)) for k in ITEM_FIELDS}
            item.update(product_id=target, cake_need=None if target else ", ".join(proposal.product_mentions),
                        name=name, verification={k: "unverified" for k in ITEM_FIELDS})
            updated["extra_items"].append(item)
        # Ngày nhận/liên hệ là thông tin dùng chung, vẫn qua validation cũ.
        shared = {k: v for k, v in changes.items() if k not in ITEM_FIELDS}
        if shared:
            clean = proposal.model_copy(deep=True)
            clean.product_mentions, clean.clear_slots = [], []
            clean.updates = TurnUpdates(**shared)
            updated, _ = apply_turn_updates(message, updated, clean, [])
    elif operation == "remove_product":
        quantity = changes.get("quantity")
        if quantity is not None:
            # Bớt N cần đúng món đã đối chiếu và số lượng cũ đã biết.
            if type(quantity) is not int or quantity <= 0:
                raise ValueError("Số lượng bớt phải là số nguyên dương.")
            if index is None:
                raise ValueError("Bạn muốn bớt món nào? Chưa đối chiếu được món trong bản nháp.")
            item = slots if index == 0 else updated["extra_items"][index - 1]
            old_quantity = item.get("quantity")
            if type(old_quantity) is not int or old_quantity <= 0:
                raise ValueError("Chưa biết số lượng đang có; hãy nêu lại số lượng trước khi bớt.")
            if quantity > old_quantity:
                raise ValueError("Số lượng bớt lớn hơn số lượng trong bản nháp; chưa thay đổi.")
            full_remove = quantity == old_quantity
            if not full_remove:
                item["quantity"] = old_quantity - quantity
        else:
            full_remove = True
            if index is None:
                if updated["extra_items"] or product_ids:
                    raise ValueError("Bạn muốn bỏ món nào? Bản nháp chưa thay đổi.")
                # Giữ cách bỏ món duy nhất chưa có ID ở empty mode.
                index = 0
        if full_remove:
            if index == 0 and updated["extra_items"]:
                replacement = updated["extra_items"].pop(0)
                for key in ITEM_FIELDS:
                    slots[key] = deepcopy(replacement.get(key))
            elif index == 0:
                # Xóa món cuối cũng xóa số lượng và các lựa chọn phụ thuộc.
                for key in ITEM_FIELDS:
                    slots[key] = None
            else:
                updated["extra_items"].pop(index - 1)
        shared = {k: v for k, v in changes.items() if k not in ITEM_FIELDS}
        if shared:
            clean = proposal.model_copy(deep=True)
            clean.product_mentions, clean.order_product_mentions, clean.clear_slots = [], [], []
            clean.updates = TurnUpdates(**shared)
            updated, _ = apply_turn_updates(message, updated, clean, [])
    elif updated["extra_items"] and operation == "select_product":
        raise ValueError("Bản nháp có nhiều món. Hãy nói rõ bỏ món cũ và thêm món mới.")
    else:
        if (index is None and pending and not product_ids and not proposal.product_mentions
                and proposal.reference == "none" and (proposal.continuation == "order"
                    or operation == "update_slots" and pending["field"] in changes)):
            index = pending.get("item_index", 0)
        if index is not None and index > 0:
            item = updated["extra_items"][index - 1]
            for key in ITEM_FIELDS:
                if key in changes:
                    if key == "quantity" and (type(changes[key]) is not int or changes[key] <= 0):
                        raise ValueError("Số lượng phải là số nguyên dương.")
                    if key not in {"product_id", "cake_need"}:
                        item[key] = deepcopy(changes[key])
            for key in proposal.clear_slots:
                if key in ITEM_FIELDS and key not in {"product_id", "cake_need"}:
                    item[key] = None
            clean = proposal.model_copy(deep=True)
            clean.product_mentions, clean.order_product_mentions, clean.clear_slots = [], [], []
            clean.updates = TurnUpdates(**{k: v for k, v in changes.items() if k not in ITEM_FIELDS})
            updated, _ = apply_turn_updates(message, updated, clean, [])
        else:
            return apply_turn_updates(message, updated, proposal, product_ids)
    updated.update(state="COLLECTING", review=None, revision=max(updated["revision"], draft["revision"] + 1),
                   verification={key: "unverified" for key, value in updated["slots"].items() if value is not None},
                   issues=[], submission=None)
    for item in updated["extra_items"]:
        item["verification"] = {key: "unverified" for key in ITEM_FIELDS if item.get(key) is not None}
    return updated, True


def without_disabled_order_fields(proposal, draft: dict):
    """Bỏ đề xuất cho trường đã tắt, không đụng giá trị cũ trong bản nháp."""
    disabled = draft.get("disabled_fields", [])
    if not disabled:
        return proposal
    clean = proposal.model_copy(deep=True)
    clean.updates = clean.updates.model_copy(update={field: None for field in disabled})
    clean.clear_slots = [field for field in clean.clear_slots if field not in disabled]
    return clean


def apply_turn_updates(message: str, draft: dict, proposal, product_ids: list[str], now=None) -> tuple[dict, bool]:
    """Áp dụng trên bản sao; một trường sai thì không trả bản cập nhật một phần."""
    updated = deepcopy(draft)
    updates = proposal.updates.model_dump(exclude_none=True)
    if proposal.order_operation == "remove_product" or "product" in proposal.clear_slots:
        updates.pop("cake_need", None)
    changed = False
    if len(product_ids) > 1:
        raise ValueError("Demo hỗ trợ một sản phẩm mỗi bản nháp. Hãy chọn một bánh; không bỏ bánh thứ hai.")
    if product_ids and updated["slots"]["product_id"] != product_ids[0]:
        updated = update_slot(updated, "product_id", product_ids[0], now)
        changed = True
        # Đổi sản phẩm phải chọn lại size/topping; không mang lựa chọn cũ sang bánh khác.
        updated["slots"]["size"] = None
        updated["slots"]["toppings"] = None
        updated["slots"]["cake_need"] = None
    elif proposal.product_mentions and not product_ids and proposal.order_operation != "remove_product" and "product" not in proposal.clear_slots:
        updated["slots"]["product_id"] = None
        updated["slots"]["size"] = None
        updated["slots"]["toppings"] = None
        updates.setdefault("cake_need", ", ".join(proposal.product_mentions))
        changed = True
    for field in proposal.clear_slots:
        target = "product_id" if field == "product" else field
        if target in updated.get("disabled_fields", []):
            continue
        if target in updated["slots"]:
            updated["slots"][target] = None
            changed = True
            if field == "product":
                updated["slots"]["cake_need"] = None
                updated["slots"]["size"] = None
                updated["slots"]["toppings"] = None
            if field == "pickup_at":
                updated.pop("pending_pickup_date", None)
    for field, value in updates.items():
        if field not in updated["slots"] or field in updated.get("disabled_fields", []):
            continue
        if field == "pickup_at":
            value, pending = resolve_pickup_phrase(value, now, updated.get("pending_pickup_date"))
            if pending:
                updated["pending_pickup_date"] = pending
                updated["slots"]["pickup_at"] = None
                changed = True
                continue
            updated.pop("pending_pickup_date", None)
        if field in {"name", "phone"}:
            value = normalize_contact_value(field, value)
        if updated["slots"][field] != value:
            updated = update_slot(updated, field, value, now)
            changed = True
    if "allergens" in updates:
        updated["allergies"] = updates["allergens"]
        changed = True
    elif "allergens" in proposal.clear_slots:
        updated["allergies"] = []
        changed = True
    if changed:
        # Các clear hoặc ngày chờ giờ cũng phải làm tăng revision.
        if updated["revision"] == draft["revision"]:
            updated["revision"] += 1
        updated.update(state="COLLECTING", review=None,
                       verification={field: "unverified" for field, value in updated["slots"].items() if value is not None},
                       issues=[], submission=None)
    return updated, changed
