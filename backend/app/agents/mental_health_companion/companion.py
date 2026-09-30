"""
Mental Health Companion —— 基于 Twin.mental 的支持性建议。

输出三类 finding:
  - mental_state: 7 日均值 + 与基线偏离
  - physiological_link: 心理和生理的关联（HRV/睡眠/压力）
  - support_action: 非药物支持动作（呼吸/走路/光照/社交）

如果检测到可能的心理危机模式（mood_7d < 3 + energy 同时下降，或本轮原话含
轻生/自伤意念表达），单独输出 crisis_warning，建议联系真人专业帮助或危机热线。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.orchestrator.schema import Intent, SpecialistFinding
from app.services.crisis_lexicon import (
    CRISIS_HOTLINES,
    CRISIS_SUPPORT_LEAD,
    contains_crisis_language,
    crisis_hotline_summary,
)
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


def _safe(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ─────────────────────── 基因心理档案 ────────────────────────


def _gene_mental_profile(twin: HealthTwin) -> List[Dict[str, Any]]:
    """从 Twin.genetic 派生心理/个性相关基因洞察。"""
    results: List[Dict[str, Any]] = []
    all_variants = (
        (twin.genetic.drug_sensitivity or [])
        + (twin.genetic.risk_variants or [])
        + (twin.genetic.protective_variants or [])
        + (twin.genetic.cognition_variants or [])
        + (twin.genetic.personality_variants or [])
    )
    by_gene: Dict[str, Dict[str, Any]] = {}
    for v in all_variants:
        name = (v.get("gene_name") or "").upper()
        if name:
            by_gene.setdefault(name, v)

    comt = by_gene.get("COMT")
    if comt:
        geno = (comt.get("genotype") or "").upper()
        if "VAL/VAL" in geno:
            results.append({"type": "gene_mental", "gene": "COMT", "profile": "战士型(Val/Val)",
                "tip": "多巴胺清除快→压力下表现稳定，适合高强度运动释放；但基础多巴胺偏低，注意保持新鲜感和奖励循环。"})
        elif "MET/MET" in geno:
            results.append({"type": "gene_mental", "gene": "COMT", "profile": "思考者型(Met/Met)",
                "tip": "多巴胺清除慢→创造力高但易焦虑；减少咖啡因、增加冥想和有氧运动（促进COMT活性），避免多任务并行。"})

    bdnf = by_gene.get("BDNF")
    if bdnf:
        geno = (bdnf.get("genotype") or "").upper()
        if "MET" in geno:
            results.append({"type": "gene_mental", "gene": "BDNF", "profile": "Val66Met携带",
                "tip": "海马体BDNF分泌减少→有氧运动是最强的天然BDNF促进剂，每周150min中等有氧可部分弥补。"})

    drd2 = by_gene.get("DRD2")
    if drd2 and (drd2.get("risk_level") or "").lower() in ("medium", "high"):
        results.append({"type": "gene_mental", "gene": "DRD2", "profile": "奖赏敏感增高",
            "tip": "多巴胺受体密度偏低→对奖赏信号更敏感→注意控制糖/酒精/手机等快感源，用运动和社交替代。"})

    tph2 = by_gene.get("TPH2")
    if tph2 and (tph2.get("risk_level") or "").lower() in ("medium", "high"):
        results.append({"type": "gene_mental", "gene": "TPH2", "profile": "血清素合成偏低",
            "tip": "情绪波动风险增高→有氧运动+ω-3(EPA≥1g/d)+早晨光照是三大天然血清素提升手段。"})

    slc6a4 = by_gene.get("SLC6A4")
    if slc6a4 and (slc6a4.get("risk_level") or "").lower() in ("medium", "high"):
        results.append({"type": "gene_mental", "gene": "SLC6A4", "profile": "焦虑易感(5-HTTLPR短臂)",
            "tip": "血清素回收减弱→负面情绪敏感性高→正念冥想+规律运动+充足日照对你效果比一般人更显著。"})

    oxtr = by_gene.get("OXTR")
    if oxtr:
        geno = (oxtr.get("genotype") or "").upper()
        if "GG" in geno:
            results.append({"type": "gene_mental", "gene": "OXTR", "profile": "高共情/社交驱动型(GG)",
                "tip": "催产素受体高表达→社交需求强、共情能力强，但孤独时心理风险高于平均→确保每天有真人互动。"})
        elif "AA" in geno:
            results.append({"type": "gene_mental", "gene": "OXTR", "profile": "独立型(AA)",
                "tip": "催产素受体低表达→独立性强、不依赖社交也能稳定→但主动练习共情可拓展社交资源。"})

    return results[:5]


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
        if contains_crisis_language(q):
            return True
        # 兜底：心理数据存在时参与 dashboard 场景
        if "general" in intent.categories and twin.mental.mood_7d_avg is not None:
            return True
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        # 在 try 之外判定:后续任何步骤失败都不能吞掉危机提示。
        # 原话只在此做关键词识别(Tier 5),finding 只给中性信号标签,不回显原文。
        crisis_language = contains_crisis_language(
            context.get("query") if isinstance(context, dict) else None
        )
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

            # 2. 危机信号检测:签到数值 + 本轮原话里的轻生/自伤表达。
            crisis = _detect_crisis(mood, energy, sleep_q)
            if crisis_language:
                crisis.append(_CRISIS_LANGUAGE_SIGNAL)
                findings.append(_crisis_language_warning(crisis))
            elif crisis:
                findings.append({
                    "type": "crisis_warning",
                    "severity": "high",
                    # 与 SafetyGuardian 的 HIGH 中文标签一致(分段合成按它排严重度)。
                    "severity_label": "警告",
                    "signals": crisis,
                    "title": "近 7 天情绪与精力持续偏低：关注安全，必要时联系专业支持",
                    "message": (
                        "系统识别到你最近情绪和精力都明显偏低。这不是需要你独自扛的。"
                        "如果感到难以承受，请联系可信赖的朋友、家人，或拨打心理援助热线："
                    ),
                    "hotlines": [dict(h) for h in CRISIS_HOTLINES],
                    "action": (
                        "今天不需要任何人勉强自己，只需要做一件能让自己感到稍微好一点的小事；"
                        f"如果感到难以承受，可以拨打心理援助热线：{crisis_hotline_summary()}。"
                    ),
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

            # 5. 基因心理档案
            gene_insights = _gene_mental_profile(twin)
            findings.extend(gene_insights)

            summary = " · ".join(summary_parts) if summary_parts else "心理数据暂缺"
            if crisis_language:
                summary = f"{_CRISIS_LANGUAGE_SUMMARY} · {summary}"
            elif crisis:
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
                    "has_crisis_language": crisis_language,
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[mental_health_companion] run failed: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=(
                    f"{_CRISIS_LANGUAGE_SUMMARY} · 心理评估失败: {e}"
                    if crisis_language
                    else f"心理评估失败: {e}"
                ),
                findings=(
                    [_crisis_language_warning([_CRISIS_LANGUAGE_SIGNAL])]
                    if crisis_language
                    else []
                ),
                raw={
                    "error": str(e),
                    "has_crisis_signal": crisis_language,
                    "has_crisis_language": crisis_language,
                },
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


_CRISIS_LANGUAGE_SIGNAL = "对话中出现轻生/自伤相关表达"
# summary 会进临床日志 SOAP 与医生报告:用中性、可能性措辞。
_CRISIS_LANGUAGE_SUMMARY = "⚠️ 对话中可能出现轻生相关表达，需先确认安全并提供心理援助热线"


def _crisis_language_warning(signals: List[str]) -> Dict[str, Any]:
    """原话含轻生/自伤表达时的危机提示。

    orchestrator 合成 prompt 只渲染 severity_label / title / action,所以热线与急救
    指引必须写进 action;message + hotlines 供客户端危机卡片展示。Web「专家裁决」
    折叠区也直接展示 title:措辞须同时适合模型与用户阅读,且对误报(夸张说法)温和。
    """
    return {
        "type": "crisis_warning",
        "severity": "high",
        "severity_label": "紧急",
        "signals": signals,
        "title": "对话中可能出现轻生相关表达：先温和确认安全并给出热线，再简要回应原问题",
        "message": CRISIS_SUPPORT_LEAD,
        "hotlines": [dict(h) for h in CRISIS_HOTLINES],
        "action": (
            "先确认此刻是否安全；如有伤害自己的打算或已处于危险中，立即拨打 120 或 110；"
            f"心理援助热线：{crisis_hotline_summary()}；并联系一位信任的人陪在身边。"
        ),
    }


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
