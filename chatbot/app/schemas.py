"""Schema nội bộ dùng dictionary; không phụ thuộc JSON hoặc database."""

from typing import Callable, Literal, TypedDict, NotRequired, Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_INFORMATION_REQUESTS = 4
INFORMATION_INTENTS = frozenset({
    "price", "size", "flavor", "availability", "recommendation", "policy",
    "allergen", "topping", "storage", "description",
})

QueryStatus = Literal["unconfigured", "no_results", "success", "error"]
StockStatus = Literal["in_stock", "out_of_stock", "preorder", "unknown"]
ProductType = Literal["cake", "drink", "cream_cake", "mini", "tea", "coffee"]
Intent = Literal[
    "greeting", "price", "size", "flavor", "availability",
    "recommendation", "policy", "order_request", "fallback",
    "allergen", "topping", "storage", "description",
    "acknowledgement", "out_of_scope", "handoff", "complaint",
]


def validate_budget_range(lower, upper, lower_inclusive, upper_inclusive) -> None:
    """Hai cận phải tạo khoảng giá có thể thỏa; None là cận chưa được nêu."""
    if lower is None or upper is None:
        return
    if lower > upper or (lower == upper and (lower_inclusive is False or upper_inclusive is False)):
        raise ValueError("Khoảng ngân sách không hợp lệ: cận dưới phải nhỏ hơn cận trên, hoặc hai cận bằng nhau và đều bao gồm biên.")


def normalize_advice_values(value):
    """Chuẩn hóa nhãn vị từ JSON của model, không đọc/phân loại tin nhắn khách."""
    from app.text_utils import normalize_text
    if not isinstance(value, dict) or not isinstance(value.get("flavor"), str):
        return value
    aliases = {
        "fruit": ("taste_family", "fruit"), "milk_tea": ("taste_family", "milk_tea"),
        "fruit_tea": ("taste_family", "fruit_tea"), "coffee_cream": ("taste_family", "coffee_cream"),
        "trai cay": ("taste_family", "fruit"), "tra sua": ("taste_family", "milk_tea"),
        "tra trai cay": ("taste_family", "fruit_tea"),
        "kem vani trang tri": ("taste_family", "cream"),
        "ca phe kem": ("taste_family", "coffee_cream"), "ca phe va kem": ("taste_family", "coffee_cream"),
        "it ngot": ("sweetness", "low"), "ngot vua": ("sweetness", "medium"), "ngot nhieu": ("sweetness", "high"),
    }
    normalized = normalize_text(value["flavor"]).replace(",", " ").replace(".", " ")
    pair = aliases.get(" ".join(normalized.split()))
    if pair:
        field, chosen = pair
        if value.get(field) not in {None, chosen}:
            raise ValueError("Conflicting advice filters.")
        value = {**value, field: chosen, "flavor": None}
    return value


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
    min_budget_vnd: int | None = Field(default=None, ge=0)
    min_price_inclusive: bool | None = None
    product_type: ProductType | None = None
    flavor: str | None = Field(default=None, max_length=100)
    sweetness: Literal["high", "medium", "low"] | None = None
    taste_family: Literal["fruit", "chocolate", "cream", "milk_tea", "fruit_tea", "matcha", "vanilla", "coffee_cream"] | None = None
    coffee_style: Literal["strong", "creamy", "mild"] | None = None
    servings: int | None = Field(default=None, ge=1)
    occasion: str | None = Field(default=None, max_length=100)
    allergens: list[str] | None = Field(default=None, max_length=10)
    available_only: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_advice(cls, value):
        return normalize_advice_values(value)

    @model_validator(mode="after")
    def valid_budget_range(self):
        validate_budget_range(self.min_budget_vnd, self.budget_vnd, self.min_price_inclusive, self.price_inclusive)
        return self


SlotName = Literal["product", "cake_need", "size", "quantity", "toppings", "cake_text", "pickup_at", "fulfillment", "name", "phone", "address", "budget_vnd", "min_budget_vnd", "product_type", "flavor", "servings", "occasion", "allergens"]

Reference = Literal["none", "last", "first", "second", "cheaper", "order", "both", "all"]


