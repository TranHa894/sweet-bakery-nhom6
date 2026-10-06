"""Một controller cho CLI/API: Qwen hiểu mọi lượt; repository/tool kiểm soát nghiệp vụ."""

from copy import deepcopy
from contextlib import nullcontext
import re
import sqlite3
from uuid import uuid4

from app import llm_client
from app.chatbot import create_state, respond, make_response, describe_products, summarize_needs
from app.config import CHAT_MODE, CONTEXT_MAX_TURNS, OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS
from app.nlu import analyze_message
from app.repositories.catalog import safe_search_products
from app.retrieval import retrieve, make_policy_response, validate_rag_answer
from app.order_flow import (
    new_draft, handle_order_message, request_handoff, collect_instructions,
    create_review, confirm_review, missing_slots, business_command_text,
)
from app.order_nlu import resolve_mentions, check_turn_grounding, apply_turn_updates, contains_unsafe_contact
from app.storage import safe_history_text, save_conversation, record_messages
from app.text_utils import normalize_text, format_vnd
from app.schemas import CurrentTurn, InformationRequest, TurnUpdates

PRODUCT_INFORMATION_INTENTS = {"price", "size", "flavor", "availability", "allergen", "topping", "storage", "description"}


def is_information_question(proposal) -> bool:
    """Intent/action do Qwen trích; câu chỉ hỏi thông tin không sửa đơn."""
    return (proposal.action == "none" and "order_request" not in proposal.intents
            and bool((PRODUCT_INFORMATION_INTENTS | {"policy", "recommendation"}).intersection(proposal.intents)))


def new_conversation(conversation_id=None, max_turns=CONTEXT_MAX_TURNS) -> dict:
    """Mỗi khách có history/needs/order riêng; không có biến list dùng chung."""
    if type(max_turns) is not int or not 1 <= max_turns <= 20:
        raise ValueError("max_turns phải từ 1 đến 20.")
    identifier = conversation_id or str(uuid4())
    return {"id": identifier, "history": [], "needs": create_state(), "model": None,
            "max_turns": max_turns, "order": new_draft(identifier), "unknown_streak": 0,
            "shown_products": [], "conversation_context": {"focus_product_ids": [], "focus_product_terms": []}}


def finish_turn(current, message, response, storage_connection=None) -> None:
    if storage_connection is not None:
        # Parent phải có trước messages foreign key; lưu cùng transaction của cả lượt.
        save_conversation(storage_connection, current)
        record_messages(storage_connection, current["id"], message, response["text"])
    current["history"].extend([
        {"role": "user", "content": safe_history_text(message)},
        {"role": "assistant", "content": safe_history_text(response["text"])},
    ])
    current["history"] = current["history"][-2 * current["max_turns"]:]
    if storage_connection is not None:
        save_conversation(storage_connection, current)


def empty_nlu(message, intents, status="success") -> dict:
    return {"raw_text": message, "normalized_text": normalize_text(message), "intents": intents,
            "product_ids": [], "product_terms": [], "query": None, "flavors": [], "budgets_vnd": [],
            "price_inclusive": True, "servings": None, "quantity": None, "size": None,
            "requires_clarification": False, "catalog_status": status}


def response_shell(message, repository, current, intents=None) -> dict:
    try:
        caps = repository.get_capabilities()
    except Exception:
        caps = {"data_mode": "unknown", "is_mock": False, "configured": False}
    status = "unconfigured" if caps["data_mode"] == "empty" else "success"
    nlu = empty_nlu(message, intents or ["fallback"], status)
    result = {"status": status, "data_mode": caps["data_mode"], "products": [], "error": None}
    return make_response("", caps, nlu, deepcopy(current["needs"]), result)


def turn_result(current, response, *, engine="ollama", error=None, attempts=0, current_turn=None) -> dict:
    return {"conversation": current, "response": response, "engine": engine, "model": current.get("model"),
            "llm_error": error, "nlu_attempts": attempts, "phrasing_status": "not_used",
            "current_turn": current_turn}


