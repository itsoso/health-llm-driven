from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from staking_report.telegram import delivery_key  # noqa: E402


def test_delivery_key_does_not_expose_chat_id() -> None:
    key = delivery_key("2026-07-22", "123456")
    assert key.startswith("telegram:daily:2026-07-22:")
    assert "123456" not in key
