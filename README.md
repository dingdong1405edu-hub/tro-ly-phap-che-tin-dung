# ⚖️ Trợ lý Pháp chế Tín dụng

Chatbot tra cứu **quy định pháp luật trong quá trình vay vốn ngân hàng**, chạy trên **Groq API**,
có **RAG** để trả lời kèm trích dẫn Điều — Khoản từ chính bộ luật bạn nạp vào, và một quy trình
**lập hồ sơ vay vốn** hoàn chỉnh: kiểm tra đủ giấy tờ → tra cứu căn cứ pháp lý →
**thẩm định giá trị doanh nghiệp** → chấm điểm tín dụng → vẽ biểu đồ → xuất PDF.

```
┌──────────────┬────────────────────────┬───────────────────────────┬─────────────┐
│ Kho văn bản  │ Hỏi đáp có trích dẫn   │ Agent lập hồ sơ vay vốn   │ Hồ sơ mẫu   │
│ (upload PDF) │ (streaming từ Groq)    │ (11 chặng, có cổng chặn)  │ (tham khảo) │
└──────────────┴────────────────────────┴───────────────────────────┴─────────────┘
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

Mở trình duyệt: **http://127.0.0.1:8000** (trang giới thiệu) — ứng dụng nằm ở
**http://127.0.0.1:8000/app**. Lần chạy đầu tiên, hệ thống yêu cầu tạo **tài khoản quản trị viên**.

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

## 3. Lập hồ sơ vay vốn

Tab **Hồ sơ vay vốn** chạy quy trình 4 bước. Điểm khác biệt: hệ thống **chỉ sinh hồ sơ khi đầu vào
đã đủ** — thiếu thì dừng lại và nói rõ thiếu gì, thay vì đưa ra một bộ hồ sơ nửa vời.

**Bước 1 — Nhập hồ sơ.** Điền thông tin khách hàng, nhu cầu vay, phương án sử dụng vốn, số liệu
tài chính, tài sản bảo đảm, và **tích những giấy tờ bạn đã có**. Danh mục giấy tờ tự đổi theo loại
hình khách hàng (cá nhân / hộ kinh doanh khác với doanh nghiệp). Cột phải hiển thị **cổng kiểm tra
điều kiện** cập nhật theo thời gian thực: còn thiếu bao nhiêu mục bắt buộc, thuộc nhóm nào.

**Bước 2 — Agent lập hồ sơ.** Quy trình 11 chặng, hiển thị trực tiếp việc đang làm ở từng chặng:

| # | Chặng | Nội dung |
|---|---|---|
| 1 | Tiếp nhận và chuẩn hoá dữ liệu | Quy đổi "5 tỷ" → `5.000.000.000`, "60 tháng" → 60 kỳ |
| 2 | **Kiểm tra tính đầy đủ** | **Cổng chặn** — thiếu mục bắt buộc là dừng, không sinh hồ sơ |
| 3 | Trích xuất dữ liệu từ mô tả tự do | Bóc tài sản bảo đảm, số liệu tài chính từ đoạn văn khách viết |
| 4 | Tra cứu căn cứ pháp lý | Tìm điều khoản chi phối khoản vay trong kho văn bản đã nạp |
| 5 | Phân tích chỉ số tài chính | 12 chỉ số kèm ngưỡng tham chiếu và đánh giá |
| 6 | **Thẩm định giá trị doanh nghiệp** | Tài sản thuần · chiết khấu dòng tiền · so sánh thị trường |
| 7 | Lập lịch trả nợ và dòng tiền | Chia gốc lãi theo năm, tính DSCR từng kỳ |
| 8 | Soạn danh mục hồ sơ phải nộp | Checklist tài liệu kèm căn cứ pháp lý tương ứng |
| 9 | Đánh giá rủi ro và chấm điểm | Nhận diện rủi ro, chấm điểm tín dụng 0–100, xếp hạng |
| 10 | Dựng biểu đồ minh hoạ | 7 biểu đồ từ chính số liệu đã tính |
| 11 | Kiểm tra chéo và hoàn tất | Soi mâu thuẫn số học giữa các phần của hồ sơ |

Nếu chưa đủ điều kiện, bước 2 hiện **màn cảnh báo**: từng mục còn thiếu, **vì sao cần**, **cách bổ
sung**, và bấm vào là nhảy thẳng tới ô nhập tương ứng. Với các mục mức "quan trọng" (không chặn),
hệ thống hỏi xác nhận trước khi chạy tiếp.

**Bước 3 — Rà soát.** Xem kết quả thẩm định (giá trị doanh nghiệp, điểm tín dụng, chỉ số tài chính,
biểu đồ) và sửa trực tiếp mọi trường của hồ sơ.

**Bước 4 — Xuất hồ sơ.** Xem trước hoặc tải PDF. File cũng được lưu tại `data/exports/`.

### Thẩm định giá trị doanh nghiệp

Toàn bộ khối này **tính bằng Python thuần, không nhờ model sinh số**. Mô hình định giá:

- **Tài sản thuần (NAV)** — tổng tài sản trừ nợ phải trả, trọng số 30%.
- **Chiết khấu dòng tiền (DCF)** — dự báo 5 năm + giá trị cuối kỳ theo Gordon, chiết khấu bằng
  WACC tính từ chính cơ cấu vốn của khách hàng, trọng số 45%.
- **So sánh thị trường** — P/E và EV/EBITDA tham chiếu nhóm SME chưa niêm yết, trọng số 25%.

Kết luận là bình quân gia quyền; phương pháp nào thiếu dữ liệu thì bị loại và trọng số phân bổ lại.
**Mọi giả định** (Re, Rd, WACC, tăng trưởng, hệ số tham chiếu) đều được in ra kèm căn cứ để cán bộ
thẩm định kiểm chứng được từng con số.

### Hồ sơ mẫu

Tab **★ Hồ sơ mẫu** có sẵn một bộ hồ sơ hoàn chỉnh của doanh nghiệp giả định (Công ty TNHH Vận tải
Đông Dương, vay 5 tỷ trong 60 tháng): 12 mục nội dung, thẩm định giá trị doanh nghiệp đầy đủ 3
phương pháp, 12 chỉ số tài chính, 23 tài liệu trong checklist, 10 căn cứ pháp lý, 7 biểu đồ.
Có nút **xem bản PDF**, **tải JSON** và **nạp thẳng dữ liệu đó vào form của bạn** để sửa lại theo
khách hàng thật.

Phần thẩm định trong hồ sơ mẫu **không viết cứng** mà chạy qua đúng engine của hệ thống, nên nó
luôn phản ánh những gì khách hàng thật sẽ nhận được.

> Hồ sơ đang nhập dở được lưu tự động trong trình duyệt. Có thể **Lưu JSON / Nhập JSON**
> để chuyển hồ sơ giữa các máy.

### Giao diện

| Đường dẫn | Nội dung |
|---|---|
| `/` | Trang giới thiệu — năng lực, quy trình, cơ chế chống suy diễn, hướng dẫn triển khai |
| `/app` | Ứng dụng: tra cứu luật · hồ sơ vay vốn · hồ sơ mẫu |
| `/app#sample` | Mở thẳng tab hồ sơ mẫu |
| `/docs` | Tài liệu API tự sinh |

