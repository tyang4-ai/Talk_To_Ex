"""Upload ingestion — store an export, parse it, and normalize it.

``save_upload(persona_id, file, session)`` streams a FastAPI ``UploadFile`` to
disk (chunked, 50 MB cap), auto-detects its format, runs the matching parser to a
``NormalizedTranscript``, encrypts BOTH the raw bytes and the normalized
transcript to disk under ``uploads/`` (Fernet), and records an ``Upload`` row
with ``message_count``.

Cross-epic note (E1 parsers): the per-format parsers, ``detect_format`` and the
optional ``normalize`` step are owned by Epic E1 and imported **lazily** inside
the call so this module compiles and imports even while E1 is being built in
parallel. The friend never picks a format — we sniff it.
"""
from __future__ import annotations

import dataclasses
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from sqlmodel import Session

from .. import crypto
from ..db import Upload

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB hard cap
_CHUNK = 1024 * 1024  # 1 MB streaming chunk

# uploads/ lives beside the backend app package root (…/backend/uploads).
UPLOADS_ROOT = Path(__file__).resolve().parents[2] / "uploads"

# format -> parser module under app.ingestion.parsers (E1)
_PARSER_MODULES = {
    "imessage": "imessage",
    "instagram": "instagram",
    "facebook": "instagram",  # Facebook Messenger uses the same Meta schema
    "whatsapp": "whatsapp",
    "wechat": "wechat",
    "sms": "sms",
    "discord": "discord",
    "telegram": "telegram",
    "email": "mail",
    "generic": "generic",
    "plaintext": "plaintext",
}


class UploadTooLarge(Exception):
    """Raised when an upload exceeds ``MAX_UPLOAD_BYTES``."""


def _persona_dir(persona_id: int) -> Path:
    d = UPLOADS_ROOT / str(persona_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _stream_to_disk(file: Any, dest: Path) -> int:
    """Stream ``file`` (FastAPI UploadFile) to ``dest`` in chunks, enforcing the
    size cap. Returns the byte count. Uses aiofiles for async disk writes."""
    import aiofiles  # local import: not needed to import this module

    total = 0
    async with aiofiles.open(dest, "wb") as out:
        while True:
            chunk = await file.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                await out.close()
                try:
                    dest.unlink(missing_ok=True)
                except OSError:
                    pass
                raise UploadTooLarge(
                    f"upload exceeds {MAX_UPLOAD_BYTES} bytes (50 MB cap)"
                )
            await out.write(chunk)
    return total


def _detect_format(path: str) -> str:
    from .parsers.detect import detect_format  # E1

    return detect_format(path)


def _run_parser(fmt: str, path: str, target: Optional[str]) -> List[Any]:
    """Import the E1 parser module for ``fmt`` and run ``parse``."""
    import importlib

    mod_name = _PARSER_MODULES.get(fmt, "plaintext")
    module = importlib.import_module(f".parsers.{mod_name}", package=__package__)
    return module.parse(path, target)


def _normalize(transcript: List[Any]) -> List[Any]:
    """Apply E1's normalizer if present; otherwise the parser output is already
    a NormalizedTranscript and passes through unchanged."""
    try:
        from .normalize import normalize  # E1 (optional)
    except ImportError:
        return transcript
    return normalize(transcript)


def _message_to_dict(m: Any) -> dict:
    """Serialize a NormalizedMessage (dataclass) or dict to a JSON-safe dict."""
    if dataclasses.is_dataclass(m) and not isinstance(m, type):
        d = dataclasses.asdict(m)
    elif isinstance(m, dict):
        d = dict(m)
    else:
        d = {
            "sender": getattr(m, "sender", ""),
            "ts": getattr(m, "ts", ""),
            "text": getattr(m, "text", ""),
            "direction": getattr(m, "direction", ""),
        }
    ts = d.get("ts")
    if hasattr(ts, "isoformat"):
        d["ts"] = ts.isoformat()
    elif ts is not None:
        d["ts"] = str(ts)
    return d


def _serialize_transcript(transcript: List[Any]) -> bytes:
    payload = [_message_to_dict(m) for m in transcript]
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


async def save_upload(
    persona_id: int,
    file: Any,
    session: Session,
    target: Optional[str] = None,
) -> Upload:
    """Persist + parse + normalize an uploaded export, returning the Upload row.

    ``file`` is a FastAPI ``UploadFile`` (``.filename``, async ``.read``).
    ``target`` is the optional display name/handle of the ex (for formats that
    disambiguate participants).
    """
    pdir = _persona_dir(persona_id)
    filename = getattr(file, "filename", None) or "upload.bin"
    token = uuid.uuid4().hex

    # 1. stream raw bytes to a temp file (parsers need a real path).
    tmp_path = pdir / f"{token}.tmp"
    size = await _stream_to_disk(file, tmp_path)

    try:
        # 2. detect format + parse + normalize.
        fmt = _detect_format(str(tmp_path))
        transcript = _run_parser(fmt, str(tmp_path), target)
        transcript = _normalize(transcript)
        message_count = len(transcript)

        # 3. encrypt raw + normalized to disk under uploads/.
        raw_bytes = tmp_path.read_bytes()
        raw_enc_path = pdir / f"{token}.raw.enc"
        norm_enc_path = pdir / f"{token}.norm.enc"
        raw_enc_path.write_bytes(crypto.encrypt(raw_bytes))
        norm_enc_path.write_bytes(crypto.encrypt(_serialize_transcript(transcript)))
    finally:
        # raw plaintext temp never lingers.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    # 4. record the Upload row.
    upload = Upload(
        persona_id=persona_id,
        filename=filename,
        format=fmt,
        raw_enc_path=str(raw_enc_path),
        normalized_enc_path=str(norm_enc_path),
        message_count=message_count,
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    return upload


def load_normalized(upload: Upload) -> List[dict]:
    """Decrypt a stored normalized transcript back into a list of message dicts.

    Used by the distillation step to feed ``distill(transcript, intake)``.
    """
    enc = Path(upload.normalized_enc_path).read_bytes()
    return json.loads(crypto.decrypt(enc).decode("utf-8"))
