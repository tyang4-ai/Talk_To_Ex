"""Global Claude spend ceiling — the operator's hard backstop against a runaway
Anthropic bill on the public service."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.billing import claude_budget
from app.config import settings


@pytest.fixture()
def session():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


def test_consume_caps_at_daily_budget(session, monkeypatch):
    monkeypatch.setattr(settings, "claude_kill_switch", False)
    monkeypatch.setattr(settings, "max_claude_calls_per_day", 3)
    for _ in range(3):
        claude_budget.consume(session)  # within budget
    assert claude_budget.remaining(session) == 0
    with pytest.raises(HTTPException) as ei:
        claude_budget.consume(session)  # over budget
    assert ei.value.status_code == 503


def test_kill_switch_blocks_everything(session, monkeypatch):
    monkeypatch.setattr(settings, "claude_kill_switch", True)
    monkeypatch.setattr(settings, "max_claude_calls_per_day", 100)
    assert claude_budget.remaining(session) == 0
    with pytest.raises(HTTPException) as ei:
        claude_budget.consume(session)
    assert ei.value.status_code == 503
