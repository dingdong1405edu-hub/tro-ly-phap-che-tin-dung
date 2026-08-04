"""Sinh vector ngữ nghĩa cho chunk & câu hỏi.

Hai backend:
  1. ``sentence-transformers`` — chất lượng cao nhất (mặc định nếu cài được).
  2. ``tfidf``  — TF-IDF + hashing trick thuần NumPy, không cần cài thêm gì.
     Đây là backend dự phòng để MVP luôn chạy được trên mọi máy.

Chọn backend qua biến môi trường EMBEDDING_BACKEND = auto | sentence-transformers | tfidf | none
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import numpy as np

from .tokenizer import tokenize

logger = logging.getLogger(__name__)


class BaseEmbedder:
    name: str = "base"
    dim: int = 0
    needs_fit: bool = False

    def fit(self, texts: list[str]) -> None:  # pragma: no cover - mặc định no-op
        return None

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

    def encode_query(self, text: str) -> np.ndarray:
        return self.encode_documents([text])[0]

    def state_dict(self) -> dict[str, Any]:
        return {"name": self.name, "dim": self.dim}

    def load_state_dict(self, state: dict[str, Any]) -> None:
        return None


# ------------------------------------------------------------- TF-IDF thuần


class TfidfHashingEmbedder(BaseEmbedder):
    """TF-IDF trên không gian băm cố định — nhẹ, không phụ thuộc, đủ tốt cho luật."""

    name = "tfidf"
    needs_fit = True

    def __init__(self, dim: int = 4096) -> None:
        self.dim = dim
        self.df = np.zeros(dim, dtype=np.float32)
        self.n_docs = 0

    @staticmethod
    def _hash(token: str, dim: int) -> int:
        h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(h, "little") % dim

    def _term_freq(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for tok in tokenize(text):
            vec[self._hash(tok, self.dim)] += 1.0
        return vec

    def fit(self, texts: list[str]) -> None:
        self.df = np.zeros(self.dim, dtype=np.float32)
        self.n_docs = 0
        for t in texts:
            tf = self._term_freq(t)
            self.df += (tf > 0).astype(np.float32)
            self.n_docs += 1
        logger.info("TF-IDF đã fit trên %d chunk, dim=%d", self.n_docs, self.dim)

    def _idf(self) -> np.ndarray:
        n = max(self.n_docs, 1)
        return np.log((n + 1.0) / (self.df + 1.0)).astype(np.float32) + 1.0

    def _vectorize(self, texts: list[str]) -> np.ndarray:
        idf = self._idf()
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            tf = self._term_freq(t)
            nz = tf > 0
            tf[nz] = 1.0 + np.log(tf[nz])
            v = tf * idf
            norm = float(np.linalg.norm(v))
            if norm > 0:
                v /= norm
            out[i] = v
        return out

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        return self._vectorize(texts)

    def state_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dim": self.dim,
            "n_docs": self.n_docs,
            "df": self.df.tolist(),
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        self.dim = int(state.get("dim", self.dim))
        self.n_docs = int(state.get("n_docs", 0))
        df = state.get("df")
        self.df = np.array(df, dtype=np.float32) if df else np.zeros(self.dim, dtype=np.float32)


# ------------------------------------------------- sentence-transformers


class SentenceTransformerEmbedder(BaseEmbedder):
    name = "sentence-transformers"

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # import trễ

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.dim = int(self.model.get_sentence_embedding_dimension())
        # Họ model E5 yêu cầu tiền tố "query:" / "passage:"
        self._e5 = "e5" in model_name.lower()

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        payload = [f"passage: {t}" for t in texts] if self._e5 else texts
        vecs = self.model.encode(
            payload,
            batch_size=16,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=len(payload) > 200,
        )
        return np.asarray(vecs, dtype=np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        payload = f"query: {text}" if self._e5 else text
        vec = self.model.encode([payload], convert_to_numpy=True, normalize_embeddings=True)
        return np.asarray(vec, dtype=np.float32)[0]

    def state_dict(self) -> dict[str, Any]:
        return {"name": self.name, "dim": self.dim, "model_name": self.model_name}


class NullEmbedder(BaseEmbedder):
    """Tắt vector — chỉ dùng BM25."""

    name = "none"
    dim = 0

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        return np.zeros((len(texts), 0), dtype=np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        return np.zeros((0,), dtype=np.float32)


# ------------------------------------------------------------------ factory


def build_embedder(backend: str, model_name: str) -> BaseEmbedder:
    backend = (backend or "auto").lower().strip()

    if backend == "none":
        return NullEmbedder()

    if backend in {"auto", "sentence-transformers", "st"}:
        try:
            emb = SentenceTransformerEmbedder(model_name)
            logger.info("Dùng embedding sentence-transformers: %s (dim=%d)", model_name, emb.dim)
            return emb
        except Exception as exc:
            if backend != "auto":
                raise RuntimeError(
                    f"Không khởi tạo được sentence-transformers ({exc}). "
                    "Cài bằng: pip install sentence-transformers torch — hoặc đặt EMBEDDING_BACKEND=tfidf"
                ) from exc
            logger.warning("Không dùng được sentence-transformers (%s) → chuyển sang TF-IDF nội bộ.", exc)

    return TfidfHashingEmbedder()


def load_embedder_from_state(state: dict[str, Any], backend: str, model_name: str) -> BaseEmbedder:
    """Khôi phục embedder khớp với chỉ mục đã lưu (tránh lệch số chiều)."""
    saved = (state or {}).get("name")
    if saved == "tfidf":
        emb = TfidfHashingEmbedder(dim=int(state.get("dim", 4096)))
        emb.load_state_dict(state)
        return emb
    if saved == "sentence-transformers":
        try:
            return SentenceTransformerEmbedder(state.get("model_name") or model_name)
        except Exception as exc:
            logger.warning("Chỉ mục cũ dùng sentence-transformers nhưng không load được (%s).", exc)
            return TfidfHashingEmbedder()
    if saved == "none":
        return NullEmbedder()
    return build_embedder(backend, model_name)


def cosine_scores(matrix: np.ndarray, query_vec: np.ndarray) -> np.ndarray:
    """matrix và query_vec đều đã chuẩn hoá L2 → tích vô hướng = cosine."""
    if matrix.size == 0 or query_vec.size == 0:
        return np.zeros((matrix.shape[0],), dtype=np.float32)
    return matrix @ query_vec.astype(np.float32)
