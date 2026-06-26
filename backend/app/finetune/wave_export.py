"""Export a persona's training data as JSONL for the WAVE trainer (the 4090 side).

Pure-Python (no torch): decrypt the persona's uploads, shape them into chat
examples (the ex as assistant), and write one ``{"messages": [...]}`` per line —
the exact input ``ops/finetune/wave/train_persona.py`` reads on the cluster.
"""
from __future__ import annotations

import json
import os

from sqlmodel import Session, select

from ..db import Persona, Upload
from ..ingestion.upload import load_normalized
from . import dataprep


def export_examples_jsonl(session: Session, persona_id: int, out_path: str) -> int:
    """Write the persona's chat examples to ``out_path`` (JSONL). Returns the count.
    Raises ValueError if the persona is missing or yields no examples."""
    persona = session.get(Persona, persona_id)
    if persona is None:
        raise ValueError(f"persona {persona_id} not found")

    transcript: list[dict] = []
    for upload in session.exec(select(Upload).where(Upload.persona_id == persona_id)).all():
        transcript.extend(load_normalized(upload))

    examples = dataprep.build_examples(transcript)
    if not examples:
        raise ValueError(f"no training examples for persona {persona_id}")

    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps({"messages": ex.messages}, ensure_ascii=False) + "\n")
    return len(examples)
