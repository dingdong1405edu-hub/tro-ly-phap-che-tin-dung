"""Luồng hỏi - đáp: viết lại truy vấn -> truy hồi -> dựng prompt -> gọi Groq."""

from __future__ import annotations

import logging
from typing import Iterator

from ..config import settings
from ..llm import groq_client, prompts
from ..rag.pipeline import get_retriever, get_store
from ..rag.retriever import Hit, format_context
from ..schemas import ChatRequest, Message, SourceRef

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 10
EXCERPT_CHARS = 420


def hits_to_sources(hits: list[Hit]) -> list[SourceRef]:
    out: list[SourceRef] = []
    for i, h in enumerate(hits, start=1):
        c = h.chunk
        body = c.body.strip()
        out.append(
            SourceRef(
                id=i,
                chunk_id=c.chunk_id,
                doc_id=c.doc_id,
                doc_title=c.doc_title,
                file_name=c.file_name,
                citation=c.citation,
                chuong=c.chuong,
                muc=c.muc,
                dieu=c.dieu,
                dieu_title=c.dieu_title,
                score=round(h.score, 4),
                excerpt=body[:EXCERPT_CHARS] + ("..." if len(body) > EXCERPT_CHARS else ""),
            )
        )
    return out


def _history_text(messages: list[Message], limit: int = 6) -> str:
    tail = [m for m in messages[:-1] if m.role in ("user", "assistant")][-limit:]
    lines = []
    for m in tail:
        who = "Người dùng" if m.role == "user" else "Trợ lý"
        content = m.content.strip().replace("\n", " ")
        lines.append(f"{who}: {content[:400]}")
    return "\n".join(lines) if lines else "(chưa có)"


def rewrite_query(messages: list[Message]) -> str:
    """Biến câu hỏi phụ thuộc ngữ cảnh thành truy vấn độc lập, giàu thuật ngữ."""
    if not messages:
        return ""
    question = messages[-1].content.strip()
    prior = [m for m in messages[:-1] if m.role in ("user", "assistant")]
    if not prior or len(question) > 400:
        return question

    try:
        rewritten = groq_client.chat(
            [
                {
                    "role": "user",
                    "content": prompts.REWRITE_PROMPT.format(
                        history=_history_text(messages), question=question
                    ),
                }
            ],
            model=settings.groq_fast_model,
            temperature=0.0,
            max_tokens=160,
        )
        rewritten = rewritten.strip().strip('"').split("\n")[0]
        if 3 < len(rewritten) < 500:
            logger.info("Truy vấn viết lại: %s", rewritten)
            # Ghép cả câu gốc để không mất từ khoá người dùng đã gõ
            return f"{rewritten} {question}"
    except Exception as exc:
        logger.warning("Không viết lại được truy vấn (%s) — dùng câu hỏi gốc.", exc)
    return question


def retrieve(query: str, top_k: int | None = None) -> list[Hit]:
    return get_retriever().search(query, top_k=top_k or settings.top_k)


def build_messages(req: ChatRequest) -> tuple[list[dict[str, str]], list[SourceRef], list[Hit]]:
    """Dựng danh sách message gửi Groq kèm nguồn trích dẫn."""
    store = get_store()
    question = req.messages[-1].content.strip() if req.messages else ""
    has_corpus = bool(store.chunks)

    hits: list[Hit] = []
    if req.use_rag and has_corpus and question:
        search_query = rewrite_query(req.messages)
        hits = retrieve(search_query, top_k=req.top_k or settings.top_k)

    if not has_corpus:
        system = prompts.NO_RAG_SYSTEM_PROMPT
        user_block = question
    elif hits:
        system = prompts.SYSTEM_PROMPT
        user_block = prompts.CONTEXT_TEMPLATE.format(context=format_context(hits), question=question)
    else:
        system = prompts.SYSTEM_PROMPT
        user_block = prompts.NO_CONTEXT_TEMPLATE.format(question=question)

    history: list[dict[str, str]] = []
    for m in req.messages[:-1][-MAX_HISTORY_MESSAGES:]:
        if m.role in ("user", "assistant") and m.content.strip():
            history.append({"role": m.role, "content": m.content.strip()[:4000]})

    llm_messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": user_block}]
    return llm_messages, hits_to_sources(hits), hits


def stream_answer(req: ChatRequest) -> Iterator[str]:
    llm_messages, _sources, _hits = build_messages(req)
    yield from groq_client.chat_stream(
        llm_messages,
        model=req.model or settings.groq_model,
        temperature=req.temperature,
    )


def answer(req: ChatRequest) -> tuple[str, list[SourceRef]]:
    llm_messages, sources, _hits = build_messages(req)
    text = groq_client.chat(
        llm_messages,
        model=req.model or settings.groq_model,
        temperature=req.temperature,
    )
    return text, sources
