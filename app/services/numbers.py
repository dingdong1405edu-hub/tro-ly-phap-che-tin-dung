"""Đọc - viết số tiền theo thói quen tiếng Việt.

Người dùng và cả model đều gõ tiền theo đủ kiểu: "5.000.000.000", "5 tỷ",
"1,2 tỷ đồng", "180 triệu/tháng", "9,5%/năm". Module này quy tất cả về float
để tính toán được, và định dạng ngược lại cho đẹp khi in ra hồ sơ.
"""

from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------- chuẩn hoá

_ACCENT_MAP = str.maketrans("đĐ", "dD")


def bo_dau(text: str) -> str:
    """Bỏ dấu tiếng Việt, hạ chữ thường — dùng để so khớp tên chỉ tiêu."""
    s = unicodedata.normalize("NFD", str(text or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.translate(_ACCENT_MAP).lower().strip()


# Hệ số nhân theo đơn vị viết tắt trong văn nói tiếng Việt
_DON_VI = [
    ("ty ty", 1e18),
    ("nghin ty", 1e12),
    ("ngan ty", 1e12),
    ("tram ty", 1e11),
    ("chuc ty", 1e10),
    ("tram trieu", 1e8),
    ("chuc trieu", 1e7),
    ("ty", 1e9),
    ("ti", 1e9),
    ("trieu", 1e6),
    ("tr", 1e6),
    ("nghin", 1e3),
    ("ngan", 1e3),
    ("k", 1e3),
]

_RE_SO = re.compile(r"[-+]?\d[\d.,\s]*")
_RE_DON_VI_THOI_GIAN = re.compile(r"^(nam|thang|quy|tuan|ngay|gio)\b")
_RE_DON_VI_TIEN = re.compile(r"ty|ti\b|trieu|nghin|ngan|vnd|dong|usd|eur")


def _tach_so(mau: str) -> float | None:
    """Đổi cụm chữ số kiểu Việt Nam sang float.

    Quy ước: dấu "." ngăn cách hàng nghìn, dấu "," ngăn cách thập phân.
    Nếu chỉ có dấu "." mà nhóm cuối không đủ 3 chữ số thì hiểu là dấu thập phân
    (kiểu Anh - Mỹ, model hay trả về như vậy).
    """
    raw = mau.replace(" ", "").strip(".,")
    if not raw:
        return None

    dau = -1.0 if raw.startswith("-") else 1.0
    raw = raw.lstrip("+-")

    if "," in raw and "." in raw:
        # "1.234.567,89" hoặc "1,234,567.89"
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        phan = raw.split(",")
        # Nhóm hàng nghìn không bao giờ mở đầu bằng số 0: "0,095" là số thập phân.
        nhom_nghin = (
            len(phan) > 1
            and all(len(p) == 3 for p in phan[1:])
            and 1 <= len(phan[0]) <= 3
            and not phan[0].startswith("0")
        )
        raw = raw.replace(",", "") if nhom_nghin else raw.replace(",", ".")
    elif "." in raw:
        phan = raw.split(".")
        if all(len(p) == 3 for p in phan[1:]) and not phan[0].startswith("0"):
            raw = raw.replace(".", "")           # "5.000.000.000"
        # còn lại giữ nguyên: "1.5" -> 1.5

    try:
        return dau * float(raw)
    except ValueError:
        return None


def doc_so(text: object, mac_dinh: float | None = None) -> float | None:
    """Trích số đầu tiên trong chuỗi, có nhân hệ số đơn vị (tỷ / triệu / nghìn)."""
    if text is None:
        return mac_dinh
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)

    goc = str(text).strip()
    if not goc:
        return mac_dinh

    phang = bo_dau(goc)
    m = _RE_SO.search(phang)
    if not m:
        return mac_dinh

    so = _tach_so(m.group(0))
    if so is None:
        return mac_dinh

    duoi = phang[m.end():].lstrip(" .-/")
    for tu, he_so in _DON_VI:
        if duoi.startswith(tu):
            ke_tiep = duoi[len(tu): len(tu) + 1]
            if ke_tiep.isalpha():          # tránh khớp nhầm "tr" trong "trong"
                continue
            return so * he_so
    return so


def doc_tien(text: object, mac_dinh: float | None = None) -> float | None:
    """Như doc_so nhưng loại bỏ các chuỗi rõ ràng không phải tiền (%, tháng...)."""
    if text is None:
        return mac_dinh
    phang = bo_dau(str(text))
    if not phang.strip():
        return mac_dinh
    if re.search(r"%|phan tram", phang) and not _RE_DON_VI_TIEN.search(phang):
        return mac_dinh

    # "trong 3 năm", "60 tháng" là mốc thời gian chứ không phải tiền
    m = _RE_SO.search(phang)
    if m:
        duoi = phang[m.end():].lstrip(" .-/")
        if _RE_DON_VI_THOI_GIAN.match(duoi) and not _RE_DON_VI_TIEN.search(phang):
            return mac_dinh
    return doc_so(text, mac_dinh)


def doc_tien_trong_cau(text: object, mac_dinh: float | None = None) -> float | None:
    """Rút số tiền từ một câu mô tả có nhiều con số.

    "Mua 04 xe đầu kéo (đơn giá 1.600.000.000/xe): 6.400.000.000 VND" phải ra
    6.400.000.000 chứ không phải 4 — nên ưu tiên con số **cuối cùng** có kèm đơn vị
    tiền tệ, thay vì con số đầu tiên gặp được.
    """
    if text is None:
        return mac_dinh
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)

    phang = bo_dau(str(text))
    if not phang.strip():
        return mac_dinh

    co_don_vi: list[float] = []
    khong_don_vi: list[float] = []
    for m in _RE_SO.finditer(phang):
        so = _tach_so(m.group(0))
        if so is None:
            continue
        duoi = phang[m.end():].lstrip(" .-/")
        if _RE_DON_VI_THOI_GIAN.match(duoi):
            continue
        he_so = 1.0
        khop = False
        for tu, hs in _DON_VI:
            if duoi.startswith(tu) and not duoi[len(tu): len(tu) + 1].isalpha():
                he_so, khop = hs, True
                break
        if khop or duoi.startswith(("vnd", "dong", "d/", "usd", "eur")):
            co_don_vi.append(so * he_so)
        else:
            khong_don_vi.append(so)

    if co_don_vi:
        return co_don_vi[-1]
    lon = [x for x in khong_don_vi if abs(x) >= 1000]
    if lon:
        return max(lon)
    return mac_dinh