class OrderItemSelection(BaseModel):
    """Một món AI đề xuất từ câu hiện tại; repository mới xác minh được ID."""

    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)
    product_mention: str | None = Field(default=None, min_length=1, max_length=200,
        description="Verbatim CURRENT cake name/alias; null for references. Never a verified product_id.")
    reference: Reference = Field(default="none",
        description="both means exactly 2 offered choices; all means every offered choice, never all draft items.")
    quantity: int | None = Field(default=None, ge=1, le=1000,
        description="Quantity for THIS cake. null when unknown. For both/all only explicit EACH quantity, never the number of selected cake types.")

    @model_validator(mode="after")
    def require_target(self):
        if not self.product_mention and self.reference == "none":
            raise ValueError("An order item needs a current product mention or a reference.")
        return self


class QueryConstraints(BaseModel):
    """Điều kiện riêng của một truy vấn, không phải slot đặt hàng."""

    model_config = ConfigDict(strict=True, extra="forbid")
    budget_vnd: int | None = Field(default=None, ge=0)
    price_inclusive: bool | None = None
    min_budget_vnd: int | None = Field(default=None, ge=0)
    min_price_inclusive: bool | None = None
    product_type: ProductType | None = None
    flavor: str | None = Field(default=None, max_length=100)
    sweetness: Literal["high", "medium", "low"] | None = None
    taste_family: Literal["fruit", "chocolate", "cream", "milk_tea", "fruit_tea", "matcha", "vanilla", "coffee_cream"] | None = None
    coffee_style: Literal["strong", "creamy", "mild"] | None = None
    servings: int | None = Field(default=None, ge=1)
    occasion: str | None = Field(default=None, max_length=100)
    allergens: list[str] | None = Field(default=None, max_length=10,
        description="Customer's explicit AVOIDANCE constraints, not ingredients merely asked about. None when unmentioned.")
    available_only: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_advice(cls, value):
        return normalize_advice_values(value)

    @model_validator(mode="after")
    def valid_budget_range(self):
        validate_budget_range(self.min_budget_vnd, self.budget_vnd, self.min_price_inclusive, self.price_inclusive)
        return self


class InformationRequest(BaseModel):
    """Một câu hỏi có đối tượng riêng; size ở đây chỉ lọc tra cứu, không sửa đơn."""

    model_config = ConfigDict(strict=True, extra="forbid")
    intents: list[Literal["price", "size", "flavor", "availability", "recommendation", "policy", "allergen", "topping", "storage", "description"]] = Field(min_length=1, max_length=10)
    question: str | None = Field(default=None, min_length=1, max_length=2000,
        description="Current-message clause (literal or known spelling alias), especially policy; never add a topic or order clause.")
    ambiguous: bool = Field(default=False, description="ONLY this request has an unclear target or attribute link.")
    product_mentions: list[str] = Field(max_length=10)
    reference: Reference = "none"
    price_preference: Literal["none", "lowest", "highest", "cheaper_than", "more_expensive_than"] = "none"
    advice: Literal["none", "guided", "any", "more"] = "none"
    search_scope: Literal["refine", "new"] = "refine"
    size: str | None = Field(default=None, max_length=100)
    filters: QueryConstraints = Field(default_factory=QueryConstraints)
    excluded_product_mentions: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def valid_price_preference(self):
        if self.advice != "none" and ("recommendation" not in self.intents or self.reference != "none" or self.product_mentions):
            raise ValueError("Advice is a catalog search, not a product reference or order action.")
        if self.search_scope == "new":
            if "recommendation" not in self.intents:
                raise ValueError("New search scope needs recommendation intent.")
            if self.reference != "none" or self.price_preference in {"cheaper_than", "more_expensive_than"}:
                raise ValueError("New search scope cannot reuse an old product reference or price anchor; use refine.")
        if "recommendation" not in self.intents and any(
                getattr(self.filters, field) is not None
                for field in ("product_type", "flavor", "budget_vnd", "min_budget_vnd")):
            raise ValueError("Search filters need recommendation intent. Named information must omit category/flavor/budget inferred from product names; do not add recommendation to bypass this.")
        if self.price_preference != "none" and "recommendation" not in self.intents:
            raise ValueError("Price preference needs recommendation intent.")
        if self.price_preference in {"cheaper_than", "more_expensive_than"} and self.reference == "cheaper":
            raise ValueError("Use an anchor such as last/first/second for a new catalog price comparison.")
        return self


