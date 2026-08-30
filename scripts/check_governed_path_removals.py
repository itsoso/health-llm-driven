#!/usr/bin/env python3
"""Run filtered governance gates when staged removals hide their old paths."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / ".pre-commit-config.yaml"
CONFIG_RELATIVE = ".pre-commit-config.yaml"
SELF_RELATIVE = "scripts/check_governed_path_removals.py"
FULL_COVERAGE_ANCHORS = frozenset((CONFIG_RELATIVE, SELF_RELATIVE))
GOVERNED_HOOK_IDS = (
    "system-map",
    "dossier-consistency",
    "agent-skill-governance",
)
_HOOK_HEADER = re.compile(r"(?m)^      - id: ([^\s#]+)\s*$")
_VALID_STATUSES = frozenset("ADMTUXB")


class SentinelError(RuntimeError):
    """A fail-closed configuration or staged-diff error."""


def _hook_blocks(config: str) -> dict[str, str]:
    headers = list(_HOOK_HEADER.finditer(config))
    blocks: dict[str, str] = {}
    for index, header in enumerate(headers):
        hook_id = header.group(1)
        if hook_id in blocks:
            raise SentinelError(f"duplicate pre-commit hook id: {hook_id}")
        end = headers[index + 1].start() if index + 1 < len(headers) else len(config)
        blocks[hook_id] = config[header.end() : end]
    return blocks


def _required_field(block: str, hook_id: str, field: str) -> str:
    matches = re.findall(rf"(?m)^        {re.escape(field)}:\s*(.+?)\s*$", block)
    if len(matches) != 1:
        raise SentinelError(
            f"{hook_id} must define exactly one {field} field; found {len(matches)}"
        )
    return matches[0]


def _files_pattern(value: str, hook_id: str) -> re.Pattern[str]:
    if len(value) < 2 or not (value.startswith("'") and value.endswith("'")):
        raise SentinelError(f"{hook_id} files must use a single-quoted scalar")
    source = value[1:-1].replace("''", "'")
    try:
        pattern = re.compile(source)
    except re.error as exc:
        raise SentinelError(f"{hook_id} files regex is invalid: {exc}") from exc
    for required_path in (CONFIG_RELATIVE, SELF_RELATIVE):
        if pattern.search(required_path) is None:
            raise SentinelError(
                f"{hook_id} files must cover sentinel source: {required_path}"
            )
    return pattern


def _load_governed_hooks() -> list[tuple[str, list[str], re.Pattern[str]]]:
    try:
        config = CONFIG_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SentinelError(f"cannot read {CONFIG_RELATIVE}: {exc}") from exc
    blocks = _hook_blocks(config)
    hooks: list[tuple[str, list[str], re.Pattern[str]]] = []
    for hook_id in GOVERNED_HOOK_IDS:
        block = blocks.get(hook_id)
        if block is None:
            raise SentinelError(f"missing pre-commit hook: {hook_id}")
        entry_text = _required_field(block, hook_id, "entry")
        try:
            entry = shlex.split(entry_text)
        except ValueError as exc:
            raise SentinelError(f"{hook_id} entry is invalid: {exc}") from exc
        if not entry:
            raise SentinelError(f"{hook_id} entry must not be empty")
        pattern = _files_pattern(_required_field(block, hook_id, "files"), hook_id)
        hooks.append((hook_id, entry, pattern))
    return hooks


def _staged_changes() -> list[tuple[str, str]]:
    command = [
        "git",
        "diff",
        "--cached",
        "--name-status",
        "--no-renames",
        "-z",
        "--",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise SentinelError(f"git diff could not start: {exc}") from exc
    if completed.returncode != 0:
        detail = os.fsdecode(completed.stderr).strip() or "no diagnostic output"
        raise SentinelError(f"git diff exited {completed.returncode}: {detail}")

    fields = completed.stdout.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        raise SentinelError("git diff returned a malformed NUL-delimited record")

    changes: list[tuple[str, str]] = []
    for index in range(0, len(fields), 2):
        status = os.fsdecode(fields[index])
        path = os.fsdecode(fields[index + 1])
        if status not in _VALID_STATUSES or not path:
            raise SentinelError(
                f"git diff returned an unsupported staged record: {status!r}"
            )
        changes.append((status, path))
    return changes


def _run_required_gates(
    hooks: list[tuple[str, list[str], re.Pattern[str]]],
    changes: list[tuple[str, str]],
    *,
    all_filtered_hooks_ran: bool,
) -> int:
    if all_filtered_hooks_ran:
        return 0
    first_failure = 0
    for hook_id, entry, pattern in hooks:
        governed_deletion = any(
            status == "D" and pattern.search(path) is not None
            for status, path in changes
        )
        governed_non_deletion = any(
            status != "D" and pattern.search(path) is not None
            for status, path in changes
        )
        if not governed_deletion or governed_non_deletion:
            continue

        print(f"→ governed removal: {hook_id}", flush=True)
        try:
            completed = subprocess.run(entry, cwd=ROOT, check=False)
            returncode = completed.returncode
        except OSError as exc:
            print(f"{hook_id} could not start: {exc}", file=sys.stderr)
            returncode = 126
        if returncode != 0 and first_failure == 0:
            first_failure = returncode
    return first_failure


def _all_filtered_hooks_ran(pre_commit_paths: list[str]) -> bool:
    unexpected = sorted(set(pre_commit_paths) - FULL_COVERAGE_ANCHORS)
    if unexpected:
        raise SentinelError(
            "unexpected pre-commit path arguments: " + ", ".join(repr(x) for x in unexpected)
        )
    return bool(pre_commit_paths)


def main(argv: list[str] | None = None) -> int:
    pre_commit_paths = sys.argv[1:] if argv is None else argv
    try:
        hooks = _load_governed_hooks()
        changes = _staged_changes()
        all_filtered_hooks_ran = _all_filtered_hooks_ran(pre_commit_paths)
    except SentinelError as exc:
        print(f"governed-path-removals: {exc}", file=sys.stderr)
        return 2
    return _run_required_gates(
        hooks,
        changes,
        all_filtered_hooks_ran=all_filtered_hooks_ran,
    )


if __name__ == "__main__":
    raise SystemExit(main())