def doc_phan_tram(text: object, mac_dinh: float | None = None) -> float | None:
    """Đọc lãi suất / tỷ lệ, luôn trả về đơn vị phần trăm (9,5%/năm -> 9.5)."""
    so = doc_so(text, None)
    if so is None:
        return mac_dinh
    # "0,095" hoặc "0.095" -> 9.5%
    if 0 < so < 1 and "%" not in str(text):
        return so * 100.0
    return so


def doc_thang(text: object, mac_dinh: int | None = None) -> int | None:
    """Đọc thời hạn vay ra số tháng: "60 tháng", "5 năm", "18 tháng"."""
    if text is None:
        return mac_dinh
    phang = bo_dau(str(text))
    m = _RE_SO.search(phang)
    if not m:
        return mac_dinh
    so = _tach_so(m.group(0))
    if so is None:
        return mac_dinh
    duoi = phang[m.end():]
    if re.search(r"\bnam\b", duoi):
        return int(round(so * 12))
    if re.search(r"\bquy\b", duoi):
        return int(round(so * 3))
    if re.search(r"\btuan\b", duoi):
        return max(1, int(round(so / 4.345)))
    if re.search(r"\bngay\b", duoi):
        return max(1, int(round(so / 30.0)))
    return int(round(so))


# --------------------------------------------------------------- định dạng


