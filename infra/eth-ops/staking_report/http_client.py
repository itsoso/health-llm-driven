import json
from typing import Any
from urllib.request import Request, urlopen


def get_json(url: str, timeout: float = 5) -> Any:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP status {response.status}")
        return json.load(response)


def post_json(url: str, payload: dict[str, Any], timeout: float = 5) -> Any:
    body = json.dumps(payload).encode()
    request = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP status {response.status}")
        return json.load(response)
