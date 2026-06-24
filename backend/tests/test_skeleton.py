from fastapi.testclient import TestClient

from app import crypto
from app.main import app


def test_health():
    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json() == {"ok": True}


def test_crypto_roundtrip_handles_unicode():
    assert crypto.dec_str(crypto.enc_str("héllo中文 👋")) == "héllo中文 👋"


def test_models_import_and_create():
    from app.db import Persona, StyleTuning, User, init_db

    init_db()
    assert User.__tablename__ == "user"
    assert Persona.__tablename__ == "persona"
    assert StyleTuning.__tablename__ == "styletuning"
