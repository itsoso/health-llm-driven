#!/usr/bin/env python3
"""Prove an OTA source is clean and runtime-equivalent to target main."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


RUNTIME_PATHS = ("mobile", "packages/shared")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _resolve_commit(repo: Path, ref: str) -> str:
    value = _git(repo, "rev-parse", f"{ref}^{{commit}}")
    if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeError(f"invalid commit resolved for {ref}")
    return value


def _runtime_tree_digest(repo: Path, commit: str) -> str:
    listing = _git(
        repo,
        "ls-tree",
        "-r",
        "--full-tree",
        commit,
        "--",
        *RUNTIME_PATHS,
    )
    return hashlib.sha256((listing + "\n").encode()).hexdigest()


def inspect_source(
    repo: Path,
    source: str,
    main: str,
    *,
    allow_divergence: bool = False,
    allow_dirty: bool = False,
) -> dict[str, str | bool]:
    source_sha = _resolve_commit(repo, source)
    main_sha = _resolve_commit(repo, main)
    dirty = _git(
        repo,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        *RUNTIME_PATHS,
    )
    if dirty and not allow_dirty:
        paths = "\n".join(dirty.splitlines()[:5])
        raise RuntimeError(f"uncommitted mobile/shared paths:\n{paths}")

    source_digest = _runtime_tree_digest(repo, source_sha)
    main_digest = _runtime_tree_digest(repo, main_sha)
    equivalent = source_digest == main_digest
    if not equivalent and not allow_divergence:
        raise RuntimeError(
            "mobile/shared runtime trees differ between source HEAD and origin/main"
        )
    return {
        "source_commit_sha": source_sha,
        "main_commit_sha": main_sha,
        "release_commit_sha": main_sha if equivalent else source_sha,
        "mobile_tree_digest": source_digest,
        "main_advanced": source_sha != main_sha,
        "runtime_equivalent": equivalent,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source", default="HEAD")
    parser.add_argument("--main", default="origin/main")
    parser.add_argument("--allow-divergence", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--format", choices=("json", "shell"), default="json")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = inspect_source(
            args.repo,
            args.source,
            args.main,
            allow_divergence=args.allow_divergence,
            allow_dirty=args.allow_dirty,
        )
    except RuntimeError as exc:
        print(f"OTA source guard rejected: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, sort_keys=True))
    else:
        for key, value in result.items():
            rendered = "1" if value is True else "0" if value is False else value
            print(f"{key.upper()}={rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
