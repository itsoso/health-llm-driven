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
AGENT_TRAJECTORY_DATASET = BACKEND / "eval" / "datasets" / "agent_trajectories.yaml"
AGENT_TRAJECTORY_GOLDENS = (
    BACKEND / "eval" / "fixtures" / "agent_trajectory_goldens.yaml"
)
REQUIRED_AGENT_GOLDEN_SCENARIOS = {
    "simple_water_write",
    "simple_fruit_write",
    "meal_context_reestimate",
    "uncertain_receipt_false_success",
    "duplicate_client_turn_side_effect",
    "idempotent_client_turn_replay",
    "read_only_delete_side_effect",
    "duplicate_same_record_side_effect",
    "missing_identity_receipt",
}
_FORBIDDEN_FIXTURE_KEYS = {
    "access_token",
    "base64",
    "content",
    "email",
    "file_name",
    "filename",
    "image_url",
    "message",
    "model_response",
    "phone",
    "prompt",
    "response",
    "source_message_id",
    "text",
    "token",
    "uri",
    "url",
    "user_id",
}
_FORBIDDEN_URI_PREFIXES = ("data:", "file://", "http://", "https://")


def run_agent_trajectory_contract_gate() -> dict[str, Any]:
    """Validate stateful task contracts without an LLM or production data."""
    from app.services.agent_kernel.goal_spec import compile_goal_spec
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.types import (
        ActionableReference,
        AgentEnvelope,
        ExecutionContext,
    )

    dataset = yaml.safe_load(AGENT_TRAJECTORY_DATASET.read_text(encoding="utf-8")) or {}
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


def _score_golden_trace(case: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    from eval.agent_trajectory_scorer import score_trajectory

    return score_trajectory(case, trace)


def _fixture_privacy_errors(value: Any, *, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key).strip().lower()
            child_path = f"{path}.{raw_key}"
            if key in _FORBIDDEN_FIXTURE_KEYS:
                errors.append(f"forbidden fixture key: {key} at {child_path}")
            errors.extend(_fixture_privacy_errors(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_fixture_privacy_errors(child, path=f"{path}[{index}]"))
    elif isinstance(value, str):
        normalized = value.lower()
        if any(prefix in normalized for prefix in _FORBIDDEN_URI_PREFIXES):
            errors.append(f"forbidden URI value at {path}")
    return errors


def run_agent_golden_trace_gate() -> dict[str, Any]:
    """Replay versioned good and bad traces through deterministic postconditions."""

    dataset = yaml.safe_load(
        AGENT_TRAJECTORY_DATASET.read_text(encoding="utf-8")
    ) or {}
    fixtures = yaml.safe_load(
        AGENT_TRAJECTORY_GOLDENS.read_text(encoding="utf-8")
    ) or {}
    cases_by_id = {
        str(case.get("id")): case
        for case in (dataset.get("cases") or [])
        if isinstance(case, dict) and case.get("id")
    }
    fixture_rows = fixtures.get("cases") or []
    failed_cases: list[dict[str, Any]] = []
    covered_scenarios: list[str] = []
    if fixtures.get("fixture_origin") != "synthetic":
        failed_cases.append(
            {
                "scenario": "__fixture__",
                "case_id": "",
                "mismatch": {"fixture": "fixture_origin must be synthetic"},
            }
        )
    for error in sorted(set(_fixture_privacy_errors(fixtures))):
        failed_cases.append(
            {
                "scenario": "__fixture__",
                "case_id": "",
                "mismatch": {"fixture": error},
            }
        )

    for fixture in fixture_rows:
        scenario = str(fixture.get("scenario") or "").strip()
        case_id = str(fixture.get("case_id") or "").strip()
        covered_scenarios.append(scenario)
        if not scenario or not fixture.get("history_ref"):
            failed_cases.append(
                {
                    "scenario": scenario or "__missing_scenario__",
                    "case_id": case_id,
                    "mismatch": {"fixture": "scenario and history_ref are required"},
                }
            )
            continue
        case = cases_by_id.get(case_id)
        if case is None:
            failed_cases.append(
                {
                    "scenario": scenario,
                    "case_id": case_id,
                    "mismatch": {"case_id": "unknown trajectory case"},
                }
            )
            continue

        expected_contract = fixture.get("expected_contract")
        if expected_contract is not None:
            if not isinstance(expected_contract, dict):
                failed_cases.append(
                    {
                        "scenario": scenario,
                        "case_id": case_id,
                        "mismatch": {"expected_contract": "must be an object"},
                    }
                )
                continue
            case = dict(case)
            case["expected"] = {
                **(case.get("expected") or {}),
                **expected_contract,
            }

        trace = dict(fixture.get("trace") or {})
        trace["case_id"] = case_id
        actual = _score_golden_trace(case, trace)
        expected = fixture.get("expected") or {}
        expected_passed = bool(expected.get("passed"))
        required_failures = set(expected.get("hard_failures") or [])
        actual_failures = set(actual.get("hard_failures") or [])
        mismatch: dict[str, Any] = {}
        if bool(actual.get("passed")) is not expected_passed:
            mismatch["passed"] = {
                "expected": expected_passed,
                "actual": bool(actual.get("passed")),
            }
        missing_failures = sorted(required_failures - actual_failures)
        if missing_failures:
            mismatch["missing_hard_failures"] = missing_failures
        if mismatch:
            failed_cases.append(
                {
                    "scenario": scenario,
                    "case_id": case_id,
                    "mismatch": mismatch,
                    "actual": actual,
                }
            )

    if len(set(covered_scenarios)) != len(covered_scenarios):
        failed_cases.append(
            {
                "scenario": "__fixture__",
                "case_id": "",
                "mismatch": {"scenario": "duplicate scenario id"},
            }
        )
    missing_scenarios = sorted(
        REQUIRED_AGENT_GOLDEN_SCENARIOS - set(covered_scenarios)
    )
    if missing_scenarios:
        failed_cases.append(
            {
                "scenario": "__fixture__",
                "case_id": "",
                "mismatch": {
                    "fixture": (
                        "missing required scenarios: " + ", ".join(missing_scenarios)
                    )
                },
            }
        )

    return {
        "status": "failed" if failed_cases else "passed",
        "fixture_version": fixtures.get("version"),
        "total_cases": len(fixture_rows),
        "covered_scenarios": sorted(set(covered_scenarios)),
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
    try:
        trajectory_goldens = run_agent_golden_trace_gate()
    except Exception as exc:  # noqa: BLE001 - a broken golden gate must block the release
        trajectory_goldens = {
            "status": "failed",
            "fixture_version": None,
            "total_cases": 0,
            "covered_scenarios": [],
            "failed_cases": [
                {
                    "scenario": "__gate__",
                    "case_id": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            ],
        }
    status = (
        "failed"
        if (
            failed_suites
            or errors
            or trajectory_contract["status"] != "passed"
            or trajectory_goldens["status"] != "passed"
        )
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
        "trajectory_goldens": trajectory_goldens,
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
    goldens = payload["trajectory_goldens"]
    mark = "OK" if goldens["status"] == "passed" else "FAIL"
    print(
        f"  [{mark}] agent_trajectory_goldens: "
        f"{goldens['total_cases'] - len(goldens['failed_cases'])}/"
        f"{goldens['total_cases']} match"
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
