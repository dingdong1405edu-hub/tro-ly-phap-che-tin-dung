"""Vẽ biểu đồ ChartSpec thành hình vector cho ReportLab.

Cùng một `ChartSpec` được web vẽ bằng SVG và PDF vẽ bằng module này, nên hai bên
luôn hiển thị y hệt nhau: cùng số liệu, cùng màu, cùng nhãn.

Quy ước trình bày (theo chuẩn trực quan hoá dữ liệu của dự án):
  * Nét mảnh, lưới mờ, không dùng hiệu ứng 3D hay đổ bóng.
  * Mọi cột và điểm đều có nhãn giá trị — bảng màu có độ tương phản dưới 3:1
    trên nền trắng nên nhãn hiển thị là bắt buộc, không phải tuỳ chọn.
  * Từ 2 chuỗi trở lên luôn có chú giải; một chuỗi thì tiêu đề đã nói rõ.
"""

from __future__ import annotations

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String, Wedge
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth

from ..schemas import ChartSpec
from ..services.numbers import dinh_dang

MUC = colors.HexColor("#5A6A7D")
LUOI = colors.HexColor("#E4E9F0")
TRUC = colors.HexColor("#C3C2B7")
CHU = colors.HexColor("#1B2430")

PHAN_TRAM_TRONG = 0.55   # tỷ lệ chiều rộng nhóm cột thực sự được tô


def _nhan_gia_tri(x: float, don_vi: str) -> str:
    if abs(x) >= 100:
        return dinh_dang(x, 0)
    if abs(x) >= 10:
        return dinh_dang(x, 1)
    return dinh_dang(x, 2)


def _cat(text: str, toi_da: int) -> str:
    text = str(text or "")
    return text if len(text) <= toi_da else text[: toi_da - 1] + "…"


def _thang_do(cao_nhat: float) -> tuple[float, list[float]]:
    """Chọn trần trục và mốc chia sao cho số đọc dễ mà không phí chỗ trống."""
    if cao_nhat <= 0:
        return 1.0, [0.0, 0.5, 1.0]
    import math

    bac = 10 ** math.floor(math.log10(cao_nhat))
    tran = 10 * bac
    for buoc in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if buoc * bac >= cao_nhat:
            tran = buoc * bac
            break
    so_moc = 4
    return tran, [tran * i / so_moc for i in range(so_moc + 1)]


class _Khung:
    """Vùng vẽ có trục — dùng chung cho biểu đồ cột và biểu đồ đường."""

    def __init__(self, d: Drawing, trai: float, duoi: float, rong: float, cao: float) -> None:
        self.d = d
        self.x0 = trai
        self.y0 = duoi
        self.w = rong
        self.h = cao

    def luoi(self, moc: list[float], tran: float, don_vi: str) -> None:
        for m in moc:
            y = self.y0 + (m / tran) * self.h if tran else self.y0
            self.d.add(Line(self.x0, y, self.x0 + self.w, y,
                            strokeColor=LUOI if m else TRUC, strokeWidth=0.6))
            self.d.add(String(self.x0 - 4, y - 2.6, _nhan_gia_tri(m, don_vi),
                              fontSize=6.2, fillColor=MUC, textAnchor="end"))

    def y(self, gia_tri: float, tran: float) -> float:
        return self.y0 + (gia_tri / tran) * self.h if tran else self.y0


def _chu_giai(d: Drawing, spec: ChartSpec, x: float, y: float, font: str) -> None:
    if len(spec.chuoi) < 2:
        return
    cx = x
    for s in spec.chuoi:
        mau = colors.HexColor(s.mau or "#2a78d6")
        if s.kieu == "nguong":
            d.add(Line(cx, y + 3, cx + 10, y + 3, strokeColor=mau, strokeWidth=1.4,
                       strokeDashArray=[3, 2]))
        else:
            d.add(Rect(cx, y, 8, 8, fillColor=mau, strokeColor=None, rx=2, ry=2))
        nhan = _cat(s.ten, 42)
        d.add(String(cx + 13, y + 1.5, nhan, fontSize=6.6, fillColor=CHU, fontName=font))
        cx += 13 + stringWidth(nhan, font, 6.6) + 16


# --------------------------------------------------------------- các loại


