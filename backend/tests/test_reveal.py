"""E14 — reveal + proactive opener + outbound safety (spec §24).

go_live activates a persona and sends the templated opener (gated by kill-switch
+ outbound screen); the outbound tripwire blocks crisis-laden generated content
and logs a direction="out" SafetyEvent; the reply path drops an unsafe model
reply. Mock-based (no Twilio/Ollama)."""
from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.config import settings
from app.db import Conversation, Message, Number, Persona, SafetyEvent, User
from app.messaging import opener, reveal, safety, twilio_webhook

OUR = "+18445550000"
FRIEND = "+15555550100"


class RecordingSender:
    def __init__(self):
        self.calls = []

    def send_bubbles(self, to, from_, bubbles, twilio=None, sleeper=None):
        self.calls.append({"to": to, "from_": from_, "bubbles": list(bubbles)})


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "kill_switch", False)
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _seed(db, *, with_peer=True, status="building"):
    with Session(db) as s:
        user = User(email="f@example.com", pw_hash="x")
        s.add(user)
        s.commit()
        s.refresh(user)
        meta = {"peer_e164": FRIEND} if with_peer else {}
        p = Persona(
            user_id=user.id, slug="m", name="小美",
            meta_json=json.dumps(meta), status=status,
        )
        s.add(p)
        s.commit()
        s.refresh(p)
        s.add(Number(persona_id=p.id, e164=OUR, mode="trial"))
        s.commit()
        return p.id


# --- opener ----------------------------------------------------------------
def test_opener_is_templated_and_deterministic(db):
    pid = _seed(db)
    with Session(db) as s:
        p = s.get(Persona, pid)
        a = opener.first_message(p)
        b = opener.first_message(p)
        assert a and a == b               # deterministic per persona
        assert "sorry" in a.lower()       # it's an apology


# --- go_live ---------------------------------------------------------------
def test_go_live_activates_and_sends_opener(db):
    pid = _seed(db)
    rec = RecordingSender()
    with Session(db) as s:
        ok = reveal.go_live(s, pid, sender=rec)
    assert ok is True
    assert rec.calls[0]["to"] == FRIEND and rec.calls[0]["from_"] == OUR
    assert "sorry" in rec.calls[0]["bubbles"][0].lower()
    with Session(db) as s:
        p = s.get(Persona, pid)
        assert p.status == "active"
        assert json.loads(p.meta_json).get("opt_in_at")        # consent recorded
        # opener persisted as an outbound turn
        msgs = s.exec(select(Message)).all()
        assert len(msgs) == 1 and msgs[0].direction == "out"


def test_go_live_silenced_by_kill_switch(db, monkeypatch):
    pid = _seed(db)
    monkeypatch.setattr(settings, "kill_switch", True)
    rec = RecordingSender()
    with Session(db) as s:
        assert reveal.go_live(s, pid, sender=rec) is False
    assert rec.calls == []


def test_go_live_noops_without_peer(db):
    pid = _seed(db, with_peer=False)
    rec = RecordingSender()
    with Session(db) as s:
        assert reveal.go_live(s, pid, sender=rec) is False
    assert rec.calls == []


# --- outbound safety screen ------------------------------------------------
def test_screen_outbound():
    assert safety.screen_outbound("hey, missed you 在吗") is True
    assert safety.screen_outbound("i want to kill myself") is False


def test_go_live_blocks_unsafe_opener_logs_outbound(db, monkeypatch):
    pid = _seed(db)
    # Force the opener to be crisis content to exercise the outbound block.
    monkeypatch.setattr(opener, "first_message", lambda persona: "i want to kill myself")
    rec = RecordingSender()
    with Session(db) as s:
        assert reveal.go_live(s, pid, sender=rec) is False
    assert rec.calls == []
    with Session(db) as s:
        ev = s.exec(select(SafetyEvent)).all()
        assert len(ev) == 1
        assert ev[0].kind == "blocked_outbound" and ev[0].direction == "out"


def test_respond_drops_unsafe_generated_reply(db, monkeypatch):
    pid = _seed(db, status="active")
    monkeypatch.setattr(twilio_webhook, "db_engine", db)
    monkeypatch.setattr(settings, "twilio_from_number", OUR)
    rec = RecordingSender()
    monkeypatch.setattr(twilio_webhook, "sender", rec)
    # the model "generates" crisis content -> must be blocked, not sent
    monkeypatch.setattr(twilio_webhook.engine, "reply", lambda *a, **k: ["i want to die"])

    twilio_webhook._respond(pid, FRIEND, OUR, "hey")

    assert rec.calls == []  # nothing sent
    with Session(db) as s:
        ev = s.exec(select(SafetyEvent)).all()
        assert len(ev) == 1 and ev[0].direction == "out"
