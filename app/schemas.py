"""Pydantic schema dùng chung cho API chat, RAG và hồ sơ vay vốn."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- Chat / RAG


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    model: str | None = None
    temperature: float | None = None
    top_k: int | None = None
    use_rag: bool = True


class SourceRef(BaseModel):
    id: int
    chunk_id: str
    doc_id: str
    doc_title: str
    file_name: str
    citation: str
    chuong: str = ""
    muc: str = ""
    dieu: str = ""
    dieu_title: str = ""
    score: float = 0.0
    excerpt: str = ""


class DocumentInfo(BaseModel):
    doc_id: str
    doc_title: str
    file_name: str
    so_hieu: str = ""
    loai_van_ban: str = ""
    n_chunks: int = 0
    n_chars: int = 0
    ingested_at: str = ""


class IngestResult(BaseModel):
    ok: bool
    documents: list[DocumentInfo] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    total_chunks: int = 0


class SearchRequest(BaseModel):
    query: str
    top_k: int | None = None


# ------------------------------------------------------- Hồ sơ vay / gọi vốn


class Party(BaseModel):
    ten: str = ""
    loai_hinh: str = ""  # Cá nhân / Hộ kinh doanh / Công ty TNHH / CTCP ...
    ma_so_thue: str = ""
    so_giay_to: str = ""  # CCCD hoặc số ĐKKD
    nguoi_dai_dien: str = ""
    chuc_vu: str = ""
    dia_chi: str = ""
    dien_thoai: str = ""
    email: str = ""
    nganh_nghe: str = ""
    nam_thanh_lap: str = ""
    von_dieu_le: str = ""


class LoanRequest(BaseModel):
    so_tien: str = ""
    bang_chu: str = ""
    don_vi: str = "VND"
    muc_dich_vay: str = ""
    thoi_han: str = ""
    phuong_thuc_cho_vay: str = ""  # từng lần / hạn mức / dự án đầu tư ...
    phuong_thuc_giai_ngan: str = ""
    phuong_thuc_tra_no: str = ""
    lai_suat_du_kien: str = ""
    von_tu_co: str = ""
    ty_le_vay_tren_tong_von: str = ""


class CollateralItem(BaseModel):
    ten_tai_san: str = ""
    mo_ta: str = ""
    gia_tri_uoc_tinh: str = ""
    giay_to_phap_ly: str = ""
    ghi_chu: str = ""


class FinancialRow(BaseModel):
    chi_tieu: str = ""
    nam_truoc: str = ""
    nam_hien_tai: str = ""
    du_kien: str = ""


class CashflowRow(BaseModel):
    ky: str = ""
    dong_tien_vao: str = ""
    dong_tien_ra: str = ""
    tra_goc: str = ""
    tra_lai: str = ""
    du_cuoi_ky: str = ""
    du_no_cuoi_ky: str = ""
    dscr: str = ""


class ChecklistItem(BaseModel):
    nhom: str = ""  # Hồ sơ pháp lý / Hồ sơ tài chính / Hồ sơ TSBĐ ...
    ten_tai_lieu: str = ""
    bat_buoc: bool = True
    can_cu_phap_ly: str = ""
    ghi_chu: str = ""


class LegalBasis(BaseModel):
    van_ban: str = ""
    dieu_khoan: str = ""
    noi_dung: str = ""
    ap_dung: str = ""


class RiskItem(BaseModel):
    rui_ro: str = ""
    muc_do: str = ""  # Cao / Trung bình / Thấp
    bien_phap: str = ""


# ------------------------------------------ Thẩm định & phân tích tài chính


class FinancialRatio(BaseModel):
    """Một chỉ số tài chính đã tính sẵn kèm ngưỡng tham chiếu và đánh giá."""

    ma: str = ""
    ten: str = ""
    gia_tri: str = ""            # đã định dạng, ví dụ "12,4%" hoặc "1,45 lần"
    so: float | None = None      # giá trị số để vẽ biểu đồ / so sánh
    don_vi: str = ""             # "%", "lần", "VND"
    nguong: str = ""             # ngưỡng tham chiếu thông lệ
    danh_gia: str = ""           # Tốt | Đạt | Cần lưu ý | Yếu | Không đủ dữ liệu
    y_nghia: str = ""
    cong_thuc: str = ""


class ValuationAssumption(BaseModel):
    ten: str = ""
    gia_tri: str = ""
    can_cu: str = ""


class ValuationDetail(BaseModel):
    khoan_muc: str = ""
    gia_tri: str = ""
    ghi_chu: str = ""


class ValuationMethod(BaseModel):
    ma: str = ""                 # NAV | DCF | MARKET
    ten: str = ""
    ap_dung_duoc: bool = True
    ly_do_khong_ap_dung: str = ""
    gia_tri: float = 0.0         # VND
    gia_tri_hien_thi: str = ""
    trong_so: float = 0.0        # 0..1
    dien_giai: str = ""
    chi_tiet: list[ValuationDetail] = Field(default_factory=list)


class DcfYear(BaseModel):
    nam: str = ""
    dong_tien_tu_do: str = ""
    he_so_chiet_khau: str = ""
    gia_tri_hien_tai: str = ""


class Valuation(BaseModel):
    """Kết quả thẩm định giá trị doanh nghiệp của khách hàng vay."""

    thuc_hien_duoc: bool = False
    ly_do: str = ""
    don_vi: str = "VND"
    nam_co_so: str = ""
    gia_dinh: list[ValuationAssumption] = Field(default_factory=list)
    phuong_phap: list[ValuationMethod] = Field(default_factory=list)
    dcf_chi_tiet: list[DcfYear] = Field(default_factory=list)
    gia_tri_ket_luan: float = 0.0
    gia_tri_ket_luan_hien_thi: str = ""
    gia_tri_bang_chu: str = ""
    khoang_thap: str = ""
    khoang_cao: str = ""
    nhan_xet: list[str] = Field(default_factory=list)
    canh_bao: list[str] = Field(default_factory=list)


class AppraisalConclusion(BaseModel):
    """Kết luận thẩm định tín dụng: điểm, xếp hạng, đề xuất."""

    diem: int = 0                # 0..100
    xep_hang: str = ""           # AAA..D
    muc_rui_ro: str = ""         # Thấp | Trung bình | Cao
    de_xuat: str = ""            # Đề xuất cho vay / cho vay có điều kiện / từ chối
    han_muc_de_xuat: str = ""
    cac_diem_manh: list[str] = Field(default_factory=list)
    cac_diem_yeu: list[str] = Field(default_factory=list)
    dieu_kien_kem_theo: list[str] = Field(default_factory=list)
    thanh_phan_diem: list[FinancialRatio] = Field(default_factory=list)


# ------------------------------------------------------------- Biểu đồ


class ChartSeries(BaseModel):
    ten: str = ""
    gia_tri: list[float] = Field(default_factory=list)
    mau: str = ""                # hex, do backend chỉ định để PDF và web trùng nhau
    kieu: str = "cot"            # cot | duong | nguong


class ChartSpec(BaseModel):
    ma: str = ""
    loai: Literal["cot", "cot_ngang", "duong", "tron"] = "cot"
    tieu_de: str = ""
    mo_ta: str = ""
    don_vi: str = ""             # nhãn đơn vị trục giá trị: "triệu VND", "%", "lần"
    he_so: float = 1.0           # giá trị gốc = gia_tri * he_so (dùng khi quy đổi đơn vị)
    nhan: list[str] = Field(default_factory=list)
    chuoi: list[ChartSeries] = Field(default_factory=list)
    ghi_chu: str = ""


# ------------------------------------------------ Kiểm tra tính đầy đủ


class ProvidedDoc(BaseModel):
    """Một loại giấy tờ khách hàng phải nộp, kèm trạng thái đã có hay chưa."""

    ma: str = ""
    nhom: str = ""
    ten: str = ""
    bat_buoc: bool = True
    da_co: bool = False
    can_cu: str = ""
    ghi_chu: str = ""


class MissingItem(BaseModel):
    ma: str = ""                 # đường dẫn trường dữ liệu, dùng để nhảy tới ô nhập
    nhom: str = ""
    ten: str = ""
    muc_do: Literal["bat_buoc", "quan_trong", "nen_co"] = "bat_buoc"
    vi_sao: str = ""
    goi_y: str = ""
    buoc: int = 1


class GroupStatus(BaseModel):
    nhom: str = ""
    da_co: int = 0
    tong: int = 0
    dat: bool = False


class ReadinessReport(BaseModel):
    """Kết quả cổng kiểm tra: chưa đủ thì pipeline dừng, không sinh hồ sơ."""

    du_dieu_kien: bool = False
    diem: int = 0
    tong_bat_buoc: int = 0
    da_co_bat_buoc: int = 0
    thieu_bat_buoc: list[MissingItem] = Field(default_factory=list)
    thieu_quan_trong: list[MissingItem] = Field(default_factory=list)
    thieu_nen_co: list[MissingItem] = Field(default_factory=list)
    giay_to_thieu: list[ProvidedDoc] = Field(default_factory=list)
    nhom_trang_thai: list[GroupStatus] = Field(default_factory=list)
    canh_bao: list[str] = Field(default_factory=list)
    thong_diep: str = ""


# ------------------------------------------------------------- Hồ sơ


class Dossier(BaseModel):
    tieu_de: str = "HỒ SƠ ĐỀ NGHỊ CẤP TÍN DỤNG"
    ngay_lap: str = ""
    noi_lap: str = ""
    to_chuc_tin_dung: str = ""
    ben_vay: Party = Field(default_factory=Party)
    de_nghi_vay: LoanRequest = Field(default_factory=LoanRequest)
    tom_tat_phuong_an: str = ""
    phuong_an_su_dung_von: list[str] = Field(default_factory=list)
    phuong_an_tra_no: str = ""
    tai_san_bao_dam: list[CollateralItem] = Field(default_factory=list)
    tinh_hinh_tai_chinh: list[FinancialRow] = Field(default_factory=list)
    dong_tien_du_kien: list[CashflowRow] = Field(default_factory=list)
    danh_muc_ho_so: list[ChecklistItem] = Field(default_factory=list)
    can_cu_phap_ly: list[LegalBasis] = Field(default_factory=list)
    danh_gia_rui_ro: list[RiskItem] = Field(default_factory=list)
    khuyen_nghi: list[str] = Field(default_factory=list)
    ghi_chu: str = ""

    # --- phần thẩm định do hệ thống tính toán ---
    ho_so_cung_cap: list[ProvidedDoc] = Field(default_factory=list)
    chi_so_tai_chinh: list[FinancialRatio] = Field(default_factory=list)
    tham_dinh_gia_tri: Valuation = Field(default_factory=Valuation)
    ket_luan_tham_dinh: AppraisalConclusion = Field(default_factory=AppraisalConclusion)
    bieu_do: list[ChartSpec] = Field(default_factory=list)
    la_ho_so_mau: bool = False


class DossierGenerateRequest(BaseModel):
    """Sinh hồ sơ từ hội thoại + (tuỳ chọn) dữ liệu người dùng đã nhập sẵn."""

    messages: list[Message] = Field(default_factory=list)
    huong_dan_them: str = ""
    dossier_hien_tai: dict[str, Any] | None = None
    model: str | None = None


class DossierPipelineRequest(DossierGenerateRequest):
    """Chạy trọn quy trình lập hồ sơ, có cổng kiểm tra đầu vào."""

    bo_qua_canh_bao: bool = False   # chỉ bỏ qua cảnh báo mức "quan trọng"
    tinh_dinh_gia: bool = True
    top_k: int | None = None


class ReadinessRequest(BaseModel):
    dossier_hien_tai: dict[str, Any] | None = None
    huong_dan_them: str = ""
    messages: list[Message] = Field(default_factory=list)


class DossierExportRequest(BaseModel):
    dossier: Dossier
    ten_file: str = ""
    kem_can_cu_phap_ly: bool = True
    kem_checklist: bool = True
    kem_tham_dinh: bool = True
    kem_bieu_do: bool = True
