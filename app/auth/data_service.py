"""Dữ liệu riêng của từng tài khoản: bàn làm việc đang nhập dở và các hồ sơ đã lưu."""

from __future__ import annotations

import json
import logging
from typing import Any

from .db import bay_gio, ket_noi
from .models import BanLamViec, HoSoDayDu, HoSoTomTat, TongQuanDuLieu
from .service import LoiTaiKhoan, dem_phien

logger = logging.getLogger(__name__)

# Chặn một tài khoản ghi khối JSON quá lớn làm phình volume.
GIOI_HAN_BYTE = 4 * 1024 * 1024
GIOI_HAN_HO_SO = 100


def _dong_goi(noi_dung: dict[str, Any]) -> str:
    chuoi = json.dumps(noi_dung, ensure_ascii=False, separators=(",", ":"))
    if len(chuoi.encode("utf-8")) > GIOI_HAN_BYTE:
        raise LoiTaiKhoan("Dữ liệu quá lớn (giới hạn 4 MB cho mỗi bản ghi).", 413)
    return chuoi


def _mo_goi(chuoi: str) -> dict[str, Any]:
    try:
        gia_tri = json.loads(chuoi)
    except (ValueError, TypeError):
        return {}
    return gia_tri if isinstance(gia_tri, dict) else {}


# -------------------------------------------------------------- bàn làm việc


def lay_ban_lam_viec(user_id: int) -> BanLamViec:
    with ket_noi() as conn:
        dong = conn.execute("SELECT * FROM workspaces WHERE user_id = ?", (user_id,)).fetchone()
    if not dong:
        return BanLamViec(co_du_lieu=False)
    return BanLamViec(co_du_lieu=True, noi_dung=_mo_goi(dong["noi_dung"]), cap_nhat=dong["cap_nhat"])


def luu_ban_lam_viec(user_id: int, noi_dung: dict[str, Any]) -> BanLamViec:
    chuoi = _dong_goi(noi_dung)
    luc = bay_gio()
    with ket_noi() as conn:
        conn.execute(
            "INSERT INTO workspaces (user_id, noi_dung, cap_nhat) VALUES (?, ?, ?)"
            " ON CONFLICT(user_id) DO UPDATE SET noi_dung = excluded.noi_dung, cap_nhat = excluded.cap_nhat",
            (user_id, chuoi, luc),
        )
    return BanLamViec(co_du_lieu=True, noi_dung=noi_dung, cap_nhat=luc)


def xoa_ban_lam_viec(user_id: int) -> None:
    with ket_noi() as conn:
        conn.execute("DELETE FROM workspaces WHERE user_id = ?", (user_id,))


# ------------------------------------------------------------- hồ sơ đã lưu


def _tom_tat(dossier: dict[str, Any], tieu_de: str) -> tuple[str, str, str, int]:
    """Rút vài trường ra cột riêng để danh sách hiển thị nhanh, khỏi phải mở JSON."""
    ben_vay = dossier.get("ben_vay") or {}
    de_nghi = dossier.get("de_nghi_vay") or {}
    ket_luan = dossier.get("ket_luan_tham_dinh") or {}

    ten_khach = str(ben_vay.get("ten") or "").strip()
    so_tien = str(de_nghi.get("so_tien") or "").strip()
    don_vi = str(de_nghi.get("don_vi") or "").strip()
    if so_tien and don_vi and don_vi not in so_tien:
        so_tien = f"{so_tien} {don_vi}"

    try:
        diem = int(ket_luan.get("diem") or 0)
    except (TypeError, ValueError):
        diem = 0

    nhan = (tieu_de or "").strip() or ten_khach or str(dossier.get("tieu_de") or "").strip() or "Hồ sơ chưa đặt tên"
    return nhan[:160], ten_khach[:160], so_tien[:60], diem


def _thanh_tom_tat(dong: Any) -> HoSoTomTat:
    return HoSoTomTat(
        id=dong["id"],
        tieu_de=dong["tieu_de"],
        ten_khach=dong["ten_khach"],
        so_tien=dong["so_tien"],
        diem=dong["diem"],
        tao_luc=dong["tao_luc"],
        cap_nhat=dong["cap_nhat"],
    )


def danh_sach_ho_so(user_id: int) -> list[HoSoTomTat]:
    with ket_noi() as conn:
        dongs = conn.execute(
            "SELECT id, tieu_de, ten_khach, so_tien, diem, tao_luc, cap_nhat"
            " FROM dossiers WHERE user_id = ? ORDER BY cap_nhat DESC",
            (user_id,),
        ).fetchall()
    return [_thanh_tom_tat(d) for d in dongs]


