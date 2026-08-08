"""Dựng file PDF "Hồ sơ đề nghị cấp tín dụng" từ đối tượng Dossier."""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import date
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from ..schemas import Dossier
from ..services.numbers import dinh_dang, doc_tien, rut_gon_tien
from . import charts
from .fonts import register_vietnamese_fonts

# Bảng màu
NAVY = colors.HexColor("#12315B")
ACCENT = colors.HexColor("#1F6FB2")
LIGHT = colors.HexColor("#EEF3F9")
BORDER = colors.HexColor("#C7D3E2")
MUTED = colors.HexColor("#5A6A7D")

MARGIN_X = 1.9 * cm
MARGIN_TOP = 2.0 * cm
MARGIN_BOTTOM = 2.0 * cm
USABLE_W = A4[0] - 2 * MARGIN_X

DISCLAIMER = (
    "Tài liệu được lập tự động bởi hệ thống Trợ lý Pháp chế Tín dụng, mang tính tham khảo. "
    "Nội dung cần được rà soát bởi cán bộ có thẩm quyền trước khi nộp cho tổ chức tín dụng."
)

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV"]


def esc(text: Any) -> str:
    """Escape cho mini-HTML của ReportLab Paragraph."""
    s = "" if text is None else str(text)
    s = unicodedata.normalize("NFC", s)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return s.replace("\n", "<br/>")


def _gon(text: Any) -> str:
    """Rút gọn số tiền cho các bảng nhiều cột: "4.090.000.000 VND" -> "4,09 tỷ VND"."""
    s = "" if text is None else str(text).strip()
    if not s:
        return ""
    so = doc_tien(s)
    return rut_gon_tien(so) if so is not None and abs(so) >= 1e6 else s


def _has(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


# ------------------------------------------------------------------ canvas


class NumberedCanvas(pdfcanvas.Canvas):
    """Canvas 2 lượt để in được 'Trang x / y' và chân trang trên mọi trang."""

    def __init__(self, *args, **kwargs) -> None:
        self._doc_title = kwargs.pop("doc_title", "")
        self._font = kwargs.pop("font", "Helvetica")
        super().__init__(*args, **kwargs)
        self._saved_states: list[dict] = []

    def showPage(self) -> None:  # noqa: N802 - API của ReportLab
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_decorations(total)
            super().showPage()
        super().save()

    def _draw_decorations(self, total_pages: int) -> None:
        page = self._pageNumber
        w, h = A4

        # Đầu trang (từ trang 2)
        if page > 1:
            self.setFont(self._font, 8)
            self.setFillColor(MUTED)
            self.drawString(MARGIN_X, h - 1.2 * cm, self._doc_title[:95])
            self.setStrokeColor(BORDER)
            self.setLineWidth(0.5)
            self.line(MARGIN_X, h - 1.35 * cm, w - MARGIN_X, h - 1.35 * cm)

        # Chân trang
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.5)
        self.line(MARGIN_X, 1.45 * cm, w - MARGIN_X, 1.45 * cm)
        self.setFont(self._font, 7.5)
        self.setFillColor(MUTED)
        self.drawString(MARGIN_X, 1.05 * cm, "Tài liệu tham khảo - cần rà soát trước khi sử dụng chính thức")
        self.drawRightString(w - MARGIN_X, 1.05 * cm, f"Trang {page} / {total_pages}")


# ------------------------------------------------------------------ styles


