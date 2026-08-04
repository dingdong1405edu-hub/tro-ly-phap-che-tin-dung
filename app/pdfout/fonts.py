"""Tìm và đăng ký font Unicode hỗ trợ tiếng Việt cho ReportLab.

Font mặc định của ReportLab (Helvetica) dùng bảng mã WinAnsi nên sẽ làm vỡ dấu
tiếng Việt. Module này dò tìm font TTF phù hợp theo thứ tự ưu tiên:
font đóng kèm dự án -> font hệ điều hành.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

BUNDLED_DIR = Path(__file__).resolve().parent / "fonts"

# Mỗi bộ: (tên hiển thị, regular, bold, italic, bold-italic)
FONT_CANDIDATES: list[tuple[str, list[str]]] = [
    ("DejaVuSans", ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf"]),
    ("TimesNewRoman", ["times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"]),
    ("Arial", ["arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"]),
    ("SegoeUI", ["segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"]),
    ("Tahoma", ["tahoma.ttf", "tahomabd.ttf", "tahoma.ttf", "tahomabd.ttf"]),
    ("Calibri", ["calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"]),
    ("LiberationSerif", [
        "LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf",
        "LiberationSerif-Italic.ttf", "LiberationSerif-BoldItalic.ttf",
    ]),
    ("NotoSans", ["NotoSans-Regular.ttf", "NotoSans-Bold.ttf", "NotoSans-Italic.ttf", "NotoSans-BoldItalic.ttf"]),
]

SEARCH_DIRS = [
    BUNDLED_DIR,
    Path("C:/Windows/Fonts"),
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts/truetype"),
    Path("/usr/share/fonts"),
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),
    Path.home() / ".fonts",
]


@dataclass
class FontSet:
    regular: str
    bold: str
    italic: str
    bold_italic: str


_cached: FontSet | None = None


def _find(file_name: str) -> Path | None:
    for d in SEARCH_DIRS:
        try:
            if not d.exists():
                continue
            p = d / file_name
            if p.exists():
                return p
            # Một số bản Linux đặt font trong thư mục con
            if d.name in {"truetype", "fonts"}:
                for sub in d.rglob(file_name):
                    return sub
        except (OSError, PermissionError):
            continue
    return None


def register_vietnamese_fonts() -> FontSet:
    """Đăng ký bộ font tiếng Việt đầu tiên tìm thấy. Ném lỗi rõ ràng nếu không có."""
    global _cached
    if _cached is not None:
        return _cached

    tried: list[str] = []
    for family, files in FONT_CANDIDATES:
        paths = [_find(f) for f in files]
        if not paths[0]:
            tried.append(files[0])
            continue

        regular_name = family
        bold_name = f"{family}-Bold"
        italic_name = f"{family}-Italic"
        bolditalic_name = f"{family}-BoldItalic"

        pdfmetrics.registerFont(TTFont(regular_name, str(paths[0])))
        pdfmetrics.registerFont(TTFont(bold_name, str(paths[1] or paths[0])))
        pdfmetrics.registerFont(TTFont(italic_name, str(paths[2] or paths[0])))
        pdfmetrics.registerFont(TTFont(bolditalic_name, str(paths[3] or paths[1] or paths[0])))
        pdfmetrics.registerFontFamily(
            regular_name, normal=regular_name, bold=bold_name, italic=italic_name, boldItalic=bolditalic_name
        )

        _cached = FontSet(regular_name, bold_name, italic_name, bolditalic_name)
        logger.info("Dùng font PDF: %s (%s)", family, paths[0])
        return _cached

    raise RuntimeError(
        "Không tìm thấy font TTF hỗ trợ tiếng Việt trên máy. "
        f"Đã thử: {', '.join(tried)}. "
        f"Cách khắc phục: tải DejaVuSans.ttf (và DejaVuSans-Bold.ttf) đặt vào thư mục {BUNDLED_DIR}"
    )
