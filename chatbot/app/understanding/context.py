"""Payload v2 gom bộ nhớ; adapter in-memory giữ controller/checkout hiện có."""
from copy import deepcopy

GROUPS={
 "focus":("discussion_context","needs","current_request"),
 "options":("shown_products","product_choices","advice_pending","advice_page","quick_replies"),
 "pending":("pending_information_request","pending_order_request","pending_order_question","request_memory","request_sequence"),
 "budget":("bundle_context",),
}
def restore_context(payload):
    current=deepcopy(payload)
    if current.get("memory_version",1)>2:
        raise ValueError("Unsupported conversation memory version")
    memory=current.pop("memory",{})
    for group,fields in GROUPS.items():
        for field in fields:
            if field not in current and field in memory.get(group,{}):
                current[field]=deepcopy(memory[group][field])
    return current

def pack_context(current):
    stored=restore_context(current)
    stored["memory_version"]=2
    stored["memory"]={group:{field:stored.pop(field) for field in fields if field in stored}
                      for group,fields in GROUPS.items()}
    return stored

def summary(current):
    """Không gửi history/name/phone/address hoặc toàn bộ card cho model."""
    focus=current.get("discussion_context",{})
    choices=current.get("product_choices",{})
    return {"state":current["order"]["state"],"focus_count":len(focus.get("focus_product_ids",[])),
        "option_count":len(choices.get("product_ids",[])),
        "pending_order":bool(current.get("pending_order_request")),
        "pending_information":bool(current.get("pending_information_request")),
        "order_question":(current.get("pending_order_question") or {}).get("field"),
        "has_combo":bool(current.get("bundle_context"))}