def failed_turn(message, repository, conversation, error, attempts=0, *, source=False) -> dict:
    current = deepcopy(conversation)
    response = response_shell(message, repository, current)
    response["text"] += f"Chưa xử lý được lượt này ({error}). Bản nháp và REVIEW được giữ nguyên; chưa tạo đơn. Bạn có thể thử lại."
    if source:
        response.update(error=error, catalog_status="error")
    return turn_result(current, response, engine="source_error" if source else "llm_error",
                       error=None if source else error, attempts=attempts)


def merge_preferences(current, proposal, resolution, mode) -> dict:
    """Delta: chỉ field có giá trị mới thay đổi; clear_slots xóa rõ ràng."""
    needs = deepcopy(current["needs"])
    filters = needs["filters"]
    # Nhu cầu tư vấn là sở thích/ràng buộc, không phải phạm vi tên bánh lượt hỏi.
    # Bỏ ID/query legacy; context tham chiếu được lưu riêng, draft vẫn giữ nguyên.
    filters.pop("product_ids", None)
    filters.pop("query", None)
    needs["data_mode"] = mode
    updates = proposal.updates.model_dump(exclude_none=True)
    if is_information_question(proposal) and "recommendation" not in proposal.intents:
        # Dị ứng khách nêu rõ vẫn là ràng buộc an toàn cho các lượt tư vấn sau;
        # điều này không đổi sản phẩm/slot trong draft của một câu hỏi thông tin.
        if "allergens" in updates:
            filters["exclude_allergens"] = list(updates["allergens"])
        elif "allergens" in proposal.clear_slots:
            filters.pop("exclude_allergens", None)
        return needs
    mapping = {"budget_vnd": "max_price_vnd", "flavor": "flavor", "servings": "servings",
               "size": "size", "occasion": "occasion", "allergens": "exclude_allergens",
               "available_only": "available_only"}
    for field in proposal.clear_slots:
        if field == "product":
            filters.pop("product_ids", None)
            filters.pop("query", None)
            needs["product_terms"] = []
        elif field in mapping:
            filters.pop(mapping[field], None)
        elif field == "quantity":
            needs["quantity"] = None
    if proposal.product_mentions or proposal.reference != "none":
        if proposal.reference == "none":
            # Hỏi tên mới thay chủ đề; bộ lọc mới lấy từ đúng lượt hiện tại.
            allergens = deepcopy(filters.get("exclude_allergens"))
            filters.clear()
            if allergens and "allergens" not in proposal.clear_slots:
                filters["exclude_allergens"] = allergens
        needs["product_terms"] = list(proposal.product_mentions)
    elif "flavor" in updates:
        # Tìm theo vị/browse mới không giữ tên cũ như lỗi người dùng đã báo.
        filters.pop("query", None)
        filters.pop("product_ids", None)
        needs["product_terms"] = []
    elif "recommendation" in proposal.intents and "budget_vnd" in updates and not proposal.order_update:
        filters.pop("query", None)
        filters.pop("product_ids", None)
        needs["product_terms"] = []
    for field, target in mapping.items():
        if field in updates:
            filters[target] = updates[field]
    if "budget_vnd" in updates:
        filters["price_inclusive"] = updates.get("price_inclusive", True)
    if "quantity" in updates:
        needs["quantity"] = updates["quantity"]
    filters.pop("product_ids", None)
    filters.pop("query", None)
    return needs


def build_current_turn(current, proposal, resolution, reference) -> CurrentTurn:
    """Query độc lập: tên/tham chiếu rõ dùng filter mới; tư vấn dùng preferences."""
    scoped = bool(proposal.product_mentions) or reference != "none" or (is_information_question(proposal) and "recommendation" not in proposal.intents)
    filters = {} if scoped else deepcopy(current["needs"]["filters"])
    if resolution["ids"]:
        filters["product_ids"] = list(resolution["ids"])
    elif proposal.product_mentions:
        filters["query"] = " ".join(proposal.product_mentions)
    mapping = {"budget_vnd": "max_price_vnd", "flavor": "flavor", "servings": "servings",
               "size": "size", "occasion": "occasion", "allergens": "exclude_allergens",
               "available_only": "available_only", "price_inclusive": "price_inclusive"}
    updates = proposal.updates.model_dump(exclude_none=True)
    for field, target in mapping.items():
        if field in updates:
            filters[target] = updates[field]
    if "budget_vnd" in updates:
        filters.setdefault("price_inclusive", True)
    return {"intents": list(proposal.intents), "product_mentions": list(proposal.product_mentions),
            "reference": reference, "product_ids": list(resolution["ids"]), "filters": filters}


