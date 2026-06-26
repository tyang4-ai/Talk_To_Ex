"""Map an Ollama base-model tag to the HuggingFace repo to fine-tune.

A persona's serving model is an Ollama tag (e.g. ``qwen2.5:14b-instruct-q4_K_M``);
QLoRA needs the corresponding full-precision HF base. Keep this mapping EXPLICIT so
an unknown tag fails loudly instead of silently training the wrong base.
"""
from __future__ import annotations

# Ollama tag -> HF repo id (the instruct/-it base the quantized Ollama model derives from).
_HF_REPO = {
    "qwen2.5:14b-instruct-q4_K_M": "Qwen/Qwen2.5-14B-Instruct",
    "qwen2.5:14b": "Qwen/Qwen2.5-14B-Instruct",
    "gemma3:12b": "google/gemma-3-12b-it",
}


def hf_repo_for(ollama_tag: str) -> str:
    """The HF repo id to fine-tune for an Ollama base tag. Raises ValueError for an
    unmapped tag so we never silently train the wrong base."""
    tag = (ollama_tag or "").strip()
    repo = _HF_REPO.get(tag)
    if repo is None and "-q" in tag:
        # tolerate a tag minus its quant suffix (…-instruct-q4_K_M -> the base entry)
        repo = _HF_REPO.get(tag.split("-q", 1)[0])
    if repo is None:
        raise ValueError(
            f"no HF base mapped for Ollama tag {ollama_tag!r} — add it to finetune.basemodels"
        )
    return repo


def is_gated(repo: str) -> bool:
    """Gemma is gated on HF (needs license acceptance + a token); used to surface a
    clear, early error rather than a 401 deep inside training."""
    return repo.startswith("google/gemma")
