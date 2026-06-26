"""The persona "build" — what runs during the async wait before the reveal.

Today the build IS the Claude distillation (seconds): load the uploaded transcript,
distill the 5-layer persona, pick the local serving model, persist artifacts. It's
wrapped as a job-queue handler ("build") so it runs OUT of the request (via a
BackgroundTask) — the user sets up, closes the tab, and the persona texts them
first when this finishes (see app/messaging/reveal). Later the "wait" evolves into
the real overnight QLoRA fine-tune (app/finetune); this module is the seam.
"""
from __future__ import annotations

import json

from sqlmodel import Session, select

from ..billing import claude_budget
from ..config import settings
from ..convo.model_router import pick_model
from ..db import Job, Persona, Upload
from ..distill.pipeline import distill
from ..ingestion.upload import load_normalized
from ..jobs import worker
from . import store


def _language_for_model(model: str) -> str:
    """Best-effort language label for an explicitly-chosen model (spec §26)."""
    if model == settings.ollama_model_zh:
        return "zh"
    if model == settings.ollama_model_en:
        return "en"
    return "manual"


def run_build(session: Session, persona_id: int) -> dict:
    """Distill a persona from its uploads and persist artifacts. The real Claude
    call (budget-gated) happens here. Raises ValueError if the persona/uploads are
    missing. Returns a summary dict. Idempotent-safe to re-run (overwrites)."""
    persona = session.get(Persona, persona_id)
    if persona is None:
        raise ValueError(f"persona {persona_id} not found")
    uploads = session.exec(select(Upload).where(Upload.persona_id == persona_id)).all()
    if not uploads:
        raise ValueError("no uploads to build from")

    transcript: list[dict] = []
    for u in uploads:
        transcript.extend(load_normalized(u))

    meta = json.loads(persona.meta_json or "{}")
    intake = meta.get("intake", {})
    override = meta.get("llm_model_override")

    if not settings.demo_mode:
        claude_budget.consume(session)  # reserve a Claude call or 503 (global ceiling)
    arts = distill(transcript, intake)  # real Claude call at runtime (needs key)
    arts.meta["intake"] = intake  # keep intake so a re-build stays possible

    if override:
        llm_model = override
        llm_language = _language_for_model(override)
        arts.meta["llm_model_override"] = override
        source = "manual"
    else:
        llm_language, llm_model = pick_model(transcript)
        source = "auto"
    arts.meta["llm_language"] = llm_language
    arts.meta["llm_model"] = llm_model
    arts.meta["llm_model_source"] = source

    store.save_artifacts(persona_id, arts, session)
    return {
        "name": persona.name,
        "message_count": len(transcript),
        "layers": list(arts.persona_json.keys()),
        "llm_language": llm_language,
        "llm_model": llm_model,
        "llm_model_source": source,
    }


def build_handler(session: Session, job: Job) -> dict:
    """Job-queue handler for kind "build": distill the persona. Returns {} (no
    adapter artifact — that's the future fine-tune path)."""
    run_build(session, job.persona_id)
    return {}


def register_build_handler() -> None:
    """Register the distillation build handler with the job worker (called at app
    startup). Unlike the GPU fine-tune handler, this needs no special hardware."""
    worker.register("build", build_handler)
