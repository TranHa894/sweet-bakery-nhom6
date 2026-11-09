"""Phân tích bằng chứng rõ ràng; không đọc file menu và không thực hiện nghiệp vụ."""
import re
from difflib import SequenceMatcher
from app.repositories.catalog import safe_search_products
from app.text_utils import ADVICE_PREFERENCE_CUES,budget_evidence
from app.schemas import OrderItemSelection,BundleBudget
from app.understanding.frames import SemanticFrame,FieldIssue
from app.understanding.normalize import normalize_message,clause_quantity
from app.understanding.validation import build_query

GROUP_PATTERN=re.compile(r"\b(?:banh kem|banh nho|banh mini|ca phe|do uong|tra|banh)\b")
GROUPS={"banh kem":"cream_cake","banh nho":"mini","banh mini":"mini","ca phe":"coffee","tra":"tea","banh":"cake","do uong":"drink"}
INFORMATION={
 "price":r"\bgia\b|\bbao nhieu\b",
 "availability":r"\b(?:con hang|het hang|con khong|con ko|co san)\b",
 "size":r"\bsize\b(?!\s*\d)|\b(?:kich thuoc|bao nhieu nguoi|may nguoi)\b",
 "flavor":r"\b(?:vi gi|huong vi gi|co vi nao)\b",
 "topping":r"\btopping\b",
 "allergen":r"\b(?:thanh phan|nguyen lieu|co sua|co trung|co hat)\b",
 "storage":r"\b(?:bao quan|han dung|de duoc bao lau)\b",
}
FLAVORS={"vani":r"\b(?:vani|vanilla)\b","dâu":r"\b(?:dau|strawberry)\b",
 "sô cô la":r"\b(?:socola|so co la|chocolate|choco)\b","trà xanh":r"\b(?:tra xanh|matcha)\b",
 "phô mai":r"\b(?:pho mai|cheese)\b","chanh leo":r"\b(?:chanh leo|chanh day)\b"}

def issue(frame,field,code,question,target=None):
    frame.issues.append(FieldIssue(field=field,code=code,question=question,target=target))

def catalog_anchors(text,products):
    spans={}
    for product in products:
        for alias in [product["name"],*product.get("aliases",[])]:
            word=normalize_message(alias)
            if not word or len(word)<3:continue
            for match in re.finditer(r"(?<!\w)"+re.escape(word)+r"(?!\w)",text):
                key=match.span()
                entry=spans.setdefault(key,{"start":key[0],"end":key[1],"mention":text[key[0]:key[1]],"products":[]})
                if product["id"] not in [p["id"] for p in entry["products"]]:entry["products"].append(product)
    result=[]
    for (start,end),entry in sorted(spans.items(),key=lambda item:-(item[0][1]-item[0][0])):
        if not any(a["start"]<=start and end<=a["end"] for a in result):result.append(entry)
    for item in result:
        # Alias ngắn như "dâu" phải đi cùng tiền tố "bánh" ngay trước nó,
        # tránh tách thêm một query bánh chung rồi trộn cả menu vào câu giá.
        prefix=re.search(r"\bbanh(?:\s+kem)?\s*$",text[:item["start"]])
        if prefix:
            item["start"]=prefix.start()
            item["mention"]=text[item["start"]:item["end"]]
    return sorted(result,key=lambda item:item["start"])

def fuzzy_candidates(text,products):
    """Chỉ ứng viên từ repository; không tự gán ID cho chuỗi chưa chắc."""
    words=text.split();best={}
    for product in products:
        for name in [product["name"],*product.get("aliases",[])]:
            alias=normalize_message(name)
            if len(alias)<7:continue
            length=len(alias.split())
            for count in {max(2,length-1),length,length+1}:
                for start in range(max(0,len(words)-count+1)):
                    phrase=" ".join(words[start:start+count])
                    score=SequenceMatcher(None,phrase,alias).ratio()
                    if score>=0.87 and score>best.get(product["id"],{}).get("score",0):
                        best[product["id"]]={"id":product["id"],"name":product["name"],"score":round(score,3)}
    return sorted(best.values(),key=lambda item:-item["score"])[:4]

def anchors(text,products):
    found=catalog_anchors(text,products)
    for match in GROUP_PATTERN.finditer(text):
        if any(item["start"]<=match.start()<item["end"] for item in found):continue
        before=re.split(r",|\b(?:va|voi)\b",text[:match.start()])[-1]
        if match[0] in {"tra","ca phe"} and re.search(r"\b(?:vi|huong)\b",before):continue
        found.append({"start":match.start(),"end":match.end(),"type":GROUPS[match[0]],"products":[],"mention":None})
    return sorted(found,key=lambda item:item["start"])

