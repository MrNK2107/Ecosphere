# Starts the EchoSphere API against a local SQLite file (no Docker/Postgres needed),
# using a local Ollama model for the LLM layer (no cloud API key needed).
$root = Split-Path -Parent $PSScriptRoot

# Load repo-root .env (AGORA_*, DEEPGRAM_API_KEY, etc.) into the process environment.
# Explicit assignments below still take precedence since they're set after this loop.
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$' -and $_ -notmatch '^\s*#') {
            $name, $value = $Matches[1], $Matches[2]
            $isPlaceholder = ($value -match '(?i)your[_-]') -or ($value -match '(?i)example\.com') -or ($value -eq "")
            if (-not $isPlaceholder) {
                [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
            }
        }
    }
}

Set-Location (Join-Path $root "apps\api")
$env:DATABASE_URL = "sqlite+aiosqlite:///./demo_run.db"
$env:REDIS_URL = ""
$env:TTS_PROVIDER = "mock"
$env:LLM_PROVIDER = "ollama"
$env:OLLAMA_MODEL_EXTRACT = "llama3.1:8b"
$env:OLLAMA_MODEL_SUMMARY = "llama3.1:8b"
& ".\.venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
