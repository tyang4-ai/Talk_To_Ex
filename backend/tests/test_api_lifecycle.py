"""E6 integration — the persona lifecycle wired through the real routers:
register -> create -> upload(real plaintext parse) -> distill(mock Claude) ->
activate(subscription-gated) -> preview(mock local engine). Mirrors the E5
isolated-DB fixture so it never touches the real file DB."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.db import User, get_session
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

    test_app = FastAPI()
    for r in (auth_router, persona_router, ingestion_router):
        test_app.include_router(r)
    test_app.dependency_overrides[get_session] = _override
    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


def _activate(engine, email: str) -> None:
    with Session(engine) as s:
        u = s.exec(select(User).where(User.email == email)).first()
        u.subscription_status = "active"
        s.add(u)
        s.commit()


def test_persona_lifecycle(client, engine, monkeypatch, tmp_path):
    email = "lifecycle@example.com"
    reg = client.post(
        "/api/auth/register", json={"email": email, "password": "pw123456"}
    )
    assert reg.status_code == 201, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    # create draft persona
    r = client.post(
        "/api/personas",
        headers=headers,
        json={"name": "Xiaomei", "intake": {"how_met": "class"}},
    )
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert r.json()["status"] == "draft"

    # upload a plaintext export — real detect + parse, no external deps
    f = tmp_path / "chat.txt"
    f.write_text("2024-01-01 Xiaomei: 想你了\n2024-01-02 Me: hey\n", encoding="utf-8")
    with f.open("rb") as fh:
        up = client.post(
            f"/api/personas/{pid}/uploads",
            headers=headers,
            files={"file": ("chat.txt", fh, "text/plain")},
        )
    assert up.status_code == 200, up.text
    assert up.json()["message_count"] >= 1

    # distill — mock the Claude pipeline
    arts = PersonaArtifacts(
        persona_md="# persona",
        memories_md="# memories",
        meta={},
        persona_json=PersonaJSON(name="Xiaomei").model_dump(),
    )
    monkeypatch.setattr("app.persona.build.distill", lambda transcript, intake: arts)
    d = client.post(f"/api/personas/{pid}/distill", headers=headers)
    assert d.status_code == 200, d.text

    # activate is gated on an active subscription
    assert client.post(f"/api/personas/{pid}/activate", headers=headers).status_code == 402
    _activate(engine, email)
    act = client.post(f"/api/personas/{pid}/activate", headers=headers)
    assert act.status_code == 200, act.text
    assert act.json()["e164"]

    # preview — mock the local model engine
    monkeypatch.setattr(
        "app.persona.routes.engine_reply", lambda *a, **k: ["hey", "想你"]
    )
    pv = client.post(
        f"/api/personas/{pid}/preview", headers=headers, json={"message": "hi"}
    )
    assert pv.status_code == 200, pv.text
    assert pv.json()["bubbles"] == ["hey", "想你"]
