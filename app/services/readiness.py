"""Cổng kiểm tra đầu vào — quyết định pipeline có được phép sinh hồ sơ hay không.

Nguyên tắc: hồ sơ tín dụng chỉ có giá trị khi khách hàng đã cung cấp đủ thông tin
và giấy tờ. Nếu còn thiếu mục **bắt buộc**, pipeline dừng lại và trả về danh sách
việc cần bổ sung thay vì sinh ra một bản hồ sơ nửa vời.

Ba mức độ:
  * ``bat_buoc``   — thiếu là chặn, không sinh hồ sơ.
  * ``quan_trong`` — không chặn nhưng cảnh báo; khách phải bấm xác nhận mới chạy tiếp.
  * ``nen_co``     — chỉ nhắc để hồ sơ thuyết phục hơn.
"""

from __future__ import annotations

from typing import Any, Callable

from ..schemas import (
    Dossier,
    GroupStatus,
    MissingItem,
    ProvidedDoc,
    ReadinessReport,
)
from .numbers import bo_dau, doc_thang, doc_tien

# ------------------------------------------------------- danh mục giấy tờ

NHOM_PHAP_LY = "Hồ sơ pháp lý"
NHOM_KHOAN_VAY = "Hồ sơ khoản vay"
NHOM_TAI_CHINH = "Hồ sơ tài chính"
NHOM_TSBD = "Hồ sơ tài sản bảo đảm"

# Danh mục giấy tờ tối thiểu cho khách hàng là tổ chức
GIAY_TO_TO_CHUC: list[dict[str, Any]] = [
    {"ma": "dkkd", "nhom": NHOM_PHAP_LY, "ten": "Giấy chứng nhận đăng ký doanh nghiệp / đăng ký kinh doanh",
     "bat_buoc": True, "can_cu": "Hồ sơ chứng minh năng lực pháp luật dân sự của khách hàng"},
    {"ma": "dieu_le", "nhom": NHOM_PHAP_LY, "ten": "Điều lệ công ty (bản mới nhất)", "bat_buoc": True},
    {"ma": "qd_bo_nhiem", "nhom": NHOM_PHAP_LY,
     "ten": "Quyết định bổ nhiệm người đại diện theo pháp luật, kế toán trưởng", "bat_buoc": True},
    {"ma": "cccd_dai_dien", "nhom": NHOM_PHAP_LY,
     "ten": "CCCD/Hộ chiếu của người đại diện theo pháp luật", "bat_buoc": True},
    {"ma": "nghi_quyet_vay", "nhom": NHOM_PHAP_LY,
     "ten": "Nghị quyết/Quyết định của chủ sở hữu, HĐTV hoặc HĐQT về việc vay vốn và thế chấp tài sản",
     "bat_buoc": True, "can_cu": "Chứng minh thẩm quyền quyết định việc vay vốn"},
    {"ma": "giay_de_nghi", "nhom": NHOM_KHOAN_VAY, "ten": "Giấy đề nghị vay vốn theo mẫu của tổ chức tín dụng",
     "bat_buoc": True},
    {"ma": "phuong_an", "nhom": NHOM_KHOAN_VAY,
     "ten": "Phương án sử dụng vốn kèm kế hoạch trả nợ", "bat_buoc": True,
     "can_cu": "Điều kiện vay vốn về phương án khả thi và khả năng trả nợ"},
    {"ma": "hop_dong_dau_ra", "nhom": NHOM_KHOAN_VAY,
     "ten": "Hợp đồng đầu vào - đầu ra, đơn hàng chứng minh nhu cầu vốn", "bat_buoc": True},
    {"ma": "bctc", "nhom": NHOM_TAI_CHINH,
     "ten": "Báo cáo tài chính 02 năm gần nhất và kỳ gần nhất", "bat_buoc": True},
    {"ma": "to_khai_thue", "nhom": NHOM_TAI_CHINH, "ten": "Tờ khai thuế GTGT, quyết toán thuế TNDN",
     "bat_buoc": True},
    {"ma": "sao_ke", "nhom": NHOM_TAI_CHINH, "ten": "Sao kê tài khoản ngân hàng 06-12 tháng gần nhất",
     "bat_buoc": True},
    {"ma": "du_no_tctd", "nhom": NHOM_TAI_CHINH,
     "ten": "Bảng kê dư nợ tại các tổ chức tín dụng khác", "bat_buoc": False},
    {"ma": "giay_to_tsbd", "nhom": NHOM_TSBD,
     "ten": "Giấy tờ chứng minh quyền sở hữu / quyền sử dụng tài sản bảo đảm", "bat_buoc": True,
     "can_cu": "Yêu cầu về điều kiện của tài sản bảo đảm"},
    {"ma": "dinh_gia_tsbd", "nhom": NHOM_TSBD, "ten": "Chứng thư thẩm định giá hoặc biên bản định giá tài sản",
     "bat_buoc": False},
    {"ma": "bao_hiem_tsbd", "nhom": NHOM_TSBD, "ten": "Hợp đồng bảo hiểm tài sản bảo đảm (nếu bắt buộc mua)",
     "bat_buoc": False},
]

