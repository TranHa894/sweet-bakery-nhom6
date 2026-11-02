"""Controller cho API web và script kiểm tra: mô hình hiểu câu; repository/tool kiểm soát nghiệp vụ."""

from copy import deepcopy
from contextlib import nullcontext
import re
import json
import random
import sqlite3
from uuid import uuid4
from time import monotonic

from app import llm_client
from app.advice import resolve_advice_selection, expand_advice_selection, apply_advice_selection, advice_question, advice_summary, diverse_products, next_advice_page, save_advice_pages, more_advice_selection, MORE_ADVICE_LABEL, recommend_bundles, bundle_summary, bundle_cards
from app.chatbot import create_state, respond, make_response, describe_products, summarize_needs
from app.config import CHAT_MODE, CONTEXT_MAX_TURNS, get_llm_settings
from app.nlu import analyze_message
from app.repositories.catalog import safe_search_products
from app.repositories.mock_catalog import canonical_flavors, _matches_product_type
from app.retrieval import retrieve, make_policy_response, validate_rag_answer
from app.order_flow import (
    new_draft, handle_order_message, request_handoff, collect_instructions,
    create_review, confirm_review, missing_slots, missing_draft_slots, pending_order_slot, order_items, business_command_text, configure_order_fields,
)
from app.order_nlu import resolve_mentions, check_turn_grounding, apply_turn_updates, apply_cart_operation, without_disabled_order_fields, plural_reference_evidence
from app.storage import safe_history_text, save_conversation, record_messages
from app.text_utils import normalize_text, format_vnd
from app.schemas import CurrentTurn, InformationRequest, TurnUpdates

PRODUCT_INFORMATION_INTENTS = {"price", "size", "flavor", "availability", "allergen", "topping", "storage", "description"}

# Bộ lọc tư vấn riêng với slot đặt hàng; mọi query dùng cùng mapping.
QUERY_FILTER_MAP = {
    "budget_vnd": "max_price_vnd", "price_inclusive": "price_inclusive",
    "min_budget_vnd": "min_price_vnd", "min_price_inclusive": "min_price_inclusive",
    "product_type": "product_type", "flavor": "flavor", "servings": "servings",
    "size": "size", "occasion": "occasion", "allergens": "exclude_allergens",
    "available_only": "available_only",
    "sweetness": "sweetness", "taste_family": "taste_family", "coffee_style": "coffee_style",
}
PRICE_FILTER_KEYS = ("max_price_vnd", "price_inclusive", "min_price_vnd", "min_price_inclusive")


def apply_query_updates(filters, updates, *, new_search=False):
    """Tìm mới bỏ nhóm/vị/giá cũ; refine giữ điều kiện, dị ứng vẫn được giữ."""
    if new_search:
        for key in (*PRICE_FILTER_KEYS, "product_type", "flavor", "servings", "occasion", "size", "sweetness", "taste_family", "coffee_style"):
            filters.pop(key, None)
    if ("product_type" in updates and filters.get("product_type")
            and updates["product_type"] != filters["product_type"]):
        # Một nhóm mới không mặc nhiên mang vị/số người của nhóm cũ.
        # Điều kiện được nhắc lại rõ (kể cả tham chiếu model hiểu) vẫn giữ.
        for key in ("flavor", "servings", "occasion", "sweetness", "taste_family", "coffee_style"):
            if key not in updates:
                filters.pop(key, None)
    # Vị cụ thể, nhóm vị và kiểu cà phê là ba cách mô tả cùng sở thích.
    # Khi khách đổi cách mô tả, bỏ giá trị cũ; chỉ kết hợp nếu lượt này
    # nêu rõ cả hai. Giữ ngân sách, độ ngọt và ràng buộc dị ứng.
    taste_fields = {"flavor", "taste_family", "coffee_style"}
    if taste_fields.intersection(updates):
        for key in taste_fields.difference(updates):
            filters.pop(key, None)
    if {"budget_vnd", "min_budget_vnd"}.intersection(updates):
        for key in PRICE_FILTER_KEYS:
            filters.pop(key, None)
    for field, target in QUERY_FILTER_MAP.items():
        if field in updates:
            if field == "allergens" and not updates[field]:
                filters.pop(target, None)
            else:
                filters[target] = updates[field]
    for field, inclusive in (("budget_vnd", "price_inclusive"), ("min_budget_vnd", "min_price_inclusive")):
        if field in updates:
            filters[inclusive] = updates.get(inclusive, True)
    # Cờ biên không có cận tiền tương ứng không phải một điều kiện tìm kiếm.
    for bound, inclusive in (("max_price_vnd", "price_inclusive"), ("min_price_vnd", "min_price_inclusive")):
        if bound not in filters:
            filters.pop(inclusive, None)



def is_information_question(proposal) -> bool:
    """Intent/action do mô hình trích; câu chỉ hỏi thông tin không sửa đơn."""
    return (proposal.action == "none" and ("order_request" not in proposal.intents or proposal.order_negated)
            and bool((PRODUCT_INFORMATION_INTENTS | {"policy", "recommendation"}).intersection(proposal.intents)))


def new_conversation(conversation_id=None, max_turns=CONTEXT_MAX_TURNS) -> dict:
    """Mỗi khách có history/needs/order riêng; không có biến list dùng chung."""
    if type(max_turns) is not int or not 1 <= max_turns <= 20:
        raise ValueError("max_turns phải từ 1 đến 20.")
    identifier = conversation_id or str(uuid4())
    return {"id": identifier, "history": [], "needs": create_state(), "model": None,
            "max_turns": max_turns, "order": new_draft(identifier), "unknown_streak": 0,
            "shown_products": [], "discussion_context": {"focus_product_ids": [], "focus_product_terms": []},
            "product_choices": {"product_ids": [], "intents": [], "selection_required": False},
            "current_request": None, "pending_information_request": None, "pending_order_question": None,
            "request_memory": [], "request_sequence": 0, "pending_order_request": None}


def initialize_memory(current) -> None:
    """Nạp phiên cũ tại chỗ trong payload; không xóa history hay migration SQL."""
    legacy = current.pop("conversation_context", None)
    current.setdefault("discussion_context", legacy or {
        "focus_product_ids": [p["id"] for p in current.get("shown_products", [])], "focus_product_terms": []})
    current.setdefault("product_choices", {"product_ids": [p["id"] for p in current.get("shown_products", [])], "intents": [], "selection_required": False})
    current.setdefault("current_request", None)
    current.setdefault("pending_information_request", None)
    current.setdefault("pending_order_question", None)
    current.setdefault("request_memory", [])
    current.setdefault("request_sequence", 0)
    current.setdefault("pending_order_request", None)
    current.setdefault("advice_pending", None)
    current.setdefault("advice_page", None)
    current.setdefault("quick_replies", [])
    current["order"].setdefault("extra_items", [])


def remember_request(current, proposal, scope, needs_clarification=False) -> None:
    """Bộ nhớ theo thứ tự và theo phiên; chỉ giữ ý định/ID, không lưu liên hệ."""
    current["request_sequence"] += 1
    order_related = (("order_request" in proposal.intents and not proposal.order_negated)
                     or proposal.continuation == "order"
                     or proposal.order_operation != "none"
                     or proposal.action in {"start_order", "review", "confirm", "cancel"})
    pending = (current.get("pending_order_request") or {}) if order_related else {}
    resolved_ids = set(scope.get("order_product_ids", []))
    if not current.get("pending_order_request"):
        for previous in current["request_memory"]:
            if previous.get("status") != "awaiting_clarification" or "order_request" not in previous["intents"]:
                continue
            if proposal.action == "cancel":
                previous["status"] = "cancelled"
            elif resolved_ids.intersection(previous.get("pending_candidate_ids", [])):
                previous["status"] = "resolved"
    current["request_memory"].append({
        "sequence": current["request_sequence"], "intents": list(proposal.intents),
        "action": proposal.action, "operation": proposal.order_operation, "continuation": proposal.continuation,
        "query_product_ids": list(dict.fromkeys(i for request in scope.get("requests", []) for i in request.get("product_ids", []))),
        "order_product_ids": list(scope.get("order_product_ids", [])),
        "questions": [{"intents": list(request["intents"]),
            "mentions": list(request.get("product_mentions", [])),
            "filters": {k: v for k, v in request.get("filters", {}).items()
                        if k in {"product_type", "flavor", "min_price_vnd", "max_price_vnd", "servings"}},
            "status": request.get("status", "answered")} for request in scope.get("requests", [])[:5]],
        "pending_candidate_ids": [candidate["id"] for candidate in
                                  pending.get("candidates", [])],
        "order_mentions": list(proposal.order_product_mentions or
                               (proposal.product_mentions if "order_request" in proposal.intents else [])),
        "quantity": (pending.get("quantity") if pending
                     else current["order"]["slots"].get("quantity") if order_related else None),
        "status": "awaiting_clarification" if needs_clarification or pending else "handled",
    })
    current["request_memory"] = current["request_memory"][-8:]


