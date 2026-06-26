#requires -RunAsAdministrator
# Register the Talk_To_Ex fine-tune worker as a logon Scheduled Task that runs AS
# THE USER (so it has the SSH keys for WAVE + atlas) and start it now. ASCII-only
# (PS 5.1 reads no-BOM .ps1 as ANSI). Run elevated.
$ErrorActionPreference = 'Continue'
$log = Join-Path $PSScriptRoot 'worker-task.log'
"setup @ $(Get-Date -Format o)" | Out-File $log

$cmd  = 'B:\Coding\Talk To Ex\ops\services\run-worker.cmd'
$user = "$env:USERDOMAIN\$env:USERNAME"
"user: $user" | Out-File $log -Append

$action    = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$cmd`""
$trigger   = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -Hidden

try {
    Register-ScheduledTask -TaskName 'TalkToExWorker' -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null
    "registered" | Out-File $log -Append
    Start-ScheduledTask -TaskName 'TalkToExWorker'
    "started" | Out-File $log -Append
} catch {
    "FAILED: $_" | Out-File $log -Append
}
Start-Sleep -Seconds 5
(Get-ScheduledTask -TaskName 'TalkToExWorker' -ErrorAction SilentlyContinue |
    Get-ScheduledTaskInfo | Select-Object LastRunTime, LastTaskResult, State | Out-String) | Out-File $log -Append
"DONE" | Out-File $log -Append
