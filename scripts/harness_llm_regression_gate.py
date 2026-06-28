#!/usr/bin/env python3
"""LLM synthesis regression gate.

Default mode is offline and zero-cost: it runs the synthesis invariant gold set
plus the representative health-agent rubric inventory. Live LLM suites stay
behind --include-live-llm so model/prompt changes have a cheap mandatory gate
and an explicit expensive gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DEFAULT_OFFLINE_SUITES = ("invariants", "health_agent_core")
LIVE_LLM_SUITES = ("orchestrator",)
DEFAULT_BASELINES = {
    "health_agent_core": "main",
    "orchestrator": "main",
}


def _baseline_for(suite: str, *, override: str | None, no_baseline: bool) -> str | None:
    if no_baseline:
        return None
    if override is not None:
        return override
    return DEFAULT_BASELINES.get(suite)


def _report_to_dict(report: Any) -> dict[str, Any]:
    return {
        "suite": report.suite,
        "total_cases": report.total_cases,
        "passed": report.passed,
        "failed": report.failed,
        "errored": report.errored,
        "avg_score": report.avg_score,
        "avg_latency_ms": report.avg_latency_ms,
        "regression": list(report.regression or []),
    }


def run_gate(
    suites: Iterable[str],
    *,
    baseline: str | None = None,
    no_baseline: bool = False,
    run_suite_fn: Callable[[str, str | None], Any] | None = None,
) -> dict[str, Any]:
    if run_suite_fn is None:
        from eval.runner import run_suite as run_suite_fn

    reports: list[Any] = []
    errors: list[dict[str, str]] = []
    for suite in suites:
        try:
            reports.append(run_suite_fn(suite, baseline=_baseline_for(suite, override=baseline, no_baseline=no_baseline)))
        except Exception as exc:  # noqa: BLE001 - gate should report all suite failures, not hide them
            errors.append({"suite": suite, "error": f"{type(exc).__name__}: {exc}"})

    failed_suites = [
        report.suite for report in reports
        if report.failed or report.errored or report.regression
    ]
    status = "failed" if failed_suites or errors else "passed"
    suite_names = [report.suite for report in reports] + [error["suite"] for error in errors]
    return {
        "status": status,
        "llm_cost": "possible" if any(suite in LIVE_LLM_SUITES for suite in suite_names) else "none",
        "suites": [_report_to_dict(report) for report in reports],
        "failed_suites": failed_suites,
        "errors": errors,
    }


def _print_text(payload: dict[str, Any]) -> None:
    print(f"LLM synthesis regression gate: {payload['status']} (llm_cost={payload['llm_cost']})")
    for report in payload["suites"]:
        mark = "OK" if not (report["failed"] or report["errored"] or report["regression"]) else "FAIL"
        line = (
            f"  [{mark}] {report['suite']}: {report['passed']}/{report['total_cases']} pass "
            f"avg={report['avg_score']}"
        )
        if report["regression"]:
            line += f" regressions={report['regression']}"
        print(line)
    for error in payload["errors"]:
        print(f"  [ERROR] {error['suite']}: {error['error']}")


def main(argv: list[str] | None = None, *, run_suite_fn: Callable[[str, str | None], Any] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run no-cost LLM synthesis regression gates.")
    parser.add_argument(
        "--suite",
        action="append",
        help="Suite to run. Repeatable. Defaults to invariants + health_agent_core.",
    )
    parser.add_argument(
        "--include-live-llm",
        action="store_true",
        help="Also run live LLM synthesis suites such as orchestrator.",
    )
    parser.add_argument("--baseline", help="Override baseline name for baseline-backed suites.")
    parser.add_argument("--no-baseline", action="store_true", help="Disable baseline comparison.")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    suites = tuple(args.suite or DEFAULT_OFFLINE_SUITES)
    if args.include_live_llm:
        suites = tuple(dict.fromkeys((*suites, *LIVE_LLM_SUITES)))

    payload = run_gate(suites, baseline=args.baseline, no_baseline=args.no_baseline, run_suite_fn=run_suite_fn)
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text(payload)
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
