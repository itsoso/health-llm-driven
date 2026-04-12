"""
Movement Coach —— L3 运动教练 specialist。

职责：
- 读 Twin 的训练负荷（ACWR/7d load/workouts）+ 心肺（VO2max/RHR）+ 基因
- 综合 Recovery Coach 的 readiness（通过 context 传递）调节建议强度
- 输出今日训练处方（强度/类型/时长）+ 本周调整方向
"""

from app.agents.movement_coach.coach import MovementCoachSpecialist

__all__ = ["MovementCoachSpecialist"]