# Danh mục giấy tờ tối thiểu cho khách hàng cá nhân / hộ kinh doanh
GIAY_TO_CA_NHAN: list[dict[str, Any]] = [
    {"ma": "cccd", "nhom": NHOM_PHAP_LY, "ten": "CCCD/Hộ chiếu của người vay và vợ/chồng", "bat_buoc": True},
    {"ma": "ho_khau", "nhom": NHOM_PHAP_LY, "ten": "Giấy tờ xác nhận cư trú", "bat_buoc": True},
    {"ma": "hon_nhan", "nhom": NHOM_PHAP_LY,
     "ten": "Giấy đăng ký kết hôn hoặc giấy xác nhận tình trạng hôn nhân", "bat_buoc": True},
    {"ma": "dkkd_ho", "nhom": NHOM_PHAP_LY,
     "ten": "Giấy chứng nhận đăng ký hộ kinh doanh (nếu vay phục vụ kinh doanh)", "bat_buoc": False},
    {"ma": "giay_de_nghi", "nhom": NHOM_KHOAN_VAY, "ten": "Giấy đề nghị vay vốn theo mẫu", "bat_buoc": True},
    {"ma": "phuong_an", "nhom": NHOM_KHOAN_VAY, "ten": "Phương án sử dụng vốn và kế hoạch trả nợ",
     "bat_buoc": True},
    {"ma": "chung_minh_muc_dich", "nhom": NHOM_KHOAN_VAY,
     "ten": "Giấy tờ chứng minh mục đích sử dụng vốn (hợp đồng mua bán, báo giá, dự toán)", "bat_buoc": True},
    {"ma": "chung_minh_thu_nhap", "nhom": NHOM_TAI_CHINH,
     "ten": "Chứng minh thu nhập: hợp đồng lao động, bảng lương, sao kê lương hoặc sổ sách bán hàng",
     "bat_buoc": True},
    {"ma": "sao_ke_cn", "nhom": NHOM_TAI_CHINH, "ten": "Sao kê tài khoản 06 tháng gần nhất", "bat_buoc": True},
    {"ma": "giay_to_tsbd", "nhom": NHOM_TSBD,
     "ten": "Giấy chứng nhận quyền sử dụng đất / đăng ký xe / giấy tờ tài sản bảo đảm khác", "bat_buoc": True},
    {"ma": "dong_y_the_chap", "nhom": NHOM_TSBD,
     "ten": "Văn bản đồng ý thế chấp của đồng sở hữu tài sản", "bat_buoc": True},
]


def la_ca_nhan(loai_hinh: str) -> bool:
    phang = bo_dau(loai_hinh)
    return any(k in phang for k in ("ca nhan", "ho kinh doanh", "ho gia dinh"))


def danh_muc_giay_to(loai_hinh: str) -> list[ProvidedDoc]:
    """Danh sách giấy tờ khách hàng cần đánh dấu đã có, tuỳ theo loại hình."""
    nguon = GIAY_TO_CA_NHAN if la_ca_nhan(loai_hinh) else GIAY_TO_TO_CHUC
    return [ProvidedDoc(**mau, da_co=False) for mau in nguon]