def local_filters(clause,kind,*,named=False):
    filters={}
    if not named:filters["product_type"]=kind
    if named:return filters
    for field,patterns in ADVICE_PREFERENCE_CUES.items():
        if field=="coffee_style" and kind!="coffee":continue
        if field=="taste_family" and re.search(r"\b(?:vi kem|kem sua|vani|trang tri)\b",clause) and kind not in {"cake","cream_cake"}:
            patterns={k:v for k,v in patterns.items() if k!="cream"}
        hits=[value for value,pattern in patterns.items() if re.search(pattern,clause)]
        if len(hits)==1:filters[field]=hits[0]
    found=[value for value,pattern in FLAVORS.items() if re.search(pattern,clause)]
    if len(found)>1 or re.search(r"\bkhong(?:\s+(?:thich|muon|lay|chon))?\s+(?:vi|huong)\b",clause):
        filters["flavor"]=found  # validator hỏi lại, không tự đảo/phớt lờ phủ định
    if len(found)==1:
        filters["flavor"]=found[0]
        if filters.get("taste_family") in {"vanilla","matcha","chocolate"}:
            filters.pop("taste_family")  # cùng ý, một field là đủ
    if re.search(r"\bkhong(?:\s+(?:thich|muon|lay|chon))?\s+(?:vi|huong)\b",clause):
        filters["flavor"]=[]
    if kind=="coffee" and filters.get("coffee_style"):filters.pop("flavor",None)
    if kind=="tea" and re.search(r"\btra sua\b",clause):filters["taste_family"]="milk_tea"
    if kind=="tea" and re.search(r"\btrai cay\b",clause):filters["taste_family"]="fruit_tea"
    return filters

def detect_reference(text):
    if re.search(r"\b(?:dang dat|trong don|trong gio)\b",text):return "order"
    if re.search(r"\b(?:ca hai|ca 2|hai loai)\b",text):return "both"
    if re.search(r"\b(?:tat ca|toan bo)\b",text):return "all"
    if re.search(r"\b(?:thu hai|thu 2|chiec 2|loai 2)\b",text):return "second"
    if re.search(r"\b(?:thu nhat|thu 1|dau tien)\b",text):return "first"
    if re.search(r"\b(?:(?:banh|mon|loai|cai|chiec)\s+(?:nay|do)|vua roi|loai vua)\b",text):return "last"
    return "none"

def price_preference(text):
    for label,pattern in (
        ("lowest",r"\b(?:re nhat|thap nhat|it tien nhat)\b"),
        ("highest",r"\b(?:dat nhat|cao nhat|mac nhat)\b"),
        ("cheaper_than",r"\b(?:re hon|gia thap hon|it tien hon)\b(?!\s*\d)"),
        ("more_expensive_than",r"\b(?:dat hon|gia cao hon|mac hon)\b(?!\s*\d)")):
        if re.search(pattern,text):return label
    return "none"


