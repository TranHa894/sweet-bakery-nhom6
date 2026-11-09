"""API cùng origin: xác thực phiên, gọi controller cũ, không xử lý nghiệp vụ mới."""

from contextlib import closing
import hashlib
from pathlib import Path
import secrets
import sqlite3
from threading import Lock
import time
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app import config
from app.conversation import handle_message, new_conversation, response_shell, finish_turn
from app.checkout import CheckoutStart, start_checkout, CheckoutAction, CheckoutView, checkout_view, apply_checkout
from app.knowledge_loader import create_knowledge_repository
from app.order_service import create_order_tools
from app.order_flow import order_items
from app.repositories.catalog import create_catalog_repository
from app.schemas import QueryStatus, StockStatus, ProductType
from app.repositories.catalog import safe_search_products
from app.storage import load_conversation, load_order_request, open_storage, save_conversation, load_messages

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
MESSAGE_MAX_LENGTH = 2000  # Giới hạn kỹ thuật của API, không là chính sách cửa hàng.
SESSION_SECONDS = 8 * 60 * 60
State = Literal["BROWSING", "COLLECTING", "REVIEW", "DEMO_CONFIRMED", "ORDER_SUBMITTED", "CANCELLED", "HANDOFF"]


class APIModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class CreateConversationRequest(APIModel):
    """Body {}: trình duyệt không được tự chọn ID hay cấu hình nguồn."""


class ChatRequest(APIModel):
    conversation_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=MESSAGE_MAX_LENGTH)

    @model_validator(mode="after")
    def check_message(self):
        if not self.message.strip():
            raise ValueError("Tin nhắn không được chỉ có khoảng trắng.")
        return self  # Giữ nguyên chữ trên bánh, không normalize toàn input.


class VariantView(APIModel):
    id: str
    size: str | None
    price_vnd: int | None = Field(ge=0)
    servings: int | None = Field(ge=1)
    stock_status: StockStatus


class ProductView(APIModel):
    id: str
    name: str
    aliases: list[str]
    category: str
    description: str
    flavor: str | None
    product_type: ProductType | None = None
    flavor_source: str | None = None
    style_tags: list[str] = Field(default_factory=list)
    advice_profile: dict | None = None
    image_url: str | None = None
    variants: list[VariantView]
    allergen: list[str] | None
    customization: list[str] | None
    min_lead_hours: int | None = Field(ge=0)
    source: str
    is_mock: bool
    active: bool | None = None
    is_demo: bool | None = None
    occasions: list[str] | None = None
    allergen_info: dict | None = None
    storage: str | None = None
    shelf_life_hours: int | None = None
    topping_options: list[dict] | None = None


class BundleItemView(APIModel):
    product_id: str
    variant_id: str
    name: str
    source: str
    is_mock: bool
    image_url: str | None
    size: str | None
    flavor: str | None
    sweetness: str | None
    quantity: int = Field(ge=1)
    unit_price_vnd: int = Field(ge=0)
    line_total_vnd: int = Field(ge=0)

    @model_validator(mode="after")
    def correct_line_total(self):
        if self.line_total_vnd != self.quantity * self.unit_price_vnd:
            raise ValueError("Sai thành tiền món.")
        return self


class BundleView(APIModel):
    price_tier: Literal["low", "medium", "high", "single"] | None = None
    reason: str = Field(default="", max_length=500)
    remaining_budget_vnd: int | None = Field(default=None, ge=0)
    items: list[BundleItemView] = Field(min_length=2, max_length=4)
    total_vnd: int = Field(ge=0)
    budget_vnd: int | None = Field(default=None, ge=0)
    extra_needed_vnd: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def correct_total(self):
        if self.total_vnd != sum(item.line_total_vnd for item in self.items):
            raise ValueError("Sai tổng tiền nhóm.")
        if self.budget_vnd is None:
            if self.extra_needed_vnd is not None or self.remaining_budget_vnd is not None:
                raise ValueError("Thiếu ngân sách để kiểm tra tiền dư/cần thêm.")
        elif self.total_vnd > self.budget_vnd:
            if self.extra_needed_vnd != self.total_vnd - self.budget_vnd or self.remaining_budget_vnd is not None:
                raise ValueError("Sai số tiền cần thêm.")
        elif self.remaining_budget_vnd != self.budget_vnd - self.total_vnd or self.extra_needed_vnd is not None:
            raise ValueError("Sai số tiền còn dư.")
        return self


