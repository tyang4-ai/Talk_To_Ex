"""Per-conversation message history: append a turn (bumping the conversation's
running ``message_count`` and ``last_active``) and fetch the most recent turns
in chronological order for prompt assembly.
"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from ..db import Conversation, Message


def append(
    session: Session,
    conv: Conversation,
    direction: str,
    body: str,
) -> Message:
    """Persist one turn and increment the conversation counter.

    ``direction`` is ``"in"`` (from the peer) or ``"out"`` (from the persona).
    """
    msg = Message(conversation_id=conv.id, direction=direction, body=body)
    session.add(msg)

    conv.message_count = (conv.message_count or 0) + 1
    conv.last_active = datetime.utcnow()
    session.add(conv)

    session.commit()
    session.refresh(msg)
    session.refresh(conv)
    return msg


def recent(session: Session, conv: Conversation, n: int = 20) -> list[Message]:
    """Return the last ``n`` messages for ``conv`` in chronological (old→new) order."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.id.desc())
        .limit(n)
    )
    rows = list(session.exec(stmt))
    rows.reverse()
    return rows
