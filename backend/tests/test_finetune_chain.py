"""Distill → fine-tune CHAIN orchestration (no GPU).

The async build distills + reveals immediately (the ex texts first on the prompt-
only voice), then queues a background QLoRA that hot-upgrades the voice. These lock
the orchestration contracts before any 4090 time: direction convention, the chain
enqueue, non-fatal fine-tune degrade, no double-opener, revealed-wins state, and
the out-of-process worker registering both job kinds.
"""
from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.config import settings
from app.db import Job, Number, Persona, User
from app.finetune import dataprep
from app.jobs import queue, run_worker, worker
from app.messaging import reveal
from app.persona import routes

OUR = "+18445550000"
FRIEND = "+15555550100"


class RecordingSender:
    calls: list = []

    def send_bubbles(self, to, from_, bubbles, twilio=None, sleeper=None):
        RecordingSender.calls.append({"to": to, "from_": from_, "bubbles": list(bubbles)})


@pytest.fixture()
def eng(monkeypatch):
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "kill_switch", False)
    monkeypatch.setattr(settings, "finetune_enabled", True)
    e = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(e)
    monkeypatch.setattr(routes, "engine", e)
    monkeypatch.setattr(reveal, "Sender", RecordingSender)
    RecordingSender.calls = []
    return e


def _seed(e, *, status="building") -> int:
    with Session(e) as s:
        u = User(email="f@e.com", pw_hash="x", phone_e164=FRIEND)
        s.add(u)
        s.commit()
        s.refresh(u)
        p = Persona(
            user_id=u.id, slug="m", name="小美", status=status,
            meta_json=json.dumps({"peer_e164": FRIEND}),
        )
        s.add(p)
        s.commit()
        s.refresh(p)
        s.add(Number(persona_id=p.id, e164=OUR, mode="trial"))
        s.commit()
        return p.id


def _fake_build_ready(session, job):
    p = session.get(Persona, job.persona_id)
    p.persona_md_enc = "built"
    session.add(p)
    session.commit()
    return {}


# --- Phase 0: direction convention ----------------------------------------
def test_dataprep_trains_on_the_ex_as_assistant():
    transcript = [
        {"text": "you up?", "direction": "out"},   # friend  -> user
        {"text": "yeah, miss you", "direction": "in"},  # the EX -> assistant
    ]
    ex = dataprep.build_examples(transcript)
    assert len(ex) == 1
    msgs = ex[0].messages
    assert msgs[0]["role"] == "user"
    assert msgs[-1]["role"] == "assistant" and msgs[-1]["content"] == "yeah, miss you"


# --- _build_state: revealed wins over a background finetune ----------------
def test_revealed_wins_over_queued_finetune():
    active = Persona(user_id=1, slug="m", name="m", status="active", persona_md_enc="x")
    ft = Job(persona_id=1, kind="finetune", status="queued")
    assert routes._build_state(active, ft) == "revealed"


# --- Phase 1: the chain enqueues a finetune after the reveal --------------
def test_build_and_reveal_chains_a_finetune(eng):
    worker.register("build", _fake_build_ready)
    pid = _seed(eng)
    with Session(eng) as s:
        jid = queue.enqueue(s, pid, kind="build").id

    routes._build_and_reveal(pid, jid)

    with Session(eng) as s:
        p = s.get(Persona, pid)
        assert p.status == "active"                                  # revealed after distill
        ft = s.exec(
            select(Job).where(Job.persona_id == pid, Job.kind == "finetune")
        ).all()
        assert len(ft) == 1 and ft[0].status == "queued"            # chained, awaiting worker
    assert len(RecordingSender.calls) == 1                          # opener sent exactly once


# --- finetune failure is NON-FATAL (clean degrade) ------------------------
def test_finetune_failure_keeps_persona_live(eng):
    pid = _seed(eng, status="active")
    with Session(eng) as s:
        queue.enqueue(s, pid, kind="finetune")

        def host_only(sess, j):
            raise RuntimeError("host-only — see ops/finetune/setup.md")

        done = worker.run_once(s, dispatch={"finetune": host_only})
        assert done.status == "failed" and "host-only" in (done.error or "")
        p = s.get(Persona, pid)
        assert p.status == "active"                                 # persona unaffected
        assert routes._build_state(p, done) == "revealed"          # UI stays revealed


# --- no double opener: on_finetune_ready is neutered ----------------------
def test_on_finetune_ready_sends_no_second_opener(eng):
    pid = _seed(eng, status="active")
    with Session(eng) as s:
        job = queue.mark(s, queue.enqueue(s, pid, kind="finetune"), "ready")
        assert reveal.on_finetune_ready(s, job, sender=RecordingSender()) is False
    assert RecordingSender.calls == []


# --- Phase 2: the worker registers both job kinds -------------------------
def test_worker_registers_build_and_finetune(monkeypatch):
    monkeypatch.setattr(settings, "finetune_enabled", True)
    run_worker._register_handlers()
    assert "build" in worker.DISPATCH and "finetune" in worker.DISPATCH
