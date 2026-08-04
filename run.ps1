# Khởi chạy hệ thống Trợ lý Pháp chế Tín dụng
# Cách dùng:  .\run.ps1          (chạy server)
#             .\run.ps1 -Setup   (tạo venv + cài thư viện rồi chạy)

param(
    [switch]$Setup,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Setup) {
    if (-not (Test-Path ".venv")) {
        Write-Host "==> Tạo môi trường ảo .venv" -ForegroundColor Cyan
        python -m venv .venv
    }
    Write-Host "==> Cài đặt thư viện" -ForegroundColor Cyan
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

if (-not (Test-Path ".env")) {
    Write-Host "!! Chưa có file .env — đang tạo từ .env.example" -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "   Hãy mở .env và điền GROQ_API_KEY (lấy tại https://console.groq.com/keys)" -ForegroundColor Yellow
}

$python = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }

Write-Host "==> Chạy tại http://127.0.0.1:$Port" -ForegroundColor Green
& $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
