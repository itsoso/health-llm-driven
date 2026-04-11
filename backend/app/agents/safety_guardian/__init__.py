"""
Safety Guardian —— L1 安全层。

职责：
- 基于确定性规则（非 LLM）对用户当下状态做安全裁决
- 覆盖：药物-药物 / 药物-补剂 / 药物-基因 / 急性阈值 / 化验异常升级 / 训练负荷
- 规则引擎 + 单一 Twin 输入 → 结构化 Alert 列表

为什么是规则而非 LLM：
- 安全裁决不能依赖幻觉（例如药物相互作用、基因敏感位点）
- 必须可审计、可追溯、可复现
- 规则可以被医学文献背书，LLM 不行
- LLM 只做可选的自然语言解释层（Phase 1.5）
"""

from app.agents.safety_guardian.guardian import evaluate_safety
from app.agents.safety_guardian.schema import Alert, Severity

__all__ = ["Alert", "Severity", "evaluate_safety"]
