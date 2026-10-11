"""Chuẩn hóa để so khớp; luôn giữ nguyên văn bản gốc ở nơi gọi."""

import re
import unicodedata


def normalize_text(text: str) -> str:
    """Chuyển chữ thường, bỏ dấu; giữ dấu . , để đọc số tiền."""
    decomposed = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    plain = re.sub(r"[^\w\s.,]", " ", plain)
    return re.sub(r"\s+", " ", plain).strip()


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