def has_reference_cue(message: str) -> bool:
    """Guard dùng ngữ cảnh cũ; không nhận diện intent hoặc chọn sản phẩm."""
    raw = normalize_text(business_command_text(message))
    return bool(re.search(r"\b(?:(?:banh|loai|chiec)\s+(?:do|nay|ay|vua\s+(?:roi|xem)|cu)|"
        r"vua roi|truoc do|trong don|dang dat|thu\s+(?:nhat|hai|1|2)|dau tien|re hon|re nhat|gia thap hon|no)\b", raw))


def resolve_message_scopes(current, proposal, repository, message: str = ""):
    """Giải từng yêu cầu tra cứu và mục tiêu đơn độc lập bằng repository."""
    topic = current["conversation_context"]["focus_product_ids"]
    selected = current["order"]["slots"]["product_id"]
    order_mentions = list(proposal.order_product_mentions)
    # Tương thích output cũ: chỉ dùng mentions chung khi không có request riêng.
    if not proposal.requests and not order_mentions:
        order_mentions = list(proposal.product_mentions)
    if not order_mentions and "order_request" in proposal.intents and proposal.updates.cake_need:
        # cake_need là dữ liệu Qwen đã trích; đối chiếu nguồn như mention, không
        # suy tên bằng regex hay chọn từ danh sách hints của prompt.
        order_mentions = [proposal.updates.cake_need]
    order_proposal = proposal.model_copy(deep=True)
    order_proposal.product_mentions = order_mentions
    order_reference = "none" if order_mentions else proposal.reference
    order_resolution = resolve_mentions(order_mentions, repository, current["shown_products"],
                                        order_reference, selected, topic)
    if is_information_question(proposal):
        # Câu hỏi thông tin không có mục tiêu sửa đơn, dù có ID đã giải cho query.
        order_resolution = {"status": "no_results", "ids": [], "ambiguous": False, "error": None}
    elif proposal.requests and proposal.action == "start_order" and not order_mentions and order_reference == "none":
        order_resolution["ambiguous"] = True
    requests = list(proposal.requests)
    if not requests and PRODUCT_INFORMATION_INTENTS.union({"recommendation"}).intersection(proposal.intents):
        requests = [InformationRequest(intents=[i for i in proposal.intents if i in PRODUCT_INFORMATION_INTENTS or i == "recommendation"],
            product_mentions=list(proposal.product_mentions), reference=proposal.reference)]
    # An empty child request is not permission to pull a historical product into
    # an explicitly named current question. Prefer the unique current subject.
    current_terms = list(dict.fromkeys(name for request in requests for name in request.product_mentions))
    if not current_terms:
        current_terms = list(proposal.product_mentions)
    current_ids = []
    if current_terms:
        current_resolution = resolve_mentions(current_terms,repository,current["shown_products"],"none",selected,topic)
        current_ids = current_resolution["ids"]
    explicit_reference = has_reference_cue(message)
    tasks = []
    for request in requests:
        query = proposal.model_copy(deep=True)
        query.intents = list(request.intents)
        query.product_mentions = list(request.product_mentions)
        query.action, query.order_update, query.clear_slots = "none", False, []
        query.requests, query.order_product_mentions, query.order_operation = [], [], "none"
        # Slot của đơn không làm filter của câu hỏi về bánh khác trong câu hỗn hợp.
        if proposal.requests and "order_request" in proposal.intents:
            query.updates = TurnUpdates()
        if request.size is not None:
            query.updates.size = request.size
        if "availability" in query.intents and "recommendation" not in query.intents:
            # Hỏi bánh hết/còn phải thấy cả out_of_stock/unknown, không lọc còn hàng.
            query.updates.available_only = None
        reference = "none" if request.product_mentions else request.reference
        if reference == "none" and not request.product_mentions and "recommendation" not in query.intents and is_information_question(query) and not query.updates.flavor:
            reference = "last"
        local_ambiguous = False
        if not query.product_mentions and "recommendation" not in query.intents and current_terms and not explicit_reference:
            if reference in {"none","last"} and len(current_terms) == 1:
                query.product_mentions = list(current_terms)
                reference = "none"
            else:
                local_ambiguous = True
        elif not query.product_mentions and reference not in {"none","last"} and not explicit_reference:
            local_ambiguous = True
        reference_focus = list(dict.fromkeys([*topic,*current_ids])) if reference == "last" and current_terms else topic
        resolution = resolve_mentions(query.product_mentions, repository, current["shown_products"], reference, selected, reference_focus)
        if not resolution["ids"] and resolution.get("unresolved_mentions") and all(has_reference_cue(term) for term in resolution["unresolved_mentions"]):
            local_ambiguous = True  # A reference phrase is not a verified cake name.
        if local_ambiguous:
            resolution.update(ids=[],ambiguous=True)
        scope = build_current_turn(current, query, resolution, reference)
        if not any(task["scope"] == scope for task in tasks):
            tasks.append({"proposal": query, "resolution": resolution, "scope": scope})
    scope = deepcopy(tasks[0]["scope"]) if tasks else build_current_turn(current, proposal, order_resolution, order_reference)
    scope["intents"] = list(proposal.intents)
    scope["requests"] = [deepcopy(task["scope"]) for task in tasks]
    scope["order_product_ids"] = list(order_resolution["ids"])
    if tasks:
        scope["product_ids"] = list(dict.fromkeys(identifier for task in tasks for identifier in task["scope"]["product_ids"]))
    return scope, tasks, order_proposal, order_resolution


