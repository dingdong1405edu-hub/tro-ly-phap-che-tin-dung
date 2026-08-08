"""Quy trình lập hồ sơ vay vốn — chạy theo chặng và phát tín hiệu tiến độ ra ngoài.

Toàn bộ công việc dài của "tool lập hồ sơ" được tách thành các chặng độc lập.
Mỗi chặng phát sự kiện để giao diện hiển thị đúng việc Agent đang làm:

    plan → step(dang_chay) → log → step(xong) → … → done

Chặng số 2 là **cổng chặn**: nếu hồ sơ chưa đủ thông tin hoặc giấy tờ bắt buộc,
pipeline phát sự kiện ``blocked`` kèm danh sách việc cần bổ sung rồi dừng hẳn —
không sinh ra bản hồ sơ nào.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator

from ..config import settings
from ..llm import groq_client, prompts
from ..rag.pipeline import get_store
from ..rag.retriever import format_context
from ..schemas import (
    Dossier,
    DossierPipelineRequest,
    ProvidedDoc,
    ReadinessReport,
    SourceRef,
)
from . import chat_service, dossier_service, readiness, valuation
from .numbers import dinh_dang_tien, doc_thanh_chu, doc_tien, doc_tien_trong_cau, rut_gon_tien

logger = logging.getLogger(__name__)

DOSSIER_TOP_K = 12

# Mô tả các chặng — gửi xuống giao diện ngay từ đầu để vẽ sẵn timeline
CHANG = [
    {"ma": "tiep_nhan", "ten": "Tiếp nhận và chuẩn hoá dữ liệu",
     "mo_ta": "Đọc thông tin khách nhập, quy đổi số tiền và thời hạn về dạng tính toán được."},
    {"ma": "kiem_tra", "ten": "Kiểm tra tính đầy đủ của hồ sơ",
     "mo_ta": "Đối chiếu thông tin và giấy tờ bắt buộc. Thiếu là dừng, không lập hồ sơ."},
    {"ma": "trich_xuat", "ten": "Trích xuất dữ liệu từ mô tả tự do",
     "mo_ta": "Bóc tài sản bảo đảm, số liệu tài chính và khoản mục sử dụng vốn từ phần mô tả."},
    {"ma": "tra_cuu", "ten": "Tra cứu căn cứ pháp lý",
     "mo_ta": "Tìm trong kho văn bản các điều khoản chi phối khoản vay này."},
    {"ma": "phan_tich", "ten": "Phân tích chỉ số tài chính",
     "mo_ta": "Tính ROA, ROE, hệ số nợ, thanh khoản, LTV kèm ngưỡng tham chiếu."},
    {"ma": "dinh_gia", "ten": "Thẩm định giá trị doanh nghiệp",
     "mo_ta": "Định giá theo tài sản thuần, chiết khấu dòng tiền và so sánh thị trường."},
    {"ma": "dong_tien", "ten": "Lập lịch trả nợ và dòng tiền",
     "mo_ta": "Chia lịch trả gốc lãi theo từng năm và tính hệ số bảo đảm trả nợ DSCR."},
    {"ma": "checklist", "ten": "Soạn danh mục hồ sơ phải nộp",
     "mo_ta": "Lập checklist tài liệu kèm căn cứ pháp lý tương ứng."},
    {"ma": "rui_ro", "ten": "Đánh giá rủi ro và chấm điểm",
     "mo_ta": "Nhận diện rủi ro, chấm điểm tín dụng và đưa ra đề xuất."},
    {"ma": "bieu_do", "ten": "Dựng biểu đồ minh hoạ",
     "mo_ta": "Vẽ biểu đồ kết quả kinh doanh, định giá, khả năng trả nợ và cơ cấu vốn."},
    {"ma": "hoan_tat", "ten": "Kiểm tra chéo và hoàn tất",
     "mo_ta": "Rà soát tính nhất quán rồi bàn giao hồ sơ hoàn chỉnh."},
]


# ------------------------------------------------------------- sự kiện


@dataclass
class SuKien:
    loai: str
    du_lieu: dict[str, Any]

    def sse(self) -> str:
        goi = {"type": self.loai, **self.du_lieu}
        return f"data: {json.dumps(goi, ensure_ascii=False)}\n\n"


def _sk(loai: str, **du_lieu: Any) -> SuKien:
    return SuKien(loai, du_lieu)


class _Chang:
    """Bộ đếm chặng — chỉ để tính phần trăm tiến độ cho giao diện."""

    def __init__(self) -> None:
        self.xong = 0
        self.tong = len(CHANG)
        self.bat_dau = time.monotonic()

    def tien_do(self) -> float:
        return round(min(self.xong / self.tong, 1.0), 3)

    def giay(self) -> float:
        return round(time.monotonic() - self.bat_dau, 1)


# -------------------------------------------------------------- tiện ích


def _ghi_chu_tu_yeu_cau(text: str, khoa: tuple[str, ...]) -> str:
    """Lọc đoạn mô tả tự do theo từ khoá để đưa vào bộ kiểm tra đầu vào."""
    if not text:
        return ""
    doan = [d.strip() for d in text.split("\n") if d.strip()]
    hop = [d for d in doan if any(k in d.lower() for k in khoa)]
    return "\n".join(hop or doan)


def _mo_ta_khoan_vay(d: Dossier) -> str:
    v = d.de_nghi_vay
    b = d.ben_vay
    dong = [
        f"Khách hàng: {b.ten or '(chưa có)'} — {b.loai_hinh or '(chưa rõ loại hình)'}",
        f"Ngành nghề: {b.nganh_nghe or '(chưa có)'}",
        f"Số tiền đề nghị vay: {v.so_tien} {v.don_vi}".strip(),
        f"Thời hạn: {v.thoi_han}",
        f"Mục đích vay: {v.muc_dich_vay}",
        f"Phương thức cho vay: {v.phuong_thuc_cho_vay or '(chưa chọn)'}",
        f"Phương thức trả nợ: {v.phuong_thuc_tra_no or '(chưa chọn)'}",
        f"Lãi suất dự kiến: {v.lai_suat_du_kien or '(chưa có)'}",
        f"Vốn tự có: {v.von_tu_co or '(chưa có)'}",
        f"Tóm tắt phương án: {d.tom_tat_phuong_an or '(chưa có)'}",
        f"Nguồn trả nợ: {d.phuong_an_tra_no or '(chưa có)'}",
    ]
    if d.tai_san_bao_dam:
        ts = "; ".join(
            f"{t.ten_tai_san} ({t.gia_tri_uoc_tinh})" for t in d.tai_san_bao_dam if t.ten_tai_san
        )
        dong.append(f"Tài sản bảo đảm: {ts}")
    return "\n".join(dong)


def _tom_tat_chi_so(chi_so: list) -> str:
    return "\n".join(
        f"- {c.ten}: {c.gia_tri} (ngưỡng {c.nguong or 'n/a'}) → {c.danh_gia}" for c in chi_so
    )


def _tom_tat_dinh_gia(dg) -> str:
    if not dg.thuc_hien_duoc:
        return f"Không thực hiện định giá. Lý do: {dg.ly_do}"
    dong = [f"Giá trị kết luận: {dg.gia_tri_ket_luan_hien_thi} ({dg.gia_tri_bang_chu})",
            f"Khoảng giá trị: {dg.khoang_thap} — {dg.khoang_cao}"]
    for p in dg.phuong_phap:
        if p.ap_dung_duoc and p.gia_tri > 0:
            dong.append(f"- {p.ten}: {p.gia_tri_hien_thi} (trọng số {round(p.trong_so * 100)}%)")
        elif p.ly_do_khong_ap_dung:
            dong.append(f"- {p.ten}: không áp dụng — {p.ly_do_khong_ap_dung}")
    return "\n".join(dong)


def _tom_tat_diem(kl) -> str:
    return (
        f"Điểm tín dụng: {kl.diem}/100 — xếp hạng {kl.xep_hang} — mức rủi ro {kl.muc_rui_ro}\n"
        f"Đề xuất: {kl.de_xuat}\n"
        f"Hạn mức đề xuất: {kl.han_muc_de_xuat or '(chưa xác định)'}"
    )


def _tom_tat_phap_ly(d: Dossier) -> str:
    if not d.can_cu_phap_ly:
        return "(Kho văn bản chưa có căn cứ nào được trích dẫn)"
    return "\n".join(
        f"- {c.van_ban} — {c.dieu_khoan}: {c.noi_dung[:180]}" for c in d.can_cu_phap_ly[:12]
    )


def _tu_dien_hoa(dossier: Dossier) -> None:
    """Điền nốt các trường suy ra được mà không cần model."""
    if not dossier.ngay_lap:
        dossier.ngay_lap = date.today().strftime("%d/%m/%Y")
    if not dossier.tieu_de:
        dossier.tieu_de = "HỒ SƠ ĐỀ NGHỊ CẤP TÍN DỤNG"

    so_tien = doc_tien(dossier.de_nghi_vay.so_tien)
    if so_tien and not dossier.de_nghi_vay.bang_chu:
        don_vi = "đồng" if (dossier.de_nghi_vay.don_vi or "VND").upper() == "VND" else dossier.de_nghi_vay.don_vi
        dossier.de_nghi_vay.bang_chu = doc_thanh_chu(so_tien, don_vi)

    don_vi_tien = dossier.de_nghi_vay.don_vi or "VND"
    for truong in ("so_tien", "von_tu_co"):
        gia_tri = str(getattr(dossier.de_nghi_vay, truong) or "").strip()
        so = doc_tien(gia_tri)
        # Chuẩn hoá "5 tỷ" -> "5.000.000.000 VND" để bảng biểu và PDF hiển thị thống nhất
        if so and not any(k in gia_tri.upper() for k in (don_vi_tien.upper(), "ĐỒNG", "DONG")):
            setattr(dossier.de_nghi_vay, truong, dinh_dang_tien(so, don_vi_tien))

    von_tu_co = doc_tien(dossier.de_nghi_vay.von_tu_co)
    if so_tien and von_tu_co and not dossier.de_nghi_vay.ty_le_vay_tren_tong_von:
        tong = so_tien + von_tu_co
        if tong > 0:
            dossier.de_nghi_vay.ty_le_vay_tren_tong_von = f"{round(so_tien / tong * 100, 1)}%".replace(".", ",")


# ------------------------------------------------------------- pipeline


def chay(req: DossierPipelineRequest) -> Iterator[SuKien]:
    """Chạy trọn quy trình, phát sự kiện tiến độ theo từng chặng."""
    dem = _Chang()

    def bat_dau(ma: str, ghi_chu: str = "") -> SuKien:
        return _sk("step", ma=ma, trang_thai="dang_chay", ghi_chu=ghi_chu,
                   tien_do=dem.tien_do(), giay=dem.giay())

    def ket_thuc(ma: str, ghi_chu: str = "", trang_thai: str = "xong") -> SuKien:
        dem.xong += 1
        return _sk("step", ma=ma, trang_thai=trang_thai, ghi_chu=ghi_chu,
                   tien_do=dem.tien_do(), giay=dem.giay())

    def nhat_ky(ma: str, text: str) -> SuKien:
        return _sk("log", ma=ma, text=text, giay=dem.giay())

    yield _sk("plan", chang=CHANG)

    # ---------------------------------------------------------- 1. tiếp nhận
    yield bat_dau("tiep_nhan")
    dossier = dossier_service.coerce_dossier(req.dossier_hien_tai or {})
    ghi_chu = (req.huong_dan_them or "").strip()

    dossier.ho_so_cung_cap = readiness.hop_nhat_giay_to(
        dossier.ben_vay.loai_hinh, dossier.ho_so_cung_cap
    )
    _tu_dien_hoa(dossier)

    so_tien = doc_tien(dossier.de_nghi_vay.so_tien)
    yield nhat_ky("tiep_nhan", f"Khách hàng: {dossier.ben_vay.ten or 'chưa có tên'}")
    if so_tien:
        yield nhat_ky("tiep_nhan", f"Quy đổi số tiền vay: {rut_gon_tien(so_tien)}")
    yield nhat_ky("tiep_nhan", f"Danh mục giấy tờ áp dụng: {len(dossier.ho_so_cung_cap)} loại")
    yield ket_thuc("tiep_nhan", "Đã chuẩn hoá dữ liệu đầu vào")

    # ------------------------------------------------------- 2. CỔNG KIỂM TRA
    yield bat_dau("kiem_tra")
    store = get_store()
    kho_trong = not store.chunks

    bao_cao = readiness.kiem_tra(
        dossier,
        ghi_chu_tai_chinh=_ghi_chu_tu_yeu_cau(ghi_chu, ("tài chính", "doanh thu", "lợi nhuận", "tài sản")),
        ghi_chu_tsbd=_ghi_chu_tu_yeu_cau(ghi_chu, ("bảo đảm", "thế chấp", "tsbđ", "sổ đỏ", "tài sản")),
        kho_van_ban_trong=kho_trong,
    )
    yield nhat_ky("kiem_tra", f"Đã đối chiếu {bao_cao.tong_bat_buoc} mục bắt buộc")
    yield nhat_ky("kiem_tra", f"Mức độ đầy đủ hiện tại: {bao_cao.diem}%")

    if not bao_cao.du_dieu_kien:
        yield ket_thuc("kiem_tra", f"Thiếu {len(bao_cao.thieu_bat_buoc)} mục bắt buộc", "chan")
        yield _sk("blocked", bao_cao=bao_cao.model_dump(), giay=dem.giay())
        return

    if bao_cao.thieu_quan_trong and not req.bo_qua_canh_bao:
        yield ket_thuc(
            "kiem_tra",
            f"Đủ điều kiện lập hồ sơ, còn {len(bao_cao.thieu_quan_trong)} mục nên bổ sung",
            "canh_bao",
        )
        yield _sk("need_confirm", bao_cao=bao_cao.model_dump(), giay=dem.giay())
        return

    yield ket_thuc("kiem_tra", "Hồ sơ đủ điều kiện — cho phép lập")
    for cb in bao_cao.canh_bao:
        yield _sk("warning", text=cb)

    # ------------------------------------------------------ 3. trích xuất
    yield bat_dau("trich_xuat")
    hoi_thoai = dossier_service.conversation_text(req.messages)
    if ghi_chu or len(hoi_thoai) > 40:
        try:
            raw = groq_client.chat_json(
                [{"role": "user", "content": prompts.EXTRACT_PROMPT.format(
                    current=json.dumps(
                        {
                            "ben_vay": dossier.ben_vay.model_dump(),
                            "de_nghi_vay": dossier.de_nghi_vay.model_dump(),
                            "so_dong_tsbd": len(dossier.tai_san_bao_dam),
                            "so_dong_tai_chinh": len(dossier.tinh_hinh_tai_chinh),
                        },
                        ensure_ascii=False, indent=1,
                    ),
                    notes=ghi_chu or "(không có)",
                    conversation=hoi_thoai,
                )}],
                model=req.model or settings.groq_model,
                temperature=0.1,
                max_tokens=3000,
            )
            them = _ap_dung_trich_xuat(dossier, raw)
            for dong in them:
                yield nhat_ky("trich_xuat", dong)
            yield ket_thuc("trich_xuat", "Đã bổ sung dữ liệu từ phần mô tả")
        except Exception as exc:
            logger.warning("Trích xuất thất bại: %s", exc)
            yield nhat_ky("trich_xuat", f"Không trích xuất được: {exc}")
            yield ket_thuc("trich_xuat", "Bỏ qua, dùng dữ liệu khách đã nhập", "bo_qua")
    else:
        yield ket_thuc("trich_xuat", "Không có mô tả tự do — bỏ qua", "bo_qua")

    _tu_dien_hoa(dossier)
    yield _sk("partial", dossier=dossier.model_dump(), giay=dem.giay())

    # -------------------------------------------------------- 4. tra cứu
    yield bat_dau("tra_cuu")
    nguon: list[SourceRef] = []
    hits = []
    if kho_trong:
        yield nhat_ky("tra_cuu", "Kho văn bản trống — bỏ qua bước trích dẫn")
        yield ket_thuc("tra_cuu", "Không có văn bản để tra cứu", "bo_qua")
    else:
        try:
            truy_van = _truy_van(dossier, hoi_thoai)
            yield nhat_ky("tra_cuu", f"Truy vấn: {truy_van[:150]}")
            hits = chat_service.retrieve(truy_van, top_k=req.top_k or DOSSIER_TOP_K)
            nguon = chat_service.hits_to_sources(hits)
            for s in nguon[:6]:
                yield nhat_ky("tra_cuu", f"[{s.id}] {s.citation} — {s.doc_title[:60]}")
            yield _sk("sources", sources=[s.model_dump() for s in nguon])
            yield ket_thuc("tra_cuu", f"Tìm được {len(nguon)} điều khoản liên quan")
        except Exception as exc:
            logger.warning("Tra cứu thất bại: %s", exc)
            yield ket_thuc("tra_cuu", f"Lỗi tra cứu: {exc}", "loi")

    # ----------------------------------------------- 5-7. phân tích số liệu
    yield bat_dau("phan_tich")
    kq = valuation.tham_dinh(dossier, diem_ho_so=bao_cao.diem, tinh_dinh_gia=req.tinh_dinh_gia)
    dossier.chi_so_tai_chinh = kq.chi_so
    co_so_lieu = sum(1 for c in kq.chi_so if c.so is not None)
    for c in kq.chi_so[:6]:
        if c.so is not None:
            yield nhat_ky("phan_tich", f"{c.ten}: {c.gia_tri} → {c.danh_gia}")
    yield ket_thuc("phan_tich", f"Tính được {co_so_lieu}/{len(kq.chi_so)} chỉ số")

    yield bat_dau("dinh_gia")
    dossier.tham_dinh_gia_tri = kq.dinh_gia
    if kq.dinh_gia.thuc_hien_duoc:
        for p in kq.dinh_gia.phuong_phap:
            if p.ap_dung_duoc and p.gia_tri > 0:
                yield nhat_ky("dinh_gia", f"{p.ten}: {rut_gon_tien(p.gia_tri)}")
        yield nhat_ky("dinh_gia", f"Kết luận: {kq.dinh_gia.gia_tri_ket_luan_hien_thi}")
        yield ket_thuc("dinh_gia", f"Giá trị doanh nghiệp {rut_gon_tien(kq.dinh_gia.gia_tri_ket_luan)}")
    else:
        yield nhat_ky("dinh_gia", kq.dinh_gia.ly_do)
        yield ket_thuc("dinh_gia", "Không áp dụng định giá doanh nghiệp", "bo_qua")

    yield bat_dau("dong_tien")
    dossier.dong_tien_du_kien = kq.dong_tien
    if kq.dong_tien:
        yield nhat_ky("dong_tien", f"Lập lịch trả nợ cho {len(kq.dong_tien)} năm")
        if kq.dscr_bq:
            yield nhat_ky("dong_tien", f"DSCR bình quân: {round(kq.dscr_bq, 2)} lần")
        yield ket_thuc("dong_tien", f"{len(kq.dong_tien)} kỳ trả nợ")
    else:
        yield ket_thuc("dong_tien", "Chưa đủ dữ liệu lập lịch trả nợ", "bo_qua")

    yield _sk("partial", dossier=dossier.model_dump(), giay=dem.giay())

    # ------------------------------------------------------ 8. checklist
    yield bat_dau("checklist")
    if hits:
        try:
            raw = groq_client.chat_json(
                [{"role": "user", "content": prompts.LEGAL_PROMPT.format(
                    loan=_mo_ta_khoan_vay(dossier),
                    context=format_context(hits, max_chars=11000),
                )}],
                model=req.model or settings.groq_model,
                temperature=0.15,
                max_tokens=5000,
            )
            n_hs, n_pl = _ap_dung_phap_ly(dossier, raw)
            yield nhat_ky("checklist", f"Danh mục hồ sơ: {n_hs} tài liệu")
            yield nhat_ky("checklist", f"Căn cứ pháp lý: {n_pl} điều khoản")
            yield ket_thuc("checklist", f"{n_hs} tài liệu · {n_pl} căn cứ")
        except Exception as exc:
            logger.warning("Soạn checklist thất bại: %s", exc)
            yield ket_thuc("checklist", f"Lỗi: {exc}", "loi")
    else:
        _checklist_du_phong(dossier)
        yield nhat_ky("checklist", "Dùng danh mục giấy tờ chuẩn theo loại hình khách hàng")
        yield ket_thuc("checklist", f"{len(dossier.danh_muc_ho_so)} tài liệu (chưa có căn cứ trích dẫn)",
                       "canh_bao")

    # -------------------------------------------------------- 9. rủi ro
    yield bat_dau("rui_ro")
    dossier.ket_luan_tham_dinh = kq.ket_luan
    yield nhat_ky("rui_ro", f"Điểm tín dụng: {kq.ket_luan.diem}/100 — hạng {kq.ket_luan.xep_hang}")
    try:
        raw = groq_client.chat_json(
            [{"role": "user", "content": prompts.APPRAISAL_PROMPT.format(
                loan=_mo_ta_khoan_vay(dossier),
                ratios=_tom_tat_chi_so(kq.chi_so),
                valuation=_tom_tat_dinh_gia(kq.dinh_gia),
                score=_tom_tat_diem(kq.ket_luan),
                legal=_tom_tat_phap_ly(dossier),
            )}],
            model=req.model or settings.groq_model,
            temperature=0.2,
            max_tokens=3500,
        )
        n_rr = _ap_dung_tham_dinh(dossier, raw)
        for r in dossier.danh_gia_rui_ro[:4]:
            yield nhat_ky("rui_ro", f"{r.muc_do}: {r.rui_ro[:80]}")
        yield ket_thuc("rui_ro", f"{n_rr} rủi ro · {len(dossier.khuyen_nghi)} khuyến nghị")
    except Exception as exc:
        logger.warning("Đánh giá rủi ro thất bại: %s", exc)
        yield ket_thuc("rui_ro", f"Lỗi: {exc}", "loi")

    # ------------------------------------------------------- 10. biểu đồ
    yield bat_dau("bieu_do")
    kq2 = valuation.tham_dinh(dossier, diem_ho_so=bao_cao.diem, tinh_dinh_gia=req.tinh_dinh_gia)
    dossier.bieu_do = kq2.bieu_do
    for b in dossier.bieu_do:
        yield nhat_ky("bieu_do", f"{b.tieu_de} ({b.loai})")
    yield ket_thuc("bieu_do", f"Dựng {len(dossier.bieu_do)} biểu đồ")

    # ------------------------------------------------------ 11. hoàn tất
    yield bat_dau("hoan_tat")
    canh_bao = _kiem_tra_cheo(dossier)
    for c in canh_bao:
        yield nhat_ky("hoan_tat", c)
    if not dossier.ghi_chu:
        dossier.ghi_chu = (
            "Hồ sơ được lập tự động từ thông tin khách hàng cung cấp. Số liệu thẩm định là kết quả "
            "tính toán trên dữ liệu đầu vào, cần đối chiếu với báo cáo tài chính đã kiểm toán và "
            "chứng thư thẩm định giá trước khi trình phê duyệt."
        )
    yield ket_thuc("hoan_tat", "Hồ sơ đã hoàn chỉnh")

    yield _sk(
        "done",
        dossier=dossier.model_dump(),
        sources=[s.model_dump() for s in nguon],
        bao_cao=bao_cao.model_dump(),
        canh_bao=canh_bao,
        giay=dem.giay(),
    )


# ------------------------------------------------- áp dụng kết quả model


def _ap_dung_trich_xuat(dossier: Dossier, raw: dict[str, Any]) -> list[str]:
    """Chỉ điền vào chỗ trống — dữ liệu khách hàng đã nhập luôn được giữ nguyên."""
    nhat_ky: list[str] = []
    if not isinstance(raw, dict):
        return nhat_ky

    for khoi in ("ben_vay", "de_nghi_vay"):
        gia_tri = raw.get(khoi)
        if not isinstance(gia_tri, dict):
            continue
        doi_tuong = getattr(dossier, khoi)
        them = 0
        for k, v in gia_tri.items():
            if not hasattr(doi_tuong, k):
                continue
            moi = dossier_service.to_str(v)
            if moi and not str(getattr(doi_tuong, k) or "").strip():
                setattr(doi_tuong, k, moi)
                them += 1
        if them:
            nhat_ky.append(f"Bổ sung {them} trường trong nhóm "
                           f"{'thông tin khách hàng' if khoi == 'ben_vay' else 'nhu cầu vay vốn'}")

    ds = raw.get("phuong_an_su_dung_von")
    if isinstance(ds, list) and not dossier.phuong_an_su_dung_von:
        dossier.phuong_an_su_dung_von = [dossier_service.to_str(x) for x in ds if dossier_service.to_str(x)]
        if dossier.phuong_an_su_dung_von:
            nhat_ky.append(f"Bóc tách {len(dossier.phuong_an_su_dung_von)} khoản mục sử dụng vốn")

    gop = dossier_service.coerce_dossier(
        {
            "tai_san_bao_dam": raw.get("tai_san_bao_dam") or [],
            "tinh_hinh_tai_chinh": raw.get("tinh_hinh_tai_chinh") or [],
        }
    )
    if gop.tai_san_bao_dam and not dossier.tai_san_bao_dam:
        dossier.tai_san_bao_dam = gop.tai_san_bao_dam
        nhat_ky.append(f"Nhận diện {len(gop.tai_san_bao_dam)} tài sản bảo đảm")
    if gop.tinh_hinh_tai_chinh and not dossier.tinh_hinh_tai_chinh:
        dossier.tinh_hinh_tai_chinh = gop.tinh_hinh_tai_chinh
        nhat_ky.append(f"Lập bảng {len(gop.tinh_hinh_tai_chinh)} chỉ tiêu tài chính")

    return nhat_ky or ["Không có dữ liệu mới cần bổ sung"]


def _ap_dung_phap_ly(dossier: Dossier, raw: dict[str, Any]) -> tuple[int, int]:
    gop = dossier_service.coerce_dossier(
        {
            "danh_muc_ho_so": raw.get("danh_muc_ho_so") or [],
            "can_cu_phap_ly": raw.get("can_cu_phap_ly") or [],
        }
    )
    if gop.danh_muc_ho_so:
        dossier.danh_muc_ho_so = gop.danh_muc_ho_so
    if gop.can_cu_phap_ly:
        dossier.can_cu_phap_ly = gop.can_cu_phap_ly

    # Model hay liệt kê thiếu — bù nốt các giấy tờ tối thiểu theo loại hình khách hàng
    _bo_sung_checklist_chuan(dossier)
    return len(dossier.danh_muc_ho_so), len(dossier.can_cu_phap_ly)


def _tu_khoa(text: str) -> set[str]:
    from .numbers import bo_dau

    bo = {"ban", "sao", "cua", "va", "cac", "co", "gan", "nhat", "theo", "mau", "cho", "nam", "trong"}
    return {t for t in bo_dau(text).replace("/", " ").split() if len(t) > 2 and t not in bo}


def _bo_sung_checklist_chuan(dossier: Dossier) -> None:
    """Thêm giấy tờ bắt buộc còn thiếu, đối chiếu theo từ khoá để không lặp lại."""
    from ..schemas import ChecklistItem

    da_co = [_tu_khoa(m.ten_tai_lieu) for m in dossier.danh_muc_ho_so]
    for chuan in readiness.danh_muc_giay_to(dossier.ben_vay.loai_hinh):
        khoa = _tu_khoa(chuan.ten)
        if not khoa:
            continue
        trung = any(len(khoa & c) >= max(2, min(len(khoa), len(c)) // 2) for c in da_co if c)
        if trung:
            continue
        dossier.danh_muc_ho_so.append(
            ChecklistItem(
                nhom=chuan.nhom, ten_tai_lieu=chuan.ten, bat_buoc=chuan.bat_buoc,
                can_cu_phap_ly="", ghi_chu=chuan.can_cu or "",
            )
        )
        da_co.append(khoa)


def _ap_dung_tham_dinh(dossier: Dossier, raw: dict[str, Any]) -> int:
    gop = dossier_service.coerce_dossier(
        {
            "danh_gia_rui_ro": raw.get("danh_gia_rui_ro") or [],
            "khuyen_nghi": raw.get("khuyen_nghi") or [],
            "tom_tat_phuong_an": raw.get("tom_tat_phuong_an") or "",
            "ghi_chu": raw.get("ghi_chu") or "",
        }
    )
    if gop.danh_gia_rui_ro:
        dossier.danh_gia_rui_ro = gop.danh_gia_rui_ro
    if gop.khuyen_nghi:
        dossier.khuyen_nghi = gop.khuyen_nghi
    if gop.tom_tat_phuong_an and not dossier.tom_tat_phuong_an:
        dossier.tom_tat_phuong_an = gop.tom_tat_phuong_an

    nhan_xet = raw.get("nhan_xet_dinh_gia")
    if isinstance(nhan_xet, list) and dossier.tham_dinh_gia_tri.thuc_hien_duoc:
        them = [dossier_service.to_str(x) for x in nhan_xet if dossier_service.to_str(x)]
        dossier.tham_dinh_gia_tri.nhan_xet = them + dossier.tham_dinh_gia_tri.nhan_xet
    return len(dossier.danh_gia_rui_ro)


def _checklist_du_phong(dossier: Dossier) -> None:
    """Khi kho văn bản trống, vẫn phải có checklist — lấy từ danh mục chuẩn."""
    if dossier.danh_muc_ho_so:
        return
    from ..schemas import ChecklistItem

    mau: list[ProvidedDoc] = readiness.danh_muc_giay_to(dossier.ben_vay.loai_hinh)
    dossier.danh_muc_ho_so = [
        ChecklistItem(
            nhom=g.nhom, ten_tai_lieu=g.ten, bat_buoc=g.bat_buoc,
            can_cu_phap_ly="", ghi_chu=g.can_cu or "",
        )
        for g in mau
    ]


def _kiem_tra_cheo(dossier: Dossier) -> list[str]:
    """Soi các mâu thuẫn số học mà model hay bỏ sót."""
    canh_bao: list[str] = []

    so_tien = doc_tien(dossier.de_nghi_vay.so_tien)
    tong_khoan_muc = sum(
        x for x in (doc_tien_trong_cau(m) for m in dossier.phuong_an_su_dung_von) if x
    )
    von_tu_co = doc_tien(dossier.de_nghi_vay.von_tu_co) or 0.0
    if so_tien and tong_khoan_muc:
        tong_von = so_tien + von_tu_co
        lech = abs(tong_khoan_muc - tong_von) / tong_von if tong_von else 0
        if lech > 0.15:
            canh_bao.append(
                f"Tổng khoản mục sử dụng vốn ({dinh_dang_tien(tong_khoan_muc)}) lệch "
                f"{round(lech * 100)}% so với tổng nguồn vốn ({dinh_dang_tien(tong_von)}). "
                "Cần rà soát lại phương án sử dụng vốn."
            )

    gia_tri_tsbd = sum(x for x in (doc_tien(t.gia_tri_uoc_tinh) for t in dossier.tai_san_bao_dam) if x)
    if so_tien and gia_tri_tsbd and so_tien > gia_tri_tsbd:
        canh_bao.append(
            f"Số tiền vay ({rut_gon_tien(so_tien)}) lớn hơn tổng giá trị tài sản bảo đảm "
            f"({rut_gon_tien(gia_tri_tsbd)}) — hệ số LTV vượt 100%."
        )

    if dossier.tham_dinh_gia_tri.canh_bao:
        canh_bao.extend(dossier.tham_dinh_gia_tri.canh_bao)

    thieu_can_cu = sum(1 for m in dossier.danh_muc_ho_so if not m.can_cu_phap_ly)
    if dossier.danh_muc_ho_so and thieu_can_cu == len(dossier.danh_muc_ho_so):
        canh_bao.append(
            "Chưa tài liệu nào trong checklist có căn cứ pháp lý trích dẫn — hãy nạp thêm văn bản "
            "pháp luật vào kho rồi lập lại hồ sơ."
        )

    if not canh_bao:
        canh_bao.append("Không phát hiện mâu thuẫn số học giữa các phần của hồ sơ.")
    return canh_bao


def _truy_van(dossier: Dossier, hoi_thoai: str) -> str:
    """Ghép truy vấn tra cứu từ chính nội dung khoản vay, không cần gọi thêm model."""
    b, v = dossier.ben_vay, dossier.de_nghi_vay
    phan = [
        "điều kiện vay vốn hồ sơ đề nghị cấp tín dụng",
        "phương án sử dụng vốn khả thi khả năng trả nợ",
        "tài sản bảo đảm thẩm định hợp đồng tín dụng giải ngân",
        b.loai_hinh, b.nganh_nghe, v.muc_dich_vay, v.phuong_thuc_cho_vay,
    ]
    truy_van = " ".join(p for p in phan if p and p.strip())
    if len(truy_van) < 60 and hoi_thoai:
        truy_van = f"{truy_van} {hoi_thoai[-400:]}"
    return truy_van[:600]


# ------------------------------------------------- chạy không cần stream


def chay_dong_bo(req: DossierPipelineRequest) -> dict[str, Any]:
    """Bản đồng bộ dùng cho test và cho client không hỗ trợ SSE."""
    ket_qua: dict[str, Any] = {"nhat_ky": []}
    for sk in chay(req):
        if sk.loai == "done":
            ket_qua.update(sk.du_lieu)
            ket_qua["trang_thai"] = "xong"
        elif sk.loai == "blocked":
            ket_qua.update(sk.du_lieu)
            ket_qua["trang_thai"] = "chan"
        elif sk.loai == "need_confirm":
            ket_qua.update(sk.du_lieu)
            ket_qua["trang_thai"] = "can_xac_nhan"
        elif sk.loai in ("step", "log"):
            ket_qua["nhat_ky"].append(sk.du_lieu)
    return ket_qua


def kiem_tra_nhanh(dossier_raw: dict[str, Any] | None, ghi_chu: str = "") -> ReadinessReport:
    """Cổng kiểm tra chạy riêng — giao diện gọi mỗi khi khách sửa form."""
    dossier = dossier_service.coerce_dossier(dossier_raw or {})
    dossier.ho_so_cung_cap = readiness.hop_nhat_giay_to(
        dossier.ben_vay.loai_hinh, dossier.ho_so_cung_cap
    )
    return readiness.kiem_tra(
        dossier,
        ghi_chu_tai_chinh=_ghi_chu_tu_yeu_cau(ghi_chu, ("tài chính", "doanh thu", "lợi nhuận", "tài sản")),
        ghi_chu_tsbd=_ghi_chu_tu_yeu_cau(ghi_chu, ("bảo đảm", "thế chấp", "tsbđ", "sổ đỏ", "tài sản")),
        kho_van_ban_trong=not get_store().chunks,
    )
