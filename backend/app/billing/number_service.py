"""Number provisioning. Gated on the owning user's active subscription:
dev/trial path returns the configured TWILIO_FROM_NUMBER; production path
auto-buys a toll-free number (behind a flag). Twilio client is injected."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session

from ..config import require, settings
from ..db import Number, Persona, User


class SubscriptionRequired(HTTPException):
    """Raised (HTTP 402) when the owning user is not on an active subscription."""

    def __init__(self, detail: str = "Active subscription required") -> None:
        super().__init__(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=detail)


def _default_twilio() -> Any:
    from twilio.rest import Client

    return Client(require("twilio_account_sid"), require("twilio_auth_token"))


def _buy_tollfree(twilio: Any | None) -> str:
    """Auto-buy a US toll-free number via Twilio and return its E.164 address."""
    if twilio is None:
        twilio = _default_twilio()
    available = twilio.available_phone_numbers("US").toll_free.list(limit=1)
    if not available:
        raise RuntimeError("No toll-free numbers available to purchase")
    chosen = available[0].phone_number
    purchased = twilio.incoming_phone_numbers.create(phone_number=chosen)
    return getattr(purchased, "phone_number", chosen)


def provision(
    session: Session,
    persona: Persona,
    twilio: Any | None = None,
    *,
    auto_buy_tollfree: bool = False,
) -> Number:
    """Assign a phone number to `persona`, only if its owner's subscription is
    active. Returns the persisted Number row. Raises SubscriptionRequired (402)
    otherwise.
    """
    owner = session.get(User, persona.user_id)
    # Gate on a real subscription only when billing is actually on (not demo, and
    # the free-for-all switch is off). Free mode assigns the number for everyone.
    billing_on = not settings.demo_mode and settings.require_subscription
    if billing_on and (owner is None or owner.subscription_status != "active"):
        raise SubscriptionRequired()

    if auto_buy_tollfree:
        e164 = _buy_tollfree(twilio)
        mode = "tollfree"
    elif settings.demo_mode:
        e164 = settings.twilio_from_number or "+15555550100"
        mode = "trial"
    else:
        e164 = require("twilio_from_number")
        mode = "trial"

    assert persona.id is not None
    number = Number(persona_id=persona.id, e164=e164, mode=mode, status="assigned")
    session.add(number)
    session.commit()
    session.refresh(number)
    return number
