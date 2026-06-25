"""Fine-tune data prep (spec §23.3 step 1) — pure, fully testable.

Turn a normalized transcript into chat-format SFT examples where the **ex** is the
assistant the model learns to imitate. Direction mapping: ``"in"`` (the ex) →
``assistant``; ``"out"`` (the friend) → ``user``. The zh/en mix is preserved
verbatim. Each example is a short sliding window ending on an ex (assistant) turn
with at least one preceding friend (user) turn — so the model always learns "given
this exchange, the ex replies like THIS".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# role for each normalized direction (the ex's lines are what we train on).
_ROLE = {"in": "assistant", "out": "user"}


@dataclass
class ChatExample:
    messages: List[dict] = field(default_factory=list)  # [{role, content}, ...], assistant-final


def _text_of(m) -> str:
    if isinstance(m, dict):
        return str(m.get("text") or m.get("body") or "")
    return str(getattr(m, "text", "") or "")


def _dir_of(m) -> str:
    if isinstance(m, dict):
        return str(m.get("direction") or "")
    return str(getattr(m, "direction", "") or "")


def build_examples(transcript, *, window: int = 6) -> List[ChatExample]:
    """Build assistant-final chat examples from a normalized transcript.

    ``window`` caps how many preceding turns of context each example carries.
    Empty-text turns are skipped; a sample is emitted only when an ex (assistant)
    turn has at least one preceding friend (user) turn within the window.
    """
    turns: List[dict] = []
    for m in transcript:
        text = _text_of(m).strip()
        role = _ROLE.get(_dir_of(m))
        if not text or role is None:
            continue
        turns.append({"role": role, "content": text})

    examples: List[ChatExample] = []
    for i, turn in enumerate(turns):
        if turn["role"] != "assistant":
            continue
        ctx = turns[max(0, i - window + 1): i + 1]
        # need at least one user turn before this assistant turn in the window
        if any(t["role"] == "user" for t in ctx[:-1]):
            examples.append(ChatExample(messages=[dict(t) for t in ctx]))
    return examples
