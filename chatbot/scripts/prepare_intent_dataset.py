"""Tạo lại bộ câu/nhãn mô phỏng do người xây dự án ghi thủ công, không dùng LLM."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def request(intents, names=(), reference="none", size=None):
    return {"intents": list(intents), "product_mentions": list(names), "reference": reference, "size": size}


def turn(message, intents, names=(), *, action="none", updates=None, clear=(), reference="none",
         edit=False, ambiguous=False, requests=None, order_names=(), operation=None, **expected):
    item = {"message": message, "label": {"intents": list(intents), "action": action,
        "product_mentions": list(names), "reference": reference, "updates": updates or {},
        "clear_slots": list(clear), "ambiguous": ambiguous, "handoff_reason": "none",
        "order_update": edit, "requests": requests or [], "order_product_mentions": list(order_names)},
        "expected": expected}
    if operation is not None:
        item["label"]["order_operation"] = operation
    return item


def info(message, intents, names, ids, **kwargs):
    kwargs.setdefault("draft_unchanged", True)
    return turn(message, intents, names, product_ids=ids, **kwargs)


def start(message, name, identifier, **kwargs):
    return turn(message, ["order_request"], [name], action="start_order", edit=True,
                order_names=[name], order_product_id=identifier, state="COLLECTING", **kwargs)


def complete(message, date, phone, **expected):
    return turn(message, ["order_request"], ["socola"], action="start_order", edit=True,
        order_names=["socola"], updates={"quantity": 1, "size": "16 cm", "toppings": [],
        "cake_text": "", "pickup_at": date, "fulfillment": "pickup", "name": "DEMO Khách A", "phone": phone},
        state="REVIEW", order_count=0, **expected)


def build():
    sets = {"dev": [], "test": []}

    def add(split, key, turns, mode="local_demo", tags=()):
        sets[split].append({"id": split + "_" + key, "mode": mode, "tags": list(tags), "turns": turns})

    add("dev", "basics", [
        turn("Xin chào", ["greeting"], draft_unchanged=True),
        info("Bánh socola giá bao nhiêu?", ["price"], ["socola"], ["demo-001"]),
        info("Bánh dâu có những size nào?", ["size"], ["dâu"], ["demo-002"]),
        info("Bánh vani có vị gì?", ["flavor"], ["vani"], ["demo-003"]),
        info("Bánh trà xanh còn hàng không?", ["availability"], ["trà xanh"], ["demo-004"]),
        info("Giá và size bánh dâu?", ["price", "size"], ["dâu"], ["demo-002"]),
        info("Bánh socola có thành phần gây dị ứng nào?", ["allergen"], ["socola"], ["demo-001"]),
    ], tags=["price", "size", "flavor", "availability", "multi_intent"])
    add("dev", "scope", [
        start("Tôi muốn đặt bánh socola", "socola", "demo-001"),
        info("Bánh dâu giá bao nhiêu?", ["price"], ["dâu"], ["demo-002"], order_product_id="demo-001"),
        info("Bánh trong đơn giá bao nhiêu?", ["price"], [], ["demo-001"], reference="order", order_product_id="demo-001"),
        info("Bảo quản bánh dâu thế nào?", ["storage"], ["dâu"], ["demo-002"], order_product_id="demo-001"),
    ], tags=["topic_switch", "draft_isolation", "multi_turn"])
    add("dev", "reference", [
        start("Mình muốn đặt socola", "socola", "demo-001"),
        info("Bánh đó giá bao nhiêu?", ["price"], [], ["demo-001"], reference="last"),
        turn("Đổi sang bánh dâu", ["order_request"], ["dâu"], edit=True, order_names=["dâu"], order_product_id="demo-002", state="COLLECTING"),
    ], tags=["reference", "order_edit"])
    add("dev", "multiple", [
        info("Giá bánh dâu và socola?", ["price"], ["dâu", "socola"], ["demo-001", "demo-002"]),
        info("Giá dâu và hương vị socola?", ["price", "flavor"], ["dâu", "socola"], ["demo-001", "demo-002"],
             requests=[request(["price"], ["dâu"]), request(["flavor"], ["socola"])]),
        info("Giá dâu size 16 cm và socola size 20 cm?", ["price"], ["dâu", "socola"], ["demo-001", "demo-002"],
             requests=[request(["price"], ["dâu"], size="16 cm"), request(["price"], ["socola"], size="20 cm")]),
        turn("Bánh đó giá bao nhiêu?", ["price"], reference="last", ambiguous=True, clarification=True, draft_unchanged=True),
    ], tags=["multi_product", "attribute_linking", "ambiguity"])
    add("dev", "spelling", [
        info("gia dau bn?", ["price"], ["dau"], ["demo-002"]),
        info("sz socola la bao nhieu?", ["size"], ["socola"], ["demo-001"]),
        info("banh tra xanh con ko?", ["availability"], ["tra xanh"], ["demo-004"]),
        turn("tu van socola duoi 300k", ["recommendation"], ["socola"], updates={"budget_vnd": 300000, "price_inclusive": False}, product_ids=["demo-001"], draft_unchanged=True),
        info("Tôi chưa muốn đặt, chỉ hỏi giá socola", ["price"], ["socola"], ["demo-001"]),
        info("Không cần socola, xem giá vani thôi", ["price"], ["socola", "vani"], ["demo-003"], requests=[request(["price"], ["vani"])]),
    ], tags=["no_accents", "abbreviation", "negation"])
    add("dev", "slots", [
        start("Tôi đặt bánh socola", "socola", "demo-001"),
        turn("Size 16 cm nhé", ["order_request"], updates={"size": "16 cm"}, edit=True, slots={"size": "16 cm"}, state="COLLECTING"),
        turn("Hai chiếc", ["order_request"], updates={"quantity": 2}, edit=True, slots={"quantity": 2}, state="COLLECTING"),
        turn("Không topping", ["order_request"], updates={"toppings": []}, edit=True, slots={"toppings": []}, state="COLLECTING"),
        turn("Ghi chữ 'Chúc vui'", ["order_request"], updates={"cake_text": "Chúc vui"}, edit=True, slots={"cake_text": "Chúc vui"}, state="COLLECTING"),
        turn("Giờ mở cửa của cửa hàng?", ["policy"], draft_unchanged=True, order_product_id="demo-001"),
        turn("Bỏ size đã chọn", ["order_request"], clear=["size"], edit=True, slots={"size": None}, state="COLLECTING"),
    ], tags=["slot_filling", "slot_clear", "multi_turn", "policy"])
    add("dev", "review", [
        complete("Tôi muốn đặt một bánh socola size 16 cm, không topping, không viết chữ, nhận cửa hàng 2099-01-04 10:00, tên DEMO Khách A, sđt TEST-0001.", "2099-01-04 10:00", "TEST-0001", order_product_id="demo-001"),
        turn("Đồng ý nhưng đổi size 20 cm", ["order_request"], action="confirm", edit=True, updates={"size": "20 cm"}, state="REVIEW", slots={"size": "20 cm"}, order_count=0),
        turn("Chưa xác nhận, cho tôi xem lại", ["order_request"], action="review", state="REVIEW", order_count=0),
    ], tags=["review_revision", "negated_confirmation"])
    add("dev", "empty", [
        start("Tôi muốn đặt socola", "socola", None),
        info("Giá bánh dâu?", ["price"], ["dâu"], [], catalog_status="unconfigured", order_product_id=None),
        turn("Hủy yêu cầu này", ["order_request"], action="cancel", state="CANCELLED", order_count=0),
        turn("Nhờ nhân viên tư vấn", ["fallback"], action="handoff", state="HANDOFF", order_count=0),
    ], mode="empty", tags=["empty", "cancel", "handoff"])
    add("dev", "unknown", [
        info("Giá bánh thiên hà?", ["price"], ["bánh thiên hà"], [], catalog_status="no_results"),
        turn("Tôi muốn đặt dâu và socola", ["order_request"], ["dâu", "socola"], action="start_order", edit=True, order_names=["dâu", "socola"], clarification=True, draft_unchanged=True, order_count=0),
        turn("Giá bao nhiêu?", ["price"], reference="last", ambiguous=True, clarification=True, draft_unchanged=True),
        turn("Tôi không muốn đặt nữa", ["order_request"], action="cancel", state="CANCELLED", order_count=0),
    ], tags=["unknown_product", "ambiguity", "negation"])
    add("dev", "empty_save", [
        complete("Tôi muốn đặt một bánh socola, size 16 cm, không topping, không viết chữ, nhận cửa hàng 2099-01-05 10:00, tên DEMO Khách A, sđt TEST-0002.", "2099-01-05 10:00", "TEST-0002", order_product_id=None),
        turn("Xác nhận", ["order_request"], action="confirm", state="HANDOFF", order_count=0, confirmed=False),
        info("Bánh vani giá bao nhiêu?", ["price"], ["vani"], [], catalog_status="unconfigured"),
    ], mode="empty", tags=["waiting_consultation", "no_real_order"])
    add("dev", "mock", [
        info("Giá và size bánh socola?", ["price", "size"], ["socola"], ["mock-001"]),
        start("Tôi muốn đặt bánh dâu", "dâu", "mock-002"),
        info("Giá bánh socola?", ["price"], ["socola"], ["mock-001"], order_product_id="mock-002"),
    ], mode="mock", tags=["mock", "draft_isolation"])

    add("test", "basics", [
        info("Cho mình biết giá bánh vani nhé", ["price"], ["vani"], ["demo-003"]),
        info("Kích thước bánh socola thế nào?", ["size"], ["socola"], ["demo-001"]),
        info("Vị của bánh dâu là gì?", ["flavor"], ["dâu"], ["demo-002"]),
        info("Bánh vani hiện còn bán chứ?", ["availability"], ["vani"], ["demo-003"]),
    ], tags=["price", "size", "flavor", "availability"])
    add("test", "switch", [
        start("Cho tôi đặt một bánh vani", "vani", "demo-003", updates={"quantity": 1}),
        info("Mình hỏi giá socola thôi", ["price"], ["socola"], ["demo-001"], order_product_id="demo-003"),
        info("Còn chiếc mình đang đặt thì giá sao?", ["price"], [], ["demo-003"], reference="order", order_product_id="demo-003"),
        info("Dâu cần bảo quản ra sao?", ["storage"], ["Dâu"], ["demo-002"], order_product_id="demo-003"),
    ], tags=["topic_switch", "reference", "draft_isolation"])
    add("test", "linked", [
        info("Vani giá mấy tiền, còn dâu có vị gì?", ["price", "flavor"], ["Vani", "dâu"], ["demo-002", "demo-003"], requests=[request(["price"], ["Vani"]), request(["flavor"], ["dâu"])]),
        info("Báo giá socola 16 cm với vani 20 cm", ["price"], ["socola", "vani"], ["demo-001", "demo-003"], requests=[request(["price"], ["socola"], size="16 cm"), request(["price"], ["vani"], size="20 cm")]),
        turn("Loại vừa rồi còn hàng chứ?", ["availability"], reference="last", ambiguous=True, clarification=True, draft_unchanged=True),
    ], tags=["multi_product", "attribute_linking", "ambiguity"])
    add("test", "language", [
        info("vani gia bn vay", ["price"], ["vani"], ["demo-003"]),
        info("banh dau co sz nao", ["size"], ["dau"], ["demo-002"]),
        info("ko dat dau dau, toi hoi gia socola", ["price"], ["dau", "socola"], ["demo-001"], requests=[request(["price"], ["socola"])]),
    ], tags=["no_accents", "abbreviation", "negation"])
    add("test", "edit", [
        start("Tôi cần đặt bánh dâu", "dâu", "demo-002"),
        turn("Lấy ba chiếc", ["order_request"], updates={"quantity": 3}, edit=True, slots={"quantity": 3}),
        turn("Đổi loại đang đặt thành vani", ["order_request"], ["vani"], edit=True, order_names=["vani"], order_product_id="demo-003", slots={"quantity": 3, "size": None, "toppings": None}),
        turn("Thôi hủy bản nháp", ["order_request"], action="cancel", state="CANCELLED", order_count=0),
    ], tags=["slot_update", "product_edit", "cancel"])
    add("test", "empty", [
        start("Mình muốn mua bánh vani", "vani", None),
        info("Socola size bao nhiêu?", ["size"], ["Socola"], [], catalog_status="unconfigured"),
        turn("Gặp người tư vấn giúp mình", ["fallback"], action="handoff", state="HANDOFF"),
    ], mode="empty", tags=["empty", "handoff"])
    add("test", "mock", [
        start("Mình đặt bánh vani", "vani", "mock-003"),
        info("Giá dâu với socola là bao nhiêu?", ["price"], ["dâu", "socola"], ["mock-001", "mock-002"], order_product_id="mock-003"),
        info("Size bánh trong đơn thế nào?", ["size"], [], ["mock-003"], reference="order", order_product_id="mock-003"),
        turn("Thêm bánh dâu nữa nhé", ["order_request"], ["dâu"], edit=True, order_names=["dâu"], operation="add_product", clarification=True, draft_unchanged=True, order_product_id="mock-003"),
        turn("Bỏ bánh vani khỏi yêu cầu", ["order_request"], ["vani"], edit=True, order_names=["vani"], operation="remove_product", clear=["product"], order_product_id=None, state="COLLECTING"),
    ], mode="mock", tags=["mock", "multi_product", "reference"])
    return sets


def main():
    for split, dialogues in build().items():
        count = 0
        for dialogue in dialogues:
            for index, item in enumerate(dialogue["turns"], 1):
                count += 1
                item.update(id=f"{split}-{count:03}", turn_index=index)
        assert count == (48 if split == "dev" else 26), (split, count)
        payload = {"version": "intent-context-v1", "annotation_revision": 2, "split": split, "sample_count": count,
            "source": "manually_labelled_synthetic", "is_mock": True,
            "scope": "Qwen NLU and controller, not overall/production evaluation", "dialogues": dialogues}
        path = ROOT / "evaluation" / f"intent_context_{split}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(split, count, "labelled turns", len(dialogues), "dialogues")


if __name__ == "__main__":
    main()
