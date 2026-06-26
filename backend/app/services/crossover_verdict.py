"""R16 P4 —— A·B·A·B 交叉实验:重复感知裁决(N-of-1 唯一能「确认效果」的一环)。

P1-P3 只能诚实地**降级**(单点/稀疏/洗脱 → 封 low),永远给不出「这个干预对你确实有效」。交叉
(反复 on/off 同一干预)是 N-of-1 的金标准:若指标在「on」相一致优于相邻「off」相、且重复 ≥2 次
→ 是真实重复出现的效应(而非趋势/噪声)。本模块据各相 (arm, level) 给重复感知裁决。

治理护栏(同 R16 全程):
- **处方/激素门控指标永不出重复裁决** —— 哪怕重复,仍被并行处方药混杂 → clinician_review。
- **相关非因果 + 封顶 moderate**:N-of-1 无盲、无随机(除用户自身序列)、单受试 → 即便干净重复也只
  到 moderate,措辞描述式(「on 相一致优于 off 相」),绝不下「证明/治愈」。这是 R16 唯一能把置信度
  抬过 low 的一环,但抬到 moderate 封顶,gated 永不抬。
- 重复不足(on<2 或 off<2)→ insufficient + low。基因无关(只按 arm/level/metric_code)。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ATTRIBUTION = "temporal_association_not_causation"


def _min_effect(metric_code: str, cycle_type: str = "metabolic_90d") -> float:
    """该指标可信效应下限 = max(mcid, √2·obs_noise) —— 既要临床意义、又要超单次测量噪声。
    复用 intervention_priors 的 per-metric 参数(别复制阈值);未登记 → DEFAULT_PRIOR(保守)。"""
    from app.services.personal_models.intervention_priors import get_prior

    p = get_prior(cycle_type, metric_code)
    return max(p.mcid, (2 ** 0.5) * p.obs_noise)


def _arm_transitions(phases: List[Dict[str, Any]]) -> int:
    """相序里 on↔off 切换次数 —— 真交叉的强度在「反复反转」,而非 A/A/B/B 块状。"""
    arms = [p["arm"] for p in phases if p.get("arm") in ("on", "off") and p.get("level") is not None]
    return sum(1 for i in range(1, len(arms)) if arms[i] != arms[i - 1])


def replication_verdict(
    phases: List[Dict[str, Any]], metric_code: str, direction: str = "down",
) -> Dict[str, Any]:
    """phases: [{"arm": "on"/"off", "level": float}] 顺序无关(按 arm 分组)。

    返回 {verdict, confidence, requires_clinician, n_on, n_off, mean_on, mean_off, attribution}。
    verdict ∈ replicated / suggestive / not_replicated / insufficient / clinician_review。
    """
    # 单一事实源(并发 561b4764 确立):所有效应估计器共用 is_clinician_gated_metric,别复制门控逻辑。
    from app.services.personal_models.intervention_priors import is_clinician_gated_metric

    gated = is_clinician_gated_metric(metric_code or "")
    on = [p["level"] for p in phases if p.get("arm") == "on" and p.get("level") is not None]
    off = [p["level"] for p in phases if p.get("arm") == "off" and p.get("level") is not None]

    out: Dict[str, Any] = {
        "n_on": len(on),
        "n_off": len(off),
        "mean_on": round(sum(on) / len(on), 3) if on else None,
        "mean_off": round(sum(off) / len(off), 3) if off else None,
        "attribution": ATTRIBUTION,
    }

    # 门控:处方/激素指标即便重复也仍混杂 → 永不出效应裁决
    if gated:
        return {**out, "verdict": "clinician_review", "confidence": "clinician_review",
                "requires_clinician": True}

    # 重复不足:需各 ≥2 个 on/off 相才谈重复
    if len(on) < 2 or len(off) < 2:
        return {**out, "verdict": "insufficient", "confidence": "low", "requires_clinician": False}

    mean_on, mean_off = out["mean_on"], out["mean_off"]
    lower_better = direction != "up"  # 默认 down=降为好
    better = (mean_on < mean_off) if lower_better else (mean_on > mean_off)
    # 干净分离:所有 on 相都优于所有 off 相(无重叠)。
    clean = (max(on) < min(off)) if lower_better else (min(on) > max(off))
    # **效应量地板(对抗评审 BLOCKING)**:on/off 均值差必须 ≥ 该指标噪声/临床意义下限,否则纯测量
    # 抖动(如体重 0.2kg)会被叫「重复有效」=over-confidence(R16 唯一抬置信度的一环,失败方向就在此)。
    mean_sep = (mean_off - mean_on) if lower_better else (mean_on - mean_off)
    min_eff = _min_effect(metric_code)
    big_enough = mean_sep >= min_eff
    # **交替地板**:真交叉强度在反复反转,≥2 次 on↔off 切换才算重复出现(否则 A/A/B/B 块状=时间趋势混杂)。
    alternating = _arm_transitions(phases) >= 2
    out["min_effect"] = round(min_eff, 3)

    if better and clean and big_enough and alternating:
        verdict, conf = "replicated", "moderate"     # 干净 + 超噪声 + 真反复反转,描述式,封顶 moderate
    elif better:
        verdict, conf = "suggestive", "low"          # 有方向但 重叠 / 量级不足 / 非交替 → 不抬过 low
    else:
        verdict, conf = "not_replicated", "low"      # 无一致效应(on 不优于 off)
    return {**out, "verdict": verdict, "confidence": conf, "requires_clinician": False}
