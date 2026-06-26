"""SQLModel engine + the full table schema (spec §7). Sensitive columns ending
in `_enc` hold Fernet tokens via app.crypto."""
from datetime import datetime
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine

from .config import settings


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    pw_hash: str
    stripe_customer_id: Optional[str] = None
    subscription_status: str = "inactive"  # inactive|active|past_due|canceled
    subscription_id: Optional[str] = None
    phone_e164: Optional[str] = None  # where the persona texts them first (the reveal)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Persona(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    slug: str = Field(index=True)
    name: str
    meta_json: str = "{}"
    persona_md_enc: Optional[str] = None
    memories_md_enc: Optional[str] = None
    style_overlay_enc: Optional[str] = None  # latest Layer-2 refinement
    status: str = "draft"  # draft|active|dormant
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Number(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    persona_id: int = Field(foreign_key="persona.id", index=True)
    e164: str = Field(index=True)
    provider: str = "twilio"
    mode: str = "trial"  # trial|tollfree
    status: str = "assigned"


class Conversation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    persona_id: int = Field(foreign_key="persona.id", index=True)
    peer_e164: str = Field(index=True)
    summary: str = ""
    message_count: int = 0
    last_active: datetime = Field(default_factory=datetime.utcnow)


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    direction: str  # in|out
    body: str
    ts: datetime = Field(default_factory=datetime.utcnow)


class MemoryChunk(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    persona_id: int = Field(foreign_key="persona.id", index=True)
    text: str
    embedding_json: Optional[str] = None


class Upload(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    persona_id: int = Field(foreign_key="persona.id", index=True)
    filename: str
    format: str
    raw_enc_path: str
    normalized_enc_path: str
    message_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Correction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    persona_id: int = Field(foreign_key="persona.id", index=True)
    instruction: str
    applied_at: datetime = Field(default_factory=datetime.utcnow)


class Version(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    persona_id: int = Field(foreign_key="persona.id", index=True)
    snapshot_json: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SafetyEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    kind: str
    body: str
    direction: str = "in"  # "in" = inbound crisis trip; "out" = blocked generated reply (§24.4)
    ts: datetime = Field(default_factory=datetime.utcnow)


class StyleTuning(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    persona_id: int = Field(foreign_key="persona.id", index=True)
    conversation_id: Optional[int] = Field(default=None, foreign_key="conversation.id")
    overlay_json_enc: str
    msg_count_at_run: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Job(SQLModel, table=True):
    """Async work item (spec §28): a persisted queue so a long fine-tune (§23)
    runs out-of-process without blocking the web app. status:
    queued → training → ready | failed."""
    id: Optional[int] = Field(default=None, primary_key=True)
    persona_id: int = Field(foreign_key="persona.id", index=True)
    kind: str = "finetune"
    status: str = "queued"  # queued|training|ready|failed
    adapter_path: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def _literal_default(col) -> Optional[str]:
    """A SQL literal for a column's simple scalar Python default, else None."""
    d = getattr(col, "default", None)
    if d is None or not getattr(d, "is_scalar", False):
        return None
    val = d.arg
    if callable(val):
        return None
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return "'" + val.replace("'", "''") + "'"
    return None


def _migrate_add_missing_columns(eng) -> None:
    """Lightweight, idempotent forward-migration (we have no Alembic): for each
    existing table, ALTER TABLE ADD COLUMN any model column that's missing. Keeps
    a dev DB created before a model gained a column from 500ing at query time."""
    from sqlalchemy import inspect, text

    insp = inspect(eng)
    existing_tables = set(insp.get_table_names())
    with eng.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all already made brand-new tables in full
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                coltype = col.type.compile(dialect=eng.dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'
                default = _literal_default(col)
                if default is not None:
                    ddl += f" DEFAULT {default}"
                conn.execute(text(ddl))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate_add_missing_columns(engine)


def get_session():
    with Session(engine) as session:
        yield session
