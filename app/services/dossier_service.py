"""Sinh hồ sơ đề nghị cấp tín dụng (JSON có cấu trúc) từ hội thoại + căn cứ pháp lý."""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from ..config import settings
from ..llm import groq_client, prompts
from ..rag.pipeline import get_store
from ..rag.retriever import format_context
from ..schemas import Dossier, DossierGenerateRequest, Message, SourceRef
from . import chat_service

logger = logging.getLogger(__name__)

DOSSIER_TOP_K = 10

FALLBACK_QUERY = (
    "điều kiện vay vốn hồ sơ đề nghị cấp tín dụng phương án sử dụng vốn khả năng trả nợ "
    "tài sản bảo đảm thẩm định hợp đồng tín dụng giải ngân"
)

# Các khoá của từng list-of-object: dùng khi model trả về list[str] thay vì list[dict]
LIST_PRIMARY_KEY = {
    "tai_san_bao_dam": "ten_tai_san",
    "tinh_hinh_tai_chinh": "chi_tieu",
    "dong_tien_du_kien": "ky",
    "danh_muc_ho_so": "ten_tai_lieu",
    "can_cu_phap_ly": "van_ban",
    "danh_gia_rui_ro": "rui_ro",
}

OBJECT_FIELDS = {"ben_vay", "de_nghi_vay"}
STR_LIST_FIELDS = {"phuong_an_su_dung_von", "khuyen_nghi"}


# --------------------------------------------------------------- tiện ích


def conversation_text(messages: list[Message], limit: int = 24, max_chars: int = 9000) -> str:
    lines: list[str] = []
    for m in messages[-limit:]:
        if m.role not in ("user", "assistant") or not m.content.strip():
            continue
        who = "KHÁCH HÀNG" if m.role == "user" else "TRỢ LÝ"
        lines.append(f"{who}: {m.content.strip()}")
    text = "\n\n".join(lines)
    return text[-max_chars:] if len(text) > max_chars else (text or "(chưa có trao đổi)")


def _to_str(v: Any) -> str:
    if v is None or isinstance(v, (dict, list)):
        return "" if v is None else json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return "Có" if v else "Không"
    return str(v).strip()


def _to_bool(v: Any, default: bool = True) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "có", "co", "bắt buộc", "bat buoc", "yes", "x"}
    if isinstance(v, (int, float)):
        return bool(v)
    return default


def coerce_dossier(raw: dict[str, Any]) -> Dossier:
    """Chuẩn hoá JSON model trả về cho khớp schema, chịu được sai lệch nhỏ."""
    if not isinstance(raw, dict):
        return Dossier()

    # Model đôi khi bọc thêm 1 lớp
    for wrapper in ("ho_so", "dossier", "data", "result"):
        if wrapper in raw and isinstance(raw[wrapper], dict) and len(raw) <= 2:
            raw = raw[wrapper]
            break

    clean: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in Dossier.model_fields:
            continue

        if key in OBJECT_FIELDS:
            clean[key] = {k: _to_str(v) for k, v in value.items()} if isinstance(value, dict) else {}
            continue

        if key in STR_LIST_FIELDS:
            if isinstance(value, list):
                clean[key] = [_to_str(v) for v in value if _to_str(v)]
            elif isinstance(value, str) and value.strip():
                clean[key] = [value.strip()]
            else:
                clean[key] = []
            continue

        if key in LIST_PRIMARY_KEY:
            items: list[dict[str, Any]] = []
            for item in value if isinstance(value, list) else []:
                if isinstance(item, dict):
                    row = {k: (_to_bool(v) if k == "bat_buoc" else _to_str(v)) for k, v in item.items()}
                elif _to_str(item):
                    row = {LIST_PRIMARY_KEY[key]: _to_str(item)}
                else:
                    continue
                items.append(row)
            clean[key] = items
            continue

        clean[key] = _to_str(value)

    try:
        dossier = Dossier.model_validate(clean)
    except Exception as exc:
        logger.warning("JSON hồ sơ không khớp schema (%s) — dùng phần hợp lệ.", exc)
        dossier = Dossier()
        for k, v in clean.items():
            try:
                setattr(dossier, k, v)
            except Exception:
                continue

    if not dossier.ngay_lap:
        dossier.ngay_lap = date.today().strftime("%d/%m/%Y")
    if not dossier.tieu_de:
        dossier.tieu_de = "HỒ SƠ ĐỀ NGHỊ CẤP TÍN DỤNG"
    return dossier


def _merge_keep_user(generated: Dossier, current: dict[str, Any] | None) -> Dossier:
    """Giá trị người dùng đã nhập luôn được giữ, model chỉ điền vào chỗ trống."""
    if not current:
        return generated

    gen = generated.model_dump()
    for key, user_val in current.items():
        if key not in gen:
            continue
        if isinstance(user_val, dict) and isinstance(gen[key], dict):
            for sub, sv in user_val.items():
                if sub in gen[key] and _to_str(sv):
                    gen[key][sub] = sv
        elif isinstance(user_val, list):
            if user_val:
                gen[key] = user_val
        elif _to_str(user_val):
            gen[key] = user_val
    return coerce_dossier(gen)


# ------------------------------------------------------------- sinh hồ sơ


def _build_search_query(conv: str) -> str:
    try:
        q = groq_client.chat(
            [{"role": "user", "content": prompts.DOSSIER_QUERY_PROMPT.format(conversation=conv[-4000:])}],
            model=settings.groq_fast_model,
            temperature=0.0,
            max_tokens=160,
        )
        q = q.strip().strip('"').split("\n")[0]
        if len(q) > 8:
            return f"{q} {FALLBACK_QUERY}"
    except Exception as exc:
        logger.warning("Không tạo được truy vấn cho hồ sơ (%s).", exc)
    return FALLBACK_QUERY


def generate_dossier(req: DossierGenerateRequest) -> tuple[Dossier, list[SourceRef]]:
    conv = conversation_text(req.messages)
    store = get_store()

    hits = []
    if store.chunks:
        query = _build_search_query(conv)
        hits = chat_service.retrieve(query, top_k=DOSSIER_TOP_K)

    context = format_context(hits, max_chars=11000) if hits else "(Chưa có văn bản pháp luật nào được nạp.)"
    current_json = (
        json.dumps(req.dossier_hien_tai, ensure_ascii=False, indent=2)
        if req.dossier_hien_tai
        else "(chưa có)"
    )

    prompt = prompts.DOSSIER_PROMPT.format(
        schema=prompts.DOSSIER_SCHEMA_HINT,
        context=context,
        current=current_json,
        conversation=conv,
        extra=req.huong_dan_them.strip() or "(không có)",
    )

    raw = groq_client.chat_json(
        [{"role": "user", "content": prompt}],
        model=req.model or settings.groq_model,
        temperature=0.15,
        max_tokens=6000,
    )

    dossier = coerce_dossier(raw)
    dossier = _merge_keep_user(dossier, req.dossier_hien_tai)
    return dossier, chat_service.hits_to_sources(hits)
