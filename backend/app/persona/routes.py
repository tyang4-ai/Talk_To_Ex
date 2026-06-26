"""Persona lifecycle API (E6): create -> upload -> distill -> activate -> preview,
plus corrections. All routes require auth and enforce ownership."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth.deps import get_current_user
from ..billing import claude_budget
from ..billing.number_service import provision
from ..config import settings
from ..convo.engine import reply as engine_reply
from ..convo.model_router import pick_model
from ..db import (
    Conversation,
    Correction,
    Job,
    MemoryChunk,
    Message,
    Number,
    Persona,
    SafetyEvent,
    StyleTuning,
    Upload,
    User,
    Version,
    engine,
    get_session,
)
from ..ingestion.upload import UPLOADS_ROOT, load_normalized
from ..jobs import queue, worker
from ..messaging import reveal
from ..persona import store
from .build import _language_for_model, register_build_handler, run_build

router = APIRouter(prefix="/api/personas", tags=["personas"])

log = logging.getLogger("talk_to_ex.persona")


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "ex"


def _owned(session: Session, user: User, persona_id: int) -> Persona:
    persona = session.get(Persona, persona_id)
    if persona is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "persona not found")
    if persona.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your persona")
    return persona


class CreatePersona(BaseModel):
    name: str
    intake: dict[str, Any] = {}
    peer_e164: Optional[str] = None  # the friend's own phone — so the persona can text first (§24)


class NumberOut(BaseModel):
    e164: str
    mode: str


class PersonaSummary(BaseModel):
    id: int
    slug: str
    name: str
    status: str
    uploads: int
    message_count: int
    has_artifacts: bool
    distilled: bool  # alias of has_artifacts for the frontend
    number: Optional[NumberOut] = None
    llm_model: Optional[str] = None
    llm_language: Optional[str] = None


def _summary(session: Session, p: Persona) -> PersonaSummary:
    uploads = session.exec(select(Upload).where(Upload.persona_id == p.id)).all()
    num = session.exec(select(Number).where(Number.persona_id == p.id)).first()
    try:
        meta = json.loads(p.meta_json or "{}")
    except Exception:
        meta = {}
    distilled = bool(p.persona_md_enc)
    return PersonaSummary(
        id=p.id,
        slug=p.slug,
        name=p.name,
        status=p.status,
        uploads=len(uploads),
        message_count=sum(u.message_count for u in uploads),
        has_artifacts=distilled,
        distilled=distilled,
        number=NumberOut(e164=num.e164, mode=num.mode) if num else None,
        llm_model=meta.get("llm_model"),
        llm_language=meta.get("llm_language"),
    )


@router.post("", response_model=PersonaSummary)
def create_persona(
    body: CreatePersona,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PersonaSummary:
    owned = session.exec(select(Persona.id).where(Persona.user_id == user.id)).all()
    if len(owned) >= settings.max_personas_per_user:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Persona limit reached ({settings.max_personas_per_user} per account).",
        )
    meta: dict[str, Any] = {"intake": body.intake}
    if body.peer_e164:
        meta["peer_e164"] = body.peer_e164
    persona = Persona(
        user_id=user.id,
        slug=_slugify(body.name),
        name=body.name,
        meta_json=json.dumps(meta, ensure_ascii=False),
        status="draft",
    )
    session.add(persona)
    session.commit()
    session.refresh(persona)
    return _summary(session, persona)


@router.get("", response_model=List[PersonaSummary])
def list_personas(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> List[PersonaSummary]:
    rows = session.exec(select(Persona).where(Persona.user_id == user.id)).all()
    return [_summary(session, p) for p in rows]


@router.get("/{persona_id}", response_model=PersonaSummary)
def get_persona(
    persona_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PersonaSummary:
    return _summary(session, _owned(session, user, persona_id))


@router.post("/{persona_id}/distill")
def distill_persona(
    persona_id: int,
    force: bool = False,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    persona = _owned(session, user, persona_id)

    # Idempotency: a persona that's already been built does NOT re-spend on Claude
    # unless the owner explicitly forces it (?force=true). Blocks re-distill loops.
    if persona.persona_md_enc and not force:
        meta = json.loads(persona.meta_json or "{}")
        return {
            "ok": True,
            "name": persona.name,
            "already_distilled": True,
            "llm_language": meta.get("llm_language"),
            "llm_model": meta.get("llm_model"),
            "llm_model_source": meta.get("llm_model_source"),
        }

    if not session.exec(select(Upload).where(Upload.persona_id == persona_id)).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no uploads to distill")

    # The distillation itself (load → Claude → pick model → persist) lives in
    # build.run_build so the async build job and this synchronous route share it.
    summary = run_build(session, persona_id)
    return {"ok": True, **summary}


# --- async build + the "reveal" ------------------------------------------------
# The intended flow: set up & close-and-forget → the build runs in the background
# → when it's done the persona texts the friend FIRST (the opener), in-voice.

_BUILDING = {"queued", "training"}


def _latest_build_job(session: Session, persona_id: int) -> Optional[Job]:
    return session.exec(
        select(Job)
        .where(Job.persona_id == persona_id, Job.kind.in_(("build", "finetune")))
        .order_by(Job.created_at.desc(), Job.id.desc())
    ).first()


def _build_and_reveal(persona_id: int, job_id: int) -> None:
    """Runs AFTER the /build response (FastAPI BackgroundTask): distill the persona
    out-of-request, then — on success — have the ex text the friend first. Opens its
    own DB session because the request's session is already closed."""
    with Session(engine) as session:
        job = queue.get(session, job_id)
        if job is None:
            return
        worker.run_job(session, job)  # marks training → ready/failed
        if job.status != "ready":
            log.warning("build job %s failed: %s", job_id, job.error)
            return
        try:
            sent = reveal.go_live(session, persona_id)  # the ex texts them first
            log.info("persona %s build done; opener sent=%s", persona_id, sent)
        except Exception:  # noqa: BLE001 — a failed reveal must not crash the worker
            log.exception("reveal failed for persona %s", persona_id)

        # Chain the (long, GPU) fine-tune that hot-upgrades the voice later. It's
        # left QUEUED for the out-of-process worker (python -m app.jobs.run_worker),
        # never tied to the web process. Failure is non-fatal: the persona keeps
        # texting on its prompt-only distilled voice (meta["llm_model"]).
        if settings.finetune_enabled:
            try:
                queue.enqueue(session, persona_id, kind="finetune")
                log.info("queued fine-tune for persona %s", persona_id)
            except Exception:  # noqa: BLE001
                log.exception("could not enqueue finetune for persona %s", persona_id)