Toàn bộ icon là **SVG dựng sẵn** trong một sprite nhúng ở đầu mỗi file HTML (không dùng emoji,
không tải từ CDN). Nút mặt trời / mặt trăng ở góc phải đổi giữa **giao diện sáng và tối**;
lựa chọn được ghi nhớ, lần đầu vào thì theo thiết lập của máy. Bảng màu, biểu đồ SVG và mọi bảng
biểu đều đổi theo. Ở khổ hẹp, bảng bên thu lại sau nút menu; trong tab hồ sơ, bảng bên tự ẩn để
form dùng hết bề ngang.

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
│   ├── chat_service.py     Viết lại truy vấn → truy hồi → dựng prompt
│   ├── dossier_service.py  Sinh hồ sơ JSON, chuẩn hoá, giữ dữ liệu người dùng nhập
│   ├── numbers.py          Đọc/viết số tiền tiếng Việt, đọc số thành chữ
│   ├── readiness.py        Cổng kiểm tra đủ giấy tờ & thông tin (chặn khi thiếu)
│   ├── valuation.py        Định giá 3 phương pháp, chỉ số tài chính, lịch trả nợ, chấm điểm
│   └── dossier_pipeline.py Quy trình 11 chặng, phát sự kiện tiến độ ra SSE
├── samples/
│   └── ho_so_mau.py        Hồ sơ vay vốn mẫu (chạy qua đúng engine thẩm định)
└── pdfout/
    ├── fonts.py            Dò font TTF có dấu tiếng Việt
    ├── charts.py           Vẽ biểu đồ vector cho PDF
    └── dossier_pdf.py      Dựng PDF (ReportLab) + đánh số trang