def describe_requested_products(products, intents):
    """Chỉ diễn đạt trường nguồn cho đúng intent của từng request."""
    if "recommendation" in intents:
        return describe_products(products)
    lines = []
    for product in products:
        lines.append(f"- {product['name']} [{product['id']}]:")
        for variant in product["variants"]:
            if "price" in intents:
                price = format_vnd(variant["price_vnd"]) if variant["price_vnd"] is not None else "chưa có giá"
                lines.append(f"  • {variant['size'] or 'chưa biết size'}: {price}.")
            if "size" in intents:
                servings = f"khoảng {variant['servings']} người" if variant["servings"] else "chưa biết số người ăn"
                lines.append(f"  • Size {variant['size'] or 'chưa biết'}; {servings}.")
            if "availability" in intents:
                labels = {"in_stock": "còn hàng", "out_of_stock": "hết hàng", "preorder": "cần đặt trước", "unknown": "chưa biết tình trạng còn hàng"}
                lines.append(f"  • {variant['size'] or 'chưa biết size'}: {labels[variant['stock_status']]}.")
        if "flavor" in intents:
            lines.append("  Hương vị: " + (product["flavor"] or "chưa xác định") + ".")
    return "\n".join(lines)


def product_answer(repository, current, proposal, response, current_turn) -> None:
    result = safe_search_products(repository, current_turn["filters"], response["data_mode"])
    response.update(catalog_status=result["status"], error=result["error"])
    if result["status"] == "error":
        raise ValueError(result["error"] or "source_error")
    if current["needs"]["filters"].get("exclude_allergens") and "recommendation" in proposal.intents:
        response["text"] += "Nhu cầu có dị ứng cần nhân viên xác minh. Mình chưa đề xuất bánh như lựa chọn an toàn; dữ liệu mô phỏng không xác nhận tránh nhiễm chéo."
        current["shown_products"] = []
        return
    if result["status"] == "unconfigured":
        turn_needs = deepcopy(current["needs"])
        turn_needs.update(filters=deepcopy(current_turn["filters"]), product_terms=list(proposal.product_mentions))
        response["text"] += summarize_needs(turn_needs) + "\nChưa có menu để đối chiếu; chưa thể xác nhận bánh đáp ứng, giá hoặc còn hàng."
        return
    if result["status"] == "no_results":
        response["text"] += "Nguồn hoạt động nhưng không tìm thấy bánh/biến thể phù hợp. Bạn có thể điều chỉnh ngân sách, size hoặc sở thích; mình không tự tạo sản phẩm."
        current["shown_products"] = []
        return
    # Trả đủ các bánh được hỏi rõ; browse chung vẫn giới hạn 5 thẻ.
    shown = result["products"] if current_turn["product_ids"] else result["products"][:5]
    current["shown_products"] = deepcopy(shown)
    response["products"] = shown
    response["text"] += describe_requested_products(shown, proposal.intents)
    for product in shown:
        if "topping" in proposal.intents:
            options = product.get("topping_options")
            response["text"] += "\n" + product["name"] + " — topping: " + (
                "; ".join(t["name"] + " +" + format_vnd(t["price_vnd"]) + "/bánh" for t in options) if options
                else "không có lựa chọn topping đã xác minh trong nguồn."
            )
        if "allergen" in proposal.intents:
            info = product.get("allergen_info")
            response["text"] += "\n" + product["name"] + " — allergen: " + (
                info["status"] + "; " + ", ".join(info["items"]) + ". " + info.get("note", "")
                if info else "chưa xác định; cần nhân viên xác minh."
            )
        if "storage" in proposal.intents:
            response["text"] += "\n" + product["name"] + " — " + product.get("storage", "Chưa có thông tin bảo quản.")
            if product.get("shelf_life_hours") is not None:
                response["text"] += f" Hạn dùng mẫu: {product['shelf_life_hours']} giờ."
        if "description" in proposal.intents:
            response["text"] += "\n" + product["description"]
    if len(result["products"]) > len(shown):
        response["text"] += f"\nHiển thị {len(shown)}/{len(result['products'])} sản phẩm phù hợp; bạn có thể lọc thêm."
    response["text"] += "\nTất cả sản phẩm/giá/tình trạng trên là MÔ PHỎNG." if response["is_mock"] else ""


