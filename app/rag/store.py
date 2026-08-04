"""Kho lưu chunk + vector, lưu trên đĩa dạng JSON + NPY (không cần DB ngoài)."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from .bm25 import BM25Index
from .chunker import Chunk, DocMeta
from .embedder import BaseEmbedder, cosine_scores, load_embedder_from_state

logger = logging.getLogger(__name__)

CHUNKS_FILE = "chunks.json"
VECTORS_FILE = "vectors.npy"
DOCS_FILE = "documents.json"
EMBEDDER_FILE = "embedder.json"


class VectorStore:
    """Kho chỉ mục trong RAM, có persist ra đĩa. An toàn với nhiều luồng."""

    def __init__(self, index_dir: Path, embedder: BaseEmbedder) -> None:
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.chunks: list[Chunk] = []
        self.vectors: np.ndarray = np.zeros((0, 0), dtype=np.float32)
        # id của từng dòng trong self.vectors — luôn đồng bộ với self.vectors
        self._vec_ids: list[str] = []
        self.documents: dict[str, dict[str, Any]] = {}
        self.bm25 = BM25Index()
        self._lock = threading.RLock()

    # ------------------------------------------------------------- I/O

    @property
    def _p_chunks(self) -> Path:
        return self.index_dir / CHUNKS_FILE

    @property
    def _p_vectors(self) -> Path:
        return self.index_dir / VECTORS_FILE

    @property
    def _p_docs(self) -> Path:
        return self.index_dir / DOCS_FILE

    @property
    def _p_embedder(self) -> Path:
        return self.index_dir / EMBEDDER_FILE

    def load(self, backend: str = "auto", model_name: str = "") -> None:
        with self._lock:
            if self._p_embedder.exists():
                state = json.loads(self._p_embedder.read_text(encoding="utf-8"))
                self.embedder = load_embedder_from_state(state, backend, model_name)

            if self._p_chunks.exists():
                raw = json.loads(self._p_chunks.read_text(encoding="utf-8"))
                self.chunks = [Chunk.from_dict(d) for d in raw]
            if self._p_docs.exists():
                self.documents = json.loads(self._p_docs.read_text(encoding="utf-8"))
            if self._p_vectors.exists():
                self.vectors = np.load(self._p_vectors)
            else:
                self.vectors = np.zeros((len(self.chunks), self.embedder.dim), dtype=np.float32)
            self._vec_ids = [c.chunk_id for c in self.chunks]

            if self.vectors.shape[0] != len(self.chunks):
                logger.warning("Vector và chunk lệch nhau — sẽ tính lại vector.")
                self._reencode_all()

            self._rebuild_bm25()
            logger.info("Đã nạp chỉ mục: %d chunk / %d văn bản", len(self.chunks), len(self.documents))

    def save(self) -> None:
        with self._lock:
            self._p_chunks.write_text(
                json.dumps([c.to_dict() for c in self.chunks], ensure_ascii=False),
                encoding="utf-8",
            )
            self._p_docs.write_text(json.dumps(self.documents, ensure_ascii=False, indent=2), encoding="utf-8")
            self._p_embedder.write_text(
                json.dumps(self.embedder.state_dict(), ensure_ascii=False), encoding="utf-8"
            )
            np.save(self._p_vectors, self.vectors)

    # --------------------------------------------------------- cập nhật

    def _rebuild_bm25(self) -> None:
        self.bm25.build([c.text for c in self.chunks])

    def _reencode_all(self) -> None:
        texts = [c.text for c in self.chunks]
        if not texts:
            self.vectors = np.zeros((0, max(self.embedder.dim, 1)), dtype=np.float32)
            self._vec_ids = []
            return

        if self.embedder.needs_fit:
            # TF-IDF: IDF phụ thuộc toàn corpus nên buộc phải tính lại tất cả (rất nhanh).
            self.embedder.fit(texts)
            self.vectors = self.embedder.encode_documents(texts)
        else:
            # Model neural: chỉ encode chunk mới, tái sử dụng vector đã có.
            cache: dict[str, np.ndarray] = {}
            if self.vectors.shape[0] == len(self._vec_ids):
                cache = {cid: self.vectors[i] for i, cid in enumerate(self._vec_ids)}

            todo = [(i, c) for i, c in enumerate(self.chunks) if c.chunk_id not in cache]
            new_vecs = (
                self.embedder.encode_documents([c.text for _, c in todo])
                if todo
                else np.zeros((0, self.embedder.dim), dtype=np.float32)
            )
            for slot, (_, c) in enumerate(todo):
                cache[c.chunk_id] = new_vecs[slot]
            self.vectors = np.vstack([cache[c.chunk_id] for c in self.chunks]).astype(np.float32)

        self._vec_ids = [c.chunk_id for c in self.chunks]

    def add_document(self, meta: DocMeta, chunks: list[Chunk], reindex: bool = True) -> None:
        """Thêm/ghi đè một văn bản (cùng doc_id sẽ được thay thế)."""
        with self._lock:
            self.remove_document(meta.doc_id, save=False, rebuild=False)
            self.chunks.extend(chunks)
            self.documents[meta.doc_id] = {
                "doc_id": meta.doc_id,
                "doc_title": meta.doc_title,
                "file_name": meta.file_name,
                "so_hieu": meta.so_hieu,
                "loai_van_ban": meta.loai_van_ban,
                "n_chunks": len(chunks),
                "n_chars": meta.n_chars,
                "ingested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            if reindex:
                self.reindex()

    def remove_document(self, doc_id: str, save: bool = True, rebuild: bool = True) -> bool:
        with self._lock:
            if doc_id not in self.documents and not any(c.doc_id == doc_id for c in self.chunks):
                return False
            keep = [i for i, c in enumerate(self.chunks) if c.doc_id != doc_id]
            if self.vectors.shape[0] == len(self.chunks):
                self.vectors = (
                    self.vectors[keep] if keep else np.zeros((0, self.vectors.shape[1]), dtype=np.float32)
                )
                self._vec_ids = [self._vec_ids[i] for i in keep] if self._vec_ids else []
            self.chunks = [self.chunks[i] for i in keep]
            self.documents.pop(doc_id, None)
            if rebuild:
                self.reindex()
            if save:
                self.save()
            return True

    def reindex(self) -> None:
        """Tính lại toàn bộ vector + BM25 rồi lưu xuống đĩa."""
        with self._lock:
            self._reencode_all()
            self._rebuild_bm25()
            self.save()

    def clear(self) -> None:
        with self._lock:
            self.chunks = []
            self.documents = {}
            self.vectors = np.zeros((0, max(self.embedder.dim, 1)), dtype=np.float32)
            self._vec_ids = []
            self.bm25 = BM25Index()
            self.save()

    # ----------------------------------------------------------- tra cứu

    def dense_search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        with self._lock:
            if not self.chunks or self.vectors.size == 0 or self.embedder.dim == 0:
                return []
            qvec = self.embedder.encode_query(query)
            if qvec.shape[0] != self.vectors.shape[1]:
                logger.warning("Số chiều vector không khớp — bỏ qua tìm kiếm ngữ nghĩa.")
                return []
            scores = cosine_scores(self.vectors, qvec)
            k = min(top_k, len(scores))
            top = np.argpartition(-scores, k - 1)[:k]
            top = top[np.argsort(-scores[top])]
            return [(int(i), float(scores[i])) for i in top]

    def bm25_search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        with self._lock:
            return self.bm25.search(query, top_k)

    def get(self, idx: int) -> Chunk:
        return self.chunks[idx]

    def stats(self) -> dict[str, Any]:
        return {
            "n_documents": len(self.documents),
            "n_chunks": len(self.chunks),
            "embedder": self.embedder.name,
            "dim": self.embedder.dim,
            "index_dir": str(self.index_dir),
        }
