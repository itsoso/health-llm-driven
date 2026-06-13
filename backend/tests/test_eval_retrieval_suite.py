"""Retrieval eval suite contract tests.

钉死 "agent 工具真去查 DB + 返回对的数据" 的端到端验证, 防止
化验查不到 / 工具不执行 / 返回空 / 截断丢数据 这类 bug 再上线没人发现.
"""

from app.tasks import eval_runner
from eval.runner import load_suite, run_suite


def test_retrieval_suite_loads_required_cases():
    cases = load_suite("retrieval")
    ids = {c.id for c in cases}
    # 本会话踩过的真 bug 必须各有一条 golden case 钉死
    assert {
        "lab_query_returns_seeded",
        "lab_query_by_indicator",
        "lab_empty_when_no_data",
        "lab_many_not_truncated",
        "stale_marked",
    }.issubset(ids)


def test_retrieval_suite_passes_against_main_baseline():
    """#146 已修, 当前 health_query 行为正确 → 全 pass, 无 regression."""
    report = run_suite("retrieval", baseline="main")

    assert report.total_cases >= 5
    assert report.failed == 0, [c.case_id for c in report.cases if not c.passed]
    assert report.errored == 0, [c.error for c in report.cases if c.error]
    assert report.regression == []


def test_retrieval_scorer_catches_wrong_value():
    """自检: 改坏 expected → scorer 真能 fail (而非假绿)."""
    cases = load_suite("retrieval")
    case = next(c for c in cases if c.id == "lab_query_returns_seeded")
    case.expected = dict(case.expected)
    case.expected["must_contain"] = list(case.expected["must_contain"]) + ["ZZZ_NONEXISTENT"]

    from eval.runner import run_case

    result = run_case(case)
    assert result.passed is False


def test_weekly_eval_runner_registers_retrieval_suite():
    assert ("retrieval", "main") in eval_runner._SUITES
