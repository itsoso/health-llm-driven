"""v3 Output Validator — MVP 只做前 3 项 (规则, 无 LLM).

六项职责 (MVP 前 3 项, 其余 TODO):
1. Schema 校验 — Pydantic strict (已由 planner 输出的 Pydantic 模型保证)
2. 黑名单拦截 — regex 禁词
3. Disclaimer 注入 — 命中灰/黑名单 → 自动附 disclaimer + 转介

4-6 留到 v2: evidence_id 校验 / 数值范围校验 / 医疗越界 LLM Critic.

v3 cross-cutting: validate_text() 给 orchestrator / agent_executor 等所有
LLM 终态文本输出统一过一遍 (不只是 ActionGraph). 这是 v3 "Safety as
cross-cutting concern" 的落地: SafetyGuardian specialist 仍跑结构化规则,
此处补上"任意 LLM 自由文本"维度.
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

# 灰名单: 涉医/涉药关键词 → 不阻断, 但触发 disclaimer
_GRAYLIST_KEYWORDS = ("药", "补剂", "痛", "症状", "剂量", "副作用", "病")

_DISCLAIMER = "温馨提示: 以上建议仅为运动恢复参考, 非医疗处方. 如症状持续或加重, 请咨询医生."

# 文本被硬拦截后, 替换为安全兜底 (避免泄露原 LLM 输出)
_BLOCKED_FALLBACK = (
    "这个问题涉及具体医疗判断, 已超出我作为健康助理的安全边界. "
    "请咨询您的主治医生或拨打 12320 卫生热线."
)


@dataclass
class ValidationResult:
    ok: bool
    blocked_actions: List[int] = field(default_factory=list)  # action index 列表
    disclaimer: str = ""
    notes: List[str] = field(default_factory=list)


@dataclass
class TextValidationResult:
    """validate_text() 的结果. 调用方根据 action 字段决定如何处理:
    - 'pass': 原文直接用
    - 'append_disclaimer': 原文末尾 + '\n\n' + disclaimer
    - 'replace': 整体替换为 _BLOCKED_FALLBACK + disclaimer (硬拦截)
    """
    ok: bool                # False = 命中黑名单, 必须替换
    action: str             # 'pass' | 'append_disclaimer' | 'replace'
    safe_text: str          # 已经处理过的最终安全文本 (调用方直接用)
    disclaimer: str = ""    # 非空 → 客户端需展示
    matched_terms: List[str] = field(default_factory=list)  # 命中的禁/灰名词, 审计用


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

        # 灰名单: 涉医/涉药关键词 → 不阻断, 但触发 disclaimer
        if any(kw in text for kw in _GRAYLIST_KEYWORDS):
            needs_disclaimer = True

    if result.blocked_actions:
        result.ok = False

    if needs_disclaimer:
        result.disclaimer = _DISCLAIMER

    return result


def validate_text(text: str) -> TextValidationResult:
    """v3 cross-cutting: 给任意 LLM 自由文本做安全校验.

    设计取舍:
    - 黑名单命中 → 整体替换 (不要泄露原文, 哪怕只有一句越界).
    - 灰名单命中 → 保留原文 + 末尾 disclaimer (不影响主信息).
    - 都不命中 → 原文直传 (零开销).

    空字符串 / None 直接 pass (上游 LLM 失败的兜底, 不在本层处理).
    """
    if not text or not text.strip():
        return TextValidationResult(ok=True, action="pass", safe_text=text or "")

    matched: List[str] = []

    # 黑名单 = 硬拦截
    blocked = _BLACKLIST.findall(text)
    if blocked:
        matched.extend(set(blocked))
        safe = f"{_BLOCKED_FALLBACK}\n\n{_DISCLAIMER}"
        logger.warning(
            "[validator.text] 黑名单拦截 terms=%s text_head=%r",
            list(set(blocked))[:3], text[:80],
        )
        return TextValidationResult(
            ok=False, action="replace",
            safe_text=safe, disclaimer=_DISCLAIMER,
            matched_terms=matched,
        )

    # 灰名单 = 加 disclaimer
    gray_hits = [kw for kw in _GRAYLIST_KEYWORDS if kw in text]
    if gray_hits:
        matched.extend(gray_hits)
        return TextValidationResult(
            ok=True, action="append_disclaimer",
            safe_text=f"{text}\n\n{_DISCLAIMER}",
            disclaimer=_DISCLAIMER,
            matched_terms=matched,
        )

    return TextValidationResult(ok=True, action="pass", safe_text=text)
