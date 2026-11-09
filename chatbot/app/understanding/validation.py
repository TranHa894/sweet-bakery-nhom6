"""Kiểm tra theo phần; lỗi một query không loại bỏ query khác đã hợp lệ."""
from pydantic import ValidationError
from app.schemas import InformationRequest,QueryConstraints
from app.understanding.frames import FieldIssue

def build_query(frame,**kwargs):
    filters=kwargs.pop("filters",{})
    clean={}
    invalid=False
    for field,value in filters.items():
        try:
            checked=QueryConstraints.model_validate({field:value})
            clean.update(checked.model_dump(exclude_none=True))
        except ValidationError:
            invalid=True
            frame.issues.append(FieldIssue(field=field,code="invalid_field",
                question="Bạn làm rõ điều kiện "+field+" cho món này nhé."))
    try:
        if invalid:return None
        return InformationRequest(**kwargs,filters=QueryConstraints.model_validate(clean))
    except ValidationError:
        frame.issues.append(FieldIssue(field="budget",code="conflicting_fields",
            question="Hai cận ngân sách chưa phù hợp; bạn cho mình khoảng tiền muốn tìm nhé."))
        return None

def validate_frame(frame):
    frame.queries=[q for q in frame.queries if q is not None]
    if frame.budget is not None and len([q for q in frame.queries if "recommendation" in q.intents])<2:
        frame.issues.append(FieldIssue(field="budget",code="incomplete_combo",
            question="Mình cần làm rõ món còn thiếu trước khi tính combo."))
        frame.budget=None
    if len(frame.queries)==1 and frame.budget is None and frame.queries[0].quantity!=1:
        frame.issues.append(FieldIssue(field="quantity",code="ambiguous_price_scope",
            question="Ngân sách này là cho mỗi món hay tổng số lượng bạn muốn mua?"))
        frame.queries=[]
    # Không thực hiện hành động ghi khi thông tin đặt có issue.
    if any(i.field.startswith("order") for i in frame.issues):
        frame.action="none";frame.operation="none";frame.items=[];frame.order_mentions=[]
    declared=list(dict.fromkeys([*frame.intents,*(i for q in frame.queries for i in q.intents)]))
    if not frame.queries:
        declared=[i for i in declared if i not in {"price","size","flavor","availability","recommendation","description","policy"}]
    frame.intents=declared or ["fallback"]
    return frame


def schema_for_prompt(node):
    """Bỏ annotation cho prompt gọn; giữ cấu trúc/ràng buộc và tên field."""
    if isinstance(node, list):
        return [schema_for_prompt(item) for item in node]
    if not isinstance(node, dict):
        return node
    result = {}
    for key, value in node.items():
        if key in {"title", "description", "default"}:
            continue
        if key in {"properties", "$defs"}:
            result[key] = {name: schema_for_prompt(spec) for name, spec in value.items()}
        else:
            result[key] = schema_for_prompt(value)
    return result
