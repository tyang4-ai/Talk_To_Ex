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

from sqlalchemy import func
from sqlmodel import Session, select

from ..config import settings
from ..db import Conversation, Message, Persona, User

PAYWALL_MESSAGE = (
    "You've used up your free messages 💔 "
    "Subscribe to keep texting: {url}"
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
    """Whether the persona's owning user has an active subscription."""
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
