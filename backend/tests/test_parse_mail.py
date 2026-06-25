"""Email parser — .mbox + .eml: counts, body extraction, direction, ts order.

Self-contained: the sample mbox/eml are written to ``tmp_path`` inline; no
network, no on-disk fixtures.
"""
import textwrap

from app.ingestion.parsers import mail

# Three messages, deliberately NOT in chronological order in the file, so the
# ascending-by-ts sort is actually exercised. The ex is "Jamie".
MBOX = (
    "From owner@example.com Mon Mar 15 09:00:00 2021\r\n"
    "From: Sam Owner <owner@example.com>\r\n"
    "To: Jamie Ex <jamie@example.com>\r\n"
    "Subject: re: dinner\r\n"
    "Date: Mon, 15 Mar 2021 09:00:00 +0000\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n"
    "\r\n"
    "Sounds good, see you at seven.\r\n"
    "> you free tonight?\r\n"
    "-- \r\n"
    "Sam | sent from my phone\r\n"
    "\r\n"
    "From jamie@example.com Sun Mar 14 20:30:00 2021\r\n"
    "From: Jamie Ex <jamie@example.com>\r\n"
    "To: Sam Owner <owner@example.com>\r\n"
    "Subject: dinner\r\n"
    "Date: Sun, 14 Mar 2021 20:30:00 +0000\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n"
    "\r\n"
    "you free tonight? i miss you\r\n"
    "\r\n"
    "From jamie@example.com Tue Mar 16 12:00:00 2021\r\n"
    "From: Jamie Ex <jamie@example.com>\r\n"
    "To: Sam Owner <owner@example.com>\r\n"
    "Subject: last word\r\n"
    "Date: Tue, 16 Mar 2021 12:00:00 +0000\r\n"
    "Content-Type: text/html; charset=utf-8\r\n"
    "\r\n"
    "<html><body><p>take <b>care</b> of yourself</p></body></html>\r\n"
)

# A single standalone .eml from the ex, body has a quoted line to strip.
EML = (
    "From: Jamie Ex <jamie@example.com>\r\n"
    "To: Sam Owner <owner@example.com>\r\n"
    "Subject: one more thing\r\n"
    "Date: Wed, 17 Mar 2021 08:15:00 +0000\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n"
    "\r\n"
    "left my charger at your place\r\n"
    "> ok bye\r\n"
)


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data.encode("utf-8"))
    return str(p)


def test_mbox_counts_body_and_order(tmp_path):
    path = _write(tmp_path, "inbox.mbox", MBOX)
    msgs = mail.parse(path, target="Jamie")

    # three non-empty bodies
    assert len(msgs) == 3

    # text/plain extracted; quoted ">" line and "-- " signature stripped
    owner_msg = next(m for m in msgs if m.sender == "Sam Owner")
    assert owner_msg.text == "Sounds good, see you at seven."
    assert ">" not in owner_msg.text
    assert "sent from my phone" not in owner_msg.text

    # text/html fallback stripped of tags
    assert any("take care of yourself" in m.text for m in msgs)

    # ascending ts order despite the file being out of order
    tss = [m.ts for m in msgs]
    assert tss == sorted(tss)
    assert all(m.ts.tzinfo is not None for m in msgs)


def test_mbox_direction_by_target(tmp_path):
    path = _write(tmp_path, "inbox.mbox", MBOX)
    msgs = mail.parse(path, target="Jamie")

    # ex (Jamie) → "in"; owner (Sam) → "out"
    by_sender = {m.sender for m in msgs}
    assert "Jamie Ex" in by_sender and "Sam Owner" in by_sender
    for m in msgs:
        if m.sender == "Jamie Ex":
            assert m.direction == "in"
        if m.sender == "Sam Owner":
            assert m.direction == "out"


def test_target_matches_email_address(tmp_path):
    # target given as an email address rather than a display name
    path = _write(tmp_path, "inbox.mbox", MBOX)
    msgs = mail.parse(path, target="jamie@example.com")
    jamie = [m for m in msgs if m.sender == "Jamie Ex"]
    assert jamie and all(m.direction == "in" for m in jamie)


def test_single_eml(tmp_path):
    path = _write(tmp_path, "note.eml", EML)
    msgs = mail.parse(path, target="Jamie")
    assert len(msgs) == 1
    assert msgs[0].text == "left my charger at your place"
    assert msgs[0].direction == "in"
    assert msgs[0].sender == "Jamie Ex"
