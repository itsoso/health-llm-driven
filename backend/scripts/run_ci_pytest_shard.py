#!/usr/bin/env python3
"""Run each pytest file in a CI shard in a fresh Python process."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import fnmatch
import glob
from pathlib import Path
import subprocess
import sys


def _option_values(arguments: Sequence[str], option: str) -> list[str]:
    values: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument.startswith(f"{option}="):
            values.append(argument.split("=", 1)[1])
        elif argument == option and index + 1 < len(arguments):
            index += 1
            values.append(arguments[index])
        index += 1
    return values


def discover_test_files(
    inputs: Sequence[str],
    pytest_args: Sequence[str] = (),
) -> list[Path]:
    """Expand file, directory, and glob inputs into unique test files."""
    discovered: list[Path] = []
    seen: set[Path] = set()
    ignored_paths = [Path(value) for value in _option_values(pytest_args, "--ignore")]
    ignored_globs = _option_values(pytest_args, "--ignore-glob")

    for raw_input in inputs:
        matches = sorted(
            (Path(match) for match in glob.glob(raw_input, recursive=True)),
            key=lambda path: str(path),
        )
        if not matches and Path(raw_input).exists():
            matches = [Path(raw_input)]

        for match in matches:
            candidates = sorted(match.rglob("test_*.py")) if match.is_dir() else (match,)
            for candidate in candidates:
                is_test_file = (
                    candidate.is_file()
                    and candidate.name.startswith("test_")
                    and candidate.suffix == ".py"
                )
                is_ignored_path = any(
                    candidate == ignored or ignored in candidate.parents
                    for ignored in ignored_paths
                )
                is_ignored_glob = any(
                    fnmatch.fnmatch(str(candidate), pattern)
                    for pattern in ignored_globs
                )
                if (
                    is_test_file
                    and not is_ignored_path
                    and not is_ignored_glob
                    and candidate not in seen
                ):
                    discovered.append(candidate)
                    seen.add(candidate)

    return discovered


def build_pytest_commands(files: Sequence[Path], pytest_args: Sequence[str]) -> list[list[str]]:
    return [
        [sys.executable, "-m", "pytest", str(test_file), *pytest_args]
        for test_file in files
    ]


def run_test_files(
    files: Sequence[Path],
    pytest_args: Sequence[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> int:
    commands = build_pytest_commands(files, pytest_args)
    total = len(commands)

    for index, command in enumerate(commands, start=1):
        print(f"[ci-shard] {index}/{total} {command[3]}", flush=True)
        result = runner(command, check=False)
        if result.returncode != 0:
            return result.returncode

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--" not in arguments:
        print("usage: run_ci_pytest_shard.py <paths...> -- <pytest args...>", file=sys.stderr)
        return 2

    separator = arguments.index("--")
    path_inputs = arguments[:separator]
    pytest_args = arguments[separator + 1 :]
    files = discover_test_files(path_inputs, pytest_args)
    if not files:
        print(f"no test files found for inputs: {path_inputs}", file=sys.stderr)
        return 2

    print(f"[ci-shard] discovered {len(files)} test files", flush=True)
    return run_test_files(files, pytest_args)


if __name__ == "__main__":
    raise SystemExit(main())
