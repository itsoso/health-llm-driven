"""Eval Runner — 加载 suite, 跑 case, 输出 SuiteReport.

每个 suite 注册:
  _RUNNERS[suite]: case.inputs → output dict (raw 业务输出)
  _SCORERS[suite]: (case, output) → dict {scorer_name: scorer_result}

run_case 汇总 — 全部 scorer 都 pass 才算 case pass.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from eval.models import CaseResult, GoldenCase, SuiteReport
from eval.scorers.exact_match import score_rule_set
from eval.scorers.grounding import score_grounding
from eval.scorers.keywords import score_keywords
from eval.scorers.llm_judge import score_llm_judge


_DATASETS_DIR = Path(__file__).parent / "datasets"
_BASELINES_DIR = Path(__file__).parent / "baselines"


_RUNNERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
_SCORERS: Dict[str, Callable[[GoldenCase, Dict[str, Any]], Dict[str, Dict[str, Any]]]] = {}


def _register_runner(suite: str):
    def deco(fn):
        _RUNNERS[suite] = fn
        return fn
    return deco


def _register_scorer(suite: str):
    def deco(fn):
        _SCORERS[suite] = fn
        return fn
    return deco


# ============= safety suite =============

@_register_runner("safety")
def _run_safety_case(case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    from datetime import datetime as _dt
    from app.agents.safety_guardian import evaluate_safety
    from app.twin.schema import HealthTwin

    twin_data = dict(case_inputs.get("twin", {}))
    twin_data.setdefault("meta", {"user_id": 0, "generated_at": _dt.now(timezone.utc)})
    twin = HealthTwin(**twin_data)
    report = evaluate_safety(twin)
    return {"rule_ids": [a.rule_id for a in report.alerts]}


@_register_scorer("safety")
def _score_safety(case: GoldenCase, output: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {"rule_set": score_rule_set(output.get("rule_ids", []), case.expected)}


# ============= orchestrator suite =============

@_register_runner("orchestrator")
def _run_orchestrator_case(case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """跑真实 _build_synthesis_prompt + _call_llm. 不依赖 DB."""
    import asyncio
    from datetime import datetime as _dt
    from app.orchestrator.orchestrator import _build_synthesis_prompt, _call_llm
    from app.orchestrator.schema import SpecialistFinding
    from app.twin.schema import HealthTwin

    twin_data = dict(case_inputs.get("twin", {}))
    twin_data.setdefault("meta", {"user_id": 0, "generated_at": _dt.now(timezone.utc)})
    twin = HealthTwin(**twin_data)

    findings = [SpecialistFinding(**f) for f in case_inputs.get("findings", [])]
    query = case_inputs.get("query", "")

    system_prompt, user_prompt = _build_synthesis_prompt(query, twin, findings)
    synthesis = asyncio.run(_call_llm(system_prompt, user_prompt))
    return {"synthesis": synthesis, "query": query}


@_register_scorer("orchestrator")
def _score_orchestrator(case: GoldenCase, output: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    text = output.get("synthesis", "")
    query = output.get("query", "")
    results = {"keywords": score_keywords(text, case.expected)}
    if "llm_judge_min_score" in case.expected:
        results["llm_judge"] = score_llm_judge(query, text, case.expected)
    return results


# ============= insight suite =============

@_register_runner("insight")
def _run_insight_case(case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """纯 grounding 逻辑测试 — 不调 LLM, 不需 DB.

    case 直接给 candidate dict (相当于 mock LLM 已经返回的结果),
    runner 只是把 candidate 透传给 scorer.
    """
    return {
        "candidate": case_inputs.get("candidate", {}),
        "available": case_inputs.get("available", {}),
    }


@_register_scorer("insight")
def _score_insight(case: GoldenCase, output: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    grounding_result = score_grounding(
        actual=output["candidate"],
        expected=case.expected,
        available=output["available"],
    )
    expected_grounded = bool(case.expected.get("expect_grounded", True))
    case_passed = grounding_result["passed"] == expected_grounded
    # 把 case_passed 注回到 result, 让 run_case 的 all() 判定生效
    grounding_result["case_passed"] = case_passed
    grounding_result["expected_grounded"] = expected_grounded
    grounding_result["passed"] = case_passed  # 覆盖, 让 run_case 看到 case 级判定
    return {"grounding": grounding_result}


# ============= 通用流程 =============

def load_suite(suite: str) -> List[GoldenCase]:
    path = _DATASETS_DIR / f"{suite}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Suite '{suite}' 数据集不存在: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = []
    _RESERVED = {"id", "description", "expected", "tags"}
    for c in raw.get("cases", []):
        # 把所有非 reserved 字段都装进 inputs, 各 suite 的 runner 自取
        inputs = {k: v for k, v in c.items() if k not in _RESERVED}
        cases.append(GoldenCase(
            id=c["id"],
            description=c.get("description", ""),
            suite=suite,
            inputs=inputs,
            expected=c.get("expected", {}),
            tags=c.get("tags", []),
        ))
    return cases


def run_case(case: GoldenCase) -> CaseResult:
    runner = _RUNNERS.get(case.suite)
    scorer = _SCORERS.get(case.suite)
    if runner is None or scorer is None:
        return CaseResult(
            case_id=case.id, suite=case.suite, passed=False,
            error=f"无 runner/scorer: {case.suite}",
        )

    t0 = time.monotonic()
    try:
        output = runner(case.inputs)
    except Exception as e:
        return CaseResult(
            case_id=case.id, suite=case.suite, passed=False,
            error=f"runner 异常: {type(e).__name__}: {e}",
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

    latency_ms = int((time.monotonic() - t0) * 1000)
    scorer_results = scorer(case, output)
    passed = all(s.get("passed", False) for s in scorer_results.values())
    scores = [s.get("score", 0.0) for s in scorer_results.values()]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    return CaseResult(
        case_id=case.id,
        suite=case.suite,
        passed=passed,
        score=round(avg_score, 3),
        details={"output": output, "scorers": scorer_results},
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
        baseline_path = _BASELINES_DIR / f"{suite}_{baseline}.json"
        report.baseline_path = str(baseline_path)
        if baseline_path.exists():
            base = json.loads(baseline_path.read_text(encoding="utf-8"))
            base_passed_ids = {c["case_id"] for c in base.get("cases", []) if c.get("passed")}
            now_failing_ids = {r.case_id for r in results if not r.passed}
            report.regression = sorted(base_passed_ids & now_failing_ids)

    return report


def write_baseline(report: SuiteReport, name: str) -> Path:
    _BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    path = _BASELINES_DIR / f"{report.suite}_{name}.json"
    path.write_text(report.model_dump_json(indent=2, exclude={"started_at"}), encoding="utf-8")
    return path
