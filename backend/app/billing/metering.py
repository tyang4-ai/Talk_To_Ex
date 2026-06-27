"""Freemium metering (spec §25).

The friend gets ``settings.free_message_limit`` free inbound messages per persona;
past that, replies require the owning user's subscription to be ``active``. Because
live inference is local (≈ free), the free tier is nearly costless — this gate is
about monetizing continued access, not covering per-message cost.

Counted unit = the friend's **inbound** messages for the persona (``direction=="in"``
across the persona's conversations). The paywall is enforced at the messaging
gateway, after the deterministic crisis tripwire (which always runs first).
"""
from __future__ import annotations

import json

from sqlalchemy import func
from sqlmodel import Session, select

from ..config import settings
from ..db import Conversation, Message, Persona, User

PAYWALL_MESSAGE = (
    "You've used up your free messages 💔 "
    "Subscribe to keep texting: {url}"
)

# Sent ONCE when the friend hits the free message cap (free mode has no Stripe, so
# this is a plain "you're done" notice rather than a subscribe pitch).
LIMIT_MESSAGE = (
    "💔 that's all the free messages for now — hope it gave you a little closure. "
    "(thanks for using Ex.Change.)"
)


def inbound_count(session: Session, persona_id: int) -> int:
    """Number of inbound (friend→persona) messages across the persona's threads."""
    stmt = (
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.persona_id == persona_id, Message.direction == "in")
    )
    return int(session.exec(stmt).one() or 0)


def subscription_active(session: Session, persona_id: int) -> bool:
    """Whether the persona's owning user has an active subscription.

    Always True when billing is off (demo mode, or the free-for-all master switch
    ``require_subscription=False``) — replies never paywall.
    """
    if settings.demo_mode or not settings.require_subscription:
        return True
    persona = session.get(Persona, persona_id)
    if persona is None:
        return False
    user = session.get(User, persona.user_id)
    return bool(user and user.subscription_status == "active")


def over_free_limit(session: Session, persona_id: int) -> bool:
    """True once prior inbound count has reached the free allowance."""
    return inbound_count(session, persona_id) >= settings.free_message_limit


def should_paywall(session: Session, persona_id: int) -> bool:
    """True if this persona is past its free allowance AND not subscribed."""
    return over_free_limit(session, persona_id) and not subscription_active(
        session, persona_id
    )


def paywall_message() -> str:
    """The templated paywall SMS, with the portal/checkout link filled in."""
    return PAYWALL_MESSAGE.format(url=settings.app_url)


# --- per-friend hard cap (applies even in free-for-all mode) ----------------
# Distinct from should_paywall: this is a flat per-friend ceiling that fires even
# when require_subscription is off (free mode). A paid subscription still lifts it.

def friend_capped(session: Session, persona_id: int) -> bool:
    """True once the friend has used the free allowance and the owner is not on a
    paid plan — enforced regardless of the free-for-all switch."""
    if not over_free_limit(session, persona_id):
        return False
    persona = session.get(Persona, persona_id)
    user = session.get(User, persona.user_id) if persona else None
    return not (user and user.subscription_status == "active")


def cap_already_notified(session: Session, persona_id: int) -> bool:
    """Whether the one-time 'limit reached' notice has already gone out."""
    persona = session.get(Persona, persona_id)
    if persona is None:
        return True
    meta = json.loads(persona.meta_json or "{}")
    return bool(meta.get("cap_notified"))


def mark_cap_notified(session: Session, persona_id: int) -> None:
    """Record that the friend has been told they hit the cap (so we tell once)."""
    persona = session.get(Persona, persona_id)
    if persona is None:
        return
    meta = json.loads(persona.meta_json or "{}")
    meta["cap_notified"] = True
    persona.meta_json = json.dumps(meta, ensure_ascii=False)
    session.add(persona)
    session.commit()


def limit_message() -> str:
    return LIMIT_MESSAGE
