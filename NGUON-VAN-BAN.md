# Kho văn bản đã nạp vào RAG

33 văn bản · 4.628 đoạn · ~4,0 triệu ký tự — cập nhật 08/08/2026.

Tất cả PDF đều là **bản sắp chữ của Công báo Chính phủ** (`congbao.chinhphu.vn`) hoặc bản
`VBHN-VPQH` trên `datafiles.chinhphu.vn` — có lớp text thật nên bóc tách được đầy đủ
Chương / Mục / Điều / Khoản.

> ⚠️ Không dùng bản PDF "văn bản gốc có chữ ký" trên `vbpl.vn` / `datafiles.chinhphu.vn`
> cho Nghị định và Thông tư: đó là **bản scan kèm OCR hỏng** (mất dấu, vỡ chữ, sai số hiệu),
> nạp vào RAG sẽ không tra cứu được. Đã kiểm tra và loại bỏ toàn bộ.

## Luật

| Văn bản | Phạm vi | Ghi chú |
|---|---|---|
| Luật Các tổ chức tín dụng — hợp nhất `158/VBHN-VPQH` | Đ1–Đ210 | Bản hợp nhất của Luật 32/2024/QH15 |
| Luật Ngân hàng Nhà nước Việt Nam `46/2010/QH12` | Đ1–Đ66 | |
| Bộ luật Dân sự `91/2015/QH13` | Đ1–Đ689 | Hợp đồng vay, biện pháp bảo đảm |
| Luật Đất đai — hợp nhất `133/VBHN-VPQH` | Đ1–Đ260 | Bản hợp nhất của Luật 31/2024/QH15 |
| Luật Nhà ở `27/2023/QH15` | Đ1–Đ198 | |
| Luật Kinh doanh bất động sản `29/2023/QH15` | Đ1–Đ83 | |
| Luật Phòng, chống rửa tiền `14/2022/QH15` | Đ1–Đ66 | |
| Luật Bảo vệ quyền lợi người tiêu dùng `19/2023/QH15` | Đ1–Đ80 | Vay tiêu dùng |
| Luật Doanh nghiệp `59/2020/QH14` | Đ1–Đ218 | Tư cách bên vay là tổ chức |
| Luật Giao dịch điện tử `20/2023/QH15` | Đ1–Đ53 | Hợp đồng tín dụng điện tử |
| Luật `43/2024/QH15` | Đ1–Đ5 | Sửa Đất đai · Nhà ở · KDBĐS · Các TCTD |

## Nghị định

| Văn bản | Phạm vi |
|---|---|
| `21/2021/NĐ-CP` — thi hành BLDS về bảo đảm thực hiện nghĩa vụ | Đ1–Đ62 |
| `99/2022/NĐ-CP` — đăng ký biện pháp bảo đảm | Đ1–Đ60 + phụ lục biểu mẫu |
| `86/2024/NĐ-CP` — mức trích, phương pháp trích lập dự phòng rủi ro | Đ1–Đ22 |
| Chính sách tín dụng nông nghiệp, nông thôn — hợp nhất `17/VBHN-NHNN` | Đ1–Đ27 |
| `19/2023/NĐ-CP` — hướng dẫn Luật Phòng, chống rửa tiền | Đ1–Đ14 |
| `55/2024/NĐ-CP` — hướng dẫn Luật Bảo vệ quyền lợi người tiêu dùng | Đ1–Đ47 |
| `340/2025/NĐ-CP` — xử phạt VPHC lĩnh vực tiền tệ và ngân hàng | Đ1–Đ210 |

## Thông tư Ngân hàng Nhà nước

| Văn bản | Phạm vi |
|---|---|
| Hoạt động cho vay — hợp nhất `21/VBHN-NHNN` (gốc `39/2016/TT-NHNN`) | Đ1–Đ35 |
| `52/2025/TT-NHNN`, `29/2026/TT-NHNN` — sửa TT 39/2016 sau ngày hợp nhất | |
| `43/2016/TT-NHNN` + `18/2019/TT-NHNN` — cho vay tiêu dùng của công ty tài chính | |
| `31/2024/TT-NHNN` — phân loại tài sản có | Đ1–Đ17 |
| `02/2023/TT-NHNN` + `06/2024/TT-NHNN` — cơ cấu lại thời hạn trả nợ, giữ nguyên nhóm nợ | |
| `22/2019/TT-NHNN` + `26/2022` + `25/2026` — giới hạn, tỷ lệ bảo đảm an toàn | |
| `41/2016/TT-NHNN` + `22/2023` — tỷ lệ an toàn vốn | |
| `09/2023/TT-NHNN` — hướng dẫn phòng, chống rửa tiền | Đ1–Đ12 |
| `15/2023/TT-NHNN` — hoạt động thông tin tín dụng | Đ1–Đ23 |

## Nguyên tắc chọn bản

1. **Ưu tiên văn bản hợp nhất (VBHN)** và bỏ các văn bản mà nó đã hợp nhất, để một điều luật
   chỉ xuất hiện ở một chỗ — tránh chiếm chỗ lẫn nhau trong `TOP_K` khi truy hồi.
2. Giữ riêng các văn bản sửa đổi **ban hành sau ngày hợp nhất** (TT 52/2025, TT 29/2026).
3. Bỏ văn bản đã hết hiệu lực: NĐ 88/2019 và NĐ 143/2021 đã được `340/2025/NĐ-CP` thay thế
   từ 09/02/2026; NĐ 55/2015 và NĐ 116/2018 nằm trong `17/VBHN-NHNN`.

## Nạp lại

```powershell
.\.venv\Scripts\python.exe scripts\ingest.py --rebuild
.\.venv\Scripts\python.exe scripts\ingest.py --stats
```
