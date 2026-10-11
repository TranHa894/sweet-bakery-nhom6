"""Schema nội bộ dùng dictionary; không phụ thuộc JSON hoặc database."""

from typing import Callable, Literal, TypedDict, NotRequired, Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

QueryStatus = Literal["unconfigured", "no_results", "success", "error"]
StockStatus = Literal["in_stock", "out_of_stock", "preorder", "unknown"]
Intent = Literal[
    "greeting", "price", "size", "flavor", "availability",
    "recommendation", "policy", "order_request", "fallback",
    "allergen", "topping", "storage", "description",
]


class LLMNLU(BaseModel):
    """Dữ liệu LLM đề xuất; không có product_id, giá bán hoặc tồn kho."""

    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)

    intents: list[Intent] = Field(min_length=1, max_length=9)
    product_mentions: list[str] = Field(max_length=10)
    budget_vnd: int | None = Field(ge=0)
    flavor: str | None
    servings: int | None = Field(ge=1)
    quantity: int | None = Field(ge=1)
    size: str | None
    price_inclusive: bool


Opening = Literal[
    "Mình đã ghi nhận yêu cầu của bạn.",
    "Mình sẽ đối chiếu nhu cầu với nguồn dữ liệu đang chọn.",
    "Bạn hãy làm rõ nhu cầu để mình tiếp tục.",
]


class LLMOpening(BaseModel):
    """LLM chọn lời mở đầu; không được tự viết lại các thông tin nghiệp vụ."""

    model_config = ConfigDict(strict=True, extra="forbid")
    opening: Opening


class LLMOrderSlots(BaseModel):
    """Mong muốn khách nêu trong câu hiện tại; không có ID/giá/confirmed."""

    model_config = ConfigDict(strict=True, extra="forbid")
    product_mentions: list[str] = Field(max_length=10)
    cake_need: str | None
    size: str | None
    quantity: int | None = Field(ge=1)
    toppings: list[str] | None
    cake_text: str | None
    pickup_at: str | None
    fulfillment: Literal["pickup", "delivery"] | None
    name: str | None
    phone: str | None
    address: str | None
    needs_clarification: bool


class TurnUpdates(BaseModel):
    """None = không đề cập; xóa dùng clear_slots. Không có ID/giá bán/stock."""

    model_config = ConfigDict(strict=True, extra="forbid")
    cake_need: str | None = Field(default=None, max_length=500)
    size: str | None = Field(default=None, max_length=100)
    quantity: int | None = Field(default=None, ge=1, le=1000)
    toppings: list[str] | None = Field(default=None, max_length=10)
    cake_text: str | None = Field(default=None, max_length=500)
    pickup_at: str | None = Field(default=None, max_length=100)
    fulfillment: Literal["pickup", "delivery"] | None = None
    name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=300)
    budget_vnd: int | None = Field(default=None, ge=0)
    price_inclusive: bool | None = None
    flavor: str | None = Field(default=None, max_length=100)
    servings: int | None = Field(default=None, ge=1)
    occasion: str | None = Field(default=None, max_length=100)
    allergens: list[str] | None = Field(default=None, max_length=10)
    available_only: bool | None = None


SlotName = Literal["product", "cake_need", "size", "quantity", "toppings", "cake_text", "pickup_at", "fulfillment", "name", "phone", "address", "budget_vnd", "flavor", "servings", "occasion", "allergens"]

Reference = Literal["none", "last", "first", "second", "cheaper", "order"]


class InformationRequest(BaseModel):
    """Một câu hỏi có đối tượng riêng; size ở đây chỉ lọc tra cứu, không sửa đơn."""

    model_config = ConfigDict(strict=True, extra="forbid")
    intents: list[Literal["price", "size", "flavor", "availability", "recommendation", "allergen", "topping", "storage", "description"]] = Field(min_length=1, max_length=9)
    product_mentions: list[str] = Field(max_length=10)
    reference: Reference = "none"
    size: str | None = Field(default=None, max_length=100)


