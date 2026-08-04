"""Bọc Groq SDK: gọi chat thường, chat streaming và chat trả về JSON."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any, Iterator

from ..config import settings

logger = logging.getLogger(__name__)

_client = None
_client_lock = threading.Lock()

MISSING_KEY_MSG = (
    "Chưa cấu hình GROQ_API_KEY. Hãy tạo file .env ở thư mục gốc dự án với nội dung:\n"
    "GROQ_API_KEY=gsk_...\n"
    "Lấy key miễn phí tại https://console.groq.com/keys"
)


def get_client():
    global _client
    with _client_lock:
        if _client is None:
            if not settings.groq_api_key:
                raise RuntimeError(MISSING_KEY_MSG)
            from groq import Groq

            _client = Groq(api_key=settings.groq_api_key, timeout=120.0, max_retries=0)
        return _client


def has_api_key() -> bool:
    return bool(settings.groq_api_key)


def _dump(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"role": m["role"], "content": m["content"]} for m in messages]


def _call_with_retry(fn, *, retries: int = 3):
    """Thử lại khi bị rate limit (429) hoặc lỗi tạm thời của nhà cung cấp."""
    delay = 1.5
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:  # groq.RateLimitError, APIStatusError...
            last = exc
            status = getattr(exc, "status_code", None)
            retryable = status in (408, 409, 429, 500, 502, 503, 529)
            if not retryable or attempt == retries - 1:
                raise
            logger.warning("Groq lỗi %s, thử lại sau %.1fs (lần %d)", status, delay, attempt + 1)
            time.sleep(delay)
            delay *= 2
    if last:
        raise last


def chat(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    client = get_client()
    resp = _call_with_retry(
        lambda: client.chat.completions.create(
            model=model or settings.groq_model,
            messages=_dump(messages),
            temperature=settings.temperature if temperature is None else temperature,
            max_tokens=max_tokens or settings.max_tokens,
        )
    )
    return (resp.choices[0].message.content or "").strip()


def chat_stream(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Iterator[str]:
    client = get_client()
    stream = _call_with_retry(
        lambda: client.chat.completions.create(
            model=model or settings.groq_model,
            messages=_dump(messages),
            temperature=settings.temperature if temperature is None else temperature,
            max_tokens=max_tokens or settings.max_tokens,
            stream=True,
        )
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        piece = getattr(delta, "content", None)
        if piece:
            yield piece


def _extract_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def chat_json(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Ép model trả về JSON hợp lệ (dùng json_object mode của Groq)."""
    client = get_client()

    def _run(use_json_mode: bool):
        kwargs: dict[str, Any] = {
            "model": model or settings.groq_model,
            "messages": _dump(messages),
            "temperature": temperature,
            "max_tokens": max_tokens or max(settings.max_tokens, 4096),
        }
        if use_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return client.chat.completions.create(**kwargs)

    try:
        resp = _call_with_retry(lambda: _run(True))
    except Exception as exc:
        logger.warning("json_object mode lỗi (%s) — thử lại ở chế độ thường.", exc)
        resp = _call_with_retry(lambda: _run(False))

    return _extract_json(resp.choices[0].message.content or "{}")


def list_models() -> list[str]:
    """Danh sách model đang khả dụng trên tài khoản Groq."""
    try:
        client = get_client()
        data = client.models.list()
        ids = [m.id for m in data.data if getattr(m, "active", True)]
        # Ưu tiên model chat, bỏ whisper/tts
        chat_ids = [i for i in ids if not re.search(r"whisper|tts|guard|embed", i, re.IGNORECASE)]
        return sorted(chat_ids or ids)
    except Exception as exc:
        logger.warning("Không lấy được danh sách model: %s", exc)
        return [settings.groq_model, settings.groq_fast_model]
