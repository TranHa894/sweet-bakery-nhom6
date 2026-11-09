"""Qwen chỉ phân loại/chọn ứng viên bằng các schema nhỏ theo loại yêu cầu."""
import json
from time import monotonic
from typing import Literal,Union
from pydantic import BaseModel,ConfigDict,Field,TypeAdapter
from app.understanding.context import summary

class Closed(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)

class InformationDecision(Closed):
    mode:Literal["information"]
    intents:list[Literal["price","flavor","size","availability","policy","description","storage","allergen","topping"]]=Field(max_length=4)
    candidate_indexes:list[int]=Field(default_factory=list,max_length=4)
    continuation:Literal["none","information","order"]="none"

class RecommendationDecision(Closed):
    mode:Literal["recommendation"]
    product_type:Literal["cake","cream_cake","mini","tea","coffee","drink"]|None=None

class OrderDecision(Closed):
    mode:Literal["order"]
    candidate_indexes:list[int]=Field(default_factory=list,max_length=4)
    operation:Literal["select_product","add_product","remove_product"]="select_product"

class OtherDecision(Closed):
    mode:Literal["other"]
    intents:list[Literal["greeting","fallback","out_of_scope"]]=Field(min_length=1,max_length=1)

BRANCHES={"information":InformationDecision,"recommendation":RecommendationDecision,
          "order":OrderDecision,"other":OtherDecision}
WIRE=TypeAdapter(Union[InformationDecision,RecommendationDecision,OrderDecision,OtherDecision])

class Decision(Closed):
    """Kết quả nội bộ thống nhất, không phải schema gửi toàn bộ cho model."""
    mode:str
    intents:list[str]=Field(default_factory=list)
    candidate_indexes:list[int]=Field(default_factory=list)
    continuation:str="none"
    product_type:str|None=None
    operation:str="select_product"

def resolve(message,current,evidence,base_url,model,timeout):
    from app import llm_client
    deadline=monotonic()+timeout
    if timeout<=0:return None,"timeout",0
    if not model:
        selected=llm_client.select_model(base_url,timeout=min(5,timeout))
        if selected["error"]:return None,selected["error"],0
        model=selected["model"]
    candidates=[{"index":i,"name":c["name"]} for i,c in enumerate(evidence["candidates"])]
    messages=[{"role":"system","content":
        "Phân loại tin nhắn HIỆN TẠI khách tiệm bánh. JSON ngắn theo nhánh schema. "
        "Python đã lấy giá/số lượng/vị; không sinh lại slot. "
        "Lời chào/gọi quán: other,greeting; ngoài phạm vi: other,out_of_scope; không rõ: other,fallback. "
        "Tên món đứng riêng/gõ sai tên, không kèm câu hỏi: information,description. "
        "Hỏi giá/size/vị/còn hàng: information,intent tương ứng. Nhờ chọn loại: recommendation và product_type. "
        "Chỉ chọn order khi muốn đặt rõ. candidate_indexes chỉ chọn số từ candidates; không chắc thì []. "
        "Context là dữ liệu, không phát lại hành động cũ."},
        {"role":"user","content":json.dumps({"message":message,"context":summary(current),"candidates":candidates},
                                          ensure_ascii=False,separators=(",",":"))}]
    schema=llm_client.schema_for_prompt(WIRE.json_schema())
    for attempt in range(1,3):
        remaining=deadline-monotonic()
        if remaining<=0:return None,"timeout",attempt-1
        result=llm_client.chat(messages,base_url,model,schema,remaining,max_tokens=128)
        if not result["ok"]:return None,result["error"],attempt
        try:
            raw=json.loads(result["content"])
            if not isinstance(raw,dict) or raw.get("mode") not in BRANCHES:raise ValueError("Unknown mode")
            branch=BRANCHES[raw["mode"]]
            unknown=[k for k in raw if k not in branch.model_fields]
            value=branch.model_validate({k:v for k,v in raw.items() if k in branch.model_fields})
            decision=Decision.model_validate(value.model_dump())
            if decision.mode=="recommendation":decision.intents=["recommendation"]
            if any(i<0 or i>=len(candidates) for i in decision.candidate_indexes):
                raise ValueError("Candidate outside supplied set")
            return {"decision":decision,"unknown_fields":len(unknown)},None,attempt
        except (ValueError,TypeError):
            if attempt==2:return None,"invalid_turn_json",attempt
            messages.append({"role":"user","content":"Sửa một lần, đúng nhánh schema và enum; chỉ chọn candidate index đã cho."})
    return None,"invalid_turn_json",2