class SourceView(APIModel):
    source_id: str
    version: str
    quote: str
    is_mock: bool


class SlotsView(APIModel):
    cake_need: str | None
    product_id: str | None
    size: str | None
    toppings: list[str] | None
    quantity: int | None = Field(ge=1)
    cake_text: str | None
    pickup_at: str | None
    fulfillment: Literal["pickup", "delivery"] | None
    name: str | None
    phone: str | None
    address: str | None


class OrderItemView(APIModel):
    product_id: str | None
    cake_need: str | None
    name: str | None = None
    size: str | None
    quantity: int | None = Field(ge=1)
    toppings: list[str] | None
    cake_text: str | None
    verification: dict[str, Literal["verified", "unverified", "not_applicable"]] = Field(default_factory=dict)


class QuoteView(APIModel):
    variant_id: str
    base_price_vnd: int = Field(ge=0)
    toppings_vnd: int = Field(ge=0)
    cake_text_vnd: int = Field(ge=0)
    unit_price_vnd: int = Field(ge=0)
    quantity: int = Field(ge=1)
    delivery_fee_vnd: int = Field(ge=0)
    total_vnd: int = Field(ge=0)
    is_mock: Literal[True]


class ReviewView(APIModel):
    items: list[OrderItemView] = Field(default_factory=list)
    revision: int
    product_name: str | None = None
    data_mode: str
    slots: SlotsView
    verification: dict[str, Literal["verified", "unverified", "not_applicable"]]
    issues: list[str]
    quote: QuoteView | None
    availability: Literal["available", "unavailable", "unknown", "unsupported", "error"]


class ChatView(APIModel):
    checkout_mode: Literal["request", "order"] = "request"
    order_id: str | None = None
    show_checkout: bool = False
    checkout: CheckoutView | None = None
    conversation_id: str
    catalog_source: str
    message: str
    state: State
    products: list[ProductView]
    recommendation_groups: list[BundleView] = Field(default_factory=list, max_length=3)
    quick_replies: list[str] = Field(default_factory=list, max_length=6)
    sources: list[SourceView]
    data_mode: str
    knowledge_mode: str
    catalog_status: QueryStatus
    policy_status: str | None
    requires_confirmation: bool
    review: ReviewView | None
    request_id: str | None = None
    demo_order_id: str | None = None
    engine: str
    errors: list[str]


class ConversationView(APIModel):
    checkout_mode: Literal["request", "order"] = "request"
    conversation_id: str
    catalog_source: str
    session_token: str
    expires_in_seconds: int
    data_mode: str
    knowledge_mode: str
    chat_mode: Literal["rule", "ollama"]
    state: State


class HistoryMessageView(APIModel):
    recommendation_groups: list[BundleView] = Field(default_factory=list, max_length=3)
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class ConversationResumeView(APIModel):
    conversation_id: str
    messages: list[HistoryMessageView]
    snapshot: ChatView
    truncated: bool


class CancelOrderRequest(APIModel):
    confirmed: bool

    @model_validator(mode="after")
    def explicit_confirmation(self):
        if not self.confirmed:
            raise ValueError("Cần đồng ý rõ ràng trước khi hủy đơn.")
        return self


class OrderUpdateView(APIModel):
    order_id: str
    status: Literal["pending_confirmation","confirmed","delivering","completed","cancelled"]
    message: str
    updated_at: str
    estimate: dict | None = None
    can_cancel: bool = False


class OrderUpdatesView(APIModel):
    orders: list[OrderUpdateView]


