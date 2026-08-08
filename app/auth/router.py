"""API tài khoản: đăng ký, đăng nhập, đăng xuất, đổi mật khẩu, quản trị người dùng."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..config import settings
from . import service
from .deps import (
    dat_cookie,
    nguoi_dung_tuy_chon,
    token_tu_request,
    xoa_cookie,
    yeu_cau_dang_nhap,
    yeu_cau_quan_tri,
)
from .models import (
    CapNhatHoSoRequest,
    CapNhatNguoiDungRequest,
    DangKyRequest,
    DangNhapRequest,
    DatLaiMatKhauRequest,
    DoiMatKhauRequest,
    KetQuaDangNhap,
    NguoiDung,
    TrangThaiAuth,
)
from .service import LoiTaiKhoan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Tài khoản"])


def _bao_loi(exc: LoiTaiKhoan) -> HTTPException:
    return HTTPException(status_code=exc.ma, detail=exc.thong_diep)


def _thiet_bi(request: Request) -> str:
    return request.headers.get("user-agent", "")


def _mo_phien(response: Response, request: Request, nguoi_dung: NguoiDung, ghi_nho: bool) -> KetQuaDangNhap:
    so_ngay = settings.session_ttl_days if ghi_nho else 1
    token, het_han = service.tao_phien(nguoi_dung.id, _thiet_bi(request), so_ngay)
    dat_cookie(response, request, token, so_ngay)
    return KetQuaDangNhap(ok=True, nguoi_dung=nguoi_dung, token=token, het_han=het_han)


# ------------------------------------------------------------------ công khai


@router.get("/status", response_model=TrangThaiAuth)
def trang_thai(nguoi_dung: NguoiDung | None = Depends(nguoi_dung_tuy_chon)) -> TrangThaiAuth:
    """Màn hình đăng nhập gọi đầu tiên để biết nên hiện form đăng nhập hay đăng ký."""
    da_co = service.dem_nguoi_dung() > 0
    return TrangThaiAuth(
        dang_nhap=nguoi_dung is not None,
        nguoi_dung=nguoi_dung,
        # Chưa có tài khoản nào thì luôn cho đăng ký, để còn lập được quản trị viên đầu tiên.
        cho_phep_dang_ky=settings.allow_registration or not da_co,
        da_co_tai_khoan=da_co,
    )


@router.post("/register", response_model=KetQuaDangNhap)
def dang_ky(req: DangKyRequest, request: Request, response: Response) -> KetQuaDangNhap:
    try:
        nguoi_dung = service.dang_ky(req.username, req.password, req.ho_ten, req.email)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc
    logger.info("Tài khoản mới: %s", nguoi_dung.username)
    return _mo_phien(response, request, nguoi_dung, ghi_nho=True)


@router.post("/login", response_model=KetQuaDangNhap)
def dang_nhap(req: DangNhapRequest, request: Request, response: Response) -> KetQuaDangNhap:
    try:
        nguoi_dung = service.xac_thuc(req.username, req.password)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc
    return _mo_phien(response, request, nguoi_dung, req.ghi_nho)


@router.post("/logout")
def dang_xuat(request: Request, response: Response) -> dict:
    """Huỷ phiên hiện tại và xoá cookie. Gọi khi chưa đăng nhập cũng không báo lỗi."""
    service.xoa_phien(token_tu_request(request))
    xoa_cookie(response, request)
    return {"ok": True}


# -------------------------------------------------------------- đã đăng nhập


@router.get("/me", response_model=NguoiDung)
def toi(nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)) -> NguoiDung:
    return nguoi_dung


@router.put("/me", response_model=NguoiDung)
def sua_ho_so(req: CapNhatHoSoRequest, nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)) -> NguoiDung:
    try:
        return service.cap_nhat_ho_so(nguoi_dung.id, req.ho_ten, req.email)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc


@router.post("/change-password")
def doi_mat_khau(
    req: DoiMatKhauRequest,
    request: Request,
    nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap),
) -> dict:
    try:
        service.doi_mat_khau(nguoi_dung.id, req.mat_khau_cu, req.mat_khau_moi)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc

    da_dong = 0
    if req.dang_xuat_thiet_bi_khac:
        # Giữ lại đúng phiên đang thao tác, đóng mọi phiên còn lại.
        da_dong = service.xoa_moi_phien(nguoi_dung.id, tru_token=token_tu_request(request))
    return {"ok": True, "da_dong_phien": da_dong}


@router.post("/logout-all")
def dang_xuat_moi_noi(request: Request, nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)) -> dict:
    da_dong = service.xoa_moi_phien(nguoi_dung.id, tru_token=token_tu_request(request))
    return {"ok": True, "da_dong_phien": da_dong}


# ------------------------------------------------------------- quản trị viên


@router.get("/users", response_model=list[NguoiDung])
def danh_sach(_admin: NguoiDung = Depends(yeu_cau_quan_tri)) -> list[NguoiDung]:
    return service.danh_sach_nguoi_dung()


@router.post("/users", response_model=NguoiDung)
def tao_tai_khoan(req: DangKyRequest, _admin: NguoiDung = Depends(yeu_cau_quan_tri)) -> NguoiDung:
    try:
        return service.tao_nguoi_dung(req.username, req.password, req.ho_ten, req.email)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc


@router.patch("/users/{user_id}", response_model=NguoiDung)
def sua_tai_khoan(
    user_id: int,
    req: CapNhatNguoiDungRequest,
    admin: NguoiDung = Depends(yeu_cau_quan_tri),
) -> NguoiDung:
    if user_id == admin.id and req.kich_hoat is False:
        raise HTTPException(status_code=409, detail="Không thể tự khoá tài khoản của chính mình.")
    try:
        return service.cap_nhat_nguoi_dung(user_id, req.vai_tro, req.kich_hoat)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc


@router.post("/users/{user_id}/password")
def dat_lai_mat_khau(
    user_id: int,
    req: DatLaiMatKhauRequest,
    _admin: NguoiDung = Depends(yeu_cau_quan_tri),
) -> dict:
    try:
        service.dat_lai_mat_khau(user_id, req.mat_khau_moi)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc
    return {"ok": True}


@router.delete("/users/{user_id}")
def xoa_tai_khoan(user_id: int, admin: NguoiDung = Depends(yeu_cau_quan_tri)) -> dict:
    if user_id == admin.id:
        raise HTTPException(status_code=409, detail="Không thể tự xoá tài khoản của chính mình.")
    try:
        service.xoa_nguoi_dung(user_id)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc
    return {"ok": True}