class LLMTurn(BaseModel):
    """Một kết quả hiểu cho cả hỏi đáp/lệnh/đặt bánh; code thực hiện hành động."""

    model_config = ConfigDict(strict=True, extra="forbid")
    intents: list[Intent] = Field(min_length=1, max_length=13)
    action: Literal["none", "start_order", "review", "confirm", "cancel", "handoff"]
    order_operation: Literal["none", "select_product", "add_product", "remove_product", "update_slots"] = Field(
        default="none", description="Explicit order operation. MUST be none without order_request intent. Select=start/replace, add=append, remove=delete, update_slots=set details. Information questions never edit the order.")
    product_mentions: list[str] = Field(max_length=10, description="Exact cake NAME/alias phrases in CURRENT message, especially when asking price/size. Retain ALL names mentioned; not verified IDs. Use [] only when no cake name is mentioned.")
    order_product_mentions: list[str] = Field(default_factory=list, max_length=10,
        description="ONLY cake names explicitly chosen to add/change/start the ORDER, not cakes asked about. [] for information-only or slot answers without cake names.")
    reference: Reference = Field(
        description="none when CURRENT message names cakes; last for implicit/current-topic references; order ONLY for explicit reference to the order draft. Never combine old draft names with current mentions.")
    updates: TurnUpdates
    clear_slots: list[SlotName] = Field(max_length=17)
    ambiguous: bool
    handoff_reason: Literal["none", "customer_requested", "severe_allergy", "complaint", "unsupported_business"]
    order_update: bool = Field(default=False, description="True only for an explicit order change or missing-slot answer; asking price/storage about another cake is NOT an order change.")
    requests: list[InformationRequest] = Field(default_factory=list, max_length=8,
        description="ONLY explicitly asked information queries. [] for order-only messages, including named cakes or slot answers. Each request intent MUST be declared in top-level intents. Bind its own names/reference/size; no negated targets or order edits.")

    @model_validator(mode="after")
    def declared_request_intents(self):
        if any(not set(request.intents).issubset(self.intents) for request in self.requests):
            raise ValueError("request intents must also be declared in top-level intents")
        if self.order_operation != "none" and "order_request" not in self.intents:
            raise ValueError("order_operation needs order_request intent")
        return self


class SlotChange(BaseModel):
    """Dạng HTTP gọn: chỉ liệt kê trường thay đổi, không sinh 17 key null."""

    model_config = ConfigDict(strict=True, extra="forbid")


class TextSlotChange(SlotChange):
    field: Literal["cake_need", "size", "cake_text", "pickup_at", "fulfillment", "name", "phone", "address", "flavor", "occasion"]
    value: str


class NumberSlotChange(SlotChange):
    field: Literal["quantity", "budget_vnd", "servings"]
    value: int = Field(ge=0)


class ListSlotChange(SlotChange):
    field: Literal["toppings", "allergens"]
    value: list[str]


class BoolSlotChange(SlotChange):
    field: Literal["price_inclusive", "available_only"]
    value: bool


class LLMWireTurn(LLMTurn):
    updates: list[Annotated[TextSlotChange | NumberSlotChange | ListSlotChange | BoolSlotChange,
                           Field(discriminator="field")]] = Field(max_length=17)


class SourceQuote(BaseModel):
    """LLM chỉ chọn source_id và trích đoạn, không tự viết chính sách mới."""

    model_config = ConfigDict(strict=True, extra="forbid")
    source_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=4000)


