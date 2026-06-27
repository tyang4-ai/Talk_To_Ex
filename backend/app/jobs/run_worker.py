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
from pathlib import Path

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
            if settings.finetune_backend == "wave":
                from ..finetune.wave_runner import wave_handler

                worker.register("finetune", wave_handler)  # SLURM QLoRA on WAVE → atlas
                log.info("finetune backend: WAVE")
            else:
                from ..finetune.pipeline import register_handler

                register_handler()  # host-only default (degrades cleanly)
                log.info("finetune backend: %s (host-only)", settings.finetune_backend)
        except Exception as exc:  # noqa: BLE001 — never block the loop on this
            log.warning("finetune handler not registered: %s", exc)


def _ssh_selfcheck() -> None:
    """Log whether the worker can SSH to WAVE + atlas from its current context.
    Critical when run as a SYSTEM service (vs the logged-in user) — confirms the
    SSH keys resolve. Non-fatal; just diagnostics in the log."""
    import subprocess

    for alias in (settings.wave_ssh_alias, settings.atlas_ssh_alias):
        try:
            r = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", alias, "echo ok"],
                capture_output=True, text=True, timeout=20,
            )
            if r.returncode == 0 and "ok" in r.stdout:
                log.info("ssh %s: OK", alias)
            else:
                log.warning("ssh %s: FAIL rc=%s %s", alias, r.returncode, (r.stderr or "").strip()[:160])
        except Exception as exc:  # noqa: BLE001
            log.warning("ssh %s: error %s", alias, exc)


def run_forever(poll_seconds: float = 5.0) -> None:
    """Drain the queue forever, sleeping when idle. Ctrl-C exits cleanly."""
    init_db()
    _register_handlers()
    _ssh_selfcheck()
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
    # Log to a file (not just stdout) so the worker can run windowless (pythonw)
    # with nothing for the user to accidentally close.
    log_dir = Path(__file__).resolve().parents[3] / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "worker.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    run_forever()


if __name__ == "__main__":
    main()