def hop_nhat_giay_to(loai_hinh: str, hien_tai: list[ProvidedDoc] | None) -> list[ProvidedDoc]:
    """Dựng lại danh mục theo loại hình nhưng giữ nguyên các ô khách đã tích."""
    da_tich = {d.ma: d for d in (hien_tai or []) if d.ma}
    ket_qua = danh_muc_giay_to(loai_hinh)
    for doc in ket_qua:
        cu = da_tich.get(doc.ma)
        if cu:
            doc.da_co = cu.da_co
            doc.ghi_chu = cu.ghi_chu
    # Giữ lại các dòng khách tự thêm không nằm trong mẫu chuẩn
    ma_chuan = {d.ma for d in ket_qua}
    ket_qua.extend(d for d in (hien_tai or []) if d.ma and d.ma not in ma_chuan)
    return ket_qua


# --------------------------------------------------- quy tắc kiểm tra trường


def _co(gia_tri: Any, do_dai: int = 1) -> bool:
    if gia_tri is None:
        return False
    if isinstance(gia_tri, (list, dict)):
        return len(gia_tri) > 0
    return len(str(gia_tri).strip()) >= do_dai


def _lay(d: Dossier, duong_dan: str) -> Any:
    cur: Any = d
    for phan in duong_dan.split("."):
        cur = getattr(cur, phan, None) if not isinstance(cur, dict) else cur.get(phan)
        if cur is None:
            return None
    return cur


class QuyTac:
    def __init__(
        self,
        ma: str,
        nhom: str,
        ten: str,
        muc_do: str,
        vi_sao: str,
        goi_y: str,
        buoc: int = 1,
        kiem: Callable[[Dossier], bool] | None = None,
        do_dai: int = 1,
    ) -> None:
        self.ma = ma
        self.nhom = nhom
        self.ten = ten
        self.muc_do = muc_do
        self.vi_sao = vi_sao
        self.goi_y = goi_y
        self.buoc = buoc
        self.kiem = kiem
        self.do_dai = do_dai

    def dat(self, d: Dossier) -> bool:
        if self.kiem:
            return bool(self.kiem(d))
        return _co(_lay(d, self.ma), self.do_dai)


def _co_so_tien(d: Dossier) -> bool:
    so = doc_tien(d.de_nghi_vay.so_tien)
    return bool(so and so > 0)


def _co_thoi_han(d: Dossier) -> bool:
    thang = doc_thang(d.de_nghi_vay.thoi_han)
    return bool(thang and thang > 0)


def _co_tai_chinh(d: Dossier, ghi_chu: str = "") -> bool:
    """Có bảng số liệu tài chính, hoặc mô tả tài chính đủ dài kèm con số."""
    co_bang = any(
        _co(r.chi_tieu) and (_co(r.nam_hien_tai) or _co(r.nam_truoc))
        for r in d.tinh_hinh_tai_chinh
    )
    if co_bang:
        return True
    return len(ghi_chu.strip()) >= 40 and any(ch.isdigit() for ch in ghi_chu)


def _co_tsbd(d: Dossier, ghi_chu: str = "") -> bool:
    co_bang = any(_co(t.ten_tai_san) for t in d.tai_san_bao_dam)
    if co_bang:
        return True
    return len(ghi_chu.strip()) >= 30


def _khong_bao_dam(d: Dossier) -> bool:
    """Khách chủ động khai vay tín chấp thì không bắt buộc khai tài sản bảo đảm."""
    phang = bo_dau(f"{d.ghi_chu} {d.de_nghi_vay.phuong_thuc_cho_vay} {d.tom_tat_phuong_an}")
    return any(k in phang for k in ("tin chap", "khong co bao dam", "khong tai san bao dam"))


