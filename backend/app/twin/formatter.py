"""
Twin → LLM context formatter。

为什么需要：
  所有 agent / LLM 都需要把 Twin 转成 prompt 里的紧凑文本。把格式化逻辑集中在这里，
  避免每个调用点重复编写、漂移分化。

设计原则：
  - 只输出"有数据"的部分，缺失字段整行跳过
  - Token 节省：每行不超过 ~100 字符
  - 紧凑但仍可读，适合作为 system/user prompt 片段
  - 不做解读、不做判断（那是 agent 的职责）
  - 数据新鲜度标签: 每个分区 header 带 (今日/昨日/N 天前) + ⚠ 过期提示,
    让 LLM synthesis 明白"这是几天前的数据", 而不是假设全部实时
"""

from datetime import datetime, timezone
from typing import List, Optional

from app.twin.schema import HealthTwin


def _age_label(freshness_ts: Optional[str], stale_days: int = 7, dead_days: int = 30) -> str:
    """把 ISO 时间戳转成 "(今日)" / "(昨日)" / "(3 天前) ⚠" / "(1 月前) ⚠⚠" / ""

    Args:
        freshness_ts: Twin.freshness.<field> 里的 ISO 字符串, 可为 None
        stale_days: 超过这个天数标一个 ⚠
        dead_days: 超过这个天数标两个 ⚠⚠
    """
    if not freshness_ts:
        return ""
    try:
        s = freshness_ts if "T" in freshness_ts else freshness_ts
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        ts = datetime.fromisoformat(s)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).days
    except Exception:
        return ""
    if age < 0:
        return ""
    if age == 0:
        return "(今日)"
    if age == 1:
        return "(昨日)"
    if age < stale_days:
        return f"({age} 天前)"
    if age < dead_days:
        return f"({age} 天前) ⚠"
    if age < 365:
        return f"({age // 30} 月前) ⚠⚠"
    return f"({age // 365} 年前) ⚠⚠"


# Human-readable evidence-grade labels for the gene block (compact, prompt-side).
_EVIDENCE_GRADE_LABEL = {
    "cpic_a": "CPIC-A",
    "pharmgkb_1a": "PharmGKB-1A",
    "clinvar_path_confirm": "ClinVar致病-需测序确认",
    "clinvar_likely": "ClinVar likely",
    "gwas_association": "GWAS弱关联",
    "proxy_uncertain": "proxy不确定",
}


def _variant_label(v: dict) -> str:
    name = str(v.get("gene_name") or "?")
    detail = str(v.get("genotype") or v.get("result_label") or "").strip()
    return f"{name} {detail}".strip()


