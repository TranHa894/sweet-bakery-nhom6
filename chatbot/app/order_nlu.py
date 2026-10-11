"""Cầu nối đề xuất Qwen → slot: kiểm tra câu gốc, không xác nhận/gọi tool."""

from copy import deepcopy
import re

from app.handoff import detect_handoff
from app.order_flow import FIELD_NAMES, business_command_text, collect_instructions, update_slot
from app.schemas import LLMOrderSlots
from app.text_utils import normalize_text, phrase_spans

CONTROL_MESSAGES = {"đặt bánh", "đặt hàng", "bắt đầu đặt bánh", "xem lại", "xác nhận",
                    "hủy", "hủy đơn", "hủy đặt bánh", "ok", "đồng ý"}
NUMBER_WORDS = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5,
                "sau": 6, "bay": 7, "tam": 8, "chin": 9, "muoi": 10}


def should_extract_order(message: str, draft: dict, nlu: dict) -> bool:
    """Chỉ câu có thông tin; field:value/lệnh/handoff giữ nhánh code cũ."""
    text = normalize_text(business_command_text(message))
    if text in {normalize_text(value) for value in CONTROL_MESSAGES} or detect_handoff(business_command_text(message)):
        return False
    field = re.match(r"\s*(?:sửa\s+|sua\s+)?([^:]+):", message, re.I)
    if field and normalize_text(field.group(1)) in FIELD_NAMES:
        return False
    starting = "order_request" in nlu["intents"] and bool(re.match(
        r"^(?:(?:toi|minh)\s+)?(?:(?:muon|can)\s+)?(?:dat|mua|lay)\b", text))
    if starting:
        return True
    if draft["submission"] or draft["state"] not in {"COLLECTING", "REVIEW"}:
        return False
    # Câu hỏi tư vấn/chính sách vẫn do controller cũ xử lý.
    if set(nlu["intents"]) & {"policy", "greeting", "price", "availability", "recommendation"}:
        return False
    return True


def contains_unsafe_contact(message: str) -> bool:
    """Không gửi số điện thoại/email thật hoặc trường contact không nhãn giả vào AI."""
    text = re.sub(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", "", message)
    if re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\w)(?:\+84|0)\d[\d .-]{7,}\d(?!\w)", text):
        return True
    normalized = normalize_text(text)
    for marker, prefix in [(r"\bten\s+(?:la\s+)?", "demo"),
                           (r"\bdia chi\s+(?:la\s+)?", "demo"),
                           (r"\b(?:sdt|dien thoai)\s+(?:la\s+)?", "test")]:
        match = re.search(marker, normalized)
        if match and not normalized[match.end():].startswith(prefix):
            return True
    return False


def check_order_proposal(message: str, nlu: dict, proposal: LLMOrderSlots) -> str | None:
    """Grounding cơ bản: giá trị phải có căn cứ câu hiện tại, không copy context."""
    text = normalize_text(message)
    if proposal.needs_clarification or nlu["requires_clarification"] or len(nlu["product_ids"]) > 1 or len(proposal.product_mentions) > 1:
        return "ambiguous_order_slots"
    for mention in proposal.product_mentions:
        if not phrase_spans(text, mention):
            return "invalid_order_grounding"
    for field in ("cake_need", "size", "name", "phone", "address"):
        value = getattr(proposal, field)
        if value and not phrase_spans(text, value):
            return "invalid_order_grounding"
    if proposal.size and not re.search(r"\b(?:size|cm|kich thuoc|co)\b", text):
        return "invalid_order_grounding"
    if proposal.quantity is not None:
        number = r"\d+|mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi"
        candidates = re.findall(rf"\b({number})\s+(?:banh|cai|chiec|hop)\b", text)
        candidates += re.findall(rf"\bso luong\s+(?:(?:len|la|thanh)\s+)?({number})\b", text)
        values = {int(value) if value.isdigit() else NUMBER_WORDS[value] for value in candidates}
        if proposal.quantity not in values:
            return "invalid_order_grounding"
    if proposal.toppings is not None:
        if proposal.toppings and ("topping" not in text or any(not phrase_spans(text, item) for item in proposal.toppings)):
            return "invalid_order_grounding"
        if not proposal.toppings and not re.search(r"khong\s+(?:(?:can|lay|them|co)\s+)?topping|topping\s+khong", text):
            return "invalid_order_grounding"
    if proposal.cake_text is not None:
        if proposal.cake_text and (not re.search(r"\bchu\b", text) or proposal.cake_text not in message):
            return "invalid_order_grounding"
        if proposal.cake_text == "" and not re.search(r"khong\s+(?:(?:viet|ghi)\s+)?chu|chu\s+khong", text):
            return "invalid_order_grounding"
    if proposal.pickup_at and proposal.pickup_at not in message:
        return "invalid_order_grounding"
    if proposal.fulfillment == "pickup" and not re.search(r"\b(?:cua hang|tu lay|den lay)\b", text):
        return "invalid_order_grounding"
    if proposal.fulfillment == "delivery" and not re.search(r"\b(?:giao|ship)\b", text):
        return "invalid_order_grounding"
    if nlu["quantity"] is not None and proposal.quantity is not None and nlu["quantity"] != proposal.quantity:
        return "invalid_order_grounding"
    return None


