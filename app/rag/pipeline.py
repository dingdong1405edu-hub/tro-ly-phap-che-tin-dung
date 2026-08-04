"""Điều phối RAG: khởi tạo kho, nạp file luật, cung cấp retriever dùng chung."""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path

from ..config import settings
from ..schemas import DocumentInfo, IngestResult
from .chunker import chunk_document, extract_doc_meta, iter_supported_files
from .embedder import build_embedder
from .loader import load_document
from .retriever import Retriever
from .store import VectorStore

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_store: VectorStore | None = None
_retriever: Retriever | None = None


def get_store() -> VectorStore:
    global _store
    with _lock:
        if _store is None:
            embedder = build_embedder(settings.embedding_backend, settings.embedding_model)
            _store = VectorStore(settings.index_dir, embedder)
            _store.load(settings.embedding_backend, settings.embedding_model)
        return _store


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever(get_store(), top_k=settings.top_k, candidate_k=settings.candidate_k)
    return _retriever


# ------------------------------------------------------------------ nạp file


def ingest_file(path: Path, store: VectorStore | None = None, reindex: bool = True) -> tuple[DocumentInfo, list[str]]:
    """Nạp 1 file luật vào chỉ mục. Trả về thông tin văn bản + cảnh báo (nếu có)."""
    store = store or get_store()
    loaded = load_document(path)
    if not loaded.text.strip():
        raise RuntimeError(f"Không bóc tách được nội dung từ {path.name}")

    meta = extract_doc_meta(loaded.text, path.name)
    meta, chunks = chunk_document(
        loaded.text,
        path.name,
        max_chars=settings.chunk_max_chars,
        overlap=settings.chunk_overlap,
        meta=meta,
    )
    if not chunks:
        raise RuntimeError(f"Không tạo được chunk nào từ {path.name}")

    store.add_document(meta, chunks, reindex=reindex)
    info = DocumentInfo(
        doc_id=meta.doc_id,
        doc_title=meta.doc_title,
        file_name=meta.file_name,
        so_hieu=meta.so_hieu,
        loai_van_ban=meta.loai_van_ban,
        n_chunks=len(chunks),
        n_chars=meta.n_chars,
        ingested_at=store.documents.get(meta.doc_id, {}).get("ingested_at", ""),
    )
    return info, loaded.warnings


def ingest_directory(directory: Path | None = None, rebuild: bool = False) -> IngestResult:
    """Nạp toàn bộ file trong thư mục data/raw_laws."""
    directory = Path(directory or settings.raw_dir)
    store = get_store()
    if rebuild:
        store.clear()

    files = iter_supported_files(directory.iterdir()) if directory.exists() else []
    result = IngestResult(ok=True)

    for f in files:
        try:
            info, warns = ingest_file(f, store=store, reindex=False)
            result.documents.append(info)
            result.warnings.extend(f"{f.name}: {w}" for w in warns)
            logger.info("Đã nạp %s (%d chunk)", f.name, info.n_chunks)
        except Exception as exc:
            result.skipped.append(f"{f.name}: {exc}")
            logger.exception("Lỗi khi nạp %s", f.name)

    store.reindex()
    result.total_chunks = len(store.chunks)
    result.ok = bool(result.documents) or not files
    return result


def save_upload(file_name: str, content: bytes) -> Path:
    """Lưu file người dùng tải lên vào data/raw_laws (tự đổi tên nếu trùng)."""
    safe = Path(file_name).name.replace("\\", "_").replace("/", "_")
    dest = settings.raw_dir / safe
    if dest.exists():
        dest.unlink()  # ghi đè để doc_id (hash theo tên file) không bị nhân bản
    dest.write_bytes(content)
    return dest


def delete_document(doc_id: str, delete_file: bool = True) -> bool:
    store = get_store()
    info = store.documents.get(doc_id)
    ok = store.remove_document(doc_id)
    if ok and delete_file and info:
        f = settings.raw_dir / info.get("file_name", "")
        if f.exists() and f.is_file():
            try:
                f.unlink()
            except OSError as exc:
                logger.warning("Không xoá được file %s: %s", f, exc)
    return ok


def reset_index() -> None:
    store = get_store()
    store.clear()


def purge_all(delete_files: bool = False) -> None:
    reset_index()
    if delete_files and settings.raw_dir.exists():
        for f in settings.raw_dir.iterdir():
            if f.is_file():
                f.unlink()
        shutil.rmtree(settings.index_dir, ignore_errors=True)
        settings.ensure_dirs()
