"""Nạp văn bản luật vào chỉ mục từ dòng lệnh.

Ví dụ:
    python scripts/ingest.py                     # nạp toàn bộ data/raw_laws (giữ chỉ mục cũ)
    python scripts/ingest.py --rebuild           # xoá chỉ mục cũ rồi nạp lại từ đầu
    python scripts/ingest.py --path D:/luat      # nạp từ thư mục khác
    python scripts/ingest.py --file luat.pdf     # nạp đúng một file
    python scripts/ingest.py --stats             # chỉ xem thống kê chỉ mục
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.rag import pipeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Nạp văn bản pháp luật vào chỉ mục RAG")
    ap.add_argument("--path", type=str, default=None, help="Thư mục chứa file luật")
    ap.add_argument("--file", type=str, default=None, help="Nạp đúng một file")
    ap.add_argument("--rebuild", action="store_true", help="Xoá chỉ mục cũ trước khi nạp")
    ap.add_argument("--stats", action="store_true", help="Chỉ hiển thị thống kê")
    args = ap.parse_args()

    store = pipeline.get_store()

    if args.stats:
        print("Thống kê chỉ mục:")
        for k, v in store.stats().items():
            print(f"  {k:14}: {v}")
        print(f"\n{len(store.documents)} văn bản:")
        for d in store.documents.values():
            print(f"  - {d['doc_title'][:80]:80} | {d['n_chunks']:4} đoạn | {d['file_name']}")
        return 0

    if args.file:
        f = Path(args.file)
        if not f.exists():
            print(f"Không thấy file: {f}", file=sys.stderr)
            return 1
        if f.parent.resolve() != settings.raw_dir.resolve():
            f = pipeline.save_upload(f.name, f.read_bytes())
            print(f"Đã sao chép vào {f}")
        info, warns = pipeline.ingest_file(f)
        for w in warns:
            print(f"  [!] {w}")
        print(f"Đã nạp: {info.doc_title} ({info.n_chunks} đoạn)")
        print(f"Tổng: {len(store.chunks)} đoạn / {len(store.documents)} văn bản")
        return 0

    directory = Path(args.path) if args.path else settings.raw_dir
    print(f"Đang quét: {directory}")
    result = pipeline.ingest_directory(directory, rebuild=args.rebuild)

    for d in result.documents:
        print(f"  [OK] {d.file_name:45} -> {d.n_chunks:4} đoạn | {d.doc_title[:60]}")
    for w in result.warnings:
        print(f"  [!]  {w}")
    for s in result.skipped:
        print(f"  [X]  {s}")

    print(f"\nHoàn tất: {len(result.documents)} văn bản, tổng {result.total_chunks} đoạn.")
    if not result.documents:
        print(f"Chưa có file nào. Hãy copy file luật (.pdf/.docx/.txt) vào: {settings.raw_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
