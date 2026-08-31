#!/usr/bin/env python3
"""Path-sensitive live LLM regression gate.

The regular synthesis gate is zero-cost and runs on every CI pass. This gate is
also zero-cost: it only detects whether a change touches high-risk LLM, prompt,
or orchestrator surfaces. If it does, CI must carry explicit evidence that the
live LLM regression suite was run.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
from pathlib import Path
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
CONFIRMATION_ENV = "HARNESS_LIVE_LLM_EVAL_CONFIRMED"
CONFIRMATION_TARGET_ENV = "HARNESS_LIVE_LLM_EVAL_TARGET_SHA"
LIVE_GATE_COMMAND = "python scripts/harness_llm_regression_gate.py --include-live-llm"

HIGH_RISK_RULES: tuple[tuple[str, str], ...] = (
    ("backend/app/orchestrator/**", "orchestrator runtime"),
    ("backend/app/api/orchestrator.py", "orchestrator runtime"),
    ("backend/app/services/agent_executor.py", "agent executor runtime"),
    ("backend/app/services/tool_schema_registry.py", "tool schema runtime"),
    ("backend/app/services/llm/**", "LLM service/runtime"),
    ("backend/app/services/*llm*.py", "LLM service/runtime"),
    ("backend/app/api/admin_llm.py", "LLM service/runtime"),
    ("backend/app/api/llm_usage.py", "LLM service/runtime"),
    ("backend/app/api/user_llm_preference.py", "LLM service/runtime"),
    ("backend/skills/**", "runtime skill/prompt"),
    ("backend/eval/**", "LLM/eval harness"),
    ("scripts/harness_llm_regression_gate.py", "LLM/eval harness"),
)

TRUTHY = {"1", "true", "yes", "y", "on"}


def _normalize_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _matches(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(f"{prefix}/")
    return fnmatch.fnmatchcase(path, pattern)


def _match_reason(path: str) -> str | None:
    for pattern, reason in HIGH_RISK_RULES:
        if _matches(pattern, path):
            return reason
    return None


def _is_confirmed(env: dict[str, str]) -> bool:
    confirmation = env.get(CONFIRMATION_ENV, "").strip().lower()
    target_sha = (
        env.get(CONFIRMATION_TARGET_ENV, "").strip()
        or env.get("GITHUB_SHA", "").strip()
    ).lower()
    if target_sha:
        return confirmation == target_sha
    return confirmation in TRUTHY


def _default_base_ref(env: dict[str, str]) -> str:
    if env.get("HARNESS_CHANGE_BASE_REF"):
        return env["HARNESS_CHANGE_BASE_REF"]
    if env.get("GITHUB_BASE_REF"):
        return f"origin/{env['GITHUB_BASE_REF']}"
    return "HEAD^"


def _changed_paths_from_git(base_ref: str, head_ref: str) -> tuple[list[str], list[str]]:
    if not base_ref or set(base_ref) == {"0"}:
        base_ref = "HEAD^"
    cmd = ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return [], [result.stderr.strip() or f"git diff failed for {base_ref}...{head_ref}"]
    return [line for line in result.stdout.splitlines() if line.strip()], []


def evaluate_paths(paths: Iterable[str], *, env: dict[str, str]) -> dict[str, object]:
    changed_paths = sorted({_normalize_path(path) for path in paths if _normalize_path(path)})
    matched_paths = [
        {"path": path, "reason": reason}
        for path in changed_paths
        if (reason := _match_reason(path)) is not None
    ]
    live_required = bool(matched_paths)
    confirmed = _is_confirmed(env)
    expected_confirmation = (
        env.get(CONFIRMATION_TARGET_ENV, "").strip()
        or env.get("GITHUB_SHA", "").strip()
        or None
    )
    status = "passed" if not live_required or confirmed else "failed"
    next_steps = ""
    if live_required and not confirmed:
        next_steps = (
            f"Run `{LIVE_GATE_COMMAND}` and preserve the run evidence, then set "
            f"the repository variable with `gh variable set {CONFIRMATION_ENV} "
            '--body "$(git rev-parse HEAD)"` before pushing that exact commit.'
        )
    return {
        "status": status,
        "live_llm_required": live_required,
        "confirmed": confirmed,
        "confirmation_env": CONFIRMATION_ENV,
        "expected_confirmation": expected_confirmation,
        "changed_paths": changed_paths,
        "matched_paths": matched_paths,
        "next_steps": next_steps,
        "errors": [],
    }


def _print_text(payload: dict[str, object]) -> None:
    print(
        "LLM live-change regression gate: "
        f"{payload['status']} (live_llm_required={payload['live_llm_required']}, "
        f"confirmed={payload['confirmed']})"
    )
    for match in payload["matched_paths"]:  # type: ignore[index]
        print(f"  [LIVE] {match['path']}: {match['reason']}")
    for error in payload["errors"]:  # type: ignore[index]
        print(f"  [ERROR] {error}")
    if payload["next_steps"]:
        print(f"  next: {payload['next_steps']}")


def main(
    argv: list[str] | None = None,
    *,
    env: dict[str, str] | None = None,
    changed_paths_fn: Callable[[str, str], tuple[list[str], list[str]]] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Require live LLM evidence for high-risk LLM changes.")
    parser.add_argument("--path", action="append", help="Changed path. Repeatable; bypasses git diff.")
    parser.add_argument("--base-ref", help="Base ref for git diff when --path is omitted.")
    parser.add_argument("--head-ref", default="HEAD", help="Head ref for git diff when --path is omitted.")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    env_map = dict(os.environ if env is None else env)
    errors: list[str] = []
    if args.path:
        changed_paths = args.path
    else:
        base_ref = args.base_ref or _default_base_ref(env_map)
        changed_paths, errors = (changed_paths_fn or _changed_paths_from_git)(base_ref, args.head_ref)

    payload = evaluate_paths(changed_paths, env=env_map)
    if errors:
        payload["status"] = "failed"
        payload["errors"] = errors
        if not payload["next_steps"]:
            payload["next_steps"] = "Fix change detection so this gate can inspect the modified paths."

    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text(payload)
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
