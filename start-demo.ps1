# EchoSphere demo launcher — Windows PowerShell.
# Starts the API (SQLite-backed, no Docker/Postgres needed) and the web dashboard,
# each in their own console window, then replays the incident transcript at a
# realistic pace so the dashboard visibly updates live, utterance by utterance —
# instead of dumping the whole scenario in one second.
#
# Usage (from repo root):
#   .\start-demo.ps1            # realistic pace (~25s total), pauses so you can open the browser first
#   .\start-demo.ps1 -Fast      # instant dump, for quick verification only
#
# Re-run any time - seeding is idempotent, it reuses "payment-001" instead of creating
# a new incident, and re-posting the same segments is a safe no-op.

param(
    [switch]$Fast
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "Starting API on http://localhost:8000 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-File", "$root\scripts\run-api.ps1"

Write-Host "Starting dashboard on http://localhost:5173 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-File", "$root\scripts\run-web.ps1"

Write-Host "Waiting for API to come up..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect("localhost", 8000)
        if ($client.Connected) { $ready = $true }
    } catch {} finally { $client.Close() }
    if ($ready) { break }
}
if (-not $ready) {
    Write-Host "API did not come up after 30s - check the API console window for errors." -ForegroundColor Red
    exit 1
}
Start-Sleep -Seconds 1  # give the app a moment past the socket accept to finish startup

if ($Fast) {
    Write-Host "API is up. Seeding demo incident payment-001 (fast)..." -ForegroundColor Cyan
    & "$root\apps\api\.venv\Scripts\python.exe" "$root\demo\seed.py" --incident payment-001 --api-url http://localhost:8000 --replay-rate 30
} else {
    Write-Host ""
    Write-Host "API and dashboard are up." -ForegroundColor Green
    Write-Host "Open http://localhost:5173 now (incident id: payment-001) - the transcript" -ForegroundColor Yellow
    Write-Host "will start replaying live in 8 seconds, one utterance every couple of seconds," -ForegroundColor Yellow
    Write-Host "so you can watch facts/gaps/actions appear on the dashboard as it happens." -ForegroundColor Yellow
    Start-Sleep -Seconds 8
    Write-Host "Replaying now..." -ForegroundColor Cyan
    & "$root\apps\api\.venv\Scripts\python.exe" "$root\demo\seed.py" --incident payment-001 --api-url http://localhost:8000 --replay-rate 1.5
}

Write-Host ""
Write-Host "Done. Dashboard: http://localhost:5173  (incident id: payment-001)" -ForegroundColor Green
Write-Host "API docs:        http://localhost:8000/docs" -ForegroundColor Green