def advance_order(current, proposal, resolution, message, tools) -> str:
    """Qwen đề xuất; hàm này áp dụng quy tắc FSM, không parse keyword thay Qwen."""
    draft = current["order"]
    if is_information_question(proposal):
        # Cờ order_update riêng lẻ không đủ để biến câu hỏi giá/bảo quản thành sửa đơn.
        # Dị ứng nghiêm trọng/yêu cầu nhân viên vẫn được xử lý như trước.
        if proposal.handoff_reason == "none" and not proposal.updates.allergens and not current["needs"]["filters"].get("exclude_allergens") and not draft.get("allergies"):
            return ""
    slot_updates = {k: v for k, v in proposal.updates.model_dump(exclude_none=True).items() if k in draft["slots"]}
    edit_with_consent = proposal.action in {"confirm", "review"} and bool(proposal.order_operation != "none" or slot_updates or proposal.clear_slots or (
        resolution["ids"] and resolution["ids"] != [draft["slots"]["product_id"]]
    ))
    reason = proposal.handoff_reason if proposal.handoff_reason != "none" else None
    if proposal.action == "handoff" and reason is None:
        reason = "customer_requested"
    if proposal.updates.allergens or current["needs"]["filters"].get("exclude_allergens") or (
        draft.get("allergies") and "allergens" not in proposal.clear_slots
    ):
        reason = reason or "allergen_requires_staff"
    if reason:
        current["order"], text = request_handoff(draft, tools, reason, current["needs"])
        return text
    if draft["submission"] and draft["submission"]["confirmed"]:
        if proposal.action == "confirm" and not proposal.order_update and not edit_with_consent:
            current["order"], text = confirm_review(draft, tools, current["needs"])
            return text
        if proposal.action == "cancel" or proposal.order_update or proposal.order_operation != "none" or edit_with_consent:
            current["order"], text = request_handoff(draft, tools, "change_confirmed_order", current["needs"])
            return text
    if proposal.action == "cancel":
        draft = deepcopy(draft)
        draft.update(state="CANCELLED", review=None)
        current["order"] = draft
        return "Đã hủy bản nháp, không tạo đơn."
    editing = proposal.order_update or proposal.order_operation != "none" or proposal.action == "start_order" or edit_with_consent or (
        "order_request" in proposal.intents and bool(slot_updates or proposal.product_mentions or proposal.clear_slots)
    )
    if editing:
        if proposal.order_operation == "remove_product":
            proposal = proposal.model_copy(deep=True)
            if "product" not in proposal.clear_slots:
                proposal.clear_slots.append("product")
            resolution = {**resolution, "ids": []}
        if len(resolution["ids"]) > 1 or len(proposal.product_mentions) > 1:
            return "Demo hỗ trợ một sản phẩm mỗi bản nháp. Bạn hãy chọn một bánh trước; mình chưa ghi nhận hoặc bỏ qua bánh nào."
        if draft["state"] in {"CANCELLED", "HANDOFF", "DEMO_CONFIRMED"}:
            if proposal.action != "start_order":
                return "Bản nháp đã kết thúc/chuyển tư vấn. Hãy bắt đầu yêu cầu đặt bánh mới."
            draft = new_draft(current["id"])
        draft = deepcopy(draft)
        draft["state"] = "COLLECTING" if draft["state"] == "BROWSING" else draft["state"]
        try:
            draft, changed = apply_turn_updates(message, draft, proposal, resolution["ids"])
        except ValueError as exception:
            return "Chưa ghi nhận thay đổi: " + str(exception) + " Bản nháp trước được giữ nguyên."
        current["order"] = draft
        if draft.get("pending_pickup_date"):
            return f"Mình ghi nhận ngày {draft['pending_pickup_date']} theo giờ Việt Nam. Bạn muốn nhận lúc mấy giờ? Chưa tự chọn giờ và chưa xác nhận đơn."
        if not missing_slots(draft["slots"]):
            current["order"], text = create_review(draft, tools)
            if current["order"].get("review") and current["order"]["review"]["mode"] == "local_demo" and any(
                issue in current["order"]["issues"] for issue in {"availability_unverified", "lead_time_unverified", "cake_text_limit_unverified", "allergen_requires_staff"}
            ):
                current["order"], ticket_text = request_handoff(current["order"], tools, "needs_verification", current["needs"])
                return text + "\n" + ticket_text
            if proposal.action == "confirm" or changed:
                text += "\nThông tin vừa thay đổi: cần đồng ý rõ ràng với REVIEW mới."
            return text
        return collect_instructions(draft)
    if proposal.action == "review":
        current["order"], text = create_review(draft, tools)
        return text
    if proposal.action == "confirm":
        current["order"], text = confirm_review(draft, tools, current["needs"])
        return text
    return ""