def _styles(fs) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    common = dict(fontName=fs.regular, textColor=colors.HexColor("#1B2430"))

    return {
        "cover_title": ParagraphStyle(
            "cover_title", parent=base, fontName=fs.bold, fontSize=21, leading=27,
            alignment=TA_CENTER, textColor=NAVY, spaceAfter=6,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", parent=base, fontName=fs.italic, fontSize=10.5, leading=15,
            alignment=TA_CENTER, textColor=MUTED, spaceAfter=4,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base, fontName=fs.bold, fontSize=12.5, leading=16,
            textColor=colors.white, spaceBefore=0, spaceAfter=0,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base, fontName=fs.bold, fontSize=10.5, leading=14,
            textColor=NAVY, spaceBefore=8, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "body", parent=base, fontSize=10, leading=14.5, alignment=TA_JUSTIFY,
            spaceAfter=4, **common,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=base, fontSize=10, leading=14.5, leftIndent=12,
            bulletIndent=3, spaceAfter=2.5, **common,
        ),
        "cell": ParagraphStyle("cell", parent=base, fontSize=9, leading=12.5, **common),
        "cell_b": ParagraphStyle(
            "cell_b", parent=base, fontName=fs.bold, fontSize=9, leading=12.5,
            textColor=colors.HexColor("#1B2430"),
        ),
        "cell_head": ParagraphStyle(
            "cell_head", parent=base, fontName=fs.bold, fontSize=9, leading=12.5, textColor=colors.white,
        ),
        "note": ParagraphStyle(
            "note", parent=base, fontName=fs.italic, fontSize=8.5, leading=12, textColor=MUTED, spaceBefore=4,
        ),
        "sign": ParagraphStyle(
            "sign", parent=base, fontName=fs.bold, fontSize=10, leading=14,
            alignment=TA_CENTER, textColor=NAVY,
        ),
        "sign_sub": ParagraphStyle(
            "sign_sub", parent=base, fontName=fs.italic, fontSize=8.5, leading=12,
            alignment=TA_CENTER, textColor=MUTED,
        ),
    }


# ------------------------------------------------------------ khối nội dung


