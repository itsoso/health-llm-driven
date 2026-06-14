"""Retrieval eval suite contract tests.

钉死 "agent 工具真去查 DB + 返回对的数据" 的端到端验证, 防止
化验查不到 / 工具不执行 / 返回空 / 截断丢数据 这类 bug 再上线没人发现.

注意 (#159): retrieval runner 跑真实 AgentExecutor + 内存 SQLite + asyncio。
`run_suite("retrieval")` 这个最重的 case 用**子进程** (`python -m eval run`) 跑,
与 CI 的 `eval run --suite retrieval` 同一条路径, 跑在独立解释器里, 物理上不可能
污染 pytest 进程的 event loop / SQLAlchemy 全局状态 (历史 6h 超时真因)。
轻量 case (load / scorer 自检 / 注册表) 留在进程内 —— runner 已用
`_run_coro_isolated` 隔离 event loop, 进程内跑也安全。
"""
import subprocess
import sys

from app.tasks import eval_runner
from eval.runner import load_suite


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
    """#146 已修, 当前 health_query 行为正确 → 全 pass, 无 regression.

    子进程跑 `python -m eval run --suite retrieval --baseline main
    --fail-on-regression`: 与 CI 同路径, 独立解释器, 不污染 pytest 进程
    (event loop / SQLAlchemy compiler 全局态)。exit 0 = 无 regression。
    """
    proc = subprocess.run(
        [sys.executable, "-m", "eval", "run", "--suite", "retrieval",
         "--baseline", "main", "--fail-on-regression"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"retrieval eval 子进程非零退出 ({proc.returncode}).\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    # 防"假绿": 输出里必须真出现 5/5 通过, 而不是 0 case 静默退出
    assert "retrieval:" in proc.stdout, f"未见 retrieval suite 输出:\n{proc.stdout}"


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