def _build_state(persona: Persona, job: Optional[Job]) -> str:
    """Friendly status for the dashboard/poller. Once the persona is revealed
    (active), a background fine-tune does NOT drag it back to 'contemplating' —
    the voice upgrade is silent, so 'revealed' wins over an in-flight finetune."""
    if persona.status == "active":
        return "revealed"               # they texted you (voice may still be upgrading)
    if job is not None and job.status in _BUILDING:
        return "contemplating"          # "they're contemplating their wrongdoings…"
    if job is not None and job.status == "failed":
        return "failed"
    if persona.persona_md_enc:
        return "ready"                  # built, opener not (yet) sent
    return "draft"                      # nothing built yet


class BuildOut(BaseModel):
    persona_id: int
    name: str
    state: str                          # draft|contemplating|ready|revealed|failed
    job_id: Optional[int] = None
    job_status: Optional[str] = None
    revealed: bool = False
    learning: bool = False              # background fine-tune still upgrading the voice
    has_phone: bool = False
    number_e164: Optional[str] = None   # the number the ex texts them FROM
    error: Optional[str] = None


def _build_payload(session: Session, persona: Persona) -> BuildOut:
    job = _latest_build_job(session, persona.id)
    owner = session.get(User, persona.user_id)
    meta = json.loads(persona.meta_json or "{}")
    number = session.exec(
        select(Number).where(Number.persona_id == persona.id)
    ).first()
    return BuildOut(
        persona_id=persona.id,
        name=persona.name,
        state=_build_state(persona, job),
        job_id=job.id if job else None,
        job_status=job.status if job else None,
        revealed=persona.status == "active",
        learning=(
            persona.status == "active"
            and job is not None
            and job.kind == "finetune"
            and job.status in _BUILDING
        ),
        has_phone=bool(meta.get("peer_e164") or (owner and owner.phone_e164)),
        number_e164=number.e164 if number else None,
        error=job.error if (job and job.status == "failed") else None,
    )


