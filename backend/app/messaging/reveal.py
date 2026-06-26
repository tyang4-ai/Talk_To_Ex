"""The "reveal" — bring a persona live and send the proactive opener (spec §24).

When a persona's fine-tune job completes, the persona goes ``active`` and texts
the friend FIRST with the curated opener (``opener.first_message``). The send is
gated by the global kill-switch (opt-out) and the outbound safety screen
(§24.4). The friend's own phone number — captured at sign-up — is stored on the
persona (``meta_json["peer_e164"]``); we text it FROM the persona's assigned
Twilio number.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from ..config import settings
from ..convo import engine, history
from ..db import Job, Number, Persona
from . import opener, safety
from .sender import Sender

log = logging.getLogger("talk_to_ex.reveal")


def go_live(session: Session, persona_id: int, sender: Optional[object] = None) -> bool:
    """Activate the persona and send its opener. Returns True if the opener went out.

    Respects the global kill-switch (opt-out) and the deterministic outbound
    safety screen. No-ops (returns False) if the friend's number or the persona's
    Twilio number is missing, or if silenced/blocked.
    """
    persona = session.get(Persona, persona_id)
    if persona is None:
        return False
    if settings.kill_switch:
        log.warning("kill-switch on — not sending opener for persona %s", persona_id)
        return False

    meta = json.loads(persona.meta_json or "{}")
    peer = meta.get("peer_e164")
    number = session.exec(
        select(Number).where(Number.persona_id == persona_id)
    ).first()
    if not peer or number is None:
        log.warning(
            "cannot send opener for persona %s — missing peer (%r) or number (%r)",
            persona_id, peer, number,
        )
        return False

    text = opener.first_message(persona)
    conv = engine.get_or_create_conversation(session, persona_id, peer)

    # Outbound safety screen — never send the opener if it trips the tripwire.
    if not safety.screen_outbound(text):
        safety.record_blocked_outbound(session, conv, text)
        return False

    persona.status = "active"
    meta["opt_in_at"] = meta.get("opt_in_at") or datetime.utcnow().isoformat()
    persona.meta_json = json.dumps(meta, ensure_ascii=False)
    persona.updated_at = datetime.utcnow()
    session.add(persona)
    session.commit()

    sndr = sender if sender is not None else Sender()
    sndr.send_bubbles(to=peer, from_=number.e164, bubbles=[text])
    history.append(session, conv, "out", text)
    log.info("persona %s is live — opener sent to %s", persona_id, peer)
    return True


def on_finetune_ready(session: Session, job: Job, sender: Optional[object] = None) -> bool:
    """Worker hook for a READY fine-tune job. In the chained build the persona was
    ALREADY revealed right after distillation (the ex texted first on the prompt-only
    voice); the fine-tune is a SILENT voice upgrade the live engine picks up via
    ``meta["adapter_model"]``. So this NO LONGER sends an opener — doing so would
    text the friend a second time. It only records the upgrade and returns False
    (nothing sent). ``sender`` is accepted for signature stability."""
    if job.kind != "finetune" or job.status != "ready":
        return False
    log.info("persona %s fine-tune ready — voice upgraded silently (no opener)", job.persona_id)
    return False
