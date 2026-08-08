"""Nghiệp vụ tài khoản: đăng ký, đăng nhập, phiên làm việc, quản trị người dùng."""

from __future__ import annotations

import logging
import sqlite3

from ..config import settings
from . import security
from .db import bay_gio, ket_noi, sau_nay
from .models import NguoiDung

logger = logging.getLogger(__name__)

VAI_TRO_HOP_LE = ("admin", "user")


class LoiTaiKhoan(Exception):
    """Lỗi nghiệp vụ có thông điệp hiển thị thẳng cho người dùng."""

    def __init__(self, thong_diep: str, ma: int = 400) -> None:
        super().__init__(thong_diep)
        self.thong_diep = thong_diep
        self.ma = ma


def _thanh_nguoi_dung(dong: sqlite3.Row) -> NguoiDung:
    return NguoiDung(
        id=dong["id"],
        username=dong["username"],
        email=dong["email"],
        ho_ten=dong["ho_ten"],
        vai_tro=dong["vai_tro"],
        kich_hoat=bool(dong["kich_hoat"]),
        tao_luc=dong["tao_luc"],
        dang_nhap_luc=dong["dang_nhap_luc"],
    )


# ------------------------------------------------------------------ truy vấn


def dem_nguoi_dung() -> int:
    with ket_noi() as conn:
        return int(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])


def tim_theo_id(user_id: int) -> NguoiDung | None:
    with ket_noi() as conn:
        dong = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _thanh_nguoi_dung(dong) if dong else None


def danh_sach_nguoi_dung() -> list[NguoiDung]:
    with ket_noi() as conn:
        dongs = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [_thanh_nguoi_dung(d) for d in dongs]


# ------------------------------------------------------------------- đăng ký


def tao_nguoi_dung(
    username: str,
    password: str,
    ho_ten: str = "",
    email: str = "",
    vai_tro: str = "user",
) -> NguoiDung:
    ten = security.chuan_hoa_ten(username)
    loi = security.loi_ten_dang_nhap(ten)
    if loi:
        raise LoiTaiKhoan(loi)
    loi = security.loi_mat_khau(password)
    if loi:
        raise LoiTaiKhoan(loi)
    if vai_tro not in VAI_TRO_HOP_LE:
        vai_tro = "user"

    with ket_noi() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (username, email, ho_ten, password_hash, vai_tro, kich_hoat, tao_luc)"
                " VALUES (?, ?, ?, ?, ?, 1, ?)",
                (
                    ten,
                    (email or "").strip(),
                    (ho_ten or "").strip(),
                    security.bam_mat_khau(password),
                    vai_tro,
                    bay_gio(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise LoiTaiKhoan("Tên đăng nhập này đã có người dùng.", 409) from exc
        dong = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()

    logger.info("Đã tạo tài khoản %s (vai trò %s)", ten, vai_tro)
    return _thanh_nguoi_dung(dong)


def dang_ky(username: str, password: str, ho_ten: str = "", email: str = "") -> NguoiDung:
    """Người đầu tiên đăng ký trở thành quản trị viên; sau đó theo cấu hình ALLOW_REGISTRATION."""
    chua_co_ai = dem_nguoi_dung() == 0
    if not chua_co_ai and not settings.allow_registration:
        raise LoiTaiKhoan("Hệ thống đang tắt chức năng tự đăng ký. Liên hệ quản trị viên để được cấp tài khoản.", 403)
    return tao_nguoi_dung(username, password, ho_ten, email, vai_tro="admin" if chua_co_ai else "user")


def bootstrap_admin() -> None:
    """Tạo sẵn tài khoản quản trị từ biến môi trường khi CSDL còn trống."""
    if not settings.admin_password:
        return
    if dem_nguoi_dung() > 0:
        return
    try:
        tao_nguoi_dung(
            settings.admin_username,
            settings.admin_password,
            ho_ten="Quản trị hệ thống",
            email=settings.admin_email,
            vai_tro="admin",
        )
        logger.info("Đã tạo tài khoản quản trị mặc định: %s", settings.admin_username)
    except LoiTaiKhoan as exc:
        logger.warning("Không tạo được tài khoản quản trị mặc định: %s", exc.thong_diep)


# ----------------------------------------------------------------- đăng nhập


def xac_thuc(username: str, password: str) -> NguoiDung:
    ten = security.chuan_hoa_ten(username)
    with ket_noi() as conn:
        dong = conn.execute("SELECT * FROM users WHERE username = ?", (ten,)).fetchone()

    # Vẫn băm một lần khi không tìm thấy tài khoản, để thời gian phản hồi
    # không tiết lộ tên đăng nhập nào có thật.
    bam = dong["password_hash"] if dong else security.bam_mat_khau("khong-ton-tai")
    hop_le = security.kiem_mat_khau(password or "", bam)

    if not dong or not hop_le:
        raise LoiTaiKhoan("Sai tên đăng nhập hoặc mật khẩu.", 401)
    if not dong["kich_hoat"]:
        raise LoiTaiKhoan("Tài khoản đã bị khoá. Liên hệ quản trị viên.", 403)
    return _thanh_nguoi_dung(dong)


def tao_phien(user_id: int, thiet_bi: str = "", so_ngay: int | None = None) -> tuple[str, str]:
    """Sinh token mới, lưu bản băm. Trả về (token gốc, thời điểm hết hạn)."""
    token = security.token_moi()
    het_han = sau_nay(so_ngay if so_ngay is not None else settings.session_ttl_days)
    with ket_noi() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, tao_luc, het_han, thiet_bi) VALUES (?, ?, ?, ?, ?)",
            (security.bam_token(token), user_id, bay_gio(), het_han, (thiet_bi or "")[:200]),
        )
        conn.execute("UPDATE users SET dang_nhap_luc = ? WHERE id = ?", (bay_gio(), user_id))
        conn.execute("DELETE FROM sessions WHERE het_han < ?", (bay_gio(),))
    return token, het_han