def reject_order_proposal(draft: dict, error: str) -> tuple[dict, str, str]:
    updated = deepcopy(draft)
    updated.update(state="COLLECTING", review=None)
    return updated, "Chưa ghi nhận thay đổi từ AI; hãy nêu từng bánh và thông tin rõ hơn, hoặc dùng trường: giá trị. " + collect_instructions(updated), error


def apply_order_proposal(message: str, draft: dict, nlu: dict, proposal: LLMOrderSlots) -> tuple[dict, str, str | None]:
    """Áp dụng nguyên lượt hoặc từ chối; không sửa input, REVIEW cũ bị bỏ."""
    error = check_order_proposal(message, nlu, proposal)
    if error:
        return reject_order_proposal(draft, error)
    changes = {key: value for key, value in proposal.model_dump().items()
               if key not in {"product_mentions", "needs_clarification"} and value is not None}
    # Model không được trả ID. Chỉ NLU lấy ID từ tên/alias repository đã đối chiếu.
    if proposal.product_mentions:
        if len(nlu["product_ids"]) == 1:
            changes["product_id"] = nlu["product_ids"][0]
        elif "cake_need" not in changes:
            changes["cake_need"] = proposal.product_mentions[0]
    if changes.get("cake_need") and len(nlu["product_ids"]) == 1:
        changes["product_id"] = nlu["product_ids"][0]
    updated = deepcopy(draft)
    if changes.get("cake_need") is not None or changes.get("product_id") is not None:
        # Chọn bánh mới không giữ product_id cũ khi nguồn chưa tìm được tên mới.
        updated["slots"]["product_id"] = None
    try:
        for key, value in changes.items():
            updated = update_slot(updated, key, value)
    except ValueError as exception:
        rejected, body, error = reject_order_proposal(draft, "invalid_order_slots")
        return rejected, str(exception) + " " + body, error
    if not changes:
        return reject_order_proposal(draft, "no_order_slots")
    return updated, "Mình đã ghi nhận thông tin bạn vừa nêu; các lựa chọn vẫn cần đối chiếu với nguồn. " + collect_instructions(updated), None


def merge_order_extraction(handled, draft: dict, message: str, nlu: dict, extraction: dict | None):
    """Giữ kết quả FSM; thêm slot AI nếu có, tuyệt đối không tự REVIEW/submit."""
    if extraction is None:
        return handled, None
    base = handled[0] if handled else draft
    if base["state"] not in {"COLLECTING", "REVIEW"} or base["submission"]:
        return handled, None
    if extraction["error"]:
        updated, body, error = reject_order_proposal(base, extraction["error"])
    else:
        updated, body, error = apply_order_proposal(message, base, nlu, extraction["data"])
    return (updated, body), error


