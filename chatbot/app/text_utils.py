"""Chuẩn hóa để so khớp; luôn giữ nguyên văn bản gốc ở nơi gọi."""

import re
import unicodedata
from decimal import Decimal


def normalize_text(text: str) -> str:
    """Chuyển chữ thường, bỏ dấu; giữ dấu . , để đọc số tiền."""
    decomposed = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    plain = re.sub(r"[^\w\s.,]", " ", plain)
    return re.sub(r"\s+", " ", plain).strip()


def normalize_business_evidence(text: str) -> str:
    """Đọc viết tắt để kiểm chứng output AI; không trích intent hay tên bánh.

    Tách khỏi normalize_text để không đổi tên/alias, câu trích và dữ liệu gốc.
    'k' chỉ là phủ định trước động từ nghiệp vụ, không mở rộng khi đứng
    sau số (300 k) hoặc đứng riêng/còn k. Đây không phải bộ nhận diện intent.
    """
    normalized = normalize_text(text)
    abbreviations = {
        "ko": "khong", "kh": "khong", "k0": "khong",
        "oke": "ok", "oki": "ok", "okie": "ok", "okay": "ok",
        "sl": "so luong",
    }
    pattern = r"\b(?:" + "|".join(abbreviations) + r")\b"
    normalized = re.sub(pattern, lambda match: abbreviations[match[0]], normalized)

    business_verbs = r"dat|mua|lay|gui|xac nhan|dong y|huy|doi|can|muon|them|bo|xoa|ghi|viet|co"
    negation_pattern = r"\bk(?=\s+(?:" + business_verbs + r")\b)"
    def contextual_negation(match):
        prefix = normalized[:match.start()].rstrip()
        # k sau số là đơn vị tiền, kể cả có khoảng trắng trước một động từ.
        if prefix and prefix[-1].isdigit():
            return match[0]
        return "khong"
    normalized = re.sub(negation_pattern, contextual_negation, normalized)
    # 2c/2chiếc là số lượng khi AI đã chọn slot; không tự chọn sản phẩm/đặt đơn.
    return re.sub(r"\b(\d+)\s*(c|cai|chiec|banh)\b", r"\1 \2", normalized)


def phrase_spans(text: str, phrase: str) -> list[tuple[int, int]]:
    """Tìm cụm đã chuẩn hóa, không khớp một phần bên trong từ khác."""
    phrase = normalize_text(phrase)
    if not phrase:
        return []
    pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
    return [match.span() for match in re.finditer(pattern, text)]


def format_vnd(value: int) -> str:
    """Định dạng số nguyên tiền Việt; không dùng để suy giá."""
    return f"{value:,}".replace(",", ".") + " đ"


# Chỉ dùng để chọn ví dụ/kiểm chứng. Không sửa message gốc hoặc tự chọn intent.
_SHOPPING_ALIASES = {
    "banh kem": ("banh sinh nhat", "birthday cake", "ga to", "gato", "gateau"),
    "banh nho": ("banh ngot nho", "banh mini", "mini cake", "banh an vat"),
    "ca phe": ("coffee", "cafe", "caphe", "ca fe", "cf"),
    "bao nhieu": ("bao nhiu", "bao nhieu", "bnhieu", "bn"),
    "gia": ("gia ca",),
    "san pham": ("sp", "mon an", "mon", "mat hang"),
    "goi y": ("gioi thieu", "de xuat", "tu van"),
}
_SHOPPING_PATTERNS = [
    (canonical, re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)"))
    for canonical, aliases in _SHOPPING_ALIASES.items() for alias in sorted(aliases, key=len, reverse=True)
]


def normalize_shopping_terms(text: str) -> str:
    """Chuẩn hóa cách gọi đồng nghĩa cho bằng chứng; raw text vẫn được giữ."""
    value = normalize_business_evidence(text)
    for canonical, pattern in _SHOPPING_PATTERNS:
        value = pattern.sub(canonical, value)
    # “Bánh ngọt” là nhóm bánh nhỏ của menu; “bánh ngọt nhiều/vừa” là mức ngọt.
    value = re.sub(r"\bbanh ngot(?=\s*(?:[,.;!?]|$|va\b|voi\b|duoi\b|tren\b|gia\b|co\b|vi\b))", "banh nho", value)
    return value


