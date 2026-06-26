"""WAVE→atlas fine-tune orchestration (mocked SSH — no cluster, no torch).

Asserts the sequence (export → ship → sbatch → poll → fetch → ollama create) and
that the persona's adapter_model gets pinned so the live engine hot-swaps.
"""
from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.config import settings
from app.db import Persona, User
from app.finetune import wave_runner


@pytest.fixture()
def session(monkeypatch):
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "finetune_epochs", 2)
    e = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(e)
    with Session(e) as s:
        u = User(email="f@e.com", pw_hash="x")
        s.add(u)
        s.commit()
        s.refresh(u)
        p = Persona(
            user_id=u.id, slug="m", name="小美",
            meta_json=json.dumps({"llm_model": "qwen2.5:14b-instruct-q4_K_M"}),
        )
        s.add(p)
        s.commit()
        s.refresh(p)
        s.pid = p.id  # type: ignore[attr-defined]
        yield s


def test_wave_finetune_orchestrates_and_pins_adapter(session, monkeypatch):
    pid = session.pid  # type: ignore[attr-defined]
    calls: list[str] = []

    # Fake every ssh/scp by inspecting the command text.
    def fake_run(cmd, *, timeout=None, check=True):
        joined = " ".join(cmd)
        calls.append(joined)
        if "echo $HOME" in joined:
            return "/home/tyang4\n"
        if "sbatch" in joined:
            return "Submitted batch job 12345\n"
        if "squeue" in joined:
            return ""                      # already left the queue → no wait
        if "test -f" in joined:
            return "OK\n"
        return ""

    monkeypatch.setattr(wave_runner, "_run", fake_run)
    monkeypatch.setattr(
        wave_runner.wave_export, "export_examples_jsonl",
        lambda s, p, path: 7,             # pretend 7 examples were written
    )

    result = wave_runner.wave_finetune(session, pid)

    assert result["adapter_model"] == f"persona-{pid}"
    assert result["adapter_path"] == f"/home/tyang4/tlx-adapters/persona-{pid}.gguf"

    # the persona now carries the adapter → the live engine prefers it
    meta = json.loads(session.get(Persona, pid).meta_json)
    assert meta["adapter_model"] == f"persona-{pid}"

    blob = "\n".join(calls)
    assert "sbatch --export=ALL,TLX_PID=" in blob and "TLX_BASE=qwen2.5:14b" in blob
    assert "scp -3" in blob                                  # WAVE → atlas relay
    assert f"ollama create persona-{pid}" in blob


def test_wave_finetune_raises_when_no_gguf(session, monkeypatch):
    pid = session.pid  # type: ignore[attr-defined]

    def fake_run(cmd, *, timeout=None, check=True):
        joined = " ".join(cmd)
        if "echo $HOME" in joined:
            return "/home/tyang4\n"
        if "sbatch" in joined:
            return "Submitted batch job 7\n"
        if "squeue" in joined:
            return ""
        if "test -f" in joined:
            return "MISSING\n"             # the job produced no artifact
        return "job log tail…"

    monkeypatch.setattr(wave_runner, "_run", fake_run)
    monkeypatch.setattr(wave_runner.wave_export, "export_examples_jsonl", lambda s, p, path: 3)

    with pytest.raises(RuntimeError, match="no GGUF"):
        wave_runner.wave_finetune(session, pid)
