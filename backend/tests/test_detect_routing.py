"""Format auto-detection routing for the expanded parser set.

Locks the collision-safe ordering: the JSON family (Meta/Instagram, Facebook,
Discord, Telegram, generic) must each route to the right parser, and a bare
``{from,text}`` record must fall to *generic*, NOT Telegram.
"""
from __future__ import annotations

import json
import zipfile

from app.ingestion.parsers.detect import detect_format


def _w(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_discord_json(tmp_path):
    data = {
        "guild": {}, "channel": {"type": "DirectTextChat", "name": "a"},
        "messages": [{
            "id": "1", "type": "Default",
            "timestamp": "2023-05-01T12:00:00.000+00:00",
            "author": {"id": "1", "name": "a", "nickname": "A", "isBot": False},
            "content": "hi",
        }],
    }
    assert detect_format(_w(tmp_path, "x.json", json.dumps(data))) == "discord"


def test_discord_bare_list(tmp_path):
    data = [{
        "type": "Default", "timestamp": "2023-05-01T12:00:00.000+00:00",
        "author": {"name": "a"}, "content": "hi",
    }]
    assert detect_format(_w(tmp_path, "x.json", json.dumps(data))) == "discord"


def test_discord_csv(tmp_path):
    csv = "AuthorID,Author,Date,Content\n1,A,2023-05-01,hi\n"
    assert detect_format(_w(tmp_path, "export.csv", csv)) == "discord"


def test_telegram_json(tmp_path):
    data = {
        "name": "A", "type": "personal_chat", "id": 1,
        "messages": [{
            "id": 1, "type": "message", "date": "2023-05-01T12:00:00",
            "date_unixtime": "1682942400", "from": "A", "from_id": "u1", "text": "hi",
        }],
    }
    assert detect_format(_w(tmp_path, "result.json", json.dumps(data))) == "telegram"


def test_instagram_json_still_wins(tmp_path):
    data = {
        "participants": [{"name": "A"}, {"name": "Me"}],
        "messages": [{"sender_name": "A", "timestamp_ms": 1682942400000, "content": "hi"}],
    }
    assert detect_format(_w(tmp_path, "message_1.json", json.dumps(data))) == "instagram"


def test_generic_json_not_telegram(tmp_path):
    # {from,text} WITHOUT telegram markers must fall to generic, not telegram.
    data = [{"from": "A", "text": "hi", "date": "2023-05-01"}]
    assert detect_format(_w(tmp_path, "x.json", json.dumps(data))) == "generic"


def test_generic_csv(tmp_path):
    csv = "sender,message,date\nA,hi,2023-05-01\n"
    assert detect_format(_w(tmp_path, "chat.csv", csv)) == "generic"


def test_email_eml_ext(tmp_path):
    eml = (
        "From: A <a@x.com>\nTo: Me <me@x.com>\nSubject: hi\n"
        "Date: Mon, 1 May 2023 12:00:00 +0000\n\nbody\n"
    )
    assert detect_format(_w(tmp_path, "m.eml", eml)) == "email"


def test_email_mbox_content_txt(tmp_path):
    mbox = (
        "From a@x.com Mon May  1 12:00:00 2023\n"
        "From: A <a@x.com>\nSubject: hi\nDate: Mon, 1 May 2023 12:00:00 +0000\n\nbody\n"
    )
    assert detect_format(_w(tmp_path, "export.txt", mbox)) == "email"


def test_eml_content_no_extension(tmp_path):
    eml = (
        "From: A <a@x.com>\nTo: Me <me@x.com>\nSubject: hi\n"
        "Date: Mon, 1 May 2023 12:00:00 +0000\n\nbody\n"
    )
    assert detect_format(_w(tmp_path, "noext", eml)) == "email"


def test_facebook_zip_label(tmp_path):
    p = tmp_path / "fb.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(
            "your_facebook_activity/messages/inbox/alice_123/message_1.json",
            json.dumps({
                "participants": [{"name": "A"}],
                "messages": [{"sender_name": "A", "timestamp_ms": 1, "content": "hi"}],
            }),
        )
    assert detect_format(str(p)) == "facebook"


def test_plaintext_fallback(tmp_path):
    assert detect_format(_w(tmp_path, "chat.txt", "2021-03-12 21:04 Alice: hey\n")) == "plaintext"
