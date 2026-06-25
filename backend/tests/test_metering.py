"""E11 — freemium metering + paywall (spec §25).

Past FREE_MESSAGE_LIMIT inbound messages, an inactive subscription gets a paywall
message instead of a persona reply; an active subscription replies normally; crisis
safety still runs first regardless. Mock-based (no Ollama, no Twilio network)."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.billing import metering
from app.config import settings
from app.db import Conversation, Message, Number, Persona, User
from app.messaging import twilio_webhook

OUR = "+18445550000"
PEER = "+15555550100"


@pytest.fixture()
def db_engine(monkeypatch):
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(twilio_webhook, "db_engine", eng)
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "twilio_from_number", OUR)
    monkeypatch.setattr(settings, "app_url", "https://ex.example/plan")
    monkeypatch.setattr(settings, "free_message_limit", 2)
    return eng


@pytest.fixture()
def seed(db_engine):
    with Session(db_engine) as s:
        user = User(email="f@example.com", pw_hash="x", subscription_status="inactive")
        s.add(user)
        s.commit()
        s.refresh(user)
        persona = Persona(user_id=user.id, slug="m", name="小美")
        s.add(persona)
        s.commit()
        s.refresh(persona)
        s.add(Number(persona_id=persona.id, e164=OUR, mode="trial"))
        s.commit()
        return persona.id


def _seed_inbound(db_engine, persona_id, n):
    with Session(db_engine) as s:
        conv = Conversation(persona_id=persona_id, peer_e164=PEER)
        s.add(conv)
        s.commit()
        s.refresh(conv)
        for i in range(n):
            s.add(Message(conversation_id=conv.id, direction="in", body=f"m{i}"))
        s.commit()


def _activate(db_engine, persona_id):
    with Session(db_engine) as s:
        p = s.get(Persona, persona_id)
        u = s.get(User, p.user_id)
        u.subscription_status = "active"
        s.add(u)
        s.commit()


class RecordingSender:
    def __init__(self):
        self.calls = []

    def send_bubbles(self, to, from_, bubbles, twilio=None, sleeper=None):
        self.calls.append({"to": to, "from_": from_, "bubbles": list(bubbles)})


# --- unit ------------------------------------------------------------------
def test_count_and_limit_helpers(db_engine, seed):
    with Session(db_engine) as s:
        assert metering.inbound_count(s, seed) == 0
        assert metering.over_free_limit(s, seed) is False
        assert metering.should_paywall(s, seed) is False
    _seed_inbound(db_engine, seed, 2)  # limit == 2
    with Session(db_engine) as s:
        assert metering.inbound_count(s, seed) == 2
        assert metering.over_free_limit(s, seed) is True
        assert metering.subscription_active(s, seed) is False
        assert metering.should_paywall(s, seed) is True


def test_active_subscription_bypasses_limit(db_engine, seed):
    _seed_inbound(db_engine, seed, 9)
    _activate(db_engine, seed)
    with Session(db_engine) as s:
        assert metering.subscription_active(s, seed) is True
        assert metering.should_paywall(s, seed) is False


def test_free_mode_disables_paywall(db_engine, seed, monkeypatch):
    """The free-for-all switch opens replies regardless of count or subscription."""
    _seed_inbound(db_engine, seed, 9)  # well past the limit, inactive sub
    monkeypatch.setattr(settings, "require_subscription", False)
    with Session(db_engine) as s:
        assert metering.over_free_limit(s, seed) is True
        assert metering.subscription_active(s, seed) is True
        assert metering.should_paywall(s, seed) is False


# --- gate in _respond ------------------------------------------------------
def test_respond_paywalls_over_limit(db_engine, seed, monkeypatch):
    _seed_inbound(db_engine, seed, 2)  # at the free limit, inactive
    rec = RecordingSender()
    monkeypatch.setattr(twilio_webhook, "sender", rec)
    monkeypatch.setattr(
        twilio_webhook.engine, "reply",
        lambda *a, **k: pytest.fail("engine must not run past the paywall"),
    )

    twilio_webhook._respond(seed, PEER, OUR, "let me back in")

    assert len(rec.calls) == 1
    msg = rec.calls[0]["bubbles"][0]
    assert "Subscribe" in msg and "https://ex.example/plan" in msg
    # the inbound was still counted
    with Session(db_engine) as s:
        assert metering.inbound_count(s, seed) == 3


def test_respond_replies_when_active(db_engine, seed, monkeypatch):
    _seed_inbound(db_engine, seed, 5)  # well past the free limit
    _activate(db_engine, seed)
    rec = RecordingSender()
    monkeypatch.setattr(twilio_webhook, "sender", rec)
    monkeypatch.setattr(twilio_webhook.engine, "reply", lambda *a, **k: ["hi", "there"])

    twilio_webhook._respond(seed, PEER, OUR, "yo")

    assert rec.calls[0]["bubbles"] == ["hi", "there"]
