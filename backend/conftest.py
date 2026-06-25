"""Test environment bootstrap. Runs before app modules import config, so secrets
are present and the DB points at a throwaway file."""
import os
import sqlite3
from cryptography.fernet import Fernet

os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC_test")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-twilio-token")
os.environ.setdefault("TWILIO_FROM_NUMBER", "+18005550100")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_x")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test")
os.environ.setdefault("STRIPE_PRICE_ID", "price_test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_ttx.db")
# Shield the suite from a DEMO_MODE=true in backend/.env (env vars outrank .env):
# tests run in production semantics; demo branches are exercised via monkeypatch.
os.environ.setdefault("DEMO_MODE", "false")


# --- Binary parser fixtures ---------------------------------------------------
# The iMessage / WeChat parsers are exercised against real SQLite files, but
# ``*.db`` is git-ignored (see root .gitignore), so these blobs are never
# committed. Build them deterministically before collection so ``pytest`` is
# green on a fresh clone with no real keys. Idempotent: only writes if missing.

_FIX = os.path.join(os.path.dirname(__file__), "tests", "fixtures")


def _build_imessage_db(path: str) -> None:
    """A minimal iMessage ``sms.db`` matching app/ingestion/parsers/imessage.py.

    Three messages, ascending Apple-epoch dates so the parser's timestamp sort
    yields: [0] plain incoming "你好", [1] outgoing, [2] NULL-text incoming whose
    body lives in ``attributedBody`` (recovered via the injected decoder; the
    default pytypedstream decoder fails on this stub blob and drops the row,
    which the "lib absent" test explicitly allows)."""
    if os.path.exists(path):
        return
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);
            CREATE TABLE chat   (ROWID INTEGER PRIMARY KEY, guid TEXT);
            CREATE TABLE message (
                ROWID          INTEGER PRIMARY KEY,
                text           TEXT,
                attributedBody BLOB,
                date           INTEGER,
                is_from_me     INTEGER,
                handle_id      INTEGER
            );
            CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
            """
        )
        conn.execute("INSERT INTO handle (ROWID, id) VALUES (1, '+15551234567')")
        conn.execute("INSERT INTO chat (ROWID, guid) VALUES (1, 'iMessage;-;+15551234567')")
        conn.executemany(
            "INSERT INTO message (ROWID, text, attributedBody, date, is_from_me, handle_id)"
            " VALUES (?,?,?,?,?,?)",
            [
                (1, "你好", None, 600_000_000, 0, 1),                 # incoming, plain text
                (2, "我很好", None, 600_000_100, 1, 0),               # outgoing
                (3, None, b"not-a-real-typedstream-attributedBody",  # NULL text -> attributedBody fallback
                 600_000_200, 0, 1),
            ],
        )
        conn.executemany(
            "INSERT INTO chat_message_join (chat_id, message_id) VALUES (?,?)",
            [(1, 1), (1, 2), (1, 3)],
        )
        conn.commit()
    finally:
        conn.close()


def _build_wechat_encrypted_db(path: str) -> None:
    """A stand-in for a SQLCipher-encrypted WeChat DB: a ``.db`` file whose head
    is NOT the plain-SQLite magic, so wechat.parse() raises ParserNeedsManualExport
    (the random 16-byte salt header is how SQLCipher files actually look)."""
    if os.path.exists(path):
        return
    salt = bytes(range(1, 17))  # 16 fixed, non-magic bytes (no "SQLite format 3\x00")
    with open(path, "wb") as fh:
        fh.write(salt + b"\x00" * 48)


def _ensure_db_fixtures() -> None:
    os.makedirs(_FIX, exist_ok=True)
    _build_imessage_db(os.path.join(_FIX, "sms.db"))
    _build_wechat_encrypted_db(os.path.join(_FIX, "wechat_encrypted.db"))


_ensure_db_fixtures()
