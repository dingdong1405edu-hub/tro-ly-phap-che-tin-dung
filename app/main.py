"""FastAPI app: API tra cứu luật vay vốn + quản lý kho văn bản + xuất PDF hồ sơ."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Iterator

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .llm import groq_client
from .pdfout.dossier_pdf import build_dossier_pdf, safe_filename
from .rag import pipeline
from .schemas import (
    ChatRequest,
    DocumentInfo,
    Dossier,
    DossierExportRequest,
    DossierGenerateRequest,
    IngestResult,
    SearchRequest,
)
from .services import chat_service, dossier_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("app")

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings.ensure_dirs()
    store = pipeline.get_store()
    logger.info("Sẵn sàng. Chỉ mục: %s", store.stats())
    if not groq_client.has_api_key():
        logger.warning("CHƯA CÓ GROQ_API_KEY — phần chat sẽ báo lỗi cho tới khi cấu hình .env")
    yield


app = FastAPI(
    title="Trợ lý Pháp chế Tín dụng",
    description="Hệ thống tra cứu quy định pháp luật trong quá trình vay vốn ngân hàng (Groq + RAG)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ hệ thống


@app.get("/api/health")
def health() -> dict:
    store = pipeline.get_store()
    return {
        "ok": True,
        "has_api_key": groq_client.has_api_key(),
        "model": settings.groq_model,
        "fast_model": settings.groq_fast_model,
        "top_k": settings.top_k,
        **store.stats(),
    }


@app.get("/api/models")
def models() -> dict:
    if not groq_client.has_api_key():
        return {"models": [settings.groq_model], "current": settings.groq_model, "has_api_key": False}
    return {"models": groq_client.list_models(), "current": settings.groq_model, "has_api_key": True}


# ------------------------------------------------------------- kho văn bản


@app.get("/api/documents", response_model=list[DocumentInfo])
def list_documents() -> list[DocumentInfo]:
    store = pipeline.get_store()
    return [DocumentInfo(**d) for d in store.documents.values()]


@app.post("/api/documents/upload", response_model=IngestResult)
async def upload_documents(files: list[UploadFile] = File(...)) -> IngestResult:
    result = IngestResult(ok=True)
    store = pipeline.get_store()

    for uf in files:
        try:
            content = await uf.read()
            if not content:
                result.skipped.append(f"{uf.filename}: file rỗng")
                continue
            path = pipeline.save_upload(uf.filename or "khong-ten", content)
            info, warns = pipeline.ingest_file(path, store=store, reindex=False)
            result.documents.append(info)
            result.warnings.extend(f"{uf.filename}: {w}" for w in warns)
        except Exception as exc:
            logger.exception("Lỗi nạp %s", uf.filename)
            result.skipped.append(f"{uf.filename}: {exc}")

    store.reindex()
    result.total_chunks = len(store.chunks)
    result.ok = bool(result.documents)
    return result


@app.post("/api/documents/reindex", response_model=IngestResult)
def reindex(rebuild: bool = Query(True, description="Xoá chỉ mục cũ rồi nạp lại toàn bộ thư mục")) -> IngestResult:
    """Quét lại thư mục data/raw_laws — dùng khi bạn copy file luật thẳng vào thư mục."""
    return pipeline.ingest_directory(rebuild=rebuild)


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, delete_file: bool = Query(True)) -> dict:
    ok = pipeline.delete_document(doc_id, delete_file=delete_file)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy văn bản")
    return {"ok": True, **pipeline.get_store().stats()}


@app.delete("/api/documents")
def clear_documents(delete_files: bool = Query(False)) -> dict:
    pipeline.purge_all(delete_files=delete_files)
    return {"ok": True, **pipeline.get_store().stats()}


@app.post("/api/search")
def search(req: SearchRequest) -> dict:
    hits = chat_service.retrieve(req.query, top_k=req.top_k or settings.top_k)
    return {"query": req.query, "sources": [s.model_dump() for s in chat_service.hits_to_sources(hits)]}


# ------------------------------------------------------------------- chat


def _sse(event: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event, **data}, ensure_ascii=False)}\n\n"


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    if not req.messages:
        raise HTTPException(status_code=400, detail="Thiếu nội dung tin nhắn")
    if not groq_client.has_api_key():
        raise HTTPException(status_code=503, detail=groq_client.MISSING_KEY_MSG)

    def generate() -> Iterator[str]:
        try:
            llm_messages, sources, _hits = chat_service.build_messages(req)
            yield _sse("sources", {"sources": [s.model_dump() for s in sources]})

            for piece in groq_client.chat_stream(
                llm_messages,
                model=req.model or settings.groq_model,
                temperature=req.temperature,
            ):
                yield _sse("delta", {"text": piece})

            yield _sse("done", {})
        except Exception as exc:
            logger.exception("Lỗi khi trả lời")
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    if not req.messages:
        raise HTTPException(status_code=400, detail="Thiếu nội dung tin nhắn")
    if not groq_client.has_api_key():
        raise HTTPException(status_code=503, detail=groq_client.MISSING_KEY_MSG)
    try:
        text, sources = chat_service.answer(req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"answer": text, "sources": [s.model_dump() for s in sources]}


# ------------------------------------------------------------ hồ sơ vay vốn


@app.post("/api/dossier/generate")
def generate_dossier(req: DossierGenerateRequest) -> dict:
    if not groq_client.has_api_key():
        raise HTTPException(status_code=503, detail=groq_client.MISSING_KEY_MSG)
    try:
        dossier, sources = dossier_service.generate_dossier(req)
    except Exception as exc:
        logger.exception("Lỗi sinh hồ sơ")
        raise HTTPException(status_code=500, detail=f"Không sinh được hồ sơ: {exc}") from exc
    return {"dossier": dossier.model_dump(), "sources": [s.model_dump() for s in sources]}


@app.post("/api/dossier/export")
def export_dossier(req: DossierExportRequest) -> Response:
    try:
        pdf_bytes = build_dossier_pdf(
            req.dossier,
            include_legal=req.kem_can_cu_phap_ly,
            include_checklist=req.kem_checklist,
        )
    except Exception as exc:
        logger.exception("Lỗi xuất PDF")
        raise HTTPException(status_code=500, detail=f"Không xuất được PDF: {exc}") from exc

    name = safe_filename(req.dossier, req.ten_file)
    (settings.export_dir / name).write_bytes(pdf_bytes)  # lưu lại 1 bản trên máy
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Filename": name,
        },
    )


@app.post("/api/dossier/preview")
def preview_dossier(dossier: Dossier = Body(...)) -> Response:
    """Xem nhanh PDF ngay trong trình duyệt (không tải về)."""
    try:
        pdf_bytes = build_dossier_pdf(dossier)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(content=pdf_bytes, media_type="application/pdf")


# ------------------------------------------------------------------- giao diện

if settings.frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(settings.frontend_dir)), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(str(settings.frontend_dir / "index.html"))
else:  # pragma: no cover

    @app.get("/", include_in_schema=False)
    def index_missing() -> JSONResponse:
        return JSONResponse({"detail": "Chưa có thư mục frontend"}, status_code=404)


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
