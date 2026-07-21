#!/usr/bin/env python3
"""Fail on high-confidence secrets in Git-tracked files."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_NAMES = re.compile(r"(^|/)\.env(?:\.backup.*|\.production|\.staging|\.local)?$")
SECRET_PATTERNS = (
    ("private key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("Aliyun access key", re.compile(rb"\bLTAI[A-Za-z0-9]{12,}\b")),
    ("GitHub token", re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("OpenAI-style key", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b")),
)
PLACEHOLDER_MARKERS = (
    b"example",
    b"placeholder",
    b"must-not-leak",
    b"secret",
    b"test",
    b"dummy",
    b"your-",
)


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def scan(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for relative in paths:
        if SENSITIVE_NAMES.search(relative) and not relative.endswith(".example"):
            findings.append(f"tracked runtime secret file: {relative}")
            continue
        path = ROOT / relative
        try:
            data = path.read_bytes()
        except (FileNotFoundError, IsADirectoryError, PermissionError):
            continue
        if b"\0" in data[:8192]:
            continue
        for label, pattern in SECRET_PATTERNS:
            matches = pattern.findall(data)
            if any(
                not any(marker in match.lower() for marker in PLACEHOLDER_MARKERS)
                for match in matches
            ):
                findings.append(f"{label}: {relative}")
    return findings


def main() -> int:
    findings = scan(tracked_files())
    if findings:
        print("Secret scan failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Secret scan passed (tracked files, high-confidence rules).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
