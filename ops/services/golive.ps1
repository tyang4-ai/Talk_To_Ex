#requires -RunAsAdministrator
# One elevated pass: restart the web service (pick up latest code) AND register +
# start the fine-tune worker as a logon Scheduled Task (runs as the user -> has the
# SSH keys for WAVE + atlas). ASCII-only (PS 5.1 reads no-BOM .ps1 as ANSI).
$ErrorActionPreference = 'Continue'
$log = Join-Path $PSScriptRoot 'golive.log'
"golive @ $(Get-Date -Format o)" | Out-File $log

# 1) Restart the app service.
Restart-Service TalkToEx
Start-Sleep -Seconds 4
(Get-Service cloudflared, TalkToEx | Select-Object Name, Status | Out-String) | Out-File $log -Append

# 2) Kill any loose detached workers so the task owns the single one.
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*run_worker*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
    Where-Object { $_.CommandLine -like '*run-worker.cmd*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

# 3) Register + start the worker scheduled task (as the user, at logon).
$cmd  = 'B:\Coding\Talk To Ex\ops\services\run-worker.cmd'
$user = "$env:USERDOMAIN\$env:USERNAME"
$action    = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$cmd`""
$trigger   = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -Hidden
try {
    Register-ScheduledTask -TaskName 'TalkToExWorker' -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null
    Start-ScheduledTask -TaskName 'TalkToExWorker'
    "worker task registered + started as $user" | Out-File $log -Append
} catch {
    "WORKER TASK FAILED: $_" | Out-File $log -Append
}

Start-Sleep -Seconds 6
try { ("health: " + (Invoke-WebRequest 'http://127.0.0.1:8080/api/health' -UseBasicParsing -TimeoutSec 6).Content) | Out-File $log -Append } catch {}
(Get-ScheduledTask -TaskName 'TalkToExWorker' -ErrorAction SilentlyContinue | Get-ScheduledTaskInfo |
    Select-Object State, LastTaskResult | Out-String) | Out-File $log -Append
"DONE" | Out-File $log -Append
