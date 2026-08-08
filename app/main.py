"""FastAPI app: API tra cứu luật vay vốn + quản lý kho văn bản + xuất PDF hồ sơ."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Iterator

from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .auth import service as auth_service
from .auth.data_router import router as data_router
from .auth.deps import yeu_cau_dang_nhap, yeu_cau_quan_tri
from .auth.models import NguoiDung
from .auth.router import router as auth_router
from .config import settings
from .llm import groq_client
from .pdfout.dossier_pdf import build_dossier_pdf, safe_filename
from .rag import pipeline
from .samples import ho_so_mau, thong_tin_mau
from .schemas import (
    ChatRequest,
    DocumentInfo,
    Dossier,
    DossierExportRequest,
    DossierGenerateRequest,
    DossierPipelineRequest,
    IngestResult,
    ReadinessRequest,
    SearchRequest,
)
from .services import chat_service, dossier_pipeline, dossier_service, readiness

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("app")

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings.ensure_dirs()
    auth_service.bootstrap_admin()
    store = pipeline.get_store()
    logger.info("Sẵn sàng. Chỉ mục: %s", store.stats())
    if not groq_client.has_api_key():
        logger.warning("CHƯA CÓ GROQ_API_KEY — phần chat sẽ báo lỗi cho tới khi cấu hình .env")
    if auth_service.dem_nguoi_dung() == 0:
        logger.warning("CHƯA CÓ TÀI KHOẢN NÀO — người đăng ký đầu tiên sẽ là quản trị viên.")
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

# Tài khoản, phiên đăng nhập và dữ liệu riêng của từng người dùng
app.include_router(auth_router)
app.include_router(data_router)


# ------------------------------------------------------------------ hệ thống


@app.get("/api/health")
def health() -> dict:
    """Công khai — Railway gọi endpoint này để kiểm tra container còn sống."""
    store = pipeline.get_store()
    return {
        "ok": True,
        "has_api_key": groq_client.has_api_key(),
        "model": settings.groq_model,
        "fast_model": settings.groq_fast_model,
        "top_k": settings.top_k,
        **store.stats(),
    }


@app.get("/api/models", dependencies=[Depends(yeu_cau_dang_nhap)])
def models() -> dict:
    if not groq_client.has_api_key():
        return {"models": [settings.groq_model], "current": settings.groq_model, "has_api_key": False}
    return {"models": groq_client.list_models(), "current": settings.groq_model, "has_api_key": True}


# ------------------------------------------------------------- kho văn bản
#
# Kho văn bản pháp luật dùng chung cho cả hệ thống: ai đăng nhập cũng tra cứu
# được, nhưng chỉ quản trị viên mới được nạp thêm hay xoá đi.


@app.get("/api/documents", response_model=list[DocumentInfo], dependencies=[Depends(yeu_cau_dang_nhap)])
def list_documents() -> list[DocumentInfo]:
    store = pipeline.get_store()
    return [DocumentInfo(**d) for d in store.documents.values()]


@app.post("/api/documents/upload", response_model=IngestResult, dependencies=[Depends(yeu_cau_quan_tri)])
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


@app.post("/api/documents/reindex", response_model=IngestResult, dependencies=[Depends(yeu_cau_quan_tri)])
def reindex(rebuild: bool = Query(True, description="Xoá chỉ mục cũ rồi nạp lại toàn bộ thư mục")) -> IngestResult:
    """Quét lại thư mục data/raw_laws — dùng khi bạn copy file luật thẳng vào thư mục."""
    return pipeline.ingest_directory(rebuild=rebuild)


@app.delete("/api/documents/{doc_id}", dependencies=[Depends(yeu_cau_quan_tri)])
def delete_document(doc_id: str, delete_file: bool = Query(True)) -> dict:
    ok = pipeline.delete_document(doc_id, delete_file=delete_file)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy văn bản")
    return {"ok": True, **pipeline.get_store().stats()}


@app.delete("/api/documents", dependencies=[Depends(yeu_cau_quan_tri)])
def clear_documents(delete_files: bool = Query(False)) -> dict:
    pipeline.purge_all(delete_files=delete_files)
    return {"ok": True, **pipeline.get_store().stats()}


@app.post("/api/search", dependencies=[Depends(yeu_cau_dang_nhap)])
def search(req: SearchRequest) -> dict:
    hits = chat_service.retrieve(req.query, top_k=req.top_k or settings.top_k)
    return {"query": req.query, "sources": [s.model_dump() for s in chat_service.hits_to_sources(hits)]}


# ------------------------------------------------------------------- chat


def _sse(event: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event, **data}, ensure_ascii=False)}\n\n"


@app.post("/api/chat/stream", dependencies=[Depends(yeu_cau_dang_nhap)])
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


@app.post("/api/chat", dependencies=[Depends(yeu_cau_dang_nhap)])
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


@app.post("/api/dossier/generate", dependencies=[Depends(yeu_cau_dang_nhap)])
def generate_dossier(req: DossierGenerateRequest) -> dict:
    if not groq_client.has_api_key():
        raise HTTPException(status_code=503, detail=groq_client.MISSING_KEY_MSG)
    try:
        dossier, sources = dossier_service.generate_dossier(req)
    except Exception as exc:
        logger.exception("Lỗi sinh hồ sơ")
        raise HTTPException(status_code=500, detail=f"Không sinh được hồ sơ: {exc}") from exc
    return {"dossier": dossier.model_dump(), "sources": [s.model_dump() for s in sources]}


@app.post("/api/dossier/pipeline/stream", dependencies=[Depends(yeu_cau_dang_nhap)])
def dossier_pipeline_stream(req: DossierPipelineRequest) -> StreamingResponse:
    """Chạy trọn quy trình lập hồ sơ, phát tiến độ từng chặng qua SSE."""
    if not groq_client.has_api_key():
        raise HTTPException(status_code=503, detail=groq_client.MISSING_KEY_MSG)

    def generate() -> Iterator[str]:
        try:
            for su_kien in dossier_pipeline.chay(req):
                yield su_kien.sse()
        except Exception as exc:
            logger.exception("Lỗi pipeline hồ sơ")
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.post("/api/dossier/pipeline", dependencies=[Depends(yeu_cau_dang_nhap)])
def dossier_pipeline_sync(req: DossierPipelineRequest) -> dict:
    """Bản chạy một lần, dùng khi client không đọc được SSE."""
    if not groq_client.has_api_key():
        raise HTTPException(status_code=503, detail=groq_client.MISSING_KEY_MSG)
    try:
        return dossier_pipeline.chay_dong_bo(req)
    except Exception as exc:
        logger.exception("Lỗi pipeline hồ sơ")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/dossier/readiness", dependencies=[Depends(yeu_cau_dang_nhap)])
def dossier_readiness(req: ReadinessRequest) -> dict:
    """Cổng kiểm tra đầu vào — giao diện gọi mỗi khi khách sửa hồ sơ."""
    bao_cao = dossier_pipeline.kiem_tra_nhanh(req.dossier_hien_tai, req.huong_dan_them)
    return bao_cao.model_dump()


@app.get("/api/dossier/required-docs", dependencies=[Depends(yeu_cau_dang_nhap)])
def required_docs(loai_hinh: str = Query("", description="Loại hình khách hàng")) -> dict:
    """Danh mục giấy tờ tối thiểu theo loại hình khách hàng."""
    danh_muc = readiness.danh_muc_giay_to(loai_hinh)
    return {
        "loai_hinh": loai_hinh,
        "la_ca_nhan": readiness.la_ca_nhan(loai_hinh),
        "giay_to": [g.model_dump() for g in danh_muc],
    }


# --------------------------------------------------------------- hồ sơ mẫu


@app.get("/api/dossier/sample", dependencies=[Depends(yeu_cau_dang_nhap)])
def dossier_sample() -> dict:
    """Hồ sơ vay vốn mẫu đầy đủ: thẩm định giá trị doanh nghiệp, biểu đồ, checklist."""
    return {"dossier": ho_so_mau().model_dump(), "tom_tat": thong_tin_mau()}


@app.get("/api/dossier/sample/pdf", dependencies=[Depends(yeu_cau_dang_nhap)])
def dossier_sample_pdf() -> Response:
    pdf_bytes = build_dossier_pdf(ho_so_mau())
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="Ho-so-vay-von-mau.pdf"'},
    )


@app.post("/api/dossier/export")
def export_dossier(
    req: DossierExportRequest,
    nguoi_dung: NguoiDung = Depends(yeu_cau_dang_nhap),
) -> Response:
    try:
        pdf_bytes = build_dossier_pdf(
            req.dossier,
            include_legal=req.kem_can_cu_phap_ly,
            include_checklist=req.kem_checklist,
            include_appraisal=req.kem_tham_dinh,
            include_charts=req.kem_bieu_do,
        )
    except Exception as exc:
        logger.exception("Lỗi xuất PDF")
        raise HTTPException(status_code=500, detail=f"Không xuất được PDF: {exc}") from exc

    # Lưu lại một bản trên đĩa, tách theo tài khoản để hai người trùng tên khách
    # hàng không ghi đè file của nhau.
    name = safe_filename(req.dossier, req.ten_file)
    thu_muc = settings.export_dir / f"u{nguoi_dung.id}"
    thu_muc.mkdir(parents=True, exist_ok=True)
    (thu_muc / name).write_bytes(pdf_bytes)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Filename": name,
        },
    )


@app.post("/api/dossier/preview", dependencies=[Depends(yeu_cau_dang_nhap)])
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
    def landing() -> FileResponse:
        """Trang giới thiệu."""
        return FileResponse(str(settings.frontend_dir / "landing.html"))

    @app.get("/app", include_in_schema=False)
    def index() -> FileResponse:
        """Ứng dụng: tra cứu luật · lập hồ sơ · hồ sơ mẫu."""
        return FileResponse(str(settings.frontend_dir / "index.html"))

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(str(settings.frontend_dir / "favicon.svg"), media_type="image/svg+xml")
else:  # pragma: no cover

    @app.get("/", include_in_schema=False)
    def index_missing() -> JSONResponse:
        return JSONResponse({"detail": "Chưa có thư mục frontend"}, status_code=404)


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