def handle_message(message, repository, conversation, *, chat_mode=CHAT_MODE, base_url=OLLAMA_BASE_URL,
                   model=OLLAMA_MODEL, timeout=OLLAMA_TIMEOUT_SECONDS, knowledge_repository=None,
                   order_tools=None, storage_connection=None) -> dict:
    """Điểm gọi chung CLI/API. Ollama lỗi giữ nguyên state; rule phải chọn chủ động."""
    if chat_mode not in {"rule", "ollama"}:
        raise ValueError("chat_mode chỉ nhận rule hoặc ollama.")
    current = deepcopy(conversation)
    current.setdefault("order", new_draft(current["id"]))
    current.setdefault("shown_products", [])
    current.setdefault("conversation_context", {
        "focus_product_ids": [p["id"] for p in current["shown_products"]], "focus_product_terms": []})
    current.setdefault("unknown_streak", 0)
    current["history"] = current["history"][-2 * current["max_turns"]:]
    if chat_mode == "rule":
        return rule_turn(message, repository, current, knowledge_repository, order_tools, storage_connection)
    if contains_unsafe_contact(message):
        return failed_turn(message, repository, conversation, "fake_contact_required")
    if not current["model"] or (model and current["model"] != model):
        selected = llm_client.select_model(base_url, model, timeout)
        if selected["error"]:
            return failed_turn(message, repository, conversation, selected["error"])
        current["model"] = selected["model"]
    extraction = llm_client.extract_turn(message, current, base_url, current["model"], timeout, repository)
    attempts = extraction["attempts"]
    if extraction["error"] or extraction["data"] is None:
        return failed_turn(message, repository, conversation, extraction["error"] or "invalid_turn_json", attempts)
    proposal = extraction["data"]
    grounding = check_turn_grounding(message, proposal, repository)
    if grounding:
        return failed_turn(message, repository, conversation, grounding, attempts)
    response = response_shell(message, repository, current, list(proposal.intents))
    current_turn, query_tasks, order_proposal, order_resolution = resolve_message_scopes(current, proposal, repository, message)
    resolutions = [order_resolution, *(task["resolution"] for task in query_tasks)]
    source_error = next((r for r in resolutions if r["status"] == "error"), None)
    if source_error:
        return failed_turn(message, repository, conversation, source_error["error"] or "source_error", attempts, source=True)
    editing = proposal.order_update or proposal.order_operation != "none" or proposal.action == "start_order" or "order_request" in proposal.intents
    multiple_order_targets = editing and (len(order_resolution["ids"]) > 1 or len(order_proposal.product_mentions) > 1)
    slots = current["order"]["slots"]
    confirmed = bool(current["order"]["submission"] and current["order"]["submission"]["confirmed"])
    adding_to_existing = not confirmed and proposal.order_operation == "add_product" and bool(slots["product_id"] or slots["cake_need"])
    wrong_remove_target = proposal.order_operation == "remove_product" and bool(order_resolution["ids"]) and order_resolution["ids"] != [slots["product_id"]]
    if proposal.ambiguous or any(r["ambiguous"] for r in resolutions) or multiple_order_targets or adding_to_existing or wrong_remove_target:
        response["requires_clarification"] = True
        if multiple_order_targets:
            response["text"] += "Demo hiện hỗ trợ một sản phẩm mỗi bản nháp. Bạn hãy chọn một bánh; mình chưa ghi nhận hoặc bỏ qua bánh nào.\n"
        if adding_to_existing:
            response["text"] += "Demo chưa hỗ trợ thêm dòng bánh hoặc cộng số lượng tương đối vào bản nháp. Bạn muốn đổi loại, đặt tổng số lượng bao nhiêu, hay nhờ tư vấn? Bánh đang đặt được giữ nguyên.\n"
        if wrong_remove_target:
            response["text"] += "Bánh yêu cầu xóa không trùng bánh đang đặt. Mình chưa xóa mục nào.\n"
        keeping_slots = "Các slot bánh cũ vẫn giữ." if adding_to_existing and current["order"].get("review") else "Bản nháp chưa thay đổi."
        response["text"] += "Mình chưa xác định chắc bánh hoặc liên kết các thuộc tính. Bạn hãy chọn rõ tên/mã hoặc vị trí bánh trong kết quả. " + keeping_slots
        current = deepcopy(conversation)
        if adding_to_existing and current["order"].get("review"):
            current["order"].update(state="COLLECTING",review=None,revision=current["order"]["revision"]+1)
            response["text"] += "\nYêu cầu thêm bánh cần làm rõ: REVIEW cũ đã mất hiệu lực, chưa thể xác nhận. Các slot bánh cũ vẫn giữ."
    else:
        current["needs"] = merge_preferences(current, proposal, order_resolution, response["data_mode"])
        response["state"] = deepcopy(current["needs"])
        try:
            for task in query_tasks:
                reply = deepcopy(response)
                reply.update(text="", products=[])
                product_answer(repository, current, task["proposal"], reply, task["scope"])
                response["text"] += reply["text"] + "\n"
                response["catalog_status"] = reply["catalog_status"]
                for product in reply["products"]:
                    existing = next((p for p in response["products"] if p["id"] == product["id"]), None)
                    if existing:
                        variant_ids = {v["id"] for v in existing["variants"]}
                        existing["variants"].extend(deepcopy(v) for v in product["variants"] if v["id"] not in variant_ids)
                    else:
                        response["products"].append(deepcopy(product))
                resolution = task["resolution"]
                if resolution["ids"] and resolution.get("unresolved_mentions"):
                    response["text"] += "\nChưa tìm thấy dữ liệu cho: " + ", ".join(resolution["unresolved_mentions"]) + ". Mình chưa đủ thông tin để báo giá hoặc xác nhận bánh này."
            if query_tasks:
                focused = list(dict.fromkeys(identifier for task in query_tasks for identifier in task["resolution"]["ids"]))
                if not focused and "recommendation" in proposal.intents:
                    focused = [p["id"] for p in response["products"]]
                terms = [name for task in query_tasks for name in task["proposal"].product_mentions]
                current["shown_products"] = deepcopy(response["products"])
                current["conversation_context"] = {"focus_product_ids": focused, "focus_product_terms": terms}
            elif order_proposal.product_mentions or proposal.reference != "none":
                current["conversation_context"] = {"focus_product_ids": list(order_resolution["ids"]), "focus_product_terms": list(order_proposal.product_mentions)}
        except ValueError:
            return failed_turn(message, repository, conversation, "source_error", attempts, source=True)
        if "greeting" in proposal.intents:
            response["text"] += "\nChào bạn! Mình có thể tư vấn bánh mẫu, hỏi đáp chính sách và đặt đơn DEMO."
        if "policy" in proposal.intents:
            retrieval = retrieve(message, knowledge_repository)
            generation = None
            if retrieval["status"] == "success":
                generation = llm_client.extract_policy_answer(message, retrieval, base_url, current["model"], timeout)
                if generation["error"]:
                    return failed_turn(message, repository, conversation, generation["error"], attempts)
                validation = validate_rag_answer(generation["data"], retrieval)
                if validation:
                    return failed_turn(message, repository, conversation, validation, attempts)
            response["policy"] = make_policy_response(
                retrieval, generation["data"] if generation else None, engine="ollama",
                attempts=generation["attempts"] if generation else 0,
            )
            response["text"] += "\n" + response["policy"]["text"]
            if retrieval["status"] == "error":
                response["error"] = retrieval["error"]
        current["unknown_streak"] = current["unknown_streak"] + 1 if list(proposal.intents) == ["fallback"] else 0
    try:
        with storage_connection if storage_connection is not None else nullcontext():
            if storage_connection is not None:
                storage_connection.execute("BEGIN IMMEDIATE")
                save_conversation(storage_connection, current)
            if not response["requires_clarification"] and order_tools is not None:
                order_text = advance_order(current, order_proposal, order_resolution, message, order_tools)
                if order_text:
                    response["text"] += "\n" + order_text
                if current["unknown_streak"] >= 2:
                    current["order"], text = request_handoff(current["order"], order_tools, "two_unknown_turns", current["needs"])
                    response["text"] += "\n" + text
            if list(proposal.intents) == ["fallback"] and not response["requires_clarification"]:
                response["text"] += "\nMình chưa hiểu yêu cầu. Bạn có thể nói rõ loại bánh, nhu cầu hoặc thông tin cần hỏi."
            if response["text"].endswith("\n") and not response["requires_clarification"]:
                response["text"] += collect_instructions(current["order"]) if current["order"]["state"] == "COLLECTING" else "Bạn muốn hỏi hoặc đặt bánh nào?"
            finish_turn(current, message, response, storage_connection)
    except sqlite3.Error:
        return failed_turn(message, repository, conversation, "storage_error", attempts, source=True)
    return turn_result(current, response, engine="source_error" if response["error"] else "ollama", attempts=attempts, current_turn=current_turn)


