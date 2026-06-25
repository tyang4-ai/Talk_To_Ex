"""Discord parser — DiscordChatExporter JSON: count, text extraction, direction
by target, ascending ts, service-record/empty-content skipping, CSV + bare-list."""
import json

from app.ingestion.parsers import discord

# genuine UTF-8-as-latin-1 mojibake for "❤" (ftfy repairs this back to a heart;
# the raw form below contains NO heart, so the assertion proves repair ran).
MOJI_HEART = "❤".encode("utf-8").decode("latin-1")


def _write_export(tmp_path):
    """A DiscordChatExporter DM dump, intentionally newest-message-FIRST in the
    file so the parser's ascending sort is actually exercised. Includes a service
    record (type != Default/Reply) and an attachment-only empty message to be
    skipped, plus mojibake to be repaired by ftfy."""
    export = {
        "guild": {"id": "0", "name": "Direct Messages"},
        "channel": {"type": "DirectTextChat", "name": "alice"},
        "messages": [
            # out of order on purpose (newest first)
            {
                "id": "4",
                "type": "Default",
                "timestamp": "2023-05-01T12:05:00.000+00:00",
                "author": {"id": "42", "name": "alice", "nickname": "Alice"},
                "content": "i miss you " + MOJI_HEART,  # mojibake heart
            },
            {
                "id": "3",
                "type": "Default",
                "timestamp": "2023-05-01T12:01:10.000+00:00",
                "author": {"id": "99", "name": "me", "nickname": "Me"},
                "content": "yeah what's up",
            },
            # attachment-only: empty content → skipped
            {
                "id": "2b",
                "type": "Default",
                "timestamp": "2023-05-01T12:00:30.000+00:00",
                "author": {"id": "42", "name": "alice", "nickname": "Alice"},
                "content": "   ",
            },
            # service record: a recipient-add → skipped
            {
                "id": "2a",
                "type": "RecipientAdd",
                "timestamp": "2023-05-01T12:00:20.000+00:00",
                "author": {"id": "42", "name": "alice", "nickname": "Alice"},
                "content": "added someone",
            },
            {
                "id": "1",
                "type": "Default",
                "timestamp": "2023-05-01T12:00:00.000+00:00",
                "author": {"id": "42", "name": "alice", "nickname": "Alice"},
                "content": "hey, you up?",
            },
        ],
    }
    p = tmp_path / "alice.json"
    p.write_text(json.dumps(export), encoding="utf-8")
    return str(p)


def test_discord_count_text_direction_and_order(tmp_path):
    path = _write_export(tmp_path)
    msgs = discord.parse(path, target="alice")

    # 5 records, but the service row + empty-content row are dropped → 3 kept
    assert len(msgs) == 3

    # text is extracted and mojibake repaired by ftfy
    assert msgs[0].text == "hey, you up?"
    assert any("i miss you" in m.text and "❤" in m.text for m in msgs)
    # the mojibake must NOT survive verbatim (proves ftfy actually repaired it)
    assert all(MOJI_HEART not in m.text for m in msgs)

    # ascending ts order (file was newest-first)
    tss = [m.ts for m in msgs]
    assert tss == sorted(tss)
    assert all(m.ts.tzinfo is not None for m in msgs)  # tz-aware UTC

    # direction by target: the ex ("alice", matched by name/nickname) is "in";
    # the owner ("me") is "out".
    by_sender = {m.sender: m for m in msgs}
    assert by_sender["Alice"].direction == "in"
    assert by_sender["Me"].direction == "out"
    assert any(m.direction == "in" for m in msgs)
    assert any(m.direction == "out" for m in msgs)


def test_discord_direction_by_nickname_match(tmp_path):
    path = _write_export(tmp_path)
    # target given as the nickname (display) rather than the handle
    msgs = discord.parse(path, target="Alice")
    assert all((m.direction == "in") == (m.sender == "Alice") for m in msgs)


def test_discord_owner_heuristic_without_target(tmp_path):
    path = _write_export(tmp_path)
    msgs = discord.parse(path, target=None)
    # first distinct sender in chronological order is "alice" (the 12:00 msg) →
    # treated as the owner ("out"); "me" becomes "in".
    first = min(msgs, key=lambda m: m.ts)
    assert first.direction == "out"
    assert any(m.direction == "in" for m in msgs)


def test_discord_bare_list_accepted(tmp_path):
    bare = [
        {
            "id": "1",
            "type": "Default",
            "timestamp": "2023-05-01T12:00:00.000+00:00",
            "author": {"id": "42", "name": "alice"},
            "content": "first",
        },
        {
            "id": "2",
            "type": "Default",
            "timestamp": "2023-05-01T12:01:00.000+00:00",
            "author": {"id": "99", "name": "me"},
            "content": "second",
        },
    ]
    p = tmp_path / "bare.json"
    p.write_text(json.dumps(bare), encoding="utf-8")
    msgs = discord.parse(str(p), target="alice")
    assert len(msgs) == 2
    assert msgs[0].text == "first" and msgs[0].direction == "in"
    assert msgs[1].direction == "out"


def test_discord_csv_fallback(tmp_path):
    p = tmp_path / "alice.csv"
    p.write_text(
        "AuthorID,Author,Date,Content\n"
        "42,alice,2023-05-01T12:00:00.000+00:00,hey there\n"
        "99,me,2023-05-01T12:01:00.000+00:00,hi\n",
        encoding="utf-8",
    )
    msgs = discord.parse(str(p), target="alice")
    assert len(msgs) == 2
    assert msgs[0].text == "hey there" and msgs[0].direction == "in"
    assert msgs[1].direction == "out"
    assert [m.ts for m in msgs] == sorted(m.ts for m in msgs)
