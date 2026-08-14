#!/usr/bin/env python3
"""Prove the active interpreter exactly matches a compiled requirements lock."""

from __future__ import annotations

import importlib.metadata
import re
import sys
from pathlib import Path


EXACT_REQUIREMENT = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^;\\\s]+)\s*\\?"
)
# ``python -m venv`` seeds pip; ensurepip/platform variants can also seed these
# two packaging tools. Application dependencies must all be present in the lock.
BOOTSTRAP_DISTRIBUTIONS = frozenset({"pip", "setuptools", "wheel"})


def _canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def verify_lock(lock_path: Path) -> list[str]:
    expected: dict[str, tuple[str, str]] = {}
    errors: list[str] = []
    for line_number, raw_line in enumerate(
        lock_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line or raw_line[0].isspace() or raw_line.startswith(("#", "--")):
            continue
        match = EXACT_REQUIREMENT.fullmatch(raw_line)
        if match is None:
            errors.append(
                f"line {line_number}: unsupported lock requirement: {raw_line}"
            )
            continue
        name = match.group("name")
        canonical_name = _canonical_name(name)
        if canonical_name in expected:
            errors.append(f"line {line_number}: duplicate lock requirement: {name}")
            continue
        expected[canonical_name] = (name, match.group("version"))

    if not expected:
        errors.append("lock contains no exact requirements")
    installed: dict[str, tuple[str, str]] = {}
    for distribution in importlib.metadata.distributions():
        raw_name = distribution.metadata.get("Name")
        if not raw_name:
            errors.append("installed distribution has no Name metadata")
            continue
        canonical_name = _canonical_name(str(raw_name))
        version = str(distribution.version)
        prior = installed.get(canonical_name)
        if prior is not None:
            errors.append(
                f"{canonical_name}: multiple installed distributions "
                f"({prior[1]}, {version})"
            )
            continue
        installed[canonical_name] = (str(raw_name), version)

    for canonical_name, (name, version) in expected.items():
        actual = installed.get(canonical_name)
        if actual is None:
            errors.append(f"{name}: missing; expected={version}")
        elif actual[1] != version:
            errors.append(f"{name}: installed={actual[1]}; expected={version}")

    for canonical_name, (name, version) in installed.items():
        if (
            canonical_name not in expected
            and canonical_name not in BOOTSTRAP_DISTRIBUTIONS
        ):
            errors.append(f"{name}: installed={version}; not present in lock")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} REQUIREMENTS_LOCK", file=sys.stderr)
        return 2
    lock_path = Path(sys.argv[1])
    try:
        errors = verify_lock(lock_path)
    except OSError as exc:
        print(f"locked requirements verification failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print(
            "locked requirements verification failed:\n" + "\n".join(errors),
            file=sys.stderr,
        )
        return 1
    package_count = sum(
        1
        for line in lock_path.read_text(encoding="utf-8").splitlines()
        if line and not line[0].isspace() and not line.startswith(("#", "--"))
    )
    print(f"LOCKED_REQUIREMENTS_OK packages={package_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
