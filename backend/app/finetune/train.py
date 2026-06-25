"""QLoRA training step (spec §23.3 step 2) — host-only real path, injectable runner.

The actual training (Unsloth / LLaMA-Factory on the 4090) is a heavyweight,
GPU-only operation, so it is NOT executed in CI. ``qlora`` takes an injectable
``runner`` (DI) the tests pass as a fake; the default runner raises a clear
host-only error with a pointer to the documented procedure. See
``ops/finetune/setup.md``.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from .dataprep import ChatExample

# runner(examples, base_model, out_dir) -> adapter_dir
Runner = Callable[[List[ChatExample], str, str], str]


def _default_runner(trainer: str) -> Runner:
    def _run(examples: List[ChatExample], base_model: str, out_dir: str) -> str:
        raise RuntimeError(
            f"real QLoRA training (trainer={trainer!r}) is host-only — run it on the "
            "RTX 4090 per ops/finetune/setup.md; inject a runner in tests/CI."
        )
    return _run


def qlora(
    examples: List[ChatExample],
    base_model: str,
    out_dir: str,
    *,
    trainer: str = "unsloth",
    runner: Optional[Runner] = None,
) -> str:
    """Train a QLoRA adapter and return its output directory.

    ``runner`` is injected in tests; in production it lazy-loads the trainer
    (host-only). Raises ``ValueError`` if there are no examples."""
    if not examples:
        raise ValueError("no training examples — cannot fine-tune")
    run = runner or _default_runner(trainer)
    return run(examples, base_model, out_dir)
