# Per-persona fine-tuning — host-only bring-up (spec §23)

The app code orchestrates the pipeline with **injectable runners** (so CI/tests
need no GPU). The three real steps below run on the **RTX 4090** (the T4 is too
small to train a 14B). The pipeline lives in `backend/app/finetune/`:
`dataprep` (pure) → `train.qlora` → `convert.to_gguf` → `serve.register_adapter`,
chained by `pipeline.run_finetune` and exposed as the `finetune` job handler
(`app/jobs/worker`). Until you wire the runners below, the `finetune` job fails
loudly with a "host-only" message — that's expected.

## 0. Where it runs
- **Train + convert + `ollama create`:** the 4090 desktop.
- **Serve:** atlas (the derived `persona-<id>` model is created wherever
  `TRAIN_OLLAMA_HOST` points; copy/registry-push to atlas for live serving, or
  create it directly on atlas if it has the base model).

## 1. Train (QLoRA) — Unsloth (preferred)
```bash
pip install "unsloth[cu124] @ git+https://github.com/unslothai/unsloth.git"
```
`dataprep.build_examples(transcript)` yields chat-format examples (the **ex** is
the assistant). Feed them to an Unsloth QLoRA SFT run on `OLLAMA_MODEL_ZH/EN`'s
HF base (e.g. `Qwen/Qwen2.5-14B-Instruct`). Cap epochs (1–3) to avoid overfitting
on short logs; hold out a few turns and sanity-check the model still
language-mirrors and doesn't parrot verbatim. Output: a LoRA adapter dir.

Wire it as the `train_runner(examples, base_model, out_dir) -> adapter_dir`
injected into `pipeline.run_finetune` (or the default runner in `train.py`).

## 2. Convert LoRA → GGUF
```bash
python llama.cpp/convert_lora_to_gguf.py <adapter_dir> --outfile persona-<id>.gguf
```
Wire as `convert_runner(adapter_dir, out_path) -> gguf_path`.

## 3. Serve as a per-persona Ollama model
`serve.build_modelfile` already emits:
```
FROM qwen2.5:14b-instruct-q4_K_M
ADAPTER ./persona-<id>.gguf
SYSTEM """…in-character stub…"""
PARAMETER num_ctx 8192
PARAMETER temperature 0.8
```
Then `ollama create persona-<id> -f Modelfile`. Wire as
`ollama_create(name, modelfile_text)`. The engine auto-targets `persona-<id>`
once `meta_json["adapter_model"]` is set (done by the pipeline).

## ⚠️ Verify day one
- **Adapter↔base compatibility** in Ollama (this path is historically finicky —
  the adapter must match the base architecture/quant).
- **No verbatim parroting / still mirrors language** on held-out turns.
- VRAM: each persona is its own derived model; the T4 holds one resident at a
  time (cold reload on switch) — fine at single-friend scale.
