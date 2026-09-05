# Starts the EchoSphere API against a local SQLite file (no Docker/Postgres needed),
# using a local Ollama model for the LLM layer (no cloud API key needed).
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "apps\api")
$env:DATABASE_URL = "sqlite+aiosqlite:///./demo_run.db"
$env:REDIS_URL = ""
$env:TTS_PROVIDER = "mock"
$env:LLM_PROVIDER = "ollama"
$env:OLLAMA_MODEL_EXTRACT = "llama3.1:8b"
$env:OLLAMA_MODEL_SUMMARY = "llama3.1:8b"
& ".\.venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