class LLMTurn(BaseModel):
    """Một kết quả hiểu cho cả hỏi đáp/lệnh/đặt bánh; code thực hiện hành động."""

    model_config = ConfigDict(strict=True, extra="forbid")
    intents: list[Intent] = Field(min_length=1, max_length=17)
    continuation: Literal["none", "information", "order", "entity"] = Field(
        default="none", description="entity ONLY bare cake name; information short continuation of information; order pending-slot answer; none explicit new question/action.")
    action: Literal["none", "start_order", "review", "confirm", "cancel", "handoff"]
    order_operation: Literal["none", "select_product", "add_product", "remove_product", "update_slots"] = Field(
        default="none", description="Explicit order operation. MUST be none without order_request intent. Select=start/replace, add=append, remove=delete, update_slots=set details. Information questions never edit the order.")
    product_mentions: list[str] = Field(max_length=10, description="Exact cake NAME/alias phrases in CURRENT message, especially when asking price/size. Retain ALL names mentioned; not verified IDs. Use [] only when no cake name is mentioned.")
    order_reference: Reference | None = Field(default=None, description="Reference ONLY for the order target; independent of question references.")
    order_ambiguous: bool = Field(default=False, description="ONLY the order target/details are unclear, not every information request.")
    order_product_mentions: list[str] = Field(default_factory=list, max_length=10,
        description="ONLY cake names explicitly chosen to add/change/start the ORDER, not cakes asked about. [] for information-only or slot answers without cake names.")
    reference: Reference = Field(
        description="none for named current cakes; last for current topic; order for the draft; both/all ONLY offered choices. Never combine old draft names with current mentions.")
    order_items: list[OrderItemSelection] = Field(default_factory=list, max_length=6,
        description="Only explicit order selections, one entry per named cake/reference with its own quantity; [] for information only.")
    response_opening: Literal["", "Mình kiểm tra thông tin cho bạn nhé.",
        "Mình đã ghi nhận nhu cầu này.", "Mình chưa đủ thông tin để kết luận."] = ""
    updates: TurnUpdates
    clear_slots: list[SlotName] = Field(max_length=20)
    ambiguous: bool
    handoff_reason: Literal["none", "customer_requested", "severe_allergy", "complaint", "unsupported_business"]
    order_negated: bool = Field(default=False, description="True ONLY when declining an order action, e.g. không đặt A, chỉ hỏi giá. The named cake can still be the query target. No order mutations allowed.")
    order_update: bool = Field(default=False, description="True only for an explicit order change or missing-slot answer; asking price/storage about another cake is NOT an order change.")
    requests_overflow: bool = False
    # Giữ đọc payload nội bộ cũ; output LLM mới được chặn ở LLMWireTurn.
    requests: list[InformationRequest] = Field(default_factory=list, max_length=16,
        description="ONLY explicitly asked information queries. [] for order-only messages, including named cakes or slot answers. Each request intent MUST be declared in top-level intents. Bind its own names/reference/size; no negated targets or order edits.")

    @model_validator(mode="after")
    def declared_request_intents(self):
        if self.requests_overflow and (self.requests or self.action != "none" or
                self.order_operation != "none" or self.order_items or self.order_update or
                (self.updates if isinstance(self.updates, list) else self.updates.model_dump(exclude_none=True)) or self.clear_slots):
            raise ValueError("Overflow must be neutral: no requests or order updates.")
        self.intents = list(dict.fromkeys(self.intents))
        if len(self.intents) > 1 and "fallback" in self.intents:
            self.intents.remove("fallback")
        if self.order_negated and (self.action != "none" or self.order_operation != "none"
                or self.order_update or self.order_product_mentions or self.order_items or self.clear_slots):
            raise ValueError("negated order must not perform an order action")
        if self.order_items and "order_request" not in self.intents:
            raise ValueError("order_items needs order_request intent")
        if self.order_items and self.order_operation not in {"select_product", "add_product", "remove_product"}:
            raise ValueError("order_items requires explicit select_product/add_product/remove_product operation; information-only cakes must not be included.")
        if any(not set(request.intents).issubset(self.intents) for request in self.requests):
            raise ValueError("request intents must also be declared in top-level intents")
        if len(self.requests) > 1 and any(
                "recommendation" in request.intents and not request.question
                for request in self.requests):
            raise ValueError("Each recommendation in a multi-request message needs its exact current question clause, so group/flavor/budget are checked independently.")
        if self.requests:
            information_intents = {"price", "size", "flavor", "availability", "recommendation", "allergen", "topping", "storage", "description"}
            covered = {intent for request in self.requests for intent in request.intents}
            if (set(self.intents) & information_intents) - covered:
                raise ValueError("every declared product information intent needs a scoped request")
        if self.action in {"start_order", "review", "confirm", "cancel"} and "order_request" not in self.intents:
            raise ValueError("order action needs order_request intent")
        if self.order_operation != "none" and "order_request" not in self.intents:
            raise ValueError("order_operation needs order_request intent")
        return self


