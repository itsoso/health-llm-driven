"""Wave 3(轻量 D3):把 Wave 1/2 建立的工具执行分级钉成 CI 不变量,防未来漂移。

三类工具执行(单一真源=活代码,本文件只断言不变量,不重抄清单):
- inline        —— 默认,<2s 快返回(绝大多数 health_query/health_record record_type)。
- slow-inline   —— 慢但走 async I/O(health_analysis→orchestrator、knowledge_search→
                   ChromaDB);经 _run_tool_with_progress 心跳 + per-tool 超时预算兜底。
- async-job     —— garmin_sync:本地 precondition → Celery enqueue,**绝不内联阻塞**。

背景:garmin_sync 曾是 record_map 里的内联阻塞同步 POST,冻死 event loop → 手机"帮我
同步"永久转圈(Wave 1 根治)。Wave 2 给慢工具加了心跳+超时。这些不变量若被未来改动
悄悄破坏(如把 garmin_sync 塞回 record_map、或改 orchestrator 内层超时超过外层),
会静默复现老 bug —— 本文件让它们变成 CI 硬门。见
project_garmin_sync_async_action_and_slow_tool_class。
"""
import ast
from pathlib import Path

import app.services.agent_executor as ae


def _exec_health_record_record_map_keys() -> set:
    """AST 扫 _exec_health_record 里 record_map 字面 dict 的字符串键(不 import 活对象)。"""
    src = Path(ae.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "_exec_health_record"
    )
    keys: set = set()
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "record_map" for t in node.targets)
            and isinstance(node.value, ast.Dict)
        ):
            for k in node.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
    return keys


# ── async-job 不变量(Wave 1 防回归)────────────────────────────────────
def test_garmin_sync_is_async_job_not_inline_record():
    keys = _exec_health_record_record_map_keys()
    assert "garmin_sync" not in keys, (
        "garmin_sync 被加回 record_map 内联阻塞 POST —— 会复现'帮我同步'永久转圈。"
        "同步必须走 _trigger_garmin_sync 异步分支(Celery enqueue)。"
    )
    src = Path(ae.__file__).read_text(encoding="utf-8")
    assert "_trigger_garmin_sync" in src, "缺 garmin_sync 异步触发分支"
    # 写诚实闸豁免必须仍在(否则异步 ack 会被误判'未取得写入回执')
    assert "garmin_sync" in ae._NON_WRITE_RECORD_TYPES


# ── slow-inline 超时分级不变量(Wave 2 A3 防回归)────────────────────────
def test_health_analysis_timeout_covers_orchestrator_internal():
    override = ae._TOOL_TIMEOUT_OVERRIDES.get("health_analysis")
    assert override is not None, "health_analysis 缺 per-tool 超时 override"
    # 外层 per-tool 超时必须 ≥ 内层 orchestrator wait_for,否则外层先砍:
    # 内层 fail-loud 措辞永不生效,还可能中途 cancel 进程内分析。
    assert override >= ae.AgentExecutor.ORCHESTRATOR_IN_PROCESS_TIMEOUT_S, (
        f"health_analysis per-tool 超时 {override}s < orchestrator 内层 "
        f"{ae.AgentExecutor.ORCHESTRATOR_IN_PROCESS_TIMEOUT_S}s —— 外层会先砍内层"
    )


def test_tool_timeout_budgets_within_client_and_above_heartbeat():
    # per-tool 预算必须 < 客户端 xhr 300s(否则客户端先超时,fail-loud 串到不了用户),
    # 且 > 心跳间隔(否则第一拍就超时、发不出心跳)。所有 override 同样受约束。
    assert 0 < ae._TOOL_HEARTBEAT_INTERVAL_S < ae._TOOL_TIMEOUT_DEFAULT_S < 300
    for name, budget in ae._TOOL_TIMEOUT_OVERRIDES.items():
        assert ae._TOOL_HEARTBEAT_INTERVAL_S < budget < 300, (
            f"{name} 超时预算 {budget}s 越界(须 ∈ (心跳间隔, 300))"
        )