frontend/                  Không cần build, không phụ thuộc npm
├── landing.html           Trang giới thiệu (phục vụ ở "/")
├── landing.css            Style riêng của trang giới thiệu
├── index.html             Vỏ ứng dụng + sprite icon SVG + màn đăng nhập
├── base.css               Token màu/chữ, reset, nút, ô nhập, icon (dùng chung)
├── styles.css             Giao diện ứng dụng
├── auth.js                Đăng nhập / đăng xuất, khoá màn hình khi hết phiên
├── app.js                 Toàn bộ logic 3 khu vực làm việc
└── favicon.svg
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
| `POST` | `/api/dossier/readiness` | Cổng kiểm tra: hồ sơ đã đủ điều kiện lập chưa |
| `GET` | `/api/dossier/required-docs` | Danh mục giấy tờ tối thiểu theo loại hình khách hàng |
| `POST` | `/api/dossier/pipeline/stream` | **Quy trình 11 chặng dạng SSE** (`plan` → `step`/`log` → `done`\|`blocked`) |
| `POST` | `/api/dossier/pipeline` | Như trên nhưng chạy một lần, trả JSON |
| `GET` | `/api/dossier/sample` | Hồ sơ vay vốn mẫu (JSON) |
| `GET` | `/api/dossier/sample/pdf` | Hồ sơ vay vốn mẫu (PDF) |
| `POST` | `/api/dossier/generate` | Sinh hồ sơ JSON từ hội thoại (bản cũ, một lượt) |
| `POST` | `/api/dossier/export` | Xuất PDF (tải về) |
| `POST` | `/api/dossier/preview` | Xuất PDF (xem trên trình duyệt) |

Sự kiện SSE của pipeline: `plan` (danh sách chặng) · `step` (trạng thái từng chặng) · `log`
(việc Agent đang làm) · `sources` (điều khoản đã tra) · `partial` (hồ sơ giữa chừng) ·
`blocked` (thiếu mục bắt buộc, dừng) · `need_confirm` (thiếu mục quan trọng, chờ xác nhận) ·
`done` · `error`.

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
- **Không đủ đầu vào thì không có đầu ra.** Cổng kiểm tra ở chặng 2 chặn hẳn việc sinh hồ sơ khi
  còn thiếu thông tin hoặc giấy tờ bắt buộc — tránh việc model "lấp chỗ trống" bằng nội dung tự nghĩ.
- **Toàn bộ số liệu thẩm định do Python tính, không do model sinh.** Chỉ số tài chính, định giá
  doanh nghiệp, lịch trả nợ, DSCR, điểm tín dụng đều là công thức tường minh; model chỉ được giao
  việc *diễn giải* kết quả đã tính và bị yêu cầu copy đúng con số.
- Chặng cuối **kiểm tra chéo số học**: tổng khoản mục sử dụng vốn so với tổng nguồn vốn, dư nợ so
  với giá trị tài sản bảo đảm — lệch quá ngưỡng là cảnh báo ngay trên giao diện.

> Đây vẫn là công cụ tham khảo. Mọi nội dung cần được cán bộ pháp chế / tín dụng rà soát
> trước khi sử dụng chính thức. Kết quả định giá không thay thế chứng thư của tổ chức thẩm định
> giá độc lập.

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
