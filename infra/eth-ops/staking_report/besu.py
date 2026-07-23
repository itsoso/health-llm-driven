from typing import Any

from .http_client import post_json


def parse_rpc_response(payload: dict[str, Any], request_id: int) -> Any:
    if payload.get("id") != request_id:
        raise ValueError("unexpected JSON-RPC response id")
    if "error" in payload:
        error = payload["error"]
        raise RuntimeError(f"RPC error {error.get('code')}: {error.get('message')}")
    if "result" not in payload:
        raise ValueError("JSON-RPC result missing")
    return payload["result"]


class BesuClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8545", timeout: float = 5) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self._request_id = 0

    def call(self, method: str, params: list[Any]) -> Any:
        self._request_id += 1
        request_id = self._request_id
        response = post_json(
            self.base_url,
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            self.timeout,
        )
        return parse_rpc_response(response, request_id)

    def block(self, block_number: int) -> dict[str, Any]:
        return self.call("eth_getBlockByNumber", [hex(block_number), True])

    def receipts(self, block_number: int) -> list[dict[str, Any]]:
        result = self.call("eth_getBlockReceipts", [hex(block_number)])
        if not isinstance(result, list):
            raise ValueError("receipt response must be a list")
        return result
