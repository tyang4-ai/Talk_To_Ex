"""Orchestrate a per-persona QLoRA on SCU WAVE HPC, served on atlas (no torch).

End-to-end, driven from the user's box by the out-of-process worker:
  export chat examples -> ship to WAVE -> submit a SLURM QLoRA job -> poll ->
  fetch the GGUF adapter -> ship to atlas -> `ollama create` -> pin
  meta["adapter_model"] so the live engine hot-swaps to the fine-tuned voice.

Pure orchestration over ssh/scp using the user's ~/.ssh/config aliases (`wave`,
`atlas`). MUST run in a process owned by the user (NOT the LocalSystem web
service) so the SSH keys resolve. WAVE needs the SCU VPN up; atlas is on Tailscale.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from datetime import datetime

from sqlmodel import Session

from ..config import settings
from ..db import Job, Persona
from . import wave_export
from .serve import _SYSTEM_STUB, persona_model_name

log = logging.getLogger("talk_to_ex.finetune.wave")


def _run(cmd: list[str], *, timeout: int | None = None, check: bool = True) -> str:
    """Run a local command (ssh/scp). Returns stdout; raises on failure."""
    log.info("exec: %s", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(
            f"command failed ({r.returncode}): {' '.join(cmd)}\n{(r.stderr or '')[-2000:]}"
        )
    return r.stdout


def _remote_home(alias: str) -> str:
    return _run(["ssh", alias, "echo $HOME"]).strip()


def wave_finetune(
    session: Session,
    persona_id: int,
    *,
    poll_seconds: int = 30,
    max_wait_seconds: int = 6 * 3600,
) -> dict:
    """Run the full WAVE→atlas fine-tune for a persona. Returns
    ``{"adapter_model", "adapter_path"}`` and pins them on the persona."""
    persona = session.get(Persona, persona_id)
    if persona is None:
        raise ValueError(f"persona {persona_id} not found")
    meta = json.loads(persona.meta_json or "{}")
    base = meta.get("llm_model") or settings.ollama_model

    wave = settings.wave_ssh_alias
    atlas = settings.atlas_ssh_alias
    tlx = settings.wave_tlx_dir.rstrip("/")
    run_dir = f"{tlx}/runs/{persona_id}"
    gguf_remote = f"{run_dir}/persona-{persona_id}.gguf"

    # 1. export the persona's chat examples locally.
    tmp = tempfile.mkdtemp(prefix=f"tlx_ft_{persona_id}_")
    local_jsonl = os.path.join(tmp, "examples.jsonl")
    n = wave_export.export_examples_jsonl(session, persona_id, local_jsonl)
    log.info("persona %s: %d training examples", persona_id, n)

    # 2. ship to WAVE.
    _run(["ssh", wave, f"mkdir -p {run_dir}"])
    _run(["scp", local_jsonl, f"{wave}:{run_dir}/examples.jsonl"])

    # 3. submit the SLURM job.
    export = (
        f"ALL,TLX_PID={persona_id},TLX_BASE={base},TLX_EPOCHS={settings.finetune_epochs}"
    )
    tok = (settings.train_hf_token or "").strip()
    if tok:
        export += f",TLX_HF_TOKEN={tok}"
    out = _run(["ssh", wave, f"cd {tlx} && sbatch --export={export} scripts/train.sbatch"])
    job_id = out.strip().split()[-1]
    log.info("persona %s: submitted WAVE job %s (base=%s)", persona_id, job_id, base)

    # 4. poll until the job leaves the queue.
    waited = 0
    while waited < max_wait_seconds:
        state = _run(["ssh", wave, f"squeue -j {job_id} -h -o %T"], check=False).strip()
        if not state:
            break
        time.sleep(poll_seconds)
        waited += poll_seconds
    else:
        raise RuntimeError(f"WAVE job {job_id} exceeded {max_wait_seconds}s")

    # verify the artifact; surface the job log tail on failure.
    chk = _run(["ssh", wave, f"test -f {gguf_remote} && echo OK || echo MISSING"], check=False)
    if "OK" not in chk:
        tail = _run(["ssh", wave, f"tail -25 {tlx}/tlx-finetune-{job_id}.out"], check=False)
        raise RuntimeError(f"WAVE job {job_id} produced no GGUF.\n{tail}")

    # 5. ship the GGUF WAVE -> atlas (relayed through this box: scp -3).
    adapters = settings.atlas_adapters_dir.rstrip("/")
    _run(["ssh", atlas, f"mkdir -p {adapters}"])
    _run(["scp", "-3", f"{wave}:{gguf_remote}", f"{atlas}:{adapters}/persona-{persona_id}.gguf"])

    # 6. `ollama create` on atlas (ADAPTER path must be absolute for Ollama).
    atlas_home = _remote_home(atlas)
    adapters_abs = adapters.replace("~", atlas_home, 1) if adapters.startswith("~") else adapters
    gguf_abs = f"{adapters_abs}/persona-{persona_id}.gguf"
    model = persona_model_name(persona_id)
    modelfile = (
        f"FROM {base}\n"
        f"ADAPTER {gguf_abs}\n"
        f'SYSTEM """{_SYSTEM_STUB}"""\n'
        "PARAMETER num_ctx 8192\n"
        "PARAMETER temperature 0.8\n"
    )
    local_mf = os.path.join(tmp, f"Modelfile.{persona_id}")
    with open(local_mf, "w", encoding="utf-8") as fh:
        fh.write(modelfile)
    _run(["scp", local_mf, f"{atlas}:{adapters}/Modelfile.{persona_id}"])
    _run(["ssh", atlas, f"ollama create {model} -f {adapters}/Modelfile.{persona_id}"])
    log.info("persona %s: served on atlas as %s", persona_id, model)

    # 7. pin the adapter so the live engine hot-swaps the voice.
    meta["adapter_model"] = model
    meta["adapter_path"] = gguf_abs
    persona.meta_json = json.dumps(meta, ensure_ascii=False)
    persona.updated_at = datetime.utcnow()
    session.add(persona)
    session.commit()
    return {"adapter_model": model, "adapter_path": gguf_abs}


def wave_handler(session: Session, job: Job) -> dict:
    """Job-queue handler ("finetune" via the WAVE backend)."""
    result = wave_finetune(session, job.persona_id)
    return {"adapter_path": result["adapter_path"]}
