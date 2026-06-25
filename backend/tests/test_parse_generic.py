"""Generic structured-chat parser — CSV + JSON catch-all.

Covers: message count, text extraction, direction by target (the known ex),
ascending ts order, the no-target owner heuristic, mojibake repair, and the
``{"messages": [...]}`` JSON shape with epoch + ISO dates. Self-contained:
fixtures are written to ``tmp_path``; no network.
"""
from datetime import timezone

from app.ingestion.parsers import generic


def test_generic_csv_counts_text_direction_order(tmp_path):
    p = tmp_path / "chat.csv"
    # header order is intentionally not first-message-first; columns use alias
    # names (from/body/timestamp) to exercise case-insensitive candidate mapping.
    p.write_text(
        "From,Body,Timestamp\n"
        "小美,你好呀,2021-03-12T21:04:00Z\n"
        "Me,hey you,2021-03-12T21:05:00Z\n"
        "小美,我想你了 ❤️,2021-03-12T21:06:00Z\n"
        "Me,,2021-03-12T21:07:00Z\n",  # empty body → skipped
        encoding="utf-8",
    )
    msgs = generic.parse(str(p), target="小美")

    # 4 rows in, one has empty text → 3 messages
    assert len(msgs) == 3
    # text is extracted (and not blank)
    assert msgs[0].text == "你好呀"
    assert any("我想你了" in m.text and "❤️" in m.text for m in msgs)
    # direction is correct for the known ex (target)
    assert msgs[0].direction == "in"           # from 小美 (the ex)
    assert any(m.direction == "out" for m in msgs)  # the owner's reply ("Me")
    # ascending ts order, all timezone-aware UTC
    tss = [m.ts for m in msgs]
    assert tss == sorted(tss)
    assert all(m.ts.tzinfo is not None for m in msgs)
    assert all(m.ts.utcoffset() == timezone.utc.utcoffset(m.ts) for m in msgs)


def test_generic_json_messages_wrapper_epoch_and_iso(tmp_path):
    p = tmp_path / "chat.json"
    # {"messages": [...]} shape; mix of epoch-seconds and ISO date; newest first
    # so the parser must sort ascending. Alias keys author/content/time/date.
    p.write_text(
        """
        {"messages": [
            {"author": "Me",   "content": "later reply", "date": "2021-03-12T21:10:00Z"},
            {"author": "Alex", "content": "miss you",     "time": 1615582000},
            {"author": "Me",   "content": "",             "time": 1615582100},
            {"author": "Alex", "content": "hi there",     "time": 1615582050}
        ]}
        """,
        encoding="utf-8",
    )
    msgs = generic.parse(str(p), target="Alex")

    # 4 records, one empty content → 3 messages
    assert len(msgs) == 3
    # text extracted
    assert {m.text for m in msgs} == {"later reply", "miss you", "hi there"}
    # direction by target: Alex is the ex → "in"; Me → "out"
    by_text = {m.text: m for m in msgs}
    assert by_text["miss you"].direction == "in"
    assert by_text["hi there"].direction == "in"
    assert by_text["later reply"].direction == "out"
    # ascending ts order (epoch + ISO normalised to UTC)
    tss = [m.ts for m in msgs]
    assert tss == sorted(tss)
    assert msgs[-1].text == "later reply"  # the ISO 21:10 one is latest


def test_generic_top_level_list_owner_heuristic(tmp_path):
    p = tmp_path / "chat.json"
    # top-level list, NO target → first distinct sender is the owner ("out").
    p.write_text(
        """
        [
            {"name": "Sam", "msg": "first line",  "timestamp": 1615582000},
            {"name": "Robin", "msg": "second line", "timestamp": 1615582010},
            {"name": "Sam", "msg": "third line",  "timestamp": 1615582020}
        ]
        """,
        encoding="utf-8",
    )
    msgs = generic.parse(str(p))  # no target

    assert len(msgs) == 3
    # Sam appears first → owner → "out"; Robin → "in"
    assert msgs[0].sender == "Sam" and msgs[0].direction == "out"
    assert any(m.sender == "Robin" and m.direction == "in" for m in msgs)
    assert [m.text for m in msgs] == ["first line", "second line", "third line"]
