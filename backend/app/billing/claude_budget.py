"""Global daily ceiling on REAL Anthropic (Claude) calls + an instant kill-switch.

The owner's hard backstop against a runaway bill on the public service: every
costly Claude call (persona distillation, corrections, style re-tune) reserves a
slot here first, and once the configured daily budget is spent — or the operator
flips ``CLAUDE_KILL_SWITCH`` — further calls are refused with HTTP 503 until UTC
midnight. Counter is per-UTC-day in the ``ClaudeUsage`` table.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlmodel import Session, select

from ..config import settings
from ..db import ClaudeUsage


def remaining(session: Session) -> int:
    """Claude calls still allowed today (0 if the kill-switch is on)."""
    if settings.claude_kill_switch:
        return 0
    day = datetime.utcnow().strftime("%Y-%m-%d")
    row = session.exec(select(ClaudeUsage).where(ClaudeUsage.day == day)).first()
    used = row.count if row else 0
    return max(0, settings.max_claude_calls_per_day - used)


def consume(session: Session, n: int = 1) -> None:
    """Reserve ``n`` Claude calls for today, or raise 503 if the operator paused
    AI or the daily budget is exhausted. Call IMMEDIATELY before the real
    ``client.messages.create``. In demo mode there is no real spend, so callers
    should skip this guard."""
    if settings.claude_kill_switch:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "AI is paused by the operator."
        )
    day = datetime.utcnow().strftime("%Y-%m-%d")
    row = session.exec(select(ClaudeUsage).where(ClaudeUsage.day == day)).first()
    if row is None:
        row = ClaudeUsage(day=day, count=0)
        session.add(row)
        session.commit()
        session.refresh(row)
    if row.count + n > settings.max_claude_calls_per_day:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Daily AI budget reached — please try again tomorrow.",
        )
    row.count += n
    session.add(row)
    session.commit()
