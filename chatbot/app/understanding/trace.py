"""Trace kỹ thuật opt-in, không lưu câu khách hoặc JSON contact."""
import hashlib
import json
from app import config

def emit(message,frame,*,seconds,calls,error=None,model_decision=None):
    if not config.NLU_TRACE:return
    # Không log raw message, mentions, updates hay field value tự do.
    record={"event":"hybrid_nlu","message_sha256":hashlib.sha256(message.encode()).hexdigest()[:16],
        "characters":len(message),"seconds":round(seconds,4),"model_calls":calls,
        "source":"hybrid" if calls else "deterministic","error":error,
        "intents":frame.intents if frame else [],
        "fields":[sorted(q.filters.model_dump(exclude_none=True)) for q in frame.queries] if frame else [],
        "issues":[{"field":i.field,"code":i.code,"target":i.target} for i in frame.issues] if frame else [],
        "model_fields":sorted(model_decision or {}),
        "model_decision":{key:value for key,value in (model_decision or {}).items()
                          if key in {"mode","intents","candidate_indexes","continuation","product_type","operation"}},
        "provenance":frame.provenance if frame else {} }
    print("[NLU trace] "+json.dumps(record,ensure_ascii=False),flush=True)


def emit_result(response,engine,error,calls):
    """Chỉ trạng thái/kích thước kết quả, không log văn bản trả lời hoặc ID phiên."""
    if not config.NLU_TRACE:return
    record={"event":"chatbot_result","engine":engine,"error":error,"nlu_calls":calls,
        "products":len(response.get("products",[])),
        "combos":len(response.get("recommendation_groups",[])),
        "clarification":bool(response.get("requires_clarification")),
        "confirmation":bool(response.get("requires_confirmation")),
        "catalog_status":response.get("catalog_status")}
    print("[NLU trace] "+json.dumps(record,ensure_ascii=False),flush=True)
