"""Hội thoại theo quy tắc; không biết file JSON hay nguồn lưu catalog."""

from copy import deepcopy

from app.nlu import analyze_message
from app.repositories.catalog import CatalogRepository, safe_search_products
from app.schemas import (
    CatalogCapabilities, ChatResponse, ChatState, NLUResult, Product, SearchResult,
)
from app.text_utils import format_vnd


def create_state() -> ChatState:
    """Tạo nhu cầu trống; controller có thể lưu state này qua storage."""
    return {"filters": {}, "quantity": None, "product_terms": [], "data_mode": None}


def update_needs(state: ChatState, nlu: NLUResult, data_mode: str) -> ChatState:
    """Trả state mới; hỏi bánh mới thì bỏ bộ lọc cũ, câu thuộc tính thì nối tiếp."""
    updated = deepcopy(state)
    if updated["data_mode"] != data_mode:
        updated["filters"].pop("product_ids", None)
    updated["data_mode"] = data_mode
    if nlu["product_ids"] or nlu["query"]:
        updated["filters"] = {}
        updated["quantity"] = None
        updated["product_terms"] = list(nlu["product_terms"])
    filters = updated["filters"]
    if nlu["product_ids"]:
        filters["product_ids"] = list(nlu["product_ids"])
    elif nlu["query"]:
        filters["query"] = nlu["query"]
    if len(nlu["flavors"]) == 1:
        filters["flavor"] = nlu["flavors"][0]
    if nlu["budgets_vnd"]:
        filters["max_price_vnd"] = nlu["budgets_vnd"][0]
        filters["price_inclusive"] = nlu["price_inclusive"]
    if nlu["servings"] is not None:
        filters["servings"] = nlu["servings"]
    if nlu["size"] is not None:
        filters["size"] = nlu["size"]
    if nlu["quantity"] is not None:
        updated["quantity"] = nlu["quantity"]
    return updated


def summarize_needs(state: ChatState) -> str:
    """Nhắc lại nhu cầu của người dùng, không khẳng định nguồn đáp ứng."""
    filters = state["filters"]
    parts = []
    if state["product_terms"]:
        parts.append("cụm bánh hỏi: " + ", ".join(state["product_terms"]))
    if "flavor" in filters:
        parts.append("vị " + filters["flavor"])
    if "max_price_vnd" in filters:
        operator = "tối đa" if filters.get("price_inclusive", True) else "dưới"
        parts.append(f"{operator} {format_vnd(filters['max_price_vnd'])}/bánh")
    if "servings" in filters:
        parts.append(f"cho {filters['servings']} người/bánh")
    if "size" in filters:
        parts.append("size " + filters["size"])
    if state["quantity"] is not None:
        parts.append(f"số lượng {state['quantity']} bánh")
    return "Đã ghi nhận nhu cầu: " + "; ".join(parts) + "." if parts else "Bạn có thể cho biết hương vị, ngân sách mỗi bánh, số người ăn và số lượng."


def describe_products(products: list[Product]) -> str:
    """Chỉ diễn đạt trường đã có trong kết quả repository."""
    stock_labels = {
        "in_stock": "còn hàng", "out_of_stock": "hết hàng",
        "preorder": "cần đặt trước", "unknown": "chưa biết tình trạng còn hàng",
    }
    lines = []
    for product in products:
        lines.append(f"- {product['name']} [{product['id']}], vị {product['flavor'] or 'chưa biết'}:")
        for variant in product["variants"]:
            price = "chưa có giá" if variant["price_vnd"] is None else format_vnd(variant["price_vnd"])
            servings = "chưa biết số người ăn" if variant["servings"] is None else f"khoảng {variant['servings']} người"
            size = variant["size"] or "chưa biết size"
            lines.append(f"  • {size}: {price}; {servings}; {stock_labels[variant['stock_status']]}.")
    return "\n".join(lines)


def make_response(
    text: str, capabilities: CatalogCapabilities, nlu: NLUResult,
    state: ChatState, result: SearchResult, clarification: bool = False,
) -> ChatResponse:
    """Mọi phản hồi đều có mode; nguồn mock luôn có nhãn dữ liệu mẫu."""
    label = f"[Nguồn: {capabilities['data_mode']}]"
    if capabilities["is_mock"]:
        label += f" [DỮ LIỆU MẪU {capabilities['data_mode']} — chỉ học và kiểm thử]"
    return {
        "text": label + "\n" + text, "data_mode": capabilities["data_mode"],
        "is_mock": capabilities["is_mock"], "catalog_status": result["status"],
        "intents": list(nlu["intents"]), "nlu": nlu, "products": result["products"],
        "state": state, "requires_clarification": clarification, "error": result["error"], "policy": None,
    }


