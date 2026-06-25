"""Upload API (E6): the friend drops an export, we sniff + parse + store it."""
from __future__ import annotations

from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlmodel import Session

from ..auth.deps import get_current_user
from ..db import Persona, User, get_session
from ..ingestion.parsers.base import ParserNeedsManualExport
from ..ingestion.upload import UploadTooLarge, load_normalized, save_upload

router = APIRouter(prefix="/api/personas", tags=["uploads"])


def _guess_ex_name(norm: list, target: Optional[str]) -> str:
    """The ex's display name: the upload target, else the first inbound sender."""
    if target:
        return target
    for m in norm:
        if m.get("direction") == "in" and m.get("sender"):
            return str(m["sender"])
    return "your ex"


@router.post("/{persona_id}/uploads")
async def upload_export(
    persona_id: int,
    file: UploadFile = File(...),
    target: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    persona = session.get(Persona, persona_id)
    if persona is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "persona not found")
    if persona.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your persona")

    try:
        up = await save_upload(persona_id, file, session, target)
    except UploadTooLarge as e:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(e))
    except ParserNeedsManualExport as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"This export is encrypted — use the plaintext-paste fallback. ({e})",
        )

    # Build the parse-preview the wizard shows ("✓ N messages from [ex]" + samples).
    norm = load_normalized(up)
    texts = [str(m.get("text") or "") for m in norm if m.get("text")]
    tss = sorted(str(m.get("ts")) for m in norm if m.get("ts"))
    return {
        "ok": True,
        "id": up.id,
        "filename": up.filename,
        "format": up.format,
        "message_count": up.message_count,
        "ex_name": _guess_ex_name(norm, target),
        "date_start": (tss[0][:10] if tss else None),
        "date_end": (tss[-1][:10] if tss else None),
        "sample_lines": texts[:3],
    }
