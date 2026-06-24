"""E5 tests — auth (register/login/JWT/protected route) + Stripe billing
(checkout DI, webhook event → subscription state) + number provisioning gate.
Fully mock-based: no network, no real keys, in-memory SQLite only."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from fastapi import FastAPI

from app.auth.jwt import create_access_token, decode_token, hash_password, verify_password
from app.billing import number_service, stripe_service
from app.billing.number_service import SubscriptionRequired
from app.billing.webhook import apply_event, reset_idempotency
from app.db import Number, Persona, User, get_session


# ---------------------------------------------------------------------------
# Fixtures: an isolated in-memory DB wired into a fresh app holding only E5's
# routers — so these tests don't depend on sibling epics' routes.py existing,
# and don't trigger the real app's file-DB lifespan.
# ---------------------------------------------------------------------------
@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture()
def client(engine):
    from app.auth.routes import router as auth_router
    from app.billing.routes import router as billing_router
    from app.billing.webhook import router as webhook_router

    def _override():
        with Session(engine) as s:
            yield s

    test_app = FastAPI()
    for r in (auth_router, billing_router, webhook_router):
        test_app.include_router(r)
    test_app.dependency_overrides[get_session] = _override
    reset_idempotency()
    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# JWT + password helpers
# ---------------------------------------------------------------------------
def test_password_hash_roundtrip():
    h = hash_password("s3cr3t-中文")
    assert h != "s3cr3t-中文"
    assert verify_password("s3cr3t-中文", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip():
    token = create_access_token(42)
    payload = decode_token(token)
    assert payload["sub"] == "42"


# ---------------------------------------------------------------------------
# Auth routes: register + login issue a JWT; protected route 401s without it.
# ---------------------------------------------------------------------------
def test_register_login_and_protected_route(client):
    reg = client.post(
        "/api/auth/register", json={"email": "Friend@Example.com", "password": "pw12345"}
    )
    assert reg.status_code == 201, reg.text
    body = reg.json()
    token = body["access_token"]
    assert token
    assert body["email"] == "friend@example.com"
    assert body["subscription_status"] == "inactive"

    # Duplicate registration is rejected.
    dup = client.post(
        "/api/auth/register", json={"email": "friend@example.com", "password": "pw12345"}
    )
    assert dup.status_code == 409

    # Login (case-insensitive email) issues a fresh JWT.
    login = client.post(
        "/api/auth/login", json={"email": "FRIEND@example.com", "password": "pw12345"}
    )
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]

    # Wrong password → 401.
    bad = client.post(
        "/api/auth/login", json={"email": "friend@example.com", "password": "nope"}
    )
    assert bad.status_code == 401

    # Protected route requires the bearer token (401 without it).
    no_auth = client.get("/api/auth/me")
    assert no_auth.status_code == 401  # missing creds

    ok = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    assert ok.json()["email"] == "friend@example.com"

    bad_token = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert bad_token.status_code == 401


# ---------------------------------------------------------------------------
# Stripe checkout: client is injected; secret read only at the boundary.
# ---------------------------------------------------------------------------
class _FakeSession:
    def __init__(self, **params):
        self.url = "https://checkout.stripe.test/session/cs_123"
        self.params = params


class _FakeStripe:
    """Mimics the bits of the stripe module create_checkout touches."""

    def __init__(self):
        self.api_key = None
        self.captured = {}

        outer = self

        class _Session:
            @staticmethod
            def create(**params):
                outer.captured = params
                return _FakeSession(**params)

        class _Checkout:
            Session = _Session

        self.checkout = _Checkout()


def test_create_checkout_uses_injected_client():
    fake = _FakeStripe()
    user = User(id=7, email="friend@example.com", pw_hash="x")
    url = stripe_service.create_checkout(user, client=fake)
    assert url == "https://checkout.stripe.test/session/cs_123"
    assert fake.api_key  # secret was set from settings at the boundary
    assert fake.captured["mode"] == "subscription"
    assert fake.captured["client_reference_id"] == "7"
    assert fake.captured["metadata"]["user_id"] == "7"
    assert fake.captured["line_items"][0]["price"]  # STRIPE_PRICE_ID


# ---------------------------------------------------------------------------
# Webhook: a fake checkout.session.completed flips the user to active; then
# number_service.provision succeeds. An inactive user → provision raises.
# Idempotency: replaying the same event id is a no-op.
# ---------------------------------------------------------------------------
def _make_user(session: Session, status: str = "inactive") -> User:
    u = User(email="friend@example.com", pw_hash=hash_password("pw"), subscription_status=status)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _make_persona(session: Session, user: User) -> Persona:
    p = Persona(user_id=user.id, slug="ex", name="Alex")
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def test_checkout_completed_activates_then_provision_succeeds(session):
    reset_idempotency()
    user = _make_user(session, "inactive")
    persona = _make_persona(session, user)

    # Inactive user cannot provision a number.
    with pytest.raises(SubscriptionRequired):
        number_service.provision(session, persona)

    event = {
        "id": "evt_001",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "object": "checkout.session",
                "client_reference_id": str(user.id),
                "metadata": {"user_id": str(user.id)},
                "customer": "cus_ABC",
                "subscription": "sub_XYZ",
            }
        },
    }
    assert apply_event(session, event) is True

    session.refresh(user)
    assert user.subscription_status == "active"
    assert user.stripe_customer_id == "cus_ABC"
    assert user.subscription_id == "sub_XYZ"

    # Now provisioning succeeds and records a Number (dev/trial path).
    number = number_service.provision(session, persona)
    assert isinstance(number, Number)
    assert number.mode == "trial"
    assert number.e164  # from TWILIO_FROM_NUMBER
    assert number.persona_id == persona.id

    # Replaying the same event id is idempotent (no-op).
    assert apply_event(session, event) is False


def test_subscription_deleted_deactivates(session):
    reset_idempotency()
    user = _make_user(session, "active")
    user.stripe_customer_id = "cus_DEF"
    session.add(user)
    session.commit()

    event = {
        "id": "evt_del",
        "type": "customer.subscription.deleted",
        "data": {"object": {"object": "subscription", "id": "sub_1", "customer": "cus_DEF"}},
    }
    assert apply_event(session, event) is True
    session.refresh(user)
    assert user.subscription_status == "canceled"


def test_invoice_paid_keeps_active_resolved_by_customer(session):
    reset_idempotency()
    user = _make_user(session, "inactive")
    user.stripe_customer_id = "cus_GHI"
    session.add(user)
    session.commit()

    event = {
        "id": "evt_inv",
        "type": "invoice.paid",
        "data": {"object": {"object": "invoice", "customer": "cus_GHI"}},
    }
    assert apply_event(session, event) is True
    session.refresh(user)
    assert user.subscription_status == "active"


def test_unhandled_event_is_ignored(session):
    reset_idempotency()
    event = {"id": "evt_x", "type": "payment_intent.created", "data": {"object": {}}}
    assert apply_event(session, event) is False


def test_provision_tollfree_uses_injected_twilio(session):
    reset_idempotency()
    user = _make_user(session, "active")
    persona = _make_persona(session, user)

    class _Num:
        phone_number = "+18445550123"

    class _TollFree:
        @staticmethod
        def list(limit=1):
            return [_Num()]

    class _Available:
        toll_free = _TollFree()

    class _IncomingNumbers:
        @staticmethod
        def create(phone_number):
            obj = _Num()
            obj.phone_number = phone_number
            return obj

    class _FakeTwilio:
        incoming_phone_numbers = _IncomingNumbers()

        @staticmethod
        def available_phone_numbers(country):
            return _Available()

    number = number_service.provision(
        session, persona, twilio=_FakeTwilio(), auto_buy_tollfree=True
    )
    assert number.mode == "tollfree"
    assert number.e164 == "+18445550123"
