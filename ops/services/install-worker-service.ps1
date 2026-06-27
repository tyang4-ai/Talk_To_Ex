#requires -RunAsAdministrator
# Run the fine-tune worker as a LocalSystem Windows SERVICE so it survives reboots
# WITHOUT a user login (replaces the logon Scheduled Task). SSH keys: point
# USERPROFILE/HOME at the user's profile so `ssh wave`/`ssh atlas` resolve ~/.ssh.
# ASCII-only (PS 5.1 reads no-BOM .ps1 as ANSI). Run elevated.
$ErrorActionPreference = 'Continue'
$log = Join-Path $PSScriptRoot 'worker-service.log'
"worker-service setup @ $(Get-Date -Format o)" | Out-File $log

$nssm = (Get-Command nssm -ErrorAction SilentlyContinue).Source
if (-not $nssm) { $nssm = "$env:LOCALAPPDATA\Microsoft\WinGet\Links\nssm.exe" }
$py      = "B:\Coding\Talk To Ex\backend\.venv\Scripts\python.exe"
$backend = "B:\Coding\Talk To Ex\backend"
$logs    = "B:\Coding\Talk To Ex\logs"
$up      = $env:USERPROFILE   # the elevating user's profile (holds ~/.ssh)
"nssm: $nssm | userprofile: $up" | Out-File $log -Append

# 0) Make the user's SSH config + keys available to the LocalSystem account: a
# SYSTEM-run ssh reads ~/.ssh from the SYSTEM profile, NOT the user's. Copy them in
# and lock the perms to SYSTEM+Admins (OpenSSH refuses world-readable private keys).
$sysSsh = "C:\Windows\System32\config\systemprofile\.ssh"
New-Item -ItemType Directory -Force $sysSsh | Out-Null
Copy-Item "$up\.ssh\*" $sysSsh -Recurse -Force -ErrorAction SilentlyContinue
icacls $sysSsh /inheritance:r 2>&1 | Out-File $log -Append
icacls $sysSsh /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" 2>&1 | Out-File $log -Append
"copied user .ssh -> systemprofile" | Out-File $log -Append

# 1) Remove the old logon task + any loose workers (the service replaces them).
schtasks /delete /tn TalkToExWorker /f 2>&1 | Out-File $log -Append
Get-CimInstance Win32_Process |
  Where-Object { ($_.Name -in 'python.exe','pythonw.exe','cmd.exe') -and ($_.CommandLine -like '*run_worker*' -or $_.CommandLine -like '*run-worker.cmd*') } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

# 2) (Re)install the service.
$svc = 'TalkToExWorkerSvc'
if (Get-Service $svc -ErrorAction SilentlyContinue) {
  & $nssm stop $svc 2>&1 | Out-File $log -Append
  & $nssm remove $svc confirm 2>&1 | Out-File $log -Append
  Start-Sleep -Seconds 1
}
& $nssm install $svc $py "-m app.jobs.run_worker" 2>&1 | Out-File $log -Append
& $nssm set $svc AppDirectory $backend
& $nssm set $svc AppEnvironmentExtra "USERPROFILE=$up" "HOME=$up" "PYTHONUTF8=1"
& $nssm set $svc AppStdout "$logs\worker.console.log"
& $nssm set $svc AppStderr "$logs\worker.console.log"
& $nssm set $svc AppRotateFiles 1
& $nssm set $svc AppRotateBytes 5242880
& $nssm set $svc Start SERVICE_AUTO_START
& $nssm set $svc AppExit Default Restart
& $nssm set $svc AppRestartDelay 5000
& $nssm set $svc DisplayName "Ex.Change fine-tune worker"
& $nssm set $svc Description "Drains the job queue (distill build + WAVE QLoRA). Runs as LocalSystem."
& $nssm start $svc 2>&1 | Out-File $log -Append

Start-Sleep -Seconds 14
(Get-Service $svc -ErrorAction SilentlyContinue | Select-Object Name, Status, StartType | Out-String) | Out-File $log -Append
"DONE" | Out-File $log -Append
