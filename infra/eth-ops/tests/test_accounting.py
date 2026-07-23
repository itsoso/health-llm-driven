from decimal import Decimal
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from staking_report.accounting import (  # noqa: E402
    calculate_priority_fees,
    consensus_delta_gwei,
    sum_known_amounts,
    wei_to_eth,
)
from staking_report.models import AmountResult  # noqa: E402


def test_wei_to_eth_preserves_decimal_precision() -> None:
    assert wei_to_eth(1_234_567_890_123_456_789) == Decimal("1.234567890123456789")


def test_consensus_delta_supports_positive_and_negative_changes() -> None:
    assert consensus_delta_gwei(32_000_000_000, 32_003_526_000) == Decimal("0.003526")
    assert consensus_delta_gwei(32_003_526_000, 32_000_000_000) == Decimal("-0.003526")


def test_priority_fees_sum_effective_tip_per_receipt() -> None:
    block = {"baseFeePerGas": "0x64"}
    receipts = [
        {"gasUsed": "0x5208", "effectiveGasPrice": "0x78"},
        {"gasUsed": "0x2710", "effectiveGasPrice": "0x6e"},
    ]

    result = calculate_priority_fees(block, receipts)

    assert result.wei == 520_000
    assert result.complete is True


def test_priority_fee_never_becomes_negative() -> None:
    result = calculate_priority_fees(
        {"baseFeePerGas": "0x64"},
        [{"gasUsed": "0x5208", "effectiveGasPrice": "0x63"}],
    )

    assert result.wei == 0
    assert result.complete is True


def test_missing_receipt_is_incomplete_not_zero() -> None:
    result = calculate_priority_fees({"baseFeePerGas": "0x64"}, None)

    assert result.wei is None
    assert result.complete is False


def test_sum_known_amounts_refuses_false_complete_total() -> None:
    result = sum_known_amounts(
        AmountResult(wei=10, complete=True),
        AmountResult(wei=None, complete=False, reason="mev_unknown"),
    )

    assert result.wei == 10
    assert result.complete is False
    assert result.reason == "mev_unknown"
