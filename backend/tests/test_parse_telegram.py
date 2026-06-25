"""Tests for the Telegram Desktop ``result.json`` parser."""
from __future__ import annotations

import json

from app.ingestion.parsers.telegram import parse


SAMPLE = {
    "name": "Alice",
    "type": "personal_chat",
    "id": 12345,
    "messages": [
        {
            "id": 2,
            "type": "message",
            "date": "2023-05-01T12:01:00",
            "date_unixtime": "1682942460",
            "from": "Me",
            "from_id": "user99",
            # polymorphic text: string + entity objects
            "text": ["call me ", {"type": "bold", "text": "now"},
                     {"type": "link", "text": "http://x"}],
        },
        {
            "id": 1,
            "type": "message",
            "date": "2023-05-01T12:00:00",
            "date_unixtime": "1682942400",
            "from": "Alice",
            "from_id": "user42",
            "text": "hey",
        },
        {
            # service record — must be skipped
            "id": 3,
            "type": "service",
            "date": "2023-05-01T12:02:00",
            "date_unixtime": "1682942520",
            "action": "phone_call",
        },
        {
            # empty text — must be skipped
            "id": 4,
            "type": "message",
            "date": "2023-05-01T12:03:00",
            "date_unixtime": "1682942580",
            "from": "Alice",
            "from_id": "user42",
            "text": "",
        },
    ],
}


def _write_sample(tmp_path) -> str:
    fp = tmp_path / "result.json"
    fp.write_text(json.dumps(SAMPLE), encoding="utf-8")
    return str(fp)


def test_message_count_and_skips(tmp_path):
    # 4 records in, but service + empty are dropped → 2 real messages.
    msgs = parse(_write_sample(tmp_path), target="Alice")
    assert len(msgs) == 2


def test_text_is_extracted_and_concatenated(tmp_path):
    msgs = parse(_write_sample(tmp_path), target="Alice")
    texts = {m.text for m in msgs}
    assert "hey" in texts
    # the polymorphic list is flattened in order, concatenating every part.
    assert "call me nowhttp://x" in texts


def test_direction_for_known_ex(tmp_path):
    # target=Alice → Alice's messages are "in", everyone else "out".
    msgs = parse(_write_sample(tmp_path), target="Alice")
    by_sender = {m.sender: m.direction for m in msgs}
    assert by_sender["Alice"] == "in"
    assert by_sender["Me"] == "out"


def test_target_match_is_case_insensitive(tmp_path):
    msgs = parse(_write_sample(tmp_path), target="  aLiCe  ")
    by_sender = {m.sender: m.direction for m in msgs}
    assert by_sender["Alice"] == "in"
    assert by_sender["Me"] == "out"


def test_owner_heuristic_without_target(tmp_path):
    # no target → first distinct sender seen in file order is the owner ("out").
    # In the sample's messages[] array "Me" appears first, so "Me" is the owner;
    # Alice (the other party) is therefore inbound. Output is ts-sorted, so
    # Alice (12:00) lands first even though "Me" was seen first.
    msgs = parse(_write_sample(tmp_path))
    by_sender = {m.sender: m.direction for m in msgs}
    assert by_sender["Me"] == "out"
    assert by_sender["Alice"] == "in"


def test_ascending_ts_order(tmp_path):
    msgs = parse(_write_sample(tmp_path), target="Alice")
    ts = [m.ts for m in msgs]
    assert ts == sorted(ts)
    # earliest (Alice, 12:00) sorts before the later (Me, 12:01).
    assert msgs[0].sender == "Alice"
    assert msgs[1].sender == "Me"


def test_ts_is_timezone_aware_utc(tmp_path):
    msgs = parse(_write_sample(tmp_path), target="Alice")
    for m in msgs:
        assert m.ts.tzinfo is not None
        assert m.ts.utcoffset().total_seconds() == 0
