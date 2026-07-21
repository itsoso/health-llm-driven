"""
LLM 仲裁层 v1 — cross_review 检测到 hard conflict 时升级 LLM 裁决.

设计原则:
  - 成本可控: 只对 hard conflicts 或 >= 2 个 conflicts 才调 LLM
  - 结构化输出: 要求 LLM 返回 JSON, 便于写 audit_log + trace UI
  - Fail-soft: LLM 失败回退到 prompt-based cross_review 渲染 (现有行为)

角色:
  裁决员不是"新建议生成器", 是"在已有 specialist 建议间选择 + 解释为什么".
  这让 AI 的判断对用户/医生可追溯 (B 端可解释性门槛).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from app.orchestrator.cross_review import Conflict
from app.orchestrator.schema import SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


@dataclass
class ArbitrationResult:
    """LLM 一次仲裁的结构化结果."""
    winning_side: str              # 'specialist_a' | 'specialist_b' | 'both' | 'neither'
    rationale: str                 # 为什么这样裁决 (3-5 句)
    final_recommendation: str      # 给用户的最终行动建议
    caveats: List[str] = field(default_factory=list)  # 注意事项 / 风险提醒
    confidence: float = 0.7        # LLM 对自己裁决的置信度 [0,1]
    conflicts_addressed: int = 0   # 这次仲裁覆盖了几个冲突

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _should_arbitrate(conflicts: List[Conflict]) -> bool:
    """决定是否触发 LLM 仲裁. 成本门槛:
      - 至少 1 个 hard 冲突, 或
      - >= 2 个冲突 (总数)
    """
    if not conflicts:
        return False
    hard = sum(1 for c in conflicts if c.severity == "hard")
    if hard >= 1:
        return True
    return len(conflicts) >= 2


def _build_arbitration_prompt(
    conflicts: List[Conflict],
    findings: List[SpecialistFinding],
    twin: HealthTwin,
) -> tuple[str, str]:
    """构造仲裁 prompt. 返回 (system, user)."""
    system = (
        "你是一位健康建议仲裁员. specialist 层 (营养/代谢/训练/鼻炎 等) 各自给出了建议, "
        "但 cross-review 发现冲突. 你的任务: 基于用户真实 Twin 数据, "
        "在冲突建议间给出**结构化裁决**.\n\n"
        "输出严格 JSON (无其他文字):\n"
        "{\n"
        '  "winning_side": "specialist_a" | "specialist_b" | "both" | "neither",\n'
        '  "rationale": "3-5 句裁决理由, 必须引用用户真实数据",\n'
        '  "final_recommendation": "给用户的一句可执行建议",\n'
        '  "caveats": ["注意1", "注意2"],\n'
        '  "confidence": 0.0-1.0 (你对自己裁决的置信度)\n'
        "}\n\n"
        "原则:\n"
        "- 如果一方明显更保守/安全, 选它 (winning_side=specialist_a 或 specialist_b)\n"
        "- 如果两方都对但适用条件不同, both\n"
        "- 如果两方都有问题, neither, 并在 caveats 建议咨询医生\n"
        "- 合规: **不构成医疗建议**. final_recommendation 必须避免诊断性措辞.\n"
    )

    # 组装冲突描述
    conflicts_desc = []
    for i, c in enumerate(conflicts, 1):
        conflicts_desc.append(
            f"### 冲突 {i} ({c.severity.upper()})\n"
            f"- specialist_a: **{c.specialist_a}**\n"
            f"- specialist_b: **{c.specialist_b}**\n"
            f"- 矛盾: {c.description}\n"
            f"- 现有规则建议: {c.resolution_hint}"
        )

    # 抽相关 specialist findings 摘要
    relevant_names: set = set()
    for c in conflicts:
        relevant_names.add(c.specialist_a)
        relevant_names.add(c.specialist_b)
    findings_desc = []
    for f in findings:
        if f.specialist_name in relevant_names:
            summary = (f.summary or "")[:300]
            findings_desc.append(f"**{f.specialist_name}**: {summary}")

    # 抽 Twin 关键指标 (精简, 避免 prompt 膨胀)
    twin_digest = []
    try:
        if twin.physiological:
            phys = twin.physiological
            hrv = getattr(phys, "hrv_latest", None) or getattr(phys, "hrv_7d_avg", None)
            rhr = getattr(phys, "resting_hr", None)
            sleep = getattr(phys, "sleep_score_latest", None)
            if hrv is not None: twin_digest.append(f"HRV={hrv}")
            if rhr is not None: twin_digest.append(f"RHR={rhr}")
            if sleep is not None: twin_digest.append(f"睡眠评分={sleep}")
        if twin.labs and getattr(twin.labs, "indicators", None):
            # 只取异常的 labs
            abnormal = [
                f"{it.name}={it.value}{it.unit or ''}"
                for it in (twin.labs.indicators or [])[:10]
                if getattr(it, "is_abnormal", False)
            ]
            if abnormal:
                twin_digest.append(f"异常化验: {', '.join(abnormal)}")
        if twin.meds and getattr(twin.meds, "active", None):
            meds = [m.name for m in twin.meds.active[:6] if getattr(m, "name", None)]
            if meds:
                twin_digest.append(f"在服药物: {', '.join(meds)}")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[arbitration] twin digest fail: {e}")

    user_parts = [
        "## 检测到的冲突\n" + "\n\n".join(conflicts_desc),
    ]
    if findings_desc:
        user_parts.append("## 涉及的 specialist 建议\n" + "\n\n".join(findings_desc))
    if twin_digest:
        user_parts.append("## 用户关键数据\n" + "; ".join(twin_digest))

    return system, "\n\n".join(user_parts)


def _parse_arbitration_response(text: str, conflicts_count: int) -> Optional[ArbitrationResult]:
    """从 LLM 返回文本里提 JSON → ArbitrationResult. 失败返回 None."""
    if not text:
        return None
    # 尝试: 直接 json.loads (如果 LLM 遵守了只输出 JSON)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # 回退: 正则抓第一个 { ... }
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            logger.warning("[arbitration] LLM 响应无 JSON 块 response_len=%s", len(text))
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            logger.warning(
                "[arbitration] JSON parse 失败 error_type=%s position=%s response_len=%s",
                type(e).__name__,
                getattr(e, "pos", None),
                len(text),
            )
            return None

    try:
        winning = str(obj.get("winning_side", "neither"))
        if winning not in {"specialist_a", "specialist_b", "both", "neither"}:
            winning = "neither"
        conf_raw = obj.get("confidence", 0.7)
        try:
            conf = float(conf_raw)
        except (TypeError, ValueError):
            conf = 0.7
        conf = max(0.0, min(1.0, conf))
        caveats_raw = obj.get("caveats") or []
        caveats = [str(c)[:200] for c in caveats_raw if c][:5]
        return ArbitrationResult(
            winning_side=winning,
            rationale=str(obj.get("rationale", ""))[:800],
            final_recommendation=str(obj.get("final_recommendation", ""))[:500],
            caveats=caveats,
            confidence=conf,
            conflicts_addressed=conflicts_count,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[arbitration] 解析字段失败: {e}")
        return None


async def arbitrate_conflicts(
    conflicts: List[Conflict],
    findings: List[SpecialistFinding],
    twin: HealthTwin,
    llm_caller,
) -> Optional[ArbitrationResult]:
    """主入口. llm_caller 是 async (system_prompt, user_prompt) -> str.

    不触发 LLM 的情况返回 None (调用方回退到 prompt-based cross_review).
    """
    if not _should_arbitrate(conflicts):
        return None

    system, user = _build_arbitration_prompt(conflicts, findings, twin)
    try:
        text = await llm_caller(system, user)
    except Exception as e:  # noqa: BLE001
        logger.warning("[arbitration] LLM 调用异常 error_type=%s", type(e).__name__)
        return None

    result = _parse_arbitration_response(text, len(conflicts))
    if result is None:
        logger.warning(
            "[arbitration] 解析失败, 回退 conflicts=%s response_len=%s",
            len(conflicts),
            len(text) if text else 0,
        )
    return result


def render_arbitration_for_prompt(result: ArbitrationResult) -> str:
    """LLM 仲裁结果渲染到 orchestrator 合成 prompt. 比 cross_review 更权威."""
    side_label = {
        "specialist_a": "采纳 specialist_a 方案",
        "specialist_b": "采纳 specialist_b 方案",
        "both": "两方都可, 按条件分场景",
        "neither": "两方都不采纳, 升级人工医师",
    }.get(result.winning_side, result.winning_side)

    lines = [
        "## 🤝 LLM 仲裁裁决 (已处理 cross-review 冲突)",
        f"- **裁决**: {side_label} (conf={result.confidence:.2f})",
        f"- **理由**: {result.rationale}",
        f"- **建议**: {result.final_recommendation}",
    ]
    if result.caveats:
        lines.append("- **注意**:")
        for cv in result.caveats:
            lines.append(f"  - {cv}")
    return "\n".join(lines)
