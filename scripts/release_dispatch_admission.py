#!/usr/bin/env python3
"""Admit only the first exact trusted workflow dispatch for a SHA and target.

This is a credential-free workflow race guard, not release authority. The shared
non-cancelling workflow concurrency group serializes runs; the lowest exact run
ID proceeds and every later duplicate fails before production credentials,
claims, vendor calls, or SSH.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request


REPOSITORY = "itsoso/health-llm-driven"
API = f"https://api.github.com/repos/{REPOSITORY}"
WORKFLOWS = {
    "trusted-release": {
        "id": 352404554,
        "path": ".github/workflows/trusted-release.yml",
        "title": "Trusted release",
        "targets": frozenset(
            {"validate", "transport", "backend", "backend-v1", "release", "testflight", "retained-testflight"}
        ),
    },
    "trusted-ota": {
        "id": 370218159,
        "path": ".github/workflows/trusted-ota.yml",
        "title": "Trusted OTA",
        "targets": frozenset({"validate", "publish"}),
    },
}
PENDING = frozenset({"queued", "in_progress", "requested", "waiting", "pending"})
TERMINALS = frozenset(
    {"success", "failure", "cancelled", "skipped", "timed_out", "action_required", "neutral", "stale", "startup_failure"}
)


class AdmissionError(RuntimeError):
    """A sanitized duplicate-admission rejection."""


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def read_token(stream=sys.stdin) -> str:
    token = stream.read(4097)
    if len(token) > 4096 or re.fullmatch(r"[A-Za-z0-9_.-]{1,4096}", token) is None:
        raise AdmissionError("GitHub read credential unavailable")
    return token


def get_json(path: str, token: str):
    if not path.startswith("/actions/workflows/") or "\r" in path or "\n" in path:
        raise AdmissionError("invalid bounded GitHub resource")
    request = urllib.request.Request(
        API + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "Cache-Control": "no-cache",
            "User-Agent": "reva-release-dispatch-admission/1.0",
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                if response.status != 200:
                    raise AdmissionError("GitHub run inventory unavailable")
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise AdmissionError("GitHub run inventory exceeds bound")
            return json.loads(raw, object_pairs_hook=unique)
        except AdmissionError:
            raise
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            raise AdmissionError("GitHub run inventory unavailable") from None
        except (json.JSONDecodeError, UnicodeError, ValueError, TypeError):
            raise AdmissionError("GitHub run inventory invalid") from None
    raise AssertionError("unreachable")


def _valid_state(run) -> bool:
    status, conclusion = run.get("status"), run.get("conclusion")
    if not isinstance(status, str) or (conclusion is not None and not isinstance(conclusion, str)):
        return False
    if status in PENDING:
        return conclusion is None
    return status == "completed" and conclusion in TERMINALS


def admit(*, workflow, target, sha, run_id, run_attempt, get_json):
    config = WORKFLOWS.get(workflow)
    if (
        config is None
        or target not in config["targets"]
        or not isinstance(sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", sha) is None
        or type(run_id) is not int
        or run_id <= 0
        or type(run_attempt) is not int
        or run_attempt != 1
    ):
        reason = "first attempt required" if type(run_attempt) is int and run_attempt != 1 else "invalid dispatch identity"
        raise AdmissionError(reason)

    path = (
        f"/actions/workflows/{config['id']}/runs?branch=main&event=workflow_dispatch"
        f"&head_sha={sha}&per_page=100"
    )
    try:
        value = get_json(path)
    except AdmissionError:
        raise
    except Exception:
        raise AdmissionError("GitHub run inventory unavailable") from None
    if (
        not isinstance(value, dict)
        or set(value) != {"total_count", "workflow_runs"}
        or type(value["total_count"]) is not int
        or not 0 < value["total_count"] <= 100
        or not isinstance(value["workflow_runs"], list)
        or value["total_count"] != len(value["workflow_runs"])
    ):
        raise AdmissionError("GitHub run inventory incomplete")

    expected_names = {f"{config['title']} · {item} · {sha}" for item in config["targets"]}
    current = []
    exact = []
    wanted_name = f"{config['title']} · {target} · {sha}"
    for run in value["workflow_runs"]:
        if (
            not isinstance(run, dict)
            or type(run.get("id")) is not int
            or run["id"] <= 0
            or run.get("workflow_id") != config["id"]
            or run.get("path") != config["path"]
            or run.get("head_sha") != sha
            or run.get("head_branch") != "main"
            or run.get("event") != "workflow_dispatch"
            or type(run.get("run_attempt")) is not int
            or run["run_attempt"] <= 0
            or run.get("name") not in expected_names
            or not _valid_state(run)
        ):
            raise AdmissionError("GitHub run identity invalid")
        if run["id"] == run_id:
            current.append(run)
        if run["name"] == wanted_name:
            exact.append(run)

    if len(current) != 1 or current[0]["run_attempt"] != run_attempt or current[0]["name"] != wanted_name:
        raise AdmissionError("current dispatch identity missing or ambiguous")
    if current[0]["status"] not in PENDING:
        raise AdmissionError("current dispatch is not active")
    if any(run["id"] < run_id for run in exact):
        raise AdmissionError("prior exact dispatch exists")
    return {"state": "ADMITTED", "workflow": workflow, "target": target, "sha": sha, "run_id": run_id}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", choices=tuple(WORKFLOWS), required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--token-stdin", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.token_stdin:
            raise AdmissionError("explicit stdin credential required")
        token = read_token()
        result = admit(
            workflow=args.workflow,
            target=args.target,
            sha=args.sha,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            get_json=lambda path: get_json(path, token),
        )
    except AdmissionError as error:
        print(f"release dispatch admission: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
