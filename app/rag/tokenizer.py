"""Tách từ tiếng Việt đơn giản, tối ưu cho tra cứu văn bản luật.

Tiếng Việt là ngôn ngữ đa âm tiết nên chỉ dùng unigram sẽ mất nghĩa
("vay vốn", "tài sản bảo đảm"...). Ở đây ta sinh cả unigram + bigram âm tiết,
đủ tốt cho BM25/TF-IDF mà không cần thư viện tách từ nặng.
"""

from __future__ import annotations

import re
import unicodedata

# Từ dừng phổ biến (giữ lại các từ có nghĩa pháp lý như "phải", "không")
STOPWORDS = {
    "và", "là", "của", "có", "cho", "các", "được", "trong", "với", "này",
    "đó", "một", "những", "từ", "khi", "thì", "đã", "sẽ", "về", "tại",
    "theo", "như", "để", "bị", "hoặc", "nếu", "mà", "còn", "cũng", "vào",
    "ra", "lên", "xuống", "rất", "nhiều", "ít", "trên", "dưới", "sau", "trước",
}

RE_TOKEN = re.compile(r"[0-9a-zà-ỹđ]+", re.IGNORECASE)


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


def syllables(text: str) -> list[str]:
    return RE_TOKEN.findall(normalize(text))


def tokenize(
    text: str,
    use_bigram: bool = True,
    drop_stopwords: bool = True,
    add_ascii: bool = True,
) -> list[str]:
    """Sinh danh sách token: unigram (đã lọc stopword) + bigram âm tiết liền kề.

    ``add_ascii`` bổ sung thêm bản không dấu của mỗi token vào cả tài liệu lẫn
    truy vấn, nhờ đó người dùng gõ "tai san bao dam" vẫn tìm ra "tài sản bảo đảm".
    """
    syls = syllables(text)
    tokens: list[str] = []

    def push(tok: str) -> None:
        tokens.append(tok)
        if add_ascii:
            plain = strip_accents(tok)
            if plain != tok:
                tokens.append(plain)

    for s in syls:
        if drop_stopwords and s in STOPWORDS:
            continue
        if len(s) == 1 and not s.isdigit():
            continue
        push(s)

    if use_bigram:
        for i in range(len(syls) - 1):
            push(f"{syls[i]}_{syls[i + 1]}")

    return tokens


def strip_accents(text: str) -> str:
    """Bỏ dấu — dùng để so khớp khi người dùng gõ không dấu."""
    text = unicodedata.normalize("NFD", normalize(text))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("đ", "d")
