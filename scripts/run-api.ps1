# Starts the EchoSphere API against a local SQLite file (no Docker/Postgres needed).
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "apps\api")
$env:DATABASE_URL = "sqlite+aiosqlite:///./demo_run.db"
$env:REDIS_URL = ""
$env:TTS_PROVIDER = "mock"
& ".\.venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
