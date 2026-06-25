"""E10 — user-overridable persona model (spec §22/§26).

Auto-detect picks the model from the uploaded log's dominant language; an explicit
override wins, takes effect immediately, and survives re-distill; "auto" re-detects.
Fully mock-based (fake distill, no Ollama/keys). Mixed zh/en."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.config import settings
from app.db import get_session
from app.distill.schema import PersonaArtifacts, PersonaJSON


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture()
def client(engine):
    from app.auth.routes import router as auth_router
    from app.ingestion.routes import router as ingestion_router
    from app.persona.routes import router as persona_router

    def _override():
        with Session(engine) as s:
            yield s

    app = FastAPI()
    for r in (auth_router, persona_router, ingestion_router):
        app.include_router(r)
    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth(client) -> dict:
    reg = client.post(
        "/api/auth/register", json={"email": "ov@example.com", "password": "pw123456"}
    )
    assert reg.status_code == 201, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


def _upload_chinese_log(client, headers, pid, tmp_path):
    f = tmp_path / "chat.txt"
    f.write_text(
        "2024-01-01 小美: 想你了\n"
        "2024-01-02 小美: 今天过得怎么样\n"
        "2024-01-03 小美: 我们好久没聊天了\n"
        "2024-01-04 小美: 记得照顾好自己\n",
        encoding="utf-8",
    )
    with f.open("rb") as fh:
        up = client.post(
            f"/api/personas/{pid}/uploads",
            headers=headers,
            files={"file": ("chat.txt", fh, "text/plain")},
        )
    assert up.status_code == 200, up.text


def test_model_override_lifecycle(client, monkeypatch, tmp_path):
    headers = _auth(client)
    pid = client.post(
        "/api/personas", headers=headers, json={"name": "Xiaomei", "intake": {}}
    ).json()["id"]
    _upload_chinese_log(client, headers, pid, tmp_path)

    # distill is mocked — the route still computes the routed model from the log.
    arts = PersonaArtifacts(
        persona_md="# p", memories_md="# m", meta={},
        persona_json=PersonaJSON(name="Xiaomei").model_dump(),
    )
    monkeypatch.setattr("app.persona.routes.distill", lambda transcript, intake: arts)

    # 1) auto-detect: Chinese-dominant log -> Qwen
    d = client.post(f"/api/personas/{pid}/distill", headers=headers)
    assert d.status_code == 200, d.text
    assert d.json()["llm_model"] == settings.ollama_model_zh
    assert d.json()["llm_model_source"] == "auto"

    # 2) override to Gemma -> immediate, reflected in the summary
    r = client.post(
        f"/api/personas/{pid}/model", headers=headers,
        json={"model": settings.ollama_model_en},
    )
    assert r.status_code == 200, r.text
    assert r.json()["llm_model"] == settings.ollama_model_en
    assert r.json()["source"] == "manual"
    summ = client.get(f"/api/personas/{pid}", headers=headers).json()
    assert summ["llm_model"] == settings.ollama_model_en

    # 3) re-distill keeps the override (does NOT revert to auto)
    arts.meta.pop("llm_model_override", None)  # fresh distill output has no hint
    d2 = client.post(f"/api/personas/{pid}/distill", headers=headers)
    assert d2.json()["llm_model"] == settings.ollama_model_en
    assert d2.json()["llm_model_source"] == "manual"

    # 4) reset to auto -> re-detect Chinese -> Qwen
    r2 = client.post(
        f"/api/personas/{pid}/model", headers=headers, json={"model": "auto"}
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["llm_model"] == settings.ollama_model_zh
    assert r2.json()["source"] == "auto"


def test_model_override_rejects_unknown(client, monkeypatch, tmp_path):
    headers = _auth(client)
    pid = client.post(
        "/api/personas", headers=headers, json={"name": "X", "intake": {}}
    ).json()["id"]
    bad = client.post(
        f"/api/personas/{pid}/model", headers=headers, json={"model": "gpt-4o"}
    )
    assert bad.status_code == 400