class OrderRequestView(APIModel):
    checkout_form: dict | None = None
    checkout_summary: dict | None = None
    items: list[OrderItemView] = Field(default_factory=list)
    id: str
    conversation_id: str
    draft_id: str
    revision: int
    kind: Literal["waiting_consultation", "demo_order", "website_order"]
    slots: SlotsView
    verification: dict[str, Literal["verified", "unverified", "not_applicable"]]
    issues: list[str]
    quote: QuoteView | None
    data_mode: str
    is_mock: Literal[True]
    # Đã ghi đơn sau xác nhận của khách; trạng thái cửa hàng nằm ở order_status.
    confirmed: bool
    is_demo: bool | None = None
    source: str | None = None
    payment_status: Literal["unpaid"] | None = None
    snapshot: dict | None = None
    order_code: str | None = None
    delivery_tracking: dict | None = None
    order_status: Literal["pending_confirmation", "confirmed", "delivering", "completed", "cancelled"] | None = None
    created_at: str | None = None

    @model_validator(mode="after")
    def check_confirmation(self):
        if self.confirmed != (self.kind in {"demo_order", "website_order"}):
            raise ValueError("Trạng thái xác nhận không khớp loại bản ghi.")
        if self.kind == "waiting_consultation" and self.quote is not None:
            raise ValueError("Yêu cầu chờ tư vấn không có báo giá xác nhận.")
        return self


class CatalogView(APIModel):
    data_mode: str
    catalog_source: str
    status: QueryStatus
    products: list[ProductView]


class HealthView(APIModel):
    status: Literal["ok"]
    catalog_source: str
    data_mode: str
    knowledge_mode: str
    chat_mode: Literal["rule", "ollama"]
    message_max_length: int


def get_data_mode(repository) -> str:
    """Metadata nguồn lỗi vẫn cho tạo phiên/ghi nhận nhu cầu, không gọi là empty."""
    try:
        return repository.get_capabilities()["data_mode"]
    except Exception:
        return "unknown"


def get_catalog_source(repository) -> str:
    try:
        capabilities = repository.get_capabilities()
        return capabilities.get("catalog_source", capabilities["data_mode"])
    except Exception:
        return "unknown"


def make_chat_view(turn: dict, knowledge_mode: str, checkout_mode: str = "request") -> dict:
    """Chuyển kết quả controller sang contract web; không trả history/model prompt."""
    conversation, response = turn["conversation"], turn["response"]
    draft, policy = conversation["order"], response.get("policy")
    snapshot, submission = draft["review"], draft["submission"]
    review = None
    if snapshot and draft["state"] == "REVIEW" and not submission:
        review = {
            "revision": snapshot["revision"], "data_mode": snapshot["mode"],
            "slots": {key: None if key in draft.get("disabled_fields", []) else value for key, value in draft["slots"].items()},
            "verification": {key: value for key, value in draft["verification"].items() if key not in draft.get("disabled_fields", [])},
            "issues": draft["issues"], "quote": snapshot["quote"],
            "availability": snapshot["availability"],
            "product_name": snapshot.get("product_name"),
            "items": order_items(draft, snapshot.get("product_name")),
        }
    sources = [{**citation, "is_mock": policy["is_mock"]} for citation in policy["citations"]] if policy else []
    errors = [response.get("error"), turn["llm_error"]]
    if policy:
        errors.extend([policy["error"], policy["llm_error"]])
    return {
        "conversation_id": conversation["id"], "message": response["text"],
        "checkout_mode": checkout_mode,
        "order_id": submission["id"] if submission and submission["kind"] == "website_order" else None,
        "catalog_source": response.get("catalog_source", response["data_mode"]),
        "state": draft["state"], "products": response["products"], "sources": sources,
        "recommendation_groups": response.get("recommendation_groups", []),
        "quick_replies": response.get("quick_replies", conversation.get("quick_replies", [])),
        "data_mode": response["data_mode"], "knowledge_mode": knowledge_mode,
        "catalog_status": response["catalog_status"], "policy_status": policy["status"] if policy else None,
        "requires_confirmation": review is not None and (
            review["availability"] == "available" and review["quote"] is not None and not review["issues"]
            if response["data_mode"] == "local_demo" and not draft.get("extra_items") else review["availability"] not in {"unavailable", "error", "unsupported"}
        ), "review": review,
        "request_id": submission["id"] if submission and submission["kind"] == "waiting_consultation" else None,
        "demo_order_id": submission["id"] if submission and submission["kind"] == "demo_order" else None,
        "engine": turn["engine"], "errors": list(dict.fromkeys(error for error in errors if error)),
        "checkout": checkout_view(conversation),
        "show_checkout": bool(response.get("show_checkout", conversation.get(
            "checkout_visible", draft["state"] in {"COLLECTING", "REVIEW"} and not submission))),
    }


