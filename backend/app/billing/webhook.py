"""Stripe webhook: verify the signature, then mutate subscription state.

Handlers are idempotent — keyed by Stripe event id — and split from the HTTP
route so tests can drive `apply_event(session, event)` directly with a fake
event dict, no signature needed.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from ..config import require
from ..db import User, get_session

router = APIRouter(tags=["billing"])

# Event ids we've already processed. In-process is sufficient for this single
# instance scaffold; Stripe retries are deduped here so a replayed event is a
# no-op that still returns 200.
_processed_event_ids: set[str] = set()

# Events that turn a subscription ON.
_ACTIVATING = {"checkout.session.completed", "invoice.paid"}
# Events that turn it OFF.
_DEACTIVATING = {"customer.subscription.deleted"}


def reset_idempotency() -> None:
    """Test helper: clear the processed-event cache."""
    _processed_event_ids.clear()


def _resolve_user(session: Session, obj: dict[str, Any]) -> User | None:
    """Find the User a Stripe event object refers to, most-specific first."""
    metadata = obj.get("metadata") or {}
    candidates_id = [
        metadata.get("user_id"),
        obj.get("client_reference_id"),
    ]
    for raw in candidates_id:
        if raw is None:
            continue
        try:
            user = session.get(User, int(raw))
        except (TypeError, ValueError):
            user = None
        if user is not None:
            return user

    customer_id = obj.get("customer")
    if customer_id:
        user = session.exec(
            select(User).where(User.stripe_customer_id == customer_id)
        ).first()
        if user is not None:
            return user

    email = obj.get("customer_email") or (obj.get("customer_details") or {}).get("email")
    if email:
        user = session.exec(select(User).where(User.email == email.lower())).first()
        if user is not None:
            return user
    return None


def _bind_stripe_ids(user: User, obj: dict[str, Any]) -> None:
    customer_id = obj.get("customer")
    if customer_id and not user.stripe_customer_id:
        user.stripe_customer_id = customer_id
    sub_id = obj.get("subscription") or (
        obj.get("id") if obj.get("object") == "subscription" else None
    )
    if sub_id:
        user.subscription_id = sub_id


def apply_event(session: Session, event: dict[str, Any]) -> bool:
    """Apply a (already-verified) Stripe event to subscription state.

    Returns True if the event was applied, False if it was a duplicate or an
    event type we don't act on. Idempotent by `event["id"]`.
    """
    event_id = event.get("id")
    if event_id is not None:
        if event_id in _processed_event_ids:
            return False
        _processed_event_ids.add(event_id)

    event_type = event.get("type")
    if event_type not in _ACTIVATING and event_type not in _DEACTIVATING:
        return False

    obj = ((event.get("data") or {}).get("object")) or {}
    user = _resolve_user(session, obj)
    if user is None:
        return False

    _bind_stripe_ids(user, obj)
    if event_type in _ACTIVATING:
        user.subscription_status = "active"
    else:
        user.subscription_status = "canceled"

    session.add(user)
    session.commit()
    return True


def construct_event(payload: bytes, sig_header: str, client: Any | None = None) -> dict[str, Any]:
    """Verify the signature and return the event. `client` defaults to the real
    stripe module; the webhook secret is required only here."""
    if client is None:
        import stripe

        client = stripe
    secret = require("stripe_webhook_secret")
    event = client.Webhook.construct_event(payload, sig_header, secret)
    if not isinstance(event, dict):
        # Real stripe returns a StripeObject (dict-like); normalize to plain dict.
        event = dict(event)
    return event


@router.post("/api/stripe/webhook")
async def stripe_webhook(
    request: Request, session: Session = Depends(get_session)
) -> dict[str, bool]:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = construct_event(payload, sig_header)
    except RuntimeError:
        # Missing webhook secret at the boundary.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook secret not configured",
        )
    except Exception:
        # Signature/payload verification failed.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature"
        )
    applied = apply_event(session, event)
    return {"received": True, "applied": applied}