def mentioned_catalog_groups(text: str, ignored_names=(), *, named_groups=None) -> set[str]:
    """Chỉ chọn ví dụ/kiểm chứng nhóm rõ; không tạo intent, filter hay ID."""
    value = normalize_shopping_terms(text.replace(";", ",").replace("?", ",").replace("!", ","))
    labels = {"cream_cake": "banh kem", "mini": "banh nho", "coffee": "ca phe", "tea": "tra"}
    named_groups = named_groups or {}
    for name in sorted(set(ignored_names) | set(named_groups), key=len, reverse=True):
        phrase = normalize_shopping_terms(name)
        if phrase:
            replacement = labels.get(named_groups.get(name), " ")
            value = re.sub(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", replacement, value)
    groups = set()
    mapping = {"banh kem": "cream_cake", "banh nho": "mini", "ca phe": "coffee",
               "tra": "tea", "do uong": "drink", "banh": "cake"}
    pattern = (r"\b(?:banh kem|banh nho|ca phe|do uong|tra|"
               r"banh(?=\s*(?:,|va\b|voi\b|gia\b|duoi\b|tren\b|nao\b|co\b|vi\b|$)))\b")
    for match in re.finditer(pattern, value):
        kind = mapping[match[0]]
        before = re.split(r"[,.;]|\b(?:va|voi)\b", value[:match.start()])[-1]
        if re.search(r"\b(?:khong|tranh|ngoai tru|bo)(?:\s+(?:can|muon|chon|tim|lay|phai))*\s*$", before):
            continue
        if kind in {"tea", "coffee"} and re.search(r"\b(?:vi|huong)\b[^,.;]*$", before):
            continue  # Vị trà xanh/cà phê của bánh không là một nhóm đồ uống khác.
        groups.add(kind)
    return groups


def numeric_evidence_text(text: str) -> str:
    """Bỏ dấu chữ, giữ dấu tiền/khoảng; dùng chung thay ba regex lệch nhau."""
    decomposed = unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


MONEY_NUMBER = r"\d+(?:[.,]\d+)*"
MONEY_UNIT = r"(?:nghin|ngan|trieu|tr|k|vnd|dong|d|₫)"
_MONEY_LITERAL = re.compile(r"(?<!\w)(" + MONEY_NUMBER + r")\s*(" + MONEY_UNIT + r")(?!\w)")
_MONEY_RANGE = re.compile(r"(?<!\w)(" + MONEY_NUMBER + r")\s*(" + MONEY_UNIT + r")?\s*"
    r"(?:-|–|—|~|den|toi)\s*(" + MONEY_NUMBER + r")\s*(" + MONEY_UNIT + r")?(?!\w)")
# Cụm ngân sách xấp xỉ phải thắng từ "giá" đứng sát số; không phải giá đúng.
APPROXIMATE_BUDGET_CUE = (r"(?:trong\s+)?(?:tam(?:\s+khoang)?|khoang)(?:\s+(?:gia|tien))?(?:\s+khoang)?"
                          r"|trong\s+(?:muc\s+)?gia")
_BUDGET_CUES = {
    "upper_strict": r"duoi|it hon|thap hon|chua toi|re hon",
    "upper_inclusive": r"khong (?:qua|vuot|hon|tren)|khong nhieu hon|dung qua|toi da|co|con|ngan sach(?: la)?" + "|" + APPROXIMATE_BUDGET_CUE,
    "lower_strict": r"tren|hon|cao hon|nhieu hon|dat hon|mac hon",
    "lower_inclusive": r"khong (?:duoi|it hon|thap hon)|it nhat|toi thieu|tu",
    "exact": r"cung gia|dong gia|bang gia|gia dung|gia(?: la)?|dung|chinh xac",
}


def parse_money(amount: str, unit: str | None) -> int:
    """300k/300.000/0,3 triệu → VNĐ nguyên; Decimal tránh lỗi số thực."""
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", amount) and not amount.startswith(("0.", "0,")):
        amount = amount.replace(".", "").replace(",", "")
    number = Decimal(amount.replace(",", "."))
    multiplier = 1_000_000 if unit in {"tr", "trieu"} else 1_000 if unit in {"k", "ngan", "nghin"} else 1
    return int(round(number * multiplier))


def normalize_money_evidence(text: str) -> str:
    """Chỉ so câu nguồn: 450k/450 nghìn/450.000đ cùng giá trị, giữ các từ khác."""
    value = normalize_shopping_terms(text)
    return _MONEY_LITERAL.sub(lambda match: str(parse_money(match[1], match[2])), value)


def budget_evidence(text: str) -> dict:
    """Bằng chứng tiền để chọn mẫu và bác output sai; KHÔNG áp filter thay Qwen."""
    raw = numeric_evidence_text(text)
    values = {parse_money(m[1], m[2]) for m in _MONEY_LITERAL.finditer(raw)}
    # Cách viết phổ biến 1tr5 = 1,5 triệu; chỉ xác minh số, không trích intent.
    values.update(int(m[1]) * 1_000_000 + int(m[2]) * 100_000
                  for m in re.finditer(r"(?<!\w)(\d+)tr(\d)(?!\w)", raw))
    expected, shapes, spans = {}, set(), []
    money_context = bool(re.search(r"\b(?:gia|tien|ngan sach|muc|tai chinh)\b", raw)
        or (re.search(r"\b(?:san pham|sp|mon|mat hang|banh|tra|ca phe)\b", raw)
            and re.search(r"\b(?:tu|khoang)\b", raw)
            and not re.search(r"\b(?:ngay|thang|nam)\b", raw)))
    for match in _MONEY_RANGE.finditer(raw):
        left_unit, right_unit = match[2], match[4]
        if not left_unit and not right_unit and not money_context:
            continue
        lower = parse_money(match[1], left_unit or right_unit)
        upper = parse_money(match[3], right_unit or left_unit)
        if not (left_unit or right_unit) and min(lower, upper) < 1000:
            continue  # Không đoán 300-400 không đơn vị thành nghìn đồng.
        values.update((lower, upper)); spans.append(match.span()); shapes.add("range")
        expected.update(min_budget_vnd=lower, budget_vnd=upper, min_price_inclusive=True, price_inclusive=True)
    candidates = []
    for shape, cue in _BUDGET_CUES.items():
        pattern = r"\b(?:" + cue + r")\s*:?\s*(" + MONEY_NUMBER + r")\s*(" + MONEY_UNIT + r")?(?!\w)"
        for match in re.finditer(pattern, raw):
            if any(match.start(1) < end and match.end(1) > start for start, end in spans):
                continue
            value = parse_money(match[1], match[2])
            if not match[2] and value < 1000:
                continue
            candidates.append((match.start(), match.end(), shape, value))
    # Cụm dài ưu tiên: "không dưới" không bị đọc thành "dưới".
    accepted = []
    for start, end, shape, value in sorted(candidates, key=lambda m: (m[0]-m[1], m[0])):
        if not any(start < b and end > a for a, b in spans + accepted):
            accepted.append((start, end)); shapes.add(shape); values.add(value)
            if shape == "exact":
                expected.update(min_budget_vnd=value, budget_vnd=value, min_price_inclusive=True, price_inclusive=True)
            elif shape.startswith("upper"):
                expected.update(budget_vnd=value, price_inclusive=shape.endswith("inclusive"))
            else:
                expected.update(min_budget_vnd=value, min_price_inclusive=shape.endswith("inclusive"))
    for match in re.finditer(r"(?<!\w)(" + MONEY_NUMBER + r")\s*(" + MONEY_UNIT + r")\s+(tro len|tro xuong|do xuong)\b", raw):
        value = parse_money(match[1], match[2]); values.add(value)
        if match[3] == "tro len":
            expected.update(min_budget_vnd=value, min_price_inclusive=True); shapes.add("lower_inclusive")
        else:
            expected.update(budget_vnd=value, price_inclusive=True); shapes.add("upper_inclusive")
    return {"values": values, "shapes": shapes, "expected": expected}


# Cùng bằng chứng cho validator và chọn ví dụ; không trích intent/slot thay LLM.
ADVICE_PREFERENCE_CUES = {
    "sweetness": {"low": r"\bit ngot\b", "medium": r"\bngot vua\b", "high": r"\bngot (?:nhieu|dam)\b",
                  "sweet": r"(?<!it )(?<!khong )\bngot\b(?!\s+(?:nhieu|dam|vua)\b)"},
    "taste_family": {"fruit": r"\btrai cay\b", "chocolate": r"\b(?:chocolate|choco|socola|so co la)\b",
        "cream": r"\b(?:vi kem|kem sua|vani|vanilla|trang tri)\b", "milk_tea": r"\btra sua\b",
        "fruit_tea": r"\btra trai cay\b", "matcha": r"\b(?:tra xanh|matcha)\b",
        "vanilla": r"\b(?:vani|vanilla)\b", "coffee_cream": r"\bca phe\s+(?:va\s+)?kem\b"},
    "coffee_style": {"strong": r"\b(?:dam|tinh tao)\b|(?<!it )\bdang\b", "creamy": r"\b(?:beo|man|de uong)\b",
        "mild": r"\b(?:diu|mat|it dang)\b"},
}
