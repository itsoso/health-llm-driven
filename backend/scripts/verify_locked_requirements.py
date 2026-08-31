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

# Packages that must not survive a lock transition even when pip reuses the
# existing production venv. ChromaDB has no patched release for
# CVE-2026-45830/45831/45833, and its legacy runtime is disabled.
FORBIDDEN_INSTALLED_PACKAGES = ("chromadb", "chroma-hnswlib")


def _normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def verify_lock(
    lock_path: Path,
    *,
    sanitize_forbidden_packages: bool = False,
) -> list[str]:
    expected: list[tuple[str, str]] = []
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
        expected.append((match.group("name"), match.group("version")))

    if not expected:
        errors.append("lock contains no exact requirements")
    for name, version in expected:
        if (
            sanitize_forbidden_packages
            and _normalize_package_name(name) in FORBIDDEN_INSTALLED_PACKAGES
        ):
            continue
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"{name}: missing; expected={version}")
            continue
        if installed != version:
            errors.append(f"{name}: installed={installed}; expected={version}")
    for name in FORBIDDEN_INSTALLED_PACKAGES:
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        errors.append(
            f"{name}: forbidden installed package; installed={installed}"
        )
    return errors


def main() -> int:
    args = sys.argv[1:]
    sanitize_forbidden_packages = False
    if args[:1] == ["--sanitize-forbidden-packages"]:
        sanitize_forbidden_packages = True
        args = args[1:]
    if len(args) != 1:
        print(
            f"usage: {sys.argv[0]} "
            "[--sanitize-forbidden-packages] REQUIREMENTS_LOCK",
            file=sys.stderr,
        )
        return 2
    lock_path = Path(args[0])
    try:
        errors = verify_lock(
            lock_path,
            sanitize_forbidden_packages=sanitize_forbidden_packages,
        )
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
