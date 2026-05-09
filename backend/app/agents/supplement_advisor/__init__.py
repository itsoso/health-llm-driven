"""
Supplement Advisor —— L3 补剂策略 specialist (Agent-Native v3 Episode 闭环).

职责：
- 读 Twin 的 genetic.nutrition_variants + labs.flagged_abnormal + medication
- 基于 SNP 矩阵推荐补剂（MTHFR / APOE / HFE / FADS1 / COMT / VDR 优先）
- 调 Safety Guardian 做 DDI/DSI 检查
- HFE C282Y 纯合 → 硬阻断铁补剂
- 输出 ProposedCard：N-of-1 试用方案 (4 周/12 周后用 lab/HRV 评分)

合规：免责声明字段, 不做 "诊断" / "处方", 用 "健康参考" 措辞.
"""

from app.agents.supplement_advisor.advisor import SupplementAdvisorSpecialist

__all__ = ["SupplementAdvisorSpecialist"]
