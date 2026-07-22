"""
Orchestrator —— 用户面对的"大脑"。

职责：
- 接收用户查询 + 当前 Twin
- 路由到相关 specialist agent (SafetyGuardian / RecoveryCoach / FuelStrategist...)
- 收集结构化 finding
- LLM 综合合并 → 流式返回

设计约束：
- 与现有 Agent 主链路共存，按灰度替换（避免风险）
- 每次对话都从 Twin 读取最新状态
- 调度结果可审计：返回 used_specialists / findings / timing
- LLM 失败时降级为纯专家结构化输出（不完美但不坏）
"""

from app.orchestrator.schema import (
    Intent,
    OrchestratorRequest,
    OrchestratorResponse,
    SpecialistFinding,
)

__all__ = [
    "Intent",
    "OrchestratorRequest",
    "OrchestratorResponse",
    "SpecialistFinding",
    "run_orchestrator",
    "stream_orchestrator",
]


def __getattr__(name: str):
    """Load the orchestration runtime only when a public runner is requested.

    Specialist modules import ``app.orchestrator.schema`` during worker startup.
    Eagerly importing the runtime here rebuilds the specialist registry while the
    specialist itself is only partially initialized, producing a circular import.
    """
    if name in {"run_orchestrator", "stream_orchestrator"}:
        from app.orchestrator.orchestrator import run_orchestrator, stream_orchestrator

        return {
            "run_orchestrator": run_orchestrator,
            "stream_orchestrator": stream_orchestrator,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