def _format_genetic_variants_blob(genetic, max_genes: int = 8) -> List[str]:
    """Evidence-aware gene block (Phase 1 去噪).

    Each variant is annotated with its static (actionability, evidence_grade)
    injected by builder._classify_genetic_variants. Behaviour per design §3:
      - act          → 前置/突出 (▲), 带证据级
      - risk_stratify→ 居中, 带证据级
      - de_emphasize → 强制前缀 "群体弱关联,个体无预测力,非诊断" (防弱模型当确定结论)
      - proxy_uncertain / proxy locus → 追加 "阴性不代表无风险" 护栏
        (HLA tag SNP 即使提级到 pharmgkb_1a, proxy 护栏仍保留)
      - act + clinvar_path_confirm (BRCA 等) → 追加创始变异覆盖护栏 (建议1)
      - risk_stratify + 高外显单基因病 (HFE) → 追加专科转诊 + 测序确认 (建议2)

    Falls back gracefully if classification keys are absent (treats as de_emphasize).
    """
    from app.services.genetic_registry import (
        DE_EMPHASIZE_PREFIX,
        PROXY_UNCERTAIN_SUFFIX,
        classify_variant,
        is_proxy_variant,
    )

    # 建议 1: 单基因高危确认级 act 项(BRCA 等,evidence_grade=clinvar_path_confirm)
    # 即便不是 proxy rsid,消费级芯片也只覆盖部分创始变异 → 阴性不能当无风险。
    # doc §3 点名 BRCA 最该挂这条护栏。
    CONFIRM_ONLY_SUFFIX = "(消费级芯片仅覆盖部分创始变异,阴性不代表无风险,需临床级测序确认)"
    # 建议 2: 高外显单基因病的 risk_stratify 项(HFE 留 tier1 不动,但补回 doc §3 的
    # 转诊框架)→ 追加专科 + 临床级测序确认一句。小白名单,只点高外显单基因病基因。
    REFERRAL_SUFFIX = "(高外显单基因病,建议专科就诊 + 临床级测序确认)"
    _REFERRAL_GENES = frozenset({"HFE"})

    g = genetic
    all_variants: List[dict] = []
    for bucket in (
        g.drug_sensitivity,
        g.risk_variants,
        g.protective_variants,
        g.nutrition_variants,
        g.recovery_variants,
        g.exercise_variants,
        g.cognition_variants,
        g.personality_variants,
        g.sleep_variants,
    ):
        for v in bucket:
            if isinstance(v, dict):
                all_variants.append(v)

    act: List[str] = []
    risk: List[str] = []
    deemph: List[str] = []

    for v in all_variants[: max_genes * 3]:
        actionability = v.get("actionability")
        grade = v.get("evidence_grade")
        key = v.get("rsid") or v.get("gene_name") or ""
        if not actionability or not grade:
            # builder did not classify (e.g. partial twin) → derive on the fly.
            actionability, grade = classify_variant(
                str(key), gene_name=v.get("gene_name")
            )

        gene_norm = str(v.get("gene_name") or "").strip().upper()
        grade_label = _EVIDENCE_GRADE_LABEL.get(grade, grade)
        label = _variant_label(v)

        # proxy 护栏:grade=proxy_uncertain 或 locus 本身是 proxy(HLA tag SNP 被
        # 提级到 pharmgkb_1a 后 grade 不再是 proxy_uncertain,但"阴性≠无风险"仍成立)。
        suffix = ""
        if grade == "proxy_uncertain" or is_proxy_variant(str(key)):
            suffix = PROXY_UNCERTAIN_SUFFIX
        # 建议 1: BRCA 等单基因高危确认级 act 项,强制创始变异覆盖护栏。
        elif actionability == "act" and grade == "clinvar_path_confirm":
            suffix = CONFIRM_ONLY_SUFFIX
        # 建议 2: HFE 等高外显单基因病 risk_stratify 项,追加转诊 + 测序确认。
        elif actionability == "risk_stratify" and gene_norm in _REFERRAL_GENES:
            suffix = REFERRAL_SUFFIX

        if actionability == "act":
            act.append(f"▲ {label} ({grade_label}){suffix}")
        elif actionability == "risk_stratify":
            risk.append(f"{label} ({grade_label}){suffix}")
        else:  # de_emphasize
            deemph.append(f"{label} ({grade_label}){suffix}")

    out: List[str] = []
    if act:
        out.append("基因(行动级 ACT,出示给医生/需确认): " + "; ".join(act[:max_genes]))
    if risk:
        out.append("基因(背景调阈值 RISK-STRATIFY): " + "; ".join(risk[:max_genes]))
    if deemph:
        out.append(
            f"基因({DE_EMPHASIZE_PREFIX}): " + "; ".join(deemph[:max_genes])
        )
    return out


