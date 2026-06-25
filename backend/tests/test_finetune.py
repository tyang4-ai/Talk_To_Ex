"""E13 — fine-tune pipeline (spec §23), fully mock-based (no GPU, no network).

dataprep shaping; the train/convert/serve steps via injected runners; the pipeline
pins adapter_model on the persona; the engine then answers on the adapter; the job
handler registers; default (real) runners raise host-only errors."""
from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.config import settings
from app.convo import engine as convo_engine
from app.db import Persona, User
from app.finetune import convert, dataprep, pipeline, serve, train
from app.jobs import worker


# --- dataprep (pure) -------------------------------------------------------
def test_build_examples_maps_ex_to_assistant():
    transcript = [
        {"direction": "out", "text": "hey 在吗"},      # friend -> user
        {"direction": "in", "text": "在啊 怎么了"},     # ex    -> assistant (target)
        {"direction": "out", "text": "miss you"},
        {"direction": "in", "text": "想你了"},          # ex    -> assistant (target)
    ]
    examples = dataprep.build_examples(transcript)
    assert len(examples) == 2
    # every example ends on the ex's (assistant) line and has a prior user turn
    for ex in examples:
        assert ex.messages[-1]["role"] == "assistant"
        assert any(m["role"] == "user" for m in ex.messages[:-1])
    assert examples[0].messages[-1]["content"] == "在啊 怎么了"   # CJK preserved
    assert examples[1].messages[-1]["content"] == "想你了"


def test_build_examples_skips_leading_ex_with_no_context():
    # an assistant turn with no preceding user turn yields no example
    assert dataprep.build_examples([{"direction": "in", "text": "hi"}]) == []


# --- step runners reject the real path off-host ----------------------------
def test_real_runners_are_host_only():
    with pytest.raises(RuntimeError, match="host-only"):
        train.qlora([dataprep.ChatExample(messages=[{"role": "assistant", "content": "x"}])], "base", "/out")
    with pytest.raises(RuntimeError, match="host-only"):
        convert.to_gguf("/adapter", "/out.gguf")
    with pytest.raises(RuntimeError, match="host-only"):
        serve.register_adapter(1, "/x.gguf", "base")


def test_qlora_requires_examples():
    with pytest.raises(ValueError, match="no training examples"):
        train.qlora([], "base", "/out", runner=lambda *a: "/never")


def test_build_modelfile_shape():
    mf = serve.build_modelfile("qwen2.5:14b-instruct-q4_K_M", "/p/persona-1.gguf")
    assert "FROM qwen2.5:14b-instruct-q4_K_M" in mf
    assert "ADAPTER /p/persona-1.gguf" in mf
    assert "num_ctx 8192" in mf


# --- pipeline orchestration (DI) -------------------------------------------
@pytest.fixture()
def persona_session(monkeypatch):
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        user = User(email="ft@example.com", pw_hash="x")
        s.add(user)
        s.commit()
        s.refresh(user)
        p = Persona(
            user_id=user.id, slug="m", name="小美",
            meta_json=json.dumps({"llm_model": "qwen2.5:14b-instruct-q4_K_M"}),
        )
        s.add(p)
        s.commit()
        s.refresh(p)
        s.persona_id = p.id  # type: ignore[attr-defined]
        yield s


def test_run_finetune_pins_adapter_and_engine_uses_it(persona_session, monkeypatch):
    pid = persona_session.persona_id  # type: ignore[attr-defined]

    # No real uploads -> stub the transcript loader with a tiny zh exchange.
    monkeypatch.setattr(
        pipeline, "load_normalized",
        lambda upload: [],  # not reached (no uploads); kept for safety
    )
    monkeypatch.setattr(
        pipeline.dataprep, "build_examples",
        lambda transcript, **k: [dataprep.ChatExample(messages=[
            {"role": "user", "content": "hi"}, {"role": "assistant", "content": "在啊"}])],
    )

    created = {}
    res = pipeline.run_finetune(
        persona_session, pid,
        train_runner=lambda ex, base, out: f"{out}/adapter",
        convert_runner=lambda adir, out: out,
        ollama_create=lambda name, mf: created.update(name=name, mf=mf),
    )

    assert res["adapter_model"] == f"persona-{pid}"
    assert res["adapter_path"].endswith(f"persona-{pid}.gguf")
    assert created["name"] == f"persona-{pid}"
    assert "ADAPTER" in created["mf"]

    # The persona now carries adapter_model, and the engine prefers it.
    p = persona_session.get(Persona, pid)
    meta = json.loads(p.meta_json)
    assert meta["adapter_model"] == f"persona-{pid}"
    assert convo_engine._persona_model(p) == f"persona-{pid}"


def test_run_finetune_errors_without_examples(persona_session, monkeypatch):
    pid = persona_session.persona_id  # type: ignore[attr-defined]
    monkeypatch.setattr(pipeline.dataprep, "build_examples", lambda transcript, **k: [])
    with pytest.raises(ValueError, match="no training examples"):
        pipeline.run_finetune(persona_session, pid)


def test_register_handler_wires_worker():
    worker.DISPATCH.pop("finetune", None)
    pipeline.register_handler()
    assert worker.DISPATCH.get("finetune") is pipeline.finetune_handler
