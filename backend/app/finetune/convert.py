"""LoRA → GGUF conversion step (spec §23.3 step 3) — host-only, injectable.

Converts a trained adapter directory into a GGUF adapter Ollama can load via the
Modelfile ``ADAPTER`` directive. The real path shells out to llama.cpp's
``convert_lora_to_gguf.py`` (host-only); ``to_gguf`` takes an injectable
``runner`` for tests. See ``ops/finetune/setup.md``.
"""
from __future__ import annotations

from typing import Callable, Optional

# runner(adapter_dir, out_path) -> gguf_path
Runner = Callable[[str, str], str]


def _default_runner(adapter_dir: str, out_path: str) -> str:
    raise RuntimeError(
        "GGUF conversion is host-only — run llama.cpp convert_lora_to_gguf.py per "
        "ops/finetune/setup.md; inject a runner in tests/CI."
    )


def to_gguf(adapter_dir: str, out_path: str, *, runner: Optional[Runner] = None) -> str:
    """Convert an adapter dir to a GGUF file at ``out_path``; return the path."""
    run = runner or _default_runner
    return run(adapter_dir, out_path)