class SlotChange(BaseModel):
    """Dạng HTTP gọn: chỉ liệt kê trường thay đổi, không sinh 17 key null."""

    model_config = ConfigDict(strict=True, extra="forbid")


class TextSlotChange(SlotChange):
    field: Literal["cake_need", "size", "cake_text", "pickup_at", "fulfillment", "name", "phone", "address", "flavor", "occasion", "product_type"]
    value: str


class NumberSlotChange(SlotChange):
    field: Literal["quantity", "budget_vnd", "min_budget_vnd", "servings"]
    value: int = Field(ge=0)


class ListSlotChange(SlotChange):
    field: Literal["toppings", "allergens"]
    value: list[str]


class BoolSlotChange(SlotChange):
    field: Literal["price_inclusive", "min_price_inclusive", "available_only"]
    value: bool


class LLMWireTurn(LLMTurn):
    """Hỏi thông tin bỏ field rỗng; lượt đặt vẫn phải xuất đủ dữ liệu thao tác."""

    action: Literal["none", "start_order", "review", "confirm", "cancel", "handoff"] = "none"
    continuation: Literal["none", "information", "order", "entity"] = "none"
    order_operation: Literal["none", "select_product", "add_product", "remove_product", "update_slots"] = "none"
    product_mentions: list[str] = Field(default_factory=list, max_length=10)
    order_reference: Reference | None = None
    order_product_mentions: list[str] = Field(default_factory=list, max_length=10)
    order_items: list[OrderItemSelection] = Field(default_factory=list, max_length=6)
    reference: Reference = "none"
    clear_slots: list[SlotName] = Field(default_factory=list, max_length=20)
    ambiguous: bool = False
    handoff_reason: Literal["none", "customer_requested", "severe_allergy", "complaint", "unsupported_business"] = "none"
    requests_overflow: bool = Field(default=False,
        description="True when more than four information request parts or intent types; neutral fallback, no order action.")
    requests: list[InformationRequest] = Field(max_length=MAX_INFORMATION_REQUESTS)
    updates: list[Annotated[TextSlotChange | NumberSlotChange | ListSlotChange | BoolSlotChange,
                           Field(discriminator="field")]] = Field(default_factory=list, max_length=20)

    @model_validator(mode="before")
    @classmethod
    def enforce_information_limit(cls, value):
        """Chặn theo cấu trúc do LLM khai báo, không đếm ý định bằng từ khóa."""
        if not isinstance(value, dict):
            return value
        intents, requests = value.get("intents"), value.get("requests")
        valid_intents = (isinstance(intents, list)
            and all(isinstance(intent, str) and intent in Intent.__args__ for intent in intents))
        overflow = ((valid_intents and len(set(intents) & INFORMATION_INTENTS) > MAX_INFORMATION_REQUESTS)
                    or isinstance(requests, list) and len(requests) > MAX_INFORMATION_REQUESTS)
        if overflow:
            # Toàn lượt là trung tính, không thực hiện đơn một phần hoặc bỏ sót im lặng.
            return {"intents": ["fallback"], "requests_overflow": True, "requests": [],
                    "updates": [], "action": "none", "product_mentions": [], "order_items": []}
        return value

    @model_validator(mode="after")
    def explicit_order_wire_fields(self):
        if "order_request" in self.intents:
            required = {"action", "product_mentions", "order_items", "updates"}
            if not required.issubset(self.model_fields_set):
                raise ValueError("Order output must explicitly include action, product_mentions, order_items and updates.")
        return self


class SourceQuote(BaseModel):
    """LLM chỉ chọn source_id và trích đoạn, không tự viết chính sách mới."""

    model_config = ConfigDict(strict=True, extra="forbid")
    source_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=4000)


