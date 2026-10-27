"""Form web dùng bản nháp, repository và tool hiện có; không gọi model cho nút bấm."""
from copy import deepcopy
from datetime import date
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.order_flow import order_items, create_review, confirm_review
from app.order_service import local_now, normalize_contact_value
from app.storage import fingerprint, draft_fingerprint

CONTACT_FIELDS = ("fullName", "phone", "email", "province", "ward", "addressLine")


class CheckoutItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    product_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=99)


class CheckoutForm(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    fullName: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=8, max_length=20)
    email: str = Field(default="", max_length=254)
    province: str = Field(min_length=1, max_length=100)
    ward: str = Field(min_length=1, max_length=100)
    addressLine: str = Field(min_length=5, max_length=250)
    deliveryDate: str = Field(default="", max_length=10)
    deliverySlot: Literal["", "morning", "afternoon", "evening"] = ""
    cakeMessage: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=500)
    consent: bool
    items: list[CheckoutItem] = Field(min_length=1, max_length=20)

    @field_validator("fullName", "phone", "email", "province", "ward", "addressLine", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("cakeMessage", mode="before")
    @classmethod
    def nfc(cls, value):
        return unicodedata.normalize("NFC", value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_contact(self):
        normalize_contact_value("name", self.fullName)
        self.phone = normalize_contact_value("phone", self.phone)
        if not re.fullmatch(r"(?:0[35789]\d{8}|\+84[35789]\d{8})", self.phone):
            raise ValueError("Số di động Việt Nam cần 10 số hoặc mã +84.")
        if self.email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.email):
            raise ValueError("Email chưa hợp lệ.")
        if not self.consent:
            raise ValueError("Cần đồng ý cung cấp thông tin để xử lý yêu cầu.")
        if self.deliveryDate:
            try:
                selected = date.fromisoformat(self.deliveryDate)
            except ValueError:
                raise ValueError("Ngày nhận cần định dạng YYYY-MM-DD.") from None
            if selected.isoformat() != self.deliveryDate or selected < local_now().date():
                raise ValueError("Ngày nhận không được ở quá khứ.")
        ids = [item.product_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("Mỗi sản phẩm chỉ có một dòng; hãy sửa số lượng.")
        return self


class CheckoutAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    conversation_id: str = Field(min_length=1, max_length=100)
    draft_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=0)
    action: Literal["review", "edit", "confirm", "cancel"]
    form: CheckoutForm | None = None
    confirmation_token: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def check_action(self):
        if (self.action == "review") != (self.form is not None):
            raise ValueError("Chỉ bước xem lại nhận dữ liệu form.")
        if self.action == "confirm" and not self.confirmation_token:
            raise ValueError("Cần bản xem lại hiện tại.")
        return self


class CheckoutView(BaseModel):
    stage: Literal["form", "review", "completed", "cancelled"]
    draft_id: str
    revision: int
    form: dict
    items: list[dict]
    summary: dict | None
    confirmation_token: str | None
    record_id: str | None


def form_defaults(conversation):
    draft = conversation["order"]
    values = {key: "" for key in (*CONTACT_FIELDS, "deliveryDate", "deliverySlot", "cakeMessage", "note")}
    values.update(conversation.get("checkout_contact", {}))
    values.update(draft.get("checkout_form", {}))
    values["fullName"] = draft["slots"].get("name") or values["fullName"]
    values["phone"] = draft["slots"].get("phone") or values["phone"]
    if not draft.get("checkout_form") and draft["slots"].get("cake_text"):
        values["cakeMessage"] = draft["slots"]["cake_text"]
    values.setdefault("consent", False)
    return values


def checkout_view(conversation):
    if not conversation.get("web_checkout"):
        return None
    draft = conversation["order"]
    submission = draft.get("submission")
    if draft["state"] == "BROWSING" and not conversation.get("pending_order_request"):
        return None
    if draft["state"] == "HANDOFF" and not submission:
        return None
    stage = "completed" if submission else "cancelled" if draft["state"] == "CANCELLED" else "form"
    summary = draft.get("checkout_summary")
    if draft.get("review") and summary and draft["state"] == "REVIEW":
        stage = "review"
    values = form_defaults(conversation)
    rows = order_items(draft)
    items = [{"product_id": item.get("product_id") or "", "name": item.get("name") or item.get("cake_need") or "",
              "quantity": item.get("quantity") or 1} for item in rows
             if item.get("product_id") or item.get("cake_need")]
    if not items:
        pending = conversation.get("pending_order_request") or {}
        items = [{"product_id": "", "name": "", "quantity": pending.get("quantity") or 1}]
    return {"stage": stage, "draft_id": draft["id"], "revision": draft["revision"],
            "form": values, "items": items, "summary": summary,
            "confirmation_token": draft.get("checkout_token") if stage in {"review", "completed"} else None,
            "record_id": submission["id"] if submission else None}


def price_items(repository, items):
    """Đơn giá luôn đọc server; không dùng giá client hoặc tự suy biến thể."""
    lines = []
    for item in items:
        result = repository.get_product(item["product_id"])
        if result["status"] != "success":
            raise ValueError("Chưa đọc được sản phẩm. Hãy chọn lại từ menu.")
        product = result["product"]
        if product.get("active") is False or len(product["variants"]) != 1:
            raise ValueError("Sản phẩm cần nhân viên xác minh lựa chọn trước khi gửi.")
        variant = product["variants"][0]
        if variant["price_vnd"] is None or variant["stock_status"] == "out_of_stock":
            raise ValueError("Sản phẩm chưa có giá hoặc đã hết hàng; chưa thể gửi.")
        lines.append({"product_id": product["id"], "name": product["name"],
                      "image_url": product.get("image_url"),
                      "variant_id": variant["id"], "unit_price_vnd": variant["price_vnd"],
                      "quantity": item["quantity"], "line_total_vnd": variant["price_vnd"] * item["quantity"]})
    return {"items": lines, "subtotal_vnd": sum(line["line_total_vnd"] for line in lines),
            "shipping_fee_vnd": None, "total_vnd": None,
            "notice": "Tổng tiền hàng theo menu tham khảo. Phí giao, lịch nhận và yêu cầu bổ sung cần cửa hàng xác nhận."}


def verify_checkout(draft, repository):
    """Dùng cả khi xác nhận bằng nút hoặc câu tự nhiên."""
    if not draft.get("checkout_form") or not draft.get("checkout_summary"):
        raise ValueError("Bạn điền form và xem lại thông tin trước khi xác nhận nhé.")
    form = CheckoutForm.model_validate({**draft["checkout_form"], "items": [
        {"product_id": item["product_id"], "quantity": item["quantity"]}
        for item in order_items(draft)]})
    summary = price_items(repository, [item.model_dump() for item in form.items])
    def amounts(value):
        return {**value, "items": [{k: v for k, v in row.items() if k != "image_url"}
                                   for row in value["items"]]}
    if amounts(summary) != amounts(draft["checkout_summary"]):
        raise ValueError("Giá hoặc sản phẩm đã thay đổi. Hãy quay lại form và xem lại.")
    if not draft.get("review") or draft["review"]["slots_hash"] != draft_fingerprint(draft):
        raise ValueError("Bản nháp đã thay đổi. Hãy xem lại trước khi xác nhận.")
    return summary


def apply_checkout(conversation, body, repository, tools):
    """Thao tác form có revision; route đã kiểm tra session và giữ lock riêng phiên."""
    if repository.get_capabilities().get("catalog_source") != "group_files":
        raise ValueError("Form này dùng menu website nhóm; nguồn hiện tại dùng luồng yêu cầu đang có.")
    current = deepcopy(conversation)
    current["web_checkout"] = True
    draft = current["order"]
    if body.draft_id != draft["id"] or body.revision != draft["revision"]:
        raise ValueError("Bản nháp đã thay đổi. Hãy tải lại thông tin hiện tại.")
    if draft.get("submission"):
        if body.action == "confirm" and body.confirmation_token == draft.get("checkout_token"):
            return current, "Yêu cầu này đã được lưu. Không tạo bản trùng."
        raise ValueError("Yêu cầu đã gửi; hãy bắt đầu yêu cầu mới để đặt thêm.")
    if draft["state"] not in {"COLLECTING", "REVIEW"} and not (
            draft["state"] == "BROWSING" and current.get("pending_order_request")):
        raise ValueError("Bản nháp đã hủy hoặc cần nhân viên xử lý. Hãy bắt đầu yêu cầu mới.")
    if draft.get("submission_pending"):
        if body.action != "confirm":
            raise ValueError("Kết quả gửi chưa rõ; cần xác nhận lại bằng khóa cũ trước khi sửa.")
    if body.action in {"edit", "cancel"}:
        draft.update(state="CANCELLED" if body.action == "cancel" else "COLLECTING",
                     review=None, revision=draft["revision"] + 1)
        draft.pop("checkout_token", None)
        current["pending_order_request"] = None
        return current, "Đã hủy bản nháp." if body.action == "cancel" else "Bạn sửa thông tin trong form rồi xem lại nhé."
    if body.action == "review":
        data = body.form.model_dump()
        items = data.pop("items")
        summary = price_items(repository, items)
        draft.update(state="COLLECTING", review=None, revision=draft["revision"] + 1,
                     checkout_form=data, checkout_summary=summary)
        draft["slots"].update(product_id=items[0]["product_id"], cake_need=None,
                              quantity=items[0]["quantity"], name=data["fullName"], phone=data["phone"],
                              size=None, toppings=None, cake_text=None)
        # Trường ngày/lời chúc/ghi chú ở checkout_form chỉ là yêu cầu chưa xác minh.
        draft["extra_items"] = [{"product_id": row["product_id"], "quantity": row["quantity"],
            "name": line["name"], "cake_need": None, "size": None, "toppings": None,
            "cake_text": None, "verification": {}} for row, line in zip(items[1:], summary["items"][1:])]
        draft, _ = create_review(draft, tools)
        if not draft.get("review"):
            raise ValueError("Chưa kiểm tra được bản nháp; chưa tạo yêu cầu.")
        draft["checkout_token"] = fingerprint({"draft_id": draft["id"], "revision": draft["revision"],
                                              "form": data, "summary": summary})
        current["order"] = draft
        current["checkout_contact"] = {key: data[key] for key in CONTACT_FIELDS}
        current["pending_order_request"] = None
        return current, "Bạn kiểm tra thông tin và tiền hàng bên dưới, rồi xác nhận gửi yêu cầu nhé."
    if body.confirmation_token != draft.get("checkout_token"):
        raise ValueError("Bản xem lại không còn hợp lệ.")
    verify_checkout(draft, repository)
    current["order"], text = confirm_review(draft, tools, current["needs"])
    return current, text
