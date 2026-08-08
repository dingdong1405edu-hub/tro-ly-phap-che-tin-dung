"""CSDL SQLite: tài khoản, phiên đăng nhập và dữ liệu riêng của từng người dùng.

File nằm trong thư mục data/ — trên Railway thư mục này là volume gắn tại
/app/data nên dữ liệu vẫn còn sau mỗi lần deploy lại.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

from ..config import settings

logger = logging.getLogger(__name__)

_khoa_khoi_tao = threading.Lock()
_da_khoi_tao = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    email         TEXT    NOT NULL DEFAULT '',
    ho_ten        TEXT    NOT NULL DEFAULT '',
    password_hash TEXT    NOT NULL,
    vai_tro       TEXT    NOT NULL DEFAULT 'user',
    kich_hoat     INTEGER NOT NULL DEFAULT 1,
    tao_luc       TEXT    NOT NULL,
    dang_nhap_luc TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tao_luc    TEXT NOT NULL,
    het_han    TEXT NOT NULL,
    thiet_bi   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_het_han ON sessions(het_han);

-- Bàn làm việc: toàn bộ nội dung đang nhập dở của một tài khoản, đồng bộ giữa các máy.
CREATE TABLE IF NOT EXISTS workspaces (
    user_id  INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    noi_dung TEXT NOT NULL,
    cap_nhat TEXT NOT NULL
);

-- Hồ sơ người dùng chủ động bấm lưu, giữ lại nhiều bản.
CREATE TABLE IF NOT EXISTS dossiers (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tieu_de   TEXT NOT NULL DEFAULT '',
    ten_khach TEXT NOT NULL DEFAULT '',
    so_tien   TEXT NOT NULL DEFAULT '',
    diem      INTEGER NOT NULL DEFAULT 0,
    noi_dung  TEXT NOT NULL,
    tao_luc   TEXT NOT NULL,
    cap_nhat  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dossiers_user ON dossiers(user_id, cap_nhat DESC);
"""


def bay_gio() -> str:
    """Mốc thời gian ISO 8601 theo UTC — so sánh chuỗi cũng ra đúng thứ tự."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sau_nay(so_ngay: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=so_ngay)).isoformat(timespec="seconds")


def _khoi_tao(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    conn.commit()


def dam_bao_schema() -> None:
    global _da_khoi_tao
    if _da_khoi_tao:
        return
    with _khoa_khoi_tao:
        if _da_khoi_tao:
            return
        settings.ensure_dirs()
        conn = sqlite3.connect(str(settings.db_path), timeout=20.0)
        try:
            _khoi_tao(conn)
            logger.info("CSDL tài khoản sẵn sàng: %s", settings.db_path)
        finally:
            conn.close()
        _da_khoi_tao = True


@contextmanager
def ket_noi() -> Iterator[sqlite3.Connection]:
    """Mỗi thao tác một kết nối riêng — an toàn khi FastAPI chạy nhiều luồng."""
    dam_bao_schema()
    conn = sqlite3.connect(str(settings.db_path), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
