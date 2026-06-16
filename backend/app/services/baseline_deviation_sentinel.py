"""王牌③「静息 HR 漂移哨兵」(R18)。

把 ``personal_baseline`` 的个人 z-score 引擎产出的「RHR 偏离自身基线」转成一条
**中性、标非因果**的归因候选 advisory,注入今日议程(``agenda_service.today``),
自动流向 today_timeline / watch_summary。

定位(与已上线模块互补,采"加层不减层"——哨兵是安全网,不静默丢急性值):
  - SafetyGuardian ``vitals.rhr_tachycardia``(≥100)/ ``vitals.rhr_bradycardia``(<40)=
    **绝对阈值规则**,均为 ``Severity.MEDIUM``(非 CRITICAL、不带 requires_medical_attention),
    且读 ``twin.physiological.resting_hr``(最新日期行,那天 RHR 可能 NULL → None →
    急性规则 early-return 不告警)。
  - 本哨兵 = **相对个人基线的软漂移**(z-score),latest 取窗口内 ``clean[-1]``(最后一个
    有 RHR 的日)。两路「latest」语义不一致,数据不同步时急性 RHR 可能两路全漏。
  - 因此哨兵**永不对急性值静默跳过**:无论急性与否都产 advisory,按严重度升级 detail 文案、
    带就医出口,做"加一层安全网",而非依赖下游接管的"减一层"。

设计:王牌③先只做 RHR(``SENTINEL_METRICS`` 可扩);措辞严守 PRD —— 中性因素类目、
标「相关,非因果」、严禁诊断/疾病词;就医出口只用「建议就医排查 / 偏离正常范围 /
筛查非诊断」,不出现 感染/炎症/疾病/确诊/治疗。

降级(守 AGENTS.md Rule #1):基线计算失败 → 记 warning 后返回 ``[]``,不破坏议程。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.personal_baseline import MetricBaseline, compute_personal_baselines

logger = logging.getLogger(__name__)

# 王牌③先只哨兵 RHR;扩别的指标只需往这里加 key(必须是 personal_baseline 已产出的 key)。
SENTINEL_METRICS = {"resting_heart_rate"}

# 急性绝对界:撞界 → **升级 detail 带就医出口**(不再静默跳过,见模块 docstring)。
# (low_exclusive, high_inclusive_floor):latest < low 或 latest >= high → 急性。
# 阈值来源对齐 backend/app/agents/safety_guardian/rules/vitals.py:
#   rhr_bradycardia: rhr < 40 → MEDIUM;rhr_tachycardia: rhr >= 100 → MEDIUM。
ACUTE_BOUNDS: Dict[str, tuple[float, float]] = {
    "resting_heart_rate": (40.0, 100.0),
}

# 归因邀请:中性因素类目 + 明确「非因果」。严禁诊断/疾病/治疗词。
ATTRIBUTION_INVITE = (
    "可回看近期睡眠 / 训练 / 饮酒 / 压力,帮你看清相关因素(相关,非因果)"
)

# 升级文案:就医出口只用「建议就医排查 / 偏离正常范围 / 筛查非诊断」,严禁禁词。
_ACUTE_SUFFIX = " · 静息心率已明显偏离正常范围,建议尽快就医排查(本提示为筛查,非诊断)"
_PERSIST_SUFFIX = " · 若持续数日不回落,建议就医排查"

# advisory 优先级:介于 data_quality(70)/correction(72-74) 附近,info 档。
_PRIORITY = 68


def _is_acute(mb: MetricBaseline) -> bool:
    """latest 撞急性绝对界 → True。无界 / latest None → False。"""
    bounds = ACUTE_BOUNDS.get(mb.key)
    if bounds is None or mb.latest is None:
        return False
    low, high = bounds
    return mb.latest < low or mb.latest >= high


def _escalation_suffix(mb: MetricBaseline) -> str:
    """按严重度给就医出口后缀(加层安全网,不依赖下游接管)。

    急性(latest 撞 ``ACUTE_BOUNDS``,RHR ≥100 或 <40)→ 尽快就医。
    持续亚急性(有方向漂移且高置信)→ 若持续数日不回落则就医。
    否则(单次抖动 / 置信不足)→ 不升级,只软 info。
    """
    if _is_acute(mb):
        return _ACUTE_SUFFIX
    if mb.trend in ("rising", "falling") and not mb.low_confidence:
        return _PERSIST_SUFFIX
    return ""


def _to_advisory(mb: MetricBaseline, user_id: int) -> Dict[str, Any]:
    """单条 MetricBaseline → 议程 advisory(对齐 agenda advisory 模式)。

    ``status="info"`` 渲染语义不变;升级体现在 detail 的就医出口(under-alarm 修复点)。
    """
    suffix = _escalation_suffix(mb)
    # 急性但非统计偏离时 mb.message 为 None(_deviation_message 只在 is_deviation 时填),
    # 直接 f-string 会渲染字面 "None"。兜底用 latest 合成一句(latest 必非空,因为已判急性)。
    base = mb.message or f"{mb.label}当前 {mb.latest:.0f}{mb.unit}"
    return {
        "type": "baseline_deviation",
        "title": f"{mb.label}偏离个人基线",
        "status": "info",
        "time_window": "anytime",
        "priority": _PRIORITY,
        "detail": f"{base} · {ATTRIBUTION_INVITE}{suffix}",
        "metric": mb.key,
        "z": round(mb.z, 2) if mb.z is not None else None,
        "low_confidence": mb.low_confidence,
        "source": {"object_type": "baseline_deviation", "object_id": user_id},
    }


def deviation_advisories(
    db: Session,
    user_id: int,
    *,
    today=None,
) -> List[Dict[str, Any]]:
    """RHR(及未来扩展指标)偏离个人基线 → 归因候选 advisory 列表。

    取 ``SENTINEL_METRICS`` 内、``is_deviation`` **或** 撞 ``ACUTE_BOUNDS`` 急性界
    任一成立的指标。**急性值即使非统计偏离也不跳过**(基线本身高且方差大时 z 可能
    <2 → ``is_deviation=False``,旧门序会静默丢急性值,即 under-alarm 洞):急性值
    破 ``is_deviation`` 门兜底产 advisory,由 ``_escalation_suffix`` 按严重度升级 detail
    文案带就医出口(加层安全网,见模块 docstring)。
    基线计算失败 → 降级返回 ``[]``,不破坏议程。
    """
    try:
        baselines: List[MetricBaseline] = compute_personal_baselines(
            db, user_id, today=today
        )
    except Exception as e:  # noqa: BLE001 — 哨兵失败不应拖垮议程(守 Rule #1)
        logger.warning(
            "[baseline_sentinel] 基线计算失败,跳过哨兵 user=%s: %s", user_id, e
        )
        return []

    advisories: List[Dict[str, Any]] = []
    for mb in baselines:
        if mb.key not in SENTINEL_METRICS:
            continue
        # 急性判定提到 is_deviation 门之前:急性值即使非统计偏离(基线本身高且方差大,
        # 如 mean=88/std=9,latest=101 → z≈1.44<2 → is_deviation=False)也要兜底产
        # advisory,堵 under-alarm 洞(见模块 docstring)。非偏离且非急性才跳过。
        acute = _is_acute(mb)
        if not mb.is_deviation and not acute:
            continue
        advisories.append(_to_advisory(mb, user_id))
    return advisories
