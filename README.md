# ⚖️ Trợ lý Pháp chế Tín dụng

Chatbot tra cứu **quy định pháp luật trong quá trình vay vốn ngân hàng**, chạy trên **Groq API**,
có **RAG** để trả lời kèm trích dẫn Điều — Khoản từ chính bộ luật bạn nạp vào, và
**xuất PDF hồ sơ gọi vốn** hoàn chỉnh.

```
┌──────────────┬────────────────────────────┬──────────────────┐
│ Kho văn bản  │  Hỏi đáp có trích dẫn      │ Hồ sơ gọi vốn    │
│ (upload PDF) │  (streaming từ Groq)       │ (form → PDF)     │
└──────────────┴────────────────────────────┴──────────────────┘
```

> **🌐 Bản đang chạy:** https://web-production-6a7ed.up.railway.app
> Mỗi lần đẩy code lên nhánh `main`, Railway tự build và deploy lại.
> Hướng dẫn triển khai chi tiết: [DEPLOY.md](DEPLOY.md)

---

## 1. Chạy trong 3 bước

```powershell
# Bước 1 — cài đặt (chỉ làm một lần)
.\run.ps1 -Setup

# Bước 2 — mở file .env vừa được tạo, điền key lấy từ https://console.groq.com/keys
#          GROQ_API_KEY=gsk_...

# Bước 3 — chạy
.\run.ps1
```

Mở trình duyệt: **http://127.0.0.1:8000**

<details>
<summary>Chạy thủ công (không dùng run.ps1)</summary>

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env      # rồi điền GROQ_API_KEY
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```
</details>

---

## 2. Nạp bộ luật vào RAG

Có 3 cách, chọn cách nào cũng được:

| Cách | Thao tác |
|---|---|
| **Kéo thả** | Thả file vào ô upload ở sidebar trái |
| **Copy thư mục** | Copy file vào `data/raw_laws/` rồi bấm nút **⟳** trên giao diện |
| **Dòng lệnh** | `python scripts/ingest.py --rebuild` |

**Định dạng hỗ trợ:** `.pdf` `.docx` `.txt` `.md` `.html`
(`.doc` cũ cần mở bằng Word và lưu lại thành `.docx`)

> ⚠️ **PDF scan** (ảnh chụp, không có lớp text) sẽ không bóc tách được — hệ thống sẽ cảnh báo.
> Hãy OCR trước, ví dụ bằng `ocrmypdf input.pdf output.pdf -l vie`.

### Gợi ý văn bản nên nạp cho lĩnh vực vay vốn

- Luật Các tổ chức tín dụng
- Bộ luật Dân sự (phần bảo đảm thực hiện nghĩa vụ, hợp đồng vay)
- Thông tư quy định về hoạt động cho vay của TCTD đối với khách hàng
- Nghị định về giao dịch bảo đảm / đăng ký biện pháp bảo đảm
- Thông tư về phân loại tài sản có, trích lập dự phòng rủi ro
- Thông tư về cơ cấu lại thời hạn trả nợ
- Quy định về lãi suất, phí; Luật Đất đai (phần thế chấp quyền sử dụng đất)

Hệ thống tự nhận diện **số hiệu văn bản**, **Chương / Mục / Điều / Khoản** và cắt chunk theo
đúng cấu trúc đó, nên trích dẫn trả về dạng: `Điều 7, Thông Tư 39/2016/TT-NHNN`.

---

## 3. Xuất PDF hồ sơ gọi vốn

1. Trao đổi với chatbot về khoản vay (khách hàng là ai, vay bao nhiêu, mục đích, tài sản bảo đảm…).
2. Bấm **📋 Hồ sơ gọi vốn** ở góc trên bên phải.
3. Bấm **✨ Tạo hồ sơ từ hội thoại** — AI đọc hội thoại + tra cứu luật rồi điền sẵn form.
4. Rà soát / sửa trực tiếp trên form (mọi trường đều sửa được, thêm/bớt dòng thoải mái).
5. Bấm **👁 Xem trước** hoặc **⬇ Xuất PDF**.

PDF gồm 10 phần: trang bìa · thông tin bên vay · nội dung đề nghị vay · phương án sử dụng vốn
và trả nợ (kèm bảng dòng tiền) · tình hình tài chính · tài sản bảo đảm · **checklist hồ sơ phải nộp
kèm căn cứ pháp lý** · căn cứ pháp lý áp dụng · đánh giá rủi ro · khuyến nghị + khối chữ ký.
Bản PDF cũng được lưu lại tại `data/exports/`.

> Hồ sơ đang nhập dở được lưu tự động trong trình duyệt. Có thể **Lưu JSON / Nhập JSON**
> để chuyển hồ sơ giữa các máy.

---

## 4. Cấu hình (`.env`)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `GROQ_API_KEY` | — | **Bắt buộc.** Lấy tại console.groq.com/keys |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Model trả lời chính |
| `GROQ_FAST_MODEL` | `llama-3.1-8b-instant` | Model nhỏ để viết lại truy vấn |
| `TEMPERATURE` | `0.15` | Tra cứu luật nên để thấp |
| `EMBEDDING_BACKEND` | `auto` | `auto` \| `sentence-transformers` \| `tfidf` \| `none` |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Dùng khi backend là sentence-transformers |
| `CHUNK_MAX_CHARS` | `1600` | Kích thước tối đa mỗi đoạn |
| `TOP_K` | `6` | Số đoạn luật đưa vào ngữ cảnh |

Danh sách model có thể đổi ngay trên giao diện (mục **Cài đặt**) — lấy trực tiếp từ tài khoản Groq.

### Nâng chất lượng tìm kiếm (tuỳ chọn)

Mặc định hệ thống dùng **BM25 + TF-IDF thuần NumPy** — chạy được ngay, không cần cài thêm gì,
và khá mạnh với văn bản luật vì người dùng thường gõ đúng thuật ngữ.

Muốn thêm khả năng hiểu ngữ nghĩa (hỏi "vay tiền mua nhà" ra được "cho vay phục vụ nhu cầu đời sống"):

```powershell
.\.venv\Scripts\python.exe -m pip install sentence-transformers torch
```

Khởi động lại là hệ thống tự dùng. Chỉ mục cũ sẽ được tính lại tự động khi bạn nạp/xoá văn bản,
hoặc chạy `python scripts/ingest.py --rebuild` để tính lại ngay.

---

## 5. Cấu trúc dự án

```
app/
├── config.py              Cấu hình từ .env
├── schemas.py             Pydantic model (chat, nguồn trích dẫn, hồ sơ vay vốn)
├── main.py                FastAPI: route + phục vụ giao diện
├── rag/
│   ├── loader.py          PDF/DOCX/TXT/HTML → text, cảnh báo PDF scan
│   ├── chunker.py         Cắt chunk theo Phần/Chương/Mục/Điều/Khoản + nhận diện số hiệu
│   ├── tokenizer.py       Tách từ tiếng Việt (unigram + bigram + bản không dấu)
│   ├── bm25.py            BM25 Okapi thuần NumPy
│   ├── embedder.py        sentence-transformers hoặc TF-IDF hashing dự phòng
│   ├── store.py           Kho chunk + vector, lưu JSON/NPY
│   ├── retriever.py       Hybrid BM25 + vector, hợp nhất RRF, ưu tiên "Điều X"
│   └── pipeline.py        Điều phối nạp file, singleton store/retriever
├── llm/
│   ├── groq_client.py     chat / chat_stream / chat_json + retry 429
│   └── prompts.py         Toàn bộ prompt tiếng Việt
├── services/
│   ├── chat_service.py    Viết lại truy vấn → truy hồi → dựng prompt
│   └── dossier_service.py Sinh hồ sơ JSON, chuẩn hoá, giữ dữ liệu người dùng nhập
└── pdfout/
    ├── fonts.py           Dò font TTF có dấu tiếng Việt
    └── dossier_pdf.py     Dựng PDF (ReportLab) + đánh số trang

