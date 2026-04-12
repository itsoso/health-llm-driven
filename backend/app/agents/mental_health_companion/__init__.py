"""
Mental Health Companion —— L3 心理陪伴 specialist。

核心原则：
1. **永远不做诊断**。抑郁/焦虑/躁郁等疾病只有精神科医生可以诊断。
2. **识别危机信号立即建议专业帮助**。
3. **非药物优先**。呼吸、运动、社交、晒太阳、冷暴露这些先于一切。
4. **隐私最高级**。日记文本不上传给外部 LLM，只在 specialist 内做关键词识别。
5. **情绪无好坏**。低落是信息，不是要"修复"的故障。

Tier 5 隐私约束：
  - 只读 twin.mental 聚合字段（mood_7d_avg 等数值）
  - 不读 twin 外部的原始日记文本
  - 输出的 finding 只含数值 + 非敏感建议，data_citation 不包含原文
"""

from app.agents.mental_health_companion.companion import MentalHealthCompanionSpecialist

__all__ = ["MentalHealthCompanionSpecialist"]
