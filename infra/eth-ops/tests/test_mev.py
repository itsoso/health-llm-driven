from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from staking_report.mev import confirmed_builder_payment  # noqa: E402


def test_mev_requires_explicit_relay_evidence() -> None:
    assert confirmed_builder_payment("0xfee", [{"to": "0xfee", "value": "0x64"}], None).complete is False
    result = confirmed_builder_payment("0xfee", [{"hash": "0x1", "to": "0xfee", "value": "0x64"}], {"payment_tx_hash": "0x1"})
    assert result.wei == 100 and result.complete is True
