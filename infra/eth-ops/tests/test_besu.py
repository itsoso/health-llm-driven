from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from staking_report.besu import parse_rpc_response  # noqa: E402


def test_rpc_response_validates_id() -> None:
    assert parse_rpc_response({"jsonrpc": "2.0", "id": 3, "result": {"number": "0x1"}}, 3)["number"] == "0x1"


def test_rpc_error_is_not_swallowed() -> None:
    with pytest.raises(RuntimeError, match="RPC error"):
        parse_rpc_response({"jsonrpc": "2.0", "id": 3, "error": {"code": -1, "message": "failed"}}, 3)


def test_wrong_rpc_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="response id"):
        parse_rpc_response({"jsonrpc": "2.0", "id": 4, "result": {}}, 3)
