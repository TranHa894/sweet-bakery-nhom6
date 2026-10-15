"""Chuẩn hóa để so khớp; luôn giữ nguyên văn bản gốc ở nơi gọi."""

import re
import unicodedata


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
