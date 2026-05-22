# start.ps1 — Dash 개발 서버 실행 스크립트
# 백엔드(FastAPI :8000)와 프론트엔드(Vite :5173)를 각각 새 창으로 실행한다

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "=== Dash 개발 서버 시작 ===" -ForegroundColor Cyan

# ── VoiceBox TTS ─────────────────────────────────────────────────────────
Write-Host "[1/3] VoiceBox TTS 확인 중..." -ForegroundColor Yellow

# 포트 17493 이미 응답하면 실행 중으로 간주
$vbAlreadyUp = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect("127.0.0.1", 17493)
    $tcp.Close()
    $vbAlreadyUp = $true
} catch {}

if ($vbAlreadyUp) {
    Write-Host "  VoiceBox 이미 실행 중 (포트 17493)" -ForegroundColor Green
} else {
    # Tauri 앱의 일반적인 설치 경로 탐색
    $vbCandidates = @(
        "$env:LOCALAPPDATA\Programs\voicebox\voicebox.exe",
        "$env:LOCALAPPDATA\Programs\Voicebox\Voicebox.exe",
        "$env:LOCALAPPDATA\voicebox\voicebox.exe",
        "C:\Program Files\Voicebox\voicebox.exe",
        "C:\Program Files (x86)\Voicebox\voicebox.exe"
    )
    $vbExe = $vbCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ($vbExe) {
        Write-Host "  VoiceBox 시작: $vbExe" -ForegroundColor Yellow
        Start-Process $vbExe -WindowStyle Minimized
        Start-Sleep -Seconds 3
        Write-Host "  VoiceBox 시작 완료" -ForegroundColor Green
    } else {
        Write-Host "  VoiceBox 미설치 또는 경로 미확인 — TTS는 supertone3로 폴백됩니다." -ForegroundColor DarkYellow
    }
}

# ── 백엔드 ──────────────────────────────────────────────────────────────
Write-Host "[2/3] 백엔드 시작 중 (FastAPI :8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "Set-Location '$root\backend'; Write-Host '=== Backend ===' -ForegroundColor Green; py -3.11 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
) -WindowStyle Normal

# 백엔드가 먼저 뜨도록 2초 대기
Start-Sleep -Seconds 2

# ── 프론트엔드 ──────────────────────────────────────────────────────────
Write-Host "[3/3] 프론트엔드 시작 중 (Vite :5173)..." -ForegroundColor Yellow
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
