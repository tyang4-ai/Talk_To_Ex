"""E3 style-tuner tests — the core-freeze guardrail (mock-based, no keys).

A fake Claude client returns a full persona JSON. The tuner must REJECT (and
persist nothing) when a frozen core layer (0/1/3/4/5) changed, and ACCEPT —
saving only the Layer-2 overlay + a StyleTuning row — when only Layer 2 changed.
Mixed zh/en throughout.
"""
from __future__ import annotations

import copy
import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import crypto
from app.config import settings
from app.convo import style_tuner
from app.convo.style_tuner import CoreLayerMutated, validate_core_unchanged
from app.db import Conversation, Persona, StyleTuning, User
from app.distill.schema import PersonaArtifacts
from app.persona import store


# --- the frozen original persona_json --------------------------------------

ORIGINAL = {
    "name": "小美 / Mei",
    "slug": "xiao-mei",
    "layer0_core": {
        "summary": "anxious-attachment, warm but tests you",
        "behavioral_rules": ["超过2小时没回会发'你在干嘛?'"],
        "tags": ["焦虑型"],
    },
    "layer1_identity": {"mbti": "ENFP", "occupation": "designer"},
    "layer2_expression": {
        "catchphrases": ["在干嘛呀"],
        "language_rule": "reply in the same language the user just used",
    },
    "layer3_emotional_logic": {"priorities": ["being remembered"]},
    "layer4_relationship_behavior": {"under_stress": "withdraws then explodes"},
    "layer5_boundaries": {"dealbreakers": ["lying", "被忽视"]},
    "corrections": [],
}


# --- fixtures --------------------------------------------------------------


@pytest.fixture()
def session(monkeypatch):
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "style_retune_every", 100)
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


@pytest.fixture()
def conv(session):
    user = User(email="t@example.com", pw_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    persona = Persona(user_id=user.id, slug="xiao-mei", name="小美 / Mei")
    session.add(persona)
    session.commit()
    session.refresh(persona)
    store.save_artifacts(
        persona.id,
        PersonaArtifacts(
            persona_md="# 小美",
            memories_md="## 关系概览",
            meta={"name": "小美 / Mei", "slug": "xiao-mei"},
            persona_json=copy.deepcopy(ORIGINAL),
        ),
        session,
    )
    # message_count at a retune boundary (100 % 100 == 0).
    c = Conversation(
        persona_id=persona.id, peer_e164="+15555550100", message_count=100
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


# --- fake claude -----------------------------------------------------------


class _Block:
    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text):
        self.content = [_Block(text)]


class _Messages:
    def __init__(self, text):
        self._text = text

    def create(self, **kwargs):
        return _Response(self._text)


class FakeClaude:
    def __init__(self, persona_json: dict):
        self.messages = _Messages(json.dumps(persona_json, ensure_ascii=False))


# --- unit tests on the validator -------------------------------------------


def test_validate_accepts_layer2_only_change():
    overlay = copy.deepcopy(ORIGINAL)
    overlay["layer2_expression"]["catchphrases"] = ["哈哈哈", "lol"]
    # must not raise
    validate_core_unchanged(ORIGINAL, overlay)


def test_validate_rejects_core_layer0_change():
    overlay = copy.deepcopy(ORIGINAL)
    overlay["layer0_core"]["behavioral_rules"] = ["totally rewritten core"]
    with pytest.raises(CoreLayerMutated) as ei:
        validate_core_unchanged(ORIGINAL, overlay)
    assert 0 in ei.value.changed


def test_validate_rejects_boundary_change():
    overlay = copy.deepcopy(ORIGINAL)
    overlay["layer5_boundaries"]["dealbreakers"] = ["nothing matters now"]
    with pytest.raises(CoreLayerMutated) as ei:
        validate_core_unchanged(ORIGINAL, overlay)
    assert 5 in ei.value.changed


# --- end-to-end maybe_retune -----------------------------------------------


def test_maybe_retune_rejects_tampered_core(session, conv):
    tampered = copy.deepcopy(ORIGINAL)
    tampered["layer0_core"]["summary"] = "now a cold avoidant — core rewritten"
    client = FakeClaude(tampered)

    with pytest.raises(CoreLayerMutated):
        style_tuner.maybe_retune(session, conv, client=client)

    # NOTHING persisted: no overlay, no StyleTuning row.
    persona = session.get(Persona, conv.persona_id)
    assert persona.style_overlay_enc is None
    assert (
        session.query(StyleTuning)
        .filter(StyleTuning.persona_id == conv.persona_id)
        .count()
        == 0
    )


def test_maybe_retune_accepts_layer2_overlay(session, conv):
    valid = copy.deepcopy(ORIGINAL)
    valid["layer2_expression"]["catchphrases"] = ["哈哈哈", "lol", "u up"]
    valid["layer2_expression"]["emoji_usage"] = "🥺 a lot now"
    client = FakeClaude(valid)

    tuning = style_tuner.maybe_retune(session, conv, client=client)

    assert tuning is not None
    assert tuning.msg_count_at_run == 100
    assert tuning.conversation_id == conv.id

    # overlay persisted on the persona, encrypted, and contains ONLY layer 2.
    persona = session.get(Persona, conv.persona_id)
    assert persona.style_overlay_enc
    stored = json.loads(crypto.dec_str(persona.style_overlay_enc))
    assert set(stored.keys()) == {"layer2_expression"}
    assert "哈哈哈" in stored["layer2_expression"]["catchphrases"]

    # a StyleTuning history row was written.
    rows = (
        session.query(StyleTuning)
        .filter(StyleTuning.persona_id == conv.persona_id)
        .all()
    )
    assert len(rows) == 1


def test_maybe_retune_noop_off_boundary(session, conv):
    conv.message_count = 137  # 137 % 100 != 0
    session.add(conv)
    session.commit()
    session.refresh(conv)

    # client would raise if called; off-boundary must not call it.
    class Boom:
        @property
        def messages(self):
            raise AssertionError("Claude must not be called off-boundary")

    assert style_tuner.maybe_retune(session, conv, client=Boom()) is None
