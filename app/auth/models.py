"""Schema cho API tài khoản và API dữ liệu người dùng."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- tài khoản


class DangKyRequest(BaseModel):
    username: str
    password: str
    ho_ten: str = ""
    email: str = ""


class DangNhapRequest(BaseModel):
    username: str
    password: str
    ghi_nho: bool = True


class DoiMatKhauRequest(BaseModel):
    mat_khau_cu: str
    mat_khau_moi: str
    dang_xuat_thiet_bi_khac: bool = True


class CapNhatHoSoRequest(BaseModel):
    ho_ten: str = ""
    email: str = ""


class NguoiDung(BaseModel):
    id: int
    username: str
    email: str = ""
    ho_ten: str = ""
    vai_tro: str = "user"
    kich_hoat: bool = True
    tao_luc: str = ""
    dang_nhap_luc: str = ""

    @property
    def la_quan_tri(self) -> bool:
        return self.vai_tro == "admin"


class TrangThaiAuth(BaseModel):
    """Trả về cho màn hình đăng nhập trước khi người dùng có phiên."""

    dang_nhap: bool = False
    nguoi_dung: NguoiDung | None = None
    cho_phep_dang_ky: bool = True
    da_co_tai_khoan: bool = False


class KetQuaDangNhap(BaseModel):
    ok: bool = True
    nguoi_dung: NguoiDung
    token: str = ""
    het_han: str = ""


class CapNhatNguoiDungRequest(BaseModel):
    vai_tro: str | None = None
    kich_hoat: bool | None = None


class DatLaiMatKhauRequest(BaseModel):
    mat_khau_moi: str


# ------------------------------------------------------------ dữ liệu riêng


class BanLamViec(BaseModel):
    """Toàn bộ nội dung đang nhập dở, đồng bộ giữa các máy của cùng một tài khoản."""

    co_du_lieu: bool = False
    noi_dung: dict[str, Any] = Field(default_factory=dict)
    cap_nhat: str = ""


class LuuBanLamViecRequest(BaseModel):
    noi_dung: dict[str, Any] = Field(default_factory=dict)


class LuuHoSoRequest(BaseModel):
    tieu_de: str = ""
    dossier: dict[str, Any] = Field(default_factory=dict)
    notes: dict[str, Any] = Field(default_factory=dict)


class HoSoTomTat(BaseModel):
    id: int
    tieu_de: str = ""
    ten_khach: str = ""
    so_tien: str = ""
    diem: int = 0
    tao_luc: str = ""
    cap_nhat: str = ""


class HoSoDayDu(HoSoTomTat):
    dossier: dict[str, Any] = Field(default_factory=dict)
    notes: dict[str, Any] = Field(default_factory=dict)


class TongQuanDuLieu(BaseModel):
    so_ho_so: int = 0
    co_ban_lam_viec: bool = False
    ban_lam_viec_cap_nhat: str = ""
    so_phien_dang_mo: int = 0
    dung_luong_kb: float = 0.0