class DossierBuilder:
    def __init__(
        self,
        dossier: Dossier,
        include_legal: bool = True,
        include_checklist: bool = True,
        include_appraisal: bool = True,
        include_charts: bool = True,
    ) -> None:
        self.d = dossier
        self.include_legal = include_legal
        self.include_checklist = include_checklist
        self.include_appraisal = include_appraisal
        self.include_charts = include_charts
        self.fs = register_vietnamese_fonts()
        self.st = _styles(self.fs)
        self.section_no = 0
        self.flow: list = []

    # ---- tiện ích dựng khối

    def section(self, title: str) -> None:
        self.section_no += 1
        label = ROMAN[self.section_no - 1] if self.section_no <= len(ROMAN) else str(self.section_no)
        para = Paragraph(f"{label}. {esc(title.upper())}", self.st["h1"])
        tbl = Table([[para]], colWidths=[USABLE_W])
        tbl.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        self.flow.append(Spacer(1, 10))
        self.flow.append(tbl)
        self.flow.append(Spacer(1, 7))

    def para(self, text: str) -> None:
        self.flow.append(Paragraph(esc(text), self.st["body"]))

    def bullets(self, items: list[str]) -> None:
        for it in items:
            if _has(it):
                self.flow.append(Paragraph(esc(it), self.st["bullet"], bulletText="•"))

    def kv_table(self, rows: list[tuple[str, Any]], label_w: float = 0.3) -> None:
        data = [
            [Paragraph(esc(k), self.st["cell_b"]), Paragraph(esc(v), self.st["cell"])]
            for k, v in rows
            if _has(v)
        ]
        if not data:
            return
        w1 = USABLE_W * label_w
        tbl = Table(data, colWidths=[w1, USABLE_W - w1], hAlign="LEFT")
        tbl.setStyle(
            TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("BACKGROUND", (0, 0), (0, -1), LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        self.flow.append(tbl)

    def grid_table(self, headers: list[str], rows: list[list[Any]], widths: list[float]) -> None:
        if not rows:
            return
        total = sum(widths)
        col_w = [USABLE_W * (w / total) for w in widths]

        data = [[Paragraph(esc(h), self.st["cell_head"]) for h in headers]]
        for r in rows:
            data.append([Paragraph(esc(c), self.st["cell"]) for c in r])

        tbl = Table(data, colWidths=col_w, repeatRows=1, hAlign="LEFT")
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(data)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F7FAFD")))
        tbl.setStyle(TableStyle(style))
        self.flow.append(tbl)

    def sub(self, text: str) -> None:
        self.flow.append(Paragraph(esc(text), self.st["h2"]))

    def hop_nhan_manh(self, tieu_de: str, dong: list[tuple[str, str]], mau=LIGHT) -> None:
        """Khối tô nền dùng cho kết luận thẩm định — thông tin quan trọng nhất trang."""
        noi_dung = [Paragraph(f"<b>{esc(tieu_de)}</b>", self.st["h2"])]
        for nhan, gia_tri in dong:
            if not _has(gia_tri):
                continue
            noi_dung.append(
                Paragraph(f"<b>{esc(nhan)}:</b> {esc(gia_tri)}", self.st["body"])
            )
        tbl = Table([[noi_dung]], colWidths=[USABLE_W])
        tbl.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), mau),
                ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ])
        )
        self.flow.append(KeepTogether(tbl))

    # ---- biểu đồ

    def _bang_bieu_do(self) -> dict:
        if not hasattr(self, "_bd_cache"):
            self._bd_cache = {b.ma: b for b in (self.d.bieu_do or [])}
            self._bd_da_ve: set[str] = set()
        return self._bd_cache

    def bieu_do(self, ma: str) -> None:
        """Chèn biểu đồ đúng chỗ nó thuộc về trong hồ sơ."""
        if not self.include_charts:
            return
        spec = self._bang_bieu_do().get(ma)
        if not spec or ma in self._bd_da_ve:
            return
        hinh = charts.ve(spec, USABLE_W, None, self.fs.regular, self.fs.bold)
        if hinh is None:
            return
        self._bd_da_ve.add(ma)

        khoi = [
            Spacer(1, 6),
            Paragraph(f"<b>Biểu đồ:</b> {esc(spec.tieu_de)}", self.st["h2"]),
        ]
        if _has(spec.mo_ta):
            khoi.append(Paragraph(esc(spec.mo_ta), self.st["note"]))
        khoi.append(Spacer(1, 3))
        khoi.append(hinh)
        if _has(spec.ghi_chu):
            khoi.append(Paragraph(esc(spec.ghi_chu), self.st["note"]))
        khoi.append(Spacer(1, 4))
        self.flow.append(KeepTogether(khoi))

    def bieu_do_con_lai(self) -> None:
        if not self.include_charts:
            return
        con = [b for ma, b in self._bang_bieu_do().items() if ma not in self._bd_da_ve]
        if not con:
            return
        self.section("Biểu đồ minh hoạ")
        for spec in con:
            self.bieu_do(spec.ma)

    # ---- các phần của hồ sơ

    def build_cover(self) -> None:
        d = self.d
        self.flow.append(Spacer(1, 1.0 * cm))
        self.flow.append(
            Paragraph("CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM", self.st["sign"])
        )
        self.flow.append(Paragraph("Độc lập - Tự do - Hạnh phúc", self.st["cover_sub"]))
        self.flow.append(Spacer(1, 0.9 * cm))

        self.flow.append(Paragraph(esc(d.tieu_de or "HỒ SƠ ĐỀ NGHỊ CẤP TÍN DỤNG"), self.st["cover_title"]))
        if _has(d.ben_vay.ten):
            self.flow.append(Paragraph(f"Bên đề nghị vay vốn: <b>{esc(d.ben_vay.ten)}</b>", self.st["cover_sub"]))
        if _has(d.to_chuc_tin_dung):
            self.flow.append(Paragraph(f"Kính gửi: {esc(d.to_chuc_tin_dung)}", self.st["cover_sub"]))

        ngay = d.ngay_lap or date.today().strftime("%d/%m/%Y")
        noi = f"{d.noi_lap}, " if _has(d.noi_lap) else ""
        self.flow.append(Paragraph(f"{noi}ngày {esc(ngay)}", self.st["cover_sub"]))
        self.flow.append(Spacer(1, 0.7 * cm))

        # Bảng tóm tắt nổi bật
        v = d.de_nghi_vay
        summary = [
            ("Số tiền đề nghị vay", f"{v.so_tien} {v.don_vi}".strip() if _has(v.so_tien) else ""),
            ("Bằng chữ", v.bang_chu),
            ("Mục đích vay vốn", v.muc_dich_vay),
            ("Thời hạn vay", v.thoi_han),
            ("Phương thức cho vay", v.phuong_thuc_cho_vay),
            ("Lãi suất dự kiến", v.lai_suat_du_kien),
            ("Vốn tự có tham gia", v.von_tu_co),
            ("Tỷ lệ vốn vay / tổng vốn", v.ty_le_vay_tren_tong_von),
        ]
        self.kv_table(summary, label_w=0.34)

        # Kết quả thẩm định đưa ngay lên trang bìa — đây là thứ người duyệt xem trước tiên
        tham_dinh = []
        if self.include_appraisal and d.tham_dinh_gia_tri.thuc_hien_duoc:
            tham_dinh.append(
                ("Giá trị doanh nghiệp sau thẩm định", d.tham_dinh_gia_tri.gia_tri_ket_luan_hien_thi)
            )
        if self.include_appraisal and d.ket_luan_tham_dinh.diem:
            k = d.ket_luan_tham_dinh
            tham_dinh.append(("Điểm tín dụng", f"{k.diem}/100 — xếp hạng {k.xep_hang} — rủi ro {k.muc_rui_ro}"))
            if _has(k.de_xuat):
                tham_dinh.append(("Đề xuất", k.de_xuat))
        if tham_dinh:
            self.flow.append(Spacer(1, 0.35 * cm))
            self.kv_table(tham_dinh, label_w=0.34)

        if _has(d.tom_tat_phuong_an):
            self.flow.append(Spacer(1, 0.45 * cm))
            self.flow.append(Paragraph("<b>Tóm tắt phương án</b>", self.st["h2"]))
            self.para(d.tom_tat_phuong_an)

        self.flow.append(Spacer(1, 0.5 * cm))
        self.flow.append(Paragraph(DISCLAIMER, self.st["note"]))
        self.flow.append(PageBreak())

    def build_borrower(self) -> None:
        b = self.d.ben_vay
        rows = [
            ("Tên bên vay", b.ten),
            ("Loại hình", b.loai_hinh),
            ("Mã số thuế", b.ma_so_thue),
            ("Số CCCD / ĐKKD", b.so_giay_to),
            ("Người đại diện", b.nguoi_dai_dien),
            ("Chức vụ", b.chuc_vu),
            ("Địa chỉ", b.dia_chi),
            ("Điện thoại", b.dien_thoai),
            ("Email", b.email),
            ("Ngành nghề kinh doanh", b.nganh_nghe),
            ("Năm thành lập", b.nam_thanh_lap),
            ("Vốn điều lệ", b.von_dieu_le),
        ]
        if not any(_has(v) for _, v in rows):
            return
        self.section("Thông tin bên đề nghị vay vốn")
        self.kv_table(rows)

    def build_loan_request(self) -> None:
        v = self.d.de_nghi_vay
        rows = [
            ("Số tiền vay", f"{v.so_tien} {v.don_vi}".strip() if _has(v.so_tien) else ""),
            ("Bằng chữ", v.bang_chu),
            ("Mục đích vay vốn", v.muc_dich_vay),
            ("Thời hạn vay", v.thoi_han),
            ("Phương thức cho vay", v.phuong_thuc_cho_vay),
            ("Phương thức giải ngân", v.phuong_thuc_giai_ngan),
            ("Phương thức trả nợ", v.phuong_thuc_tra_no),
            ("Lãi suất dự kiến", v.lai_suat_du_kien),
            ("Vốn tự có", v.von_tu_co),
            ("Tỷ lệ vốn vay / tổng vốn", v.ty_le_vay_tren_tong_von),
        ]
        if not any(_has(x) for _, x in rows):
            return
        self.section("Nội dung đề nghị cấp tín dụng")
        self.kv_table(rows)

    def build_plan(self) -> None:
        d = self.d
        if not (_has(d.phuong_an_su_dung_von) or _has(d.phuong_an_tra_no) or _has(d.dong_tien_du_kien)):
            return
        self.section("Phương án sử dụng vốn và trả nợ")

        if _has(d.phuong_an_su_dung_von):
            self.sub("1. Kế hoạch sử dụng vốn")
            self.bullets(d.phuong_an_su_dung_von)
            self.bieu_do("nguon_von")

        if _has(d.phuong_an_tra_no):
            self.sub("2. Nguồn trả nợ và kế hoạch trả nợ")
            self.para(d.phuong_an_tra_no)

        if _has(d.dong_tien_du_kien):
            self.sub("3. Dòng tiền dự kiến và lịch trả nợ")
            self.para(
                "Cột “Dòng tiền vào” là dòng tiền thuần từ hoạt động sau khi đã dành phần trả nợ "
                "cho các khoản vay hiện hữu. Cột “Trả gốc”, “Trả lãi” và “Dư nợ cuối kỳ” tính riêng "
                "cho khoản vay đang đề nghị."
            )
            self.flow.append(Spacer(1, 3))
            self.grid_table(
                ["Kỳ", "Dòng tiền vào", "Trả gốc", "Trả lãi", "Tổng phải trả",
                 "Còn lại", "Dư nợ cuối kỳ", "DSCR"],
                [
                    [r.ky, _gon(r.dong_tien_vao), _gon(r.tra_goc), _gon(r.tra_lai),
                     _gon(r.dong_tien_ra), _gon(r.du_cuoi_ky), _gon(r.du_no_cuoi_ky), r.dscr]
                    for r in d.dong_tien_du_kien
                ],
                [1.0, 1.5, 1.3, 1.3, 1.4, 1.3, 1.3, 0.9],
            )
            self.bieu_do("tra_no")
            self.bieu_do("dscr")
            self.bieu_do("du_no")

    def build_financials(self) -> None:
        if not _has(self.d.tinh_hinh_tai_chinh):
            return
        self.section("Tình hình tài chính")
        self.grid_table(
            ["Chỉ tiêu", "Năm trước", "Năm hiện tại", "Dự kiến"],
            [[r.chi_tieu, r.nam_truoc, r.nam_hien_tai, r.du_kien] for r in self.d.tinh_hinh_tai_chinh],
            [2.6, 1.4, 1.4, 1.4],
        )
        self.bieu_do("kqkd")

    def build_ratios(self) -> None:
        if not (self.include_appraisal and _has(self.d.chi_so_tai_chinh)):
            return
        co_so = [c for c in self.d.chi_so_tai_chinh if c.so is not None]
        if not co_so:
            return
        self.section("Phân tích chỉ số tài chính")
        self.para(
            "Các chỉ số dưới đây do hệ thống tính trực tiếp từ bảng số liệu tài chính nêu trên. "
            "Cột “Ngưỡng tham chiếu” là mức thông lệ trong thẩm định tín dụng, không phải quy định "
            "bắt buộc của pháp luật."
        )
        self.flow.append(Spacer(1, 4))
        self.grid_table(
            ["Chỉ số", "Giá trị", "Ngưỡng tham chiếu", "Đánh giá", "Cách tính"],
            [[c.ten, c.gia_tri, c.nguong, c.danh_gia, c.cong_thuc] for c in co_so],
            [2.6, 1.1, 1.5, 1.1, 2.9],
        )

    def build_valuation(self) -> None:
        v = self.d.tham_dinh_gia_tri
        if not self.include_appraisal or not v or not (v.thuc_hien_duoc or _has(v.ly_do)):
            return

        self.section("Thẩm định giá trị doanh nghiệp")

        if not v.thuc_hien_duoc:
            self.para(v.ly_do or "Không đủ dữ liệu để thẩm định giá trị doanh nghiệp.")
            return

        self.hop_nhan_manh(
            "Kết quả thẩm định",
            [
                ("Giá trị doanh nghiệp", f"{v.gia_tri_ket_luan_hien_thi}"),
                ("Bằng chữ", v.gia_tri_bang_chu),
                ("Khoảng giá trị hợp lý", f"{v.khoang_thap} — {v.khoang_cao}"),
                ("Kỳ số liệu cơ sở", v.nam_co_so),
            ],
        )
        self.flow.append(Spacer(1, 8))
        self.bieu_do("dinh_gia")

        self.sub("1. Các giả định sử dụng")
        self.grid_table(
            ["Giả định", "Giá trị", "Căn cứ"],
            [[a.ten, a.gia_tri, a.can_cu] for a in v.gia_dinh],
            [2.2, 1.6, 4.4],
        )

        self.sub("2. Kết quả theo từng phương pháp")
        self.grid_table(
            ["Phương pháp", "Giá trị", "Trọng số", "Diễn giải"],
            [
                [
                    p.ten,
                    p.gia_tri_hien_thi if p.ap_dung_duoc else "Không áp dụng",
                    f"{dinh_dang(p.trong_so * 100, 0)}%" if p.ap_dung_duoc else "—",
                    p.dien_giai or p.ly_do_khong_ap_dung,
                ]
                for p in v.phuong_phap
            ],
            [2.3, 1.7, 0.8, 4.4],
        )

        for p in v.phuong_phap:
            if not (p.ap_dung_duoc and p.chi_tiet):
                continue
            self.sub(f"Chi tiết — {p.ten}")
            self.grid_table(
                ["Khoản mục", "Giá trị", "Ghi chú"],
                [[c.khoan_muc, c.gia_tri, c.ghi_chu] for c in p.chi_tiet],
                [3.2, 2.2, 3.4],
            )

        if _has(v.dcf_chi_tiet):
            self.sub("3. Bảng chiết khấu dòng tiền")
            self.grid_table(
                ["Kỳ", "Dòng tiền tự do", "Hệ số chiết khấu", "Giá trị hiện tại"],
                [[r.nam, r.dong_tien_tu_do, r.he_so_chiet_khau, r.gia_tri_hien_tai]
                 for r in v.dcf_chi_tiet],
                [1.4, 2.4, 1.6, 2.4],
            )

        if _has(v.nhan_xet):
            self.sub("4. Nhận xét")
            self.bullets(v.nhan_xet)
        if _has(v.canh_bao):
            self.sub("Lưu ý")
            self.bullets(v.canh_bao)

    def build_conclusion(self) -> None:
        k = self.d.ket_luan_tham_dinh
        if not self.include_appraisal or not k or not k.diem:
            return
        self.section("Kết luận thẩm định và đề xuất")

        self.hop_nhan_manh(
            "Chấm điểm tín dụng",
            [
                ("Điểm tổng hợp", f"{k.diem}/100"),
                ("Xếp hạng", k.xep_hang),
                ("Mức rủi ro", k.muc_rui_ro),
                ("Đề xuất", k.de_xuat),
                ("Hạn mức đề xuất", k.han_muc_de_xuat),
            ],
        )
        self.flow.append(Spacer(1, 8))

        if _has(k.thanh_phan_diem):
            self.sub("1. Cấu phần điểm")
            self.grid_table(
                ["Cấu phần", "Điểm đạt", "Đánh giá", "Nội dung xét"],
                [[t.ten, t.gia_tri, t.danh_gia, t.y_nghia] for t in k.thanh_phan_diem],
                [2.4, 1.0, 1.2, 4.4],
            )

        if _has(k.cac_diem_manh):
            self.sub("2. Điểm mạnh")
            self.bullets(k.cac_diem_manh)
        if _has(k.cac_diem_yeu):
            self.sub("3. Điểm cần lưu ý")
            self.bullets(k.cac_diem_yeu)
        if _has(k.dieu_kien_kem_theo):
            self.sub("4. Điều kiện kèm theo đề xuất")
            self.bullets(k.dieu_kien_kem_theo)

    def build_collateral(self) -> None:
        if not _has(self.d.tai_san_bao_dam):
            return
        self.section("Tài sản bảo đảm")
        self.grid_table(
            ["Tài sản", "Mô tả", "Giá trị ước tính", "Giấy tờ pháp lý", "Ghi chú"],
            [
                [r.ten_tai_san, r.mo_ta, r.gia_tri_uoc_tinh, r.giay_to_phap_ly, r.ghi_chu]
                for r in self.d.tai_san_bao_dam
            ],
            [1.7, 2.3, 1.3, 1.9, 1.3],
        )
        self.bieu_do("tsbd")

    def build_checklist(self) -> None:
        if not (self.include_checklist and _has(self.d.danh_muc_ho_so)):
            return
        self.section("Danh mục hồ sơ phải nộp")
        self.para(
            "Bảng dưới đây liệt kê tài liệu cần chuẩn bị. Cột “Bắt buộc” đánh dấu tài liệu "
            "không thể thiếu; cột “Căn cứ” dẫn chiếu quy định pháp luật tương ứng."
        )
        self.flow.append(Spacer(1, 4))

        rows = []
        for i, item in enumerate(self.d.danh_muc_ho_so, start=1):
            rows.append([
                str(i),
                item.nhom,
                item.ten_tai_lieu,
                "Bắt buộc" if item.bat_buoc else "Bổ sung",
                item.can_cu_phap_ly,
                "[    ]",  # ô tích tay — dùng ký tự ASCII để font nào cũng hiển thị được
            ])
        self.grid_table(
            ["TT", "Nhóm hồ sơ", "Tên tài liệu", "Yêu cầu", "Căn cứ pháp lý", "Đã có"],
            rows,
            [0.5, 1.6, 3.0, 1.0, 2.2, 0.6],
        )

    def build_legal(self) -> None:
        if not (self.include_legal and _has(self.d.can_cu_phap_ly)):
            return
        self.section("Căn cứ pháp lý áp dụng")
        self.grid_table(
            ["Văn bản", "Điều khoản", "Nội dung quy định", "Áp dụng cho hồ sơ"],
            [[r.van_ban, r.dieu_khoan, r.noi_dung, r.ap_dung] for r in self.d.can_cu_phap_ly],
            [2.0, 1.2, 3.2, 2.2],
        )

    def build_risks(self) -> None:
        if not _has(self.d.danh_gia_rui_ro):
            return
        self.section("Đánh giá rủi ro và biện pháp giảm thiểu")
        self.grid_table(
            ["Rủi ro", "Mức độ", "Biện pháp giảm thiểu"],
            [[r.rui_ro, r.muc_do, r.bien_phap] for r in self.d.danh_gia_rui_ro],
            [2.8, 1.0, 4.0],
        )

    def build_recommendations(self) -> None:
        d = self.d
        if not (_has(d.khuyen_nghi) or _has(d.ghi_chu)):
            return
        self.section("Khuyến nghị hoàn thiện hồ sơ")
        if _has(d.khuyen_nghi):
            self.bullets(d.khuyen_nghi)
        if _has(d.ghi_chu):
            self.flow.append(Spacer(1, 4))
            self.flow.append(Paragraph("<b>Ghi chú:</b>", self.st["h2"]))
            self.para(d.ghi_chu)

    def build_signature(self) -> None:
        ngay = self.d.ngay_lap or date.today().strftime("%d/%m/%Y")
        noi = self.d.noi_lap or "………………"
        left = [
            Paragraph("XÁC NHẬN CỦA TỔ CHỨC TÍN DỤNG", self.st["sign"]),
            Paragraph("(Ký, ghi rõ họ tên, đóng dấu)", self.st["sign_sub"]),
            Spacer(1, 2.0 * cm),
        ]
        right = [
            Paragraph(f"{esc(noi)}, ngày {esc(ngay)}", self.st["sign_sub"]),
            Paragraph("ĐẠI DIỆN BÊN VAY", self.st["sign"]),
            Paragraph("(Ký, ghi rõ họ tên, đóng dấu)", self.st["sign_sub"]),
            Spacer(1, 1.7 * cm),
            Paragraph(esc(self.d.ben_vay.nguoi_dai_dien or ""), self.st["sign"]),
        ]
        tbl = Table([[left, right]], colWidths=[USABLE_W / 2, USABLE_W / 2])
        tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        self.flow.append(Spacer(1, 0.9 * cm))
        self.flow.append(KeepTogether(tbl))

    def build(self) -> list:
        self.build_cover()
        self.build_borrower()
        self.build_loan_request()
        self.build_plan()
        self.build_financials()
        self.build_ratios()
        self.build_valuation()
        self.build_collateral()
        self.build_conclusion()
        self.build_checklist()
        self.build_legal()
        self.build_risks()
        self.build_recommendations()
        self.bieu_do_con_lai()
        self.build_signature()
        self.flow.append(Spacer(1, 0.6 * cm))
        self.flow.append(Paragraph(DISCLAIMER, self.st["note"]))
        return self.flow