def analyze(message,current,repository):
    text=normalize_message(message)
    frame=SemanticFrame()
    catalog=safe_search_products(repository,{}) if repository is not None else {"status":"unconfigured","products":[]}
    products=catalog["products"] if catalog["status"]=="success" else []
    found=anchors(text,products)
    evidence={"text":text,"anchors":found,"candidates":[],"source_status":catalog["status"]}
    frame.provenance={"normalization":"python","explicit_fields":"python"}
    frame.reference=detect_reference(text)
    info=[kind for kind,pattern in INFORMATION.items() if re.search(pattern,text)]
    money=budget_evidence(text)
    ranking=price_preference(text)
    if frame.reference in {"both","all","first","second","last","order"} and not any(a["products"] for a in found):
        # Từ "bánh" trong "cả hai bánh đó" không phải tìm nhóm bánh mới.
        if not money["values"] and not re.search(r"\b(?:goi y|tim)\b",text):
            found=[]
    order=re.search(r"\b(?:dat|tao don|them|bo|xoa|doi sang|doi thanh)\b",text)
    negated=bool(re.search(r"\b(?:khong|chua|dung)(?:\s+muon)?\s+(?:dat|mua|lay)\b",text))
    frame.negated=negated
    evidence["explicit_order"]=bool(order and not negated)
    if re.fullmatch(r"(?:xem|cho (?:toi|minh) xem) them(?: lua chon)?(?: khac)?[ .!]*",text):
        frame.intents=["recommendation"]
        frame.queries=[build_query(frame,intents=["recommendation"],product_mentions=[],
            question=message,advice="more")]
        return frame,evidence
    if re.search(r"\b(?:nhan vien|nguoi that|tu van vien|khieu nai)\b",text):
        frame.intents=["complaint" if "khieu nai" in text else "handoff"]
        frame.action="handoff";frame.handoff_reason="complaint" if "khieu nai" in text else "customer_requested"
        return frame,evidence
    if re.search(r"\b(?:di ung|tranh|kieng)\b",text):
        # Không có bằng chứng thành phần an toàn: không suy từ not_listed.
        frame.intents=["handoff"];frame.action="handoff";frame.handoff_reason="severe_allergy"
        return frame,evidence
    if re.fullmatch(r"(?:xin )?(?:chao(?: ban)?|hello|hi|hey)[ .,!]*",text):
        frame.intents=["greeting"];return frame,evidence
    policy_question=bool(re.search(r"\b(?:chinh sach|quy dinh|dieu kien)\b|\b(?:cach|lam sao)\s+(?:de\s+)?huy\b",text)
        or re.search(r"\bhuy don\b.*\b(?:duoc khong|duoc ko|the nao|mat phi|co duoc)\b",text))
    if re.search(r"\b(?:huy|cancel)\b",text) and not policy_question and not re.search(r"\b(?:khong|chua|dung)(?:\s+muon)?\s+huy\b",text):
        frame.intents=["order_request"];frame.action="cancel";return frame,evidence
    if re.match(r"^(?:(?:toi|minh|em)\s+)?(?:xac nhan|dong y|chot don|gui yeu cau|ok)\b",text):
        if not order and current["order"].get("review"):
            frame.intents=["order_request"];frame.action="confirm";return frame,evidence
        frame.needs_model=True
    if re.search(r"\b(?:xem lai|review)\b",text):
        frame.intents=["order_request"];frame.action="review";return frame,evidence
    # Xóa điều kiện phải có động từ rõ, không dùng null của một lượt khác.
    for field,pattern in {
        "budget_vnd":r"\b(?:bo|xoa|khong gioi han)\s+(?:gioi han )?(?:gia|ngan sach)\b",
        "flavor":r"\b(?:bo|xoa|khong can)\s+(?:dieu kien )?(?:vi|huong vi)\b",
    }.items():
        if re.search(pattern,text):frame.clear.append(field)
    if frame.clear and not found:
        frame.intents=["recommendation"]
        frame.queries=[build_query(frame,intents=["recommendation"],product_mentions=[],
            question=message,search_scope="refine")]
        return frame,evidence
    quantity_update=re.search(r"\b(?:so luong|tang len|giam con|doi thanh)\s*(?:la|len|con)?\s*(\d+)\b",text)
    if quantity_update and not found and current["order"]["state"] in {"COLLECTING","REVIEW"}:
        quantity=int(quantity_update[1])
        if 1<=quantity<=1000:
            frame.intents=["order_request"];frame.operation="update_slots";frame.updates["quantity"]=quantity
        else:
            issue(frame,"order.quantity","invalid_quantity","Số lượng cần là số nguyên từ 1 đến 1000; bạn nhập lại nhé.")
        return frame,evidence
    pending=(current.get("pending_order_question") or {}).get("field")
    if not found and not info and not order and not money["values"] and not re.search(
            r"\b(?:goi y|tim|combo|san pham|ngot|vi|ca phe|tra|banh|chinh sach)\b",text):
        contact_value=(
            pending=="phone" and re.fullmatch(r"(?:\+?[\d .()-]{5,25}|test-\d+)",text)
            or pending=="name" and len(text.split())<=6
            and re.fullmatch(r"[a-z ]+",text)
            and not re.search(r"\b(?:dang|muon|can|hoi|khong|chua|gi|nao|sao|phan van|chuyen)\b",text))
        if contact_value:
            frame.intents=["order_request"];frame.continuation="order";frame.operation="update_slots"
            frame.updates[pending]=message.strip();return frame,evidence
        if pending=="quantity":
            quantity=clause_quantity(text)
            if quantity:
                frame.intents=["order_request"];frame.continuation="order";frame.operation="update_slots"
                frame.updates["quantity"]=quantity;return frame,evidence
    if policy_question or re.search(r"\b(?:chinh sach|phi giao|giao hang|thanh toan|gio mo cua|doi tra)\b",text):
        frame.intents.append("policy")
        frame.queries.append(build_query(frame,intents=["policy"],product_mentions=[],question=message))
    preference=any(re.search(pattern,text) for field,patterns in ADVICE_PREFERENCE_CUES.items()
        if field!="coffee_style" or re.search(r"\bca phe\b",text)
        or (current.get("discussion_context") or {}).get("product_type")=="coffee"
        for pattern in patterns.values())
    wants_advice=bool(re.search(r"\b(?:goi y|tim|combo|nen chon|muon mua|can mua|gi cung duoc|loai nao cung duoc|tuy ban)\b",text)
        or not order and (money["values"] or preference or ranking!="none"))
    if re.search(r"\bcho (?:toi|minh|em)\s+(?:mot|hai|ba|\d+)\b",text) and any(a["products"] for a in found) and not info:
        order=re.search(r"\bcho\b",text)
    each=re.search(r"\bmoi (?:loai|mon)\s+(\d+)\b",text)
    budget_phrase=re.search(
        r"\b(?:trong (?:muc )?gia|trong tam gia|tam gia|khoang gia|ngan sach(?: (?:la|khoang|tam))*|(?:toi|minh|em)(?: chi)? (?:co|con)(?: (?:khoang|tam))?|voi(?: ngan sach)?(?: (?:khoang|tam))?)\s*[: ]*\d[\d., ]*(?:k|nghin|ngan|dong|d|trieu|tr)?\b",text)
    shared=bool(len(found)>=2 and budget_phrase and (len(money["values"])==1 or "range" in money["shapes"]))
    if shared and money["expected"].get("budget_vnd") is not None:
        try:
            frame.budget=BundleBudget(question=budget_phrase[0],**money["expected"])
        except ValueError:
            issue(frame,"budget","invalid_range","Bạn kiểm tra lại hai cận của tổng ngân sách nhé.")
            return frame,evidence
    if len(found)>4 and not order:
        issue(frame,"queries","too_many_requests","Mỗi tin mình xử lý tối đa bốn yêu cầu; bạn chia thành hai tin nhé.")
        return frame,evidence
    previous_end=0
    for index,anchor in enumerate(found):
        end=found[index+1]["start"] if index+1<len(found) else len(text)
        start=anchor["start"]
        prefix=text[previous_end:start]
        quantity=clause_quantity(prefix)
        invalid_quantity=bool(re.search(r"(?:^|\s)(?:-\d+|0|100[1-9]|10[1-9]\d|1[1-9]\d\d|[2-9]\d{3}|\d{5,})\s*(?:(?:cai|ly|coc|chiec)\s*)?$",prefix))
        if each:
            quantity=int(each[1]);invalid_quantity=not 1<=quantity<=1000
        if invalid_quantity and order:quantity=None
        clause=text[start:end].strip(" ,.")
        if shared and start<=budget_phrase.start()<end:
            clause=text[start:budget_phrase.start()].strip(" ,.")
        clause=re.sub(r"\s+(?:va|voi)$","",clause)
        previous_end=anchor["end"]
        if re.search(r"\b(?:khong|dung)\s+(?:hoi|xem)(?:\s+gia)?\s*$",prefix):
            continue
        named=bool(anchor["products"])
        mentions=[anchor["mention"]] if named else []
        kind=anchor.get("type") or anchor["products"][0].get("product_type")
        local_info=[i for i,pattern in INFORMATION.items() if re.search(pattern,clause)]
        # Động từ hỏi đứng trước đối tượng: áp khi không gắn thuộc tính cục bộ khác.
        prefix_info=[i for i,pattern in INFORMATION.items()
                     if re.search(pattern,re.split(r"[,;]|\b(?:va|voi)\b",prefix)[-1])]
        explicit_info=bool(local_info or prefix_info)
        if not local_info:
            local_info=prefix_info or (info if len(found)==1 or all(
                not re.search(p,text[a["start"]:found[n+1]["start"]] if n+1<len(found) else text[a["start"]:])
                for n,a in enumerate(found) for p in INFORMATION.values()) else [])
        size_match=re.search(r"\b(\d+)\s*cm\b",clause)
        local_order=bool(order and not negated and (
            re.search(r"\b(?:dat|tao don|them|bo|xoa|doi sang|doi thanh)\b",prefix)
            or order.start()<start and not prefix_info))
        if local_order:
            if not explicit_info:local_info=[]
            if invalid_quantity:
                issue(frame,"order.quantity","invalid_quantity","Số lượng món cần từ 1 đến 1000; bạn kiểm tra lại nhé.",index)
            if size_match:frame.updates["size"]=size_match[1]+" cm"
            if not named and frame.reference!="none" and re.search(r"\b(?:banh|mon|loai)\s+(?:nay|do|thu|dang dat)",clause):
                frame.items.append(OrderItemSelection(reference=frame.reference,quantity=quantity))
                frame.order_reference=frame.reference
            else:
                mention=anchor["mention"] if named else clause
                frame.order_mentions.append(mention)
                frame.items.append(OrderItemSelection(product_mention=mention,reference="none",quantity=quantity))
        if local_info and (named or not wants_advice):
            query=build_query(frame,intents=local_info,
                product_mentions=[] if not named and frame.reference!="none" else mentions or [clause],
                reference=frame.reference if not named else "none",question=clause,
                size=size_match[1]+" cm" if size_match else None)
            frame.queries.append(query);frame.intents.extend(local_info)
        elif not local_order or negated or wants_advice or ranking!="none":
            if named and not wants_advice and not negated and ranking=="none":
                frame.queries.append(build_query(frame,intents=["description"],product_mentions=mentions,question=clause))
                frame.intents.append("description")
                if len(found)==1 and normalize_message(message)==anchor["mention"]:
                    frame.continuation="entity"
            else:
                filters=local_filters(clause,kind,named=False)
                if not shared:filters.update(budget_evidence(clause)["expected"])
                frame.queries.append(build_query(frame,intents=["recommendation"],product_mentions=mentions,
                    question=clause,quantity=quantity or 1,
                    price_preference=ranking,search_scope="refine" if ranking in {"cheaper_than","more_expensive_than"} else "new",filters=filters))
                frame.intents.append("recommendation")
    if order and not negated:
        frame.intents.append("order_request")
        frame.operation="add_product" if re.search(r"\bthem\b",text) else "remove_product" if re.search(r"\b(?:bo|xoa)\b",text) else "select_product"
        frame.action="start_order" if frame.operation=="select_product" else "none"
        frame.mentions=list(dict.fromkeys(frame.order_mentions))
        if not frame.items and frame.reference!="none":
            frame.items=[OrderItemSelection(reference=frame.reference,quantity=clause_quantity(re.sub(r"\b(?:nay|do|nua|nhe)\b","",text)))]
            frame.order_reference=frame.reference
        if not frame.items:
            issue(frame,"order.product","missing_product","Bạn muốn đặt món nào? Mình giữ các thông tin đã có.")
            frame.operation="none";frame.action="none";frame.intents=[i for i in frame.intents if i!="order_request"]
    if not found and not order:
        if frame.reference!="none" and ranking=="none":
            intents=info or list((current.get("product_choices") or {}).get("intents") or ["description"])
            frame.queries=[build_query(frame,intents=intents,product_mentions=[],reference=frame.reference,question=message)]
            frame.intents=intents
            if not info:frame.continuation="information"
        elif wants_advice or any(re.search(p,text) for p in FLAVORS.values()):
            filters=local_filters(text,None);filters.update(money["expected"])
            frame.queries.append(build_query(frame,intents=["recommendation"],product_mentions=[],question=message,
                price_preference=ranking,
                search_scope="refine" if ranking in {"cheaper_than","more_expensive_than"} or not re.search(r"\b(?:goi y|tim|san pham)\b",text) else "new",
                filters=filters,advice="any" if re.search(r"\b(?:gi cung duoc|loai nao cung duoc|tuy ban)\b",text) else "none" if money["values"] or ranking!="none" else "guided"))
            frame.intents.append("recommendation")
        elif info:
            frame.queries.append(build_query(frame,intents=info,product_mentions=[],reference="last",question=message))
            frame.intents.extend(info)
        elif not frame.intents:
            evidence["candidates"]=fuzzy_candidates(text,products)
            frame.needs_model=True
    # Câu xác nhận kèm sửa chưa bao giờ được gửi ngay.
    if frame.action=="confirm" and (frame.items or frame.updates):
        frame.action="none";frame.operation="update_slots"
    if re.search(r"\b(?:duoi|tren|khoang|gia|ngan sach)\s+\d{1,3}(?:\s*(?:den|-)\s*\d{1,3})?(?![\d\w.,])(?:\s|$)",text) and not money["expected"]:
        frame.queries=[q for q in frame.queries if q is not None and "recommendation" not in q.intents]
        issue(frame,"budget","missing_unit","Bạn cho mình rõ đơn vị tiền (ví dụ 300k hoặc 300.000đ) nhé.")
    frame.queries=[q for q in frame.queries if q is not None]
    frame.mentions=list(dict.fromkeys([*frame.mentions,*(m for q in frame.queries for m in q.product_mentions)]))
    frame.intents=list(dict.fromkeys(frame.intents))
    frame.provenance["quantity"]="python" if any(i.quantity is not None for i in frame.items) else "unspecified"
    return frame,evidence
