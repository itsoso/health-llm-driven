#!/usr/bin/env python3
"""Resolve one exact available iOS Simulator name or UDID from simctl JSON."""

from __future__ import annotations

import json
import sys
from typing import Any


def resolve_available_simulator(payload: dict[str, Any], requested: str) -> str:
    matches = [
        str(device.get("udid"))
        for runtime_devices in payload.get("devices", {}).values()
        for device in runtime_devices
        if device.get("isAvailable") is True
        and requested in {device.get("name"), device.get("udid")}
        and device.get("udid")
    ]
    if len(matches) != 1:
        raise ValueError("destination must match exactly one available iOS Simulator")
    return matches[0]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: resolve_ios_simulator.py <name-or-udid>", file=sys.stderr)
        return 2
    try:
        payload = json.load(sys.stdin)
        print(resolve_available_simulator(payload, argv[1]))
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
