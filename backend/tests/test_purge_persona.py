"""Re-break-up: deleting a persona must wipe every related DB row AND the
encrypted upload files on disk (the data genuinely leaves the box)."""
from __future__ import annotations

import pytest
from sqlalchemy import func
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.persona import routes
from app.db import (
    Conversation, Correction, Job, MemoryChunk, Message, Number, Persona,
    SafetyEvent, StyleTuning, Upload, User, Version,
)


@pytest.fixture()
def session(tmp_path, monkeypatch):
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    # uploads live under a temp dir we can assert gets wiped
    monkeypatch.setattr(routes, "UPLOADS_ROOT", tmp_path)
    with Session(eng) as s:
        yield s


def _seed(s, tmp_path):
    user = User(email="a@b.c", pw_hash="x")
    s.add(user); s.commit(); s.refresh(user)
    p = Persona(user_id=user.id, slug="m", name="Sam", persona_md_enc="enc")
    s.add(p); s.commit(); s.refresh(p)

    s.add(Number(persona_id=p.id, e164="+18005550001"))
    conv = Conversation(persona_id=p.id, peer_e164="+18005550002")
    s.add(conv); s.commit(); s.refresh(conv)
    s.add(Message(conversation_id=conv.id, direction="in", body="hi"))
    s.add(SafetyEvent(conversation_id=conv.id, kind="crisis", body="x"))
    s.add(StyleTuning(persona_id=p.id, conversation_id=conv.id, overlay_json_enc="e", msg_count_at_run=1))
    s.add(Correction(persona_id=p.id, instruction="no emojis"))
    s.add(Version(persona_id=p.id, snapshot_json="{}"))
    s.add(MemoryChunk(persona_id=p.id, text="mem"))
    s.add(Job(persona_id=p.id))

    pdir = tmp_path / str(p.id)
    pdir.mkdir(parents=True)
    raw = pdir / "x.raw.enc"
    raw.write_bytes(b"secret chat bytes")
    s.add(Upload(
        persona_id=p.id, filename="x.txt", format="plaintext",
        raw_enc_path=str(raw), normalized_enc_path=str(pdir / "x.norm.enc"),
    ))
    s.commit()
    return p, pdir


def _count(s, model) -> int:
    return int(s.exec(select(func.count(model.id))).one())


def test_purge_removes_every_row_and_the_disk_files(session, tmp_path):
    p, pdir = _seed(session, tmp_path)
    assert pdir.exists() and (pdir / "x.raw.enc").exists()

    routes._purge_persona(session, p)

    for model in (Persona, Number, Conversation, Message, SafetyEvent, StyleTuning,
                  Correction, Version, MemoryChunk, Job, Upload):
        assert _count(session, model) == 0, f"{model.__name__} rows survived purge"

    # the encrypted chat files are gone from disk
    assert not pdir.exists()
