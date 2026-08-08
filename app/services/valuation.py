"""Thẩm định tín dụng bằng tính toán thuần Python — không nhờ model bịa số.

Gồm bốn khối:
  1. Bóc số liệu tài chính từ bảng người dùng nhập (khớp tên chỉ tiêu tiếng Việt).
  2. Tính bộ chỉ số tài chính kèm ngưỡng tham chiếu và đánh giá.
  3. Thẩm định giá trị doanh nghiệp theo 3 phương pháp: tài sản thuần, chiết khấu
     dòng tiền (DCF) và so sánh thị trường, rồi bình quân gia quyền ra kết luận.
  4. Lập lịch trả nợ, dòng tiền dự kiến, DSCR và chấm điểm tín dụng.

Mọi giả định đều được ghi lại trong `Valuation.gia_dinh` để cán bộ thẩm định
kiểm chứng được, đúng nguyên tắc "không suy diễn số liệu" của hệ thống.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from ..schemas import (
    AppraisalConclusion,
    CashflowRow,
    ChartSeries,
    ChartSpec,
    DcfYear,
    Dossier,
    FinancialRatio,
    Valuation,
    ValuationAssumption,
    ValuationDetail,
    ValuationMethod,
)
from .numbers import (
    bo_dau,
    dinh_dang,
    dinh_dang_lan,
    dinh_dang_phan_tram,
    dinh_dang_tien,
    doc_phan_tram,
    doc_so,
    doc_thang,
    doc_thanh_chu,
    doc_tien,
    rut_gon_tien,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------- tham số

THUE_TNDN = 0.20                 # thuế suất thu nhập doanh nghiệp phổ thông
LAI_SUAT_VAY_MAC_DINH = 10.5     # %/năm khi khách chưa nêu
LAI_SUAT_PHI_RUI_RO = 3.5        # %/năm — lợi suất trái phiếu Chính phủ 10 năm
PHAN_BU_RUI_RO_VCP = 8.5         # %/năm — phần bù rủi ro vốn cổ phần thị trường VN
HE_SO_BETA = 1.10                # beta tham chiếu nhóm doanh nghiệp SME
PHAN_BU_QUY_MO = 3.0             # %/năm — phần bù rủi ro quy mô nhỏ
TANG_TRUONG_VINH_VIEN = 3.0      # %/năm
SO_NAM_DU_BAO = 5
PE_THAM_CHIEU = 8.0              # lần — SME chưa niêm yết, đã chiết khấu thanh khoản
EV_EBITDA_THAM_CHIEU = 5.5       # lần
TY_LE_VON_LUU_DONG = 0.10        # ΔVLĐ ≈ 10% mức tăng doanh thu

TRONG_SO_GOC = {"NAV": 0.30, "DCF": 0.45, "MARKET": 0.25}

# Bảng màu đã kiểm định độ tương phản & mù màu (xem references/palette.md)
MAU = {
    "chinh": "#2a78d6",
    "phu": "#eb6834",
    "ba": "#1baf7a",
    "bon": "#eda100",
    "nam": "#e87ba4",
    "sau": "#008300",
    "nguong": "#d03b3b",
}

# --------------------------------------------------- bóc số liệu tài chính

CHI_TIEU = [
    ("doanh_thu", ("doanh thu thuan", "doanh thu ban hang", "tong doanh thu", "doanh thu")),
    ("gia_von", ("gia von hang ban", "gia von")),
    ("loi_nhuan_gop", ("loi nhuan gop",)),
    ("loi_nhuan_truoc_thue", ("loi nhuan truoc thue", "lntt", "lai truoc thue")),
    ("loi_nhuan_sau_thue", ("loi nhuan sau thue", "lnst", "loi nhuan rong", "lai rong", "loi nhuan")),
    ("ebitda", ("ebitda",)),
    ("khau_hao", ("khau hao",)),
    ("chi_phi_lai_vay", ("chi phi lai vay", "lai vay")),
    ("tai_san_ngan_han", ("tai san ngan han",)),
    ("tong_tai_san", ("tong tai san", "tong cong tai san", "tong nguon von")),
    ("hang_ton_kho", ("hang ton kho", "ton kho")),
    ("phai_thu", ("phai thu khach hang", "khoan phai thu", "phai thu")),
    ("tien", ("tien va cac khoan tuong duong tien", "tien va tuong duong tien", "tien mat")),
    ("no_ngan_han", ("no ngan han",)),
    ("no_vay", ("vay va no thue tai chinh", "du no vay", "no vay")),
    ("no_phai_tra", ("tong no phai tra", "no phai tra", "tong no")),
    ("von_chu_so_huu", ("von chu so huu", "vcsh", "von chu")),
    ("thu_nhap", ("thu nhap binh quan", "tong thu nhap", "thu nhap")),
    ("chi_phi_sinh_hoat", ("chi phi sinh hoat", "chi phi hoat dong", "tong chi phi")),
]

COT = ("nam_truoc", "nam_hien_tai", "du_kien")


@dataclass
class SoLieu:
    """Bảng số liệu đã chuẩn hoá: chi_tieu -> [năm trước, năm nay, dự kiến]."""

    bang: dict[str, list[float | None]] = field(default_factory=dict)
    nhan_ky: list[str] = field(default_factory=lambda: ["Năm trước", "Năm hiện tại", "Dự kiến"])

    def lay(self, khoa: str, cot: int = 1) -> float | None:
        """Lấy giá trị, tự lùi về cột liền trước nếu cột yêu cầu trống."""
        gia_tri = self.bang.get(khoa)
        if not gia_tri:
            return None
        for i in (cot, 1, 0, 2):
            if 0 <= i < len(gia_tri) and gia_tri[i] is not None:
                return gia_tri[i]
        return None

    def day(self, khoa: str) -> list[float | None]:
        return self.bang.get(khoa, [None, None, None])

    def co(self, *khoa: str) -> bool:
        return all(self.lay(k) is not None for k in khoa)

    def dat(self, khoa: str, cot: int, gia_tri: float | None) -> None:
        self.bang.setdefault(khoa, [None, None, None])[cot] = gia_tri


def _khop_chi_tieu(ten: str) -> str | None:
    phang = bo_dau(ten)
    if not phang:
        return None
    for khoa, mau in CHI_TIEU:
        for m in mau:
            if m in phang:
                return khoa
    return None


def _nhan_ky(d: Dossier) -> list[str]:
    """Đoán nhãn kỳ báo cáo từ các năm 4 chữ số xuất hiện trong dữ liệu."""
    nguon = " ".join(
        [r.chi_tieu for r in d.tinh_hinh_tai_chinh]
        + [d.tom_tat_phuong_an or "", d.ghi_chu or ""]
    )
    nam = sorted({int(x) for x in re.findall(r"\b(20[0-4]\d)\b", nguon)})
    nam = [n for n in nam if 2000 <= n <= date.today().year + 3]
    if len(nam) >= 3:
        nam = nam[-3:]
        return [str(nam[0]), str(nam[1]), f"{nam[2]} (DK)"]
    if len(nam) == 2:
        return [str(nam[0]), str(nam[1]), f"{nam[1] + 1} (DK)"]
    if len(nam) == 1:
        return [str(nam[0] - 1), str(nam[0]), f"{nam[0] + 1} (DK)"]
    return ["Năm trước", "Năm hiện tại", "Dự kiến"]


def boc_so_lieu(d: Dossier) -> SoLieu:
    sl = SoLieu(nhan_ky=_nhan_ky(d))
    for row in d.tinh_hinh_tai_chinh:
        khoa = _khop_chi_tieu(row.chi_tieu)
        if not khoa:
            continue
        for i, ten_cot in enumerate(COT):
            gia_tri = doc_tien(getattr(row, ten_cot, ""))
            if gia_tri is not None:
                sl.dat(khoa, i, gia_tri)

    # Suy ra các chỉ tiêu còn thiếu từ quan hệ kế toán cơ bản
    for i in range(3):
        tts = sl.day("tong_tai_san")[i]
        npt = sl.day("no_phai_tra")[i]
        vcsh = sl.day("von_chu_so_huu")[i]
        if vcsh is None and tts is not None and npt is not None:
            sl.dat("von_chu_so_huu", i, tts - npt)
        elif npt is None and tts is not None and vcsh is not None:
            sl.dat("no_phai_tra", i, tts - vcsh)
        elif tts is None and npt is not None and vcsh is not None:
            sl.dat("tong_tai_san", i, npt + vcsh)

        lnst = sl.day("loi_nhuan_sau_thue")[i]
        lntt = sl.day("loi_nhuan_truoc_thue")[i]
        if lntt is None and lnst is not None:
            sl.dat("loi_nhuan_truoc_thue", i, lnst / (1 - THUE_TNDN))
        elif lnst is None and lntt is not None:
            sl.dat("loi_nhuan_sau_thue", i, lntt * (1 - THUE_TNDN))

        dt = sl.day("doanh_thu")[i]
        gv = sl.day("gia_von")[i]
        if sl.day("loi_nhuan_gop")[i] is None and dt is not None and gv is not None:
            sl.dat("loi_nhuan_gop", i, dt - gv)

        lntt = sl.day("loi_nhuan_truoc_thue")[i]
        kh = sl.day("khau_hao")[i]
        lv = sl.day("chi_phi_lai_vay")[i]
        if sl.day("ebitda")[i] is None and lntt is not None and (kh is not None or lv is not None):
            sl.dat("ebitda", i, lntt + (kh or 0.0) + (lv or 0.0))
    return sl


# ------------------------------------------------------ chỉ số tài chính


def _danh_gia(so: float, tot: float, dat: float, cao_la_tot: bool = True) -> str:
    if cao_la_tot:
        if so >= tot:
            return "Tốt"
        if so >= dat:
            return "Đạt"
        return "Cần lưu ý"
    if so <= tot:
        return "Tốt"
    if so <= dat:
        return "Đạt"
    return "Cần lưu ý"


def _ty_le(tu: float | None, mau: float | None) -> float | None:
    if tu is None or mau in (None, 0):
        return None
    return tu / mau


def tinh_chi_so(d: Dossier, sl: SoLieu, dscr_bq: float | None = None) -> list[FinancialRatio]:
    cs: list[FinancialRatio] = []

    def them(ma, ten, so, don_vi, dinh_dang_fn, nguong, danh_gia, y_nghia, cong_thuc):
        cs.append(
            FinancialRatio(
                ma=ma, ten=ten, so=None if so is None else round(so, 4),
                gia_tri="—" if so is None else dinh_dang_fn(so), don_vi=don_vi,
                nguong=nguong, danh_gia="Không đủ dữ liệu" if so is None else danh_gia(so),
                y_nghia=y_nghia, cong_thuc=cong_thuc,
            )
        )

    dt_truoc, dt_nay = sl.day("doanh_thu")[0], sl.lay("doanh_thu")
    tang_truong = None
    if dt_truoc and dt_nay and dt_truoc > 0:
        tang_truong = (dt_nay / dt_truoc - 1) * 100
    them("tang_truong_dt", "Tăng trưởng doanh thu", tang_truong, "%", dinh_dang_phan_tram,
         "≥ 5%/năm", lambda x: _danh_gia(x, 15, 5),
         "Cho thấy quy mô hoạt động của khách hàng đang mở rộng hay thu hẹp.",
         "(Doanh thu kỳ này / Doanh thu kỳ trước − 1) × 100")

    bien_ln = _ty_le(sl.lay("loi_nhuan_sau_thue"), sl.lay("doanh_thu"))
    them("bien_lnst", "Biên lợi nhuận sau thuế", None if bien_ln is None else bien_ln * 100,
         "%", dinh_dang_phan_tram, "≥ 5%", lambda x: _danh_gia(x, 10, 4),
         "Một đồng doanh thu để lại bao nhiêu đồng lợi nhuận.",
         "Lợi nhuận sau thuế / Doanh thu")

    roa = _ty_le(sl.lay("loi_nhuan_sau_thue"), sl.lay("tong_tai_san"))
    them("roa", "ROA — Tỷ suất sinh lời trên tổng tài sản",
         None if roa is None else roa * 100, "%", dinh_dang_phan_tram,
         "≥ 5%", lambda x: _danh_gia(x, 10, 4),
         "Hiệu quả khai thác toàn bộ tài sản của doanh nghiệp.",
         "Lợi nhuận sau thuế / Tổng tài sản")

    roe = _ty_le(sl.lay("loi_nhuan_sau_thue"), sl.lay("von_chu_so_huu"))
    them("roe", "ROE — Tỷ suất sinh lời trên vốn chủ sở hữu",
         None if roe is None else roe * 100, "%", dinh_dang_phan_tram,
         "≥ 12%", lambda x: _danh_gia(x, 18, 10),
         "Mức sinh lời trên phần vốn chủ sở hữu thực góp.",
         "Lợi nhuận sau thuế / Vốn chủ sở hữu")

    de = _ty_le(sl.lay("no_phai_tra"), sl.lay("von_chu_so_huu"))
    them("no_vcsh", "Hệ số nợ trên vốn chủ sở hữu", de, "lần", dinh_dang_lan,
         "≤ 2,5 lần", lambda x: _danh_gia(x, 1.5, 2.5, cao_la_tot=False),
         "Mức độ phụ thuộc vào vốn vay; càng cao thì rủi ro tài chính càng lớn.",
         "Nợ phải trả / Vốn chủ sở hữu")

    tu_tai_tro = _ty_le(sl.lay("von_chu_so_huu"), sl.lay("tong_tai_san"))
    them("tu_tai_tro", "Hệ số tự tài trợ", None if tu_tai_tro is None else tu_tai_tro * 100,
         "%", dinh_dang_phan_tram, "≥ 30%", lambda x: _danh_gia(x, 40, 25),
         "Tỷ trọng vốn chủ trong tổng nguồn vốn — đệm chịu lỗ của doanh nghiệp.",
         "Vốn chủ sở hữu / Tổng tài sản")

    thanh_toan = _ty_le(sl.lay("tai_san_ngan_han"), sl.lay("no_ngan_han"))
    them("thanh_toan_hh", "Hệ số thanh toán hiện hành", thanh_toan, "lần", dinh_dang_lan,
         "≥ 1,2 lần", lambda x: _danh_gia(x, 1.5, 1.0),
         "Khả năng dùng tài sản ngắn hạn để trả các khoản nợ đến hạn trong 12 tháng.",
         "Tài sản ngắn hạn / Nợ ngắn hạn")

    vong_quay = _ty_le(sl.lay("gia_von"), sl.lay("hang_ton_kho"))
    them("vong_quay_htk", "Vòng quay hàng tồn kho", vong_quay, "lần", dinh_dang_lan,
         "≥ 4 vòng/năm", lambda x: _danh_gia(x, 6, 3),
         "Tốc độ luân chuyển hàng hoá; quá thấp là dấu hiệu ứ đọng vốn.",
         "Giá vốn hàng bán / Hàng tồn kho")

    ebit = sl.lay("loi_nhuan_truoc_thue")
    lai_vay = sl.lay("chi_phi_lai_vay")
    kha_nang_lai = None
    if ebit is not None and lai_vay:
        kha_nang_lai = (ebit + lai_vay) / lai_vay
    them("tra_lai", "Hệ số khả năng trả lãi vay", kha_nang_lai, "lần", dinh_dang_lan,
         "≥ 2 lần", lambda x: _danh_gia(x, 4, 2),
         "Lợi nhuận trước lãi vay gấp bao nhiêu lần chi phí lãi phải trả.",
         "(Lợi nhuận trước thuế + Lãi vay) / Lãi vay")

    them("dscr", "DSCR — Hệ số bảo đảm trả nợ bình quân", dscr_bq, "lần", dinh_dang_lan,
         "≥ 1,2 lần", lambda x: _danh_gia(x, 1.5, 1.2),
         "Dòng tiền còn lại sau khi trả nợ cũ gấp bao nhiêu lần nghĩa vụ của khoản vay này.",
         "(Lợi nhuận sau thuế + Khấu hao − Nghĩa vụ nợ hiện hữu) / (Trả gốc + Trả lãi) khoản vay mới")

    von_vay = doc_tien(d.de_nghi_vay.so_tien)
    gia_tri_tsbd = sum(x for x in (doc_tien(t.gia_tri_uoc_tinh) for t in d.tai_san_bao_dam) if x)
    ltv = _ty_le(von_vay, gia_tri_tsbd or None)
    them("ltv", "LTV — Dư nợ trên giá trị tài sản bảo đảm",
         None if ltv is None else ltv * 100, "%", dinh_dang_phan_tram,
         "≤ 70%", lambda x: _danh_gia(x, 60, 75, cao_la_tot=False),
         "Phần dư nợ được tài sản bảo đảm che phủ; càng thấp thì tổn thất dự kiến càng nhỏ.",
         "Số tiền vay / Tổng giá trị tài sản bảo đảm")

    von_tu_co = doc_tien(d.de_nghi_vay.von_tu_co)
    ty_le_tu_co = None
    if von_tu_co is not None and von_vay:
        tong_von = von_tu_co + von_vay
        ty_le_tu_co = von_tu_co / tong_von * 100 if tong_von else None
    them("von_tu_co", "Tỷ lệ vốn tự có tham gia phương án", ty_le_tu_co, "%",
         dinh_dang_phan_tram, "≥ 20%", lambda x: _danh_gia(x, 30, 15),
         "Phần vốn khách hàng bỏ ra — thể hiện mức độ cùng chịu rủi ro với ngân hàng.",
         "Vốn tự có / (Vốn tự có + Vốn vay)")

    return cs


# ------------------------------------------- thẩm định giá trị doanh nghiệp


def _tinh_wacc(sl: SoLieu, lai_suat_vay: float, no_moi: float | None) -> tuple[float, float, float]:
    """Trả về (WACC, chi phí vốn chủ, chi phí nợ sau thuế) — đơn vị %."""
    re_ = LAI_SUAT_PHI_RUI_RO + HE_SO_BETA * PHAN_BU_RUI_RO_VCP + PHAN_BU_QUY_MO
    rd = lai_suat_vay * (1 - THUE_TNDN)

    vcsh = sl.lay("von_chu_so_huu") or 0.0
    no = sl.lay("no_vay")
    if no is None:
        no = sl.lay("no_phai_tra") or 0.0
    no += no_moi or 0.0

    tong = vcsh + no
    if tong <= 0:
        wacc = re_
    else:
        wacc = (vcsh / tong) * re_ + (no / tong) * rd
    return max(9.0, min(wacc, 20.0)), re_, rd


def _phuong_phap_nav(sl: SoLieu) -> ValuationMethod:
    pp = ValuationMethod(ma="NAV", ten="Phương pháp tài sản thuần (NAV)", trong_so=0.0)
    tts, npt, vcsh = sl.lay("tong_tai_san"), sl.lay("no_phai_tra"), sl.lay("von_chu_so_huu")
    if vcsh is None:
        pp.ap_dung_duoc = False
        pp.ly_do_khong_ap_dung = "Thiếu Tổng tài sản hoặc Nợ phải trả nên không xác định được vốn chủ sở hữu."
        return pp

    pp.gia_tri = max(vcsh, 0.0)
    pp.gia_tri_hien_thi = dinh_dang_tien(pp.gia_tri)
    pp.dien_giai = (
        "Giá trị doanh nghiệp bằng tổng tài sản trừ toàn bộ nợ phải trả theo sổ sách. "
        "Đây là mức sàn tham chiếu, chưa tính giá trị thương hiệu và lợi thế kinh doanh."
    )
    pp.chi_tiet = [
        ValuationDetail(khoan_muc="Tổng tài sản", gia_tri=dinh_dang_tien(tts) or "—"),
        ValuationDetail(khoan_muc="Trừ: Nợ phải trả", gia_tri=dinh_dang_tien(npt) or "—"),
        ValuationDetail(khoan_muc="Giá trị tài sản thuần", gia_tri=dinh_dang_tien(pp.gia_tri),
                        ghi_chu="Bằng vốn chủ sở hữu theo sổ sách"),
    ]
    return pp


def _phuong_phap_dcf(sl: SoLieu, wacc: float, g: float) -> tuple[ValuationMethod, list[DcfYear]]:
    pp = ValuationMethod(ma="DCF", ten="Phương pháp chiết khấu dòng tiền (DCF)", trong_so=0.0)
    lntt = sl.lay("loi_nhuan_truoc_thue")
    if lntt is None or lntt <= 0:
        pp.ap_dung_duoc = False
        pp.ly_do_khong_ap_dung = (
            "Chưa có số liệu lợi nhuận, hoặc doanh nghiệp đang lỗ nên dòng tiền tự do không dương."
        )
        return pp, []
    if wacc <= TANG_TRUONG_VINH_VIEN + 0.5:
        pp.ap_dung_duoc = False
        pp.ly_do_khong_ap_dung = "Tỷ suất chiết khấu không lớn hơn tốc độ tăng trưởng dài hạn."
        return pp, []

    lai_vay = sl.lay("chi_phi_lai_vay") or 0.0
    khau_hao = sl.lay("khau_hao") or 0.0
    ebit = lntt + lai_vay
    nopat = ebit * (1 - THUE_TNDN)

    dt_truoc, dt_nay = sl.day("doanh_thu")[0], sl.lay("doanh_thu")
    if dt_truoc and dt_nay and dt_nay > dt_truoc:
        delta_vld = (dt_nay - dt_truoc) * TY_LE_VON_LUU_DONG
    elif dt_nay:
        delta_vld = dt_nay * (g / 100) * TY_LE_VON_LUU_DONG
    else:
        delta_vld = 0.0

    # Đầu tư duy trì giả định bằng khấu hao nên hai khoản này triệt tiêu nhau
    fcff_0 = nopat + khau_hao - khau_hao - delta_vld
    if fcff_0 <= 0:
        pp.ap_dung_duoc = False
        pp.ly_do_khong_ap_dung = "Dòng tiền tự do năm cơ sở không dương sau khi trừ nhu cầu vốn lưu động."
        return pp, []

    r = wacc / 100
    gr = g / 100
    gt = TANG_TRUONG_VINH_VIEN / 100

    chi_tiet: list[DcfYear] = []
    tong_pv = 0.0
    fcff_n = fcff_0
    for n in range(1, SO_NAM_DU_BAO + 1):
        fcff_n = fcff_0 * ((1 + gr) ** n)
        he_so = 1 / ((1 + r) ** n)
        pv = fcff_n * he_so
        tong_pv += pv
        chi_tiet.append(
            DcfYear(
                nam=f"Năm {n}",
                dong_tien_tu_do=dinh_dang_tien(fcff_n),
                he_so_chiet_khau=dinh_dang(he_so, 4),
                gia_tri_hien_tai=dinh_dang_tien(pv),
            )
        )

    gia_tri_cuoi = fcff_n * (1 + gt) / (r - gt)
    pv_cuoi = gia_tri_cuoi / ((1 + r) ** SO_NAM_DU_BAO)
    chi_tiet.append(
        DcfYear(
            nam="Giá trị cuối kỳ",
            dong_tien_tu_do=dinh_dang_tien(gia_tri_cuoi),
            he_so_chiet_khau=dinh_dang(1 / ((1 + r) ** SO_NAM_DU_BAO), 4),
            gia_tri_hien_tai=dinh_dang_tien(pv_cuoi),
        )
    )

    ev = tong_pv + pv_cuoi
    no_vay = sl.lay("no_vay")
    if no_vay is None:
        no_vay = sl.lay("no_phai_tra") or 0.0
        ghi_chu_no = "Chưa tách riêng nợ vay nên lấy toàn bộ nợ phải trả (thận trọng)"
    else:
        ghi_chu_no = ""
    tien = sl.lay("tien") or 0.0
    no_rong = max(no_vay - tien, 0.0)

    pp.gia_tri = max(ev - no_rong, 0.0)
    pp.gia_tri_hien_thi = dinh_dang_tien(pp.gia_tri)
    pp.dien_giai = (
        f"Chiết khấu dòng tiền tự do {SO_NAM_DU_BAO} năm cộng giá trị cuối kỳ theo mô hình Gordon, "
        f"tỷ suất chiết khấu WACC {dinh_dang_phan_tram(wacc)}, tăng trưởng giai đoạn dự báo "
        f"{dinh_dang_phan_tram(g)}, tăng trưởng vĩnh viễn {dinh_dang_phan_tram(TANG_TRUONG_VINH_VIEN)}."
    )
    pp.chi_tiet = [
        ValuationDetail(khoan_muc="Lợi nhuận trước thuế và lãi vay (EBIT)", gia_tri=dinh_dang_tien(ebit)),
        ValuationDetail(khoan_muc=f"Lợi nhuận sau thuế trên EBIT (thuế {int(THUE_TNDN * 100)}%)",
                        gia_tri=dinh_dang_tien(nopat)),
        ValuationDetail(khoan_muc="Trừ: tăng nhu cầu vốn lưu động", gia_tri=dinh_dang_tien(delta_vld),
                        ghi_chu=f"{int(TY_LE_VON_LUU_DONG * 100)}% mức tăng doanh thu"),
        ValuationDetail(khoan_muc="Dòng tiền tự do năm cơ sở", gia_tri=dinh_dang_tien(fcff_0)),
        ValuationDetail(khoan_muc=f"Hiện giá dòng tiền {SO_NAM_DU_BAO} năm", gia_tri=dinh_dang_tien(tong_pv)),
        ValuationDetail(khoan_muc="Hiện giá giá trị cuối kỳ", gia_tri=dinh_dang_tien(pv_cuoi)),
        ValuationDetail(khoan_muc="Giá trị doanh nghiệp (EV)", gia_tri=dinh_dang_tien(ev)),
        ValuationDetail(khoan_muc="Trừ: nợ vay ròng", gia_tri=dinh_dang_tien(no_rong), ghi_chu=ghi_chu_no),
        ValuationDetail(khoan_muc="Giá trị vốn chủ sở hữu", gia_tri=dinh_dang_tien(pp.gia_tri)),
    ]
    return pp, chi_tiet


def _phuong_phap_thi_truong(sl: SoLieu) -> ValuationMethod:
    pp = ValuationMethod(ma="MARKET", ten="Phương pháp so sánh thị trường", trong_so=0.0)
    lnst = sl.lay("loi_nhuan_sau_thue")
    ebitda = sl.lay("ebitda")

    ket_qua: list[tuple[str, float]] = []
    chi_tiet: list[ValuationDetail] = []

    if lnst is not None and lnst > 0:
        gt = lnst * PE_THAM_CHIEU
        ket_qua.append(("P/E", gt))
        chi_tiet.append(
            ValuationDetail(
                khoan_muc=f"Theo P/E tham chiếu {dinh_dang(PE_THAM_CHIEU, 1)} lần",
                gia_tri=dinh_dang_tien(gt),
                ghi_chu=f"Lợi nhuận sau thuế {rut_gon_tien(lnst)}",
            )
        )

    if ebitda is not None and ebitda > 0:
        no_vay = sl.lay("no_vay")
        if no_vay is None:
            no_vay = sl.lay("no_phai_tra") or 0.0
        no_rong = max(no_vay - (sl.lay("tien") or 0.0), 0.0)
        gt = max(ebitda * EV_EBITDA_THAM_CHIEU - no_rong, 0.0)
        ket_qua.append(("EV/EBITDA", gt))
        chi_tiet.append(
            ValuationDetail(
                khoan_muc=f"Theo EV/EBITDA tham chiếu {dinh_dang(EV_EBITDA_THAM_CHIEU, 1)} lần",
                gia_tri=dinh_dang_tien(gt),
                ghi_chu=f"EBITDA {rut_gon_tien(ebitda)}, trừ nợ vay ròng {rut_gon_tien(no_rong)}",
            )
        )

    if not ket_qua:
        pp.ap_dung_duoc = False
        pp.ly_do_khong_ap_dung = "Chưa có lợi nhuận sau thuế hoặc EBITDA dương để áp hệ số so sánh."
        return pp

    pp.gia_tri = sum(v for _, v in ket_qua) / len(ket_qua)
    pp.gia_tri_hien_thi = dinh_dang_tien(pp.gia_tri)
    pp.dien_giai = (
        "Áp hệ số định giá bình quân của nhóm doanh nghiệp cùng quy mô chưa niêm yết. "
        "Hệ số đã chiết khấu cho tính thanh khoản thấp của phần vốn góp."
    )
    chi_tiet.append(
        ValuationDetail(khoan_muc="Bình quân các hệ số", gia_tri=dinh_dang_tien(pp.gia_tri))
    )
    pp.chi_tiet = chi_tiet
    return pp


def tham_dinh_gia_tri(d: Dossier, sl: SoLieu) -> Valuation:
    kq = Valuation(nam_co_so=sl.nhan_ky[1])

    la_ca_nhan = "ca nhan" in bo_dau(d.ben_vay.loai_hinh)
    if la_ca_nhan:
        kq.thuc_hien_duoc = False
        kq.ly_do = (
            "Khách hàng là cá nhân nên không áp dụng thẩm định giá trị doanh nghiệp. "
            "Thay vào đó hệ thống đánh giá theo thu nhập và khả năng trả nợ."
        )
        return kq
    if not sl.bang:
        kq.thuc_hien_duoc = False
        kq.ly_do = (
            "Chưa có bảng số liệu tài chính nên không đủ cơ sở định giá. "
            "Cần bổ sung tối thiểu: doanh thu, lợi nhuận sau thuế, tổng tài sản, nợ phải trả."
        )
        return kq

    lai_suat = doc_phan_tram(d.de_nghi_vay.lai_suat_du_kien) or LAI_SUAT_VAY_MAC_DINH
    no_moi = doc_tien(d.de_nghi_vay.so_tien)
    wacc, re_, rd = _tinh_wacc(sl, lai_suat, no_moi)

    dt_truoc, dt_nay = sl.day("doanh_thu")[0], sl.lay("doanh_thu")
    if dt_truoc and dt_nay and dt_truoc > 0:
        g = max(0.0, min((dt_nay / dt_truoc - 1) * 100, 12.0))
        can_cu_g = "Tốc độ tăng doanh thu thực tế kỳ gần nhất, giới hạn trần 12%/năm cho thận trọng."
    else:
        g = 6.0
        can_cu_g = "Chưa đủ dữ liệu chuỗi doanh thu — dùng mức tăng trưởng thận trọng 6%/năm."

    nav = _phuong_phap_nav(sl)
    dcf, dcf_chi_tiet = _phuong_phap_dcf(sl, wacc, g)
    thi_truong = _phuong_phap_thi_truong(sl)
    danh_sach = [nav, dcf, thi_truong]

    ap_dung = [p for p in danh_sach if p.ap_dung_duoc and p.gia_tri > 0]
    if not ap_dung:
        kq.thuc_hien_duoc = False
        kq.ly_do = "Không phương pháp nào đủ dữ liệu đầu vào để định giá."
        kq.phuong_phap = danh_sach
        kq.canh_bao = [p.ly_do_khong_ap_dung for p in danh_sach if p.ly_do_khong_ap_dung]
        return kq

    tong_trong_so = sum(TRONG_SO_GOC[p.ma] for p in ap_dung)
    for p in danh_sach:
        p.trong_so = round(TRONG_SO_GOC[p.ma] / tong_trong_so, 4) if p in ap_dung else 0.0

    ket_luan = sum(p.gia_tri * p.trong_so for p in ap_dung)
    cac_gia_tri = [p.gia_tri for p in ap_dung]

    kq.thuc_hien_duoc = True
    kq.phuong_phap = danh_sach
    kq.dcf_chi_tiet = dcf_chi_tiet
    kq.gia_tri_ket_luan = round(ket_luan)
    kq.gia_tri_ket_luan_hien_thi = dinh_dang_tien(ket_luan)
    kq.gia_tri_bang_chu = doc_thanh_chu(ket_luan)
    kq.khoang_thap = dinh_dang_tien(min(min(cac_gia_tri), ket_luan * 0.85))
    kq.khoang_cao = dinh_dang_tien(max(max(cac_gia_tri), ket_luan * 1.15))
    kq.gia_dinh = [
        ValuationAssumption(ten="Kỳ số liệu cơ sở", gia_tri=sl.nhan_ky[1],
                            can_cu="Cột 'Năm hiện tại' trong bảng tình hình tài chính"),
        ValuationAssumption(ten="Chi phí vốn chủ sở hữu (Re)", gia_tri=dinh_dang_phan_tram(re_),
                            can_cu=f"Lãi suất phi rủi ro {dinh_dang_phan_tram(LAI_SUAT_PHI_RUI_RO)} + "
                                   f"beta {dinh_dang(HE_SO_BETA, 2)} × phần bù thị trường "
                                   f"{dinh_dang_phan_tram(PHAN_BU_RUI_RO_VCP)} + phần bù quy mô "
                                   f"{dinh_dang_phan_tram(PHAN_BU_QUY_MO)}"),
        ValuationAssumption(ten="Chi phí nợ sau thuế (Rd)", gia_tri=dinh_dang_phan_tram(rd),
                            can_cu=f"Lãi suất vay {dinh_dang_phan_tram(lai_suat)} × "
                                   f"(1 − thuế {int(THUE_TNDN * 100)}%)"),
        ValuationAssumption(ten="Tỷ suất chiết khấu bình quân (WACC)", gia_tri=dinh_dang_phan_tram(wacc),
                            can_cu="Bình quân gia quyền theo cơ cấu vốn sau khi tính cả khoản vay đề nghị"),
        ValuationAssumption(ten="Tăng trưởng giai đoạn dự báo", gia_tri=dinh_dang_phan_tram(g), can_cu=can_cu_g),
        ValuationAssumption(ten="Tăng trưởng vĩnh viễn",
                            gia_tri=dinh_dang_phan_tram(TANG_TRUONG_VINH_VIEN),
                            can_cu="Xấp xỉ tốc độ tăng trưởng dài hạn của nền kinh tế"),
        ValuationAssumption(ten="Hệ số P/E và EV/EBITDA tham chiếu",
                            gia_tri=f"{dinh_dang(PE_THAM_CHIEU, 1)} lần / {dinh_dang(EV_EBITDA_THAM_CHIEU, 1)} lần",
                            can_cu="Mặt bằng doanh nghiệp cùng quy mô chưa niêm yết, đã chiết khấu thanh khoản"),
        ValuationAssumption(ten="Trọng số các phương pháp",
                            gia_tri=" · ".join(
                                f"{p.ma} {dinh_dang_phan_tram(p.trong_so * 100, 0)}" for p in danh_sach
                            ),
                            can_cu="Trọng số gốc 30/45/25, phân bổ lại cho các phương pháp đủ dữ liệu"),
    ]

    nhan_xet: list[str] = []
    if nav.ap_dung_duoc and dcf.ap_dung_duoc and nav.gia_tri > 0:
        ty_le = dcf.gia_tri / nav.gia_tri
        if ty_le >= 1.3:
            nhan_xet.append(
                f"Giá trị theo dòng tiền cao hơn giá trị sổ sách {dinh_dang(ty_le, 2)} lần, "
                "cho thấy doanh nghiệp đang khai thác tài sản hiệu quả."
            )
        elif ty_le <= 0.8:
            nhan_xet.append(
                "Giá trị theo dòng tiền thấp hơn giá trị sổ sách — hiệu quả sinh lời trên tài sản "
                "còn thấp, cần rà soát lại chất lượng tài sản và khoản phải thu."
            )
    von_vay = doc_tien(d.de_nghi_vay.so_tien)
    if von_vay and ket_luan > 0:
        ty_le_vay = von_vay / ket_luan * 100
        nhan_xet.append(
            f"Khoản vay đề nghị {rut_gon_tien(von_vay)} tương đương "
            f"{dinh_dang_phan_tram(ty_le_vay)} giá trị doanh nghiệp sau thẩm định."
        )
        if ty_le_vay > 100:
            kq.canh_bao.append(
                "Số tiền đề nghị vay vượt giá trị doanh nghiệp sau thẩm định — cần tăng tài sản "
                "bảo đảm hoặc giảm quy mô khoản vay."
            )
    nhan_xet.append(
        "Kết quả là giá trị tham chiếu phục vụ thẩm định tín dụng, không thay thế chứng thư "
        "thẩm định giá của tổ chức có chức năng thẩm định giá độc lập."
    )
    kq.nhan_xet = nhan_xet

    for p in danh_sach:
        if not p.ap_dung_duoc and p.ly_do_khong_ap_dung:
            kq.canh_bao.append(f"{p.ten}: {p.ly_do_khong_ap_dung}")
    return kq


# ------------------------------------------------ lịch trả nợ & dòng tiền


def _kieu_tra_no(text: str) -> str:
    phang = bo_dau(text)
    if "nien kim" in phang or "co dinh hang thang" in phang or "goc va lai co dinh" in phang:
        return "nien_kim"
    if "goc cuoi ky" in phang or "cuoi ky" in phang:
        return "goc_cuoi_ky"
    return "goc_deu"


@dataclass
class KyTraNo:
    nam: int
    tra_goc: float
    tra_lai: float
    du_no_cuoi: float


def lich_tra_no(von_vay: float, so_thang: int, lai_suat_nam: float, kieu: str) -> list[KyTraNo]:
    """Chia lịch trả nợ theo tháng rồi gộp về từng năm."""
    if von_vay <= 0 or so_thang <= 0:
        return []
    so_thang = min(so_thang, 360)
    r = lai_suat_nam / 100 / 12
    du_no = von_vay

    if kieu == "nien_kim" and r > 0:
        ky_khoan = von_vay * r / (1 - (1 + r) ** (-so_thang))
    else:
        ky_khoan = 0.0

    theo_nam: dict[int, list[float]] = {}
    for thang in range(1, so_thang + 1):
        lai = du_no * r
        if kieu == "nien_kim" and ky_khoan:
            goc = min(ky_khoan - lai, du_no)
        elif kieu == "goc_cuoi_ky":
            goc = du_no if thang == so_thang else 0.0
        else:
            goc = min(von_vay / so_thang, du_no)
        goc = max(goc, 0.0)
        du_no = max(du_no - goc, 0.0)

        nam = (thang - 1) // 12 + 1
        cong = theo_nam.setdefault(nam, [0.0, 0.0, 0.0])
        cong[0] += goc
        cong[1] += lai
        cong[2] = du_no

    return [KyTraNo(nam=n, tra_goc=v[0], tra_lai=v[1], du_no_cuoi=v[2]) for n, v in sorted(theo_nam.items())]


KY_HAN_CON_LAI_NO_CU = 5   # năm — giả định kỳ hạn bình quân còn lại của dư nợ hiện hữu


def nghia_vu_no_hien_huu(sl: SoLieu) -> float:
    """Ước nghĩa vụ trả nợ hằng năm của các khoản vay khách hàng đang có.

    Không trừ phần này thì DSCR bị thổi phồng, vì dòng tiền của cả doanh nghiệp
    được đem so với riêng nghĩa vụ của khoản vay mới.
    """
    lai_vay = sl.lay("chi_phi_lai_vay") or 0.0
    no_vay = sl.lay("no_vay")
    goc = (no_vay / KY_HAN_CON_LAI_NO_CU) if no_vay else 0.0
    return lai_vay + goc


def lap_dong_tien(d: Dossier, sl: SoLieu) -> tuple[list[CashflowRow], float | None, list[KyTraNo]]:
    """Dựng bảng dòng tiền dự kiến và DSCR bình quân."""
    von_vay = doc_tien(d.de_nghi_vay.so_tien)
    so_thang = doc_thang(d.de_nghi_vay.thoi_han)
    lai_suat = doc_phan_tram(d.de_nghi_vay.lai_suat_du_kien) or LAI_SUAT_VAY_MAC_DINH
    if not von_vay or not so_thang:
        return [], None, []

    lich = lich_tra_no(von_vay, so_thang, lai_suat, _kieu_tra_no(d.de_nghi_vay.phuong_thuc_tra_no))
    if not lich:
        return [], None, []

    # Dòng tiền thuần từ hoạt động: lợi nhuận sau thuế cộng khấu hao, tăng dần theo g,
    # sau khi đã dành phần trả nợ cho các khoản vay hiện hữu.
    lnst = sl.lay("loi_nhuan_sau_thue")
    khau_hao = sl.lay("khau_hao") or 0.0
    thu_nhap = sl.lay("thu_nhap")
    goc_dong_tien = None
    if lnst is not None:
        goc_dong_tien = max(lnst + khau_hao - nghia_vu_no_hien_huu(sl), 0.0)
    elif thu_nhap is not None:
        chi_phi = sl.lay("chi_phi_sinh_hoat") or 0.0
        goc_dong_tien = max(thu_nhap - chi_phi, 0.0)

    dt_truoc, dt_nay = sl.day("doanh_thu")[0], sl.lay("doanh_thu")
    if dt_truoc and dt_nay and dt_truoc > 0:
        g = max(0.0, min((dt_nay / dt_truoc - 1), 0.12))
    else:
        g = 0.05

    rows: list[CashflowRow] = []
    cac_dscr: list[float] = []
    for ky in lich:
        nghia_vu = ky.tra_goc + ky.tra_lai
        vao = None if goc_dong_tien is None else goc_dong_tien * ((1 + g) ** (ky.nam - 1))
        dscr = None
        if vao is not None and nghia_vu > 0:
            dscr = vao / nghia_vu
            cac_dscr.append(dscr)
        rows.append(
            CashflowRow(
                ky=f"Năm {ky.nam}",
                dong_tien_vao=dinh_dang_tien(vao) if vao is not None else "",
                dong_tien_ra=dinh_dang_tien(nghia_vu),
                tra_goc=dinh_dang_tien(ky.tra_goc),
                tra_lai=dinh_dang_tien(ky.tra_lai),
                du_cuoi_ky=dinh_dang_tien(vao - nghia_vu) if vao is not None else "",
                du_no_cuoi_ky=dinh_dang_tien(ky.du_no_cuoi),
                dscr=dinh_dang_lan(dscr) if dscr is not None else "",
            )
        )

    dscr_bq = sum(cac_dscr) / len(cac_dscr) if cac_dscr else None
    return rows, dscr_bq, lich


# --------------------------------------------------------------- biểu đồ


def _co_so_lieu(chuoi: list[float]) -> bool:
    return any(abs(x) > 1e-9 for x in chuoi)


def dung_bieu_do(d: Dossier, sl: SoLieu, dinh_gia: Valuation, lich: list[KyTraNo]) -> list[ChartSpec]:
    bd: list[ChartSpec] = []
    TY = 1e9

    # 1. Kết quả kinh doanh qua các kỳ
    dt = [x or 0.0 for x in sl.day("doanh_thu")]
    ln = [x or 0.0 for x in sl.day("loi_nhuan_sau_thue")]
    if _co_so_lieu(dt) or _co_so_lieu(ln):
        co_cot = [i for i in range(3) if (dt[i] or ln[i])]
        bd.append(
            ChartSpec(
                ma="kqkd", loai="cot", tieu_de="Doanh thu và lợi nhuận sau thuế",
                mo_ta="Quy mô hoạt động và hiệu quả sinh lời qua các kỳ báo cáo.",
                don_vi="tỷ VND", he_so=TY,
                nhan=[sl.nhan_ky[i] for i in co_cot],
                chuoi=[
                    ChartSeries(ten="Doanh thu", mau=MAU["chinh"],
                                gia_tri=[round(dt[i] / TY, 3) for i in co_cot]),
                    ChartSeries(ten="Lợi nhuận sau thuế", mau=MAU["phu"],
                                gia_tri=[round(ln[i] / TY, 3) for i in co_cot]),
                ],
            )
        )

    # 2. So sánh các phương pháp định giá
    if dinh_gia.thuc_hien_duoc:
        ap_dung = [p for p in dinh_gia.phuong_phap if p.ap_dung_duoc and p.gia_tri > 0]
        if ap_dung:
            nhan = [p.ten.split("(")[0].strip() for p in ap_dung] + ["Kết luận (bình quân gia quyền)"]
            gia_tri = [round(p.gia_tri / TY, 3) for p in ap_dung] + [
                round(dinh_gia.gia_tri_ket_luan / TY, 3)
            ]
            bd.append(
                ChartSpec(
                    ma="dinh_gia", loai="cot_ngang",
                    tieu_de="Giá trị doanh nghiệp theo từng phương pháp",
                    mo_ta="Ba cách tiếp cận độc lập và kết quả bình quân gia quyền dùng làm kết luận.",
                    don_vi="tỷ VND", he_so=TY, nhan=nhan,
                    chuoi=[ChartSeries(ten="Giá trị doanh nghiệp", mau=MAU["chinh"], gia_tri=gia_tri)],
                    ghi_chu="Cột cuối là giá trị kết luận sau khi gán trọng số cho từng phương pháp.",
                )
            )

    # 3. Nghĩa vụ trả nợ so với dòng tiền tạo ra
    if lich:
        nhan = [f"Năm {k.nam}" for k in lich]
        nghia_vu = [round((k.tra_goc + k.tra_lai) / TY, 3) for k in lich]
        chuoi = [ChartSeries(ten="Nghĩa vụ trả nợ (gốc + lãi)", mau=MAU["phu"], gia_tri=nghia_vu)]

        dong_vao: list[float] = []
        for row in d.dong_tien_du_kien[: len(lich)]:
            v = doc_tien(row.dong_tien_vao)
            dong_vao.append(round((v or 0.0) / TY, 3))
        if len(dong_vao) == len(lich) and _co_so_lieu(dong_vao):
            chuoi.insert(0, ChartSeries(ten="Dòng tiền thuần từ hoạt động", mau=MAU["chinh"], gia_tri=dong_vao))

        bd.append(
            ChartSpec(
                ma="tra_no", loai="cot",
                tieu_de="Khả năng trả nợ theo từng năm",
                mo_ta="So sánh dòng tiền doanh nghiệp tạo ra với nghĩa vụ trả gốc và lãi trong năm.",
                don_vi="tỷ VND", he_so=TY, nhan=nhan, chuoi=chuoi,
            )
        )

        # 4. Dư nợ giảm dần
        bd.append(
            ChartSpec(
                ma="du_no", loai="duong",
                tieu_de="Dư nợ vay còn lại cuối mỗi năm",
                mo_ta="Tiến độ giảm dư nợ theo lịch trả nợ đã thoả thuận.",
                don_vi="tỷ VND", he_so=TY, nhan=nhan,
                chuoi=[
                    ChartSeries(ten="Dư nợ cuối năm", mau=MAU["ba"], kieu="duong",
                                gia_tri=[round(k.du_no_cuoi / TY, 3) for k in lich])
                ],
            )
        )

        # 5. DSCR theo năm kèm ngưỡng an toàn
        dscr_theo_nam: list[float] = []
        for i, k in enumerate(lich):
            nghia = k.tra_goc + k.tra_lai
            v = doc_tien(d.dong_tien_du_kien[i].dong_tien_vao) if i < len(d.dong_tien_du_kien) else None
            dscr_theo_nam.append(round(v / nghia, 3) if v and nghia > 0 else 0.0)
        if _co_so_lieu(dscr_theo_nam):
            bd.append(
                ChartSpec(
                    ma="dscr", loai="duong",
                    tieu_de="Hệ số bảo đảm trả nợ (DSCR) theo năm",
                    mo_ta="DSCR dưới 1,2 lần là mức cần theo dõi chặt; dưới 1,0 lần là dòng tiền "
                          "không đủ trả nợ trong năm đó.",
                    don_vi="lần", he_so=1.0, nhan=nhan,
                    chuoi=[
                        ChartSeries(ten="DSCR", mau=MAU["chinh"], kieu="duong", gia_tri=dscr_theo_nam),
                        ChartSeries(ten="Ngưỡng an toàn 1,2 lần", mau=MAU["nguong"], kieu="nguong",
                                    gia_tri=[1.2] * len(nhan)),
                    ],
                )
            )

    # 6. Cơ cấu nguồn vốn của phương án
    von_vay = doc_tien(d.de_nghi_vay.so_tien)
    von_tu_co = doc_tien(d.de_nghi_vay.von_tu_co)
    if von_vay and von_tu_co:
        bd.append(
            ChartSpec(
                ma="nguon_von", loai="tron",
                tieu_de="Cơ cấu nguồn vốn của phương án",
                mo_ta="Tỷ trọng vốn tự có khách hàng tham gia so với vốn đề nghị ngân hàng tài trợ.",
                don_vi="tỷ VND", he_so=TY,
                nhan=["Vốn tự có", "Vốn vay ngân hàng"],
                chuoi=[
                    ChartSeries(
                        ten="Nguồn vốn", mau=MAU["chinh"],
                        gia_tri=[round(von_tu_co / TY, 3), round(von_vay / TY, 3)],
                    )
                ],
            )
        )

    # 7. Tài sản bảo đảm
    ts = [(t.ten_tai_san or "Tài sản", doc_tien(t.gia_tri_uoc_tinh)) for t in d.tai_san_bao_dam]
    ts = [(ten, v) for ten, v in ts if v]
    if ts:
        bd.append(
            ChartSpec(
                ma="tsbd", loai="cot_ngang",
                tieu_de="Giá trị tài sản bảo đảm",
                mo_ta="Giá trị ước tính từng tài sản; tổng giá trị so với dư nợ quyết định hệ số LTV.",
                don_vi="tỷ VND", he_so=TY,
                nhan=[ten for ten, _ in ts],
                chuoi=[ChartSeries(ten="Giá trị ước tính", mau=MAU["ba"],
                                   gia_tri=[round(v / TY, 3) for _, v in ts])],
                ghi_chu=(
                    f"Tổng giá trị {rut_gon_tien(sum(v for _, v in ts))}"
                    + (f" · Dư nợ đề nghị {rut_gon_tien(von_vay)}" if von_vay else "")
                ),
            )
        )

    return bd


# ------------------------------------------------------ chấm điểm tín dụng


def _diem_theo_moc(gia_tri: float | None, moc: list[tuple[float, float]], mac_dinh: float) -> float:
    """moc là danh sách (ngưỡng, điểm) sắp giảm dần theo ngưỡng."""
    if gia_tri is None:
        return mac_dinh
    for nguong, diem in moc:
        if gia_tri >= nguong:
            return diem
    return 0.0


def cham_diem(
    d: Dossier,
    chi_so: list[FinancialRatio],
    dinh_gia: Valuation,
    diem_ho_so: int,
) -> AppraisalConclusion:
    tra = {c.ma: c.so for c in chi_so}
    thanh_phan: list[FinancialRatio] = []

    def ghi(ten: str, diem: float, toi_da: float, dien_giai: str) -> None:
        thanh_phan.append(
            FinancialRatio(
                ma=ten, ten=ten, so=round(diem, 1),
                gia_tri=f"{dinh_dang(diem, 1)}/{dinh_dang(toi_da, 0)}",
                don_vi="điểm", nguong=f"tối đa {dinh_dang(toi_da, 0)} điểm",
                danh_gia=_danh_gia(diem / toi_da * 100 if toi_da else 0, 75, 50),
                y_nghia=dien_giai,
            )
        )

    # 1. Khả năng trả nợ — trọng số lớn nhất
    d_dscr = _diem_theo_moc(tra.get("dscr"), [(2.0, 30), (1.5, 26), (1.2, 21), (1.0, 13), (0.0, 6)], 12)
    ghi("Khả năng trả nợ (DSCR)", d_dscr, 30,
        "Dòng tiền tạo ra so với nghĩa vụ trả gốc và lãi hằng năm.")

    # 2. Hiệu quả sinh lời
    d_roe = _diem_theo_moc(tra.get("roe"), [(20, 15), (15, 12), (10, 9), (5, 5), (0, 2)], 6)
    d_bien = _diem_theo_moc(tra.get("bien_lnst"), [(12, 10), (8, 8), (5, 6), (2, 3), (0, 1)], 4)
    ghi("Hiệu quả sinh lời", d_roe + d_bien, 25, "ROE và biên lợi nhuận sau thuế.")

    # 3. Cơ cấu vốn và thanh khoản
    de = tra.get("no_vcsh")
    d_de = 8.0 if de is None else (8 if de <= 1.5 else 6 if de <= 2.5 else 3 if de <= 4 else 1)
    d_tt = _diem_theo_moc(tra.get("thanh_toan_hh"), [(1.5, 7), (1.2, 6), (1.0, 4), (0, 2)], 4)
    ghi("Cơ cấu vốn và thanh khoản", d_de + d_tt, 15, "Hệ số nợ trên vốn chủ và hệ số thanh toán hiện hành.")

    # 4. Tài sản bảo đảm
    ltv = tra.get("ltv")
    if ltv is None:
        d_ltv = 6.0
    else:
        d_ltv = 20 if ltv <= 50 else 17 if ltv <= 70 else 12 if ltv <= 90 else 6
    ghi("Bảo đảm tiền vay", d_ltv, 20, "Mức che phủ của tài sản bảo đảm đối với dư nợ (LTV).")

    # 5. Mức độ đầy đủ hồ sơ
    d_hs = max(0.0, min(10.0, diem_ho_so / 10.0))
    ghi("Mức độ đầy đủ hồ sơ", d_hs, 10, "Tỷ lệ thông tin và giấy tờ bắt buộc đã được cung cấp.")

    tong = sum(t.so or 0 for t in thanh_phan)
    diem = int(round(max(0.0, min(tong, 100.0))))

    if diem >= 92:
        xep_hang, muc = "AAA", "Thấp"
    elif diem >= 84:
        xep_hang, muc = "AA", "Thấp"
    elif diem >= 74:
        xep_hang, muc = "A", "Thấp"
    elif diem >= 64:
        xep_hang, muc = "BBB", "Trung bình"
    elif diem >= 54:
        xep_hang, muc = "BB", "Trung bình"
    elif diem >= 44:
        xep_hang, muc = "B", "Cao"
    else:
        xep_hang, muc = "CCC", "Cao"

    if diem >= 74:
        de_xuat = "Đủ điều kiện xem xét cấp tín dụng theo đề nghị"
    elif diem >= 54:
        de_xuat = "Có thể xem xét cấp tín dụng kèm điều kiện bổ sung"
    else:
        de_xuat = "Chưa đủ cơ sở đề xuất cấp tín dụng — cần bổ sung hồ sơ và cơ cấu lại phương án"

    manh: list[str] = []
    yeu: list[str] = []
    for c in chi_so:
        if c.so is None:
            continue
        if c.danh_gia == "Tốt":
            manh.append(f"{c.ten}: {c.gia_tri} (ngưỡng tham chiếu {c.nguong})")
        elif c.danh_gia == "Cần lưu ý":
            yeu.append(f"{c.ten}: {c.gia_tri} — chưa đạt ngưỡng {c.nguong}")

    dieu_kien: list[str] = []
    if (tra.get("ltv") or 0) > 70:
        dieu_kien.append("Bổ sung tài sản bảo đảm để đưa hệ số LTV về mức không quá 70%.")
    if (tra.get("dscr") or 99) < 1.2:
        dieu_kien.append("Kéo dài thời hạn vay hoặc giảm quy mô khoản vay để DSCR đạt tối thiểu 1,2 lần.")
    if (tra.get("von_tu_co") or 99) < 20:
        dieu_kien.append("Nâng tỷ lệ vốn tự có tham gia phương án lên tối thiểu 20%.")
    if (tra.get("no_vcsh") or 0) > 2.5:
        dieu_kien.append("Giảm hệ số nợ trên vốn chủ sở hữu xuống dưới 2,5 lần trước khi giải ngân.")
    dieu_kien.append("Giải ngân chuyển khoản trực tiếp cho bên thụ hưởng theo đúng mục đích vay vốn.")
    dieu_kien.append("Kiểm tra sử dụng vốn vay định kỳ và sau mỗi lần giải ngân.")

    han_muc = ""
    von_vay = doc_tien(d.de_nghi_vay.so_tien)
    if von_vay:
        if diem >= 68:
            han_muc = dinh_dang_tien(von_vay)
        elif diem >= 50:
            han_muc = f"{dinh_dang_tien(von_vay * 0.8)} (bằng 80% mức đề nghị)"
        else:
            han_muc = "Chưa xác định — phụ thuộc hồ sơ bổ sung"

    return AppraisalConclusion(
        diem=diem, xep_hang=xep_hang, muc_rui_ro=muc, de_xuat=de_xuat,
        han_muc_de_xuat=han_muc,
        cac_diem_manh=manh[:6], cac_diem_yeu=yeu[:6],
        dieu_kien_kem_theo=dieu_kien[:6], thanh_phan_diem=thanh_phan,
    )


# --------------------------------------------------------------- đầu vào


@dataclass
class KetQuaThamDinh:
    so_lieu: SoLieu
    chi_so: list[FinancialRatio]
    dinh_gia: Valuation
    dong_tien: list[CashflowRow]
    bieu_do: list[ChartSpec]
    ket_luan: AppraisalConclusion
    dscr_bq: float | None = None


def tham_dinh(d: Dossier, diem_ho_so: int = 100, tinh_dinh_gia: bool = True) -> KetQuaThamDinh:
    """Chạy trọn khối thẩm định trên một hồ sơ và trả về mọi thành phần đã tính."""
    sl = boc_so_lieu(d)
    dong_tien, dscr_bq, lich = lap_dong_tien(d, sl)

    # Nếu người dùng đã tự nhập bảng dòng tiền thì tôn trọng số liệu của họ
    if d.dong_tien_du_kien and any(r.dong_tien_vao for r in d.dong_tien_du_kien):
        dong_tien_dung = d.dong_tien_du_kien
    else:
        dong_tien_dung = dong_tien or d.dong_tien_du_kien
    d_tam = d.model_copy(update={"dong_tien_du_kien": dong_tien_dung})

    if not dscr_bq:
        cac = [doc_so(r.dscr) for r in dong_tien_dung if r.dscr]
        cac = [x for x in cac if x]
        dscr_bq = sum(cac) / len(cac) if cac else None

    chi_so = tinh_chi_so(d_tam, sl, dscr_bq)
    dinh_gia = tham_dinh_gia_tri(d_tam, sl) if tinh_dinh_gia else Valuation(
        thuc_hien_duoc=False, ly_do="Người dùng chọn bỏ qua bước thẩm định giá trị doanh nghiệp."
    )
    bieu_do = dung_bieu_do(d_tam, sl, dinh_gia, lich)
    ket_luan = cham_diem(d_tam, chi_so, dinh_gia, diem_ho_so)

    return KetQuaThamDinh(
        so_lieu=sl, chi_so=chi_so, dinh_gia=dinh_gia, dong_tien=dong_tien_dung,
        bieu_do=bieu_do, ket_luan=ket_luan, dscr_bq=dscr_bq,
    )
