#!/usr/bin/env python3
"""Admit timing observation only for a complete backend pytest matrix."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


_BACKEND_JOB = re.compile(r"backend-test-balanced-(\d{2})")


def is_full_backend_run(payload: dict[str, Any], *, worker_count: int) -> bool:
    if type(worker_count) is not int or worker_count < 1:
        raise ValueError("worker_count must be a positive integer")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("jobs payload must contain a list")

    matched = [job for job in jobs if _BACKEND_JOB.fullmatch(str(job.get("name", "")))]
    if not matched:
        return False

    expected = {f"backend-test-balanced-{index:02d}" for index in range(1, worker_count + 1)}
    names = [str(job.get("name", "")) for job in matched]
    if len(names) != len(set(names)) or set(names) != expected:
        raise ValueError("incomplete backend timing matrix")
    if any(
        job.get("status") not in (None, "completed")
        or job.get("conclusion") != "success"
        for job in matched
    ):
        raise ValueError("timing observation requires a successful backend timing matrix")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs-json", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.jobs_json.read_text(encoding="utf-8"))
    eligible = is_full_backend_run(payload, worker_count=args.workers)
    with args.github_output.open("a", encoding="utf-8") as output:
        output.write(f"eligible={'true' if eligible else 'false'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