def finish_turn(current, message, response, storage_connection=None) -> None:
    initialize_memory(current)
    draft = current["order"]
    current["pending_order_question"] = pending_order_slot(draft) if draft["state"] == "COLLECTING" else None
    response["text"] = response["text"].strip()
    current["quick_replies"] = list(response.get("quick_replies", []))
    # Chỉ để khôi phục giao diện; không đưa thẻ/ảnh vào prompt hoặc bản nháp.
    current["recommendation_groups"] = deepcopy(response.get("recommendation_groups", []))
    if "show_checkout" in response:
        current["checkout_visible"] = response["show_checkout"]
    contacts = [draft["slots"].get(key) for key in ("name", "phone", "address")]
    if storage_connection is not None:
        # Parent phải có trước messages foreign key; lưu cùng transaction của cả lượt.
        save_conversation(storage_connection, current)
        message_id = record_messages(storage_connection, current["id"], message, response["text"], contact_values=contacts)
        if current["recommendation_groups"]:
            cards = current.setdefault("recommendation_history", {})
            cards[str(message_id)] = deepcopy(current["recommendation_groups"])
            # Web khôi phục tối đa 100 tin; giữ tối đa 50 câu trả lời có nhóm.
            current["recommendation_history"] = dict(list(cards.items())[-50:])
    current["history"].extend([
        {"role": "user", "content": safe_history_text(message, contacts)},
        {"role": "assistant", "content": safe_history_text(response["text"], contacts)},
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


def turn_result(current, response, *, engine=None, error=None, attempts=0, current_turn=None) -> dict:
    engine = engine or current.get("llm_provider", "ollama")
    return {"conversation": current, "response": response, "engine": engine, "model": current.get("model"),
            "llm_error": error, "nlu_attempts": attempts, "phrasing_status": "not_used",
            "current_turn": current_turn}


def failed_turn(message, repository, conversation, error, attempts=0, *, source=False, http_status=None) -> dict:
    current = deepcopy(conversation)
    response = response_shell(message, repository, current)
    response["show_checkout"] = False
    notices = {
        "invalid_api_request": "Ollama chưa chấp nhận request. Kiểm tra phiên bản Ollama và cấu hình model.",
        "invalid_response": "Chưa đọc được phản hồi hợp lệ từ dịch vụ model. Bạn có thể thử lại.",
        "invalid_turn_json": "Model chưa trả kết quả đúng cấu trúc. Bạn có thể thử lại.",
        "service_unavailable": "Dịch vụ model tạm thời chưa sẵn sàng. Bạn có thể thử lại sau.",
        "model_runtime_missing": "Không khởi động được AI trên máy chủ do thiếu thành phần chạy model. Cần sửa cài đặt Ollama.",
        "content_blocked": "Dịch vụ model chưa xử lý được nội dung này. Bạn có thể diễn đạt lại.",
        "invalid_config": "Cấu hình dịch vụ model chưa hợp lệ. Cần kiểm tra cấu hình chatbot.",
        "invalid_model": "Tên model chưa hợp lệ. Cần kiểm tra cấu hình chatbot.",
        "model_not_found": "Chưa tìm thấy model local đã cấu hình. Kiểm tra ollama list và OLLAMA_MODEL.",
        "timeout": "Qwen phản hồi quá thời gian chờ. Hãy chờ rồi thử lại; đóng bớt ứng dụng nếu máy thiếu RAM.",
        "connection_error": "Không kết nối được dịch vụ model. Kiểm tra kết nối rồi thử lại.",
        "output_truncated": "Kết quả model chưa đầy đủ. Bạn có thể thử lại.",
    }
    notice = notices.get(error, "Chưa xử lý được lượt này. Bạn có thể thử lại.")
    # Chỉ đưa mã HTTP dạng số ra giao diện; không dùng body/message từ nhà cung cấp.
    valid_http_status = not source and type(http_status) is int and 400 <= http_status <= 599
    if valid_http_status:
        if error == "service_unavailable":
            notice = {
                500: "Máy chủ model trả lỗi nội bộ (HTTP 500). Cần kiểm tra trạng thái và log Ollama.",
                501: "API model chưa hỗ trợ yêu cầu này (HTTP 501). Cần kiểm tra cấu hình client.",
                502: "Cổng kết nối tới model trả lỗi (HTTP 502). Bạn có thể thử lại sau.",
                503: "Dịch vụ model tạm thời chưa sẵn sàng (HTTP 503). Bạn có thể thử lại sau.",
                504: "Máy chủ model trả lỗi quá thời gian chờ (HTTP 504). Bạn có thể thử lại.",
            }.get(http_status, f"API model trả lỗi máy chủ (HTTP {http_status}). Bạn có thể thử lại sau.")
        else:
            notice += f" (HTTP {http_status})"
    response["text"] += notice
    if current.get("order", {}).get("state") in {"COLLECTING", "REVIEW"}:
        response["text"] += " Thông tin bạn đã cung cấp được giữ nguyên; chưa gửi yêu cầu."
    response["error"] = error
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
    advice = [request.filters.model_dump(exclude_none=True) for request in proposal.requests
              if "recommendation" in request.intents]
    safety = [allergen for request in proposal.requests
              if set(request.intents) - {"policy"}
              for allergen in (request.filters.allergens or [])]
    if safety:
        updates["allergens"] = list(dict.fromkeys([*(updates.get("allergens") or []), *safety]))
    if updates.get("allergens"):
        # Một điều kiện tránh mới không tự xóa những điều kiện đã biết.
        previous = [] if "allergens" in proposal.clear_slots else filters.get("exclude_allergens", [])
        updates["allergens"] = list(dict.fromkeys([*previous, *updates["allergens"]]))
    if advice:
        # Điều kiện tra cứu cũng là nhu cầu tư vấn đã kiểm chứng của khách.
        # Nhiều truy vấn khác điều kiện không được gộp thành một sở thích sai.
        shared = dict(advice[0])
        for constraints in advice[1:]:
            shared = {key: value for key, value in shared.items()
                      if key in constraints and constraints[key] == value}
        updates = {**shared, **updates}
    mapping = QUERY_FILTER_MAP
    for field in proposal.clear_slots:
        if field == "product":
            filters.pop("product_ids", None)
            filters.pop("query", None)
            needs["product_terms"] = []
        elif field in {"budget_vnd", "min_budget_vnd"}:
            for key in PRICE_FILTER_KEYS:
                filters.pop(key, None)
        elif field in mapping:
            filters.pop(mapping[field], None)
        elif field == "quantity":
            needs["quantity"] = None
    if is_information_question(proposal) and "recommendation" not in proposal.intents:
        # Dị ứng khách nêu rõ vẫn là ràng buộc an toàn cho các lượt tư vấn sau;
        # điều này không đổi sản phẩm/slot trong draft của một câu hỏi thông tin.
        # Nếu khách bỏ điều kiện cũ rồi nêu giá trị mới cùng lượt, giữ delta mới.
        explicit = {field: updates[field] for field in proposal.clear_slots if field in updates}
        if {"budget_vnd", "min_budget_vnd"}.intersection(proposal.clear_slots):
            explicit.update({k: v for k, v in updates.items()
                if k in {"budget_vnd", "min_budget_vnd", "price_inclusive", "min_price_inclusive"}})
        apply_query_updates(filters, explicit)
        if "quantity" in explicit:
            needs["quantity"] = explicit["quantity"]
        if "allergens" in updates:
            if updates["allergens"]:
                filters["exclude_allergens"] = list(updates["allergens"])
            else:
                filters.pop("exclude_allergens", None)
        elif "allergens" in proposal.clear_slots:
            filters.pop("exclude_allergens", None)
        return needs
    query_mentions = list(proposal.product_mentions) or list(dict.fromkeys(
        name for request in proposal.requests if "recommendation" in request.intents
        and request.reference == "none" for name in request.product_mentions))
    advice_requests = [request for request in proposal.requests if "recommendation" in request.intents]
    if advice_requests and all(request.price_preference in {"cheaper_than", "more_expensive_than"}
                               for request in advice_requests):
        # Tên ở đây là mốc so giá, không phải đổi chủ đề để xóa ngân sách đã có.
        query_mentions = []
    new_search = bool(advice_requests) and all(
        request.search_scope == "new" and request.price_preference not in {"cheaper_than", "more_expensive_than"}
        for request in advice_requests)
    if ("flavor" in updates and "product_type" not in updates and not query_mentions
            and "recommendation" in proposal.intents and not new_search):
        # Câu hỏi thông tin có thể đổi chủ đề mà không đổi preferences/draft.
        # Đổi vị tiếp theo dùng nhóm đã đối chiếu của chủ đề gần nhất.
        topic = current.get("discussion_context", {})
        if "product_type" in topic:
            if topic["product_type"]:
                updates["product_type"] = topic["product_type"]
            else:
                filters.pop("product_type", None)
    if query_mentions or proposal.reference != "none":
        if proposal.reference == "none":
            # Tên mới ở câu hỏi con cũng thay chủ đề tư vấn; không đổi draft.
            allergens = deepcopy(filters.get("exclude_allergens"))
            filters.clear()
            if allergens and "allergens" not in proposal.clear_slots:
                filters["exclude_allergens"] = allergens
        needs["product_terms"] = query_mentions
    elif "flavor" in updates:
        # Tìm theo vị/browse mới không giữ tên cũ như lỗi người dùng đã báo.
        filters.pop("query", None)
        filters.pop("product_ids", None)
        needs["product_terms"] = []
    elif ("recommendation" in proposal.intents
          and {"budget_vnd", "min_budget_vnd", "product_type"}.intersection(updates)
          and not proposal.order_update):
        filters.pop("query", None)
        filters.pop("product_ids", None)
        needs["product_terms"] = []
    apply_query_updates(filters, updates, new_search=new_search)
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
    apply_query_updates(filters, proposal.updates.model_dump(exclude_none=True))
    return {"intents": list(proposal.intents), "product_mentions": list(proposal.product_mentions),
            "reference": reference, "product_ids": list(resolution["ids"]), "filters": filters}


def continue_order_request(current, proposal, message=""):
    """Nối tên do mô hình trích với thao tác đã được nhận diện ở lượt trước."""
    pending = current.get("pending_order_request")
    if (not pending or pending["revision"] != current["order"]["revision"]
            or proposal.action not in {"none", "start_order"}):
        return proposal
    names = list(proposal.product_mentions)
    if not names:
        names = list(dict.fromkeys(name for request in proposal.requests
            if request.intents == ["description"] for name in request.product_mentions))
    # Model đôi khi trả description/none cho tên trần. Chỉ nối khi TOÀN BỘ
    # tin nhắn là đúng tên mà model đã trích, không chứa câu hỏi thông tin.
    def bare_name(value):
        text = normalize_text(value)
        return text.removeprefix("banh kem ").removeprefix("banh ")
    entity_answer = (set(proposal.intents) == {"description"} and len(names) == 1
                     and bare_name(message) == bare_name(names[0]))
    reference = proposal.order_reference or proposal.reference
    if reference == "none" and len(proposal.order_items) == 1:
        reference = proposal.order_items[0].reference
    reference_answer = (reference != "none" and is_choice_only(message)
                        and not any(set(request.intents) - {"description"} for request in proposal.requests))
    flavor_answer = (proposal.continuation == "order" and proposal.updates.flavor is not None
                     and not any(set(request.intents) - {"description"} for request in proposal.requests))
    if not ((names and (proposal.continuation in {"entity", "order"} or entity_answer))
            or reference_answer or flavor_answer):
        return proposal
    result = proposal.model_copy(deep=True)
    result.intents = ["order_request"]
    result.continuation = "order"
    result.order_operation = pending["operation"]
    result.action = "start_order" if pending["operation"] == "select_product" else "none"
    result.product_mentions = names
    result.order_product_mentions = list(names)
    result.order_reference = reference if not names else "none"
    result.order_update, result.requests = True, []
    return result


def is_choice_only(message: str) -> bool:
    """Guard cho câu chỉ chọn từ danh sách; không nhận diện ý định chung."""
    raw = normalize_text(message)
    return bool(re.fullmatch(
        r"(?:(?:ca\s*(?:hai|2)|tat\s*ca|toan\s*bo)\s*(?:cac\s*)?(?:loai\s*banh|banh|loai|cai|chiec)?"
        r"|(?:banh|loai|chiec)?\s*(?:thu\s*(?:nhat|hai|1|2)|dau\s*tien))"
        r"(?:\s*(?:do|nay|ay))?(?:\s*(?:nhe|nha|a|nhe ban))?", raw))


def continue_information(current, proposal, message=""):
    """mô hình nhận dạng câu nối tiếp; Python gắn lại câu hỏi đang chờ, không dò từ khóa."""
    selecting_information = proposal.reference in {"both", "all", "first", "second"} and proposal.action == "none"
    if selecting_information and not is_choice_only(message) and proposal.requests and any(
            request.intents != ["description"] for request in proposal.requests):
        return proposal  # Câu hỏi mới đã rõ: không đổi price thành flavor của lượt trước.
    if (proposal.continuation not in {"entity", "information"} and not selecting_information) or not (proposal.product_mentions or proposal.reference != "none"):
        return proposal
    if proposal.action != "none" or "order_request" in proposal.intents or proposal.order_update:
        return proposal
    # Câu nối vẫn có thể nêu điều kiện mới: không thay bằng bộ lọc cũ.
    if any(request.filters.model_dump(exclude_none=True) or request.size is not None
           or request.price_preference != "none" or request.search_scope == "new"
           for request in proposal.requests):
        return proposal
    pending = current.get("pending_information_request")
    if not pending and proposal.product_mentions:
        previous = (current.get("current_request") or {}).get("requests", [])
        if previous and all(request["intents"] == ["recommendation"] for request in previous):
            # Sau khi đã gợi ý xong, tên món là đối tượng đang xem mới.
            # Không phát lại bộ lọc giá cũ như một câu tư vấn chưa giải quyết.
            # Câu hỏi đang chờ làm rõ và chọn bằng thứ tự vẫn dùng nhánh cũ.
            return proposal
    if not pending:
        pending = (current.get("current_request") or {}).get("requests", [])
    if not pending:
        return proposal
    previous_intents = list(dict.fromkeys(intent for request in pending for intent in request["intents"]))
    signatures = {
        (tuple(sorted(request["intents"])), request.get("size"),
         json.dumps({k: v for k, v in request.get("filters", {}).items()
                     if k not in {"product_ids", "query"}}, sort_keys=True, ensure_ascii=False))
        for request in pending
    }
    if not previous_intents or len(signatures) != 1:
        # Truy vấn đã tách theo từng bánh có thể cùng một ý định/bộ lọc.
        # Chỉ ghép khi các thuộc tính giống nhau; không ghép price A với flavor B.
        result = proposal.model_copy(deep=True)
        result.ambiguous = True
        return result
    result = proposal.model_copy(deep=True)
    result.intents = previous_intents
    previous = pending[0]
    filters = deepcopy(previous.get("filters", {}))
    apply_query_updates(filters, proposal.updates.model_dump(exclude_none=True))
    mapping = {target: field for field, target in QUERY_FILTER_MAP.items()}
    constraints = {mapping[k]: v for k, v in filters.items()
        if k in mapping and k != "size"}
    # clear_slots là delta hiện tại: không mang điều kiện đã bỏ từ request cũ.
    for field in proposal.clear_slots:
        constraints.pop(field, None)
        if field in {"budget_vnd", "min_budget_vnd"}:
            for key in ("budget_vnd", "min_budget_vnd", "price_inclusive", "min_price_inclusive"):
                constraints.pop(key, None)
    previous_size = None if "size" in proposal.clear_slots else previous.get("size") or filters.get("size")
    result.requests = [InformationRequest(intents=previous_intents,
        product_mentions=list(proposal.product_mentions), reference=proposal.reference,
        size=previous_size, filters=constraints)]
    result.continuation = "information"
    return result


def has_reference_cue(message: str) -> bool:
    """Guard dùng ngữ cảnh cũ; không nhận diện intent hoặc chọn sản phẩm."""
    raw = normalize_text(business_command_text(message))
    return (plural_reference_evidence(message, "both") or plural_reference_evidence(message, "all")) or bool(re.search(r"\b(?:(?:banh|loai|chiec)\s+(?:do|nay|ay|vua\s+(?:roi|xem)|cu)|"
        r"vua roi|truoc do|trong don|dang dat|thu\s+(?:nhat|hai|1|2)|dau tien|re hon|re nhat|gia thap hon|no|ca\s*(?:hai|2)|tat ca|toan bo)\b", raw))


def resolve_current_choice(resolution, reference, repository, shown, *, ambiguous=False):
    """Tham chiếu theo tên trong lượt hiện tại; không mượn danh sách lịch sử."""
    current = deepcopy(resolution)
    if current["status"] == "error":
        current["ids"] = []
        return current
    if (ambiguous or current["status"] != "success" or current["ambiguous"]
            or current.get("unresolved_mentions") or not current["ids"]):
        current.update(ids=[], ambiguous=True)
        return current
    identifiers = list(current["ids"])
    if reference == "cheaper":
        # So sánh các bánh vừa nêu, không dùng giá bánh khác trong bản nháp.
        # Giá thiếu hoặc bằng nhau không đủ để xác định một bánh rẻ hơn.
        result = safe_search_products(repository, {"product_ids": identifiers})
        if result["status"] == "error":
            return {"status": "error", "ids": [], "ambiguous": False, "error": result["error"]}
        by_id = {product["id"]: product for product in result["products"]}
        prices = {}
        for identifier in identifiers:
            values = [variant["price_vnd"] for variant in by_id.get(identifier, {}).get("variants", [])
                      if variant["price_vnd"] is not None]
            if not values:
                current.update(ids=[], ambiguous=True)
                return current
            prices[identifier] = min(values)
        lowest = min(prices.values())
        cheapest = [identifier for identifier, price in prices.items() if price == lowest]
        if len(prices) < 2 or len(cheapest) != 1:
            current.update(ids=[], ambiguous=True)
            return current
        current.update(ids=cheapest, ambiguous=False)
        return current
    return resolve_mentions([], repository, shown, reference, None, identifiers, choice_ids=identifiers)


def resolve_message_scopes(current, proposal, repository, message: str = ""):
    """Giải từng yêu cầu tra cứu và mục tiêu đơn độc lập bằng repository."""
    topic = current["discussion_context"]["focus_product_ids"]
    selected = current["order"]["slots"]["product_id"]
    choice_ids = current["product_choices"]["product_ids"]
    order_mentions = list(proposal.order_product_mentions)
    # Tương thích output cũ: chỉ dùng mentions chung khi không có request riêng.
    if not proposal.requests and not order_mentions:
        order_mentions = list(proposal.product_mentions)
    if not order_mentions and "order_request" in proposal.intents and proposal.updates.cake_need:
        # cake_need là dữ liệu mô hình đã trích; đối chiếu nguồn như mention, không
        # suy tên bằng regex hay chọn từ danh sách hints của prompt.
        order_mentions = [proposal.updates.cake_need]
    order_proposal = proposal.model_copy(deep=True)
    order_proposal.product_mentions = order_mentions
    order_reference = "none" if order_mentions else (proposal.order_reference or proposal.reference)
    pending = current.get("pending_order_request")
    order_choices = choice_ids
    if (pending and pending.get("revision") == current["order"]["revision"]
            and proposal.continuation == "order"):
        order_choices = [candidate["id"] for candidate in pending.get("candidates", [])] or choice_ids
    order_resolution = resolve_mentions(order_mentions, repository, current["shown_products"],
                                        order_reference, selected, topic, choice_ids=order_choices)
    if proposal.order_operation == "update_slots" and order_resolution["status"] != "error":
        shared_fields = {"pickup_at", "fulfillment", "name", "phone", "address"}
        delta_fields = set(order_proposal.updates.model_dump(exclude_none=True))
        # Liên hệ/hình thức nhận dùng chung cho bản nháp, không chọn lại bánh
        # chỉ vì model kèm reference=last của câu hỏi giá trong cùng tin nhắn.
        if (delta_fields or proposal.clear_slots) and delta_fields <= shared_fields and set(proposal.clear_slots) <= shared_fields:
            order_resolution = {"status": "no_results", "ids": [], "ambiguous": False, "error": None}
            order_proposal.product_mentions = []
        elif order_resolution["ids"] and not set(order_resolution["ids"]).issubset(
                item["product_id"] for item in order_items(current["order"]) if item["product_id"]):
            # update_slots sửa món đã có; chọn bánh khác cần select/add rõ ràng.
            order_resolution.update(ids=[], ambiguous=True)
    if is_information_question(proposal):
        # Câu hỏi thông tin không có mục tiêu sửa đơn, dù có ID đã giải cho query.
        order_resolution = {"status": "no_results", "ids": [], "ambiguous": False, "error": None}
    elif proposal.requests and proposal.action == "start_order" and not order_mentions and order_reference == "none":
        order_resolution["ambiguous"] = True
    requests = list(proposal.requests)
    if not requests and PRODUCT_INFORMATION_INTENTS.union({"recommendation"}).intersection(proposal.intents):
        requests = [InformationRequest(intents=[i for i in proposal.intents if i in PRODUCT_INFORMATION_INTENTS or i == "recommendation"],
            product_mentions=list(proposal.product_mentions), reference=proposal.reference)]
    if "policy" in proposal.intents and not any("policy" in request.intents for request in requests):
        requests.append(InformationRequest(intents=["policy"], product_mentions=[], question=message))
    # Separate product/policy questions even if mô hình groups them in one request.
    expanded = []
    for request in requests:
        product_intents = [intent for intent in request.intents if intent != "policy"]
        if product_intents:
            expanded.append(request.model_copy(update={"intents": product_intents}))
        if "policy" in request.intents:
            expanded.append(request.model_copy(update={"intents": ["policy"], "product_mentions": [], "reference": "none"}))
    requests = expanded
    # An empty child request is not permission to pull a historical product into
    # an explicitly named current question. Prefer the unique current subject.
    current_terms = list(dict.fromkeys(name for request in requests for name in request.product_mentions))
    if not current_terms:
        current_terms = list(proposal.product_mentions)
    current_ids = []
    current_resolution = None
    if current_terms:
        current_resolution = resolve_mentions(current_terms,repository,current["shown_products"],"none",selected,topic)
        current_ids = current_resolution["ids"]
    current_names_ambiguous = any(request.ambiguous for request in requests if request.product_mentions)
    choice_references = {"first", "second", "cheaper", "both", "all"}
    explicit_reference = has_reference_cue(message)
    tasks = []
    for request in requests:
        if request.intents == ["policy"]:
            scope = {"intents": ["policy"], "product_mentions": [], "reference": "none",
                     "product_ids": [], "filters": {}, "question": request.question or message,
                     "ambiguous": request.ambiguous}
            tasks.append({"proposal": proposal.model_copy(update={"intents": ["policy"]}),
                "resolution": {"status": "no_results", "ids": [], "ambiguous": False, "error": None},
                "scope": scope, "request": request})
            continue
        query = proposal.model_copy(deep=True)
        query.intents = list(request.intents)
        query.product_mentions = list(request.product_mentions)
        query.action, query.order_update, query.clear_slots = "none", False, []
        query.requests, query.order_product_mentions, query.order_operation = [], [], "none"
        # Slot của đơn không làm filter của câu hỏi về bánh khác trong câu hỗn hợp.
        if proposal.requests:
            # Mỗi truy vấn có bộ lọc riêng. Output cũ có một câu hỏi độc lập
            # được phép giữ điều kiện tìm kiếm ở updates; không lấy slot đơn.
            constraints = {}
            if len(proposal.requests) == 1 and is_information_question(proposal):
                constraints = {k: v for k, v in proposal.updates.model_dump(exclude_none=True).items()
                    if k in QUERY_FILTER_MAP}
            constraints.update(request.filters.model_dump(exclude_none=True))
            query.updates = TurnUpdates(**constraints)
        if request.size is not None:
            query.updates.size = request.size
        if "availability" in query.intents and "recommendation" not in query.intents:
            # Hỏi bánh hết/còn phải thấy cả out_of_stock/unknown, không lọc còn hàng.
            query.updates.available_only = None
        reference = "none" if request.product_mentions else request.reference
        if request.price_preference in {"cheaper_than", "more_expensive_than"} and reference == "none" and not request.product_mentions:
            reference = "last"  # Anchor đã được AI yêu cầu so giá; ID/giá do nguồn xác minh.
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
        reference_focus = topic
        if reference == "last" and current_terms and not explicit_reference:
            reference_focus = current_ids
        if not query.product_mentions and reference in choice_references and current_resolution is not None:
            resolution = resolve_current_choice(current_resolution, reference, repository, current["shown_products"],
                                                ambiguous=current_names_ambiguous)
        else:
            query_choices = choice_ids
            if (pending and pending.get("revision") == current["order"]["revision"]
                    and not query.product_mentions and reference in {"first", "second"}
                    and len(choice_ids) < (2 if reference == "second" else 1)):
                query_choices = [candidate["id"] for candidate in pending.get("candidates", [])]
            resolution = resolve_mentions(query.product_mentions, repository, current["shown_products"], reference, selected, reference_focus,
                                          choice_ids=query_choices)
        # Một tên nhóm khớp nhiều bánh vẫn trả được thông tin từng bánh.
        # Mơ hồ do liên kết thuộc tính/tham chiếu vẫn phải hỏi lại.
        if (query.product_mentions and len(query.product_mentions) == 1 and not request.ambiguous
                and resolution["ambiguous"] and resolution.get("candidates")
                and not resolution.get("unresolved_mentions")):
            ids = list(dict.fromkeys(p["id"] for p in resolution["candidates"]))
            resolution.update(ids=ids, status="success", ambiguous=False)
        if not resolution["ids"] and resolution.get("unresolved_mentions") and all(has_reference_cue(term) for term in resolution["unresolved_mentions"]):
            local_ambiguous = True  # A reference phrase is not a verified cake name.
        if local_ambiguous:
            resolution.update(ids=[],ambiguous=True)
        scope = build_current_turn(current, query, resolution, reference)
        if request.search_scope == "new" and request.price_preference not in {"cheaper_than", "more_expensive_than"}:
            apply_query_updates(scope["filters"], query.updates.model_dump(exclude_none=True), new_search=True)
            scope["search_scope"] = "new"
        if request.price_preference != "none":
            scope["price_preference"] = request.price_preference
        if request.price_preference in {"cheaper_than", "more_expensive_than"}:
            # ID tham chiếu chỉ là mốc giá, KHÔNG khóa kết quả tìm kiếm vào bánh cũ.
            scope["comparison_product_ids"] = list(resolution["ids"])
            scope["product_ids"] = []
            scope["filters"] = deepcopy(current["needs"]["filters"])
            for key in ("product_ids", "query"):
                scope["filters"].pop(key, None)
            apply_query_updates(scope["filters"], query.updates.model_dump(exclude_none=True))
            resolution = {**resolution, "ids": []}
        advice_mode = request.advice
        if (advice_mode == "none" and current.get("advice_pending")
                and request.intents == ["recommendation"] and not request.product_mentions and request.reference == "none"):
            advice_mode = "guided"  # FSM tiếp tục bảng tư vấn; intent/filter vẫn do Qwen.
        scope.update(ambiguous=request.ambiguous, advice=advice_mode if len(requests) == 1 else "none")
        if request.question:
            scope["question"] = request.question
        if request.excluded_product_mentions:
            excluded = resolve_mentions(request.excluded_product_mentions, repository, [], "none")
            if excluded["status"] == "error":
                resolution = excluded
            elif excluded["ambiguous"] or excluded.get("unresolved_mentions"):
                resolution["ambiguous"] = True
            else:
                scope["filters"]["exclude_product_ids"] = excluded["ids"]
        if not any(task["scope"] == scope for task in tasks):
            tasks.append({"proposal": query, "resolution": resolution, "scope": scope, "request": request})
    # "A giá bao nhiêu? Đặt bánh này" refers to A in THIS message first.
    # A reference over several current products is ambiguous, never an old draft.
    named_tasks = [task for task in tasks if task["scope"]["product_mentions"] and task["resolution"]["ids"]]
    if (not order_mentions and order_reference == "last" and "order_request" in proposal.intents
            and proposal.order_operation in {"select_product", "add_product", "remove_product"} and named_tasks):
        mentioned_now = list(dict.fromkeys(identifier for task in named_tasks for identifier in task["resolution"]["ids"]))
        order_resolution = {"status": "success", "ids": mentioned_now if len(mentioned_now) == 1 else [],
            "ambiguous": len(mentioned_now) != 1 or any(task["scope"].get("ambiguous") or task["resolution"]["ambiguous"] for task in named_tasks),
            "error": None}
    if (not order_mentions and order_reference in choice_references and "order_request" in proposal.intents
            and proposal.order_operation in {"select_product", "add_product", "remove_product"}
            and current_resolution is not None):
        order_resolution = resolve_current_choice(current_resolution, order_reference, repository, current["shown_products"],
                                                  ambiguous=current_names_ambiguous)
    if (not proposal.order_items and not is_information_question(proposal)
            and order_reference in {"both", "all"} and order_resolution["ids"] and not order_resolution["ambiguous"]
            and proposal.order_operation in {"select_product", "add_product", "remove_product"}):
        # Schema cũ có một quantity chung đã được grounding EACH kiểm chứng.
        # Không suy quantity từ số lượng lựa chọn; None sẽ được hỏi từng món.
        order_resolution["item_selections"] = [
            {"product_id": identifier, "quantity": proposal.updates.quantity, "product_mention": None}
            for identifier in order_resolution["ids"]]
    if proposal.order_items and not is_information_question(proposal):
        current_candidates = list(dict.fromkeys(identifier for task in tasks for identifier in task["resolution"]["ids"]))
        offered = order_choices if proposal.continuation == "order" else current_candidates or choice_ids
        selections = []
        item_candidates, unresolved_items = [], []
        item_error = None
        ambiguous_item = False
        for item in proposal.order_items:
            mentions = [item.product_mention] if item.product_mention else []
            if not mentions and item.reference in choice_references and current_resolution is not None:
                found = resolve_current_choice(current_resolution, item.reference, repository, current["shown_products"],
                                               ambiguous=current_names_ambiguous)
            else:
                found = resolve_mentions(mentions, repository, current["shown_products"],
                                         item.reference, selected, topic, choice_ids=offered)
            item_candidates.extend(found.get("candidates", []))
            unresolved_items.extend(found.get("unresolved_mentions", []))
            if found["status"] == "error":
                item_error = found["error"] or "source_error"
            if found["status"] == "unconfigured" and item.product_mention:
                selections.append({"product_id": None, "quantity": item.quantity,
                                   "product_mention": item.product_mention})
                continue  # Thu thập mong muốn unverified, không bịa ID sản phẩm.
            if found["ambiguous"] or not found["ids"] or found.get("unresolved_mentions"):
                ambiguous_item = True
            for identifier in found["ids"]:
                if any(previous["product_id"] == identifier for previous in selections):
                    ambiguous_item = True  # Không đoán cách cộng hai dòng trùng nhau.
                selections.append({"product_id": identifier, "quantity": item.quantity,
                                   "product_mention": item.product_mention})
        order_resolution = {"status": "error" if item_error else "success" if selections else "no_results",
                            "ids": list(dict.fromkeys(item["product_id"] for item in selections if item["product_id"])),
                            "ambiguous": ambiguous_item or len(selections) > 6, "error": item_error,
                            "item_selections": selections,
                            "candidates": list({candidate["id"]: candidate for candidate in item_candidates}.values()),
                            "unresolved_mentions": list(dict.fromkeys(unresolved_items))}
    if (pending and pending.get("revision") == current["order"]["revision"]
            and proposal.continuation == "order" and not order_mentions and proposal.updates.flavor):
        # Model trích vị trong câu hiện tại; chỉ lọc những lựa chọn của yêu cầu
        # đang chờ, không chọn bánh khác từ lần hỏi giá xen ngang.
        candidates = [candidate["id"] for candidate in pending.get("candidates", [])]
        if candidates:
            found = safe_search_products(repository, {"product_ids": candidates, "flavor": proposal.updates.flavor})
            products = found["products"]
            order_resolution = {
                "status": found["status"], "error": found["error"],
                "ids": [product["id"] for product in products] if len(products) == 1 else [],
                "ambiguous": len(products) != 1,
                "candidates": [{"id": product["id"], "name": product["name"]} for product in products] or deepcopy(pending["candidates"]),
            }
    scope = deepcopy(tasks[0]["scope"]) if tasks else build_current_turn(current, proposal, order_resolution, order_reference)
    scope["intents"] = list(proposal.intents)
    scope["requests"] = [deepcopy(task["scope"]) for task in tasks]
    scope["order_product_ids"] = list(order_resolution["ids"])
    if tasks:
        scope["product_ids"] = list(dict.fromkeys(identifier for task in tasks for identifier in task["scope"]["product_ids"]))
    return scope, tasks, order_proposal, order_resolution


def deduplicate_information_tasks(tasks):
    """Mỗi bộ lọc/sản phẩm/intent chỉ trả một lần, kể cả model sinh request lặp."""
    from app.storage import fingerprint
    seen, result, grouped = {}, [], {}
    for task in tasks:
        scope, resolution = task["scope"], task["resolution"]
        if scope["intents"] == ["policy"] or scope.get("ambiguous") or resolution["ambiguous"] or not resolution["ids"]:
            key = fingerprint({key: value for key, value in scope.items() if key != "question"} if scope["intents"] != ["policy"] else scope)
            if key not in seen:
                seen[key] = set(scope["intents"])
                result.append(task)
            continue
        for identifier in resolution["ids"]:
            filters = {**scope["filters"], "product_ids": [identifier]}
            # Tra cứu thông tin cùng món/cùng điều kiện chỉ làm một lần.
            # Tư vấn/xếp giá giữ riêng vì ID có thể là mốc so sánh.
            information = "recommendation" not in scope["intents"]
            key = fingerprint({"filters": filters, "information": information,
                               "price_preference": scope.get("price_preference", "none")})
            new_intents = [intent for intent in scope["intents"] if intent not in seen.get(key, set())]
            if not new_intents:
                continue
            seen.setdefault(key, set()).update(new_intents)
            if information and key in grouped:
                existing = grouped[key]
                existing["scope"]["intents"].extend(new_intents)
                existing["proposal"] = existing["proposal"].model_copy(
                    update={"intents": list(existing["scope"]["intents"])})
                continue
            child = {**task, "scope": {**scope, "intents": new_intents, "product_ids": [identifier], "filters": filters},
                "resolution": {**resolution, "ids": [identifier]},
                "proposal": task["proposal"].model_copy(update={"intents": new_intents})}
            result.append(child)
            if information:
                grouped[key] = child
    return result


def describe_requested_products(products, intents):
    """Chỉ diễn đạt trường nguồn cho đúng intent của từng request."""
    if "recommendation" in intents:
        return describe_products(products)
    lines = []
    for product in products:
        if intents == ["price"] and len(product["variants"]) == 1:
            variant = product["variants"][0]
            price = format_vnd(variant["price_vnd"]) if variant["price_vnd"] is not None else "chưa có giá"
            size_note = " (" + variant["size"] + ")" if variant["size"] else ""
            lines.append(f"{product['name']}{size_note}: {price}.")
            continue
        lines.append(product["name"] + ":")
        for variant in product["variants"]:
            if "price" in intents:
                price = format_vnd(variant["price_vnd"]) if variant["price_vnd"] is not None else "chưa có giá"
                prefix = variant["size"] + ": " if variant["size"] else ""
                lines.append(f"  • {prefix}{price}.")
            if "size" in intents:
                servings = f"khoảng {variant['servings']} người" if variant["servings"] else "chưa biết số người ăn"
                lines.append(f"  • Size {variant['size'] or 'chưa biết'}; {servings}.")
            if "availability" in intents:
                labels = {"in_stock": "còn hàng", "out_of_stock": "hết hàng", "preorder": "cần đặt trước", "unknown": "chưa biết tình trạng còn hàng"}
                prefix = variant["size"] + ": " if variant["size"] else ""
                lines.append(f"  • {prefix}{labels[variant['stock_status']]}.")
        if "flavor" in intents:
            label = "  Vị ghi trong tên: " if product.get("flavor_source") == "product_name" else "  Hương vị: "
            lines.append(label + (product["flavor"] or "chưa xác định") + ".")
            if product.get("style_tags"):
                lines.append("  Đặc điểm: " + "; ".join(product["style_tags"]) + ".")
    return "\n".join(lines)


def recommendation_result(repository, current, scope, data_mode):
    """Lọc điều kiện trước, xếp giá hoặc lấy ngẫu nhiên; không nhờ LLM tính giá."""
    filters = deepcopy(scope["filters"])
    preference = scope.get("price_preference", "none")
    relative = preference in {"cheaper_than", "more_expensive_than"}
    notice = ""
    preferred_flavors = set()
    if relative:
        anchor_ids = scope.get("comparison_product_ids", [])
        anchor_filters = {"product_ids": anchor_ids}
        if filters.get("size"):
            anchor_filters["size"] = filters["size"]
        anchors = safe_search_products(repository, anchor_filters, data_mode)
        if anchors["status"] in {"error", "unconfigured"}:
            return anchors, notice
        if len(anchors["products"]) != 1:
            return {**anchors, "status": "no_results", "products": []}, "Chưa xác định được một sản phẩm làm mốc so giá. Bạn muốn so với sản phẩm nào?"
        anchor = anchors["products"][0]
        variants = anchor["variants"]
        # Tham chiếu tới thẻ đã xem giữ đúng biến thể, nhưng giá phải đọc lại từ nguồn.
        previous = next((p for p in current["shown_products"] if p["id"] == anchor["id"]), None)
        if previous and not scope["product_mentions"] and not filters.get("size"):
            variant_ids = {v["id"] for v in previous["variants"]}
            variants = [v for v in variants if v["id"] in variant_ids]
        prices = {v["price_vnd"] for v in variants if v["price_vnd"] is not None}
        if not prices:
            return {**anchors, "status": "no_results", "products": []}, "Chưa có giá đã xác minh của sản phẩm làm mốc nên chưa thể so sánh."
        if len(prices) != 1 or any(v["price_vnd"] is None for v in variants):
            return {**anchors, "status": "no_results", "products": []}, "Sản phẩm làm mốc có nhiều mức giá hoặc giá chưa rõ. Bạn muốn so với biến thể nào?"
        price = next(iter(prices))
        if not filters.get("product_type"):
            filters["product_type"] = next((kind for kind in ("cream_cake", "mini", "tea", "coffee", "cake", "drink")
                                            if _matches_product_type(anchor, kind)), None)
            if filters["product_type"] is None:
                filters.pop("product_type")
        filters["exclude_product_ids"] = list(dict.fromkeys([*filters.get("exclude_product_ids", []), anchor["id"]]))
        if preference == "cheaper_than":
            # Giao với ngân sách nêu rõ trong lượt này, không âm thầm nới điều kiện.
            if filters.get("max_price_vnd", price) >= price:
                filters.update(max_price_vnd=price, price_inclusive=False)
        elif filters.get("min_price_vnd", price) <= price:
            filters.update(min_price_vnd=price, min_price_inclusive=False)
        if not filters.get("flavor"):
            preferred_flavors = canonical_flavors(anchor["flavor"])
        scope["filters"] = filters
    result = safe_search_products(repository, filters, data_mode)
    if result["status"] != "success":
        return result, notice
    products = result["products"]
    def price_of(product):
        values = [v["price_vnd"] for v in product["variants"] if v["price_vnd"] is not None]
        if not values:
            return None
        return max(values) if preference in {"highest", "cheaper_than"} else min(values)
    if preference != "none":
        products = [p for p in products if price_of(p) is not None]
        if not products:
            return {**result, "products": [], "status": "no_results"}, "Menu chưa có đủ giá đã xác minh để xếp hạng sản phẩm."

    if relative and preferred_flavors:
        same_flavor = [p for p in products if preferred_flavors.issubset(canonical_flavors(p["flavor"]))]
        if same_flavor:
            products = same_flavor
            notice = "Ưu tiên sản phẩm cùng hương vị với loại vừa xem."
        elif products:
            notice = "Chưa tìm thấy sản phẩm được ghi nhận cùng hương vị ở mức giá này; bạn có thể thử các lựa chọn khác dưới đây."
    if preference != "none" or any(key in filters for key in ("min_price_vnd", "max_price_vnd")):
        reverse = preference in {"highest", "cheaper_than"}
        products = sorted(products, key=lambda p: (price_of(p) is None, price_of(p) or 0), reverse=reverse)
        if products and preference in {"lowest", "highest"}:
            extreme = price_of(products[0])
            products = [{**p, "variants": [v for v in p["variants"] if v["price_vnd"] == extreme]}
                        for p in products if price_of(p) == extreme]
            notice = "Các lựa chọn " + ("rẻ nhất" if preference == "lowest" else "đắt nhất") + " theo giá đã có trong menu và các điều kiện bạn yêu cầu."
    else:
        products = random.sample(products, len(products))
    return {**result, "products": products, "status": "success" if products else "no_results"}, notice


def product_answer(repository, current, proposal, response, current_turn, *, pagination_pages=None) -> None:
    current_turn["result_product_ids"] = []
    if "recommendation" in proposal.intents:
        result, notice = recommendation_result(repository, current, current_turn, response["data_mode"])
    else:
        result = safe_search_products(repository, current_turn["filters"], response["data_mode"])
        notice = ""
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
        if "recommendation" in proposal.intents:
            summary = {**current["needs"], "filters": deepcopy(current_turn["filters"]),
                       "product_terms": list(current_turn["product_mentions"])}
            if summary["filters"] or summary["product_terms"] or summary["quantity"] is not None:
                response["text"] += summarize_needs(summary) + "\n"
        response["text"] += "Chưa có menu để đối chiếu thông tin bạn hỏi."
        return
    if result["status"] == "no_results":
        if current_turn.get("advice") == "more":
            next_advice_page(current, current_turn, [],
                response.get("catalog_source", response["data_mode"]), pages=pagination_pages)
        if notice:
            response["text"] += notice
            response["requires_clarification"] = notice.endswith("?")
            current["shown_products"] = []
            return
        unsupported = repository.get_capabilities().get("unsupported_search_filters", [])
        labels = {"size": "size", "servings": "số người ăn", "flavor": "hương vị",
                  "occasion": "dịp sử dụng", "available_only": "tồn kho", "exclude_allergens": "thành phần/dị ứng"}
        missing_metadata = [labels.get(field, field) for field in unsupported
                            if current_turn["filters"].get(field) is not None
                            and not (field == "available_only" and current_turn["filters"][field] is False)]
        if missing_metadata:
            response["text"] += "Menu chưa cung cấp " + ", ".join(missing_metadata) + "; chưa thể tìm bánh theo điều kiện này. "
            response["text"] += ("Cần nhân viên xác minh thành phần trước khi tư vấn theo yêu cầu tránh nguyên liệu."
                                 if current_turn["filters"].get("exclude_allergens")
                                 else "Bạn có thể tìm theo tên, nhóm hoặc ngân sách.")
        else:
            response["text"] += "Menu hiện tại chưa có món phù hợp với yêu cầu này."
            if current_turn.get("advice") in {"guided", "any"}:
                fallback_filters = deepcopy(current_turn["filters"])
                # Chỉ mời xem VỊ KHÁC; giữ nguyên ngân sách/nhóm/độ ngọt/dị ứng.
                removed = [fallback_filters.pop(key) for key in ("flavor", "taste_family", "coffee_style") if key in fallback_filters]
                alternatives = safe_search_products(repository, fallback_filters, response["data_mode"]) if removed else None
                if alternatives and alternatives["status"] == "error":
                    raise ValueError(alternatives["error"] or "source_error")
                if alternatives and alternatives["status"] == "success":
                    offered = diverse_products(alternatives["products"])
                    response["text"] += "\nNếu bạn muốn thử vị khác, có thể tham khảo:\n" + advice_summary(offered)
                    response["products"] = offered
                    current_turn["result_product_ids"] = [p["id"] for p in offered]
                    current["shown_products"] = deepcopy(offered)
                    current["advice_pending"] = None
                    response["quick_replies"] = []
                    return
            response["text"] += " Bạn có thể đổi hương vị hoặc ngân sách để mình tìm tiếp."
        current["shown_products"] = []
        return
    guided = proposal.intents == ["recommendation"] and current_turn.get("advice") in {"guided", "any", "more"}
    if guided:
        question = advice_question(current, current_turn, result["products"])
        if question:
            response["text"] += question
            response["quick_replies"] = [o["label"] for o in current["advice_pending"]["options"]]
            current["shown_products"] = []
            return
    # Câu hỏi tên rõ vẫn trả đủ; tư vấn theo bước tối đa ba món.
    shown = (result["products"][:4] if "recommendation" in proposal.intents
             else result["products"] if current_turn["product_ids"] else result["products"][:5])
    has_more = False
    if "recommendation" in proposal.intents:
        shown, has_more = next_advice_page(current, current_turn, result["products"],
            response.get("catalog_source", response["data_mode"]),
            limit=3 if guided else 4, pages=pagination_pages)
        current["advice_pending"] = None
        response["quick_replies"] = [MORE_ADVICE_LABEL] if has_more else []
        if not shown:
            current["shown_products"] = []
            current_turn["result_product_ids"] = []
            response["text"] += "Mình đã giới thiệu hết các sản phẩm phù hợp với điều kiện này. Bạn có thể đổi loại, hương vị hoặc ngân sách để xem thêm."
            return
    current["shown_products"] = deepcopy(shown)
    response["products"] = shown
    current_turn["result_product_ids"] = [product["id"] for product in shown]
    if notice:
        response["text"] += notice + "\n"
    response["text"] += advice_summary(shown, has_more=has_more) if guided else describe_requested_products(shown, proposal.intents)
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
    if not guided and len(result["products"]) > len(shown):
        response["text"] += f"\nHiển thị {len(shown)}/{len(result['products'])} sản phẩm phù hợp; bạn có thể lọc thêm."
    # Nhãn mô phỏng đã có ở đầu response; không lặp lại sau từng yêu cầu.


def answer_policy_request(question, knowledge_repository, base_url, model, timeout):
    """Một câu chính sách -> retriever -> mô hình chọn nguồn; không chạy tool đơn."""
    retrieval = retrieve(question, knowledge_repository)
    generation, error = None, None
    if retrieval["status"] == "success":
        generation = llm_client.extract_policy_answer(question, retrieval, base_url, model, timeout)
        error = generation["error"]
        if not error:
            error = validate_rag_answer(generation["data"], retrieval)
    policy = make_policy_response(retrieval,
        generation["data"] if generation and not error else None,
        engine="ollama",
        attempts=generation["attempts"] if generation else 0)
    if error:
        # Không coi trích đoạn mặc định là câu trả lời mô hình thành công.
        policy.update(status="insufficient", citations=[], source_ids=[], llm_error=error)
        policy["text"] = "Chưa xử lý được câu hỏi chính sách này; bạn có thể thử lại."
    return policy, error


def merge_policy_responses(previous, policy):
    """Giữ nguồn cho mọi câu chính sách để API hiện có vẫn hiển thị được."""
    if previous is None:
        return deepcopy(policy)
    combined = deepcopy(previous)
    if policy["text"] not in combined["text"]:
        combined["text"] += "\n" + policy["text"]
    combined["attempts"] += policy["attempts"]
    combined["is_mock"] = combined["is_mock"] or policy["is_mock"]
    combined["error"] = combined["error"] or policy["error"]
    combined["llm_error"] = combined["llm_error"] or policy["llm_error"]
    if combined["status"] != policy["status"]:
        combined["status"] = "insufficient"
    for citation in policy["citations"]:
        if citation not in combined["citations"]:
            combined["citations"].append(deepcopy(citation))
    combined["source_ids"] = list(dict.fromkeys([*combined["source_ids"], *policy["source_ids"]]))
    return combined


def information_clarification(task):
    """Hỏi đúng đối tượng còn chưa rõ, không hỏi lại tất cả ý định."""
    scope, resolution = task["scope"], task["resolution"]
    subjects = ", ".join(scope["product_mentions"])
    choices = "; ".join(dict.fromkeys(product["name"] for product in resolution.get("candidates", [])))
    if choices:
        return f"{subjects or 'Đối tượng bạn nhắc'} khớp nhiều sản phẩm. Bạn chọn loại nào: {choices}?"
    if subjects:
        return f"Mình chưa liên kết rõ thuộc tính với {subjects}. Bạn gắn thuộc tính còn thiếu với từng bánh nhé."
    label = "giá" if scope["intents"] == ["price"] else "thông tin"
    return f"Bạn muốn hỏi {label} của bánh nào?"


def advance_order(current, proposal, resolution, message, tools, repository=None, *, outcome=None) -> str:
    """mô hình đề xuất; hàm này áp dụng quy tắc FSM, không parse keyword thay mô hình."""
    draft = current["order"]
    proposal = without_disabled_order_fields(proposal, draft)
    if proposal.order_negated:
        return ""
    if is_information_question(proposal):
        # Cờ order_update riêng lẻ không đủ để biến câu hỏi giá/bảo quản thành sửa đơn.
        # Dị ứng nghiêm trọng/yêu cầu nhân viên vẫn được xử lý như trước.
        if proposal.handoff_reason == "none" and not proposal.updates.allergens and not current["needs"]["filters"].get("exclude_allergens") and not draft.get("allergies"):
            return ""
    slot_updates = {k: v for k, v in proposal.updates.model_dump(exclude_none=True).items() if k in draft["slots"]}
    edit_with_consent = proposal.action in {"confirm", "review"} and bool(proposal.order_operation in {"add_product", "remove_product"} or slot_updates or proposal.clear_slots or (
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
    # Đặt thêm sau bản đã gửi là bản mới; sửa/hủy bản đã gửi vẫn qua hỗ trợ.
    new_request = (proposal.action == "start_order" or proposal.order_operation == "add_product") and bool(
        resolution["ids"] or resolution.get("item_selections") or proposal.product_mentions)
    if new_request and draft.get("submission") and not draft.get("submission_pending"):
        previous_slots = draft["slots"]
        draft = new_draft(current["id"], draft.get("optional_fields", []), draft.get("disabled_fields", []))
        for field in ("name", "phone"):
            draft["slots"][field] = previous_slots.get(field)
        current["order"] = draft
        current["pending_order_request"] = None
        current["pending_order_question"] = None
    if draft["submission"] and draft["submission"]["confirmed"]:
        if proposal.action == "confirm" and not edit_with_consent:
            current["order"], text = confirm_review(draft, tools, current["needs"])
            return text
        if proposal.action == "cancel" or proposal.order_update or proposal.order_operation != "none" or edit_with_consent:
            current["order"], text = request_handoff(draft, tools, "change_confirmed_order", current["needs"])
            return text
    if proposal.action == "cancel" and draft.get("submission_pending"):
        return "Kết quả gửi đơn chưa xác định; chưa thể hủy như bản nháp. Hãy kiểm tra lại với khóa chống trùng cũ."
    if proposal.action == "cancel":
        draft = deepcopy(draft)
        draft.update(state="CANCELLED", review=None)
        current["order"] = draft
        current["pending_order_request"] = None
        return "Đã hủy bản nháp, không tạo đơn."
    if current.get("pending_order_request") and (proposal.action in {"confirm", "review"} or "acknowledgement" in proposal.intents):
        return "Yêu cầu thêm/đổi/bỏ bánh còn cần làm rõ. Bạn hãy nói rõ bánh và số lượng muốn thay đổi; mình chưa gửi yêu cầu."
    # Cờ order_update đơn lẻ không là delta. Với confirm/review, chỉ thay
    # đổi thực sự được đề xuất mới làm quay về REVIEW; còn lại gọi xác nhận.
    editing = edit_with_consent if proposal.action in {"confirm", "review"} else (
        proposal.order_operation != "none" or proposal.action == "start_order" or (
            "order_request" in proposal.intents and bool(slot_updates or proposal.product_mentions or proposal.clear_slots)))
    if draft.get("submission_pending") and editing:
        return "Kết quả gửi đơn còn chưa xác định. Bản nháp được giữ nguyên; hãy xác nhận lại để kiểm tra bằng khóa chống trùng cũ trước khi thay đổi."
    if editing:
        if proposal.order_operation == "remove_product" and not draft.get("extra_items") and proposal.updates.quantity is None and not resolution.get("item_selections"):
            proposal = proposal.model_copy(deep=True)
            if "product" not in proposal.clear_slots:
                proposal.clear_slots.append("product")
            resolution = {**resolution, "ids": []}
        if not resolution.get("item_selections") and (len(resolution["ids"]) > 1 or len(proposal.product_mentions) > 1):
            return "Bạn hãy thêm từng loại bánh và số lượng để mình ghi nhận đúng từng món."
        if draft["state"] in {"CANCELLED", "HANDOFF", "DEMO_CONFIRMED"}:
            if proposal.action != "start_order":
                return "Bản nháp đã kết thúc/chuyển tư vấn. Hãy bắt đầu yêu cầu đặt bánh mới."
            draft = new_draft(current["id"], draft.get("optional_fields", []), draft.get("disabled_fields", []))
        draft = deepcopy(draft)
        draft["state"] = "COLLECTING" if draft["state"] == "BROWSING" else draft["state"]
        try:
            selections = resolution.get("item_selections", [])
            if selections:
                changed = False
                for index, item in enumerate(selections):
                    part = proposal.model_copy(deep=True)
                    part.order_items = []
                    part.product_mentions = [item["product_mention"]] if item["product_mention"] else []
                    part.order_product_mentions = list(part.product_mentions)
                    values = part.updates.model_dump(exclude_none=True)
                    values.pop("quantity", None)
                    if item["quantity"] is not None:
                        values["quantity"] = item["quantity"]
                    part.updates = TurnUpdates(**values)
                    if index > 0:
                        part.clear_slots = []
                        if part.order_operation == "select_product":
                            part.order_operation = "add_product"
                    draft, item_changed = apply_cart_operation(message, draft, part, [item["product_id"]] if item["product_id"] else [],
                                                               repository, current.get("pending_order_question"))
                    changed = changed or item_changed
            else:
                draft, changed = apply_cart_operation(message, draft, proposal, resolution["ids"], repository, current.get("pending_order_question"))
        except ValueError as exception:
            if outcome is not None:
                outcome["requires_clarification"] = True
            if current["order"].get("review") and not current["order"].get("submission"):
                current["order"].update(state="COLLECTING", review=None, revision=current["order"]["revision"] + 1)
            # Sai liên hệ không phải là chưa chọn rõ bánh; giữ bước đang hỏi.
            from app.order_service import normalize_contact_value
            for field in ("name", "phone"):
                if field in slot_updates:
                    try:
                        normalize_contact_value(field, slot_updates[field])
                    except ValueError as contact_error:
                        return str(contact_error) + " Thông tin trước đó được giữ nguyên."
            current["pending_order_request"] = {
                "operation": proposal.order_operation, "product_ids": list(resolution["ids"]),
                "product_mentions": list(proposal.product_mentions), "revision": current["order"]["revision"],
            }
            return "Chưa ghi nhận thay đổi: " + str(exception) + " Bản nháp trước được giữ nguyên."
        current["order"] = draft
        if outcome is not None:
            outcome["changed"] = changed
        current["pending_order_request"] = None
        if draft.get("pending_pickup_date") and "pickup_at" not in draft.get("disabled_fields", []):
            return f"Mình ghi nhận ngày {draft['pending_pickup_date']} theo giờ Việt Nam. Bạn muốn nhận lúc mấy giờ? Chưa tự chọn giờ và chưa xác nhận đơn."
        if current.get("web_checkout"):
            draft.pop("checkout_token", None)
            return "Mình đã ghi nhận sản phẩm. Bạn kiểm tra và điền thông tin trong form bên dưới nhé."
        if not missing_draft_slots(draft):
            current["order"], text = create_review(draft, tools)
            if current["order"].get("review") and current["order"]["review"]["mode"] == "local_demo" and any(
                issue in current["order"]["issues"] for issue in {"availability_unverified", "lead_time_unverified", "cake_text_limit_unverified", "allergen_requires_staff"}
            ):
                current["order"], ticket_text = request_handoff(current["order"], tools, "needs_verification", current["needs"])
                return text + "\n" + ticket_text
            if proposal.action == "confirm" or changed:
                text += "\nThông tin vừa thay đổi: cần đồng ý rõ ràng với bản tóm tắt mới trước khi gửi."
            return text
        return collect_instructions(draft)
    if current.get("web_checkout") and not draft.get("submission") and proposal.action in {"review", "confirm"}:
        from app.checkout import verify_checkout
        if proposal.action == "review":
            return "Bạn kiểm tra thông tin trong form và bấm Xem lại yêu cầu nhé."
        try:
            verify_checkout(draft, repository)
        except ValueError as error:
            return str(error)
    if proposal.action == "review":
        current["order"], text = create_review(draft, tools)
        return text
    if proposal.action == "confirm":
        current["order"], text = confirm_review(draft, tools, current["needs"])
        return text
    if draft["submission"] and ("order_request" in proposal.intents or "acknowledgement" in proposal.intents):
        # Model có thể không trả action=confirm khi REVIEW đã được gửi.
        # Chỉ nhắc lại kết quả đã lưu; confirm_review trả sớm, không gọi tool.
        current["order"], text = confirm_review(draft, tools, current["needs"])
        return text
    if "acknowledgement" in proposal.intents:
        if draft["state"] == "COLLECTING":
            return collect_instructions(draft)
        if draft["state"] == "REVIEW":
            return "Bạn muốn gửi bản tóm tắt này không? Nếu muốn, hãy nói 'xác nhận gửi yêu cầu'."
        return "Bạn muốn hỏi thêm thông tin nào về sản phẩm?"
    if "order_request" in proposal.intents and draft["state"] == "COLLECTING":
        return collect_instructions(draft)
    return ""


def continue_combo(current, proposal, message=""):
    """Nối delta đã kiểm chứng vào bộ lọc combo, tách biệt hoàn toàn bản nháp."""
    saved = current.get("bundle_context")
    if (not saved or proposal.bundle_budget is not None or proposal.action != "none"
            or proposal.order_operation != "none" or proposal.intents != ["recommendation"]
            or not proposal.requests or any(r.search_scope != "refine" for r in proposal.requests)):
        return proposal, None
    components = saved["components"]
    types = [c["filters"].get("product_type") for c in components]
    targets = [r.filters.product_type for r in proposal.requests]
    from app.schemas import BundleBudget
    budget_change = None
    if len(proposal.requests) == 1 and targets == [None]:
        delta = proposal.requests[0].filters.model_dump(exclude_none=True)
        if ("budget_vnd" in delta and set(delta) <=
                {"budget_vnd", "min_budget_vnd", "price_inclusive", "min_price_inclusive"}):
            budget_change = BundleBudget(question=message, **delta)
            targets = types
    if (any(t is None or types.count(t) != 1 for t in targets)
            or len(set(targets)) != len(targets)
            or any(r.product_mentions or r.reference != "none" for r in proposal.requests)):
        return proposal, "Bạn muốn điều chỉnh món nào trong combo?"
    result = proposal.model_copy(deep=True)
    inverse = {target: field for field, target in QUERY_FILTER_MAP.items()}
    requests = []
    for component in components:
        values = {inverse[k]: v for k, v in component["filters"].items() if k in inverse}
        kind = values.get("product_type")
        change = next((r for r in proposal.requests if r.filters.product_type == kind), None)
        if change:
            for field in proposal.clear_slots:
                values.pop(field, None)
            values.update(change.filters.model_dump(exclude_none=True))
        requests.append(InformationRequest(
            intents=["recommendation"], question=change.question if change and change.question else kind,
            product_mentions=component.get("product_mentions", []),
            quantity=component["quantity"], search_scope="new", filters=values))
    result.requests = requests
    result.bundle_budget = budget_change or (BundleBudget.model_validate(saved["budget"]) if saved["budget"] else None)
    return result, None


def handle_message(message, repository, conversation, *, chat_mode=CHAT_MODE, base_url=None,
                   model=None, timeout=None, knowledge_repository=None,
                   order_tools=None, storage_connection=None) -> dict:
    """Điểm gọi của API web/script kiểm tra. Model lỗi giữ nguyên state; rule phải chọn chủ động."""
    if chat_mode not in {"rule", "ollama"}:
        raise ValueError("chat_mode chỉ nhận rule hoặc ollama.")
    endpoint, configured_model, configured_timeout = get_llm_settings(chat_mode)
    base_url = endpoint if base_url is None else base_url
    model = configured_model if model is None else model
    timeout = configured_timeout if timeout is None else timeout
    deadline = monotonic() + timeout
    current = deepcopy(conversation)
    current.setdefault("order", new_draft(current["id"]))
    current.setdefault("shown_products", [])
    initialize_memory(current)
    current.setdefault("unknown_streak", 0)
    current["history"] = current["history"][-2 * current["max_turns"]:]
    try:
        capabilities = repository.get_capabilities()
        current["order"] = configure_order_fields(current["order"], capabilities.get("optional_order_fields", []), capabilities.get("disabled_order_fields", []))
        current["pending_order_question"] = pending_order_slot(current["order"]) if current["order"]["state"] == "COLLECTING" else None
    except Exception:
        return failed_turn(message, repository, conversation, "source_error", source=True)
    if chat_mode == "rule":
        return rule_turn(message, repository, current, knowledge_repository, order_tools, storage_connection)
    if current.get("llm_provider") != "ollama" or not current["model"] or (model and current["model"] != model):
        selected = llm_client.select_model(base_url, model, timeout)
        if selected["error"]:
            return failed_turn(message, repository, conversation, selected["error"])
        current["model"] = selected["model"]
    current["llm_provider"] = chat_mode
    original_message = message
    advice_selection = resolve_advice_selection(current, message)
    message = expand_advice_selection(current, message)
    extraction = llm_client.extract_turn(message, current, base_url, current["model"],
        max(0, deadline - monotonic()), repository)
    attempts = extraction["attempts"]
    if extraction["error"] or extraction["data"] is None:
        return failed_turn(message, repository, conversation, extraction["error"] or "invalid_turn_json", attempts,
                           http_status=extraction.get("http_status"))
    # Kiểm chứng delta của model TRƯỚC khi bổ sung các điều kiện đã xác minh
    # từ lượt trước. Điều kiện cũ không phải thông tin model tự bịa trong câu mới.
    proposal = without_disabled_order_fields(extraction["data"], current["order"])
    if proposal.requests_overflow:
        response = response_shell(message, repository, current, ["fallback"])
        response["show_checkout"] = False
        response["text"] += ("Mỗi tin nhắn mình xử lý tối đa 4 yêu cầu hoặc loại thông tin. "
            "Bạn chia thành hai tin giúp mình nhé. Mình chưa thay đổi hoặc gửi yêu cầu đặt bánh.")
        with storage_connection if storage_connection is not None else nullcontext():
            finish_turn(current, original_message, response, storage_connection)
        return turn_result(current, response, attempts=attempts)
    from app.order_nlu import normalize_bundle_preferences
    proposal = normalize_bundle_preferences(message, proposal, current)
    grounding = check_turn_grounding(message, proposal, repository, current)
    if grounding:
        return failed_turn(message, repository, conversation, grounding, attempts)
    if (advice_selection is None and len(proposal.requests) == 1
            and proposal.requests[0].advice == "more"
            and not proposal.requests[0].filters.model_dump(exclude_none=True)):
        advice_selection = more_advice_selection(current)
    try:
        proposal = apply_advice_selection(proposal, advice_selection, filter_map=QUERY_FILTER_MAP)
    except ValueError:
        return failed_turn(message, repository, conversation, "invalid_advice_selection", attempts)
    proposal = continue_order_request(current, proposal, message)
    # Ý nối tiếp do mô hình phân loại; code chỉ kiểm tra quyền dùng ngữ cảnh.
    if (proposal.continuation == "order" and current["order"]["state"] not in {"COLLECTING", "REVIEW"}
            and not current.get("pending_order_request")
            and not (current["order"].get("submission") and
                     (proposal.action == "start_order" or proposal.order_operation == "add_product"))):
        return failed_turn(message, repository, conversation, "no_pending_order", attempts)
    if proposal.continuation in {"information", "entity"} and (
        proposal.action != "none" or proposal.order_update or proposal.order_operation != "none"
        or "order_request" in proposal.intents
    ):
        return failed_turn(message, repository, conversation, "conflicting_continuation", attempts)
    proposal = continue_information(current, proposal, message)
    proposal = without_disabled_order_fields(proposal, current["order"])
    proposal, combo_question = continue_combo(current, proposal, message)
    response = response_shell(message, repository, current, list(proposal.intents))
    if combo_question:
        from app.advice import selection_sentence
        response["text"] += combo_question
        delta = proposal.requests[0].filters.model_dump(exclude_none=True)
        response["quick_replies"] = [selection_sentence({**delta,
            "product_type": c["filters"].get("product_type")}).removeprefix("Gợi ý ")
            for c in current["bundle_context"]["components"]]
        response["requires_clarification"] = True
        response["show_checkout"] = False
        with storage_connection if storage_connection is not None else nullcontext():
            finish_turn(current, original_message, response, storage_connection)
        return turn_result(current, response, attempts=attempts)
    # Áp dụng delta nhu cầu trước khi lập truy vấn: clear_slots không để lại filter cũ.
    # ID đơn vẫn chỉ được giải/kiểm tra ở repository sau bước này.
    current["needs"] = merge_preferences(current, proposal, None, response["data_mode"])
    current_turn, query_tasks, order_proposal, order_resolution = resolve_message_scopes(current, proposal, repository, message)
    # Mỗi thành phần bundle là một suất món, không gộp mất số lượng.
    if proposal.bundle_budget is None:
        query_tasks = deduplicate_information_tasks(query_tasks)
    bundle_tasks = [task for task in query_tasks if "recommendation" in task["scope"]["intents"]]
    use_bundle = (proposal.bundle_budget is not None or
        (2 <= len(bundle_tasks) <= 4 and proposal.action == "none"
         and all(t["request"].intents == ["recommendation"]
                 and t["request"].reference == "none"
                 and t["request"].price_preference == "none"
                 and not any(k in t["scope"]["filters"] for k in ("max_price_vnd", "min_price_vnd"))
                 for t in bundle_tasks)))
    if use_bundle:
        # Ngân sách tổng không được ghi thành trần giá riêng cho mọi món.
        for task in bundle_tasks:
            task["scope"]["quantity"] = task["request"].quantity
        current_turn["bundle_budget"] = proposal.bundle_budget.model_dump() if proposal.bundle_budget else None
    selected_page = (advice_selection or {}).get("page")
    if selected_page is not None and len(query_tasks) == 1:
        # Điều kiện từ trang trước đã được kiểm chứng, không nhờ model đoán lại.
        query_tasks[0]["scope"]["filters"] = deepcopy(selected_page["filters"])
        query_tasks[0]["scope"].update(deepcopy(selected_page.get("ranking", {})))
    # Số lượng trong nhu cầu tư vấn là dữ liệu đã được validate ở lượt trước.
    # Không buộc khách nhắc lại, và không nhờ model chép số cũ vào delta mới.
    known_quantity = current["needs"].get("quantity")
    if (proposal.action == "start_order" and order_proposal.order_operation == "select_product"
            and current["order"]["state"] in {"BROWSING", "COLLECTING", "REVIEW"}
            and current["order"]["slots"]["quantity"] is None
            and order_proposal.updates.quantity is None and "quantity" not in proposal.clear_slots
            and type(known_quantity) is int and known_quantity > 0):
        order_proposal.updates = order_proposal.updates.model_copy(update={"quantity": known_quantity})
    pending_request = current.get("pending_order_request")
    if (pending_request and pending_request["operation"] == "add_product"
            and pending_request["revision"] == current["order"]["revision"]
            and (proposal.continuation == "order" or proposal.order_operation == "update_slots") and proposal.updates.quantity is not None
            and not proposal.product_mentions and proposal.action not in {"confirm", "cancel"}):
        # mô hình nhận diện câu trả lời số lượng; nối đúng thao tác đã được validate trước.
        order_proposal.order_operation = "add_product"
        order_resolution = resolve_mentions([], repository, [], "none")
        order_resolution["ids"] = list(pending_request["product_ids"])
        order_resolution["status"] = "success" if order_resolution["ids"] else order_resolution["status"]
        current_turn["order_product_ids"] = list(order_resolution["ids"])
    if (pending_request and pending_request["revision"] == current["order"]["revision"]
            and proposal.continuation == "order" and order_resolution["ids"]
            and order_proposal.order_operation == pending_request["operation"]):
        order_proposal.updates = TurnUpdates(**{**pending_request.get("updates", {}),
            **order_proposal.updates.model_dump(exclude_none=True)})
        selections = order_resolution.get("item_selections", [])
        if len(selections) == 1 and selections[0]["quantity"] is None:
            selections[0]["quantity"] = pending_request.get("quantity")
    resolutions = [order_resolution, *(task["resolution"] for task in query_tasks)]
    source_error = next((r for r in resolutions if r["status"] == "error"), None)
    if source_error:
        return failed_turn(message, repository, conversation, source_error["error"] or "source_error", attempts, source=True)
    editing = not proposal.order_negated and (proposal.order_update or proposal.order_operation != "none" or proposal.action == "start_order" or "order_request" in proposal.intents)
    multiple_order_targets = editing and not order_resolution.get("item_selections") and (len(order_resolution["ids"]) > 1 or len(order_proposal.product_mentions) > 1)
    cart_ids = [item["product_id"] for item in order_items(current["order"]) if item["product_id"]]
    wrong_remove_target = proposal.order_operation == "remove_product" and bool(order_resolution["ids"]) and not set(order_resolution["ids"]).issubset(cart_ids)
    # Một phần chưa rõ chỉ chặn phần đó, không chặn mọi câu hỏi.
    local_ambiguity = (proposal.order_ambiguous or order_resolution["ambiguous"]
        or any(task["scope"].get("ambiguous") or task["resolution"]["ambiguous"] for task in query_tasks))
    global_ambiguity = proposal.ambiguous and not local_ambiguity
    order_blocked = editing and (global_ambiguity or proposal.order_ambiguous
        or order_resolution["ambiguous"] or multiple_order_targets or wrong_remove_target)
    # Ràng buộc tránh áp dụng cho mọi gợi ý trong cùng lượt và các lượt sau.
    # Tra cứu giá/thông tin riêng vẫn trả đúng câu hỏi, không tự biến thành đơn.
    mandatory_allergens = current["needs"]["filters"].get("exclude_allergens", [])
    for task in query_tasks:
        if mandatory_allergens and "recommendation" in task["scope"]["intents"]:
            existing = task["scope"]["filters"].get("exclude_allergens", [])
            task["scope"]["filters"]["exclude_allergens"] = list(dict.fromkeys([*existing, *mandatory_allergens]))
    response["state"] = deepcopy(current["needs"])
    pending_information, answered_tasks = [], []
    policy_llm_error = None
    policy_texts = set()
    product_texts = set()
    pagination_pages = []
    opening_used = False
    bundle_done = False
    try:
        for task in query_tasks:
            scope, resolution = task["scope"], task["resolution"]
            if global_ambiguity or scope.get("ambiguous") or resolution["ambiguous"]:
                response["requires_clarification"] = True
                response["text"] += information_clarification(task) + "\n"
                scope["status"] = "awaiting_clarification"
                pending_information.append(task["request"].model_dump())
                continue
            if use_bundle and task in bundle_tasks:
                if not bundle_done:
                    if any(t["scope"].get("ambiguous") or t["resolution"]["ambiguous"] for t in bundle_tasks):
                        response["requires_clarification"] = True
                        response["text"] += "Mình cần làm rõ các món trước khi ghép combo theo ngân sách.\n"
                    else:
                        bundle = recommend_bundles(repository,
                            [{"filters": t["scope"]["filters"], "quantity": t["request"].quantity} for t in bundle_tasks],
                            proposal.bundle_budget, response["data_mode"])
                        response["catalog_status"] = bundle["status"]
                        if bundle["status"] == "error":
                            raise ValueError(bundle["error"] or "source_error")
                        if bundle["status"] == "unconfigured":
                            response["text"] += "Chưa có menu để ghép combo và kiểm tra tổng giá.\n"
                        elif not bundle["groups"]:
                            response["text"] += "Mình chưa tìm được combo phù hợp với các món và ngân sách này. Bạn muốn đổi món, hương vị hay điều chỉnh ngân sách thế nào?\n"
                        else:
                            response["text"] += bundle_summary(bundle["groups"], proposal.bundle_budget) + "\n"
                            response["recommendation_groups"] = bundle_cards(bundle["groups"], proposal.bundle_budget)
                            current["bundle_context"] = {
                                "budget": proposal.bundle_budget.model_dump() if proposal.bundle_budget else None,
                                "components": [{"filters": deepcopy(t["scope"]["filters"]),
                                                "quantity": t["request"].quantity,
                                                "product_mentions": list(t["request"].product_mentions)}
                                               for t in bundle_tasks]}
                            for index, component_task in enumerate(bundle_tasks):
                                component_task["scope"]["result_product_ids"] = list(dict.fromkeys(
                                    g["items"][index]["product"]["id"] for g in bundle["groups"]))
                            by_id = {}
                            for group in bundle["groups"]:
                                for item in group["items"]:
                                    product, variant = item["product"], item["variant"]
                                    shown = by_id.setdefault(product["id"], {**deepcopy(product), "variants": []})
                                    if variant["id"] not in {v["id"] for v in shown["variants"]}:
                                        shown["variants"].append(deepcopy(variant))
                            response["products"].extend(by_id.values())
                        current["advice_pending"], current["advice_page"] = None, None
                    bundle_done = True
                scope["status"] = "answered" if response["catalog_status"] == "success" else "insufficient_data"
                answered_tasks.append(task)
                continue
            if scope["intents"] == ["policy"]:
                policy, error = answer_policy_request(scope.get("question") or message,
                    knowledge_repository, base_url, current["model"], max(0, deadline - monotonic()))
                response["policy"] = merge_policy_responses(response["policy"], policy)
                if policy["text"] not in policy_texts:
                    response["text"] += policy["text"] + "\n"
                    policy_texts.add(policy["text"])
                scope["status"] = "answered" if policy["status"] == "answered" else "insufficient_data"
                policy_llm_error = policy_llm_error or error
                if policy["error"] or error:
                    response["error"] = policy["error"] or error
                    order_blocked = True  # Không ghi đơn khi model/nguồn chính sách lỗi.
                answered_tasks.append(task)
                continue
            reply = deepcopy(response)
            reply.update(text="", products=[], error=None)
            product_answer(repository, current, task["proposal"], reply, scope, pagination_pages=pagination_pages)
            if reply["text"] not in product_texts:
                if len(query_tasks) > 1 and "recommendation" in task["scope"]["intents"]:
                    group_label = {"cream_cake": "Bánh kem", "mini": "Bánh ngọt nhỏ", "tea": "Trà",
                                   "coffee": "Cà phê", "cake": "Các loại bánh", "drink": "Đồ uống"}.get(
                                       task["scope"]["filters"].get("product_type"))
                    if group_label:
                        response["text"] += group_label + ":\n"
                response["text"] += reply["text"] + "\n"
                product_texts.add(reply["text"])
            if reply.get("quick_replies"):
                response["quick_replies"] = reply["quick_replies"]
            response["catalog_status"] = reply["catalog_status"]
            response["requires_clarification"] |= reply["requires_clarification"]
            scope["status"] = "answered" if reply["catalog_status"] == "success" else "insufficient_data"
            answered_tasks.append(task)
            for product in reply["products"]:
                existing = next((p for p in response["products"] if p["id"] == product["id"]), None)
                if existing:
                    variant_ids = {v["id"] for v in existing["variants"]}
                    existing["variants"].extend(deepcopy(v) for v in product["variants"] if v["id"] not in variant_ids)
                else:
                    response["products"].append(deepcopy(product))
            if resolution["ids"] and resolution.get("unresolved_mentions"):
                response["text"] += "Chưa tìm thấy dữ liệu cho: " + ", ".join(resolution["unresolved_mentions"]) + ". Chưa đủ thông tin để báo giá hoặc xác nhận bánh này.\n"
        if pagination_pages:
            has_more = save_advice_pages(current, pagination_pages, advice_selection)
            response["quick_replies"] = [MORE_ADVICE_LABEL] if has_more else []
        # Chỉ giữ câu cần chọn/làm rõ. Thiếu dữ liệu nguồn không yêu cầu khách lặp lại câu đã rõ.
        if query_tasks:
            current["pending_information_request"] = pending_information or None
            product_tasks = [task for task in answered_tasks if task["scope"]["intents"] != ["policy"]]
            if product_tasks:
                focused = list(dict.fromkeys(identifier for task in product_tasks for identifier in task["resolution"]["ids"]))
                if not focused and "recommendation" in proposal.intents:
                    focused = [p["id"] for p in response["products"]]
                current["shown_products"] = deepcopy(response["products"])
                # Nhóm được hỏi rõ vẫn là chủ đề khi chưa có kết quả.
                product_types = {task["scope"]["filters"].get("product_type") for task in product_tasks}
                if product_types == {None}:
                    product_types = {product.get("product_type") for product in response["products"]}
                current["discussion_context"] = {"focus_product_ids": focused,
                    "focus_product_terms": [name for task in product_tasks for name in task["scope"]["product_mentions"]],
                    "product_type": next(iter(product_types)) if len(product_types) == 1 else None}
            information_tasks = [task for task in query_tasks if task["scope"]["intents"] != ["policy"]]
            if information_tasks:
                offered = list(dict.fromkeys(
                    identifier for task in information_tasks
                    for identifier in (task["resolution"]["ids"] or
                                       [p["id"] for p in task["resolution"].get("candidates", [])])))
                if not offered and not pending_information:
                    offered = [p["id"] for p in response["products"]]
                if (current["product_choices"]["product_ids"] and all(
                        "recommendation" not in task["scope"]["intents"]
                        and not task["scope"]["product_mentions"] and task["scope"]["reference"] != "none"
                        for task in information_tasks)):
                    offered = list(current["product_choices"]["product_ids"])
                current["product_choices"] = {
                    "product_ids": offered,
                    "intents": list(dict.fromkeys(intent for task in information_tasks for intent in task["scope"]["intents"])),
                    "selection_required": bool(pending_information),
                }
        elif proposal.continuation == "none" and proposal.action != "none":
            current["pending_information_request"] = None
        if not query_tasks and not order_blocked and (order_proposal.product_mentions or proposal.reference != "none"):
            current["discussion_context"] = {"focus_product_ids": list(order_resolution["ids"]),
                "focus_product_terms": list(order_proposal.product_mentions)}
    except ValueError:
        return failed_turn(message, repository, conversation, "source_error", attempts, source=True)
    if "greeting" in proposal.intents:
        response["text"] += "Chào bạn!\n"
    if "out_of_scope" in proposal.intents:
        response["text"] += "Mình hỗ trợ thông tin sản phẩm và yêu cầu đặt bánh.\n"
    if order_blocked and response["error"] and editing:
        response["text"] += "Phần đặt bánh chưa được thực hiện do lỗi xử lý; bản nháp được giữ nguyên.\n"
    if order_blocked and not response["error"]:
        response["requires_clarification"] = True
        if multiple_order_targets:
            response["text"] += "Phần đặt bánh cần gắn số lượng với từng món; mình giữ các thông tin đã rõ.\n"
        elif wrong_remove_target:
            response["text"] += "Bánh yêu cầu xóa không trùng bánh trong bản nháp; mình chưa xóa món nào.\n"
        else:
            choices = "; ".join(dict.fromkeys(product["name"] for product in order_resolution.get("candidates", [])))
            quantity = proposal.updates.quantity
            if len(proposal.order_items) == 1 and proposal.order_items[0].reference not in {"both", "all"}:
                quantity = proposal.order_items[0].quantity or quantity
            if quantity is None and pending_request:
                quantity = pending_request.get("quantity")
            if quantity is not None:
                response["text"] += f"Mình giữ số lượng {quantity} đã ghi nhận. "
            response["text"] += ("Phần đặt bánh: bạn chọn sản phẩm nào trong " + choices + "?\n" if choices
                else "Phần đặt bánh còn chưa rõ sản phẩm hoặc thông tin cần đổi; mình giữ bản nháp hiện tại.\n")
        if current["order"].get("review") and not current["order"].get("submission"):
            current["order"].update(state="COLLECTING", review=None, revision=current["order"]["revision"] + 1)
            response["text"] += "Bản REVIEW cũ đã mất hiệu lực do yêu cầu sửa còn chưa rõ.\n"
        if proposal.order_operation in {"select_product", "add_product", "remove_product"}:
            # Giá trị này đã qua grounding ở lượt hiện tại. Chỉ gắn quantity nếu
            # một tên/alias chưa được phân giải; nhiều món chưa liên kết thì giữ trường dùng chung.
            remembered = {k: v for k, v in order_proposal.updates.model_dump(exclude_none=True).items()
                if k in current["order"]["slots"] and k not in {"cake_need", "product_id", "size", "toppings", "cake_text"}
                and (k != "quantity" or len(order_proposal.product_mentions) <= 1)}
            previous_pending = current.get("pending_order_request") or {}
            quantity = proposal.updates.quantity
            if len(proposal.order_items) == 1 and proposal.order_items[0].reference not in {"both", "all"}:
                quantity = proposal.order_items[0].quantity or quantity
            same_request = (previous_pending.get("operation") == proposal.order_operation
                and (proposal.continuation == "order"
                     or previous_pending.get("product_mentions") == list(order_proposal.product_mentions)))
            if same_request:
                remembered = {**previous_pending.get("updates", {}), **remembered}
                quantity = quantity or previous_pending.get("quantity")
            if quantity is not None:
                remembered["quantity"] = quantity
            candidates = order_resolution.get("candidates", [])
            if not candidates and same_request:
                candidates = previous_pending.get("candidates", [])
            current["pending_order_request"] = {"operation": proposal.order_operation,
                "product_ids": list(order_resolution["ids"]), "revision": current["order"]["revision"],
                "product_mentions": list(order_proposal.product_mentions),
                "candidates": deepcopy(candidates), "quantity": quantity,
                "items": [item.model_dump(exclude_none=True) for item in proposal.order_items],
                "updates": remembered}
    current["unknown_streak"] = current["unknown_streak"] + 1 if list(proposal.intents) == ["fallback"] else 0
    current_turn["requests"] = [deepcopy(task["scope"]) for task in query_tasks]
    if (not use_bundle and any(r.search_scope == "new" and
            "recommendation" in r.intents for r in proposal.requests)):
        current.pop("bundle_context", None)
    current["current_request"] = deepcopy(current_turn)
    try:
        with storage_connection if storage_connection is not None else nullcontext():
            if storage_connection is not None:
                storage_connection.execute("BEGIN IMMEDIATE")
                save_conversation(storage_connection, current)
            order_text = ""
            order_outcome = {"changed": False}
            if not order_blocked and order_tools is not None:
                order_text = advance_order(current, order_proposal, order_resolution, message, order_tools, repository, outcome=order_outcome)
                if order_text:
                    response["text"] += "\n" + order_text
                if order_outcome.get("requires_clarification"):
                    response["requires_clarification"] = True
                if order_outcome["changed"] and not query_tasks and order_resolution["ids"]:
                    current["discussion_context"] = {
                        "focus_product_ids": list(order_resolution["ids"]),
                        "focus_product_terms": list(order_proposal.product_mentions)}
                if current["unknown_streak"] >= 2:
                    current["order"], text = request_handoff(current["order"], order_tools, "two_unknown_turns", current["needs"])
                    response["text"] += "\n" + text
            if list(proposal.intents) == ["fallback"] and not response["requires_clarification"] and not query_tasks and not order_text and not response["text"].split("\n", 1)[-1].strip():
                response["text"] += "\nMình chưa hiểu yêu cầu. Bạn có thể nói rõ loại bánh, nhu cầu hoặc thông tin cần hỏi."
            # Không nối câu hỏi size/đặt hàng sau câu trả lời thông tin.
            # pending_order_question vẫn lưu riêng để tiếp tục khi khách muốn.
            if not response["text"].split("\n", 1)[-1].strip() and not response["requires_clarification"]:
                response["text"] += "Bạn muốn biết giá, thông tin bánh hay bắt đầu đặt bánh?"
            opening = proposal.response_opening
            allowed_opening = (
                opening == "Mình kiểm tra thông tin cho bạn nhé." and answered_tasks
                or opening == "Mình đã ghi nhận nhu cầu này." and order_outcome["changed"] and current["order"]["state"] == "COLLECTING"
                or opening == "Mình chưa đủ thông tin để kết luận." and response["requires_clarification"])
            if allowed_opening and not response.get("recommendation_groups"):
                opening_used = True
                label, separator, body = response["text"].partition("\n")
                response["text"] = label + separator + opening + "\n" + body
            response["show_checkout"] = bool(not proposal.order_negated and (
                "order_request" in proposal.intents or proposal.action in {"review", "confirm", "cancel"}))
            remember_request(current, proposal, current_turn, response["requires_clarification"])
            finish_turn(current, original_message, response, storage_connection)
    except sqlite3.Error:
        return failed_turn(message, repository, conversation, "storage_error", attempts, source=True)
    result = turn_result(current, response, engine="llm_error" if policy_llm_error else ("source_error" if response["error"] else chat_mode), error=policy_llm_error, attempts=attempts, current_turn=current_turn)
    if opening_used:
        result["phrasing_status"] = "success"
    return result


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
