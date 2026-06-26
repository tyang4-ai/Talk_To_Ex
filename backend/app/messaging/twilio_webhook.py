"""Twilio inbound SMS webhook (spec §6, §8, §12, §13).

``POST /sms`` is the single ingress for friend→persona texts. It must return an
empty TwiML ``<Response></Response>`` well within Twilio's ~15 s timeout, then
do the slow work (local Ollama reply) asynchronously:

1. Validate ``X-Twilio-Signature`` (Twilio ``RequestValidator``) → 403 on fail.
2. Parse the ``application/x-www-form-urlencoded`` body (``From``/``To``/``Body``).
3. Honor the global ``kill_switch`` and a simple per-peer rate cap → ack-and-drop.
4. Run the deterministic crisis tripwire (``safety.check``) BEFORE the model. On
   a hit → ``safety.handle_crisis`` (hotline + SafetyEvent + operator alert),
   then return empty TwiML — the persona is never invoked.
5. Otherwise schedule ``_respond`` as a background task and return empty TwiML
   immediately.

The reply work runs in ``_respond`` with its OWN database session, because the
request-scoped session is closed once the TwiML response is sent.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import APIRouter, Request, Response
from starlette.background import BackgroundTask
from sqlmodel import Session, select

from twilio.request_validator import RequestValidator

from ..billing import metering
from ..config import settings
from ..convo import engine, history, style_tuner, summary
from ..db import Conversation, Number, engine as db_engine
from . import safety
from .sender import Sender

log = logging.getLogger("talk_to_ex.messaging")

router = APIRouter()

# Empty TwiML acknowledgement — exact literal Twilio expects (no XML decl).
EMPTY_TWIML = "<Response></Response>"
TWIML_MEDIA_TYPE = "application/xml"

# One module-level sender so tests can swap it for a fake recorder.
sender = Sender()

# --- per-peer rate cap -----------------------------------------------------
# Bound runaway loops / cost: at most RATE_MAX inbound messages per peer within
# RATE_WINDOW_S. State is in-process (single-box scaffold) and resettable.
RATE_MAX = 20
RATE_WINDOW_S = 60.0
_peer_hits: dict[str, deque] = defaultdict(deque)


def reset_rate_limiter() -> None:
    """Clear per-peer rate-cap state (used by tests, mirrors billing's reset)."""
    _peer_hits.clear()


def _rate_limited(peer: str, now: Optional[float] = None) -> bool:
    """Return True if ``peer`` has exceeded the cap in the rolling window."""
    now = time.monotonic() if now is None else now
    hits = _peer_hits[peer]
    cutoff = now - RATE_WINDOW_S
    while hits and hits[0] < cutoff:
        hits.popleft()
    if len(hits) >= RATE_MAX:
        return True
    hits.append(now)
    return False


def _twiml_response(background: Optional[BackgroundTask] = None) -> Response:
    """Build the empty-TwiML 200 ack, optionally carrying a background task."""
    return Response(
        content=EMPTY_TWIML,
        media_type=TWIML_MEDIA_TYPE,
        status_code=200,
        background=background,
    )


def _resolve_persona_id(session: Session, our_number: str) -> Optional[int]:
    """Map the inbound ``To`` (our Twilio number) to the owning persona id."""
    stmt = select(Number).where(Number.e164 == our_number)
    num = session.exec(stmt).first()
    return num.persona_id if num else None


def _respond(persona_id: int, peer_e164: str, our_number: str, body: str) -> None:
    """Background worker: generate + send the persona's reply, then persist.

    Opens its OWN session (the request session is already closed). Ordering is
    load-bearing: ``engine.reply`` appends ``body`` as the latest user turn and
    reads prior history itself, so we must call it BEFORE persisting the inbound
    message — otherwise the inbound would appear twice in the prompt.
    """
    try:
        with Session(db_engine) as session:
            conv = engine.get_or_create_conversation(session, persona_id, peer_e164)

            # 0) Freemium gate (spec §25): past the free allowance and no active
            # subscription → send the paywall instead of a persona reply. Crisis
            # safety already ran in the webhook, so it is never short-circuited.
            if metering.should_paywall(session, persona_id):
                sender.send_bubbles(
                    to=peer_e164,
                    from_=our_number,
                    bubbles=[metering.paywall_message()],
                )
                history.append(session, conv, "in", body)  # count it; no reply
                return

            # 1) Generate the reply from prior context + this (unpersisted) turn.
            bubbles = engine.reply(session, persona_id, peer_e164, body)

            # 1b) Outbound safety screen (§24.4): never send model output that
            # trips the deterministic tripwire — block the whole reply + log.
            if not all(safety.screen_outbound(b) for b in bubbles):
                safety.record_blocked_outbound(session, conv, " / ".join(bubbles))
                history.append(session, conv, "in", body)  # count the inbound
                return

            # 2) Send each bubble out via Twilio REST (to the friend, from us).
            sender.send_bubbles(to=peer_e164, from_=our_number, bubbles=bubbles)

            # 3) Now persist the turns: inbound first, then each outbound bubble.
            history.append(session, conv, "in", body)
            for bubble in bubbles:
                history.append(session, conv, "out", bubble)

            # 4) Periodic maintenance keyed off the refreshed message_count.
            summary.maybe_resummarize(session, conv)
            style_tuner.maybe_retune(session, conv)
    except Exception:  # never let a background failure crash silently-unlogged
        log.exception("reply background task failed (peer=%s)", peer_e164)


def _signature_ok(request: Request, params: dict, signature: str) -> bool:
    """Validate the Twilio signature, tolerant of the reverse proxy.

    Twilio signs the PUBLIC https URL it POSTs to, but behind the Cloudflare
    tunnel ``request.url`` is the internal ``http://localhost`` one, so a naive
    check rejects every real message. Accept a match against either the URL the
    app computed (correct when uvicorn runs with ``--proxy-headers``) or the
    configured public ``app_url`` + path.
    """
    validator = RequestValidator(settings.twilio_auth_token)
    candidates = [str(request.url)]
    if settings.app_url:
        candidates.append(settings.app_url.rstrip("/") + request.url.path)
    return any(validator.validate(u, params, signature) for u in candidates)


@router.post("/sms")
async def inbound_sms(request: Request) -> Response:
    """Twilio inbound-SMS webhook. Validates, gates, and acks with empty TwiML."""
    raw_signature = request.headers.get("X-Twilio-Signature", "")
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}

    if not _signature_ok(request, params, raw_signature):
        return Response(status_code=403, content="invalid signature")

    sender_e164 = params.get("From", "")
    our_number = params.get("To", "")
    body = params.get("Body", "")

    # Global kill-switch: silence ALL replies instantly (ack so Twilio stops).
    if settings.kill_switch:
        return _twiml_response()

    # Per-peer rate cap: ack-and-drop past the ceiling.
    if sender_e164 and _rate_limited(sender_e164):
        log.warning("rate cap hit for peer %s — dropping inbound", sender_e164)
        return _twiml_response()

    # Deterministic crisis tripwire — runs BEFORE the model.
    verdict = safety.check(body)
    if verdict.crisis:
        with Session(db_engine) as session:
            persona_id = _resolve_persona_id(session, our_number)
            if persona_id is not None:
                conv = engine.get_or_create_conversation(
                    session, persona_id, sender_e164
                )
                safety.handle_crisis(session, conv, sender)
            else:
                log.warning(
                    "crisis inbound to unknown number %s — alerting only", our_number
                )
        return _twiml_response()

    # Safe path: resolve persona, schedule the slow reply, ack immediately.
    with Session(db_engine) as session:
        persona_id = _resolve_persona_id(session, our_number)
    if persona_id is None:
        log.warning("inbound to unassigned number %s — ignoring", our_number)
        return _twiml_response()

    task = BackgroundTask(_respond, persona_id, sender_e164, our_number, body)
    return _twiml_response(background=task)