def _quy_tac(ghi_chu_tai_chinh: str, ghi_chu_tsbd: str) -> list[QuyTac]:
    return [
        QuyTac("ben_vay.ten", "Thông tin khách hàng", "Tên khách hàng / doanh nghiệp", "bat_buoc",
               "Không có tên bên vay thì hồ sơ không xác định được chủ thể đề nghị cấp tín dụng.",
               "Ghi đúng tên trên giấy đăng ký kinh doanh hoặc CCCD.", 1, do_dai=2),
        QuyTac("ben_vay.loai_hinh", "Thông tin khách hàng", "Loại hình khách hàng", "bat_buoc",
               "Loại hình quyết định danh mục giấy tờ pháp lý phải nộp và cách thẩm định.",
               "Chọn Cá nhân, Hộ kinh doanh, Công ty TNHH, Công ty cổ phần…", 1),
        QuyTac("ben_vay.so_giay_to", "Thông tin khách hàng", "Số CCCD hoặc số đăng ký kinh doanh",
               "bat_buoc", "Là căn cứ định danh khách hàng trong hợp đồng tín dụng.",
               "Nhập số CCCD với cá nhân, số ĐKKD với tổ chức.", 1, do_dai=6),
        QuyTac("ben_vay.dia_chi", "Thông tin khách hàng", "Địa chỉ trụ sở / thường trú", "quan_trong",
               "Địa chỉ là thông tin bắt buộc trên hợp đồng tín dụng và hợp đồng bảo đảm.",
               "Ghi địa chỉ đầy đủ theo giấy tờ pháp lý.", 1, do_dai=8),
        QuyTac("ben_vay.nganh_nghe", "Thông tin khách hàng", "Ngành nghề kinh doanh chính", "quan_trong",
               "Ngành nghề quyết định nhóm quy định pháp luật áp dụng và mức rủi ro ngành.",
               "Ghi ngành nghề chính đang tạo ra doanh thu.", 1),
        QuyTac("ben_vay.nguoi_dai_dien", "Thông tin khách hàng", "Người đại diện theo pháp luật",
               "quan_trong", "Cần xác định người có thẩm quyền ký hợp đồng tín dụng.",
               "Bỏ qua nếu khách hàng là cá nhân tự vay.", 1,
               kiem=lambda d: la_ca_nhan(d.ben_vay.loai_hinh) or _co(d.ben_vay.nguoi_dai_dien)),
        QuyTac("to_chuc_tin_dung", "Thông tin khách hàng", "Ngân hàng dự kiến vay", "nen_co",
               "Giúp hồ sơ ghi đúng nơi nhận và áp dụng đúng biểu mẫu.",
               "Ghi tên ngân hàng và chi nhánh dự kiến nộp hồ sơ.", 1),

        QuyTac("de_nghi_vay.so_tien", "Nhu cầu vay vốn", "Số tiền đề nghị vay", "bat_buoc",
               "Thiếu số tiền thì không tính được lịch trả nợ, DSCR, LTV hay hạn mức đề xuất.",
               "Nhập số tiền, ví dụ 5.000.000.000 hoặc 5 tỷ.", 1, kiem=_co_so_tien),
        QuyTac("de_nghi_vay.thoi_han", "Nhu cầu vay vốn", "Thời hạn vay", "bat_buoc",
               "Thời hạn quyết định lịch trả nợ và khả năng cân đối dòng tiền của khách hàng.",
               "Nhập ví dụ 60 tháng hoặc 5 năm.", 1, kiem=_co_thoi_han),
        QuyTac("de_nghi_vay.muc_dich_vay", "Nhu cầu vay vốn", "Mục đích vay vốn", "bat_buoc",
               "Mục đích vay là điều kiện vay vốn bắt buộc và là căn cứ kiểm tra sử dụng vốn sau giải ngân.",
               "Mô tả cụ thể: mua gì, phục vụ hoạt động nào, ở đâu.", 1, do_dai=15),
        QuyTac("de_nghi_vay.lai_suat_du_kien", "Nhu cầu vay vốn", "Lãi suất dự kiến", "quan_trong",
               "Không có lãi suất thì lịch trả nợ và chi phí vốn chỉ là ước lượng theo mặt bằng chung.",
               "Ghi theo thông báo của ngân hàng, ví dụ 9,5%/năm.", 1),
        QuyTac("de_nghi_vay.phuong_thuc_tra_no", "Nhu cầu vay vốn", "Phương thức trả nợ", "quan_trong",
               "Cách trả nợ ảnh hưởng trực tiếp tới áp lực dòng tiền từng năm.",
               "Chọn trả gốc đều, niên kim hoặc gốc cuối kỳ.", 1),
        QuyTac("de_nghi_vay.von_tu_co", "Nhu cầu vay vốn", "Vốn tự có tham gia phương án", "quan_trong",
               "Tỷ lệ vốn tự có là một tiêu chí chấm điểm và thường là điều kiện cấp tín dụng.",
               "Ghi số vốn khách hàng bỏ ra trong tổng vốn của phương án.", 1),

        QuyTac("tom_tat_phuong_an", "Phương án sử dụng vốn", "Tóm tắt phương án sử dụng vốn", "bat_buoc",
               "Phương án sử dụng vốn khả thi là điều kiện vay vốn bắt buộc theo quy định pháp luật.",
               "Viết 3-6 câu: làm gì, quy mô, đầu ra, vì sao khả thi.", 1, do_dai=40),
        QuyTac("phuong_an_tra_no", "Phương án sử dụng vốn", "Nguồn trả nợ và kế hoạch trả nợ", "bat_buoc",
               "Ngân hàng chỉ cho vay khi xác định được nguồn trả nợ cụ thể.",
               "Nêu rõ nguồn thu nào trả nợ, mỗi kỳ trả bao nhiêu.", 1, do_dai=25),
        QuyTac("phuong_an_su_dung_von", "Phương án sử dụng vốn", "Các khoản mục sử dụng vốn", "quan_trong",
               "Bóc tách khoản mục giúp kiểm soát giải ngân đúng mục đích.",
               "Mỗi dòng một khoản mục kèm số tiền.", 1),

        QuyTac("tinh_hinh_tai_chinh", "Tài chính", "Số liệu tài chính", "bat_buoc",
               "Không có số liệu tài chính thì không thẩm định được giá trị doanh nghiệp và khả năng trả nợ.",
               "Nhập tối thiểu: doanh thu, lợi nhuận sau thuế, tổng tài sản, nợ phải trả của 2 kỳ gần nhất.",
               1, kiem=lambda d: _co_tai_chinh(d, ghi_chu_tai_chinh)),
        QuyTac("tai_san_bao_dam", "Tài sản bảo đảm", "Tài sản bảo đảm", "bat_buoc",
               "Thiếu tài sản bảo đảm thì không tính được hệ số LTV và mức tổn thất dự kiến.",
               "Khai từng tài sản kèm giá trị ước tính và giấy tờ pháp lý. "
               "Nếu vay tín chấp, hãy ghi rõ 'vay tín chấp' trong phần ghi chú.",
               1, kiem=lambda d: _khong_bao_dam(d) or _co_tsbd(d, ghi_chu_tsbd)),
    ]


