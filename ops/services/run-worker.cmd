@echo off
REM Talk_To_Ex out-of-process job worker (processes the queued fine-tune jobs).
REM MUST run as the logged-in USER (not LocalSystem) so it has the SSH keys for
REM WAVE (training) + atlas (serving). Launched by the TalkToExWorker scheduled
REM task at logon. Reads backend/.env (FINETUNE_BACKEND=wave).
cd /d "B:\Coding\Talk To Ex\backend"
if not exist "..\logs" mkdir "..\logs"
REM Python's FileHandler owns worker.log; redirect raw stdout/stderr (startup
REM errors) to a SEPARATE file to avoid a double-open lock on worker.log.
".venv\Scripts\python.exe" -m app.jobs.run_worker >> "..\logs\worker.console.log" 2>&1
