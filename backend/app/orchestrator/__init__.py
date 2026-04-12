"""
Orchestrator —— 用户面对的"大脑"。

职责：
- 接收用户查询 + 当前 Twin
- 路由到相关 specialist agent (SafetyGuardian / RecoveryCoach / FuelStrategist...)
- 收集结构化 finding
- LLM 综合合并 → 流式返回

设计约束：
- 与 OpenClaw 共存，不是替换（避免风险）
- 每次对话都从 Twin 读取最新状态
- 调度结果可审计：返回 used_specialists / findings / timing
- LLM 失败时降级为纯专家结构化输出（不完美但不坏）
"""

from app.orchestrator.orchestrator import run_orchestrator, stream_orchestrator
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