@router.post("/{persona_id}/build", response_model=BuildOut)
def build_persona(
    persona_id: int,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BuildOut:
    """Kick off the async build (set up & forget). Returns immediately; the persona
    texts the friend first when the build finishes. Idempotent: a build already in
    flight is not duplicated."""
    persona = _owned(session, user, persona_id)

    if not session.exec(select(Upload).where(Upload.persona_id == persona_id)).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "upload a chat export first")

    # Already built or revealed, or a build already in flight → return current state
    # rather than re-spending on Claude. (The poller calls this on every visit.)
    if persona.persona_md_enc or persona.status == "active":
        return _build_payload(session, persona)
    existing = _latest_build_job(session, persona_id)
    if existing is not None and existing.status in _BUILDING:
        return _build_payload(session, persona)  # already brewing — don't double-spend

    # Record where the ex will text them (captured at signup) on the persona, and
    # make sure it has a number to text FROM.
    meta = json.loads(persona.meta_json or "{}")
    if user.phone_e164:
        meta["peer_e164"] = user.phone_e164
    if not session.exec(select(Number).where(Number.persona_id == persona_id)).first():
        try:
            provision(session, persona)
        except Exception:  # noqa: BLE001 — build can proceed; reveal no-ops w/o a number
            log.warning("number provision failed for persona %s", persona_id)
    persona.status = "building"
    persona.meta_json = json.dumps(meta, ensure_ascii=False)
    persona.updated_at = datetime.utcnow()
    session.add(persona)
    session.commit()

    job = queue.enqueue(session, persona_id, kind="build")
    background.add_task(_build_and_reveal, persona_id, job.id)
    return _build_payload(session, persona)


