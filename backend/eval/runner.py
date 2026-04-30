"""Eval Runner — 加载 suite, 跑 case, 输出 SuiteReport.

v1 只支持 safety suite (Safety Guardian 规则集); orchestrator/insight 后续扩.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from eval.models import CaseResult, GoldenCase, SuiteReport
from eval.scorers.exact_match import score_rule_set


_DATASETS_DIR = Path(__file__).parent / "datasets"
_BASELINES_DIR = Path(__file__).parent / "baselines"


# 每个 suite 的 case 跑法 — 从 inputs 跑到 actual rule_ids
_RUNNERS = {}


def _register_runner(suite: str):
    def deco(fn):
        _RUNNERS[suite] = fn
        return fn
    return deco


@_register_runner("safety")
def _run_safety_case(case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """从 case.twin (dict) 构造 HealthTwin, 跑 evaluate_safety, 返回 rule_id 集合."""
    from datetime import datetime as _dt
    from app.agents.safety_guardian import evaluate_safety
    from app.twin.schema import HealthTwin, TwinMeta

    twin_data = dict(case_inputs.get("twin", {}))
    # 必填 meta — 用 user_id=0 标识 fixture twin
    twin_data.setdefault("meta", {"user_id": 0, "generated_at": _dt.now(timezone.utc)})
    twin = HealthTwin(**twin_data)

    report = evaluate_safety(twin)
    return {"rule_ids": [a.rule_id for a in report.alerts]}


def load_suite(suite: str) -> List[GoldenCase]:
    path = _DATASETS_DIR / f"{suite}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Suite '{suite}' 数据集不存在: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = []
    for c in raw.get("cases", []):
        cases.append(GoldenCase(
            id=c["id"],
            description=c.get("description", ""),
            suite=suite,
            inputs={"twin": c.get("twin", {})},
            expected=c.get("expected", {}),
            tags=c.get("tags", []),
        ))
    return cases


def run_case(case: GoldenCase) -> CaseResult:
    runner = _RUNNERS.get(case.suite)
    if runner is None:
        return CaseResult(
            case_id=case.id, suite=case.suite, passed=False,
            error=f"无 runner: {case.suite}",
        )

    t0 = time.monotonic()
    try:
        actual = runner(case.inputs)
    except Exception as e:
        return CaseResult(
            case_id=case.id, suite=case.suite, passed=False,
            error=f"runner 异常: {type(e).__name__}: {e}",
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

    latency_ms = int((time.monotonic() - t0) * 1000)
    score = score_rule_set(actual.get("rule_ids", []), case.expected)
    return CaseResult(
        case_id=case.id,
        suite=case.suite,
        passed=score["passed"],
        score=score["score"],
        details={"actual": actual, "scoring": score},
        latency_ms=latency_ms,
    )


def run_suite(suite: str, baseline: Optional[str] = None) -> SuiteReport:
    cases = load_suite(suite)
    results = [run_case(c) for c in cases]

    passed = sum(1 for r in results if r.passed)
    errored = sum(1 for r in results if r.error)
    failed = len(results) - passed - errored
    avg_score = (sum(r.score for r in results) / len(results)) if results else 0.0
    avg_latency = (sum(r.latency_ms for r in results) // len(results)) if results else 0

    report = SuiteReport(
        suite=suite,
        total_cases=len(results),
        passed=passed,
        failed=failed,
        errored=errored,
        avg_score=round(avg_score, 3),
        avg_latency_ms=avg_latency,
        cases=results,
    )

    if baseline:
        baseline_path = _BASELINES_DIR / f"{baseline}.json"
        report.baseline_path = str(baseline_path)
        if baseline_path.exists():
            base = json.loads(baseline_path.read_text(encoding="utf-8"))
            base_passed_ids = {c["case_id"] for c in base.get("cases", []) if c.get("passed")}
            now_failing_ids = {r.case_id for r in results if not r.passed}
            report.regression = sorted(base_passed_ids & now_failing_ids)

    return report


def write_baseline(report: SuiteReport, name: str) -> Path:
    _BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    path = _BASELINES_DIR / f"{name}.json"
    path.write_text(report.model_dump_json(indent=2, exclude={"started_at"}), encoding="utf-8")
    return path