def dinh_dang(so: float | None, chu_so_thap_phan: int = 0) -> str:
    """1234567.8 -> "1.234.568" (dấu chấm ngăn nghìn, phẩy ngăn thập phân)."""
    if so is None:
        return ""
    try:
        s = f"{float(so):,.{chu_so_thap_phan}f}"
    except (TypeError, ValueError):
        return ""
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def dinh_dang_tien(so: float | None, don_vi: str = "VND") -> str:
    if so is None:
        return ""
    txt = dinh_dang(round(so))
    return f"{txt} {don_vi}".strip()


def rut_gon_tien(so: float | None, don_vi: str = "VND") -> str:
    """1_250_000_000 -> "1,25 tỷ VND" — dùng cho nhãn biểu đồ và bảng tóm tắt."""
    if so is None:
        return ""
    x = float(so)
    dau = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e9:
        thanh = f"{dinh_dang(x / 1e9, 2)} tỷ"
    elif x >= 1e6:
        thanh = f"{dinh_dang(x / 1e6, 1)} triệu"
    elif x >= 1e3:
        thanh = f"{dinh_dang(x / 1e3, 0)} nghìn"
    else:
        thanh = dinh_dang(x, 0)
    return f"{dau}{thanh} {don_vi}".strip()


def dinh_dang_phan_tram(so: float | None, chu_so: int = 1) -> str:
    if so is None:
        return ""
    return f"{dinh_dang(so, chu_so)}%"


def dinh_dang_lan(so: float | None, chu_so: int = 2) -> str:
    if so is None:
        return ""
    return f"{dinh_dang(so, chu_so)} lần"


# --------------------------------------------------------- đọc số thành chữ

_CHU_SO = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_HANG = ["", " nghìn", " triệu", " tỷ", " nghìn tỷ", " triệu tỷ"]


def _doc_ba_chu_so(n: int, day_du: bool) -> str:
    tram, chuc, donvi = n // 100, (n // 10) % 10, n % 10
    phan: list[str] = []

    if tram or day_du:
        phan.append(f"{_CHU_SO[tram]} trăm")

    if chuc == 0:
        if donvi and (tram or day_du):
            phan.append("lẻ")
        if donvi:
            phan.append(_CHU_SO[donvi])
    elif chuc == 1:
        phan.append("mười")
        if donvi == 1:
            phan.append("một")
        elif donvi == 5:
            phan.append("lăm")
        elif donvi:
            phan.append(_CHU_SO[donvi])
    else:
        phan.append(f"{_CHU_SO[chuc]} mươi")
        if donvi == 1:
            phan.append("mốt")
        elif donvi == 4:
            phan.append("tư")
        elif donvi == 5:
            phan.append("lăm")
        elif donvi:
            phan.append(_CHU_SO[donvi])

    return " ".join(phan)


def doc_thanh_chu(so: float | None, don_vi: str = "đồng") -> str:
    """1_250_000_000 -> "Một tỷ hai trăm năm mươi triệu đồng chẵn"."""
    if so is None:
        return ""
    n = int(round(abs(float(so))))
    if n == 0:
        return f"Không {don_vi}".strip()

    nhom: list[int] = []
    while n > 0:
        nhom.append(n % 1000)
        n //= 1000

    phan: list[str] = []
    for i in range(len(nhom) - 1, -1, -1):
        if nhom[i] == 0:
            continue
        day_du = i != len(nhom) - 1
        phan.append(_doc_ba_chu_so(nhom[i], day_du) + _HANG[i] if i < len(_HANG) else "")

    text = " ".join(p for p in phan if p)
    text = re.sub(r"\s+", " ", text).strip()
    dau = "Âm " if float(so) < 0 else ""
    ket = " chẵn" if int(round(abs(float(so)))) % 1000 == 0 else ""
    cau = f"{dau}{text} {don_vi}{ket}".strip()
    return cau[0].upper() + cau[1:]
