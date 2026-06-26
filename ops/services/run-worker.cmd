@echo off
REM Talk_To_Ex out-of-process job worker (processes the queued fine-tune jobs).
REM MUST run as the logged-in USER (not LocalSystem) so it has the SSH keys for
REM WAVE (training) + atlas (serving). Launched by the TalkToExWorker scheduled
REM task at logon. Reads backend/.env (FINETUNE_BACKEND=wave).
cd /d "B:\Coding\Talk To Ex\backend"
if not exist "..\logs" mkdir "..\logs"
".venv\Scripts\python.exe" -m app.jobs.run_worker >> "..\logs\worker.log" 2>&1
