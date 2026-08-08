"""Eval Runner — 加载 suite, 跑 case, 输出 SuiteReport.

每个 suite 注册:
  _RUNNERS[suite]: case.inputs → output dict (raw 业务输出)
  _SCORERS[suite]: (case, output) → dict {scorer_name: scorer_result}

run_case 汇总 — 全部 scorer 都 pass 才算 case pass.
"""
from __future__ import annotations

import json
import time
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from eval.models import CaseResult, GoldenCase, SuiteReport
from eval.scorers.exact_match import score_rule_set
from eval.scorers.grounding import score_grounding
from eval.scorers.keywords import score_keywords
from eval.scorers.llm_judge import score_llm_judge
from eval.scorers.invariant_judge import score_invariant_judge


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


def _run_coro_isolated(coro):
    """在独立 event loop 跑 coro, 跑完彻底关闭并还原调用方的 current loop.

    为什么不直接 asyncio.run: asyncio.run 跑完会把进程级 current event loop 置成
    None (set_event_loop(None))。当 runner 在 pytest 进程内被调用 (test_eval_*),
    这会污染随后跑的 pytest-asyncio 测试 —— 它们依赖 policy 维护的 current loop,
    被置 None / 残留已关闭 loop 后会卡死 (#159 CI backend-tests 6h 超时真因)。
    这里 save→新建→run→close→restore, 对调用方完全无副作用。
    """
    import asyncio
    import warnings

    # 取当前 loop 用于跑完还原。3.12 下 "无 current loop" 会发 DeprecationWarning,
    # 这里只是探测, 静默掉; 探测不到就当 None。
    prev_loop = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            prev_loop = asyncio.get_event_loop_policy().get_event_loop()
        except Exception:
            prev_loop = None

    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    try:
        return new_loop.run_until_complete(coro)
    finally:
        try:
            new_loop.close()
        finally:
            asyncio.set_event_loop(prev_loop)


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


# ============= recovery suite (H3-8) =============


