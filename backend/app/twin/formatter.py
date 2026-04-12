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
"""

from typing import List

from app.twin.schema import HealthTwin


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
        phys_parts.append(f"SpO2 {p.spo2_avg:.0f}%")
    if p.vo2max_running is not None:
        phys_parts.append(f"VO2max {p.vo2max_running:.0f}")
    if phys_parts:
        lines.append("生理: " + ", ".join(phys_parts))

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
        lines.append("身体: " + ", ".join(body_parts))

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
        lines.append("化验: " + ", ".join(lab_parts))
    if L.flagged_abnormal:
        abn_names = [str(a.get("item_name")) for a in L.flagged_abnormal[:max_abnormal] if a.get("item_name")]
        if abn_names:
            lines.append(f"异常项: {', '.join(abn_names)}")

    # ─── 药物 on-board
    if twin.medication.active_meds:
        med_names = [m.get("name") for m in twin.medication.active_meds if m.get("name")]
        if med_names:
            line = f"在服药物 ({len(med_names)}种): " + ", ".join(med_names[:6])
            if twin.medication.adherence_7d_pct is not None:
                line += f" | 7日依从率 {twin.medication.adherence_7d_pct:.0f}%"
            lines.append(line)

    # ─── 补剂今日打卡
    s = twin.supplement
    if s.total_active_count > 0:
        lines.append(f"补剂: 今日 {s.taken_today_count}/{s.total_active_count} 已打卡")

    # ─── 基因（关注药物敏感和风险位点）
    g = twin.genetic
    if g.has_profile and g.total_variants > 0:
        gene_lines: List[str] = []
        for v in g.drug_sensitivity[:max_genes]:
            gene_lines.append(f"{v.get('gene_name','?')} {v.get('genotype','')}".strip())
        if gene_lines:
            lines.append(f"药物基因: {', '.join(gene_lines)}")
        risk_lines = [
            f"{v.get('gene_name','?')} {v.get('result_label','')}".strip()
            for v in g.risk_variants[:5]
        ]
        if risk_lines:
            lines.append(f"基因风险: {', '.join(risk_lines)}")

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
        lines.append("今日行为: " + ", ".join(beh_parts))

    # ─── 鼻炎 / 慢病
    if beh.sneeze_count_today or beh.nasal_wash_count_today:
        lines.append(
            f"鼻炎今日: 喷嚏 {beh.sneeze_count_today}次 / 洗鼻 {beh.nasal_wash_count_today}次"
        )

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

    return "\n".join(lines)
