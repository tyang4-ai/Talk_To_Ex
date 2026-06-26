"""Real, host-only QLoRA runners for the 4090 trainer (spec §23.3).

These fulfill the injectable runner contracts in train/convert/serve with actual
GPU work. torch/transformers/trl/peft are imported LAZILY (inside the functions) so
this module stays importable in the torch-free app venv — only the out-of-process
worker on the 4090 (running in .venv-train with settings.finetune_real_runners=True)
actually calls them.
"""
from __future__ import annotations

import logging
import os
from typing import List

from .dataprep import ChatExample

log = logging.getLogger("talk_to_ex.finetune.host")

# LoRA target projections for Qwen/Gemma-style decoder blocks.
_LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def train_runner(examples: List[ChatExample], base_model_tag: str, out_dir: str) -> str:
    """QLoRA SFT on the 4090: load the base 4-bit (nf4, double-quant, bf16 compute),
    attach LoRA, train on the chat-templated assistant-final windows, and save the
    PEFT adapter to ``out_dir/adapter``. Returns that adapter directory.

    The ex is the assistant in every example (see dataprep), so the model learns to
    reply in their voice. Short SMS turns → seq_len 1024 is plenty.
    """
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    from ..config import settings
    from .basemodels import hf_repo_for, is_gated

    if not examples:
        raise ValueError("no training examples — cannot fine-tune")

    repo = hf_repo_for(base_model_tag)
    token = (settings.train_hf_token or "").strip() or None
    if is_gated(repo) and not token:
        raise RuntimeError(
            f"{repo} is gated on HuggingFace — accept its license and set TRAIN_HF_TOKEN"
        )

    os.makedirs(out_dir, exist_ok=True)
    adapter_dir = os.path.join(out_dir, "adapter")

    log.info("loading tokenizer + 4-bit base %s (%d examples)", repo, len(examples))
    tok = AutoTokenizer.from_pretrained(repo, token=token)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    # Render each assistant-final window to one chat-templated training string.
    texts = [tok.apply_chat_template(ex.messages, tokenize=False) for ex in examples]
    dataset = Dataset.from_dict({"text": texts})

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    model = AutoModelForCausalLM.from_pretrained(
        repo,
        quantization_config=bnb,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        attn_implementation="sdpa",
        token=token,
    )
    model.config.use_cache = False

    lora = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=_LORA_TARGETS,
    )
    cfg = SFTConfig(
        output_dir=out_dir,
        dataset_text_field="text",
        max_seq_length=1024,
        packing=False,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=16,
        num_train_epochs=2,
        learning_rate=2e-4,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_steps=5,
        save_strategy="no",
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",
        report_to=[],
    )
    trainer = SFTTrainer(
        model=model,
        args=cfg,
        train_dataset=dataset,
        processing_class=tok,
        peft_config=lora,
    )
    log.info("training (epochs=%s)…", cfg.num_train_epochs)
    trainer.train()
    trainer.model.save_pretrained(adapter_dir)
    tok.save_pretrained(adapter_dir)
    log.info("adapter saved -> %s", adapter_dir)
    return adapter_dir
