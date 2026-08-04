"""Cắt văn bản quy phạm pháp luật Việt Nam thành chunk theo đúng cấu trúc.

Nguyên tắc: một chunk lý tưởng = một **Điều** (kèm ngữ cảnh Chương/Mục).
Điều quá dài sẽ tách tiếp theo **Khoản**. Mỗi chunk đều được gắn "header ngữ cảnh"
ở đầu text để khi truy hồi ra vẫn tự đứng độc lập và trích dẫn được ngay.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

# ------------------------------------------------------------------ regex

RE_PHAN = re.compile(r"^\s*PH[ẦA]N\s+(?:TH[ỨU]\s+)?([IVXLCDM]+|\d+|[A-Za-zÀ-ỹ]+)\b[\.:]?\s*(.*)$", re.IGNORECASE)
RE_CHUONG = re.compile(r"^\s*CH[ƯU]{1}[ƠO]NG\s+([IVXLCDM]+|\d+)\b[\.:]?\s*(.*)$", re.IGNORECASE)
RE_MUC = re.compile(r"^\s*M[ỤU]C\s+(\d+|[IVXLCDM]+)\b[\.:]?\s*(.*)$", re.IGNORECASE)
RE_DIEU = re.compile(r"^\s*[ĐD]i[ềe]u\s+(\d+[a-zA-Z]?)\s*[\.:\-–]?\s*(.*)$", re.IGNORECASE)
RE_KHOAN = re.compile(r"^\s*(\d{1,2})[\.\)]\s+(.*)$")

RE_SO_HIEU = re.compile(r"\b(\d{1,4}\s*/\s*\d{4}\s*/\s*[A-ZĐ][A-ZĐ\-]{1,20})\b")
RE_SO_HIEU_LUAT = re.compile(r"\b(\d{1,3}\s*/\s*\d{4}\s*/\s*QH\d{1,2})\b")

LOAI_VAN_BAN = [
    "BỘ LUẬT",
    "LUẬT",
    "PHÁP LỆNH",
    "NGHỊ ĐỊNH",
    "NGHỊ QUYẾT",
    "THÔNG TƯ LIÊN TỊCH",
    "THÔNG TƯ",
    "QUYẾT ĐỊNH",
    "CHỈ THỊ",
    "CÔNG VĂN",
    "VĂN BẢN HỢP NHẤT",
]


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    order: int
    text: str  # text đầy đủ (header ngữ cảnh + nội dung) — dùng để embed & hiển thị
    body: str  # nội dung gốc không header
    doc_title: str = ""
    file_name: str = ""
    so_hieu: str = ""
    loai_van_ban: str = ""
    phan: str = ""
    chuong: str = ""
    muc: str = ""
    dieu: str = ""
    dieu_title: str = ""
    citation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Chunk":
        allowed = {f for f in Chunk.__dataclass_fields__}  # type: ignore[attr-defined]
        return Chunk(**{k: v for k, v in d.items() if k in allowed})


@dataclass
class DocMeta:
    doc_id: str
    file_name: str
    doc_title: str = ""
    so_hieu: str = ""
    loai_van_ban: str = ""
    n_chars: int = 0
    warnings: list[str] = field(default_factory=list)


# ------------------------------------------------------- metadata văn bản


def make_doc_id(file_name: str) -> str:
    return hashlib.sha1(file_name.encode("utf-8")).hexdigest()[:12]


def extract_doc_meta(text: str, file_name: str) -> DocMeta:
    """Đoán số hiệu, loại và tên văn bản từ phần đầu file."""
    head = "\n".join(text.split("\n")[:60])
    head_upper = head.upper()

    so_hieu = ""
    m = RE_SO_HIEU_LUAT.search(head) or RE_SO_HIEU.search(head)
    if not m:
        m = RE_SO_HIEU_LUAT.search(text[:8000]) or RE_SO_HIEU.search(text[:8000])
    if m:
        so_hieu = re.sub(r"\s+", "", m.group(1))

    loai = ""
    pos = len(head_upper) + 1
    for lv in LOAI_VAN_BAN:
        i = head_upper.find(lv)
        if i != -1 and i < pos:
            loai, pos = lv, i

    # Tên văn bản: dòng bắt đầu bằng "Quy định", "Về việc", hoặc dòng in hoa sau loại văn bản
    title = ""
    lines = [ln.strip() for ln in head.split("\n") if ln.strip()]
    for idx, ln in enumerate(lines):
        if ln.upper() == loai and loai:
            for nxt in lines[idx + 1 : idx + 5]:
                if RE_SO_HIEU.search(nxt) or len(nxt) < 8:
                    continue
                title = nxt
                break
            break
    if not title:
        for ln in lines:
            if re.match(r"^(Quy định|Về việc|Sửa đổi|Hướng dẫn|Ban hành)", ln, re.IGNORECASE) and len(ln) > 12:
                title = ln
                break

    title = re.sub(r"\s+", " ", title).strip(" .;:")
    parts = [p for p in (loai.title() if loai else "", so_hieu) if p]
    display = " ".join(parts)
    if title:
        display = f"{display} - {title}" if display else title
    if not display:
        display = file_name.rsplit(".", 1)[0]

    return DocMeta(
        doc_id=make_doc_id(file_name),
        file_name=file_name,
        doc_title=display[:300],
        so_hieu=so_hieu,
        loai_van_ban=loai.title() if loai else "",
        n_chars=len(text),
    )


def build_citation(meta: DocMeta, dieu: str) -> str:
    ten_ngan = " ".join(p for p in (meta.loai_van_ban, meta.so_hieu) if p) or meta.doc_title[:60]
    if dieu:
        return f"Điều {dieu}, {ten_ngan}"
    return ten_ngan


def _header(meta: DocMeta, phan: str, chuong: str, muc: str, dieu: str, dieu_title: str) -> str:
    bits = [f"[{meta.doc_title}]"]
    for b in (phan, chuong, muc):
        if b:
            bits.append(b)
    if dieu:
        bits.append(f"Điều {dieu}" + (f". {dieu_title}" if dieu_title else ""))
    return " > ".join(bits)


# ------------------------------------------------------------- cắt chunk


def _split_long_text(body: str, max_chars: int, overlap: int) -> list[str]:
    """Tách một khối dài theo Khoản, nếu vẫn dài thì theo đoạn/câu, có overlap."""
    lines = body.split("\n")

    # Gom theo khoản: mỗi khối bắt đầu tại dòng dạng "1. ", "2) "
    blocks: list[str] = []
    cur: list[str] = []
    for ln in lines:
        if RE_KHOAN.match(ln) and cur:
            blocks.append("\n".join(cur).strip())
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        blocks.append("\n".join(cur).strip())
    blocks = [b for b in blocks if b]

    # Khối nào vẫn quá dài thì cắt tiếp theo câu
    refined: list[str] = []
    for b in blocks:
        if len(b) <= max_chars:
            refined.append(b)
            continue
        sentences = re.split(r"(?<=[\.;:])\s+", b)
        buf = ""
        for s in sentences:
            if buf and len(buf) + len(s) + 1 > max_chars:
                refined.append(buf.strip())
                buf = buf[-overlap:] if overlap else ""
            buf = f"{buf} {s}".strip()
        if buf.strip():
            refined.append(buf.strip())

    # Gộp các khối nhỏ liền kề cho đến max_chars
    merged: list[str] = []
    buf = ""
    for b in refined:
        if buf and len(buf) + len(b) + 2 > max_chars:
            merged.append(buf)
            buf = b
        else:
            buf = f"{buf}\n{b}".strip()
    if buf:
        merged.append(buf)
    return merged or [body]


def chunk_document(
    text: str,
    file_name: str,
    max_chars: int = 1600,
    overlap: int = 200,
    meta: DocMeta | None = None,
) -> tuple[DocMeta, list[Chunk]]:
    """Cắt toàn bộ văn bản thành danh sách Chunk kèm metadata cấu trúc."""
    meta = meta or extract_doc_meta(text, file_name)
    lines = text.split("\n")

    phan = chuong = muc = ""
    cur_dieu = ""
    cur_dieu_title = ""
    buf: list[str] = []
    sections: list[dict[str, Any]] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append(
                {
                    "phan": phan,
                    "chuong": chuong,
                    "muc": muc,
                    "dieu": cur_dieu,
                    "dieu_title": cur_dieu_title,
                    "body": body,
                }
            )
        buf.clear()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            buf.append("")
            continue

        m_dieu = RE_DIEU.match(line)
        if m_dieu and len(line) < 250:
            flush()
            cur_dieu = m_dieu.group(1)
            cur_dieu_title = re.sub(r"\s+", " ", m_dieu.group(2)).strip(" .:-")
            buf.append(line)
            continue

        m_chuong = RE_CHUONG.match(line)
        if m_chuong and len(line) < 200:
            flush()
            tail = m_chuong.group(2).strip(" .:-")
            chuong = f"Chương {m_chuong.group(1).upper()}" + (f". {tail}" if tail else "")
            muc = ""
            cur_dieu = cur_dieu_title = ""
            continue

        m_muc = RE_MUC.match(line)
        if m_muc and len(line) < 200:
            flush()
            tail = m_muc.group(2).strip(" .:-")
            muc = f"Mục {m_muc.group(1)}" + (f". {tail}" if tail else "")
            cur_dieu = cur_dieu_title = ""
            continue

        m_phan = RE_PHAN.match(line)
        if m_phan and len(line) < 200 and line.upper() == line:
            flush()
            tail = m_phan.group(2).strip(" .:-")
            phan = f"Phần {m_phan.group(1).upper()}" + (f". {tail}" if tail else "")
            chuong = muc = ""
            cur_dieu = cur_dieu_title = ""
            continue

        buf.append(line)

    flush()

    # Không phát hiện được cấu trúc "Điều" -> cắt kiểu thường
    if not any(s["dieu"] for s in sections):
        sections = [
            {"phan": "", "chuong": "", "muc": "", "dieu": "", "dieu_title": "", "body": part}
            for part in _split_long_text(text, max_chars, overlap)
        ]

    chunks: list[Chunk] = []
    order = 0
    for sec in sections:
        body = sec["body"].strip()
        if len(body) < 25:
            continue
        pieces = [body] if len(body) <= max_chars else _split_long_text(body, max_chars, overlap)
        total = len(pieces)
        for i, piece in enumerate(pieces):
            header = _header(meta, sec["phan"], sec["chuong"], sec["muc"], sec["dieu"], sec["dieu_title"])
            if total > 1:
                header += f" (phần {i + 1}/{total})"
            chunk_id = f"{meta.doc_id}-{order:05d}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=meta.doc_id,
                    order=order,
                    text=f"{header}\n{piece}",
                    body=piece,
                    doc_title=meta.doc_title,
                    file_name=meta.file_name,
                    so_hieu=meta.so_hieu,
                    loai_van_ban=meta.loai_van_ban,
                    phan=sec["phan"],
                    chuong=sec["chuong"],
                    muc=sec["muc"],
                    dieu=sec["dieu"],
                    dieu_title=sec["dieu_title"],
                    citation=build_citation(meta, sec["dieu"]),
                )
            )
            order += 1

    return meta, chunks


def iter_supported_files(paths: Iterable) -> list:
    from .loader import SUPPORTED_EXTENSIONS

    out = []
    for p in paths:
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
            out.append(p)
    return sorted(out, key=lambda x: x.name.lower())
