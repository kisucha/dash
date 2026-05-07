# stop.ps1 — Dash 개발 서버 종료 스크립트
# 1순위: 포트 기반 PID 탐색 후 종료
# 2순위: WMI CommandLine 기반 프로세스 탐색 (포트 PID가 유효하지 않을 때)

Write-Host ""
Write-Host "=== Dash 개발 서버 종료 ===" -ForegroundColor Cyan

# ── 포트 기반 종료 (PID 존재 여부 먼저 확인) ──────────────────────────────

function Stop-ByPort {
  param([int]$Port, [string]$Name)

  $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if (-not $conns) { return $false }

  $killed = $false
  $procIds = $conns.OwningProcess | Sort-Object -Unique

  foreach ($procId in $procIds) {
    # PID 0은 시스템 예약 — 건너뜀
    if ($procId -eq 0) { continue }

    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc) {
      try {
        Stop-Process -Id $procId -Force
        Write-Host "  [종료] $Name (PID $procId, :$Port)" -ForegroundColor Green
        $killed = $true
      } catch {
        Write-Host "  [오류] $Name PID $procId 종료 실패: $_" -ForegroundColor Yellow
      }
    } else {
      # 프로세스는 이미 없지만 TCP 스택이 아직 포트를 점유 중 (Windows 지연 해제)
      # 오류가 아니라 정상 종료된 상태로 처리
      Write-Host "  [완료] $Name (:$Port) — 프로세스 이미 종료됨 (PID $procId)" -ForegroundColor Gray
      $killed = $true
    }
  }
  return $killed
}

# ── WMI CommandLine 기반 추가 탐색 ────────────────────────────────────────

function Stop-ByCommandLine {
  param([string]$Filter, [string]$Name)

  $procs = Get-WmiObject Win32_Process -Filter $Filter -ErrorAction SilentlyContinue
  if (-not $procs) { return $false }

  $killed = $false
  foreach ($p in $procs) {
    try {
      Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
      Write-Host "  [종료] $Name (PID $($p.ProcessId), 이름 기반)" -ForegroundColor Green
      $killed = $true
    } catch {}
  }
  return $killed
}

# ── 백엔드 종료 (포트 8000 → uvicorn python 프로세스) ────────────────────

$backendKilled = Stop-ByPort -Port 8000 -Name "백엔드(FastAPI)"

if (-not $backendKilled) {
  # 포트 탐색 실패 시 uvicorn CommandLine 기반 탐색
  $wmiFilter = "Name = 'python.exe' AND CommandLine LIKE '%uvicorn%'"
  $backendKilled = Stop-ByCommandLine -Filter $wmiFilter -Name "백엔드(FastAPI)"

  if (-not $backendKilled) {
    Write-Host "  [없음] 백엔드(FastAPI) (:8000) — 실행 중이지 않음" -ForegroundColor Gray
  }
}

# ── 프론트엔드 종료 (포트 5173 → node/vite 프로세스) ────────────────────

$frontendKilled = Stop-ByPort -Port 5173 -Name "프론트엔드(Vite)"

if (-not $frontendKilled) {
  # 포트 탐색 실패 시 vite CommandLine 기반 탐색
  $wmiFilter = "Name = 'node.exe' AND CommandLine LIKE '%vite%'"
  $frontendKilled = Stop-ByCommandLine -Filter $wmiFilter -Name "프론트엔드(Vite)"

  if (-not $frontendKilled) {
    Write-Host "  [없음] 프론트엔드(Vite) (:5173) — 실행 중이지 않음" -ForegroundColor Gray
  }
}

Write-Host ""
Write-Host "완료." -ForegroundColor Green
