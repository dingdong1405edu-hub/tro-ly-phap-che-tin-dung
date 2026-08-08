"""API dữ liệu riêng: bàn làm việc đồng bộ giữa các máy và kho hồ sơ đã lưu."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from . import data_service
from .deps import yeu_cau_dang_nhap
from .models import (
    BanLamViec,
    HoSoDayDu,
    HoSoTomTat,
    LuuBanLamViecRequest,
    LuuHoSoRequest,
    NguoiDung,
    TongQuanDuLieu,
)
from .service import LoiTaiKhoan

router = APIRouter(prefix="/api/data", tags=["Dữ liệu người dùng"])


def _bao_loi(exc: LoiTaiKhoan) -> HTTPException:
    return HTTPException(status_code=exc.ma, detail=exc.thong_diep)


# -------------------------------------------------------------- bàn làm việc


@router.get("/workspace", response_model=BanLamViec)
def lay_ban_lam_viec(nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)) -> BanLamViec:
    return data_service.lay_ban_lam_viec(nguoi_dung.id)


@router.put("/workspace", response_model=BanLamViec)
def luu_ban_lam_viec(
    req: LuuBanLamViecRequest, nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)
) -> BanLamViec:
    try:
        return data_service.luu_ban_lam_viec(nguoi_dung.id, req.noi_dung)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc


@router.delete("/workspace")
def xoa_ban_lam_viec(nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)) -> dict:
    data_service.xoa_ban_lam_viec(nguoi_dung.id)
    return {"ok": True}


# ------------------------------------------------------------- hồ sơ đã lưu


@router.get("/dossiers", response_model=list[HoSoTomTat])
def danh_sach(nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)) -> list[HoSoTomTat]:
    return data_service.danh_sach_ho_so(nguoi_dung.id)


@router.post("/dossiers", response_model=HoSoTomTat)
def luu_moi(req: LuuHoSoRequest, nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)) -> HoSoTomTat:
    try:
        return data_service.luu_ho_so(nguoi_dung.id, req.tieu_de, req.dossier, req.notes)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc


@router.get("/dossiers/{ho_so_id}", response_model=HoSoDayDu)
def mo(ho_so_id: int, nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)) -> HoSoDayDu:
    try:
        return data_service.lay_ho_so(nguoi_dung.id, ho_so_id)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc


@router.put("/dossiers/{ho_so_id}", response_model=HoSoTomTat)
def ghi_de(
    ho_so_id: int, req: LuuHoSoRequest, nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)
) -> HoSoTomTat:
    try:
        return data_service.ghi_de_ho_so(nguoi_dung.id, ho_so_id, req.tieu_de, req.dossier, req.notes)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc


@router.patch("/dossiers/{ho_so_id}", response_model=HoSoTomTat)
def doi_ten(
    ho_so_id: int,
    tieu_de: str = Body("", embed=True),
    nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap),
) -> HoSoTomTat:
    try:
        return data_service.doi_ten_ho_so(nguoi_dung.id, ho_so_id, tieu_de)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc


@router.delete("/dossiers/{ho_so_id}")
def xoa(ho_so_id: int, nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)) -> dict:
    try:
        data_service.xoa_ho_so(nguoi_dung.id, ho_so_id)
    except LoiTaiKhoan as exc:
        raise _bao_loi(exc) from exc
    return {"ok": True}


# ------------------------------------------------------------------ tổng quan


@router.get("/summary", response_model=TongQuanDuLieu)
def tong_quan(nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)) -> TongQuanDuLieu:
    return data_service.tong_quan(nguoi_dung.id)


@router.delete("/all")
def xoa_tat_ca(nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap)) -> dict:
    data_service.xoa_toan_bo_du_lieu(nguoi_dung.id)
    return {"ok": True}
