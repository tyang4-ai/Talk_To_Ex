"""E4 messaging gateway + safety tests — fully mock-based (no network, no keys).

Covers:
* the inbound webhook returns 200 with body ``<Response></Response>`` and
  schedules a background reply task for a benign message (signed with a valid
  X-Twilio-Signature via RequestValidator);
* an invalid signature → 403;
* crisis input (zh ``我想自杀`` + en ``i want to kill myself``) bypasses the
  engine, sends the static hotline message, and logs a ``SafetyEvent`` — with a
  fake sender/twilio injected.
Mixed zh/en throughout.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool
from twilio.request_validator import RequestValidator

from app.config import settings
from app.db import Conversation, Message, Number, Persona, SafetyEvent, User
from app.messaging import safety, twilio_webhook
from app.messaging.safety import CRISIS_MESSAGE, SafetyVerdict, check


# ---------------------------------------------------------------------------
# Shared fixtures: in-memory DB wired into both the global engine the webhook's
# background/crisis paths use AND a fresh app holding only the messaging router.
# ---------------------------------------------------------------------------
AUTH_TOKEN = "test-twilio-auth-token"
OUR_NUMBER = "+18445550000"
PEER = "+15555550100"


@pytest.fixture()
def db_engine(monkeypatch):
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    # The webhook opens its OWN sessions from app.db.engine; point it at this DB.
    monkeypatch.setattr(twilio_webhook, "db_engine", eng)
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "twilio_auth_token", AUTH_TOKEN)
    monkeypatch.setattr(settings, "twilio_from_number", OUR_NUMBER)
    monkeypatch.setattr(settings, "kill_switch", False)
    twilio_webhook.reset_rate_limiter()
    return eng


@pytest.fixture()
def seed(db_engine):
    """Persona + a Number bound to OUR_NUMBER so To→persona resolves."""
    with Session(db_engine) as s:
        user = User(email="friend@example.com", pw_hash="x")
        s.add(user)
        s.commit()
        s.refresh(user)
        persona = Persona(user_id=user.id, slug="xiao-mei", name="小美 / Mei")
        s.add(persona)
        s.commit()
        s.refresh(persona)
        s.add(Number(persona_id=persona.id, e164=OUR_NUMBER, mode="trial"))
        s.commit()
        return persona.id


@pytest.fixture()
def client(db_engine):
    app = FastAPI()
    app.include_router(twilio_webhook.router)
    with TestClient(app) as c:
        yield c


def _sign(url: str, params: dict) -> str:
    return RequestValidator(AUTH_TOKEN).compute_signature(url, params)


# ---------------------------------------------------------------------------
# safety.check — bilingual tripwire unit coverage
# ---------------------------------------------------------------------------
def test_check_flags_chinese_self_harm():
    v = check("我想自杀")
    assert isinstance(v, SafetyVerdict)
    assert v.crisis is True


def test_check_flags_english_self_harm():
    assert check("i want to kill myself").crisis is True
    assert check("I WANT TO DIE").crisis is True  # case-insensitive


def test_check_passes_benign():
    assert check("hey, you up? 在吗").crisis is False
    assert check("").crisis is False


# ---------------------------------------------------------------------------
# Webhook: benign message → 200 + empty TwiML + scheduled background task.
# ---------------------------------------------------------------------------
def test_benign_message_acks_and_schedules(client, seed, monkeypatch):
    called = {}

    def fake_respond(persona_id, peer_e164, our_number, body):
        called["args"] = (persona_id, peer_e164, our_number, body)

    # Replace the real reply worker so we assert scheduling without Ollama/DB.
    monkeypatch.setattr(twilio_webhook, "_respond", fake_respond)

    params = {"From": PEER, "To": OUR_NUMBER, "Body": "hey 在吗"}
    url = "http://testserver/sms"
    resp = client.post(
        "/sms",
        data=params,
        headers={"X-Twilio-Signature": _sign(url, params)},
    )

    assert resp.status_code == 200
    assert resp.text == "<Response></Response>"
    assert resp.headers["content-type"].startswith("application/xml")

    # TestClient runs the response's background task before returning.
    assert called["args"][0] == seed  # persona resolved from To→Number
    assert called["args"][1] == PEER
    assert called["args"][2] == OUR_NUMBER
    assert called["args"][3] == "hey 在吗"


# ---------------------------------------------------------------------------
# Webhook: invalid / missing signature → 403, no scheduling.
# ---------------------------------------------------------------------------
def test_invalid_signature_rejected(client, seed, monkeypatch):
    boom = lambda *a, **k: pytest.fail("must not schedule on bad signature")
    monkeypatch.setattr(twilio_webhook, "_respond", boom)

    params = {"From": PEER, "To": OUR_NUMBER, "Body": "hey"}
    resp = client.post(
        "/sms",
        data=params,
        headers={"X-Twilio-Signature": "deadbeef-not-a-real-signature"},
    )
    assert resp.status_code == 403

    # Missing header entirely also 403s.
    resp2 = client.post("/sms", data=params)
    assert resp2.status_code == 403


# ---------------------------------------------------------------------------
# Crisis path: bypasses the engine, sends the hotline, logs a SafetyEvent.
# ---------------------------------------------------------------------------
class FakeTwilio:
    """Records every messages.create call (no network)."""

    def __init__(self):
        self.sent = []

        outer = self

        class _Messages:
            @staticmethod
            def create(to, from_, body):
                outer.sent.append({"to": to, "from_": from_, "body": body})
                return {"sid": f"SM{len(outer.sent):032d}"}

        self.messages = _Messages()


class RecordingSender:
    """Stand-in for the module sender; drives the injected fake twilio + sleeper."""

    def __init__(self, twilio):
        self._twilio = twilio
        self.calls = []

    def send_bubbles(self, to, from_, bubbles, twilio=None, sleeper=None):
        self.calls.append({"to": to, "from_": from_, "bubbles": list(bubbles)})
        # Exercise the real injection contract: no sleep, fake twilio.
        for b in bubbles:
            self._twilio.messages.create(to=to, from_=from_, body=b)


@pytest.mark.parametrize("crisis_body", ["我想自杀", "i want to kill myself"])
def test_crisis_bypasses_engine_sends_hotline_logs_event(
    client, seed, db_engine, monkeypatch, crisis_body
):
    # The engine must NOT be invoked on a crisis hit.
    def boom_reply(*a, **k):
        pytest.fail("engine.reply must not run on crisis")

    monkeypatch.setattr(twilio_webhook.engine, "reply", boom_reply)
    monkeypatch.setattr(
        twilio_webhook, "_respond", lambda *a, **k: pytest.fail("no background reply")
    )

    fake_twilio = FakeTwilio()
    rec_sender = RecordingSender(fake_twilio)
    monkeypatch.setattr(twilio_webhook, "sender", rec_sender)

    params = {"From": PEER, "To": OUR_NUMBER, "Body": crisis_body}
    url = "http://testserver/sms"
    resp = client.post(
        "/sms",
        data=params,
        headers={"X-Twilio-Signature": _sign(url, params)},
    )

    # Empty TwiML ack even on crisis.
    assert resp.status_code == 200
    assert resp.text == "<Response></Response>"

    # The static hotline message went out to the peer from our number.
    assert len(rec_sender.calls) == 1
    call = rec_sender.calls[0]
    assert call["to"] == PEER
    assert call["from_"] == OUR_NUMBER
    assert call["bubbles"] == [CRISIS_MESSAGE]
    # And it actually reached the (fake) Twilio REST layer.
    assert fake_twilio.sent[0]["body"] == CRISIS_MESSAGE
    assert "988" in fake_twilio.sent[0]["body"]

    # A SafetyEvent was logged against the conversation; no outbound persona msg.
    with Session(db_engine) as s:
        events = s.exec(select(SafetyEvent)).all()
        assert len(events) == 1
        assert events[0].kind == "crisis"
        assert events[0].body == CRISIS_MESSAGE
        conv = s.exec(select(Conversation)).first()
        assert conv is not None and events[0].conversation_id == conv.id
        # The engine never ran → no Message rows persisted.
        assert s.exec(select(Message)).all() == []


# ---------------------------------------------------------------------------
# handle_crisis is exercisable directly with an injected sender (unit-level).
# ---------------------------------------------------------------------------
def test_handle_crisis_direct(db_engine, seed, monkeypatch):
    monkeypatch.setattr(settings, "twilio_from_number", OUR_NUMBER)

    fake_twilio = FakeTwilio()
    rec_sender = RecordingSender(fake_twilio)

    with Session(db_engine) as s:
        conv = Conversation(persona_id=seed, peer_e164=PEER)
        s.add(conv)
        s.commit()
        s.refresh(conv)

        event = safety.handle_crisis(s, conv, rec_sender)
        assert event.id is not None
        assert event.kind == "crisis"

    assert rec_sender.calls[0]["to"] == PEER
    assert rec_sender.calls[0]["from_"] == OUR_NUMBER