def resolve_mentions(mentions: list[str], repository, shown: list[dict], reference: str, selected_id=None, focus_ids=None) -> dict:
    """ID chỉ từ repository hoặc thẻ đã lấy từ repository. Không đoán alias trùng."""
    result = repository.search_products({})
    if result["status"] != "success":
        return {"status": result["status"], "ids": [], "ambiguous": False, "error": result["error"]}
    products = result["products"]
    by_id = {p["id"]: p for p in products}
    ids = []
    unresolved = []
    ambiguous = False
    for mention in mentions:
        text = normalize_text(mention)
        short = re.sub(r"^(?:banh\s+)?(?:kem\s+)?", "", text)
        exact = [p["id"] for p in products if text == normalize_text(p["id"]) or
                 any(text == normalize_text(x) or short == normalize_text(x) for x in [p["name"], *p["aliases"]])]
        if not exact:
            matches = repository.search_products({"query": mention})
            if matches["status"] == "error":
                return {"status": "error", "ids": [], "ambiguous": False, "error": matches["error"]}
            exact = [p["id"] for p in matches["products"]]
        if len(exact) > 1:
            ambiguous = True
        elif exact:
            ids.append(exact[0])
        else:
            unresolved.append(mention)
    # Tên rõ trong lượt này là phạm vi truy vấn. Không cộng thêm draft chỉ vì
    # model đồng thời trả reference=last (lỗi đã tái hiện với Qwen thật).
    if not mentions and reference != "none":
        valid = [p for p in shown if p["id"] in by_id]
        target = None
        if reference == "last":
            candidates = list(focus_ids) if focus_ids is not None else [p["id"] for p in valid]
            if selected_id:
                candidates.append(selected_id)
            candidates = list(dict.fromkeys(identifier for identifier in candidates if identifier in by_id))
            target = by_id[candidates[0]] if len(candidates) == 1 else None
        elif reference == "order":
            target = by_id.get(selected_id)
        elif reference in {"first", "second"}:
            index = 0 if reference == "first" else 1
            target = valid[index] if len(valid) > index else None
        elif reference == "cheaper":
            def price(p):
                return min((v["price_vnd"] for v in p["variants"] if v["price_vnd"] is not None), default=10**15)
            selected = by_id.get(selected_id)
            cheaper = [p for p in valid if selected is None or price(p) < price(selected)]
            target = min(cheaper, key=price) if cheaper else None
        if target is None:
            ambiguous = True
        else:
            ids.append(target["id"])
    return {"status": "success" if ids else "no_results", "ids": list(dict.fromkeys(ids)),
            "ambiguous": ambiguous, "unresolved_mentions": unresolved, "error": None}


def catalog_alias_hints(message: str, repository) -> list[str]:
    """Gợi ý từ vựng nguồn cho Qwen; không tạo intent, ID hoặc chọn đơn."""
    if repository is None:
        return []
    try:
        result = repository.search_products({})
    except Exception:
        return []
    raw = normalize_text(business_command_text(message))
    return list(dict.fromkeys(normalize_text(term) for product in result["products"]
        for term in [product["name"], *product["aliases"]]
        if re.search(r"(?<!\w)" + re.escape(normalize_text(term)) + r"(?!\w)", raw)))


def catalog_grounded_names(raw: str, repository):
    """Alias thật có trong câu cho phép tên chuẩn cùng ID; không trích intent."""
    try:
        result = repository.search_products({})
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


