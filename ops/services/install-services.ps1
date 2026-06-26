#requires -RunAsAdministrator
<#
  Ex.Change (Talk To Ex) — install the public stack as TRUE Windows services on
  the 4090 desktop, so the site survives reboots / logoff / crashes with no
  terminal open. Idempotent: re-running reinstalls cleanly.

  Two services:
    1. cloudflared  -> the named tunnel (ex.yang9ru.online -> 127.0.0.1:8080)
    2. TalkToEx     -> the FastAPI app (uvicorn :8080) wrapped by NSSM

  Run ONCE in an elevated PowerShell:
    powershell -ExecutionPolicy Bypass -File "B:\Coding\Talk To Ex\ops\services\install-services.ps1"

  The Cloudflare tunnel token is read from backend\.env at runtime (never printed,
  never stored in this script).
#>
# NOTE: 'Continue', not 'Stop'. cloudflared/nssm/winget write normal INFO logs to
# STDERR, and under PS 5.1 'Stop' turns any native-exe stderr line into a fake
# terminating error. We validate explicitly (throw on path/exit-code failures) and
# verify service state at the end instead.
$ErrorActionPreference = 'Continue'
Start-Transcript -Path (Join-Path $PSScriptRoot 'install.log') -Force | Out-Null
try {
    $RepoRoot    = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)    # script is in ops\services\ -> ...\Talk To Ex
    $Backend     = Join-Path $RepoRoot 'backend'
    $Python      = Join-Path $Backend  '.venv\Scripts\python.exe'
    $EnvFile     = Join-Path $Backend  '.env'
    $Cloudflared = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
    $LogDir      = Join-Path $RepoRoot 'logs'
    New-Item -ItemType Directory -Force $LogDir | Out-Null

    Write-Host "== Ex.Change service install ==" -ForegroundColor Cyan
    Write-Host "Repo:    $RepoRoot"
    Write-Host "Python:  $Python"

    if (-not (Test-Path $Python))      { throw "venv python not found: $Python" }
    if (-not (Test-Path $EnvFile))     { throw ".env not found: $EnvFile" }
    if (-not (Test-Path $Cloudflared)) { throw "cloudflared.exe not found: $Cloudflared" }

    # --- read the tunnel token from .env (never printed) ---
    $token = $null
    foreach ($line in Get-Content $EnvFile) {
        if ($line -match '^\s*CLOUDFLARE_TUNNEL_TOKEN\s*=\s*(.+?)\s*$') {
            $token = $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    if ([string]::IsNullOrWhiteSpace($token)) { throw "CLOUDFLARE_TUNNEL_TOKEN not set in $EnvFile" }
    Write-Host "Tunnel token: loaded from .env (length $($token.Length))"

    # --- stop loose background processes so the services can bind cleanly ---
    Write-Host "`nStopping any loose cloudflared / uvicorn processes..." -ForegroundColor Yellow
    Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    try {
        Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    } catch {}
    Start-Sleep -Seconds 1

    # =================================================================
    # 1) cloudflared -> Windows service (token-based, auto-start at boot)
    # =================================================================
    if (Get-Service cloudflared -ErrorAction SilentlyContinue) {
        Write-Host "`ncloudflared service exists; reinstalling..." -ForegroundColor Yellow
        Stop-Service cloudflared -ErrorAction SilentlyContinue
        & $Cloudflared service uninstall 2>&1 | Out-Host
        Start-Sleep -Seconds 2
    }
    Write-Host "Installing cloudflared service..." -ForegroundColor Green
    & $Cloudflared service install $token 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "cloudflared service install returned exit $LASTEXITCODE" }
    Start-Sleep -Seconds 2
    Set-Service cloudflared -StartupType Automatic
    Start-Service cloudflared -ErrorAction SilentlyContinue

    # =================================================================
    # 2) Ex.Change app (uvicorn) -> Windows service via NSSM
    # =================================================================
    $nssm = (Get-Command nssm -ErrorAction SilentlyContinue).Source
    if (-not $nssm) {
        Write-Host "`nInstalling NSSM via winget..." -ForegroundColor Green
        try { winget install --id NSSM.NSSM -e --accept-source-agreements --accept-package-agreements | Out-Host } catch {}
        $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
        $nssm = (Get-Command nssm -ErrorAction SilentlyContinue).Source
    }
    if (-not $nssm) {
        Write-Host "winget path failed; downloading NSSM directly..." -ForegroundColor Yellow
        $z = Join-Path $env:TEMP 'nssm.zip'; $d = Join-Path $env:TEMP 'nssm-extract'
        Invoke-WebRequest 'https://nssm.cc/release/nssm-2.24.zip' -OutFile $z
        Expand-Archive $z $d -Force
        $nssm = (Get-ChildItem $d -Recurse -Filter nssm.exe |
                 Where-Object { $_.FullName -match 'win64' } | Select-Object -First 1).FullName
    }
    if (-not $nssm) { throw "could not obtain nssm.exe" }
    Write-Host "NSSM: $nssm"

    $svc = 'TalkToEx'
    if (Get-Service $svc -ErrorAction SilentlyContinue) {
        Write-Host "$svc service exists; removing to reinstall..." -ForegroundColor Yellow
        & $nssm stop $svc 2>&1 | Out-Host
        & $nssm remove $svc confirm 2>&1 | Out-Host
        Start-Sleep -Seconds 1
    }
    $uviArgs = '-m uvicorn app.main:app --host 127.0.0.1 --port 8080 --proxy-headers --forwarded-allow-ips=*'
    & $nssm install $svc $Python $uviArgs
    & $nssm set $svc AppDirectory $Backend
    & $nssm set $svc AppStdout (Join-Path $LogDir 'app.out.log')
    & $nssm set $svc AppStderr (Join-Path $LogDir 'app.err.log')
    & $nssm set $svc AppRotateFiles 1
    & $nssm set $svc AppRotateBytes 10485760
    & $nssm set $svc AppEnvironmentExtra 'PYTHONUTF8=1'
    & $nssm set $svc AppExit Default Restart
    & $nssm set $svc AppRestartDelay 3000
    & $nssm set $svc Start SERVICE_AUTO_START
    & $nssm set $svc DisplayName 'Ex.Change (Talk To Ex) API'
    & $nssm set $svc Description 'FastAPI app serving ex.yang9ru.online (uvicorn :8080)'
    & $nssm start $svc

    Start-Sleep -Seconds 4
    Write-Host "`n== Status ==" -ForegroundColor Cyan
    Get-Service cloudflared, $svc | Select-Object Name, Status, StartType | Format-Table -AutoSize | Out-Host
    Write-Host "Local health:" -ForegroundColor Cyan
    try {
        (Invoke-WebRequest 'http://127.0.0.1:8080/api/health' -UseBasicParsing -TimeoutSec 6).Content | Out-Host
    } catch { Write-Host "health check failed: $_" -ForegroundColor Red }

    Write-Host "`nDONE. Both services auto-start at boot. Manage with:" -ForegroundColor Green
    Write-Host "  Get-Service cloudflared, TalkToEx"
    Write-Host "  Restart-Service TalkToEx     # after a code update"
}
catch {
    Write-Host "INSTALL FAILED: $_" -ForegroundColor Red
    throw
}
finally {
    Stop-Transcript | Out-Null
}
