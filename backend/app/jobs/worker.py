"""Job worker (spec §28, §23).

``run_once`` claims one queued job and dispatches it by ``kind`` to a registered
handler, marking the job ``ready`` (with any returned fields, e.g. ``adapter_path``)
on success or ``failed`` (with the error) on exception. The handler is looked up
in a dispatch table so callers/tests can inject a fake — no GPU or network is
touched here. A thin out-of-process loop (or cron poll) calls ``run_once`` so a
2-day fine-tune never blocks the web app.

Handlers have signature ``handler(session, job) -> dict | None`` where the dict is
merged into the job on success (e.g. ``{"adapter_path": "..."}``).
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from sqlmodel import Session

from ..db import Job
from . import queue

Handler = Callable[[Session, Job], Optional[dict]]

# kind -> handler. E13 registers the "finetune" handler here at wiring time.
DISPATCH: Dict[str, Handler] = {}


def register(kind: str, handler: Handler) -> None:
    """Register a handler for a job kind (idempotent overwrite)."""
    DISPATCH[kind] = handler


def run_once(session: Session, dispatch: Optional[Dict[str, Handler]] = None) -> Optional[Job]:
    """Process one queued job, if any. Returns the job (now ready/failed) or None."""
    table = DISPATCH if dispatch is None else dispatch
    job = queue.claim_next(session)
    if job is None:
        return None

    handler = table.get(job.kind)
    if handler is None:
        return queue.mark(session, job, "failed", error=f"no handler for kind {job.kind!r}")

    try:
        result = handler(session, job) or {}
    except Exception as exc:  # noqa: BLE001 — record the failure, never crash the loop
        return queue.mark(session, job, "failed", error=str(exc))
    return queue.mark(session, job, "ready", **result)
