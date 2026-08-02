from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from staking_report.beacon import parse_execution_payload, parse_validator  # noqa: E402


def test_parse_validator_requires_expected_index() -> None:
    payload = {"data": [{"index": "1331", "balance": "32003533000", "status": "active_ongoing", "validator": {"slashed": False}}]}
    result = parse_validator(payload, 1331)
    assert result.balance_gwei == 32_003_533_000
    assert result.status == "active_ongoing"
    assert result.slashed is False


def test_parse_execution_payload_maps_beacon_block() -> None:
    payload = {"data": {"message": {"slot": "42", "proposer_index": "1331", "body": {"execution_payload": {"block_number": "99", "block_hash": "0xabc"}}}}}
    result = parse_execution_payload(payload, 1331)
    assert result.slot == 42
    assert result.block_number == 99


def test_other_validator_block_is_excluded() -> None:
    payload = {"data": {"message": {"slot": "42", "proposer_index": "7", "body": {"execution_payload": {"block_number": "99", "block_hash": "0xabc"}}}}}
    assert parse_execution_payload(payload, 1331) is None