def _ve_cot(spec: ChartSpec, w: float, h: float, font: str, font_dam: str) -> Drawing:
    d = Drawing(w, h)
    co_chu_giai = len(spec.chuoi) >= 2
    trai, phai = 34.0, 8.0
    duoi = 30.0 + (12 if co_chu_giai else 0)
    tren = 22.0   # chừa chỗ cho nhãn giá trị của mốc cao nhất
    k = _Khung(d, trai, duoi, w - trai - phai, h - duoi - tren)

    tat_ca = [v for s in spec.chuoi for v in s.gia_tri]
    tran, moc = _thang_do(max(tat_ca + [0]))
    k.luoi(moc, tran, spec.don_vi)

    n_nhom = max(len(spec.nhan), 1)
    rong_nhom = k.w / n_nhom
    n_chuoi = max(len(spec.chuoi), 1)
    rong_cot = rong_nhom * PHAN_TRAM_TRONG / n_chuoi

    for i, nhan in enumerate(spec.nhan):
        giua = k.x0 + rong_nhom * (i + 0.5)
        bat_dau = giua - rong_cot * n_chuoi / 2
        for j, s in enumerate(spec.chuoi):
            if i >= len(s.gia_tri):
                continue
            gia_tri = s.gia_tri[i]
            chieu_cao = max(k.y(gia_tri, tran) - k.y0, 0.6)
            x = bat_dau + j * rong_cot
            # Chừa 2px giữa các cột cạnh nhau cho mắt tách được khối màu
            d.add(Rect(x + 1, k.y0, max(rong_cot - 2, 1.5), chieu_cao,
                       fillColor=colors.HexColor(s.mau or "#2a78d6"), strokeColor=None, rx=2, ry=2))
            d.add(String(x + rong_cot / 2, k.y0 + chieu_cao + 2.5, _nhan_gia_tri(gia_tri, spec.don_vi),
                         fontSize=5.9, fillColor=CHU, textAnchor="middle", fontName=font))
        d.add(String(giua, k.y0 - 9, _cat(nhan, 16), fontSize=6.3, fillColor=MUC,
                     textAnchor="middle", fontName=font))

    d.add(String(trai - 30, h - 9, f"Đơn vị: {spec.don_vi}", fontSize=6.2, fillColor=MUC, fontName=font))
    if co_chu_giai:
        _chu_giai(d, spec, trai, 8, font)
    return d


def _ve_cot_ngang(spec: ChartSpec, w: float, h: float, font: str, font_dam: str) -> Drawing:
    d = Drawing(w, h)
    nhan_w = min(max(w * 0.30, 90), 190)
    trai, phai, duoi, tren = nhan_w, 52.0, 16.0, 12.0
    vung_w = w - trai - phai
    vung_h = h - duoi - tren

    chuoi = spec.chuoi[0] if spec.chuoi else None
    if not chuoi or not spec.nhan:
        return d
    tran = max(chuoi.gia_tri + [0]) or 1.0

    n = len(spec.nhan)
    cao_dong = vung_h / n
    for i, nhan in enumerate(spec.nhan):
        gia_tri = chuoi.gia_tri[i] if i < len(chuoi.gia_tri) else 0.0
        y = duoi + vung_h - cao_dong * (i + 1)
        cao_cot = min(cao_dong * 0.58, 15)
        dai = max(vung_w * (gia_tri / tran), 0.6)
        # Dòng cuối của biểu đồ định giá là kết luận — tô đậm hơn để nổi bật
        la_ket_luan = spec.ma == "dinh_gia" and i == n - 1
        mau = colors.HexColor("#184f95" if la_ket_luan else (chuoi.mau or "#2a78d6"))
        d.add(Rect(trai, y + (cao_dong - cao_cot) / 2, dai, cao_cot,
                   fillColor=mau, strokeColor=None, rx=2, ry=2))
        d.add(String(trai - 6, y + cao_dong / 2 - 2.4, _cat(nhan, int(nhan_w / 3.4)),
                     fontSize=6.3, fillColor=CHU, textAnchor="end",
                     fontName=font_dam if la_ket_luan else font))
        d.add(String(trai + dai + 4, y + cao_dong / 2 - 2.4, _nhan_gia_tri(gia_tri, spec.don_vi),
                     fontSize=6.5, fillColor=CHU, fontName=font_dam if la_ket_luan else font))

    d.add(Line(trai, duoi, trai, duoi + vung_h, strokeColor=TRUC, strokeWidth=0.6))
    d.add(String(trai, h - 8, f"Đơn vị: {spec.don_vi}", fontSize=6.2, fillColor=MUC, fontName=font))
    return d


