"""
慢病专科 specialists —— 一病一 agent。

每个 specialist 聚焦一种慢病，使用 Twin 做状态评估 + 个性化行动建议。
与 Safety Guardian 不同：Safety Guardian 做确定性规则裁决（禁忌/阈值），
Chronic Specialists 做日常管理（趋势追踪、生活方式、复诊提醒）。

当前实现：
- RhinitisSpecialist: 过敏性鼻炎（已有 HealthCheckin 数据）
- HypertensionSpecialist: 高血压管理
- MetabolicSpecialist: 代谢健康（血糖/血脂/体重）
"""

from app.agents.chronic_specialists.hypertension import HypertensionSpecialist
from app.agents.chronic_specialists.metabolic import MetabolicSpecialist
from app.agents.chronic_specialists.rhinitis import RhinitisSpecialist

__all__ = [
    "HypertensionSpecialist",
    "MetabolicSpecialist",
    "RhinitisSpecialist",
]
