"""Out-of-process job worker loop (spec §23.4 / §28).

The web process never runs long jobs — the async distill is a per-request
BackgroundTask, and a multi-hour QLoRA fine-tune must NOT be tied to uvicorn. This
is the single background worker that drains the persisted queue: claim the oldest
queued job, run it, repeat. ``queue.claim_next`` enforces one training job at a
time (the box has one GPU), so a second concurrent worker is a no-op by design.

Run it on the box with the GPU trainer (the 4090):

    cd backend && python -m app.jobs.run_worker

Fine-tune failure is non-fatal here: a job with no real runner wired raises the
"host-only" message, the job is marked ``failed``, and the persona keeps texting on
its prompt-only distilled voice. The loop logs and continues — it never crashes.
"""
from __future__ import annotations

import logging
import time

from sqlmodel import Session

from ..config import settings
from ..db import engine, init_db
from . import worker

log = logging.getLogger("talk_to_ex.worker")


def _register_handlers() -> None:
    """Populate worker.DISPATCH with every job kind this worker can run."""
    from ..persona.build import register_build_handler

    register_build_handler()  # "build" = distillation (no GPU)
    if settings.finetune_enabled:
        try:
            from ..finetune.pipeline import register_handler

            register_handler()  # "finetune" = QLoRA (host-only runners)
        except Exception as exc:  # noqa: BLE001 — never block the loop on this
            log.warning("finetune handler not registered: %s", exc)


def run_forever(poll_seconds: float = 5.0) -> None:
    """Drain the queue forever, sleeping when idle. Ctrl-C exits cleanly."""
    init_db()
    _register_handlers()
    log.info("worker loop started (poll=%.1fs, kinds=%s)", poll_seconds, list(worker.DISPATCH))
    try:
        while True:
            with Session(engine) as session:
                job = worker.run_once(session)
                if job is not None:
                    log.info("job %s kind=%s -> %s%s", job.id, job.kind, job.status,
                             f" ({job.error})" if job.error else "")
            if job is None:
                time.sleep(poll_seconds)
    except KeyboardInterrupt:
        log.info("worker loop stopped")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_forever()


if __name__ == "__main__":
    main()
