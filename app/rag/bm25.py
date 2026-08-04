"""BM25 (Okapi) thuần NumPy — tìm kiếm theo từ khoá, bù cho điểm yếu của vector.

Với văn bản luật, người dùng hay gõ đúng thuật ngữ ("tài sản bảo đảm",
"Điều 7", "hạn mức tín dụng") nên BM25 thường chính xác hơn cả embedding.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from .tokenizer import tokenize

K1 = 1.5
B = 0.75


class BM25Index:
    def __init__(self) -> None:
        self.inverted: dict[str, list[tuple[int, int]]] = {}
        self.doc_len = np.zeros(0, dtype=np.float32)
        self.avgdl = 1.0
        self.n_docs = 0
        self.idf: dict[str, float] = {}

    def build(self, texts: list[str]) -> None:
        self.n_docs = len(texts)
        inverted: dict[str, list[tuple[int, int]]] = defaultdict(list)
        doc_len = np.zeros(self.n_docs, dtype=np.float32)

        for i, text in enumerate(texts):
            tokens = tokenize(text)
            doc_len[i] = len(tokens) or 1
            tf: dict[str, int] = defaultdict(int)
            for t in tokens:
                tf[t] += 1
            for t, c in tf.items():
                inverted[t].append((i, c))

        self.inverted = dict(inverted)
        self.doc_len = doc_len
        self.avgdl = float(doc_len.mean()) if self.n_docs else 1.0
        self.idf = {
            term: float(np.log(1.0 + (self.n_docs - len(post) + 0.5) / (len(post) + 0.5)))
            for term, post in self.inverted.items()
        }

    def search(self, query: str, top_k: int = 30) -> list[tuple[int, float]]:
        if not self.n_docs:
            return []

        scores = np.zeros(self.n_docs, dtype=np.float32)
        norm = K1 * (1.0 - B + B * self.doc_len / max(self.avgdl, 1e-6))

        seen: set[str] = set()
        for term in tokenize(query):
            if term in seen:
                continue
            seen.add(term)
            postings = self.inverted.get(term)
            if not postings:
                continue
            idf = self.idf.get(term, 0.0)
            idx = np.fromiter((p[0] for p in postings), dtype=np.int64, count=len(postings))
            tf = np.fromiter((p[1] for p in postings), dtype=np.float32, count=len(postings))
            scores[idx] += idf * (tf * (K1 + 1.0)) / (tf + norm[idx])

        k = min(top_k, self.n_docs)
        if k <= 0:
            return []
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(int(i), float(scores[i])) for i in top if scores[i] > 0]
