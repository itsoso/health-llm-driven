from decimal import Decimal
from typing import Any

from .models import AmountResult


WEI_PER_ETH = Decimal(10**18)
GWEI_PER_ETH = Decimal(10**9)


def wei_to_eth(wei: int) -> Decimal:
    return Decimal(wei) / WEI_PER_ETH


def consensus_delta_gwei(start: int, end: int) -> Decimal:
    return Decimal(end - start) / GWEI_PER_ETH


def _rpc_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean is not an RPC quantity")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 16) if value.startswith("0x") else int(value)
    raise ValueError("invalid RPC quantity")


def calculate_priority_fees(
    block: dict[str, Any],
    receipts: list[dict[str, Any]] | None,
) -> AmountResult:
    if receipts is None:
        return AmountResult(None, False, "receipts_missing")
    base_fee = _rpc_int(block["baseFeePerGas"])
    total = 0
    for receipt in receipts:
        gas_used = _rpc_int(receipt["gasUsed"])
        effective_price = _rpc_int(receipt["effectiveGasPrice"])
        total += gas_used * max(0, effective_price - base_fee)
    return AmountResult(total, True)


def sum_known_amounts(*amounts: AmountResult) -> AmountResult:
    known_total = sum(item.wei for item in amounts if item.wei is not None)
    incomplete = next((item for item in amounts if not item.complete), None)
    return AmountResult(
        known_total,
        incomplete is None,
        incomplete.reason if incomplete else None,
    )