def create_app(*, catalog_repository=None, knowledge_repository=None,
               db_path=config.CHATBOT_DB_PATH, chat_mode=config.CHAT_MODE,
               knowledge_mode=config.KNOWLEDGE_MODE, base_url=None,
               model=None, timeout=None,
               session_seconds=SESSION_SECONDS, order_tools_factory=None, order_updates_reader=None) -> FastAPI:
    """Factory cho chạy thật/test: nguồn được truyền vào, không đổi logic chatbot."""
    endpoint, configured_model, configured_timeout = config.get_llm_settings(chat_mode)
    base_url = endpoint if base_url is None else base_url
    model = configured_model if model is None else model
    timeout = configured_timeout if timeout is None else timeout
    catalog = catalog_repository if catalog_repository is not None else create_catalog_repository(config.CATALOG_MODE, db_path)
    knowledge = knowledge_repository if knowledge_repository is not None else create_knowledge_repository(
        knowledge_mode, db_path if knowledge_mode == "local_demo" else config.KNOWLEDGE_PATH)
    application = FastAPI(title="Chatbot bánh — thử nghiệm local", version="0.6.0")
    order_factory = order_tools_factory or create_order_tools
    checkout_mode = "order" if order_tools_factory is not None else "request"
    sessions: dict[str, dict] = {}  # Chỉ hash token; không lưu token vào SQLite/log.
    registry_lock = Lock()

    @application.middleware("http")
    async def no_cache_private_data(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif (path in {"/", "/chatbot/", "/website"} or
              path.startswith("/website/") and (path.endswith("/") or Path(path).suffix == ".html")):
            # HTML mới không tiếp tục nằm trong HTTP cache sau cập nhật.
            response.headers["Cache-Control"] = "no-store"
        elif path.startswith(("/website/", "/static/")) and Path(path).suffix in {".html", ".js", ".css"}:
            response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def authorize(authorization: str | None) -> dict:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "session_required")
        token = authorization[7:]
        if not 32 <= len(token) <= 128:
            raise HTTPException(401, "invalid_session")
        digest = hashlib.sha256(token.encode()).hexdigest()
        with registry_lock:
            session = sessions.get(digest)
            if session is None or session["expires_at"] <= time.monotonic():
                sessions.pop(digest, None)
                raise HTTPException(401, "invalid_or_expired_session")
            return session

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request, exception):
        # Không echo input (có thể chứa liên hệ hoặc header do khách gửi nhầm).
        fields = [{"loc": error["loc"], "type": error["type"]} for error in exception.errors()]
        return JSONResponse(status_code=422, content={"detail": "invalid_request", "fields": fields})

    @application.exception_handler(ResponseValidationError)
    async def invalid_response(request, exception):
        return JSONResponse(status_code=500, content={"detail": "invalid_server_response"})

    @application.exception_handler(sqlite3.Error)
    async def storage_error(request, exception):
        return JSONResponse(status_code=503, content={"detail": "storage_unavailable"})

    @application.get("/health", response_model=HealthView)
    def health():
        return {"status": "ok", "catalog_source": get_catalog_source(catalog), "data_mode": get_data_mode(catalog),
                "knowledge_mode": knowledge_mode, "chat_mode": chat_mode,
                "message_max_length": MESSAGE_MAX_LENGTH}

    @application.get("/api/catalog", response_model=CatalogView)
    def read_catalog():
        result = safe_search_products(catalog, {}, get_data_mode(catalog))
        if result["status"] in {"error", "unconfigured"}:
            raise HTTPException(503, "catalog_unavailable")
        return {"data_mode": result["data_mode"], "catalog_source": get_catalog_source(catalog),
                "status": result["status"], "products": result["products"]}

    @application.post("/api/conversations", response_model=ConversationView, status_code=201)
    def start_conversation(body: CreateConversationRequest):
        conversation = new_conversation()
        conversation["web_checkout"] = get_catalog_source(catalog) == "group_files"
        token = secrets.token_urlsafe(32)  # 256 bit ngẫu nhiên; UUID chỉ là ID.
        digest = hashlib.sha256(token.encode()).hexdigest()
        with registry_lock:
            now = time.monotonic()
            for key in list(sessions):
                if sessions[key]["expires_at"] <= now:
                    del sessions[key]
            if len(sessions) >= 200:
                raise HTTPException(503, "session_capacity_reached")
            with closing(open_storage(db_path)) as connection, connection:
                save_conversation(connection, conversation)
            sessions[digest] = {"conversation_id": conversation["id"], "expires_at": now + session_seconds, "lock": Lock()}
        return {"conversation_id": conversation["id"], "session_token": token, "checkout_mode": checkout_mode,
                "catalog_source": get_catalog_source(catalog),
                "expires_in_seconds": session_seconds, "data_mode": get_data_mode(catalog),
                "knowledge_mode": knowledge_mode, "chat_mode": chat_mode, "state": "BROWSING"}

    @application.get("/api/conversations/{id}", response_model=ConversationResumeView)
    def resume_conversation(id: str, authorization: str | None = Header(default=None)):
        session = authorize(authorization)
        if id != session["conversation_id"]:
            raise HTTPException(404, "conversation_not_found")
        # Cùng lock với chat: chờ lượt đang xử lý, không gửi lại yêu cầu/đặt đơn.
        with session["lock"], closing(open_storage(db_path)) as connection:
            conversation = load_conversation(connection, id)
            if conversation is None:
                raise HTTPException(404, "conversation_not_found")
            history = load_messages(connection, id, 101, include_ids=True)
            saved_groups = conversation.get("recommendation_history", {})
            for entry in history:
                entry["recommendation_groups"] = saved_groups.get(str(entry.pop("id")), [])
            response = response_shell("", catalog, conversation)
            latest_ids = {identifier for question in (conversation.get("current_request") or {}).get("requests", [])
                          for identifier in question.get("result_product_ids", [])}
            response["products"] = [product for product in conversation.get("shown_products", [])
                                    if history and product["id"] in latest_ids]
            response["recommendation_groups"] = conversation.get("recommendation_groups", [])
            snapshot = make_chat_view({"conversation": conversation, "response": response,
                "engine": chat_mode, "llm_error": None}, knowledge_mode, checkout_mode)
            return {"conversation_id": id, "messages": history[-100:],
                    "snapshot": snapshot, "truncated": len(history) > 100}

    @application.post("/api/chat", response_model=ChatView)
    def chat(body: ChatRequest, authorization: str | None = Header(default=None)):
        session = authorize(authorization)
        if body.conversation_id != session["conversation_id"]:
            raise HTTPException(404, "conversation_not_found")
        # def route chạy trong threadpool. Connection mở/dùng/đóng cùng thread.
        # Lock riêng phiên ngăn hai lượt cùng sửa một draft/lịch sử.
        with session["lock"], closing(open_storage(db_path)) as connection:
            conversation = load_conversation(connection, session["conversation_id"])
            if conversation is None:
                raise HTTPException(404, "conversation_not_found")
            conversation["web_checkout"] = get_catalog_source(catalog) == "group_files"
            tools = order_factory(catalog, connection, conversation["id"])
            turn = handle_message(body.message, catalog, conversation, chat_mode=chat_mode,
                                  base_url=base_url, model=model, timeout=timeout,
                                  knowledge_repository=knowledge, order_tools=tools,
                                  storage_connection=connection)
            return make_chat_view(turn, knowledge_mode, checkout_mode)

    @application.post("/api/checkout/start", response_model=ChatView)
    def select_checkout(body: CheckoutStart, authorization: str | None = Header(default=None)):
        session = authorize(authorization)
        if body.conversation_id != session["conversation_id"]:
            raise HTTPException(404, "conversation_not_found")
        with session["lock"], closing(open_storage(db_path)) as connection, connection:
            conversation = load_conversation(connection, body.conversation_id)
            if conversation is None:
                raise HTTPException(404, "conversation_not_found")
            try:
                current, message = start_checkout(conversation, body, catalog)
            except ValueError as error:
                raise HTTPException(409, str(error)) from None
            response = response_shell(message, catalog, current)
            response["text"] += message
            response["show_checkout"] = True
            finish_turn(current, "Chọn món từ thẻ sản phẩm hoặc combo.", response, connection)
            return make_chat_view({"conversation": current, "response": response,
                                   "engine": "form", "llm_error": None}, knowledge_mode, checkout_mode)

    @application.post("/api/checkout", response_model=ChatView)
    def checkout(body: CheckoutAction, authorization: str | None = Header(default=None)):
        session = authorize(authorization)
        if body.conversation_id != session["conversation_id"]:
            raise HTTPException(404, "conversation_not_found")
        with session["lock"], closing(open_storage(db_path)) as connection, connection:
            conversation = load_conversation(connection, body.conversation_id)
            if conversation is None:
                raise HTTPException(404, "conversation_not_found")
            tools = order_factory(catalog, connection, conversation["id"])
            try:
                current, message = apply_checkout(conversation, body, catalog, tools)
            except ValueError as error:
                raise HTTPException(409, str(error)) from None
            response = response_shell(message, catalog, current)
            response["text"] += message
            response["show_checkout"] = True
            finish_turn(current, {"review": "Xem lại thông tin đã nhập trên form.",
                                 "edit": "Sửa thông tin yêu cầu.", "cancel": "Hủy bản nháp.",
                                 "confirm": "Xác nhận gửi yêu cầu."}[body.action], response, connection)
            return make_chat_view({"conversation": current, "response": response,
                                   "engine": "form", "llm_error": None}, knowledge_mode, checkout_mode)

    @application.get("/api/order-updates", response_model=OrderUpdatesView)
    def read_delivery_updates(authorization: str | None = Header(default=None)):
        session=authorize(authorization)
        if order_updates_reader is None:
            return {"orders":[]}
        with session["lock"],closing(open_storage(db_path)) as connection:
            return {"orders":order_updates_reader(connection,session["conversation_id"])}

    @application.post("/api/order-requests/{id}/cancel", response_model=OrderUpdateView)
    def cancel_submitted_order(id: str, body: CancelOrderRequest,
                               authorization: str | None = Header(default=None)):
        session = authorize(authorization)
        if len(id) > 100:
            raise HTTPException(404, "order_request_not_found")
        with session["lock"], closing(open_storage(db_path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            cancel = order_factory(catalog, connection, session["conversation_id"]).get("cancel_order")
            if cancel is None:
                raise HTTPException(409, {"code": "cancellation_unsupported",
                                         "message": "Nguồn đơn hiện tại chưa hỗ trợ tự hủy. Bạn nhờ nhân viên kiểm tra nhé."})
            result = cancel(id)
            if result["error"] == "order_not_found":
                raise HTTPException(404, "order_request_not_found")
            if result["status"] != "available" or result["data"] is None:
                raise HTTPException(409, {"code": result["error"],
                                         "message": result.get("message") or "Chưa hủy được đơn. Bạn có thể thử lại."})
            return result["data"]

    @application.get("/api/order-requests/{id}", response_model=OrderRequestView)
    def get_order_request(id: str, authorization: str | None = Header(default=None)):
        session = authorize(authorization)
        if len(id) > 100:
            raise HTTPException(404, "order_request_not_found")
        with session["lock"], closing(open_storage(db_path)) as connection:
            result = order_factory(catalog, connection, session["conversation_id"])["get_order"](id)
            if result["status"] in {"error", "unsupported", "unknown"}:
                raise HTTPException(503, "order_tool_unavailable")
            if result["status"] == "unavailable" or result["data"] is None:
                raise HTTPException(404, "order_request_not_found")
            return result["data"]

    @application.get("/chatbot/", include_in_schema=False)
    @application.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    group_static = config.GROUP_PROJECT_ROOT / "static"
    if group_static.is_dir():
        # Phục vụ website nhóm cùng origin; widget dùng lại trang /chatbot/.
        application.mount("/website", StaticFiles(directory=group_static, html=True), name="group_website")
    return application


app = create_app()
