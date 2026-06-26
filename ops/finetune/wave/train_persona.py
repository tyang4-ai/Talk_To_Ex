#!/usr/bin/env python
"""Standalone per-persona QLoRA trainer for WAVE (spec §23.3, steps 2-3).

Runs inside a SLURM GPU job in the tlx-train conda env. No Talk_To_Ex app deps —
the 4090 worker ships a JSONL of chat examples (one {"messages":[...]} per line,
the ex as the assistant) and this trains a LoRA on the matching HF base, then
converts it to a GGUF adapter for Ollama.

    python train_persona.py \
        --examples data/<pid>/examples.jsonl \
        --base-tag qwen2.5:14b-instruct-q4_K_M \
        --persona-id 7 --out runs/<pid> [--epochs 2] [--llama-cpp ../llama.cpp]

Output: <out>/adapter/ (PEFT) and <out>/persona-<pid>.gguf (Ollama ADAPTER).
V100-safe: uses fp16 where bf16 isn't supported (Volta).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

# Ollama base tag -> HF repo (mirror of app.finetune.basemodels).
HF_REPO = {
    "qwen2.5:14b-instruct-q4_K_M": "Qwen/Qwen2.5-14B-Instruct",
    "qwen2.5:14b": "Qwen/Qwen2.5-14B-Instruct",
    "gemma3:12b": "google/gemma-3-12b-it",
}
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def hf_repo_for(tag: str) -> str:
    repo = HF_REPO.get(tag) or (HF_REPO.get(tag.split("-q", 1)[0]) if "-q" in tag else None)
    if not repo:
        sys.exit(f"no HF base mapped for tag {tag!r}")
    return repo


def load_examples(path: str):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        sys.exit(f"no examples in {path}")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--examples", required=True)
    ap.add_argument("--base-tag", required=True)
    ap.add_argument("--persona-id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--llama-cpp", default=os.path.join(os.path.dirname(__file__), "..", "llama.cpp"))
    args = ap.parse_args()

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    repo = hf_repo_for(args.base_tag)
    token = (os.environ.get("HF_TOKEN") or "").strip() or None
    rows = load_examples(args.examples)
    os.makedirs(args.out, exist_ok=True)
    adapter_dir = os.path.join(args.out, "adapter")

    # Volta (V100) has no native bf16 — fall back to fp16.
    use_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    compute_dtype = torch.bfloat16 if use_bf16 else torch.float16
    print(f"[train] base={repo} examples={len(rows)} bf16={use_bf16} "
          f"gpu={torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'}",
          flush=True)

    tok = AutoTokenizer.from_pretrained(repo, token=token)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    texts = [tok.apply_chat_template(r["messages"], tokenize=False) for r in rows]
    dataset = Dataset.from_dict({"text": texts})

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )
    model = AutoModelForCausalLM.from_pretrained(
        repo, quantization_config=bnb, torch_dtype=compute_dtype,
        device_map="auto", attn_implementation="sdpa", token=token,
    )
    model.config.use_cache = False

    lora = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM", target_modules=LORA_TARGETS,
    )
    cfg = SFTConfig(
        output_dir=args.out,
        dataset_text_field="text",
        max_seq_length=1024,
        packing=False,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=16,
        num_train_epochs=args.epochs,
        learning_rate=2e-4,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_steps=5,
        save_strategy="no",
        bf16=use_bf16,
        fp16=not use_bf16,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",
        report_to=[],
    )
    trainer = SFTTrainer(
        model=model, args=cfg, train_dataset=dataset,
        processing_class=tok, peft_config=lora,
    )
    trainer.train()
    trainer.model.save_pretrained(adapter_dir)
    tok.save_pretrained(adapter_dir)
    print(f"[train] adapter saved -> {adapter_dir}", flush=True)

    # LoRA -> GGUF adapter (pure-python llama.cpp converter; no build).
    gguf_out = os.path.join(args.out, f"persona-{args.persona_id}.gguf")
    conv = os.path.join(args.llama_cpp, "convert_lora_to_gguf.py")
    cmd = [sys.executable, conv, adapter_dir, "--base", repo, "--outfile", gguf_out, "--outtype", "f16"]
    print(f"[convert] {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)
    print(f"GGUF_READY {gguf_out}", flush=True)


if __name__ == "__main__":
    main()
