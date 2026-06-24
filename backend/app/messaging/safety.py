"""Deterministic, pre-model crisis-safety layer (spec §12).

``check(body)`` runs a bilingual keyword/regex tripwire BEFORE any LLM is
touched. On a hit, ``handle_crisis`` bypasses the persona entirely: it sends a
fixed 988 + hotline message via the injected sender, writes a ``SafetyEvent``
row, and alerts the operator (log + optional email stub). We never rely on the
model's own refusal — it is jailbreakable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session

from ..config import settings
from ..db import Conversation, SafetyEvent
from . import crisis_words

log = logging.getLogger("talk_to_ex.safety")


@dataclass
class SafetyVerdict:
    """Outcome of the deterministic tripwire for one inbound body."""

    crisis: bool
    matched: Optional[str] = None


# Static, model-free reply sent on a crisis hit. Bilingual (zh + en) because the
# inbound language is unknown at tripwire time and we must reach the user either
# way. 988 = US Suicide & Crisis Lifeline; a generic local-hotline line follows.
CRISIS_MESSAGE = (
    "It sounds like you're going through something really painful, and you "
    "deserve real support right now. Please reach out to people who can help: "
    "call or text 988 (US Suicide & Crisis Lifeline, 24/7), or text HOME to "
    "741741 (Crisis Text Line). If you're in immediate danger, call 911.\n\n"
    "你现在的痛苦是真实的，你值得被认真对待。请联系能帮助你的人："
    "在美国可拨打或发短信至 988（自杀与危机生命线，全天候）；"
    "在中国大陆可拨打 北京心理危机研究与干预中心热线 010-82951332，"
    "或全国希望24热线 400-161-9995。如有即时危险，请拨打当地急救电话。"
)


def check(body: str) -> SafetyVerdict:
    """Return a :class:`SafetyVerdict` flagging self-harm/suicide content.

    English is matched case-insensitively; Chinese substrings are matched on the
    raw text. Regexes catch small phrasing variations across both languages.
    """
    if not body:
        return SafetyVerdict(crisis=False)

    lowered = body.lower()

    for kw in crisis_words.EN_KEYWORDS:
        if kw in lowered:
            return SafetyVerdict(crisis=True, matched=kw)

    for kw in crisis_words.ZH_KEYWORDS:
        if kw in body:
            return SafetyVerdict(crisis=True, matched=kw)

    for pat in crisis_words.CRISIS_PATTERNS:
        if pat.search(body):
            return SafetyVerdict(crisis=True, matched=pat.pattern)

    return SafetyVerdict(crisis=False)


def _alert_operator(conv: Conversation, body: str) -> None:
    """Notify the operator of a crisis hit (log always; email is a stub).

    The email path is intentionally a stub for the scaffold: it only fires when
    ``operator_alert_email`` is configured, and never raises into the request /
    background path. Wire a real transport here at bring-up.
    """
    log.warning(
        "CRISIS tripwire fired on conversation %s (peer=%s): %r",
        conv.id,
        conv.peer_e164,
        body,
    )
    if settings.operator_alert_email:
        # Stub: a real SMTP/API send goes here. Kept side-effect-free + safe.
        log.warning(
            "operator alert would be emailed to %s (conversation %s)",
            settings.operator_alert_email,
            conv.id,
        )


def handle_crisis(session: Session, conv: Conversation, sender) -> SafetyEvent:
    """Run the crisis response: hotline reply, ``SafetyEvent`` log, operator alert.

    ``sender`` is any object with ``send_bubbles(to, from_, bubbles)`` (injected
    in tests). The reply goes to ``conv.peer_e164`` from the configured
    ``twilio_from_number`` (single-number scaffold). Returns the persisted
    ``SafetyEvent`` row.
    """
    sender.send_bubbles(
        to=conv.peer_e164,
        from_=settings.twilio_from_number,
        bubbles=[CRISIS_MESSAGE],
    )

    event = SafetyEvent(conversation_id=conv.id, kind="crisis", body=CRISIS_MESSAGE)
    session.add(event)
    session.commit()
    session.refresh(event)

    _alert_operator(conv, CRISIS_MESSAGE)
    return event
