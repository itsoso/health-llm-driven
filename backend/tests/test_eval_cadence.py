"""cadence.py 单测 —— P6 评测常态化的回归器 + 漂移闸。

覆盖:
  - summarize_run: 单臂家族聚合正确(每家族 overall 均分 + 全局 overall)
  - detect_drift: 掉 0.6 判红 / 掉 0.4 判绿 / 首跑绿 / 一边缺分不判
  - run_cadence: history 追加不覆盖(旧记录保留、新记录在末尾)
  - check_env: 缺凭证 fail-loud(缺一个/缺全部/齐全)
  - judge 全失败 → overall=None → exit 2(不假绿)

runner / judge 全用注入 fake,不真调网、不真 LLM、不出网。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from evals.comparative.battery import (
    Battery,
    Question,
    FAMILY_QUOTA,
)
from evals.comparative import cadence


# ─────────────────────────── 复用最小合法 battery ───────────────────────────


def _mini_battery() -> Battery:
    """满足家族配比的最小合法 battery(与 test_comparative_eval 同构)。"""
    qs = []
    for fam, quota in FAMILY_QUOTA.items():
        for i in range(quota):
            fups = ["追问一"] if fam == "multi_turn" else []
            qs.append(
                Question(
                    id=f"{fam}_{i}",
                    family=fam,
                    prompt=f"{fam} 问题 {i}",
                    requires_personal_data=(fam != "fact"),
                    scoring_notes="判分要点",
                    follow_ups=fups,
                )
            )
    return Battery(questions=qs)


def _score(prompt_id: str, family: str, overall: float, arm: str = "xiaoba") -> Dict[str, Any]:
    """构造一条已打好分的 judge 输出(五维都给同一个整数分,overall 由参数直给)。"""
    s = max(1, min(5, round(overall)))
    return {
        "arm": arm,
        "blind_id": f"b_{prompt_id}",
        "prompt_id": prompt_id,
        "family": family,
        "latency_ms": 800,
        "cost": None,
        "dimensions": {
            d: {"score": s, "reason": ""}
            for d in ("factual", "personalization", "safety", "actionability", "honesty")
        },
        "flags": [],
        "overall": overall,
    }


# ─────────────────────────── check_env fail-loud ───────────────────────────


def test_check_env_all_present():
    assert cadence.check_env({"REVA_EVAL_TOKEN": "t", "TOKENPLAN_API_KEY": "k"}) == []


def test_check_env_missing_one():
    missing = cadence.check_env({"REVA_EVAL_TOKEN": "t"})
    assert missing == ["TOKENPLAN_API_KEY"]


def test_check_env_missing_all():
    assert set(cadence.check_env({})) == {"REVA_EVAL_TOKEN", "TOKENPLAN_API_KEY"}


def test_check_env_blank_counts_as_missing():
    # 空白值等同缺失(不静默把空串当有效凭证)
    missing = cadence.check_env({"REVA_EVAL_TOKEN": "   ", "TOKENPLAN_API_KEY": "k"})
    assert missing == ["REVA_EVAL_TOKEN"]


def test_main_missing_env_exits_2(monkeypatch):
    # 清掉两把凭证 → main 应 fail-loud exit 2,绝不真跑
    monkeypatch.delenv("REVA_EVAL_TOKEN", raising=False)
    monkeypatch.delenv("TOKENPLAN_API_KEY", raising=False)
    rc = cadence.main(["--run-id", "2026-07-06T00:00:00Z"])
    assert rc == 2


# ─────────────────────────── summarize_run 聚合正确 ───────────────────────────


def test_summarize_run_family_and_overall():
    # fact 两题 (4, 5) → fact 家族均分 4.5;state_read 一题 3 → 3.0
    scores = [
        _score("fact_0", "fact", 4.0),
        _score("fact_1", "fact", 5.0),
        _score("state_read_0", "state_read", 3.0),
    ]
    summary = cadence.summarize_run(scores, transcript_errors=0)
    assert summary["scores_by_family"]["fact"] == 4.5
    assert summary["scores_by_family"]["state_read"] == 3.0
    # 全局 overall = 所有 overall 均分 = (4+5+3)/3 = 4.0
    assert summary["overall"] == 4.0
    assert summary["errors"] == {"transcript": 0, "judge": 0, "total": 0}


def test_summarize_run_counts_judge_and_transcript_errors():
    scores = [
        _score("fact_0", "fact", 4.0),
        {  # judge 失败(overall=None + error)
            "arm": "xiaoba",
            "prompt_id": "fact_1",
            "family": "fact",
            "dimensions": {},
            "flags": ["judge_error:RuntimeError"],
            "overall": None,
            "error": "judge 挂了",
        },
    ]
    summary = cadence.summarize_run(scores, transcript_errors=2)
    assert summary["errors"]["judge"] == 1
    assert summary["errors"]["transcript"] == 2
    assert summary["errors"]["total"] == 3
    # 有效家族分只计入非 None 的那条
    assert summary["scores_by_family"]["fact"] == 4.0


def test_summarize_run_all_judge_failed_overall_none():
    scores = [
        {
            "arm": "xiaoba",
            "prompt_id": "fact_0",
            "family": "fact",
            "dimensions": {},
            "flags": ["judge_error:X"],
            "overall": None,
            "error": "boom",
        },
    ]
    summary = cadence.summarize_run(scores, transcript_errors=0)
    assert summary["overall"] is None
    assert summary["errors"]["judge"] == 1


# ─────────────────────────── detect_drift 判定 ───────────────────────────


def test_detect_drift_first_run_is_green():
    cur = {"scores_by_family": {"fact": 4.0}}
    assert cadence.detect_drift(None, cur, threshold=0.5) == []


def test_detect_drift_drop_0_6_is_red():
    prev = {"scores_by_family": {"fact": 4.5, "state_read": 4.0}}
    cur = {"scores_by_family": {"fact": 3.9, "state_read": 4.0}}  # fact 掉 0.6
    drifts = cadence.detect_drift(prev, cur, threshold=0.5)
    assert len(drifts) == 1
    assert drifts[0]["family"] == "fact"
    assert drifts[0]["drop"] == pytest.approx(0.6)


def test_detect_drift_drop_0_4_is_green():
    prev = {"scores_by_family": {"fact": 4.5}}
    cur = {"scores_by_family": {"fact": 4.1}}  # 掉 0.4,不超 0.5
    assert cadence.detect_drift(prev, cur, threshold=0.5) == []


def test_detect_drift_exactly_threshold_is_green():
    # 严格大于:恰好掉 0.5 不判红
    prev = {"scores_by_family": {"fact": 4.5}}
    cur = {"scores_by_family": {"fact": 4.0}}
    assert cadence.detect_drift(prev, cur, threshold=0.5) == []


def test_detect_drift_improvement_never_red():
    # 涨分绝不判红
    prev = {"scores_by_family": {"fact": 3.0}}
    cur = {"scores_by_family": {"fact": 4.8}}
    assert cadence.detect_drift(prev, cur, threshold=0.5) == []


def test_detect_drift_missing_side_not_judged():
    # 一边缺分(None 或家族缺失)→ 不判漂移(无从比较,不假红)
    prev = {"scores_by_family": {"fact": 4.5, "new_fam": None}}
    cur = {"scores_by_family": {"fact": 4.4}}  # fact 只掉 0.1;new_fam 无当前分
    assert cadence.detect_drift(prev, cur, threshold=0.5) == []


def test_detect_drift_multiple_families_sorted_by_drop():
    prev = {"scores_by_family": {"fact": 4.5, "state_read": 4.0, "honesty": 5.0}}
    cur = {"scores_by_family": {"fact": 3.0, "state_read": 3.3, "honesty": 5.0}}
    # fact 掉 1.5,state_read 掉 0.7,honesty 不掉
    drifts = cadence.detect_drift(prev, cur, threshold=0.5)
    assert [d["family"] for d in drifts] == ["fact", "state_read"]
    assert drifts[0]["drop"] == pytest.approx(1.5)


# ─────────────────────────── run_cadence: history 追加 + exit code ───────────────────────────


def _fake_runner(answers_by_family: Dict[str, str]):
    """fake runner:给每题回一段非空回答(依家族取)。签名 (Battery)->List[dict]。"""

    def _run(battery: Battery) -> List[Dict[str, Any]]:
        rows = []
        for q in battery.questions:
            rows.append(
                {
                    "arm": "xiaoba",
                    "prompt_id": q.id,
                    "family": q.family,
                    "answer": answers_by_family.get(q.family, "回答"),
                    "latency_ms": 100,
                    "cost": None,
                    "error": None,
                }
            )
        return rows

    return _run


def _fake_judge_runner(overall_by_family: Dict[str, float]):
    """fake judge:按家族给定 overall 打分。签名 (records, Battery)->List[dict]。"""

    def _run(records: List[Dict[str, Any]], battery: Battery) -> List[Dict[str, Any]]:
        return [
            _score(r["prompt_id"], r["family"], overall_by_family.get(r["family"], 4.0))
            for r in records
        ]

    return _run


def test_run_cadence_first_run_records_and_exits_0(tmp_path):
    hist = tmp_path / "history.jsonl"
    b = _mini_battery()
    result = cadence.run_cadence(
        run_id="run-1",
        battery=b,
        runner=_fake_runner({}),
        judge_runner=_fake_judge_runner({"fact": 4.0, "state_read": 4.0}),
        history_path=hist,
        threshold=0.5,
    )
    assert result["exit_code"] == 0
    assert result["last"] is None
    assert result["drifts"] == []
    # 历史落了一条
    rows = [json.loads(l) for l in hist.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-1"
    assert rows[0]["ts"] == "run-1"  # ts 用外部 run-id,不用当前时钟
    assert rows[0]["scores_by_family"]["fact"] == 4.0


def test_run_cadence_second_run_appends_not_overwrites(tmp_path):
    hist = tmp_path / "history.jsonl"
    b = _mini_battery()
    # 第一跑:基线
    cadence.run_cadence(
        run_id="run-1",
        battery=b,
        runner=_fake_runner({}),
        judge_runner=_fake_judge_runner({"fact": 4.0}),
        history_path=hist,
        threshold=0.5,
    )
    # 第二跑:分数持平
    result = cadence.run_cadence(
        run_id="run-2",
        battery=b,
        runner=_fake_runner({}),
        judge_runner=_fake_judge_runner({"fact": 4.0}),
        history_path=hist,
        threshold=0.5,
    )
    rows = [json.loads(l) for l in hist.read_text().splitlines() if l.strip()]
    assert len(rows) == 2  # 追加而非覆盖
    assert [r["run_id"] for r in rows] == ["run-1", "run-2"]
    assert result["last"]["run_id"] == "run-1"  # 与上一条比
    assert result["exit_code"] == 0


def test_run_cadence_drift_exits_2_with_detail(tmp_path):
    hist = tmp_path / "history.jsonl"
    b = _mini_battery()
    # 基线:fact 家族高分
    cadence.run_cadence(
        run_id="run-1",
        battery=b,
        runner=_fake_runner({}),
        judge_runner=_fake_judge_runner({"fact": 5.0}),
        history_path=hist,
        threshold=0.5,
    )
    # 回归:fact 家族掉到 4.0(掉 1.0 > 0.5)
    result = cadence.run_cadence(
        run_id="run-2",
        battery=b,
        runner=_fake_runner({}),
        judge_runner=_fake_judge_runner({"fact": 4.0}),
        history_path=hist,
        threshold=0.5,
    )
    assert result["exit_code"] == 2
    assert any(d["family"] == "fact" for d in result["drifts"])
    fact_drift = [d for d in result["drifts"] if d["family"] == "fact"][0]
    assert fact_drift["prev"] == 5.0
    assert fact_drift["current"] == 4.0
    # 即便漂移,当前记录仍落历史(留档可回看)
    rows = [json.loads(l) for l in hist.read_text().splitlines() if l.strip()]
    assert len(rows) == 2


def test_run_cadence_all_judge_failed_exits_2(tmp_path):
    hist = tmp_path / "history.jsonl"
    b = _mini_battery()

    def _all_fail_judge(records, battery):
        return [
            {
                "arm": "xiaoba",
                "prompt_id": r["prompt_id"],
                "family": r["family"],
                "dimensions": {},
                "flags": ["judge_error:X"],
                "overall": None,
                "error": "boom",
            }
            for r in records
        ]

    result = cadence.run_cadence(
        run_id="run-1",
        battery=b,
        runner=_fake_runner({}),
        judge_runner=_all_fail_judge,
        history_path=hist,
        threshold=0.5,
    )
    # 无有效家族分 → overall None → exit 2(不假绿)
    assert result["exit_code"] == 2
    assert result["record"]["overall"] is None
    # 仍留档
    rows = [json.loads(l) for l in hist.read_text().splitlines() if l.strip()]
    assert len(rows) == 1


def test_run_cadence_counts_runner_errors(tmp_path):
    hist = tmp_path / "history.jsonl"
    b = _mini_battery()

    def _runner_with_one_error(battery):
        rows = _fake_runner({})(battery)
        rows[0]["error"] = "网络炸了"  # 一题 runner 失败
        return rows

    result = cadence.run_cadence(
        run_id="run-1",
        battery=b,
        runner=_runner_with_one_error,
        judge_runner=_fake_judge_runner({}),
        history_path=hist,
        threshold=0.5,
    )
    assert result["record"]["errors"]["transcript"] == 1
    assert result["record"]["errors"]["total"] >= 1
