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


class DossierGenerateRequest(BaseModel):
    """Sinh hồ sơ từ hội thoại + (tuỳ chọn) dữ liệu người dùng đã nhập sẵn."""

    messages: list[Message] = Field(default_factory=list)
    huong_dan_them: str = ""
    dossier_hien_tai: dict[str, Any] | None = None
    model: str | None = None


class DossierExportRequest(BaseModel):
    dossier: Dossier
    ten_file: str = ""
    kem_can_cu_phap_ly: bool = True
    kem_checklist: bool = True
