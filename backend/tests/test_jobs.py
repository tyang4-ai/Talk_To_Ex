"""E12 — async job queue + worker (spec §28).

A persisted queue: enqueue → claim-once → mark; the worker dispatches by kind to an
injected handler and records ready/failed. No GPU, no network."""
from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import Job, Persona, User
from app.jobs import queue, worker


@pytest.fixture()
def session():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        user = User(email="j@example.com", pw_hash="x")
        s.add(user)
        s.commit()
        s.refresh(user)
        persona = Persona(user_id=user.id, slug="m", name="小美")
        s.add(persona)
        s.commit()
        s.refresh(persona)
        s.persona_id = persona.id  # type: ignore[attr-defined]
        yield s


def test_enqueue_and_claim_once(session):
    pid = session.persona_id  # type: ignore[attr-defined]
    job = queue.enqueue(session, pid)
    assert job.status == "queued" and job.kind == "finetune"

    claimed = queue.claim_next(session)
    assert claimed is not None and claimed.id == job.id
    assert claimed.status == "training"
    # second claim finds nothing (the only job is now training, not queued)
    assert queue.claim_next(session) is None


def test_mark_transitions(session):
    pid = session.persona_id  # type: ignore[attr-defined]
    job = queue.enqueue(session, pid)
    queue.mark(session, job, "ready", adapter_path="/p/persona-1.gguf")
    assert job.status == "ready"
    assert job.adapter_path == "/p/persona-1.gguf"
    # idempotent re-mark is fine
    queue.mark(session, job, "ready")
    assert job.status == "ready"


def test_worker_runs_handler_to_ready(session):
    pid = session.persona_id  # type: ignore[attr-defined]
    queue.enqueue(session, pid)

    seen = {}

    def fake_handler(sess, job: Job):
        seen["persona_id"] = job.persona_id
        return {"adapter_path": f"/adapters/persona-{job.persona_id}.gguf"}

    done = worker.run_once(session, dispatch={"finetune": fake_handler})
    assert done is not None
    assert done.status == "ready"
    assert done.adapter_path == f"/adapters/persona-{pid}.gguf"
    assert seen["persona_id"] == pid
    # queue now empty
    assert worker.run_once(session, dispatch={"finetune": fake_handler}) is None


def test_worker_records_failure(session):
    pid = session.persona_id  # type: ignore[attr-defined]
    queue.enqueue(session, pid)

    def boom(sess, job):
        raise RuntimeError("trainer exploded")

    done = worker.run_once(session, dispatch={"finetune": boom})
    assert done.status == "failed"
    assert "trainer exploded" in (done.error or "")


def test_worker_unknown_kind_fails_cleanly(session):
    pid = session.persona_id  # type: ignore[attr-defined]
    queue.enqueue(session, pid, kind="mystery")
    done = worker.run_once(session, dispatch={})
    assert done.status == "failed"
    assert "no handler" in (done.error or "")
