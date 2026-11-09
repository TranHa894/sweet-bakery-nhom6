"""Chuẩn hóa để phân tích; luôn giữ văn bản người dùng riêng."""
import re
import unicodedata
from app.text_utils import normalize_shopping_terms

def normalize_message(message):
    value=normalize_shopping_terms(unicodedata.normalize("NFC",message).replace(";",","))
    value=re.sub(r"\bdt\b","dien thoai",value)
    value=re.sub(r"\b(?:ko|kh|k0)\b","khong",value)
    return value

def clause_quantity(prefix):
    words={"mot":1,"hai":2,"ba":3,"bon":4,"nam":5,"sau":6,"bay":7,"tam":8,"chin":9,"muoi":10}
    match=re.search(r"(?<!\w)(\d+|"+"|".join(words)+r")\s*(?:(?:cai|coc|ly|chiec|phan|c)\s*)?$",prefix)
    if not match:return None
    value=int(match[1]) if match[1].isdigit() else words[match[1]]
    return value if 1<=value<=1000 else None
