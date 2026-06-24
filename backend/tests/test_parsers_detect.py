"""Format auto-detection sniffing each fixture to the right parser."""
import os

from app.ingestion.parsers.detect import detect_format

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_detect_imessage_sqlite_magic():
    assert detect_format(os.path.join(FIX, "sms.db")) == "imessage"


def test_detect_instagram_json():
    p = os.path.join(
        FIX, "instagram", "your_instagram_activity", "messages",
        "inbox", "ex_thread", "message_1.json",
    )
    assert detect_format(p) == "instagram"


def test_detect_whatsapp_ios_header():
    assert detect_format(os.path.join(FIX, "whatsapp_ios_chat.txt")) == "whatsapp"


def test_detect_whatsapp_android_header():
    assert detect_format(os.path.join(FIX, "whatsapp_android_chat.txt")) == "whatsapp"


def test_detect_sms_xml_root():
    assert detect_format(os.path.join(FIX, "sms_backup.xml")) == "sms"


def test_detect_wechat_text_export():
    assert detect_format(os.path.join(FIX, "wechat_export.txt")) == "wechat"


def test_detect_plaintext_fallback():
    assert detect_format(os.path.join(FIX, "plain_paste.txt")) == "plaintext"