class RAGAnswer(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    supported: bool
    quotes: list[SourceQuote] = Field(max_length=3)


PolicyClause = TypedDict("PolicyClause", {
    "id": str, "title": str, "content": str, "version": str, "is_mock": bool,
})
KnowledgeResult = TypedDict("KnowledgeResult", {
    "status": QueryStatus, "knowledge_mode": str, "is_mock": bool,
    "clauses": list[PolicyClause], "corpus_sha256": str | None, "error": str | None,
})
KnowledgeChunk = TypedDict("KnowledgeChunk", {
    "source_id": str, "title": str, "content": str, "version": str,
    "is_mock": bool, "score": float,
})
RetrievalResult = TypedDict("RetrievalResult", {
    "status": QueryStatus, "knowledge_mode": str, "is_mock": bool,
    "chunks": list[KnowledgeChunk], "corpus_sha256": str | None,
    "retriever_version": str, "error": str | None,
})
PolicyResponse = TypedDict("PolicyResponse", {
    "text": str, "knowledge_mode": str, "is_mock": bool,
    "status": Literal["unconfigured", "no_results", "answered", "insufficient", "error"],
    "source_ids": list[str], "citations": list[dict], "retrieval": RetrievalResult,
    "engine": Literal["rule", "ollama", "rule_fallback", "not_used"],
    "error": str | None, "llm_error": str | None, "attempts": int,
})
RAGExtractionResult = TypedDict("RAGExtractionResult", {
    "data": RAGAnswer | None, "error": str | None, "attempts": int,
})


ChatMessage = TypedDict("ChatMessage", {"role": Literal["user", "assistant", "system"], "content": str})
LLMCallResult = TypedDict("LLMCallResult", {
    "ok": bool, "content": str | None, "error": str | None,
    "model": str | None, "http_status": int | None,
})
LLMExtractionResult = TypedDict("LLMExtractionResult", {
    "data": LLMNLU | None, "error": str | None, "attempts": int, "repaired": bool,
})

Variant = TypedDict("Variant", {
    "id": str, "size": str | None, "price_vnd": int | None,
    "servings": int | None, "stock_status": StockStatus,
})
Product = TypedDict("Product", {
    "id": str, "name": str, "aliases": list[str], "category": str,
    "description": str, "flavor": str | None, "variants": list[Variant],
    "allergen": list[str] | None, "customization": list[str] | None,
    "min_lead_hours": int | None, "source": str, "is_mock": bool,
    "active": NotRequired[bool], "is_demo": NotRequired[bool],
    "occasions": NotRequired[list[str]], "allergen_info": NotRequired[dict],
    "storage": NotRequired[str], "shelf_life_hours": NotRequired[int],
    "topping_options": NotRequired[list[dict]],
})
SearchFilters = TypedDict("SearchFilters", {
    "query": str, "product_ids": list[str], "flavor": str,
    "max_price_vnd": int, "price_inclusive": bool, "servings": int, "size": str,
    "occasion": str, "exclude_allergens": list[str], "available_only": bool,
}, total=False)
CurrentTurn = TypedDict("CurrentTurn", {
    "intents": list[Intent], "product_mentions": list[str], "reference": str,
    "product_ids": list[str], "filters": SearchFilters,
    "requests": NotRequired[list[dict]], "order_product_ids": NotRequired[list[str]],
})
ConversationContext = TypedDict("ConversationContext", {
    "focus_product_ids": list[str], "focus_product_terms": list[str],
})
SearchResult = TypedDict("SearchResult", {
    "status": QueryStatus, "data_mode": str,
    "products": list[Product], "error": str | None,
})
ProductResult = TypedDict("ProductResult", {
    "status": QueryStatus, "data_mode": str,
    "product": Product | None, "error": str | None,
})
CatalogCapabilities = TypedDict("CatalogCapabilities", {
    "data_mode": str, "is_mock": bool, "configured": bool,
    "policy_available": bool, "can_accept_real_orders": bool,
})
NLUResult = TypedDict("NLUResult", {
    "raw_text": str, "normalized_text": str, "intents": list[Intent],
    "product_ids": list[str], "product_terms": list[str], "query": str | None,
    "flavors": list[str], "budgets_vnd": list[int], "price_inclusive": bool,
    "servings": int | None, "quantity": int | None, "size": str | None,
    "requires_clarification": bool, "catalog_status": QueryStatus,
})
ChatState = TypedDict("ChatState", {
    "filters": SearchFilters, "quantity": int | None,
    "product_terms": list[str], "data_mode": str | None,
})
ChatResponse = TypedDict("ChatResponse", {
    "text": str, "data_mode": str, "is_mock": bool,
    "catalog_status": QueryStatus, "intents": list[Intent],
    "nlu": NLUResult, "products": list[Product], "state": ChatState,
    "requires_clarification": bool, "error": str | None, "policy": PolicyResponse | None,
})
Conversation = TypedDict("Conversation", {
    "id": str, "history": list[ChatMessage], "needs": ChatState,
    "model": str | None, "max_turns": int,
    "order": dict, "unknown_streak": int,
})
ConversationTurn = TypedDict("ConversationTurn", {
    "conversation": Conversation, "response": ChatResponse,
    "engine": Literal["rule", "ollama", "llm_error", "source_error"],
    "model": str | None, "llm_error": str | None, "nlu_attempts": int,
    "phrasing_status": Literal["not_used", "success", "fallback"],
})

ToolStatus = Literal["available", "unavailable", "unknown", "unsupported", "error"]
ToolResult = TypedDict("ToolResult", {"status": ToolStatus, "data": dict | None, "error": str | None})
OrderTools = TypedDict("OrderTools", {
    "check_availability": Callable[[dict], ToolResult],
    "calculate_quote": Callable[[dict], ToolResult],
    "submit_order_request": Callable[[dict, str], ToolResult],
    "create_handoff_ticket": Callable[[str, str, str], ToolResult],
    "get_order": Callable[[str], ToolResult],
})


def validate_product(product: Product) -> None:
    """Kiểm tra dữ liệu tại biên nguồn; dữ liệu sai gây ValueError."""
    required = set(Product.__required_keys__)
    if not isinstance(product, dict) or not required <= set(product) or set(product) - set(Product.__annotations__):
        raise ValueError("Sản phẩm phải có đầy đủ các trường của Product.")
    for key in ("id", "name", "category", "description", "source"):
        if not isinstance(product[key], str) or not product[key].strip():
            raise ValueError(f"{key} phải là chuỗi có nội dung.")
    if type(product["is_mock"]) is not bool:
        raise ValueError("is_mock phải là boolean.")
    if product["flavor"] is not None and not isinstance(product["flavor"], str):
        raise ValueError("flavor phải là chuỗi hoặc None.")
    for key in ("aliases", "allergen", "customization"):
        value = product[key]
        if value is None and key != "aliases":
            continue
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"{key} phải là danh sách chuỗi hoặc None khi cho phép.")
    lead = product["min_lead_hours"]
    if lead is not None and (type(lead) is not int or lead < 0):
        raise ValueError("min_lead_hours phải là số nguyên không âm hoặc None.")
    for flag in ("active", "is_demo"):
        if flag in product and type(product[flag]) is not bool:
            raise ValueError("Cờ sản phẩm phải là boolean.")
    if "allergen_info" in product:
        info = product["allergen_info"]
        if not isinstance(info, dict) or info.get("status") not in {"contains", "may_contain", "unknown", "not_listed"} or not isinstance(info.get("items"), list):
            raise ValueError("allergen_info sai schema.")
    if not isinstance(product["variants"], list) or not product["variants"]:
        raise ValueError("Sản phẩm phải có ít nhất một biến thể.")
    seen_ids = set()
    for variant in product["variants"]:
        if not isinstance(variant, dict) or set(variant) != set(Variant.__annotations__):
            raise ValueError("Biến thể không đúng schema Variant.")
        if not isinstance(variant["id"], str) or not variant["id"] or variant["id"] in seen_ids:
            raise ValueError("ID biến thể phải có nội dung và không trùng trong sản phẩm.")
        seen_ids.add(variant["id"])
        if variant["size"] is not None and not isinstance(variant["size"], str):
            raise ValueError("size phải là chuỗi hoặc None.")
        for key in ("price_vnd", "servings"):
            value = variant[key]
            minimum = 0 if key == "price_vnd" else 1
            if value is not None and (type(value) is not int or value < minimum):
                raise ValueError(f"{key} không hợp lệ; chưa biết phải dùng None.")
        if variant["stock_status"] not in {"in_stock", "out_of_stock", "preorder", "unknown"}:
            raise ValueError("stock_status không hợp lệ; chưa biết phải dùng unknown.")
