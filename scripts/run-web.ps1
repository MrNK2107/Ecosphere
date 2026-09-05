# Starts the EchoSphere dashboard dev server.
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "apps\web")
npx vite --host 0.0.0.0 --port 5173