# --------------------------------------------------------------- kiểm tra


def kiem_tra(
    d: Dossier,
    ghi_chu_tai_chinh: str = "",
    ghi_chu_tsbd: str = "",
    kho_van_ban_trong: bool = False,
) -> ReadinessReport:
    """Chấm mức độ sẵn sàng của hồ sơ; ``du_dieu_kien`` False là chặn pipeline."""
    quy_tac = _quy_tac(ghi_chu_tai_chinh, ghi_chu_tsbd)

    thieu_bat_buoc: list[MissingItem] = []
    thieu_quan_trong: list[MissingItem] = []
    thieu_nen_co: list[MissingItem] = []

    theo_nhom: dict[str, list[int]] = {}
    for qt in quy_tac:
        dat = qt.dat(d)
        cong = theo_nhom.setdefault(qt.nhom, [0, 0])
        cong[1] += 1
        if dat:
            cong[0] += 1
            continue
        muc = MissingItem(ma=qt.ma, nhom=qt.nhom, ten=qt.ten, muc_do=qt.muc_do,
                          vi_sao=qt.vi_sao, goi_y=qt.goi_y, buoc=qt.buoc)
        if qt.muc_do == "bat_buoc":
            thieu_bat_buoc.append(muc)
        elif qt.muc_do == "quan_trong":
            thieu_quan_trong.append(muc)
        else:
            thieu_nen_co.append(muc)

    # --- giấy tờ ---
    giay_to = hop_nhat_giay_to(d.ben_vay.loai_hinh, d.ho_so_cung_cap)
    giay_to_bat_buoc = [g for g in giay_to if g.bat_buoc]
    giay_to_thieu = [g for g in giay_to_bat_buoc if not g.da_co]

    nhom_giay_to = "Giấy tờ phải nộp"
    theo_nhom[nhom_giay_to] = [
        len(giay_to_bat_buoc) - len(giay_to_thieu),
        len(giay_to_bat_buoc),
    ]
    for g in giay_to_thieu:
        thieu_bat_buoc.append(
            MissingItem(
                ma=f"ho_so_cung_cap.{g.ma}", nhom=nhom_giay_to, ten=g.ten, muc_do="bat_buoc",
                vi_sao=g.can_cu or "Là giấy tờ tối thiểu trong bộ hồ sơ đề nghị cấp tín dụng.",
                goi_y="Chuẩn bị bản sao có chứng thực rồi tích vào ô tương ứng ở bước 1.", buoc=1,
            )
        )

    # --- điểm & thông điệp ---
    tong_bat_buoc = sum(1 for qt in quy_tac if qt.muc_do == "bat_buoc") + len(giay_to_bat_buoc)
    da_co_bat_buoc = tong_bat_buoc - len(thieu_bat_buoc)

    trong_so = {"bat_buoc": 3.0, "quan_trong": 1.5, "nen_co": 0.5}
    tong_diem = sum(trong_so[qt.muc_do] for qt in quy_tac) + trong_so["bat_buoc"] * len(giay_to_bat_buoc)
    mat_diem = (
        trong_so["bat_buoc"] * len(thieu_bat_buoc)
        + trong_so["quan_trong"] * len(thieu_quan_trong)
        + trong_so["nen_co"] * len(thieu_nen_co)
    )
    diem = int(round(max(0.0, (tong_diem - mat_diem) / tong_diem * 100))) if tong_diem else 0

    canh_bao: list[str] = []
    if kho_van_ban_trong:
        canh_bao.append(
            "Kho văn bản pháp luật đang trống — hồ sơ sẽ không có mục căn cứ pháp lý trích dẫn. "
            "Hãy nạp Thông tư, Nghị định liên quan ở cột trái trước khi lập hồ sơ."
        )
    if thieu_quan_trong:
        canh_bao.append(
            f"Còn {len(thieu_quan_trong)} thông tin quan trọng chưa có. Hồ sơ vẫn lập được "
            "nhưng phần thẩm định sẽ kém chính xác hơn."
        )

    du_dieu_kien = not thieu_bat_buoc
    if du_dieu_kien:
        thong_diep = (
            f"Hồ sơ đã đủ điều kiện để lập. Mức độ đầy đủ {diem}%"
            + (f", còn {len(thieu_quan_trong)} mục nên bổ sung." if thieu_quan_trong else ".")
        )
    else:
        nhom_thieu = sorted({m.nhom for m in thieu_bat_buoc})
        thong_diep = (
            f"Chưa thể lập hồ sơ: còn thiếu {len(thieu_bat_buoc)} mục bắt buộc "
            f"thuộc {len(nhom_thieu)} nhóm ({', '.join(nhom_thieu)}). "
            "Vui lòng bổ sung đầy đủ rồi chạy lại."
        )

    return ReadinessReport(
        du_dieu_kien=du_dieu_kien,
        diem=diem,
        tong_bat_buoc=tong_bat_buoc,
        da_co_bat_buoc=da_co_bat_buoc,
        thieu_bat_buoc=thieu_bat_buoc,
        thieu_quan_trong=thieu_quan_trong,
        thieu_nen_co=thieu_nen_co,
        giay_to_thieu=giay_to_thieu,
        nhom_trang_thai=[
            GroupStatus(nhom=ten, da_co=v[0], tong=v[1], dat=v[0] >= v[1])
            for ten, v in theo_nhom.items()
        ],
        canh_bao=canh_bao,
        thong_diep=thong_diep,
    )
