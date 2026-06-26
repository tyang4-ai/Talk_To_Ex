#!/bin/bash
#SBATCH --job-name=tlx-finetune
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=08:00:00
#SBATCH --output=%x-%j.out
#SBATCH --mail-user=tyang4@scu.edu
#SBATCH --mail-type=END,FAIL
#
# Per-persona QLoRA on a V100. Submit from the 4090 worker:
#   ssh wave "cd <TLX> && sbatch --export=ALL,TLX_PID=7,TLX_BASE=qwen2.5:14b-instruct-q4_K_M,\
#             TLX_EPOCHS=2,TLX_HF_TOKEN=<tok> scripts/train.sbatch"
# Expects runs/<PID>/examples.jsonl to already be staged; writes runs/<PID>/persona-<PID>.gguf.
set -euo pipefail

PROJ=/WAVE/projects/bioagenticai
TLX="$PROJ/tyang4/talk-to-ex"
ENV="$PROJ/conda-envs/tyang4/tlx-train"

export HF_HOME="$TLX/hf-cache"          # model cache on the 400GB project area, not $HOME
export HF_TOKEN="${TLX_HF_TOKEN:-}"

PID="${TLX_PID:?set TLX_PID}"
BASE="${TLX_BASE:?set TLX_BASE}"
EPOCHS="${TLX_EPOCHS:-2}"
RUN="$TLX/runs/$PID"

module purge
module load Anaconda3
source activate "$ENV"

echo "JOB $SLURM_JOB_ID on $(hostname) | persona=$PID base=$BASE epochs=$EPOCHS"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

python "$TLX/scripts/train_persona.py" \
  --examples "$RUN/examples.jsonl" \
  --base-tag "$BASE" \
  --persona-id "$PID" \
  --out "$RUN" \
  --epochs "$EPOCHS" \
  --llama-cpp "$TLX/llama.cpp"

echo "TLX_DONE persona=$PID gguf=$RUN/persona-$PID.gguf"
