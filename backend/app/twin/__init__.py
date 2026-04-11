"""
Digital Health Twin — 用户的实时健康状态视图。

架构定位：
- 位于 service 层之上，api 层之下
- 由 api/twin.py 暴露为 GET /api/v1/twin/me
- 所有 agent 读 Twin，不再各自拼装 context
- 组装逻辑只依赖 service 层函数（_collectors.py 是过渡期的薄 SQL 层）

不要做的事：
- 不在这里写业务规则、LLM 调用、告警裁决 —— 那是上层 agent 的职责
- 不在这里持久化 —— Twin 是派生视图，不是新数据
"""

from app.twin.schema import HealthTwin
from app.twin.builder import build_twin

__all__ = ["HealthTwin", "build_twin"]