def _ve_duong(spec: ChartSpec, w: float, h: float, font: str, font_dam: str) -> Drawing:
    d = Drawing(w, h)
    co_chu_giai = len(spec.chuoi) >= 2
    trai, phai = 34.0, 12.0
    duoi = 30.0 + (12 if co_chu_giai else 0)
    tren = 22.0   # chừa chỗ cho nhãn giá trị của mốc cao nhất
    k = _Khung(d, trai, duoi, w - trai - phai, h - duoi - tren)

    tat_ca = [v for s in spec.chuoi for v in s.gia_tri]
    tran, moc = _thang_do(max(tat_ca + [0]))
    k.luoi(moc, tran, spec.don_vi)

    n = max(len(spec.nhan), 1)
    buoc = k.w / max(n - 1, 1) if n > 1 else k.w

    for i, nhan in enumerate(spec.nhan):
        x = k.x0 + (buoc * i if n > 1 else k.w / 2)
        d.add(String(x, k.y0 - 9, _cat(nhan, 14), fontSize=6.3, fillColor=MUC,
                     textAnchor="middle", fontName=font))

    for s in spec.chuoi:
        mau = colors.HexColor(s.mau or "#2a78d6")
        diem: list[float] = []
        for i, gia_tri in enumerate(s.gia_tri[:n]):
            x = k.x0 + (buoc * i if n > 1 else k.w / 2)
            diem.extend([x, k.y(gia_tri, tran)])
        if len(diem) < 4:
            continue
        if s.kieu == "nguong":
            d.add(PolyLine(diem, strokeColor=mau, strokeWidth=1.1, strokeDashArray=[3, 2]))
            continue
        d.add(PolyLine(diem, strokeColor=mau, strokeWidth=1.6))
        for i in range(0, len(diem), 2):
            x, y = diem[i], diem[i + 1]
            # Vòng trắng quanh điểm để nét không dính vào nhau khi hai chuỗi cắt qua
            d.add(Circle(x, y, 3.4, fillColor=colors.white, strokeColor=None))
            d.add(Circle(x, y, 2.4, fillColor=mau, strokeColor=None))
            d.add(String(x, y + 5.5, _nhan_gia_tri(s.gia_tri[i // 2], spec.don_vi),
                         fontSize=5.9, fillColor=CHU, textAnchor="middle", fontName=font))

    d.add(String(trai - 30, h - 9, f"Đơn vị: {spec.don_vi}", fontSize=6.2, fillColor=MUC, fontName=font))
    if co_chu_giai:
        _chu_giai(d, spec, trai, 8, font)
    return d


def _ve_tron(spec: ChartSpec, w: float, h: float, font: str, font_dam: str) -> Drawing:
    d = Drawing(w, h)
    chuoi = spec.chuoi[0] if spec.chuoi else None
    if not chuoi or not spec.nhan:
        return d
    tong = sum(chuoi.gia_tri) or 1.0

    ban_kinh = min(h * 0.36, 58)
    cx, cy = ban_kinh + 24, h / 2
    trong = ban_kinh * 0.55

    bang_mau = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
    goc = 90.0
    for i, nhan in enumerate(spec.nhan):
        gia_tri = chuoi.gia_tri[i] if i < len(chuoi.gia_tri) else 0.0
        cung = gia_tri / tong * 360
        mau = colors.HexColor(bang_mau[i % len(bang_mau)])
        # Vành trắng giữa các miếng để ranh giới luôn đọc được
        d.add(Wedge(cx, cy, ban_kinh, goc - cung, goc,
                    fillColor=mau, strokeColor=colors.white, strokeWidth=1.6))
        goc -= cung
    # Khoét lỗ giữa thành hình vành khuyên — dễ so sánh tỷ trọng hơn hình tròn đặc
    d.add(Circle(cx, cy, trong, fillColor=colors.white, strokeColor=None))

    # Chú giải dạng danh sách, có cả giá trị và tỷ trọng nên không phụ thuộc màu
    lx = cx + ban_kinh + 22
    ly = cy + (len(spec.nhan) - 1) * 8
    for i, nhan in enumerate(spec.nhan):
        gia_tri = chuoi.gia_tri[i] if i < len(chuoi.gia_tri) else 0.0
        mau = colors.HexColor(bang_mau[i % len(bang_mau)])
        d.add(Rect(lx, ly - 1, 8, 8, fillColor=mau, strokeColor=None, rx=2, ry=2))
        d.add(String(lx + 13, ly + 1, _cat(nhan, 30), fontSize=6.8, fillColor=CHU, fontName=font_dam))
        d.add(String(lx + 13, ly - 7.5,
                     f"{_nhan_gia_tri(gia_tri, spec.don_vi)} {spec.don_vi} · "
                     f"{dinh_dang(gia_tri / tong * 100, 1)}%",
                     fontSize=6.3, fillColor=MUC, fontName=font))
        ly -= 20
    return d


_BO_VE = {
    "cot": _ve_cot,
    "cot_ngang": _ve_cot_ngang,
    "duong": _ve_duong,
    "tron": _ve_tron,
}


def chieu_cao_goi_y(spec: ChartSpec) -> float:
    if spec.loai == "cot_ngang":
        return max(72.0, 26.0 * len(spec.nhan) + 34)
    if spec.loai == "tron":
        return max(110.0, 26.0 * len(spec.nhan) + 60)
    return 158.0


def ve(spec: ChartSpec, rong: float, cao: float | None, font: str, font_dam: str) -> Drawing | None:
    """Dựng Drawing cho một ChartSpec; trả về None nếu không có số liệu."""
    if not spec.chuoi or not spec.nhan:
        return None
    if not any(s.gia_tri for s in spec.chuoi):
        return None
    ham = _BO_VE.get(spec.loai)
    if not ham:
        return None
    try:
        return ham(spec, rong, cao or chieu_cao_goi_y(spec), font, font_dam)
    except Exception:  # biểu đồ hỏng không được làm sập cả file PDF
        return None
