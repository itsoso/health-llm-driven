from typing import Any

from .models import AmountResult


def confirmed_builder_payment(
    fee_recipient: str,
    transactions: list[dict[str, Any]],
    relay_evidence: dict[str, Any] | None,
) -> AmountResult:
    if not relay_evidence:
        return AmountResult(None, False, "mev_unknown")
    expected = relay_evidence.get("payment_tx_hash")
    for tx in transactions:
        if tx.get("hash") == expected and str(tx.get("to", "")).lower() == fee_recipient.lower():
            return AmountResult(int(tx["value"], 16), True)
    return AmountResult(None, False, "mev_evidence_mismatch")