@router.get("/{persona_id}/status", response_model=BuildOut)
def persona_status(
    persona_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BuildOut:
    """Poll the build/reveal state — drives the 'he's contemplating…' screen."""
    persona = _owned(session, user, persona_id)
    return _build_payload(session, persona)


class ModelIn(BaseModel):
    model: str  # one of OLLAMA_MODEL_ZH / OLLAMA_MODEL_EN, or "auto" to re-detect


@router.post("/{persona_id}/model")
def set_persona_model(
    persona_id: int,
    body: ModelIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Override (or reset to auto) the local model that voices this persona.

    The choice is stored on the persona and takes effect immediately — the live
    engine reads ``meta_json["llm_model"]`` per reply — and survives re-distill
    via ``llm_model_override``. ``"auto"`` clears the override and re-detects from
    the uploaded log's dominant language (spec §22/§26)."""
    persona = _owned(session, user, persona_id)
    model = body.model.strip()
    allowed = {settings.ollama_model_zh, settings.ollama_model_en, "auto"}
    if model not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"model must be one of {sorted(allowed)}",
        )

    meta = json.loads(persona.meta_json or "{}")
    if model == "auto":
        meta.pop("llm_model_override", None)
        meta["llm_model_source"] = "auto"
        uploads = session.exec(
            select(Upload).where(Upload.persona_id == persona_id)
        ).all()
        if uploads:
            transcript: list[dict] = []
            for u in uploads:
                transcript.extend(load_normalized(u))
            meta["llm_language"], meta["llm_model"] = pick_model(transcript)
    else:
        meta["llm_model_override"] = model
        meta["llm_model"] = model
        meta["llm_language"] = _language_for_model(model)
        meta["llm_model_source"] = "manual"

    persona.meta_json = json.dumps(meta, ensure_ascii=False)
    persona.updated_at = datetime.utcnow()
    session.add(persona)
    session.commit()
    return {
        "ok": True,
        "llm_model": meta.get("llm_model"),
        "llm_language": meta.get("llm_language"),
        "source": meta.get("llm_model_source"),
    }


@router.post("/{persona_id}/activate")
def activate_persona(
    persona_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    persona = _owned(session, user, persona_id)
    if not persona.persona_md_enc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "distill the persona before activating"
        )
    number = provision(session, persona)  # raises 402 if subscription not active
    persona.status = "active"
    session.add(persona)
    session.commit()
    return {"ok": True, "e164": number.e164, "mode": number.mode}


class KillIn(BaseModel):
    enabled: bool


@router.post("/{persona_id}/kill")
def kill_persona(
    persona_id: int,
    body: KillIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Per-persona silence toggle (operator kill-switch). Records the flag on the
    persona; the messaging path honors it alongside the global KILL_SWITCH."""
    persona = _owned(session, user, persona_id)
    meta = json.loads(persona.meta_json or "{}")
    meta["killed"] = body.enabled
    persona.meta_json = json.dumps(meta, ensure_ascii=False)
    persona.updated_at = datetime.utcnow()
    session.add(persona)
    session.commit()
    return {"ok": True, "killed": body.enabled}


def _purge_persona(session: Session, persona: Persona) -> None:
    """Delete a persona and EVERYTHING tied to it — DB rows for every related
    table plus the encrypted chat files on disk. This is the "re-break-up": the
    ex's data genuinely leaves the box.
    """
    pid = persona.id
    conv_ids = session.exec(
        select(Conversation.id).where(Conversation.persona_id == pid)
    ).all()
    if conv_ids:
        for msg in session.exec(
            select(Message).where(Message.conversation_id.in_(conv_ids))
        ).all():
            session.delete(msg)
        for ev in session.exec(
            select(SafetyEvent).where(SafetyEvent.conversation_id.in_(conv_ids))
        ).all():
            session.delete(ev)
    # persona-scoped tables (StyleTuning first — it references conversations)
    for model in (StyleTuning, Conversation, Number, MemoryChunk, Correction, Version, Job, Upload):
        for row in session.exec(select(model).where(model.persona_id == pid)).all():
            session.delete(row)
    session.delete(persona)
    session.commit()

    # wipe the encrypted raw/normalized uploads from disk (the sensitive part).
    import shutil

    pdir = UPLOADS_ROOT / str(pid)
    if pdir.exists():
        shutil.rmtree(pdir, ignore_errors=True)


@router.delete("/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_persona(
    persona_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    """Permanently delete a persona and all of its data (the "re-break-up").
    Irreversible; the caller (portal) confirms first. Releasing the Twilio number
    is a TODO for when live SMS is wired."""
    persona = _owned(session, user, persona_id)
    _purge_persona(session, persona)


class CorrectionIn(BaseModel):
    instruction: str


@router.post("/{persona_id}/corrections")
def correct_persona(
    persona_id: int,
    body: CorrectionIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    persona = _owned(session, user, persona_id)
    instruction = (body.instruction or "").strip()
    if not instruction:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty correction")
    if len(instruction) > settings.max_correction_chars:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"correction too long (max {settings.max_correction_chars} characters)",
        )
    meta = json.loads(persona.meta_json or "{}")
    if int(meta.get("corrections_count", 0)) >= settings.max_corrections_per_persona:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "correction limit reached for this persona"
        )
    if not settings.demo_mode:
        claude_budget.consume(session)  # reserve a Claude call or 503 (global ceiling)
    store.apply_correction(persona_id, instruction, session)  # Claude at runtime
    return {"ok": True}


class PreviewIn(BaseModel):
    message: str


class PreviewOut(BaseModel):
    bubbles: List[str]


@router.post("/{persona_id}/preview", response_model=PreviewOut)
def preview_persona(
    persona_id: int,
    body: PreviewIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PreviewOut:
    persona = _owned(session, user, persona_id)
    if not persona.persona_md_enc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "distill the persona first")
    # Stable per-user preview thread; engine.reply is read-only re: history.
    bubbles = engine_reply(session, persona_id, f"preview:{user.id}", body.message)
    return PreviewOut(bubbles=bubbles)
