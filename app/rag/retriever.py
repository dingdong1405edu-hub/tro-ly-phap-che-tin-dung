"""Truy hồi lai: BM25 + vector ngữ nghĩa, hợp nhất bằng RRF, cộng điểm ưu tiên
khi câu hỏi trỏ đích danh "Điều X" hoặc số hiệu văn bản.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .chunker import Chunk
from .store import VectorStore
from .tokenizer import strip_accents

RRF_K = 60.0

RE_Q_DIEU = re.compile(r"đi[eề]u\s+(\d+[a-zA-Z]?)", re.IGNORECASE)
RE_Q_KHOAN = re.compile(r"kho[aả]n\s+(\d+)", re.IGNORECASE)
RE_Q_SOHIEU = re.compile(r"(\d{1,4}\s*/\s*\d{4}\s*/\s*[A-Za-zĐđ][A-Za-zĐđ\-]{1,20})")


@dataclass
class Hit:
    chunk: Chunk
    score: float
    dense_rank: int | None = None
    bm25_rank: int | None = None
    boost: float = 0.0


def _targeted_boost(query: str, chunk: Chunk) -> float:
    """Ưu tiên chunk khớp đích danh Điều / số hiệu văn bản được nhắc trong câu hỏi."""
    boost = 0.0

    dieu_refs = {m.group(1).lower() for m in RE_Q_DIEU.finditer(query)}
    if dieu_refs and chunk.dieu and chunk.dieu.lower() in dieu_refs:
        boost += 0.35

    for m in RE_Q_SOHIEU.finditer(query):
        so = re.sub(r"\s+", "", m.group(1)).upper()
        if chunk.so_hieu and so in chunk.so_hieu.upper():
            boost += 0.25

    # Khớp thuật ngữ trong tiêu đề Điều thường rất "đúng ý"
    if chunk.dieu_title:
        title_tokens = set(strip_accents(chunk.dieu_title).split())
        q_tokens = set(strip_accents(query).split())
        common = title_tokens & q_tokens
        if len(common) >= 2:
            boost += min(0.05 * len(common), 0.2)

    return boost


class Retriever:
    def __init__(self, store: VectorStore, top_k: int = 6, candidate_k: int = 30) -> None:
        self.store = store
        self.top_k = top_k
        self.candidate_k = candidate_k

    def search(self, query: str, top_k: int | None = None, candidate_k: int | None = None) -> list[Hit]:
        top_k = top_k or self.top_k
        candidate_k = candidate_k or max(self.candidate_k, top_k * 4)
        if not self.store.chunks or not query.strip():
            return []

        dense = self.store.dense_search(query, candidate_k)
        sparse = self.store.bm25_search(query, candidate_k)

        # Reciprocal Rank Fusion
        fused: dict[int, float] = {}
        dense_rank: dict[int, int] = {}
        bm25_rank: dict[int, int] = {}

        for rank, (idx, _score) in enumerate(dense):
            dense_rank[idx] = rank + 1
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
        for rank, (idx, _score) in enumerate(sparse):
            bm25_rank[idx] = rank + 1
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)

        hits: list[Hit] = []
        for idx, base in fused.items():
            chunk = self.store.get(idx)
            boost = _targeted_boost(query, chunk)
            hits.append(
                Hit(
                    chunk=chunk,
                    score=base * 100.0 + boost,
                    dense_rank=dense_rank.get(idx),
                    bm25_rank=bm25_rank.get(idx),
                    boost=boost,
                )
            )

        hits.sort(key=lambda h: h.score, reverse=True)
        return self._diversify(hits, top_k)

    @staticmethod
    def _diversify(hits: list[Hit], top_k: int) -> list[Hit]:
        """Hạn chế lấy quá nhiều chunk từ cùng một Điều/văn bản để câu trả lời đa nguồn."""
        picked: list[Hit] = []
        per_doc: dict[str, int] = {}
        seen_dieu: set[tuple[str, str]] = set()
        max_per_doc = max(2, top_k // 2 + 1)

        for h in hits:
            key = (h.chunk.doc_id, h.chunk.dieu)
            if h.chunk.dieu and key in seen_dieu:
                continue
            if per_doc.get(h.chunk.doc_id, 0) >= max_per_doc:
                continue
            picked.append(h)
            per_doc[h.chunk.doc_id] = per_doc.get(h.chunk.doc_id, 0) + 1
            if h.chunk.dieu:
                seen_dieu.add(key)
            if len(picked) >= top_k:
                break

        if len(picked) < top_k:  # bù thêm nếu lọc quá tay
            chosen = {id(h) for h in picked}
            for h in hits:
                if id(h) not in chosen:
                    picked.append(h)
                    if len(picked) >= top_k:
                        break
        return picked


def format_context(hits: list[Hit], max_chars: int = 9000) -> str:
    """Ghép các đoạn luật thành khối ngữ cảnh đánh số [1], [2]... cho LLM trích dẫn."""
    parts: list[str] = []
    used = 0
    for i, h in enumerate(hits, start=1):
        c = h.chunk
        head_bits = [f"[{i}]", c.doc_title]
        if c.chuong:
            head_bits.append(c.chuong)
        if c.muc:
            head_bits.append(c.muc)
        if c.dieu:
            head_bits.append(f"Điều {c.dieu}" + (f". {c.dieu_title}" if c.dieu_title else ""))
        block = " | ".join(head_bits) + "\n" + c.body.strip()

        if used + len(block) > max_chars:
            block = block[: max(0, max_chars - used)]
            if block.strip():
                parts.append(block)
            break
        parts.append(block)
        used += len(block)
    return "\n\n---\n\n".join(parts)
