# EchoSphere demo launcher — Windows PowerShell.
# Starts the API (SQLite-backed, no Docker/Postgres needed) and the web dashboard,
# each in their own console window so you can see logs, then seeds the demo incident.
#
# Usage (from repo root):
#   .\start-demo.ps1
# Re-run any time - seeding is idempotent, it reuses "payment-001" instead of creating
# a new incident.

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

Write-Host "API is up. Seeding demo incident payment-001..." -ForegroundColor Cyan
& "$root\apps\api\.venv\Scripts\python.exe" "$root\demo\seed.py" --incident payment-001 --api-url http://localhost:8000 --replay-rate 30

Write-Host ""
Write-Host "Done. Dashboard: http://localhost:5173  (incident id: payment-001)" -ForegroundColor Green
Write-Host "API docs:        http://localhost:8000/docs" -ForegroundColor Green
