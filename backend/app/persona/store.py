"""Persona artifact store — encrypted CRUD + versioning + corrections.

Persists :class:`PersonaArtifacts` onto the ``Persona`` row:
- ``persona_md``  -> ``persona_md_enc``   (Fernet token)
- ``memories_md`` -> ``memories_md_enc``  (Fernet token)
- ``meta``        -> ``meta_json``        (plaintext JSON; non-sensitive sidecar)
- ``persona_json``-> embedded inside ``meta_json`` under ``"persona_json"`` so the
  whole machine-readable persona round-trips with the row.

Every save snapshots the full artifacts into a ``Version`` row and prunes to the
last 10 (ex-skill version_manager pattern). ``apply_correction`` runs the
adapted ``correction_handler.md`` prompt through the injected anthropic client.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, List, Optional

from sqlmodel import Session, select

from .. import crypto
from ..config import settings
from ..db import Correction, Persona, StyleTuning, Version
from ..distill.pipeline import _default_client, _extract_text, _parse_envelope, load_prompt
from ..distill.schema import PersonaArtifacts, PersonaJSON

MAX_VERSIONS = 10


def save_artifacts(
    persona_id: int, arts: PersonaArtifacts, session: Session
) -> Persona:
    """Encrypt + persist artifacts onto the Persona row; snapshot a Version.

    The ``meta_json`` column stores the (non-sensitive) meta dict with the full
    ``persona_json`` nested under a ``persona_json`` key, so the typed 5-layer
    model survives the round-trip alongside the encrypted markdown.
    """
    persona = session.get(Persona, persona_id)
    if persona is None:
        raise ValueError(f"persona {persona_id} not found")

    persona.persona_md_enc = crypto.enc_str(arts.persona_md)
    persona.memories_md_enc = crypto.enc_str(arts.memories_md)

    meta_payload = dict(arts.meta or {})
    meta_payload["persona_json"] = arts.persona_json
    persona.meta_json = json.dumps(meta_payload, ensure_ascii=False)
    persona.updated_at = datetime.utcnow()

    session.add(persona)

    _snapshot_version(persona_id, arts, session)
    session.commit()
    session.refresh(persona)
    _prune_versions(persona_id, session)
    return persona


def load(persona_id: int, session: Session) -> PersonaArtifacts:
    """Decrypt + reassemble artifacts from the Persona row."""
    persona = session.get(Persona, persona_id)
    if persona is None:
        raise ValueError(f"persona {persona_id} not found")
    if not persona.persona_md_enc or not persona.memories_md_enc:
        raise ValueError(f"persona {persona_id} has no saved artifacts")

    persona_md = crypto.dec_str(persona.persona_md_enc)
    memories_md = crypto.dec_str(persona.memories_md_enc)

    meta_payload = json.loads(persona.meta_json or "{}")
    persona_json = meta_payload.pop("persona_json", {}) or {}

    return PersonaArtifacts(
        persona_md=persona_md,
        memories_md=memories_md,
        meta=meta_payload,
        persona_json=persona_json,
    )


def _snapshot_version(
    persona_id: int, arts: PersonaArtifacts, session: Session
) -> None:
    snapshot = json.dumps(arts.model_dump(), ensure_ascii=False)
    session.add(Version(persona_id=persona_id, snapshot_json=snapshot))


def _prune_versions(persona_id: int, session: Session) -> None:
    """Keep only the most recent ``MAX_VERSIONS`` Version rows for a persona."""
    rows = session.exec(
        select(Version)
        .where(Version.persona_id == persona_id)
        .order_by(Version.created_at.desc(), Version.id.desc())
    ).all()
    for stale in rows[MAX_VERSIONS:]:
        session.delete(stale)
    session.commit()


def versions(persona_id: int, session: Session) -> List[Version]:
    """Return saved Version rows, newest first (at most ``MAX_VERSIONS``)."""
    return list(
        session.exec(
            select(Version)
            .where(Version.persona_id == persona_id)
            .order_by(Version.created_at.desc(), Version.id.desc())
        ).all()
    )


# --- Layer-2 style overlay persistence (consumed by E3 convo/style_tuner) ---


def save_style_overlay(
    persona_id: int,
    overlay_json: dict,
    msg_count_at_run: int,
    session: Session,
    conversation_id: Optional[int] = None,
) -> StyleTuning:
    """Persist a periodic Layer-2 style overlay (§9.1).

    Writes the encrypted overlay onto ``Persona.style_overlay_enc`` (the *latest*
    refinement the live engine assembles) AND appends a ``StyleTuning`` history
    row. Core layers (0,1,3,4,5) are never touched here — the tuner's
    ``validate_core_unchanged`` guard runs before calling this. The overlay is a
    Layer-2 dict (the ``layer2_expression`` shape from the persona schema).
    """
    persona = session.get(Persona, persona_id)
    if persona is None:
        raise ValueError(f"persona {persona_id} not found")

    token = crypto.enc_str(json.dumps(overlay_json, ensure_ascii=False))
    persona.style_overlay_enc = token
    persona.updated_at = datetime.utcnow()
    session.add(persona)

    tuning = StyleTuning(
        persona_id=persona_id,
        conversation_id=conversation_id,
        overlay_json_enc=token,
        msg_count_at_run=msg_count_at_run,
    )
    session.add(tuning)
    session.commit()
    session.refresh(tuning)
    return tuning


def load_style_overlay(persona_id: int, session: Session) -> Optional[dict]:
    """Decrypt the latest Layer-2 style overlay, or ``None`` if none saved yet."""
    persona = session.get(Persona, persona_id)
    if persona is None:
        raise ValueError(f"persona {persona_id} not found")
    if not persona.style_overlay_enc:
        return None
    return json.loads(crypto.dec_str(persona.style_overlay_enc))


def _correction_messages(arts: PersonaArtifacts, instruction: str) -> dict:
    system = (
        "You apply a user correction to an existing ex-persona using the "
        "adapted correction_handler prompt below. Preserve everything else; "
        "fold the correction into the right artifact and the right layer. "
        "Mixed Chinese/English is expected.\n\n"
        "Return ONE JSON object (optionally in a ```json fence) with keys "
        '"persona_md", "memories_md", "persona_json", "meta" — the FULL updated '
        "artifacts.\n\n"
        f"===== correction_handler.md =====\n{load_prompt('correction_handler.md')}"
    )
    user = (
        "CURRENT persona.md:\n"
        f"{arts.persona_md}\n\n"
        "CURRENT memories.md:\n"
        f"{arts.memories_md}\n\n"
        "CURRENT persona.json:\n"
        f"{json.dumps(arts.persona_json, ensure_ascii=False)}\n\n"
        "CURRENT meta:\n"
        f"{json.dumps(arts.meta, ensure_ascii=False)}\n\n"
        f"CORRECTION INSTRUCTION:\n{instruction}\n"
    )
    return {"system": system, "user": user}


def apply_correction(
    persona_id: int,
    instruction: str,
    session: Session,
    client: Optional[Any] = None,
) -> PersonaArtifacts:
    """Apply a natural-language correction via the injected anthropic client.

    Loads current artifacts, runs ``correction_handler.md``, saves the updated
    artifacts (new Version snapshot), and records a ``Correction`` row. The
    anthropic client is injected (default real, built lazily) so tests pass a
    fake returning the corrected envelope.
    """
    arts = load(persona_id, session)

    # Demo mode: keyless — record the correction text + bump the counter, no Claude.
    if client is None and settings.demo_mode:
        pj = dict(arts.persona_json or {})
        pj["corrections"] = list(pj.get("corrections") or []) + [instruction]
        meta = dict(arts.meta or {})
        meta["corrections_count"] = int(meta.get("corrections_count", 0)) + 1
        updated = PersonaArtifacts(
            persona_md=arts.persona_md,
            memories_md=arts.memories_md,
            meta=meta,
            persona_json=pj,
        )
        save_artifacts(persona_id, updated, session)
        session.add(Correction(persona_id=persona_id, instruction=instruction))
        session.commit()
        return updated

    if client is None:
        client = _default_client()

    msgs = _correction_messages(arts, instruction)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=8192,
        system=msgs["system"],
        messages=[{"role": "user", "content": msgs["user"]}],
    )
    envelope = _parse_envelope(_extract_text(response))

    persona_json = envelope.get("persona_json", arts.persona_json) or {}
    typed = PersonaJSON.model_validate(persona_json)
    meta = envelope.get("meta", arts.meta) or {}
    # We are the authority on the counter — derive from the prior artifacts so a
    # model that also incremented it can't double-count.
    prior_count = int((arts.meta or {}).get("corrections_count", 0))
    meta["corrections_count"] = prior_count + 1

    updated = PersonaArtifacts(
        persona_md=envelope.get("persona_md", arts.persona_md),
        memories_md=envelope.get("memories_md", arts.memories_md),
        meta=meta,
        persona_json=typed.model_dump(),
    )

    save_artifacts(persona_id, updated, session)
    session.add(Correction(persona_id=persona_id, instruction=instruction))
    session.commit()
    return updated
