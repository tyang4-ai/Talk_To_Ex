"""Async build + the reveal (set up & forget → the ex texts you first).

Covers the new seam: worker.run_job dispatches a held job; the /build route
enqueues + (via its BackgroundTask) builds then has the persona text the friend
first; /status reports the state machine. Claude (build) and Twilio (send) are
mocked — the distillation itself is covered by the distill tests, go_live by
test_reveal.
"""
from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet
from fastapi import BackgroundTasks
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.config import settings
from app.db import Job, Number, Persona, Upload, User
from app.jobs import queue, worker
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
    e = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(e)
    monkeypatch.setattr(routes, "engine", e)          # _build_and_reveal opens this
    monkeypatch.setattr(reveal, "Sender", RecordingSender)
    RecordingSender.calls = []
    return e


def _seed(e, *, phone=FRIEND, with_number=True) -> tuple[int, int]:
    with Session(e) as s:
        user = User(email="f@example.com", pw_hash="x", phone_e164=phone)
        s.add(user)
        s.commit()
        s.refresh(user)
        p = Persona(user_id=user.id, slug="m", name="小美", status="draft")
        s.add(p)
        s.commit()
        s.refresh(p)
        s.add(Upload(
            persona_id=p.id, filename="c.txt", format="plaintext",
            raw_enc_path="r", normalized_enc_path="n", message_count=3,
        ))
        if with_number:
            s.add(Number(persona_id=p.id, e164=OUR, mode="trial"))
        s.commit()
        return user.id, p.id


def _fake_build_handler(session, job):
    """Stand in for the Claude distillation: mark the persona built."""
    p = session.get(Persona, job.persona_id)
    p.persona_md_enc = "built"
    session.add(p)
    session.commit()
    return {}


# --- worker.run_job --------------------------------------------------------
def test_run_job_dispatches_held_job(eng):
    _user, pid = _seed(eng)
    with Session(eng) as s:
        job = queue.enqueue(s, pid, kind="build")
        done = worker.run_job(s, job, dispatch={"build": _fake_build_handler})
        assert done.status == "ready"
        assert s.get(Persona, pid).persona_md_enc == "built"


def test_run_job_records_failure(eng):
    _user, pid = _seed(eng)
    with Session(eng) as s:
        job = queue.enqueue(s, pid, kind="build")

        def boom(sess, j):
            raise RuntimeError("distill exploded")

        done = worker.run_job(s, job, dispatch={"build": boom})
        assert done.status == "failed" and "exploded" in (done.error or "")


# --- state mapping ---------------------------------------------------------
def test_build_state_mapping(eng):
    draft = Persona(user_id=1, slug="x", name="x", status="draft")
    assert routes._build_state(draft, None) == "draft"
    job = Job(persona_id=1, kind="build", status="training")
    assert routes._build_state(draft, job) == "contemplating"
    job.status = "failed"
    assert routes._build_state(draft, job) == "failed"
    built = Persona(user_id=1, slug="x", name="x", status="draft", persona_md_enc="x")
    job.status = "ready"
    assert routes._build_state(built, job) == "ready"
    active = Persona(user_id=1, slug="x", name="x", status="active", persona_md_enc="x")
    assert routes._build_state(active, job) == "revealed"


# --- full /build -> background -> reveal -> /status ------------------------
def test_build_enqueues_then_ex_texts_first(eng):
    worker.register("build", _fake_build_handler)
    uid, pid = _seed(eng)
    with Session(eng) as s:
        user = s.get(User, uid)

        bg = BackgroundTasks()
        out = routes.build_persona(pid, bg, user=user, session=s)
        assert out.state == "contemplating"
        assert s.get(Persona, pid).status == "building"
        # peer captured from the signup phone
        assert json.loads(s.get(Persona, pid).meta_json)["peer_e164"] == FRIEND

    # drain the BackgroundTask (FastAPI would run this after the response)
    for task in bg.tasks:
        task.func(*task.args, **task.kwargs)

    # the ex texted the friend first
    assert len(RecordingSender.calls) == 1
    assert RecordingSender.calls[0]["to"] == FRIEND
    assert RecordingSender.calls[0]["from_"] == OUR
    assert "sorry" in RecordingSender.calls[0]["bubbles"][0].lower()

    with Session(eng) as s:
        user = s.get(User, uid)
        status_out = routes.persona_status(pid, user=user, session=s)
        assert status_out.state == "revealed"
        assert status_out.revealed is True


def test_build_idempotent_while_in_flight(eng):
    worker.register("build", _fake_build_handler)
    uid, pid = _seed(eng)
    with Session(eng) as s:
        user = s.get(User, uid)
        # a build already queued
        queue.enqueue(s, pid, kind="build")
        bg = BackgroundTasks()
        routes.build_persona(pid, bg, user=user, session=s)
        # no second job, no background task scheduled
        jobs = s.exec(select(Job).where(Job.persona_id == pid)).all()
        assert len(jobs) == 1
        assert bg.tasks == []