frontend/                  index.html · styles.css · app.js (không cần build)
scripts/ingest.py          CLI nạp luật
data/raw_laws/             File luật gốc
data/index/                Chỉ mục
data/exports/              PDF đã xuất
```

---

## 6. API

| Method | Endpoint | Công dụng |
|---|---|---|
| `GET` | `/api/health` | Trạng thái + thống kê chỉ mục |
| `GET` | `/api/models` | Model khả dụng trên tài khoản Groq |
| `POST` | `/api/chat/stream` | Hỏi đáp dạng SSE (`sources` → `delta`… → `done`) |
| `POST` | `/api/chat` | Hỏi đáp một lần, trả JSON |
| `POST` | `/api/search` | Chỉ truy hồi, không gọi LLM (tiện để debug RAG) |
| `GET` | `/api/documents` | Danh sách văn bản đã nạp |
| `POST` | `/api/documents/upload` | Upload nhiều file |
| `POST` | `/api/documents/reindex` | Quét lại `data/raw_laws` |
| `DELETE` | `/api/documents/{doc_id}` | Xoá 1 văn bản |
| `POST` | `/api/dossier/generate` | Sinh hồ sơ JSON từ hội thoại |
| `POST` | `/api/dossier/export` | Xuất PDF (tải về) |
| `POST` | `/api/dossier/preview` | Xuất PDF (xem trên trình duyệt) |

Tài liệu tương tác: **http://127.0.0.1:8000/docs**

---

## 7. Cách hệ thống chống "chém gió"

- Prompt buộc model **chỉ dùng ngữ cảnh được cấp**, mọi khẳng định phải kèm `[số]` + Điều/Khoản.
- Khi truy hồi không ra kết quả → model được lệnh nói thẳng *"kho văn bản chưa đủ căn cứ"*.
- Khi **chưa nạp văn bản nào** → chuyển sang prompt riêng, bắt buộc gắn nhãn cảnh báo và
  không được trích dẫn số hiệu như thể đã kiểm chứng.
- Mỗi câu trả lời hiển thị **đầy đủ đoạn luật gốc** đã dùng — bấm vào chip `[1]` để nhảy tới nguồn,
  đối chiếu ngay.
- Riêng phần hồ sơ: model bị cấm bịa tên người, số tiền, mã số thuế — trường nào không có dữ liệu
  thì để trống.

> Đây vẫn là công cụ tham khảo. Mọi nội dung cần được cán bộ pháp chế / tín dụng rà soát
> trước khi sử dụng chính thức.

---

## 8. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| `Chưa cấu hình GROQ_API_KEY` | Tạo file `.env` ở thư mục gốc, điền `GROQ_API_KEY=gsk_...`, khởi động lại |
| Trả lời chung chung, không trích dẫn | Chưa nạp văn bản, hoặc PDF là bản scan — kiểm tra số "đoạn đã lập chỉ mục" ở sidebar |
| Upload xong mà `0 đoạn` | PDF scan → cần OCR |
| `Không tìm thấy font TTF hỗ trợ tiếng Việt` | Tải `DejaVuSans.ttf` + `DejaVuSans-Bold.ttf` bỏ vào `app/pdfout/fonts/` |
| Lỗi 429 từ Groq | Hệ thống tự thử lại 3 lần; nếu vẫn lỗi, giảm `TOP_K` hoặc đổi sang model nhỏ hơn |
| Muốn xoá sạch làm lại | `python scripts/ingest.py --rebuild` |
