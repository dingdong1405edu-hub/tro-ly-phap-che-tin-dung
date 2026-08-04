# Triển khai (Deploy)

Dự án chạy được ở hai nơi: máy cá nhân và Railway.

---

## 1. Chạy trên máy cá nhân

```powershell
.\run.ps1 -Setup      # lần đầu: tạo .venv + cài thư viện
.\run.ps1             # các lần sau
```

Mở http://127.0.0.1:8000

Trước khi chạy, tạo file `.env` từ `.env.example` và điền `GROQ_API_KEY`
(lấy miễn phí tại https://console.groq.com/keys).

---

## 2. Deploy lên Railway

### Cấu hình đã có sẵn trong repo

| File | Vai trò |
|---|---|
| `railway.json` | Builder Nixpacks, lệnh khởi động, health check `/api/health` |
| `Procfile` | Lệnh khởi động dự phòng |
| `.python-version` | Ghim Python 3.11 |
| `requirements.txt` | Thư viện Python |

Lệnh khởi động trên Railway:

```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

`$PORT` do Railway cấp — **không** hardcode 8000 trên môi trường production.

### Biến môi trường cần đặt trên Railway

| Biến | Bắt buộc | Ghi chú |
|---|---|---|
| `GROQ_API_KEY` | ✅ | Thiếu key thì phần chat và sinh hồ sơ trả về lỗi 503 |
| `GROQ_MODEL` | – | Mặc định `llama-3.3-70b-versatile` |
| `GROQ_FAST_MODEL` | – | Mặc định `llama-3.1-8b-instant` |
| `TEMPERATURE` | – | Mặc định `0.15` |
| `MAX_TOKENS` | – | Mặc định `2048` |
| `EMBEDDING_BACKEND` | – | `tfidf` cho bản deploy nhẹ (không cần torch) |
| `TOP_K` / `CANDIDATE_K` | – | Số đoạn văn bản đưa vào ngữ cảnh |

### Lưu trữ dữ liệu

Container trên Railway có ổ đĩa tạm — file luật tải lên sẽ **mất sau mỗi lần
deploy lại** nếu không gắn volume. Repo này được deploy kèm một volume gắn tại
`/app/data`, nên `data/raw_laws`, `data/index`, `data/exports` được giữ lại
qua các lần deploy.

### Font tiếng Việt cho PDF

Bộ font DejaVu Sans được đóng gói sẵn trong `app/pdfout/fonts/` để chức năng
xuất PDF hồ sơ hiển thị đúng dấu tiếng Việt trên container Linux (image gốc
không cài sẵn font TTF nào). Font DejaVu dùng giấy phép tự do (Bitstream Vera
License), được phép phân phối kèm.
