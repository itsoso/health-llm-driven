from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from staking_report.exchange import parse_rate  # noqa: E402


def test_parse_eth_cny_rate() -> None:
    rate = parse_rate({"ethereum": {"cny": 25000}}, "coingecko", datetime.now(timezone.utc))
    assert str(rate.eth_cny) == "25000"


@pytest.mark.parametrize("value", [0, -1, True, "nan", "inf"])
def test_invalid_rate_rejected(value) -> None:
    with pytest.raises(ValueError):
        parse_rate({"ethereum": {"cny": value}}, "provider", datetime.now(timezone.utc))
