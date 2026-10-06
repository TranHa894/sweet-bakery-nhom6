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
from app.conversation import handle_message, new_conversation
from app.knowledge_loader import create_knowledge_repository
from app.order_service import create_order_tools
from app.repositories.catalog import create_catalog_repository
from app.schemas import QueryStatus, StockStatus
from app.storage import load_conversation, load_order_request, open_storage, save_conversation

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
MESSAGE_MAX_LENGTH = 2000  # Giới hạn kỹ thuật của API, không là chính sách cửa hàng.
SESSION_SECONDS = 8 * 60 * 60
State = Literal["BROWSING", "COLLECTING", "REVIEW", "DEMO_CONFIRMED", "CANCELLED", "HANDOFF"]


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
    revision: int
    product_name: str | None = None
    data_mode: str
    slots: SlotsView
    verification: dict[str, Literal["verified", "unverified", "not_applicable"]]
    issues: list[str]
    quote: QuoteView | None
    availability: Literal["available", "unavailable", "unknown", "unsupported", "error"]


class ChatView(APIModel):
    conversation_id: str
    message: str
    state: State
    products: list[ProductView]
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
    conversation_id: str
    session_token: str
    expires_in_seconds: int
    data_mode: str
    knowledge_mode: str
    chat_mode: Literal["rule", "ollama"]
    state: State


class OrderRequestView(APIModel):
    id: str
    conversation_id: str
    draft_id: str
    revision: int
    kind: Literal["waiting_consultation", "demo_order"]
    slots: SlotsView
    verification: dict[str, Literal["verified", "unverified", "not_applicable"]]
    issues: list[str]
    quote: QuoteView | None
    data_mode: str
    is_mock: Literal[True]
    confirmed: bool
    is_demo: bool | None = None
    source: str | None = None
    payment_status: Literal["unpaid"] | None = None
    snapshot: dict | None = None
    order_code: str | None = None
    created_at: str | None = None

    @model_validator(mode="after")
    def check_confirmation(self):
        if self.confirmed != (self.kind == "demo_order"):
            raise ValueError("Trạng thái xác nhận không khớp loại bản ghi.")
        if self.kind == "waiting_consultation" and self.quote is not None:
            raise ValueError("Yêu cầu chờ tư vấn không có báo giá xác nhận.")
        return self


class HealthView(APIModel):
    status: Literal["ok"]
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


def make_chat_view(turn: dict, knowledge_mode: str) -> dict:
    """Chuyển kết quả controller sang contract web; không trả history/model prompt."""
    conversation, response = turn["conversation"], turn["response"]
    draft, policy = conversation["order"], response.get("policy")
    snapshot, submission = draft["review"], draft["submission"]
    review = None
    if snapshot and draft["state"] == "REVIEW" and not submission:
        review = {
            "revision": snapshot["revision"], "data_mode": snapshot["mode"],
            "slots": draft["slots"], "verification": draft["verification"],
            "issues": draft["issues"], "quote": snapshot["quote"],
            "availability": snapshot["availability"],
            "product_name": snapshot.get("product_name"),
        }
    sources = [{**citation, "is_mock": policy["is_mock"]} for citation in policy["citations"]] if policy else []
    errors = [response.get("error"), turn["llm_error"]]
    if policy:
        errors.extend([policy["error"], policy["llm_error"]])
    return {
        "conversation_id": conversation["id"], "message": response["text"],
        "state": draft["state"], "products": response["products"], "sources": sources,
        "data_mode": response["data_mode"], "knowledge_mode": knowledge_mode,
        "catalog_status": response["catalog_status"], "policy_status": policy["status"] if policy else None,
        "requires_confirmation": review is not None and (
            review["availability"] == "available" and review["quote"] is not None and not review["issues"]
            if response["data_mode"] == "local_demo" else review["availability"] != "unavailable"
        ), "review": review,
        "request_id": submission["id"] if submission and submission["kind"] == "waiting_consultation" else None,
        "demo_order_id": submission["id"] if submission and submission["kind"] == "demo_order" else None,
        "engine": turn["engine"], "errors": list(dict.fromkeys(error for error in errors if error)),
    }


def create_app(*, catalog_repository=None, knowledge_repository=None,
               db_path=config.CHATBOT_DB_PATH, chat_mode=config.CHAT_MODE,
               knowledge_mode=config.KNOWLEDGE_MODE, base_url=config.OLLAMA_BASE_URL,
               model=config.OLLAMA_MODEL, timeout=config.OLLAMA_TIMEOUT_SECONDS,
               session_seconds=SESSION_SECONDS) -> FastAPI:
    """Factory cho chạy thật/test: nguồn được truyền vào, không đổi logic chatbot."""
    catalog = catalog_repository if catalog_repository is not None else create_catalog_repository(config.CATALOG_MODE, db_path)
    knowledge = knowledge_repository if knowledge_repository is not None else create_knowledge_repository(
        knowledge_mode, db_path if knowledge_mode == "local_demo" else config.KNOWLEDGE_PATH)
    application = FastAPI(title="Chatbot bánh — thử nghiệm local", version="0.6.0")
    sessions: dict[str, dict] = {}  # Chỉ hash token; không lưu token vào SQLite/log.
    registry_lock = Lock()

    @application.middleware("http")
    async def no_cache_private_data(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
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
        return {"status": "ok", "data_mode": get_data_mode(catalog),
                "knowledge_mode": knowledge_mode, "chat_mode": chat_mode,
                "message_max_length": MESSAGE_MAX_LENGTH}

    @application.post("/api/conversations", response_model=ConversationView, status_code=201)
    def start_conversation(body: CreateConversationRequest):
        conversation = new_conversation()
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
        return {"conversation_id": conversation["id"], "session_token": token,
                "expires_in_seconds": session_seconds, "data_mode": get_data_mode(catalog),
                "knowledge_mode": knowledge_mode, "chat_mode": chat_mode, "state": "BROWSING"}

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
            tools = create_order_tools(catalog, connection, conversation["id"])
            turn = handle_message(body.message, catalog, conversation, chat_mode=chat_mode,
                                  base_url=base_url, model=model, timeout=timeout,
                                  knowledge_repository=knowledge, order_tools=tools,
                                  storage_connection=connection)
            return make_chat_view(turn, knowledge_mode)

    @application.get("/api/order-requests/{id}", response_model=OrderRequestView)
    def get_order_request(id: str, authorization: str | None = Header(default=None)):
        session = authorize(authorization)
        if len(id) > 100:
            raise HTTPException(404, "order_request_not_found")
        with session["lock"], closing(open_storage(db_path)) as connection:
            result = create_order_tools(catalog, connection, session["conversation_id"])["get_order"](id)
            if result["status"] in {"error", "unsupported", "unknown"}:
                raise HTTPException(503, "order_tool_unavailable")
            if result["status"] == "unavailable" or result["data"] is None:
                raise HTTPException(404, "order_request_not_found")
            return result["data"]

    @application.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return application


app = create_app()
