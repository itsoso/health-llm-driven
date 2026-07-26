from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mobile-sim-screenshots.sh"


def read_script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_capture_uses_canonical_tab_routes_for_today_chat_and_record() -> None:
    script = read_script()

    assert 'capture "01-today" "/(tabs)/today"' in script
    assert 'capture "02-chat" "/(tabs)/chat"' in script
    assert 'capture "03-record" "/(tabs)/record"' in script
    assert 'capture "01-today" "/"' not in script
    assert 'capture "02-chat" "/chat"' not in script
    assert 'capture "03-record" "/record"' not in script


def test_manifest_records_the_same_canonical_routes_as_capture() -> None:
    script = read_script()

    assert '("01-today", "/(tabs)/today")' in script
    assert '("02-chat", "/(tabs)/chat")' in script
    assert '("03-record", "/(tabs)/record")' in script