def check_turn_grounding(message: str, proposal, repository=None) -> str | None:
    """Kiểm tra căn cứ literal, không dùng bộ rule để thay intent Qwen."""
    raw = normalize_text(message)
    business_raw = normalize_text(business_command_text(message))
    mentions = [*proposal.product_mentions, *proposal.order_product_mentions]
    for request in proposal.requests:
        mentions.extend(request.product_mentions)
        if request.size:
            compact = normalize_text(request.size).replace(" ", "")
            digits = re.match(r"^(\d+)cm$", compact)
            if compact not in raw.replace(" ", "") and not (digits and re.search(r"\b" + digits[1] + r"\b", raw)):
                return "ungrounded_query_size"
    grounded_names = catalog_grounded_names(business_raw, repository) if repository is not None else set()
    for mention in mentions:
        if normalize_text(mention) not in business_raw:
            # Prefix bánh/kem is optional in the resolver too. A conjunction may
            # say 'bánh dâu và socola' while Qwen emits 'bánh socola'.
            short = re.sub(r"^(?:banh\s+)?(?:kem\s+)?", "", normalize_text(mention))
            literal_short = bool(short and re.search(r"(?<!\w)" + re.escape(short) + r"(?!\w)", business_raw))
            if not literal_short and grounded_names is not None and normalize_text(mention) not in grounded_names:
                return "invalid_turn_mention"
    updates = proposal.updates.model_dump(exclude_none=True)
    for field in ("cake_need", "flavor", "occasion", "name", "phone", "address"):
        if field in updates and normalize_text(updates[field]) not in business_raw:
            return "ungrounded_slot"
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
    for match in re.finditer(r"(?<!\w)(\d+(?:[.,]\d+)*)(?:\s*(k|nghin|ngan|trieu|tr))?", raw):
        value = match[1]
        unit = match[2]
        if unit:
            number = float(value.replace(",", ".")) * (1000 if unit in {"k", "nghin", "ngan"} else 1000000)
        else:
            number = float(value.replace(".", "").replace(",", ""))
        numbers.add(int(number))
    for field in ("quantity", "servings", "budget_vnd"):
        if field in updates and updates[field] not in numbers:
            return "ungrounded_number"
    for topping in updates.get("toppings", []):
        if normalize_text(topping) not in raw:
            return "ungrounded_topping"
    if "toppings" in updates and not updates["toppings"] and not re.search(r"\b(?:khong topping|khong them topping|bo topping|topping\s*:\s*khong)\b", raw):
        return "ungrounded_topping_clear"
    if "cake_text" in updates and updates["cake_text"] == "" and not re.search(r"\b(?:khong (?:viet|ghi) chu|bo chu|chu\s*:\s*khong)\b", raw):
        return "ungrounded_cake_text_clear"
    if updates.get("pickup_at"):
        phrase = normalize_text(updates["pickup_at"])
        phrase = re.sub(r"(\d{4}-\d{2}-\d{2})t", r"\1 ", phrase)
        if phrase not in raw:
            return "ungrounded_pickup_at"
    if updates.get("fulfillment"):
        pattern = r"\b(?:cua hang|pickup)\b" if updates["fulfillment"] == "pickup" else r"\b(?:giao|ship|delivery)\b"
        if not re.search(pattern, raw):
            return "ungrounded_fulfillment"
    for allergen in updates.get("allergens", []):
        if normalize_text(allergen) not in raw:
            return "ungrounded_allergen"
    if proposal.action == "confirm":
        text = normalize_text(business_command_text(message))
        if "?" in text or re.search(r"\b(?:khong|chua|dung)\b.*\b(?:xac nhan|dong y|chot don)\b", text) or not re.match(r"^(?:(?:toi|minh|em)\s+)?(?:xac nhan|dong y|chot don|ok)\b", text):
            return "confirmation_not_explicit"
    if proposal.clear_slots and not re.search(r"\b(?:xoa|bo|khong can|khong muon|huy)\b", business_raw):
        return "ungrounded_clear"
    if proposal.order_operation == "remove_product" and not re.search(r"\b(?:xoa|bo|khong can|khong muon|huy)\b", business_raw):
        return "ungrounded_remove"
    return None


def check_catalog_grounding(message: str, proposal, repository) -> str | None:
    """Phát hiện model bỏ tên nguồn trong câu; chỉ từ chối/sửa, không thay intent."""
    all_mentions = [*proposal.product_mentions, *proposal.order_product_mentions]
    for request in proposal.requests:
        all_mentions.extend(request.product_mentions)
    result = repository.search_products({})
    if result["status"] != "success":
        return None  # Controller sẽ xử lý lỗi nguồn, không gọi là lỗi model.
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
            if re.search(r"(?<!\w)" + re.escape(normalized) + r"(?!\w)", raw) and not represented:
                return "missing_catalog_mention"
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


def apply_turn_updates(message: str, draft: dict, proposal, product_ids: list[str], now=None) -> tuple[dict, bool]:
    """Áp dụng trên bản sao; một trường sai thì không trả bản cập nhật một phần."""
    updated = deepcopy(draft)
    updates = proposal.updates.model_dump(exclude_none=True)
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
    elif proposal.product_mentions and not product_ids:
        updated["slots"]["product_id"] = None
        updated["slots"]["size"] = None
        updated["slots"]["toppings"] = None
        updates.setdefault("cake_need", ", ".join(proposal.product_mentions))
        changed = True
    for field in proposal.clear_slots:
        target = "product_id" if field == "product" else field
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
        if field not in updated["slots"]:
            continue
        if field == "pickup_at":
            value, pending = resolve_pickup_phrase(value, now, updated.get("pending_pickup_date"))
            if pending:
                updated["pending_pickup_date"] = pending
                updated["slots"]["pickup_at"] = None
                changed = True
                continue
            updated.pop("pending_pickup_date", None)
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
