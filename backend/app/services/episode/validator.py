"""v3 Output Validator — MVP 只做前 3 项 (规则, 无 LLM).

六项职责 (MVP 前 3 项, 其余 TODO):
1. Schema 校验 — Pydantic strict (已由 planner 输出的 Pydantic 模型保证)
2. 黑名单拦截 — regex 禁词
3. Disclaimer 注入 — 命中灰/黑名单 → 自动附 disclaimer + 转介

4-6 留到 v2: evidence_id 校验 / 数值范围校验 / 医疗越界 LLM Critic.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import List

from app.services.episode.protocol_registry import ProtocolAction

logger = logging.getLogger(__name__)


# v3 黑名单: 诊断/处方/药物剂量调整 (General Wellness 红线).
_BLACKLIST = re.compile(
    r"(诊断|处方|胰岛素调整|降压药剂量|停药|确诊|治愈|推荐剂量|服药剂量|"
    r"加药|减药|换药|mg/kg)",
    re.IGNORECASE,
)

_DISCLAIMER = "温馨提示: 以上建议仅为运动恢复参考, 非医疗处方. 如症状持续或加重, 请咨询医生."


@dataclass
class ValidationResult:
    ok: bool
    blocked_actions: List[int] = field(default_factory=list)  # action index 列表
    disclaimer: str = ""
    notes: List[str] = field(default_factory=list)


def validate_actions(actions: List[ProtocolAction]) -> ValidationResult:
    """对 ActionGraph 做黑名单 + disclaimer 判定.

    返回:
      ok=True 不代表无 disclaimer, 只代表没触发硬拦截.
    """
    result = ValidationResult(ok=True)
    needs_disclaimer = False

    for idx, a in enumerate(actions):
        text = " ".join(filter(None, [a.title, a.body or ""]))
        if _BLACKLIST.search(text):
            result.blocked_actions.append(idx)
            result.notes.append(
                f"action[{idx}] '{a.template_id}' 命中黑名单, 阻断输出"
            )
            logger.warning("Validator 拦截 action %s: %s", a.template_id, text[:80])
            needs_disclaimer = True

        # 灰名单: 含"药"/"补剂"/"症状"等字样但不是硬禁 → 加 disclaimer
        if any(kw in text for kw in ("药", "补剂", "痛", "症状")):
            needs_disclaimer = True

    if result.blocked_actions:
        result.ok = False

    if needs_disclaimer:
        result.disclaimer = _DISCLAIMER

    return result