def respond(
    message: str, repository: CatalogRepository, state: ChatState | None = None,
    *, nlu: NLUResult | None = None, include_policy_notice: bool = True,
) -> ChatResponse:
    """Xử lý một lượt; repository được truyền vào (dependency injection)."""
    state = deepcopy(state) if state is not None else create_state()
    previous_state = deepcopy(state)
    nlu = deepcopy(nlu) if nlu is not None else analyze_message(message, repository)
    try:
        capabilities = repository.get_capabilities()
    except Exception:
        capabilities = {
            "data_mode": "unknown", "is_mock": False, "configured": False,
            "policy_available": False, "can_accept_real_orders": False,
        }
        nlu["catalog_status"] = "error"
    mode = capabilities["data_mode"]
    result: SearchResult = {
        "status": nlu["catalog_status"], "data_mode": mode, "products": [], "error": None,
    }
    if result["status"] == "error":
        result["error"] = "source_error"
        return make_response("Không truy vấn được nguồn dữ liệu. Chưa thể xác nhận sản phẩm, giá hoặc còn hàng; hãy kiểm tra nguồn rồi thử lại.", capabilities, nlu, state, result)
    intents = nlu["intents"]
    policy_only = "policy" in intents and (
        all(intent in {"policy", "greeting"} for intent in intents)
        or (not nlu["product_ids"] and not nlu["query"] and not nlu["flavors"] and "order_request" not in intents)
    )
    if policy_only:
        text = "Chưa có tài liệu chính sách để đối chiếu; mình chưa đủ thông tin về giao hàng, thanh toán, đổi trả hoặc bảo quản." if include_policy_notice else ""
        return make_response(text, capabilities, nlu, state, result)
    if nlu["requires_clarification"]:
        return make_response("Mình chưa liên kết chắc các bánh và thuộc tính, hoặc có điều kiện chưa hỗ trợ. Bạn hãy nêu từng bánh kèm ngân sách, hương vị, số người ăn và số lượng; dùng số dương cho số người/số lượng/size.", capabilities, nlu, state, result, True)

    if intents != ["fallback"] and any(intent != "greeting" for intent in intents):
        state = update_needs(state, nlu, mode)
    notes = []
    if "greeting" in intents:
        notes.append("Chào bạn! Mình có thể ghi nhận nhu cầu và tra cứu catalog đang chọn.")
    if "policy" in intents and include_policy_notice:
        notes.append("Chưa có tài liệu chính sách để đối chiếu; mình chưa đủ thông tin về giao hàng, thanh toán, đổi trả hoặc bảo quản.")
    if "order_request" in intents:
        notes.append("Mình chỉ ghi nhận ý định đặt bánh; hiện chưa tạo hoặc xác nhận đơn hàng.")

    if intents == ["greeting"]:
        notes.append("Bạn muốn hỏi giá, size, hương vị hay tìm bánh theo ngân sách?")
        if mode == "empty":
            notes.append("Chưa có menu để đối chiếu.")
        return make_response("\n".join(notes), capabilities, nlu, state, result)

    if result["status"] == "unconfigured":
        notes.append(summarize_needs(state))
        notes.append("Chưa có menu để đối chiếu. Mình chưa đủ thông tin để xác nhận có bánh đáp ứng nhu cầu, giá hoặc tình trạng còn hàng.")
        return make_response("\n".join(notes), capabilities, nlu, state, result)

    if intents == ["greeting"]:
        notes.append("Bạn muốn hỏi giá, size, hương vị hay tìm bánh theo ngân sách? Chính sách chưa có tài liệu.")
        return make_response("\n".join(notes), capabilities, nlu, state, result)
    if intents == ["fallback"]:
        return make_response("Mình chưa hiểu yêu cầu. Bạn hãy hỏi giá/size một bánh, hoặc nêu hương vị, ngân sách và số người ăn.", capabilities, nlu, state, result)
    policy_without_product = (
        "policy" in intents and not nlu["product_ids"] and not nlu["query"]
        and not nlu["flavors"] and "order_request" not in intents
    )
    if policy_without_product or all(intent in {"policy", "greeting"} for intent in intents):
        return make_response("\n".join(notes), capabilities, nlu, state, result)

    result = safe_search_products(repository, state["filters"], mode)
    notes.append(summarize_needs(state))
    if result["status"] == "success":
        notes.append("Các sản phẩm/biến thể có thông tin phù hợp trong nguồn đang chọn:")
        notes.append(describe_products(result["products"]))
        if capabilities["is_mock"]:
            notes.append("Giá và tình trạng ở trên đều là mẫu mô phỏng, không xác nhận cửa hàng thật có bán.")
    elif result["status"] == "no_results":
        notes.append("Nguồn hoạt động nhưng không tìm thấy sản phẩm/biến thể phù hợp với các điều kiện đã biết. Mục chưa có giá/số người không được dùng để xác nhận điều kiện tương ứng; đây không phải kết luận cửa hàng hết hàng.")
    elif result["status"] == "unconfigured":
        notes.append("Chưa có menu để đối chiếu; chưa thể xác nhận sản phẩm, giá hoặc còn hàng.")
    else:
        return make_response("Không truy vấn được nguồn dữ liệu; chưa thể xác nhận kết quả. Hãy kiểm tra nguồn rồi thử lại.", capabilities, nlu, previous_state, result)
    return make_response("\n".join(notes), capabilities, nlu, state, result)