def twin_to_prompt_blob(twin: HealthTwin, max_abnormal: int = 5, max_genes: int = 8) -> str:
    """
    把 Twin 格式化为一段紧凑文本，适合塞进 LLM prompt。

    典型长度：300-800 tokens（取决于数据完整度）。

    Args:
        twin: 通过 build_twin() 构建的健康孪生
        max_abnormal: 最多列出的异常化验项数量
        max_genes: 最多列出的基因变异数量

    Returns:
        换行分隔的文本块；缺数据时返回空字符串
    """
    lines: List[str] = []

    # ─── 生理（Garmin/HRV/睡眠）
    phys_parts: List[str] = []
    p = twin.physiological
    if p.hrv_latest is not None:
        hrv_text = f"HRV {p.hrv_latest:.0f}ms"
        if p.hrv_7d_avg:
            hrv_text += f"(7日均 {p.hrv_7d_avg:.0f})"
        phys_parts.append(hrv_text)
    if p.resting_hr is not None:
        phys_parts.append(f"静息心率 {p.resting_hr}")
    if p.sleep_score_latest is not None:
        s = f"睡眠分 {p.sleep_score_latest}"
        if p.sleep_duration_h_latest:
            s += f"({p.sleep_duration_h_latest:.1f}h)"
        phys_parts.append(s)
    if p.sleep_deep_h_avg_14d is not None:
        phys_parts.append(f"深睡14d均 {p.sleep_deep_h_avg_14d:.1f}h")
    if p.body_battery_current is not None:
        phys_parts.append(f"电量 {p.body_battery_current}")
    if p.stress_level_current is not None:
        phys_parts.append(f"压力 {p.stress_level_current}")
    if p.steps_today is not None:
        phys_parts.append(f"步数 {p.steps_today}")
    if p.spo2_avg is not None:
        spo2_text = f"SpO2 {p.spo2_avg:.0f}%"
        if p.spo2_odi is not None:
            spo2_text += f" ODI={p.spo2_odi:.1f}"
        if p.spo2_min_overnight is not None:
            spo2_text += f" 最低{p.spo2_min_overnight}%"
        phys_parts.append(spo2_text)
    if p.vo2max_running is not None:
        phys_parts.append(f"VO2max {p.vo2max_running:.0f}")
    if phys_parts:
        age = _age_label(twin.freshness.garmin)
        lines.append(f"生理{age}: " + ", ".join(phys_parts))
        # P4: 多源 → 每字段的源 (e.g. "HRV←oura, SpO2←ringconn, 步数←garmin")
        # 仅多源场景输出 (>1 unique source),单源不啰嗦
        srcs = p.field_sources
        if srcs:
            unique = set(srcs.values())
            if len(unique) > 1:
                items = []
                _label = {"resting_heart_rate": "RHR", "spo2_avg": "SpO2", "sleep_score": "睡眠",
                          "steps": "步数", "hrv": "HRV"}
                for k in ["hrv", "resting_heart_rate", "spo2_avg", "sleep_score", "steps"]:
                    if k in srcs:
                        items.append(f"{_label.get(k, k)}←{srcs[k]}")
                if items:
                    lines.append("数据源: " + ", ".join(items))
        # R3: 跨源置信度 + 偏离(冲突降置信不平均,标暂以谁为准)
        if p.device_agreement_index is not None and len(p.device_sources) > 1:
            lines.append(f"多源一致性: {p.device_agreement_index:.0%}({'/'.join(p.device_sources)})")
        for d in (p.divergent_metrics or [])[:3]:
            lines.append(f"  ⚠ {d.label} {d.outlier_source} 偏离{d.deviation_pct:+.0f}%,暂以 {d.trusted_source} 为准")

    # ─── 个人基线对比 (Phase 0: 你现在 vs 你自己的历史)
    # 优先展 deviation (|z|>=2), 再补几条非偏离指标的 z 供 LLM 判断"在不在自己常态内"。
    pbs = p.personal_baselines
    if pbs:
        dev_lines: List[str] = []
        for mb in pbs:
            if mb.is_deviation and mb.message:
                dev_lines.append("  ⚠ " + mb.message)
        if dev_lines:
            lines.append("个人基线偏离:")
            lines.extend(dev_lines[:5])
        # 非偏离但有 z 的指标: 紧凑一行, 让 LLM 知道"这些在常态内"
        normal = [
            f"{mb.label} {mb.latest:.0f}{mb.unit}(基线{mb.baseline_mean:.0f}±"
            f"{mb.baseline_std:.0f},{mb.z:+.1f}σ)"
            for mb in pbs
            if not mb.is_deviation and mb.z is not None and mb.latest is not None
        ]
        if normal:
            lines.append("个人基线(常态内): " + ", ".join(normal[:6]))

    # ─── 身体
    b = twin.body_composition
    body_parts: List[str] = []
    if b.weight_kg is not None:
        body_parts.append(f"体重 {b.weight_kg:.1f}kg")
    if b.bmi is not None:
        bmi_text = f"BMI {b.bmi:.1f}"
        if b.bmi_category:
            bmi_text += f"({b.bmi_category})"
        body_parts.append(bmi_text)
    if b.body_fat_pct is not None:
        body_parts.append(f"体脂 {b.body_fat_pct:.1f}%")
    if b.tdee_kcal is not None:
        body_parts.append(f"TDEE {b.tdee_kcal:.0f}kcal")
    if body_parts:
        age = _age_label(twin.freshness.weight)
        lines.append(f"身体{age}: " + ", ".join(body_parts))

    # ─── CGM 连续血糖
    c = twin.cgm
    if c.has_cgm and (c.latest_mg_dl or c.readings_count_24h):
        cgm_parts: List[str] = []
        if c.latest_mg_dl:
            arrow = f" {c.latest_trend_arrow}" if c.latest_trend_arrow else ""
            cgm_parts.append(f"最新 {c.latest_mg_dl:.0f}mg/dL{arrow}")
        if c.mean_24h_mg_dl:
            cgm_parts.append(f"24h均 {c.mean_24h_mg_dl:.0f}")
        if c.cv_24h_pct:
            cgm_parts.append(f"CV {c.cv_24h_pct:.0f}%")
        if c.tir_24h_pct is not None:
            cgm_parts.append(f"TIR {c.tir_24h_pct:.0f}%")
        if c.gmi_estimated_a1c:
            cgm_parts.append(f"GMI≈A1C {c.gmi_estimated_a1c}")
        if c.severe_low_count_24h or c.severe_high_count_24h:
            cgm_parts.append(
                f"24h 严重值: 低{c.severe_low_count_24h}次/高{c.severe_high_count_24h}次"
            )
        if cgm_parts:
            lines.append("CGM: " + ", ".join(cgm_parts))

    # ─── 化验 / 生物标志物
    L = twin.labs
    lab_parts: List[str] = []
    if L.blood_pressure_systolic and L.blood_pressure_diastolic:
        lab_parts.append(f"血压 {L.blood_pressure_systolic}/{L.blood_pressure_diastolic}")
    if L.total_cholesterol is not None:
        lab_parts.append(f"总胆固醇 {L.total_cholesterol}")
    if L.blood_glucose is not None:
        lab_parts.append(f"血糖 {L.blood_glucose}")
    if lab_parts:
        age = _age_label(twin.freshness.labs, stale_days=90, dead_days=365)
        lines.append(f"化验{age}: " + ", ".join(lab_parts))
    if L.flagged_abnormal:
        abn_names = [str(a.get("item_name")) for a in L.flagged_abnormal[:max_abnormal] if a.get("item_name")]
        if abn_names:
            lines.append(f"异常项: {', '.join(abn_names)}")

    # ─── 药物 on-board
    if twin.medication.active_meds:
        med_names = [m.get("name") for m in twin.medication.active_meds if m.get("name")]
        if med_names:
            age = _age_label(twin.freshness.medication)
            line = f"在服药物{age} ({len(med_names)}种): " + ", ".join(med_names[:6])
            if twin.medication.adherence_7d_pct is not None:
                line += f" | 7日依从率 {twin.medication.adherence_7d_pct:.0f}%"
            lines.append(line)

    # ─── 补剂今日打卡
    s = twin.supplement
    if s.total_active_count > 0:
        lines.append(f"补剂: 今日 {s.taken_today_count}/{s.total_active_count} 已打卡")

    # ─── 基因配置（结构化摘要）
    if twin.gene_config and twin.gene_config.has_data:
        gc = twin.gene_config
        if gc.summary_lines:
            lines.append("基因配置: " + "; ".join(gc.summary_lines[:8]))
        config_parts: List[str] = []
        if gc.methylation != "normal":
            config_parts.append(f"甲基化={gc.methylation}")
        if gc.saturated_fat_sensitivity == "high":
            config_parts.append("饱和脂肪敏感")
        if gc.omega3_conversion == "reduced":
            config_parts.append("Omega3转化低")
        if gc.obesity_risk == "elevated":
            config_parts.append("肥胖风险↑")
        if gc.muscle_type != "mixed":
            config_parts.append(f"肌纤维={gc.muscle_type}")
        if gc.inflammation_tendency != "normal":
            config_parts.append(f"炎症={gc.inflammation_tendency}")
        if gc.antioxidant_capacity == "reduced":
            config_parts.append("抗氧化↓")
        if gc.caffeine_metabolism == "slow":
            config_parts.append("咖啡因慢代谢")
        if gc.alcohol_metabolism == "deficient":
            config_parts.append("酒精代谢缺陷")
        if gc.stress_type != "mixed":
            config_parts.append(f"心理={gc.stress_type}")
        if gc.drug_metabolism:
            dm_parts = [f"{k}={v}" for k, v in gc.drug_metabolism.items() if v != "normal"]
            if dm_parts:
                config_parts.append(f"药物代谢: {','.join(dm_parts)}")
        if config_parts:
            lines.append("基因参数: " + ", ".join(config_parts))
    elif twin.genetic.has_profile and twin.genetic.total_variants > 0:
        # 回退：无 GeneConfig 时仍输出原始变异 (Phase 1: evidence-aware 去噪渲染)
        lines.extend(_format_genetic_variants_blob(twin.genetic, max_genes=max_genes))

    # 解析中提示: PDF 上传后 LLM 应回 "解析中, 稍后补充" 而不是 "无数据"
    if twin.genetic.pending_profile_count > 0:
        lines.append(
            f"基因报告解析中: {twin.genetic.pending_profile_count} 份 PDF 还在 AI 后台处理 "
            f"(基因相关问题暂时无法回答, 请提示用户稍后再问)"
        )

    # ─── 环境
    e = twin.environment
    env_parts: List[str] = []
    if e.city:
        env_parts.append(e.city)
    if e.temperature_c is not None:
        env_parts.append(f"{e.temperature_c:.0f}°C")
    if e.humidity_pct is not None:
        env_parts.append(f"湿度 {e.humidity_pct:.0f}%")
    if e.aqi is not None:
        env_parts.append(f"AQI {e.aqi}" + (f"({e.aqi_level})" if e.aqi_level else ""))
    if e.outdoor_exercise_suitability:
        env_parts.append(f"户外运动: {e.outdoor_exercise_suitability}")
    if env_parts:
        lines.append("环境: " + ", ".join(env_parts))

    # ─── 行为 / 饮食 / 训练
    beh = twin.behavioral
    beh_parts: List[str] = []
    if beh.diet_calories_today:
        d = f"饮食 {beh.diet_calories_today:.0f}kcal"
        if beh.diet_protein_g_today:
            d += f"/蛋白{beh.diet_protein_g_today:.0f}g"
        beh_parts.append(d)
    if beh.meals_logged_today:
        beh_parts.append(f"{beh.meals_logged_today}餐")
    if beh.water_ml_today:
        beh_parts.append(f"水 {beh.water_ml_today}/{beh.water_goal_ml}ml")
    if beh.workouts_this_week:
        beh_parts.append(f"本周 {beh.workouts_this_week} 次运动")
    if beh.acute_chronic_ratio is not None:
        acwr_text = f"ACWR {beh.acute_chronic_ratio:.2f}"
        if beh.acwr_zone:
            acwr_text += f"({beh.acwr_zone})"
        beh_parts.append(acwr_text)
    if beh_parts:
        age = _age_label(twin.freshness.diet, stale_days=2, dead_days=7)
        lines.append(f"今日行为{age}: " + ", ".join(beh_parts))

    # ─── 近 7 天训练详情 (LLM 能看到 HR zones / 训练效果 / 主观疲劳)
    if beh.recent_workouts:
        lines.append(f"近 7 天训练 ({len(beh.recent_workouts)} 次):")
        for w in beh.recent_workouts[:5]:  # 最多展 5 条避免 prompt 膨胀
            segs = []
            if w.workout_date: segs.append(w.workout_date)
            if w.workout_type: segs.append(w.workout_type)
            if w.duration_min: segs.append(f"{w.duration_min:.0f}min")
            if w.distance_km: segs.append(f"{w.distance_km:.1f}km")
            if w.avg_hr: segs.append(f"平均 HR {w.avg_hr}")
            if w.hr_zone_dominant:
                segs.append(f"主 Z{w.hr_zone_dominant}")
            if w.training_effect_aerobic:
                segs.append(f"有氧效果 {w.training_effect_aerobic:.1f}")
            if w.perceived_exertion:
                segs.append(f"主观 {w.perceived_exertion}/10")
            if w.feeling:
                segs.append(f"感受 {w.feeling}")
            lines.append("  · " + " / ".join(segs))

    # ─── 鼻炎 / 慢病
    if beh.sneeze_count_today or beh.nasal_wash_count_today:
        lines.append(
            f"鼻炎今日: 喷嚏 {beh.sneeze_count_today}次 / 洗鼻 {beh.nasal_wash_count_today}次"
        )

    # ─── 急性病 / 感冒症状安全约束
    acute = twin.acute
    acute_parts: List[str] = []
    if acute.illness_names:
        acute_parts.append("病症=" + "/".join(acute.illness_names[:3]))
    if acute.recent_symptoms:
        acute_parts.append("症状=" + "；".join(acute.recent_symptoms[:3]))
    if acute.illness_severity_max is not None:
        acute_parts.append(f"最高严重度 {acute.illness_severity_max}/10")
    if acute.suspected_cold:
        acute_parts.append("疑似感冒/上呼吸道症状")
    if acute.fever_reported:
        acute_parts.append("提到发热")
    if acute.should_rest_from_training:
        acute_parts.append("运动目标=暂停/不强求")
    if acute_parts:
        lines.append("急性状态: " + ", ".join(acute_parts))
        if acute.training_guardrail:
            lines.append("急性状态约束: " + acute.training_guardrail)

    # ─── 心理
    m = twin.mental
    mental_parts: List[str] = []
    if m.mood_7d_avg is not None:
        mental_parts.append(f"情绪7d {m.mood_7d_avg:.1f}")
    if m.energy_7d_avg is not None:
        mental_parts.append(f"精力7d {m.energy_7d_avg:.1f}")
    if m.stress_7d_avg is not None:
        mental_parts.append(f"压力7d {m.stress_7d_avg:.1f}")
    if mental_parts:
        lines.append("心理: " + ", ".join(mental_parts))

    # ─── 目标
    if twin.goals.active_goals_count > 0:
        titles = [
            str(g_.get("title"))
            for g_ in twin.goals.active_goals[:3]
            if g_.get("title")
        ]
        if titles:
            lines.append(f"当前目标 ({twin.goals.active_goals_count}): {' / '.join(titles)}")

    # 数据质量 → Agent 置信度门控:数据稀疏/陈旧时追加 hedge 指令(末尾,不破坏既有
    # 首行格式),让 LLM 在低置信数据上多保守、少断言(Next Horizon Tier 5)。仅非空 blob。
    if lines:
        try:
            from app.services.data_confidence import assess_data_confidence
            hint = assess_data_confidence(twin).get("hedge_hint")
            if hint:
                lines.append(f"⚠️ {hint}")
        except Exception:  # noqa: BLE001
            pass

    return "\n".join(lines)
