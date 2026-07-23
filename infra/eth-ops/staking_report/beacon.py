from dataclasses import dataclass
from typing import Any

from .http_client import get_json


@dataclass(frozen=True)
class ValidatorState:
    index: int
    balance_gwei: int
    status: str
    slashed: bool


@dataclass(frozen=True)
class ProposedBlock:
    slot: int
    block_number: int
    block_hash: str


def parse_validator(payload: dict[str, Any], expected_index: int) -> ValidatorState:
    rows = payload.get("data") or []
    if len(rows) != 1 or int(rows[0]["index"]) != expected_index:
        raise ValueError("unexpected validator index")
    row = rows[0]
    return ValidatorState(
        expected_index,
        int(row["balance"]),
        str(row["status"]),
        bool(row["validator"]["slashed"]),
    )


def parse_execution_payload(payload: dict[str, Any], validator_index: int) -> ProposedBlock | None:
    message = payload["data"]["message"]
    if int(message["proposer_index"]) != validator_index:
        return None
    execution = message["body"]["execution_payload"]
    return ProposedBlock(int(message["slot"]), int(execution["block_number"]), execution["block_hash"])


class BeaconClient:
    def __init__(self, base_url: str = "http://127.0.0.1:5052", timeout: float = 5) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def validator(self, index: int, state: str = "head") -> ValidatorState:
        payload = get_json(
            f"{self.base_url}/eth/v1/beacon/states/{state}/validators?id={index}",
            self.timeout,
        )
        return parse_validator(payload, index)

    def block(self, block_id: str, validator_index: int) -> ProposedBlock | None:
        payload = get_json(f"{self.base_url}/eth/v2/beacon/blocks/{block_id}", self.timeout)
        return parse_execution_payload(payload, validator_index)
