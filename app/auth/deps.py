"""Phụ thuộc FastAPI: đọc phiên từ cookie hoặc header, chặn request chưa đăng nhập."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response

from ..config import settings
from . import service
from .models import NguoiDung

TEN_COOKIE = "tctd_session"


# ------------------------------------------------------------------- cookie


def dung_https(request: Request) -> bool:
    """Railway đứng sau proxy nên phải nhìn X-Forwarded-Proto mới biết là HTTPS."""
    proto = request.headers.get("x-forwarded-proto", "")
    if proto:
        return proto.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


def _co_secure(request: Request) -> bool:
    che_do = (settings.cookie_secure or "auto").strip().lower()
    if che_do in ("1", "true", "yes", "on"):
        return True
    if che_do in ("0", "false", "no", "off"):
        return False
    return dung_https(request)


def dat_cookie(response: Response, request: Request, token: str, so_ngay: int) -> None:
    response.set_cookie(
        TEN_COOKIE,
        token,
        max_age=so_ngay * 24 * 3600,
        httponly=True,          # JavaScript không đọc được token → giảm hậu quả nếu dính XSS
        samesite="lax",
        secure=_co_secure(request),
        path="/",
    )


def xoa_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(TEN_COOKIE, path="/", samesite="lax", secure=_co_secure(request))


# -------------------------------------------------------------------- phiên


def token_tu_request(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(TEN_COOKIE, "")


def nguoi_dung_tuy_chon(request: Request) -> NguoiDung | None:
    """Dùng cho endpoint công khai muốn biết người dùng là ai (nếu có)."""
    return service.nguoi_dung_theo_token(token_tu_request(request))


def yeu_cau_dang_nhap(request: Request) -> NguoiDung:
    nguoi_dung = service.nguoi_dung_theo_token(token_tu_request(request))
    if nguoi_dung is None:
        raise HTTPException(
            status_code=401,
            detail="Bạn cần đăng nhập để dùng chức năng này.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return nguoi_dung


def yeu_cau_quan_tri(nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)) -> NguoiDung:
    if nguoi_dung.vai_tro != "admin":
        raise HTTPException(status_code=403, detail="Chức năng này chỉ dành cho quản trị viên.")
    return nguoi_dung
