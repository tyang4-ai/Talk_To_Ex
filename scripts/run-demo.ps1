# Talk_To_Ex — run the full website locally in DEMO mode (no external accounts).
# Builds the frontend if needed, then serves the SPA + API at http://localhost:8080.
# Persona chat replies come from the real local model on atlas (OLLAMA_BASE_URL).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path "$root\frontend\dist\index.html")) {
  Write-Host "Building frontend (one-time)..." -ForegroundColor Cyan
  Push-Location "$root\frontend"; npm install; npm run build; Pop-Location
}

Push-Location "$root\backend"
$env:DEMO_MODE = "true"           # local distill + Stripe/Twilio bypass
$env:PYTHONUTF8 = "1"
Write-Host "`n  Talk_To_Ex demo is starting — open  http://localhost:8080`n" -ForegroundColor Green
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8080
Pop-Location
