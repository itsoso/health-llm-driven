#!/usr/bin/env python3
"""Read one bounded GitHub Actions resource with atomic, limited retries."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable


ATTEMPTS = 3
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


class ReadError(RuntimeError):
    """A read-only GitHub request exhausted its bounded attempts."""


def _command(repository: str, run_id: int | None, resource: str) -> list[str]:
    if not REPOSITORY_RE.fullmatch(repository):
        raise ValueError("repository must be owner/name")
    if resource == "runs":
        if run_id is not None:
            raise ValueError("runs resource does not accept run_id")
        return [
            "gh",
            "run",
            "list",
            "--repo",
            repository,
            "--workflow",
            "CI",
            "--branch",
            "main",
            "--status",
            "success",
            "--limit",
            "12",
            "--json",
            "databaseId,headSha,headBranch,workflowName,status,conclusion,attempt",
        ]
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("run_id must be a positive integer")
    if resource == "jobs":
        suffix = "jobs?per_page=100"
    elif resource == "logs":
        suffix = "logs"
    else:
        raise ValueError("resource must be jobs, logs or runs")
    return [
        "gh",
        "api",
        "-H",
        "Accept: application/vnd.github+json",
        f"repos/{repository}/actions/runs/{run_id}/{suffix}",
    ]


def read_action_resource(
    *,
    repository: str,
    run_id: int | None,
    resource: str,
    output: Path,
    run: Callable[..., object] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Retry one read inside the current workflow attempt and replace atomically."""

    command = _command(repository, run_id, resource)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    last_return_code: int | None = None

    for attempt in range(1, ATTEMPTS + 1):
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w+b",
                prefix=f".{output.name}.",
                dir=output.parent,
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                result = run(
                    command,
                    stdout=stream,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                last_return_code = int(getattr(result, "returncode"))
                stream.flush()
                os.fsync(stream.fileno())
            if last_return_code == 0 and temporary.stat().st_size > 0:
                os.replace(temporary, output)
                return
        except OSError:
            last_return_code = None
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

        if attempt < ATTEMPTS:
            sleep(float(2 ** (attempt - 1)))

    suffix = "unknown exit" if last_return_code is None else f"exit {last_return_code}"
    raise ReadError(
        f"GitHub Actions {resource} read failed after {ATTEMPTS} attempts ({suffix})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--resource", choices=("jobs", "logs", "runs"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        read_action_resource(
            repository=args.repository,
            run_id=args.run_id,
            resource=args.resource,
            output=args.output,
        )
    except (ReadError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
