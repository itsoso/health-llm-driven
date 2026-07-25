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

import yaml


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


def run_agent_trajectory_contract_gate() -> dict[str, Any]:
    """Validate stateful task contracts without an LLM or production data."""
    from app.services.agent_kernel.goal_spec import compile_goal_spec
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.types import (
        ActionableReference,
        AgentEnvelope,
        ExecutionContext,
    )

    dataset_path = BACKEND / "eval" / "datasets" / "agent_trajectories.yaml"
    dataset = yaml.safe_load(dataset_path.read_text(encoding="utf-8")) or {}
    failed_cases: list[dict[str, Any]] = []
    cases = dataset.get("cases") or []
    for case in cases:
        context = ExecutionContext.for_test(user_id=1, channel="eval")
        envelope = AgentEnvelope(user_id=1, channel="eval", text=case["user"])
        intent = build_intent_frame(envelope, context)
        references = tuple(
            ActionableReference(
                kind=item["kind"],
                source_message_id=item.get("source_message_id"),
                data=item.get("data") or {},
            )
            for item in case.get("prior_actionable") or []
        )
        goal = compile_goal_spec(
            envelope=envelope,
            context=context,
            intent=intent,
            actionable_references=references,
        )
        expected = case.get("expected") or {}
        actual = {
            "goal_kind": goal.kind,
            "domain": goal.domain,
            "operation": goal.operation,
            "target_date": goal.target_date,
            "target_meal_types": list(goal.target_meal_types),
            "target_record_type": goal.target_record_type,
            "target_values": dict(goal.target_values),
            "requires_lookup": goal.requires_lookup,
            "requires_verification": goal.requires_verification,
            "prohibited_operations": list(goal.prohibited_operations),
            "clarification": goal.requires_clarification,
        }
        mismatch = {
            key: {"expected": value, "actual": actual.get(key)}
            for key, value in expected.items()
            if actual.get(key) != value
        }
        if mismatch:
            failed_cases.append({"case_id": case.get("id"), "mismatch": mismatch})
    return {
        "status": "failed" if failed_cases else "passed",
        "total_cases": len(cases),
        "failed_cases": failed_cases,
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
    try:
        trajectory_contract = run_agent_trajectory_contract_gate()
    except Exception as exc:  # noqa: BLE001 - a broken gate must fail loudly in its report
        trajectory_contract = {
            "status": "failed",
            "total_cases": 0,
            "failed_cases": [{"case_id": "__gate__", "error": f"{type(exc).__name__}: {exc}"}],
        }
    status = (
        "failed"
        if failed_suites or errors or trajectory_contract["status"] != "passed"
        else "passed"
    )
    suite_names = [report.suite for report in reports] + [error["suite"] for error in errors]
    return {
        "status": status,
        "llm_cost": "possible" if any(suite in LIVE_LLM_SUITES for suite in suite_names) else "none",
        "suites": [_report_to_dict(report) for report in reports],
        "failed_suites": failed_suites,
        "errors": errors,
        "trajectory_contract": trajectory_contract,
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
    trajectory = payload["trajectory_contract"]
    mark = "OK" if trajectory["status"] == "passed" else "FAIL"
    print(
        f"  [{mark}] agent_trajectory_contract: "
        f"{trajectory['total_cases'] - len(trajectory['failed_cases'])}/"
        f"{trajectory['total_cases']} pass"
    )


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