class RAGAnswer(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    supported: bool
    quotes: list[SourceQuote] = Field(max_length=3)


class RAGSentenceSelection(BaseModel):
    """Wire nội bộ: model chọn số câu; Python lấy nguyên văn từ nguồn."""

    model_config = ConfigDict(strict=True, extra="forbid")
    source_id: str = Field(min_length=1, max_length=100)
    sentence_ids: list[Annotated[int, Field(ge=1)]] = Field(min_length=1, max_length=8)


class RAGWireAnswer(BaseModel):
    """Giảm token sinh; không đổi RAGAnswer/citations trả cho chatbot/API."""

    model_config = ConfigDict(strict=True, extra="forbid")
    supported: bool
    selections: list[RAGSentenceSelection] = Field(max_length=3)


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

Variant = TypedDict("Variant", {
    "id": str, "size": str | None, "price_vnd": int | None,
    "servings": int | None, "stock_status": StockStatus,
})
Product = TypedDict("Product", {
    "id": str, "name": str, "aliases": list[str], "category": str,
    "description": str, "flavor": str | None, "variants": list[Variant],
    "product_type": NotRequired[ProductType], "flavor_source": NotRequired[str],
    "style_tags": NotRequired[list[str]], "advice_profile": NotRequired[dict], "image_url": NotRequired[str],
    "allergen": list[str] | None, "customization": list[str] | None,
    "min_lead_hours": int | None, "source": str, "is_mock": bool,
    "active": NotRequired[bool], "is_demo": NotRequired[bool],
    "occasions": NotRequired[list[str]], "allergen_info": NotRequired[dict],
    "storage": NotRequired[str], "shelf_life_hours": NotRequired[int],
    "topping_options": NotRequired[list[dict]],
})
SearchFilters = TypedDict("SearchFilters", {
    "query": str, "product_ids": list[str], "flavor": str, "sweetness": str, "taste_family": str, "coffee_style": str,
    "max_price_vnd": int, "price_inclusive": bool, "min_price_vnd": int,
    "min_price_inclusive": bool, "product_type": ProductType, "servings": int, "size": str,
    "occasion": str, "exclude_allergens": list[str], "available_only": bool, "exclude_product_ids": list[str],
}, total=False)
CurrentTurn = TypedDict("CurrentTurn", {
    "intents": list[Intent], "product_mentions": list[str], "reference": str,
    "product_ids": list[str], "filters": SearchFilters,
    "requests": NotRequired[list[dict]], "order_product_ids": NotRequired[list[str]],
    "question": NotRequired[str], "ambiguous": NotRequired[bool],
    "price_preference": NotRequired[str], "comparison_product_ids": NotRequired[list[str]],
    "search_scope": NotRequired[str], "result_product_ids": NotRequired[list[str]],
    "status": NotRequired[Literal["answered", "insufficient_data", "awaiting_clarification"]],
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
    "catalog_source": NotRequired[str], "can_create_demo_orders": NotRequired[bool],
    "optional_order_fields": NotRequired[list[str]], "disabled_order_fields": NotRequired[list[str]],
    "unsupported_search_filters": NotRequired[list[str]],
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
    "catalog_source": NotRequired[str],
})
Conversation = TypedDict("Conversation", {
    "id": str, "history": list[ChatMessage], "needs": ChatState,
    "model": str | None, "max_turns": int,
    "order": dict, "unknown_streak": int,
    "discussion_context": dict, "product_choices": NotRequired[dict], "current_request": dict | None,
    "pending_information_request": list[dict] | None, "pending_order_question": dict | None,
    "request_memory": NotRequired[list[dict]], "request_sequence": NotRequired[int],
    "pending_order_request": NotRequired[dict | None],
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
    if product.get("product_type") not in {None, "cake", "drink", "cream_cake", "mini", "tea", "coffee"}:
        raise ValueError("product_type không hợp lệ.")
    if "flavor_source" in product and not isinstance(product["flavor_source"], str):
        raise ValueError("flavor_source phải là chuỗi.")
    if "style_tags" in product and (not isinstance(product["style_tags"], list) or
            any(not isinstance(tag, str) or not tag.strip() for tag in product["style_tags"])):
        raise ValueError("style_tags phải là danh sách chuỗi có nội dung.")
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
