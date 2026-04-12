"""
Recovery Coach —— L3 恢复教练 specialist。

职责：
- 读 Twin 的生理状态（HRV/睡眠/压力/body battery）+ 训练负荷
- 计算当日 readiness score (0-100)
- 输出具体的恢复建议和今日活动强度推荐

为什么不用 LLM 算 readiness：
- readiness 是数学函数，不是判断题
- 可复现、可审计、可 A/B 校准
- LLM 只负责把 finding 翻译成人话（orchestrator 层做）
"""

from app.agents.recovery_coach.coach import (
    RecoveryCoachSpecialist,
    compute_readiness,
)

__all__ = ["RecoveryCoachSpecialist", "compute_readiness"]