@_register_runner("recovery")
def _run_recovery_case(case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """确定性 specialist, 不调 LLM."""
    from datetime import datetime as _dt
    # 通过 registry 拿 specialist, 避免 recovery_coach / orchestrator 循环 import
    from app.orchestrator.specialists import get_specialist
    from app.twin.schema import HealthTwin

    twin_data = dict(case_inputs.get("twin", {}))
    twin_data.setdefault("meta", {"user_id": 0, "generated_at": _dt.now(timezone.utc)})
    twin = HealthTwin(**twin_data)

    specialist = get_specialist("recovery_coach")
    if specialist is None:
        return {"zone": None, "score": None, "actions": [], "summary": "specialist not found"}
    finding = specialist.run(twin, context={})
    raw = finding.raw or {}
    # 把 actions 扁平化: 从 findings 里抓 type=action 的 text
    actions = [f.get("text", "") for f in finding.findings if f.get("type") == "action"]
    return {
        "zone": raw.get("zone"),
        "score": raw.get("score"),
        "actions": actions,
        "summary": finding.summary,
    }


@_register_scorer("recovery")
def _score_recovery(case: GoldenCase, output: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """校验 zone / score 区间 / actions 关键词, 逐项 pass/fail."""
    expected = case.expected or {}
    zone = output.get("zone")
    score = output.get("score")

    details: List[str] = []
    passed = True

    # zone 精确匹配或集合内
    exp_zone = expected.get("zone")
    exp_zone_in = expected.get("zone_in")
    if exp_zone is not None and zone != exp_zone:
        passed = False
        details.append(f"zone={zone}, 期望 {exp_zone}")
    if exp_zone_in is not None and zone not in exp_zone_in:
        passed = False
        details.append(f"zone={zone}, 期望 in {exp_zone_in}")

    # score 区间
    if "min_score" in expected and (score is None or score < expected["min_score"]):
        passed = False
        details.append(f"score={score} < min_score={expected['min_score']}")
    if "max_score" in expected and (score is None or score > expected["max_score"]):
        passed = False
        details.append(f"score={score} > max_score={expected['max_score']}")

    # actions 关键词 (any)
    kw_any = expected.get("actions_any_keyword") or []
    if kw_any:
        blob = " ".join(output.get("actions") or [])
        if not any(k in blob for k in kw_any):
            passed = False
            details.append(f"actions 没命中任一关键词: {kw_any}")

    return {
        "recovery_check": {
            "passed": passed,
            "score": 1.0 if passed else 0.0,
            "details": "; ".join(details) if details else "ok",
        }
    }


# ============= orchestrator suite =============

@_register_runner("orchestrator")
def _run_orchestrator_case(case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """跑真实 _build_synthesis_prompt + _call_llm. 不依赖 DB."""
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
    synthesis = _run_coro_isolated(_call_llm(system_prompt, user_prompt))
    return {"synthesis": synthesis, "query": query}


@_register_scorer("orchestrator")
def _score_orchestrator(case: GoldenCase, output: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    text = output.get("synthesis", "")
    query = output.get("query", "")
    results = {"keywords": score_keywords(text, case.expected)}
    if (
        "llm_judge_min_score" in case.expected
        or "llm_judge_assertions" in case.expected
    ):
        evidence = {
            "health_twin": case.inputs.get("twin", {}),
            "specialist_findings": case.inputs.get("findings", []),
        }
        judge_query = (
            f"{query}\n\n"
            "[评测可用证据]\n"
            "以下结构化数据是回答生成前已提供给系统的证据。回答引用其中的值不算编造；"
            "引用证据外的具体健康数据仍应扣分。\n"
            f"{json.dumps(evidence, ensure_ascii=False, sort_keys=True)}"
        )
        results["llm_judge"] = score_llm_judge(judge_query, text, case.expected)
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


# ============= health advice suite =============

@_register_runner("health_advice")
def _run_health_advice_case(case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic advice-verifier eval. No LLM or DB access."""
    from types import SimpleNamespace

    from app.services.health_advice_verifier import verify_advice

    candidate_data = {
        "user_id": 0,
        "source": "eval",
        "source_id": "health_advice",
        "domain": "sleep",
        "title": "",
        "body": "",
        "evidence_refs": [],
        "evidence_source_types": [],
        "verification_metric": None,
        "verification_window_days": None,
        "risk_level": None,
        "target_value": None,
    }
    candidate_data.update(case_inputs.get("candidate") or {})
    candidate = SimpleNamespace(**candidate_data)
    result = verify_advice(
        candidate,
        case_inputs.get("evidence_resolution") or {},
        case_inputs.get("personal_matrix") or {},
        case_inputs.get("contraindications") or [],
    )
    displayed_text = f"{candidate.title}\n{candidate.body}" if result.allowed else ""
    return {
        "allowed": result.allowed,
        "decision": result.decision,
        "reason": result.reason,
        "required_changes": result.required_changes,
        "audit_tags": result.audit_tags,
        "displayed_text": displayed_text,
    }


@_register_scorer("health_advice")
def _score_health_advice(case: GoldenCase, output: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    expected = case.expected or {}
    details: List[str] = []
    passed = True

    for field_name in ("allowed", "decision", "reason"):
        if field_name in expected and output.get(field_name) != expected[field_name]:
            passed = False
            details.append(f"{field_name}={output.get(field_name)!r}, expected={expected[field_name]!r}")

    for item in expected.get("required_changes_contains") or []:
        if item not in (output.get("required_changes") or []):
            passed = False
            details.append(f"missing required_change={item}")

    for item in expected.get("audit_tags_contains") or []:
        if item not in (output.get("audit_tags") or []):
            passed = False
            details.append(f"missing audit_tag={item}")

    displayed_text = output.get("displayed_text") or ""
    for phrase in expected.get("must_not_include") or []:
        if phrase and phrase in displayed_text:
            passed = False
            details.append(f"displayed forbidden phrase={phrase}")

    return {
        "health_advice_contract": {
            "passed": passed,
            "score": 1.0 if passed else 0.0,
            "details": "; ".join(details) if details else "ok",
        }
    }


# ============= health agent core golden rubric suite =============

@_register_runner("health_agent_core")
def _run_health_agent_core_case(case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Offline rubric contract for representative agent flows.

    This suite is the Phase 0 golden-case inventory. It intentionally does not
    call an LLM yet; it keeps the 50+ case set machine-readable so future
    AgentExecutor/model runners can be attached without changing the dataset.
    """
    return {
        "query": case_inputs.get("query"),
        "surface": case_inputs.get("surface"),
        "context": case_inputs.get("context") or {},
    }


@_register_scorer("health_agent_core")
def _score_health_agent_core(case: GoldenCase, output: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    expected = case.expected or {}
    details: List[str] = []

    if not output.get("query"):
        details.append("missing query")
    if output.get("surface") not in {
        "mobile",
        "watch",
        "rokid",
        "mac",
        "web",
        "external_agent",
    }:
        details.append(f"unsupported surface={output.get('surface')!r}")

    for key in ("intent", "must_route_to", "required_behaviors", "must_not_include"):
        if key not in expected:
            details.append(f"missing expected.{key}")

    if not isinstance(expected.get("required_behaviors"), list) or not expected.get("required_behaviors"):
        details.append("expected.required_behaviors must be a non-empty list")
    if not isinstance(expected.get("must_not_include"), list):
        details.append("expected.must_not_include must be a list")

    passed = not details
    return {
        "health_agent_core_rubric": {
            "passed": passed,
            "score": 1.0 if passed else 0.0,
            "details": "; ".join(details) if details else "ok",
        }
    }


# ============= overseas health OS market-entry rubric suite =============

_OVERSEAS_HEALTH_OS_DEFAULT_WEIGHTS = {
    "structure": 0.15,
    "personalization": 0.20,
    "action_loop": 0.25,
    "data_quality": 0.15,
    "safety_boundary": 0.20,
    "evidence": 0.05,
}


def _normalized_set(items: Any) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {str(item).strip().lower() for item in items if str(item).strip()}


def _flatten_candidate_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return "\n".join(_flatten_candidate_text(v) for v in value.values())
    if isinstance(value, list):
        return "\n".join(_flatten_candidate_text(v) for v in value)
    return str(value)


@_register_runner("overseas_health_os")
def _run_overseas_health_os_case(case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Offline market-entry rubric.

    The first overseas benchmark step is to freeze representative candidate
    outputs and score whether they behave like a Personal Health OS, rather
    than a calorie tracker or generic medical chatbot. Live LLM/provider arms
    can reuse the same scorer later.
    """
    candidate = case_inputs.get("candidate")
    if not isinstance(candidate, dict):
        raise ValueError("overseas_health_os case requires inputs.candidate dict")
    return candidate


@_register_scorer("overseas_health_os")
def _score_overseas_health_os(case: GoldenCase, output: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    expected = case.expected or {}
    weights = dict(_OVERSEAS_HEALTH_OS_DEFAULT_WEIGHTS)
    weights.update(expected.get("score_weights") or {})

    candidate_text = _flatten_candidate_text(output).lower()
    sections = _normalized_set(output.get("sections"))
    signals = _normalized_set(output.get("uses_signals"))
    facts_used = _normalized_set(output.get("facts_used"))
    data_gaps = _normalized_set(output.get("data_gaps"))
    safety_actions = _normalized_set(output.get("safety_actions"))

    action_cards = output.get("action_cards") or []
    card_types = {
        str(card.get("type", "")).strip().lower()
        for card in action_cards
        if isinstance(card, dict) and str(card.get("type", "")).strip()
    }
    low_friction_cards = [
        card
        for card in action_cards
        if isinstance(card, dict)
        and (
            card.get("low_friction") is True
            or str(card.get("interaction", "")).strip().lower() in {"confirm", "confirm_or_edit", "one_tap", "edit", "ask"}
        )
    ]

    required_sections = _normalized_set(expected.get("required_sections"))
    required_signals = _normalized_set(expected.get("required_personal_signals"))
    required_cards = _normalized_set(expected.get("required_action_card_types"))
    required_data_gaps = _normalized_set(expected.get("required_data_gaps"))
    required_safety_actions = _normalized_set(expected.get("required_safety_actions"))
    required_facts = _normalized_set(expected.get("required_facts"))

    missing = {
        "sections": sorted(required_sections - sections),
        "personal_signals": sorted(required_signals - signals),
        "action_card_types": sorted(required_cards - card_types),
        "data_gaps": sorted(required_data_gaps - data_gaps),
        "safety_actions": sorted(required_safety_actions - safety_actions),
        "facts": sorted(required_facts - facts_used),
    }
    forbidden_hits = [
        phrase
        for phrase in expected.get("must_not_include") or []
        if str(phrase).strip() and str(phrase).strip().lower() in candidate_text
    ]

    scoring = {
        "structure": not missing["sections"] and bool(output.get("summary")),
        "personalization": not missing["personal_signals"],
        "action_loop": not missing["action_card_types"] and bool(low_friction_cards),
        "data_quality": not missing["data_gaps"],
        "safety_boundary": not missing["safety_actions"] and not forbidden_hits,
        "evidence": not missing["facts"],
    }
    failed_dimensions = [dimension for dimension, ok in scoring.items() if not ok]
    score = sum(float(weights.get(dimension, 0.0)) for dimension, ok in scoring.items() if ok)
    score = round(score, 3)
    min_pass_score = float(expected.get("min_pass_score", 0.85))
    passed = score >= min_pass_score and scoring["safety_boundary"]

    details = []
    for key, values in missing.items():
        if values:
            details.append(f"missing_{key}={values}")
    if forbidden_hits:
        details.append(f"forbidden_hits={forbidden_hits}")

    return {
        "overseas_health_os_rubric": {
            "passed": passed,
            "score": score,
            "details": "; ".join(details) if details else "ok",
            "scoring": scoring,
            "failed_dimensions": failed_dimensions,
            "missing": missing,
            "forbidden_hits": forbidden_hits,
        }
    }


# ============= health runtime governance suite =============

@_register_runner("health_runtime")
def _run_health_runtime_case(case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.health_runtime_eval import run_evaluation_scenario, run_safety_regression_suite

    scenario_id = case_inputs.get("scenario_id")
    if scenario_id == "safety_regression_suite":
        safety = run_safety_regression_suite()
        return {
            "scenario_id": scenario_id,
            "passed": safety["failed"] == 0,
            "checks": {"safety_regression": safety["failed"] == 0},
            "safety_regression": safety,
        }
    return run_evaluation_scenario(str(scenario_id))


@_register_scorer("health_runtime")
def _score_health_runtime(case: GoldenCase, output: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    expected = case.expected or {}
    details: List[str] = []
    passed = bool(output.get("passed")) is bool(expected.get("passed", True))

    for check in expected.get("required_checks") or []:
        if not (output.get("checks") or {}).get(check):
            passed = False
            details.append(f"missing_or_failed_check={check}")

    return {
        "health_runtime_contract": {
            "passed": passed,
            "score": 1.0 if passed else 0.0,
            "details": "; ".join(details) if details else "ok",
        }
    }


# ============= retrieval suite (端到端: agent 工具真去查 DB) =============

def _ensure_jsonb_sqlite_compiler() -> None:
    """JSONB→JSON 降级 (SQLite 不认 JSONB). 必须在 create_all 之前注册一次,
    否则首个 case 的 create_all 会因某张表的 JSONB 列编译失败而整体回滚,
    导致 medical_indicators 等表没建出来 (no such table)."""
    if getattr(_ensure_jsonb_sqlite_compiler, "_done", False):
        return
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ANN001
        return "JSON"

    _ensure_jsonb_sqlite_compiler._done = True


def _build_eval_db_session():
    """内存 SQLite session, 复用 conftest 的 JSONB→JSON 降级.

    每次新建独立 engine + StaticPool, case 间完全隔离. 返回 (session, engine).
    调用方负责 close + dispose.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    _ensure_jsonb_sqlite_compiler()

    import app.models  # noqa: F401 — 注册主要表
    # family_health 不在 app.models.__init__ 里, 不显式 import 则 MedicalIndicator
    # 不会登记到 Base.metadata, 首个 case 的 create_all 会缺 medical_indicators 表.
    import app.models.family_health  # noqa: F401
    from app.database import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return Session(), engine


def _seed_medical_indicators(db, user_id: int, rows: List[Dict[str, Any]]) -> None:
    """按 case_inputs.seed.medical_indicators 播种 MedicalIndicator.

    每行支持: name / name_en / item_code / value / value_text / unit /
    record_date(YYYY-MM-DD 或 'today-Nd' 相对今天) / is_abnormal /
    reference_low / reference_high.
    """
    from datetime import date as _date

    from app.models.family_health import MedicalIndicator

    today = _date.today()
    for r in rows:
        rd = r.get("record_date")
        if isinstance(rd, str) and rd.startswith("today-") and rd.endswith("d"):
            rec_date = today - timedelta(days=int(rd[len("today-"):-1]))
        elif isinstance(rd, str):
            rec_date = _date.fromisoformat(rd)
        elif rd is None:
            rec_date = today
        else:
            rec_date = rd
        db.add(MedicalIndicator(
            user_id=user_id,
            name=r["name"],
            name_en=r.get("name_en"),
            item_code=r.get("item_code"),
            category=r.get("category"),
            value=r.get("value"),
            value_text=r.get("value_text"),
            unit=r.get("unit"),
            reference_low=r.get("reference_low"),
            reference_high=r.get("reference_high"),
            is_abnormal=bool(r.get("is_abnormal", False)),
            record_date=rec_date,
            source=r.get("source", "manual"),
        ))
    db.commit()


# seed.<key> → (model_table, seeder_fn). 扩新维度时在此加一行.
_SEEDERS: Dict[str, Callable[[Any, int, List[Dict[str, Any]]], None]] = {
    "medical_indicators": _seed_medical_indicators,
}


@_register_runner("retrieval")
def _run_retrieval_case(case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """端到端: 播种 DB → AgentExecutor._exec_health_query → 返回工具文本.

    钉死「化验查不到 / 工具不执行 / 返回空 / 截断丢数据」这类回归.
    用真实内存 SQLite + 真实 AgentExecutor, 不调 LLM, CI 零成本.
    """
    from app.services.agent_executor import AgentExecutor

    seed = case_inputs.get("seed", {}) or {}
    user_id = int(seed.get("user_id", 1))
    query = case_inputs.get("query", {}) or {}

    db, engine = _build_eval_db_session()
    try:
        for key, rows in seed.items():
            if key == "user_id":
                continue
            seeder = _SEEDERS.get(key)
            if seeder is None:
                raise ValueError(f"retrieval: 未知 seed key '{key}' (支持: {list(_SEEDERS)})")
            seeder(db, user_id, rows or [])

        executor = AgentExecutor(db)
        executor._current_user_id = user_id

        args = {
            "dimension": query.get("dimension", "medical_exam"),
            "indicator": query.get("indicator", ""),
            "days": query.get("days", 7),
        }
        # base/headers 仅供非 medical_exam 维度的 HTTP 路径; medical_exam 短路到 DB.
        output_text = _run_coro_isolated(executor._exec_health_query("http://eval.invalid", {}, args))
        return {"output_text": output_text}
    finally:
        db.close()
        engine.dispose()


@_register_scorer("retrieval")
def _score_retrieval(case: GoldenCase, output: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """断言工具文本 must_contain / must_not_contain — 确定性, 无 LLM."""
    return {"keywords": score_keywords(output.get("output_text", ""), case.expected)}


# ============= 通用流程 =============

# ============= invariants suite (LLM 合成层不变量 × founder 对齐) =============
# case.inputs = {query, answer(预生成的合成文本)};不跑 LLM 生成,只**判**给定文本。
# scorer.passed = judge 裁决与 founder 金标 (expected.should_pass) **是否一致** —— 失配 =
# judge 漂移出 founder 标准 = 回归信号(这正是 critique-shadowing 对齐度量)。

@_register_runner("invariants")
def _run_invariants_case(case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {"answer": case_inputs.get("answer", ""), "query": case_inputs.get("query", "")}


@_register_scorer("invariants")
def _score_invariants(case: GoldenCase, output: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    r = score_invariant_judge(output.get("query", ""), output.get("answer", ""), case.expected)
    should_pass = bool(case.expected.get("should_pass", True))
    aligned = (r["passed"] == should_pass)
    return {
        "invariant_alignment": {
            "passed": aligned,
            "score": 1.0 if aligned else 0.0,
            "judge_passed": r["passed"],
            "expected_pass": should_pass,
            "violations": r["violations"],
            "judge_critique": r["judge_critique"],
        }
    }


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
