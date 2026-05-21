# start.ps1 — Dash 개발 서버 실행 스크립트
# 백엔드(FastAPI :8000)와 프론트엔드(Vite :5173)를 각각 새 창으로 실행한다

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "=== Dash 개발 서버 시작 ===" -ForegroundColor Cyan

# ── 백엔드 ──────────────────────────────────────────────────────────────
Write-Host "[1/2] 백엔드 시작 중 (FastAPI :8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "Set-Location '$root\backend'; Write-Host '=== Backend ===' -ForegroundColor Green; py -3.11 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
) -WindowStyle Normal

# 백엔드가 먼저 뜨도록 2초 대기
Start-Sleep -Seconds 2

# ── 프론트엔드 ──────────────────────────────────────────────────────────
Write-Host "[2/2] 프론트엔드 시작 중 (Vite :5173)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "Set-Location '$root\frontend'; Write-Host '=== Frontend ===' -ForegroundColor Green; npm run dev"
) -WindowStyle Normal

Write-Host ""
Write-Host "완료! 잠시 후 브라우저에서 접속하세요:" -ForegroundColor Green
Write-Host "  http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "종료하려면 stop.ps1 을 실행하세요." -ForegroundColor Gray