def rule_turn(message, repository, current, knowledge_repository, tools, connection) -> dict:
    """Chế độ offline tường minh dùng lại rule/FSM cũ; không fallback tự động từ AI."""
    nlu = analyze_message(message, repository)
    response = respond(message, repository, current["needs"], nlu=nlu, include_policy_notice=False)
    try:
        with connection if connection is not None else nullcontext():
            if connection is not None:
                save_conversation(connection, current)
            handled = handle_order_message(message, current["order"], nlu, tools, current["needs"]) if tools else None
            if handled:
                current["order"], text = handled
                response["text"] = response["text"].split("\n", 1)[0] + "\n" + text
                response["products"] = []
                response["state"] = deepcopy(current["needs"])
            else:
                current["needs"] = deepcopy(response["state"])
                retrieval = retrieve(message, knowledge_repository)
                if "policy" in nlu["intents"] or (retrieval["status"] == "success" and nlu["intents"] == ["fallback"]):
                    response["policy"] = make_policy_response(retrieval)
                    response["text"] += "\n" + response["policy"]["text"]
                current["unknown_streak"] = current["unknown_streak"] + 1 if nlu["intents"] == ["fallback"] and not response["policy"] else 0
                if current["unknown_streak"] >= 2 and tools:
                    current["order"], text = request_handoff(current["order"], tools, "two_unknown_turns", current["needs"])
                    response["text"] += "\n" + text
            finish_turn(current, message, response, connection)
    except sqlite3.Error:
        return failed_turn(message, repository, current, "storage_error", source=True)
    return turn_result(current, response, engine="source_error" if response["error"] else "rule")
