"""DEMO_MODE — the keyless local fallbacks that make the wizard clickable on
localhost with no external accounts. (CI runs with DEMO_MODE=false; these flip it
per-test via monkeypatch.)"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.billing import metering, number_service
from app.config import settings
from app.db import Persona, User, get_session
from app.distill.fallback import distill_local
from app.distill.schema import PersonaJSON


# --- local distillation fallback (pure) ------------------------------------
def test_distill_local_builds_valid_artifacts():
    transcript = [
        {"direction": "in", "text": "想你了", "sender": "小美"},
        {"direction": "out", "text": "我也是", "sender": "me"},
        {"direction": "in", "text": "在干嘛", "sender": "小美"},
    ]
    intake = {"nickname": "小美", "personality_tags": ["warm"], "attachment_style": "anxious"}
    arts = distill_local(transcript, intake)
    # structurally valid 5-layer persona
    pj = PersonaJSON.model_validate(arts.persona_json)
    assert pj.name == "小美"
    assert pj.layer2_expression.examples  # grounded in the real chat
    assert arts.persona_md and arts.memories_md
    assert arts.meta["distilled_by"] == "local-demo"


# --- demo bypasses (DB-backed) ---------------------------------------------
@pytest.fixture()
def session(monkeypatch):
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        u = User(email="d@example.com", pw_hash="x", subscription_status="inactive")
        s.add(u)
        s.commit()
        s.refresh(u)
        p = Persona(user_id=u.id, slug="m", name="小美", status="draft")
        s.add(p)
        s.commit()
        s.refresh(p)
        s.persona_id = p.id  # type: ignore[attr-defined]
        yield s


def test_provision_bypasses_subscription_in_demo(session, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "twilio_from_number", "+15555550100")
    p = session.get(Persona, session.persona_id)  # type: ignore[attr-defined]
    num = number_service.provision(session, p)  # inactive user, but demo → OK
    assert num.e164 == "+15555550100" and num.mode == "trial"


def test_provision_still_gated_when_not_demo(session, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    p = session.get(Persona, session.persona_id)  # type: ignore[attr-defined]
    with pytest.raises(number_service.SubscriptionRequired):
        number_service.provision(session, p)


def test_metering_active_in_demo(session, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    assert metering.subscription_active(session, session.persona_id) is True  # type: ignore[attr-defined]


def test_demo_checkout_returns_intake(monkeypatch):
    from app.auth.routes import router as auth_router
    from app.billing.routes import router as billing_router

    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)

    def _override():
        with Session(eng) as s:
            yield s

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(billing_router)
    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        tok = c.post(
            "/api/auth/register", json={"email": "c@example.com", "password": "pw123456"}
        ).json()["access_token"]
        r = c.post("/api/billing/checkout", headers={"Authorization": f"Bearer {tok}"}, json={})
        assert r.status_code == 200 and r.json()["url"] == "/intake"