def nguoi_dung_theo_token(token: str) -> NguoiDung | None:
    if not token:
        return None
    with ket_noi() as conn:
        dong = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id"
            " WHERE s.token_hash = ? AND s.het_han > ?",
            (security.bam_token(token), bay_gio()),
        ).fetchone()
    if not dong or not dong["kich_hoat"]:
        return None
    return _thanh_nguoi_dung(dong)


def xoa_phien(token: str) -> None:
    if not token:
        return
    with ket_noi() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (security.bam_token(token),))


def xoa_moi_phien(user_id: int, tru_token: str = "") -> int:
    with ket_noi() as conn:
        if tru_token:
            cur = conn.execute(
                "DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?",
                (user_id, security.bam_token(tru_token)),
            )
        else:
            cur = conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        return cur.rowcount


def dem_phien(user_id: int) -> int:
    with ket_noi() as conn:
        dong = conn.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE user_id = ? AND het_han > ?",
            (user_id, bay_gio()),
        ).fetchone()
    return int(dong["n"])


# ------------------------------------------------------------ đổi thông tin


def doi_mat_khau(user_id: int, mat_khau_cu: str, mat_khau_moi: str) -> None:
    loi = security.loi_mat_khau(mat_khau_moi)
    if loi:
        raise LoiTaiKhoan(loi)

    with ket_noi() as conn:
        dong = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if not dong or not security.kiem_mat_khau(mat_khau_cu or "", dong["password_hash"]):
            raise LoiTaiKhoan("Mật khẩu hiện tại không đúng.", 401)
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (security.bam_mat_khau(mat_khau_moi), user_id),
        )


def cap_nhat_ho_so(user_id: int, ho_ten: str, email: str) -> NguoiDung:
    with ket_noi() as conn:
        conn.execute(
            "UPDATE users SET ho_ten = ?, email = ? WHERE id = ?",
            ((ho_ten or "").strip()[:120], (email or "").strip()[:160], user_id),
        )
        dong = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not dong:
        raise LoiTaiKhoan("Không tìm thấy tài khoản.", 404)
    return _thanh_nguoi_dung(dong)


# -------------------------------------------------------------- quản trị viên


def _dem_admin_dang_hoat_dong(conn: sqlite3.Connection, tru_id: int | None = None) -> int:
    if tru_id is None:
        dong = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE vai_tro = 'admin' AND kich_hoat = 1"
        ).fetchone()
    else:
        dong = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE vai_tro = 'admin' AND kich_hoat = 1 AND id <> ?",
            (tru_id,),
        ).fetchone()
    return int(dong["n"])


def cap_nhat_nguoi_dung(user_id: int, vai_tro: str | None, kich_hoat: bool | None) -> NguoiDung:
    """Đổi vai trò / khoá tài khoản. Luôn giữ lại ít nhất một quản trị viên đang hoạt động."""
    with ket_noi() as conn:
        dong = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not dong:
            raise LoiTaiKhoan("Không tìm thấy tài khoản.", 404)

        vai_tro_moi = dong["vai_tro"] if vai_tro is None else vai_tro
        if vai_tro_moi not in VAI_TRO_HOP_LE:
            raise LoiTaiKhoan("Vai trò không hợp lệ.")
        kich_hoat_moi = bool(dong["kich_hoat"]) if kich_hoat is None else bool(kich_hoat)

        con_la_admin = vai_tro_moi == "admin" and kich_hoat_moi
        if not con_la_admin and _dem_admin_dang_hoat_dong(conn, tru_id=user_id) == 0:
            raise LoiTaiKhoan("Phải còn ít nhất một quản trị viên đang hoạt động.", 409)

        conn.execute(
            "UPDATE users SET vai_tro = ?, kich_hoat = ? WHERE id = ?",
            (vai_tro_moi, 1 if kich_hoat_moi else 0, user_id),
        )
        if not kich_hoat_moi:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        dong = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _thanh_nguoi_dung(dong)


def dat_lai_mat_khau(user_id: int, mat_khau_moi: str) -> None:
    loi = security.loi_mat_khau(mat_khau_moi)
    if loi:
        raise LoiTaiKhoan(loi)
    with ket_noi() as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (security.bam_mat_khau(mat_khau_moi), user_id),
        )
        if not cur.rowcount:
            raise LoiTaiKhoan("Không tìm thấy tài khoản.", 404)
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def xoa_nguoi_dung(user_id: int) -> None:
    """Xoá tài khoản kèm toàn bộ phiên và dữ liệu riêng (ràng buộc ON DELETE CASCADE)."""
    with ket_noi() as conn:
        dong = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not dong:
            raise LoiTaiKhoan("Không tìm thấy tài khoản.", 404)
        if _dem_admin_dang_hoat_dong(conn, tru_id=user_id) == 0:
            raise LoiTaiKhoan("Phải còn ít nhất một quản trị viên đang hoạt động.", 409)
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
