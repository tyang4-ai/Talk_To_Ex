"""Fine-tune pipeline orchestration (spec §23) + the job-queue handler.

Chains dataprep → QLoRA train → GGUF convert → register the per-persona Ollama
adapter model, then pins ``adapter_model`` on the persona so the live engine
(``convo.engine._persona_model``) answers on the fine-tuned voice. Every external
step (train/convert/ollama-create) is injectable, so the orchestration is fully
mock-testable; the real steps are GPU/host-only (``ops/finetune/setup.md``).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from ..config import settings
from ..db import Job, Persona, Upload
from ..ingestion.upload import load_normalized
from ..jobs import worker
from . import convert, dataprep, serve, train

# adapters/ lives beside the backend app package root (…/backend/adapters).
ADAPTERS_ROOT = Path(__file__).resolve().parents[2] / "adapters"


def run_finetune(
    session: Session,
    persona_id: int,
    *,
    base_model: Optional[str] = None,
    train_runner=None,
    convert_runner=None,
    ollama_create=None,
    work_dir: Optional[str] = None,
) -> dict:
    """Train + serve a persona's voice adapter; pin it on the persona. Returns
    ``{"adapter_model", "adapter_path"}``. Runners are injected in tests."""
    persona = session.get(Persona, persona_id)
    if persona is None:
        raise ValueError(f"persona {persona_id} not found")

    transcript: list = []
    for u in session.exec(select(Upload).where(Upload.persona_id == persona_id)).all():
        transcript.extend(load_normalized(u))
    examples = dataprep.build_examples(transcript)
    if not examples:
        raise ValueError(f"no training examples for persona {persona_id}")

    meta = json.loads(persona.meta_json or "{}")
    base = base_model or meta.get("llm_model") or settings.ollama_model
    root = Path(work_dir) if work_dir else (ADAPTERS_ROOT / str(persona_id))
    adapter_out = str(root / "lora")
    gguf_out = str(root / f"persona-{persona_id}.gguf")

    adapter_dir = train.qlora(
        examples, base, adapter_out,
        trainer=settings.finetune_trainer, runner=train_runner,
    )
    gguf_path = convert.to_gguf(adapter_dir, gguf_out, runner=convert_runner)
    name = serve.register_adapter(
        persona_id, gguf_path, base, ollama_create=ollama_create
    )

    meta["adapter_model"] = name
    meta["adapter_path"] = gguf_path
    persona.meta_json = json.dumps(meta, ensure_ascii=False)
    persona.updated_at = datetime.utcnow()
    session.add(persona)
    session.commit()
    return {"adapter_model": name, "adapter_path": gguf_path}


def finetune_handler(session: Session, job: Job) -> dict:
    """Job-queue handler (worker contract): run the pipeline, return adapter_path
    so the worker records it on the job. Uses the real (host-only) runners by
    default — until a trainer is wired on the 4090, the job fails loudly with a
    host-only message, which is the honest scaffold state."""
    result = run_finetune(session, job.persona_id)
    return {"adapter_path": result["adapter_path"]}


def register_handler() -> None:
    """Register the finetune handler with the job worker (called at app/worker
    startup when fine-tuning is enabled)."""
    worker.register("finetune", finetune_handler)
