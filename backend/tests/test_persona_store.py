"""E2 persona store tests — encrypted round-trip + version cap (mock-based).

Uses a throwaway in-memory SQLite engine and a generated Fernet key (no real
secrets). A fake anthropic client exercises apply_correction.
"""
import json

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from app import crypto
from app.config import settings
from app.db import Persona, User, Version
from app.distill.schema import PersonaArtifacts
from app.persona import store


@pytest.fixture()
def session(monkeypatch):
    # generated key — crypto reads settings.fernet_key at call time.
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def persona_id(session):
    user = User(email="t@example.com", pw_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    persona = Persona(user_id=user.id, slug="xiao-mei", name="小美")
    session.add(persona)
    session.commit()
    session.refresh(persona)
    return persona.id


def _arts(version=1):
    return PersonaArtifacts(
        persona_md="# 小美\n## Layer 0\n超过2小时会发'你在干嘛?'",
        memories_md="## 关系概览\nmet in college 大学认识",
        meta={"name": "小美", "slug": "xiao-mei", "version": version},
        persona_json={
            "name": "小美",
            "slug": "xiao-mei",
            "layer0_core": {"behavioral_rules": ["超过2小时会发'你在干嘛?'"]},
            "layer2_expression": {"catchphrases": ["在干嘛呀"]},
        },
    )


def test_save_load_round_trips_encrypted(session, persona_id):
    store.save_artifacts(persona_id, _arts(), session)

    # on-disk columns are Fernet tokens, NOT plaintext.
    persona = session.get(Persona, persona_id)
    assert persona.persona_md_enc and "小美" not in persona.persona_md_enc
    assert persona.memories_md_enc and "关系概览" not in persona.memories_md_enc
    # decrypting the stored token recovers the original mixed zh/en text.
    assert crypto.dec_str(persona.persona_md_enc).startswith("# 小美")

    loaded = store.load(persona_id, session)
    assert loaded.persona_md.startswith("# 小美")
    assert "关系概览" in loaded.memories_md
    assert loaded.meta["slug"] == "xiao-mei"
    # persona_json round-trips (nested under meta_json on disk, split back out).
    parsed = loaded.parsed_persona()
    assert parsed.layer0_core.behavioral_rules == ["超过2小时会发'你在干嘛?'"]
    assert "persona_json" not in loaded.meta  # not leaked into meta


def test_versions_caps_at_10(session, persona_id):
    for i in range(1, 16):  # 15 saves
        store.save_artifacts(persona_id, _arts(version=i), session)

    rows = store.versions(persona_id, session)
    assert len(rows) == store.MAX_VERSIONS == 10

    # the retained snapshots are the most recent ones (versions 6..15).
    kept_versions = sorted(
        json.loads(r.snapshot_json)["meta"]["version"] for r in rows
    )
    assert kept_versions == list(range(6, 16))

    # DB truly pruned, not just the query.
    total = session.query(Version).filter(Version.persona_id == persona_id).count()
    assert total == 10


# --- apply_correction with a fake anthropic client -------------------------


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


class FakeAnthropic:
    def __init__(self, text):
        self.messages = _Messages(text)


def test_apply_correction_updates_and_records(session, persona_id):
    store.save_artifacts(persona_id, _arts(), session)

    corrected_envelope = {
        "persona_md": "# 小美\n## Layer 0\n## 修正记录\n[场景：约饭] 应该用暗示",
        "memories_md": "## 关系概览\nmet in college 大学认识",
        "persona_json": {
            "name": "小美",
            "slug": "xiao-mei",
            "layer2_expression": {"catchphrases": ["你说我们好久没吃火锅了哦～"]},
            "corrections": ["[场景：约饭] 不应该直接说'我想吃火锅'，应该暗示"],
        },
        "meta": {"name": "小美", "slug": "xiao-mei", "version": 1},
    }
    client = FakeAnthropic(json.dumps(corrected_envelope, ensure_ascii=False))

    updated = store.apply_correction(
        persona_id, "她不会直接说我想吃火锅，应该暗示", session, client=client
    )

    assert "修正记录" in updated.persona_md
    assert updated.meta["corrections_count"] == 1
    assert updated.parsed_persona().corrections

    # a Correction row was recorded and the change persisted.
    from app.db import Correction

    corr = (
        session.query(Correction)
        .filter(Correction.persona_id == persona_id)
        .all()
    )
    assert len(corr) == 1
    assert "火锅" in corr[0].instruction

    reloaded = store.load(persona_id, session)
    assert "修正记录" in reloaded.persona_md


# --- Layer-2 style overlay persistence (E3 hook) ---------------------------


def test_style_overlay_round_trips_and_records_tuning(session, persona_id):
    from app.db import Persona, StyleTuning

    assert store.load_style_overlay(persona_id, session) is None

    overlay = {
        "catchphrases": ["在干嘛呀", "lol"],
        "emoji_usage": "🥺 more lately",
        "language_rule": "reply in the same language the user just used",
    }
    tuning = store.save_style_overlay(persona_id, overlay, 100, session)

    # encrypted at rest, not plaintext.
    persona = session.get(Persona, persona_id)
    assert persona.style_overlay_enc and "在干嘛呀" not in persona.style_overlay_enc

    loaded = store.load_style_overlay(persona_id, session)
    assert loaded == overlay

    # a StyleTuning history row was recorded with the run's message count.
    assert tuning.msg_count_at_run == 100
    rows = (
        session.query(StyleTuning)
        .filter(StyleTuning.persona_id == persona_id)
        .all()
    )
    assert len(rows) == 1
