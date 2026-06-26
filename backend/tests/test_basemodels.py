"""Ollama tag -> HF base mapping for QLoRA (pure, no GPU)."""
from __future__ import annotations

import pytest

from app.finetune.basemodels import hf_repo_for, is_gated


def test_known_tags_map():
    assert hf_repo_for("qwen2.5:14b-instruct-q4_K_M") == "Qwen/Qwen2.5-14B-Instruct"
    assert hf_repo_for("gemma3:12b") == "google/gemma-3-12b-it"


def test_quant_suffix_tolerated():
    # a base tag without the explicit quant suffix still resolves
    assert hf_repo_for("qwen2.5:14b") == "Qwen/Qwen2.5-14B-Instruct"


def test_unknown_tag_raises():
    with pytest.raises(ValueError, match="no HF base"):
        hf_repo_for("llama3:70b")


def test_gated_flags_gemma_only():
    assert is_gated("google/gemma-3-12b-it") is True
    assert is_gated("Qwen/Qwen2.5-14B-Instruct") is False