# ------------------------------------------------------------------- render


def build_dossier_pdf(
    dossier: Dossier,
    include_legal: bool = True,
    include_checklist: bool = True,
    include_appraisal: bool = True,
    include_charts: bool = True,
) -> bytes:
    builder = DossierBuilder(dossier, include_legal, include_checklist, include_appraisal, include_charts)
    story = builder.build()

    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=dossier.tieu_de or "Hồ sơ đề nghị cấp tín dụng",
        author="Trợ lý Pháp chế Tín dụng",
        subject="Hồ sơ đề nghị cấp tín dụng",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame])])

    header_title = dossier.tieu_de or "Hồ sơ đề nghị cấp tín dụng"
    if dossier.ben_vay.ten:
        header_title = f"{header_title} — {dossier.ben_vay.ten}"

    def canvas_maker(*args, **kwargs):
        return NumberedCanvas(*args, doc_title=header_title, font=builder.fs.regular, **kwargs)

    doc.build(story, canvasmaker=canvas_maker)
    return buf.getvalue()


def safe_filename(dossier: Dossier, custom: str = "") -> str:
    if custom.strip():
        base = custom.strip()
    else:
        who = dossier.ben_vay.ten or "ho-so-vay-von"
        base = f"Ho-so-de-nghi-cap-tin-dung_{who}"
    base = unicodedata.normalize("NFD", base)
    base = "".join(ch for ch in base if unicodedata.category(ch) != "Mn").replace("đ", "d").replace("Đ", "D")
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-._") or "ho-so-vay-von"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base[:120]
