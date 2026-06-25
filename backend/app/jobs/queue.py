"""Persisted async job queue (spec §28).

A thin DB-backed queue so a long fine-tune (§23) runs out-of-process and never
blocks the web app. Single-worker assumption (one concurrent training job, §23.4):
``claim_next`` flips the oldest ``queued`` job to ``training`` and returns it, so a
second call returns ``None`` until that job leaves ``training``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from ..db import Job


def enqueue(session: Session, persona_id: int, kind: str = "finetune") -> Job:
    """Add a new ``queued`` job for a persona."""
    job = Job(persona_id=persona_id, kind=kind, status="queued")
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def claim_next(session: Session) -> Optional[Job]:
    """Claim the oldest ``queued`` job (flip to ``training``) or return ``None``."""
    stmt = (
        select(Job)
        .where(Job.status == "queued")
        .order_by(Job.created_at, Job.id)
        .limit(1)
    )
    job = session.exec(stmt).first()
    if job is None:
        return None
    job.status = "training"
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def mark(session: Session, job: Job, status: str, **fields) -> Job:
    """Set a job's status (+ optional ``adapter_path``/``error``) and timestamp."""
    job.status = status
    for key, value in fields.items():
        setattr(job, key, value)
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get(session: Session, job_id: int) -> Optional[Job]:
    return session.get(Job, job_id)
