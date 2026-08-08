"""Cấu hình tập trung cho toàn hệ thống, đọc từ biến môi trường / file .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Groq ---
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_fast_model: str = "llama-3.1-8b-instant"
    temperature: float = 0.15
    max_tokens: int = 2048

    # --- RAG ---
    embedding_backend: str = "auto"  # auto | sentence-transformers | tfidf | none
    embedding_model: str = "intfloat/multilingual-e5-small"
    chunk_max_chars: int = 1600
    chunk_overlap: int = 200
    top_k: int = 6
    candidate_k: int = 30

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000

    # --- Tài khoản & phiên đăng nhập ---
    session_ttl_days: int = 30
    allow_registration: bool = True
    # Cookie phiên: auto = chỉ bật cờ Secure khi đang chạy trên HTTPS.
    cookie_secure: str = "auto"
    # Tạo sẵn tài khoản quản trị khi CSDL còn trống (bỏ trống thì người đăng ký
    # đầu tiên sẽ tự trở thành quản trị viên).
    admin_username: str = "admin"
    admin_password: str = ""
    admin_email: str = ""

    # --- Đường dẫn ---
    @property
    def data_dir(self) -> Path:
        return ROOT_DIR / "data"

    @property
    def db_path(self) -> Path:
        """CSDL tài khoản + dữ liệu người dùng. Nằm trong data/ nên đi theo volume."""
        return self.data_dir / "app.db"

    @property
    def raw_dir(self) -> Path:
        """Nơi lưu file luật gốc do người dùng tải lên."""
        return self.data_dir / "raw_laws"

    @property
    def index_dir(self) -> Path:
        """Nơi lưu chỉ mục vector + metadata."""
        return self.data_dir / "index"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def frontend_dir(self) -> Path:
        return ROOT_DIR / "frontend"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.raw_dir, self.index_dir, self.export_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
