<#
  Stand up the QLoRA TRAINER venv on the 4090 (Python 3.12, via uv — already
  installed). Separate from backend/.venv (Python 3.14, no ML wheels). One-shot:

      powershell -ExecutionPolicy Bypass -File ops\finetune\install-train-env.ps1

  ~5-6 GB of wheels; no admin needed. After the first successful train, lock it:
      uv pip freeze --python .venv-train > backend\requirements-train.lock
#>
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # ...\Talk To Ex
$venv = Join-Path $repo '.venv-train'
$req  = Join-Path $repo 'backend\requirements-train.txt'

Write-Host "== QLoRA trainer venv ==" -ForegroundColor Cyan
Write-Host "venv: $venv"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv not found on PATH" }

Write-Host "`nCreating Python 3.12 venv..." -ForegroundColor Green
uv venv --python 3.12 $venv
$py = Join-Path $venv 'Scripts\python.exe'

Write-Host "`nInstalling torch (CUDA 12.4 wheels — ships its own runtime)..." -ForegroundColor Green
uv pip install --python $py torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124

Write-Host "`nInstalling the HF QLoRA stack..." -ForegroundColor Green
uv pip install --python $py -r $req

Write-Host "`n== Verify ==" -ForegroundColor Cyan
& $py -c "import torch; print('torch', torch.__version__, '| cuda?', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU')"
& $py -c "import bitsandbytes, transformers, peft, trl, datasets, accelerate; print('HF stack imports OK')"
Write-Host "`nDone. Trainer venv ready at $venv" -ForegroundColor Green
