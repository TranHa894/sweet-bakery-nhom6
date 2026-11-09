"""Entry point NLU lai; không gọi parser cũ khi Qwen lỗi."""
from time import perf_counter
from pydantic import ValidationError
from app.schemas import InformationRequest,OrderItemSelection
from app.understanding.deterministic import analyze,local_filters
from app.understanding.validation import validate_frame
from app.understanding.frames import FieldIssue
from app.understanding.model import resolve
from app.understanding.trace import emit

def extract(message,conversation,base_url,model,timeout,repository=None):
    started=perf_counter();calls=0;decision_data=None
    try:
        frame,evidence=analyze(message,conversation,repository)
    except (ValidationError,ValueError):
        from app.understanding.frames import SemanticFrame
        frame=SemanticFrame(issues=[FieldIssue(field="request",code="invalid_constraint",
            question="Một điều kiện chưa hợp lệ; bạn kiểm tra lại số lượng hoặc khoảng tiền nhé.")])
        evidence={"candidates":[],"text":"","source_status":"success"}
    if evidence["source_status"]=="error":
        emit(message,frame,seconds=perf_counter()-started,calls=0,error="source_error")
        return {"data":None,"error":"source_error","attempts":0}
    if frame.needs_model:
        decision_data,error,calls=resolve(message,conversation,evidence,base_url,model,timeout)
        if error:
            emit(message,frame,seconds=perf_counter()-started,calls=calls,error=error)
            return {"data":None,"error":error,"attempts":calls}
        choice=decision_data["decision"]
        frame.provenance["intent"]="qwen"
        selected=[evidence["candidates"][i]["name"] for i in choice.candidate_indexes]
        intents=list(choice.intents)
        if decision_data["unknown_fields"]:
            frame.issues.append(FieldIssue(field="model",code="unknown_model_fields",question=""))
        if choice.mode=="order":
            # Tập tên đóng, thao tác chỉ tạo draft; xác nhận vẫn do FSM kiểm tra.
            if selected and evidence.get("explicit_order"):
                frame.intents=["order_request"]
                frame.operation=choice.operation
                frame.action="start_order" if choice.operation=="select_product" else "none"
                frame.order_mentions=selected;frame.mentions=selected
                frame.items=[OrderItemSelection(product_mention=name) for name in selected]
            else:
                frame.issues.append(FieldIssue(field="order.product",code="unproven_order_intent" if not evidence.get("explicit_order") else "unclear_product",
                    question="Bạn đang hỏi thông tin hay muốn đặt món nào? Mình chưa thay đổi bản nháp."))
        elif selected:
            supported=[i for i in intents if i in {"price","size","flavor","availability","description","storage","allergen","topping"}] or ["description"]
            frame.intents=supported
            frame.queries=[InformationRequest(intents=supported,product_mentions=selected,question=message)]
            frame.mentions=selected
        elif choice.mode=="recommendation":
            frame.intents=["recommendation"]
            frame.queries=[InformationRequest(intents=["recommendation"],product_mentions=[],question=message,
                advice="guided",filters=local_filters(evidence["text"],choice.product_type))]
        elif intents==["policy"]:
            frame.intents=intents;frame.queries=[InformationRequest(intents=intents,product_mentions=[],question=message)]
        else:
            frame.intents=[i for i in intents if i in {"greeting","out_of_scope"}] or ["fallback"]
        frame.continuation=choice.continuation
    frame=validate_frame(frame)
    try:
        value=frame.as_turn()
    except ValidationError:
        # Không làm rơi phần thông tin hợp lệ chỉ vì một action mâu thuẫn.
        frame.action="none";frame.operation="none";frame.items=[];frame.order_mentions=[]
        frame.intents=list(dict.fromkeys(i for q in frame.queries for i in q.intents)) or ["fallback"]
        frame.issues.append(FieldIssue(field="order",code="conflicting_action",
            question="Phần thao tác đặt hàng chưa rõ; mình giữ bản nháp hiện tại."))
        value=frame.as_turn()
    emit(message,frame,seconds=perf_counter()-started,calls=calls,
         model_decision=decision_data["decision"].model_dump() if decision_data else None)
    return {"data":value,"error":None,"attempts":calls,"validated":True,
        "source":"hybrid" if calls else "deterministic",
        "clarification":" ".join(dict.fromkeys(i.question for i in frame.issues if i.question)),
        "field_issues":[i.model_dump() for i in frame.issues]}
