"""E3 conversation engine tests — fully mock-based (no Ollama, no keys).

A fake Ollama client returns a fixed bubble-delimited string; we assert the
engine splits it into bubbles and that the assembled system prompt carries the
persona name + the explicit language-mirroring rule. Mixed zh/en throughout.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings
from app.convo import engine
from app.convo.engine import build_system_prompt, split_bubbles
from app.db import Conversation, Message, Persona, User
from app.distill.schema import PersonaArtifacts
from app.persona import store


# --- fixtures --------------------------------------------------------------


@pytest.fixture()
def session(monkeypatch):
    # generated key — crypto reads settings.fernet_key at call time.
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


@pytest.fixture()
def persona_id(session):
    user = User(email="t@example.com", pw_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    persona = Persona(user_id=user.id, slug="xiao-mei", name="小美 / Mei")
    session.add(persona)
    session.commit()
    session.refresh(persona)
    # Save artifacts via the real E2 store so persona_json lands exactly where
    # the engine reads it (meta_json["persona_json"]).
    arts = PersonaArtifacts(
        persona_md="# 小美 / Mei\n## Layer 0\n超过2小时会发'你在干嘛?'",
        memories_md="## 关系概览\nmet in college 大学认识",
        meta={"name": "小美 / Mei", "slug": "xiao-mei"},
        persona_json={
            "name": "小美 / Mei",
            "slug": "xiao-mei",
            "layer0_core": {"behavioral_rules": ["超过2小时会发'你在干嘛?'"]},
            "layer1_identity": {"mbti": "ENFP"},
            "layer2_expression": {
                "catchphrases": ["在干嘛呀", "u up?"],
                "language_rule": "reply in the same language the user just used",
            },
            "layer5_boundaries": {"dealbreakers": ["lying", "被忽视"]},
        },
    )
    store.save_artifacts(persona.id, arts, session)
    return persona.id


# --- fake ollama -----------------------------------------------------------


class FakeOllama:
    """Records the messages it was called with; returns a canned reply."""

    def __init__(self, reply: str):
        self._reply = reply
        self.last_messages = None

    def chat(self, messages, *, num_ctx=8192, temperature=0.8):
        self.last_messages = messages
        return self._reply


# --- tests -----------------------------------------------------------------


def test_split_bubbles_on_delimiter():
    assert split_bubbles("hey\n---\nu up?") == ["hey", "u up?"]
    # whitespace-only fragments are dropped; a single bubble survives.
    assert split_bubbles("  在啊  ") == ["在啊"]
    assert split_bubbles("a\n---\n\n---\nb") == ["a", "b"]


def test_reply_splits_into_bubbles(session, persona_id):
    fake = FakeOllama("hey\n---\nu up?")
    out = engine.reply(session, persona_id, "+15555550100", "you around?", ollama=fake)
    assert out == ["hey", "u up?"]


def test_reply_system_prompt_has_name_and_language_rule(session, persona_id):
    fake = FakeOllama("ya\n---\n怎么了")
    engine.reply(session, persona_id, "+15555550100", "在吗", ollama=fake)

    # The fake captured the messages the engine assembled.
    msgs = fake.last_messages
    assert msgs[0]["role"] == "system"
    system = msgs[0]["content"]
    assert "小美 / Mei" in system  # persona name present
    assert "same language the user just used" in system  # language-mirror rule
    # the latest inbound turn is the final user message.
    assert msgs[-1] == {"role": "user", "content": "在吗"}


def test_build_system_prompt_includes_frozen_layers(session, persona_id):
    persona = session.get(Persona, persona_id)
    prompt = build_system_prompt(persona)
    # frozen core layer content surfaces (zh preserved), plus the SMS format rule.
    assert "超过2小时会发" in prompt
    assert "被忽视" in prompt
    assert "Separate each bubble" in prompt


def test_reply_uses_prior_history_and_overlay(session, persona_id):
    # seed a conversation with prior turns + a Layer-2 style overlay.
    conv = Conversation(persona_id=persona_id, peer_e164="+15555550100", summary="they broke up last fall")
    session.add(conv)
    session.commit()
    session.refresh(conv)
    session.add(Message(conversation_id=conv.id, direction="in", body="hey"))
    session.add(Message(conversation_id=conv.id, direction="out", body="hi"))
    session.commit()

    from app import crypto

    persona = session.get(Persona, persona_id)
    persona.style_overlay_enc = crypto.enc_str(
        '{"layer2_expression": {"catchphrases": ["lol", "哈哈哈"]}}'
    )
    session.add(persona)
    session.commit()

    fake = FakeOllama("lol\n---\n哈哈哈")
    out = engine.reply(session, persona_id, "+15555550100", "miss u", ollama=fake)
    assert out == ["lol", "哈哈哈"]

    msgs = fake.last_messages
    # the rolling summary was injected as a system message.
    assert any(
        m["role"] == "system" and "broke up last fall" in m["content"] for m in msgs
    )
    # prior turns are present in order before the latest inbound.
    bodies = [m["content"] for m in msgs]
    assert "hey" in bodies and "hi" in bodies
    assert bodies[-1] == "miss u"
    # the fresh overlay's catchphrases reached the system prompt.
    assert "哈哈哈" in msgs[0]["content"]
