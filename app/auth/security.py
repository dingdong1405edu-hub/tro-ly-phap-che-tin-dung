"""Băm mật khẩu và sinh token phiên — chỉ dùng thư viện chuẩn, không cần cài thêm."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

# PBKDF2-HMAC-SHA256. Số vòng lặp đủ chậm để chống dò mật khẩu, đủ nhanh để
# một lần đăng nhập không cảm nhận được độ trễ trên máy chủ nhỏ của Railway.
THUAT_TOAN = "pbkdf2_sha256"
SO_VONG = 240_000

DO_DAI_MAT_KHAU_TOI_THIEU = 8
DO_DAI_TEN_TOI_THIEU = 3
DO_DAI_TEN_TOI_DA = 32

_TEN_HOP_LE = re.compile(r"^[a-z0-9._-]+$")


# ------------------------------------------------------------------ mật khẩu


def bam_mat_khau(mat_khau: str) -> str:
    """Trả về chuỗi tự mô tả: thuật toán$số vòng$muối$giá trị băm."""
    muoi = secrets.token_bytes(16)
    dan_xuat = hashlib.pbkdf2_hmac("sha256", mat_khau.encode("utf-8"), muoi, SO_VONG)
    return f"{THUAT_TOAN}${SO_VONG}${muoi.hex()}${dan_xuat.hex()}"


def kiem_mat_khau(mat_khau: str, da_bam: str) -> bool:
    """So khớp theo kiểu thời gian hằng số để không lộ thông tin qua thời gian phản hồi."""
    try:
        thuat_toan, so_vong, muoi_hex, bam_hex = da_bam.split("$")
        if thuat_toan != THUAT_TOAN:
            return False
        dan_xuat = hashlib.pbkdf2_hmac(
            "sha256", mat_khau.encode("utf-8"), bytes.fromhex(muoi_hex), int(so_vong)
        )
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(dan_xuat.hex(), bam_hex)


# -------------------------------------------------------------------- token


def token_moi() -> str:
    """Token phiên gửi cho trình duyệt. Chỉ xuất hiện đúng một lần, sau đó chỉ lưu bản băm."""
    return secrets.token_urlsafe(36)


def bam_token(token: str) -> str:
    """Lưu bản băm xuống CSDL: lộ file CSDL cũng không mạo danh được phiên đang mở."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --------------------------------------------------------------- kiểm tra đầu vào


def chuan_hoa_ten(username: str) -> str:
    return (username or "").strip().lower()


def loi_ten_dang_nhap(username: str) -> str:
    """Trả về chuỗi rỗng nếu hợp lệ, ngược lại là thông báo cho người dùng."""
    ten = chuan_hoa_ten(username)
    if len(ten) < DO_DAI_TEN_TOI_THIEU:
        return f"Tên đăng nhập phải có ít nhất {DO_DAI_TEN_TOI_THIEU} ký tự."
    if len(ten) > DO_DAI_TEN_TOI_DA:
        return f"Tên đăng nhập tối đa {DO_DAI_TEN_TOI_DA} ký tự."
    if not _TEN_HOP_LE.match(ten):
        return "Tên đăng nhập chỉ gồm chữ thường không dấu, số và các ký tự . _ -"
    return ""


def loi_mat_khau(mat_khau: str) -> str:
    if len(mat_khau or "") < DO_DAI_MAT_KHAU_TOI_THIEU:
        return f"Mật khẩu phải có ít nhất {DO_DAI_MAT_KHAU_TOI_THIEU} ký tự."
    if mat_khau.strip() != mat_khau:
        return "Mật khẩu không được bắt đầu hoặc kết thúc bằng khoảng trắng."
    return ""