def luu_ho_so(user_id: int, tieu_de: str, dossier: dict[str, Any], notes: dict[str, Any]) -> HoSoTomTat:
    nhan, ten_khach, so_tien, diem = _tom_tat(dossier, tieu_de)
    chuoi = _dong_goi({"dossier": dossier, "notes": notes})
    luc = bay_gio()

    with ket_noi() as conn:
        dong = conn.execute(
            "SELECT COUNT(*) AS n FROM dossiers WHERE user_id = ?", (user_id,)
        ).fetchone()
        if int(dong["n"]) >= GIOI_HAN_HO_SO:
            raise LoiTaiKhoan(
                f"Đã đạt giới hạn {GIOI_HAN_HO_SO} hồ sơ đã lưu. Hãy xoá bớt bản cũ trước khi lưu thêm.", 409
            )
        cur = conn.execute(
            "INSERT INTO dossiers (user_id, tieu_de, ten_khach, so_tien, diem, noi_dung, tao_luc, cap_nhat)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, nhan, ten_khach, so_tien, diem, chuoi, luc, luc),
        )
        moi = conn.execute(
            "SELECT id, tieu_de, ten_khach, so_tien, diem, tao_luc, cap_nhat FROM dossiers WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return _thanh_tom_tat(moi)


def lay_ho_so(user_id: int, ho_so_id: int) -> HoSoDayDu:
    with ket_noi() as conn:
        dong = conn.execute(
            "SELECT * FROM dossiers WHERE id = ? AND user_id = ?", (ho_so_id, user_id)
        ).fetchone()
    if not dong:
        raise LoiTaiKhoan("Không tìm thấy hồ sơ đã lưu.", 404)

    goi = _mo_goi(dong["noi_dung"])
    return HoSoDayDu(
        **_thanh_tom_tat(dong).model_dump(),
        dossier=goi.get("dossier") or {},
        notes=goi.get("notes") or {},
    )


def ghi_de_ho_so(
    user_id: int, ho_so_id: int, tieu_de: str, dossier: dict[str, Any], notes: dict[str, Any]
) -> HoSoTomTat:
    nhan, ten_khach, so_tien, diem = _tom_tat(dossier, tieu_de)
    chuoi = _dong_goi({"dossier": dossier, "notes": notes})

    with ket_noi() as conn:
        cur = conn.execute(
            "UPDATE dossiers SET tieu_de = ?, ten_khach = ?, so_tien = ?, diem = ?, noi_dung = ?, cap_nhat = ?"
            " WHERE id = ? AND user_id = ?",
            (nhan, ten_khach, so_tien, diem, chuoi, bay_gio(), ho_so_id, user_id),
        )
        if not cur.rowcount:
            raise LoiTaiKhoan("Không tìm thấy hồ sơ đã lưu.", 404)
        dong = conn.execute(
            "SELECT id, tieu_de, ten_khach, so_tien, diem, tao_luc, cap_nhat FROM dossiers WHERE id = ?",
            (ho_so_id,),
        ).fetchone()
    return _thanh_tom_tat(dong)


def doi_ten_ho_so(user_id: int, ho_so_id: int, tieu_de: str) -> HoSoTomTat:
    nhan = (tieu_de or "").strip()[:160] or "Hồ sơ chưa đặt tên"
    with ket_noi() as conn:
        cur = conn.execute(
            "UPDATE dossiers SET tieu_de = ?, cap_nhat = ? WHERE id = ? AND user_id = ?",
            (nhan, bay_gio(), ho_so_id, user_id),
        )
        if not cur.rowcount:
            raise LoiTaiKhoan("Không tìm thấy hồ sơ đã lưu.", 404)
        dong = conn.execute(
            "SELECT id, tieu_de, ten_khach, so_tien, diem, tao_luc, cap_nhat FROM dossiers WHERE id = ?",
            (ho_so_id,),
        ).fetchone()
    return _thanh_tom_tat(dong)


def xoa_ho_so(user_id: int, ho_so_id: int) -> None:
    with ket_noi() as conn:
        cur = conn.execute(
            "DELETE FROM dossiers WHERE id = ? AND user_id = ?", (ho_so_id, user_id)
        )
        if not cur.rowcount:
            raise LoiTaiKhoan("Không tìm thấy hồ sơ đã lưu.", 404)


# ------------------------------------------------------------------ tổng quan


def tong_quan(user_id: int) -> TongQuanDuLieu:
    with ket_noi() as conn:
        so_ho_so = int(
            conn.execute("SELECT COUNT(*) AS n FROM dossiers WHERE user_id = ?", (user_id,)).fetchone()["n"]
        )
        byte_ho_so = int(
            conn.execute(
                "SELECT COALESCE(SUM(LENGTH(noi_dung)), 0) AS n FROM dossiers WHERE user_id = ?", (user_id,)
            ).fetchone()["n"]
        )
        ws = conn.execute("SELECT cap_nhat, LENGTH(noi_dung) AS n FROM workspaces WHERE user_id = ?", (user_id,)).fetchone()

    return TongQuanDuLieu(
        so_ho_so=so_ho_so,
        co_ban_lam_viec=bool(ws),
        ban_lam_viec_cap_nhat=ws["cap_nhat"] if ws else "",
        so_phien_dang_mo=dem_phien(user_id),
        dung_luong_kb=round((byte_ho_so + (int(ws["n"]) if ws else 0)) / 1024, 1),
    )


def xoa_toan_bo_du_lieu(user_id: int) -> None:
    with ket_noi() as conn:
        conn.execute("DELETE FROM dossiers WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM workspaces WHERE user_id = ?", (user_id,))
