"""Persona lifecycle API (E6): create -> upload -> distill -> activate -> preview,
plus corrections. All routes require auth and enforce ownership."""
from __future__ import annotations

import json
import re
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth.deps import get_current_user
from ..billing.number_service import provision
from ..convo.engine import reply as engine_reply
from ..db import Number, Persona, Upload, User, get_session
from ..distill.pipeline import distill
from ..ingestion.upload import load_normalized
from ..persona import store

router = APIRouter(prefix="/api/personas", tags=["personas"])


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


class PersonaSummary(BaseModel):
    id: int
    slug: str
    name: str
    status: str
    uploads: int
    message_count: int
    has_artifacts: bool
    number: Optional[str] = None


def _summary(session: Session, p: Persona) -> PersonaSummary:
    uploads = session.exec(select(Upload).where(Upload.persona_id == p.id)).all()
    num = session.exec(select(Number).where(Number.persona_id == p.id)).first()
    return PersonaSummary(
        id=p.id,
        slug=p.slug,
        name=p.name,
        status=p.status,
        uploads=len(uploads),
        message_count=sum(u.message_count for u in uploads),
        has_artifacts=bool(p.persona_md_enc),
        number=num.e164 if num else None,
    )


@router.post("", response_model=PersonaSummary)
def create_persona(
    body: CreatePersona,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PersonaSummary:
    persona = Persona(
        user_id=user.id,
        slug=_slugify(body.name),
        name=body.name,
        meta_json=json.dumps({"intake": body.intake}, ensure_ascii=False),
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
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    persona = _owned(session, user, persona_id)
    uploads = session.exec(select(Upload).where(Upload.persona_id == persona_id)).all()
    if not uploads:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no uploads to distill")

    transcript: list[dict] = []
    for u in uploads:
        transcript.extend(load_normalized(u))

    intake = json.loads(persona.meta_json or "{}").get("intake", {})
    arts = distill(transcript, intake)  # real Claude call at runtime (needs key)
    arts.meta["intake"] = intake  # keep intake so re-distill stays possible
    store.save_artifacts(persona_id, arts, session)
    return {
        "ok": True,
        "name": persona.name,
        "message_count": len(transcript),
        "layers": list(arts.persona_json.keys()),
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


class CorrectionIn(BaseModel):
    instruction: str


@router.post("/{persona_id}/corrections")
def correct_persona(
    persona_id: int,
    body: CorrectionIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _owned(session, user, persona_id)
    store.apply_correction(persona_id, body.instruction, session)  # Claude at runtime
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
