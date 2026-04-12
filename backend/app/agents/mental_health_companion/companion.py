"""
Mental Health Companion —— 基于 Twin.mental 的支持性建议。

输出三类 finding:
  - mental_state: 7 日均值 + 与基线偏离
  - physiological_link: 心理和生理的关联（HRV/睡眠/压力）
  - support_action: 非药物支持动作（呼吸/走路/光照/社交）

如果检测到可能的心理危机模式（mood_7d < 3 + energy 同时下降），
单独输出 crisis_warning，建议联系真人专业帮助或危机热线。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.orchestrator.schema import Intent, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


def _safe(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class MentalHealthCompanionSpecialist:
    name = "mental_health_companion"
    category = "mental"

    TRIGGER_KEYWORDS = {
        "情绪", "心情", "压力大", "焦虑", "抑郁", "心理",
        "不开心", "沮丧", "低落", "烦躁", "睡不着",
        "压力", "紧张", "心烦",
        "mood", "stress", "anxiety", "depression", "sad", "mental",
    }

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        if "mental" in intent.categories:
            return True
        q = (intent.raw_query or "").lower()
        if any(k in q for k in self.TRIGGER_KEYWORDS):
            return True
        # 兜底：心理数据存在时参与 dashboard 场景
        if "general" in intent.categories and twin.mental.mood_7d_avg is not None:
            return True
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        try:
            m = twin.mental
            p = twin.physiological

            findings: List[Dict[str, Any]] = []
            summary_parts: List[str] = []

            mood = _safe(m.mood_7d_avg)
            energy = _safe(m.energy_7d_avg)
            stress = _safe(m.stress_7d_avg)
            sleep_q = _safe(m.sleep_quality_7d_avg)

            # 1. 心理状态聚合
            if any(v is not None for v in (mood, energy, stress, sleep_q)):
                findings.append({
                    "type": "mental_state",
                    "mood_7d": mood,
                    "energy_7d": energy,
                    "stress_7d": stress,
                    "sleep_quality_7d": sleep_q,
                })
                if mood is not None:
                    summary_parts.append(f"情绪 {mood:.1f}/10")
                if energy is not None:
                    summary_parts.append(f"精力 {energy:.1f}/10")
                if stress is not None:
                    summary_parts.append(f"压力 {stress:.1f}/10")

            # 2. 危机信号检测
            crisis = _detect_crisis(mood, energy, sleep_q)
            if crisis:
                findings.append({
                    "type": "crisis_warning",
                    "severity": "high",
                    "signals": crisis,
                    "message": (
                        "系统识别到你最近情绪和精力都明显偏低。这不是需要你独自扛的。"
                        "如果感到难以承受，请联系可信赖的朋友、家人，或拨打心理援助热线："
                    ),
                    "hotlines": [
                        {"name": "北京心理危机研究与干预中心", "number": "010-82951332"},
                        {"name": "全国心理援助热线", "number": "400-161-9995"},
                        {"name": "希望24热线", "number": "400-161-9995"},
                    ],
                    "action": "今天不需要任何人勉强自己，只需要做一件能让自己感到稍微好一点的小事。",
                })

            # 3. 生理-心理关联
            if p.hrv_latest and p.hrv_7d_avg and p.hrv_7d_avg > 0:
                ratio = p.hrv_latest / p.hrv_7d_avg
                if ratio < 0.85:
                    findings.append({
                        "type": "physiological_link",
                        "observation": (
                            f"HRV 最近一天 {p.hrv_latest:.0f} 低于 7 日均值 "
                            f"{p.hrv_7d_avg:.0f}，这是交感神经激活升高的生理信号，"
                            "与主观感到焦虑/紧张时的身体表现一致。"
                        ),
                        "action": "做一次 5 分钟的 4-7-8 慢呼吸（吸 4 秒 - 屏 7 秒 - 呼 8 秒），能在几分钟内激活副交感神经。",
                    })

            # 4. 支持性行动（非药物优先）
            actions = _build_support_actions(mood, energy, stress, sleep_q, p)
            for idx, act in enumerate(actions, 1):
                findings.append({
                    "type": "support_action",
                    "order": idx,
                    "text": act,
                })

            summary = " · ".join(summary_parts) if summary_parts else "心理数据暂缺"
            if crisis:
                summary = "⚠️ 识别到情绪低落信号 · " + summary

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=summary,
                findings=findings,
                raw={
                    "mood_7d": mood,
                    "energy_7d": energy,
                    "stress_7d": stress,
                    "has_crisis_signal": bool(crisis),
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[mental_health_companion] run failed: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"心理评估失败: {e}",
                findings=[],
                raw={"error": str(e)},
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )


# ────────────────────── helpers ──────────────────────


def _detect_crisis(
    mood: Optional[float],
    energy: Optional[float],
    sleep_q: Optional[float],
) -> List[str]:
    """启发式检测"需要专业帮助"的信号组合。保守为主。"""
    signals: List[str] = []
    if mood is not None and mood < 3:
        signals.append("情绪持续低于 3/10")
    if mood is not None and energy is not None and mood < 4 and energy < 4:
        signals.append("情绪和精力同时偏低")
    if mood is not None and sleep_q is not None and mood < 4 and sleep_q < 5:
        signals.append("情绪偏低伴睡眠质量差")
    return signals


def _build_support_actions(
    mood: Optional[float],
    energy: Optional[float],
    stress: Optional[float],
    sleep_q: Optional[float],
    phys,
) -> List[str]:
    """根据状态组装 2-4 条非药物支持行动。"""
    actions: List[str] = []

    # 通用护城河：每日最起码能做的事
    if (mood is not None and mood < 5) or (energy is not None and energy < 5):
        actions.append(
            "今天做一件能让你感觉稍微好一点的小事，不求完美：10 分钟散步、冲个澡、"
            "给一个朋友发条消息都算。"
        )

    # 压力高 → 呼吸/冷刺激
    if stress is not None and stress >= 6:
        actions.append(
            "压力偏高：做 5 分钟 4-7-8 呼吸 或 30 秒冷水洗脸，"
            "能在几分钟内把交感-副交感平衡拉回来。"
        )

    # 睡眠质量差 → 睡前卫生
    if sleep_q is not None and sleep_q < 6:
        actions.append(
            "睡眠质量偏低：今晚提前 30 分钟关屏，卧室温度调到 18-20°C，"
            "睡前 2 小时避免咖啡因和剧烈运动。"
        )

    # HRV 低 → 走路
    if phys.stress_level_current is not None and phys.stress_level_current >= 60:
        actions.append("生理压力值偏高：饭后 15 分钟慢走能显著降低应激激素。")

    # 光照 / 社交 是经过大样本验证的通用基础
    actions.append(
        "基础护城河：早上 10 分钟户外光照（不戴墨镜）+ 每天和真人说一次话"
        "（不用是深度对话），这两件事是情绪稳态最便宜的两个杠杆。"
    )

    return actions[:4]
