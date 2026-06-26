#!/bin/bash
# One-time: build the Talk_To_Ex QLoRA training env + project layout on WAVE.
# Run on a WAVE login node:  bash setup_env.sh   (logs to the same dir)
# Idempotent: re-running skips what already exists.
set -euo pipefail

PROJ=/WAVE/projects/bioagenticai
TLX="$PROJ/tyang4/talk-to-ex"
ENV="$PROJ/conda-envs/tyang4/tlx-train"
LLAMA="$TLX/llama.cpp"

echo "== Talk_To_Ex WAVE setup =="
echo "project: $TLX"
echo "env:     $ENV"

module purge
module load Anaconda3

mkdir -p "$TLX"/{data,runs,scripts,adapters,base}

# --- conda env (Python 3.12, matches the locally-validated stack) ---
if [ ! -d "$ENV" ]; then
  echo "creating conda env…"
  conda create -y --prefix "$ENV" python=3.12
fi
# `source activate` is the robust form for a full prefix in a non-interactive shell
source activate "$ENV"
python -m pip install --upgrade pip -q

echo "installing torch (CUDA 12.4 wheels)…"
python -m pip install -q torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124

echo "installing the HF QLoRA stack…"
python -m pip install -q \
  transformers==4.48.0 peft==0.14.0 trl==0.13.0 accelerate==1.3.0 \
  datasets==3.2.0 bitsandbytes==0.45.0 sentencepiece==0.2.0 protobuf==5.29.3 \
  "huggingface_hub>=0.27,<1.0" gguf

# --- llama.cpp (python LoRA->GGUF converter; no compile, just the scripts + gguf-py) ---
if [ ! -d "$LLAMA" ]; then
  echo "cloning llama.cpp (shallow)…"
  git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA"
fi

echo "== verify (imports only; no GPU on the login node) =="
python -c "import torch; print('torch', torch.__version__)"
python -c "import transformers, peft, trl, bitsandbytes, datasets, gguf; print('hf+gguf stack OK')"
test -f "$LLAMA/convert_lora_to_gguf.py" && echo "convert_lora_to_gguf.py present"
echo "WAVE_ENV_READY"
