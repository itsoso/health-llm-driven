"""
急性生命体征阈值规则 —— 最快速、最确定的安全层。

来源：
- BP: 2017 ACC/AHA High Blood Pressure Guideline
- SpO2: ATS clinical practice guideline
- HR: European Society of Cardiology resting HR guidance
"""

from typing import Optional

from app.agents.safety_guardian.engine import register
from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import HealthTwin


# ─────────────────────────── Blood Pressure ───────────────────────────


@register
def bp_severe_reading(twin: HealthTwin) -> Optional[Alert]:
    """Single severe blood-pressure reading: recheck and symptom-based triage."""
    sys_bp = twin.labs.blood_pressure_systolic
    dia_bp = twin.labs.blood_pressure_diastolic
    if sys_bp is None and dia_bp is None:
        return None

    if (sys_bp and sys_bp >= 180) or (dia_bp and dia_bp >= 120):
        return Alert(
            rule_id="vitals.bp_severe_reading",
            category="vitals",
            severity=Severity.HIGH,
            title="血压严重升高",
            message=(
                f"测得血压 {sys_bp}/{dia_bp} mmHg，达到严重升高范围（收缩压≥180 或舒张压≥120）。"
                "单次读数不能独立判断是否存在需要急诊处置的情况。"
            ),
            action=(
                "停止剧烈活动，静坐至少 1 分钟后复测；若复测仍处于此范围，请尽快联系医疗专业人员。"
                "若出现胸痛、气促、背痛、麻木或无力、视力改变或说话困难，请立即拨打急救电话。"
            ),
            data_citation={"systolic": sys_bp, "diastolic": dia_bp, "date": str(twin.labs.blood_pressure_date)},
            references=[
                "https://www.ahajournals.org/doi/10.1161/HYP.0000000000000065",
            ],
            requires_medical_attention=True,
        )
    return None


@register
def bp_stage_2_hypertension(twin: HealthTwin) -> Optional[Alert]:
    """二级高血压 140-179/90-119。"""
    sys_bp = twin.labs.blood_pressure_systolic
    dia_bp = twin.labs.blood_pressure_diastolic
    if sys_bp is None and dia_bp is None:
        return None

    # 已被 severe-reading rule 捕获的跳过
    if (sys_bp and sys_bp >= 180) or (dia_bp and dia_bp >= 120):
        return None

    if (sys_bp and 140 <= sys_bp < 180) or (dia_bp and 90 <= dia_bp < 120):
        return Alert(
            rule_id="vitals.bp_stage_2_hypertension",
            category="vitals",
            severity=Severity.HIGH,
            title="血压达二级高血压水平",
            message=(
                f"测得血压 {sys_bp}/{dia_bp} mmHg。ACC/AHA 2017 指南将 ≥140/90 定义为二级高血压，"
                "持续此水平会增加中风、心梗、肾病的远期风险。"
            ),
            action="建议 1 周内复测 3 次静坐 5 分钟后的血压；如多次确认 ≥140/90，请就诊内科或心内科评估是否启动降压治疗。",
            data_citation={"systolic": sys_bp, "diastolic": dia_bp},
            references=[
                "https://www.ahajournals.org/doi/10.1161/HYP.0000000000000065",
            ],
        )
    return None


@register
def bp_hypotension(twin: HealthTwin) -> Optional[Alert]:
    """低血压 <90/60 —— 有症状才需要处理，但仍值得提示。"""
    sys_bp = twin.labs.blood_pressure_systolic
    dia_bp = twin.labs.blood_pressure_diastolic
    if sys_bp is None and dia_bp is None:
        return None

    if (sys_bp and sys_bp < 90) or (dia_bp and dia_bp < 60):
        return Alert(
            rule_id="vitals.bp_hypotension",
            category="vitals",
            severity=Severity.MEDIUM,
            title="血压偏低",
            message=(
                f"测得血压 {sys_bp}/{dia_bp} mmHg，低于一般正常范围（收缩压 ≥90、舒张压 ≥60）。"
                "若伴随头晕、乏力、站起时眼前发黑，需要重视。"
            ),
            action="排查脱水、贫血、药物副作用（某些降压药、利尿剂过量）；缓慢起立，避免长时间站立；若出现晕厥请就医。",
            data_citation={"systolic": sys_bp, "diastolic": dia_bp},
        )
    return None


# ─────────────────────────── Resting Heart Rate ───────────────────────────


@register
def rhr_tachycardia(twin: HealthTwin) -> Optional[Alert]:
    """静息心率 ≥100 持续偏快。"""
    rhr = twin.physiological.resting_hr
    if rhr is None:
        return None

    if rhr >= 100:
        return Alert(
            rule_id="vitals.rhr_tachycardia",
            category="vitals",
            severity=Severity.MEDIUM,
            title="静息心率偏快",
            message=(
                f"静息心率 {rhr} 次/分，高于成人正常上限 100。"
                "可能原因：压力、脱水、睡眠不足、感染、咖啡因、甲亢、贫血、心律失常等。"
            ),
            action="排查近期咖啡/茶/能量饮料摄入；检查是否脱水；若持续一周以上或伴心悸/胸闷请就诊心内科。",
            data_citation={"resting_hr": rhr},
        )
    return None


@register
def rhr_bradycardia(twin: HealthTwin) -> Optional[Alert]:
    """
    静息心率 <45（非运动员）偏慢 —— 运动员可接受更低。
    这里无法判断用户运动员水平，所以只在 <40 时警告。
    """
    rhr = twin.physiological.resting_hr
    if rhr is None:
        return None

    if rhr < 40:
        return Alert(
            rule_id="vitals.rhr_bradycardia",
            category="vitals",
            severity=Severity.MEDIUM,
            title="静息心率过缓",
            message=(
                f"静息心率 {rhr} 次/分，低于 40。如果你不是耐力运动员，这偏低需要评估"
                "（可能提示窦房结功能、传导阻滞、甲减、药物作用）。"
            ),
            action="若伴头晕、乏力、晕厥，建议就诊心内科做心电图；运动员人群单纯低心率通常安全。",
            data_citation={"resting_hr": rhr},
        )
    return None


# ─────────────────────────── SpO2 ──────────────────────────────────────


# 夜间低氧"持续负荷"佐证阈值 —— 单点最低值必须有这两个之一支撑才算真低氧。
# ODI(氧减指数,每小时 desaturation 次数)轻度 OSA 的临床门槛约 5；
# below_90% 整夜低于 90% 的时长占比,>=1% 已属可量化负荷。
_SPO2_ODI_BURDEN = 5.0
_SPO2_BELOW90_BURDEN = 1.0


@register
def spo2_min_nocturnal_severe(twin: HealthTwin) -> Optional[Alert]:
    """夜间最低 SpO2 < 88% — 比 avg 更能揭示 OSA/严重低氧发作。

    临床上 avg 可能正常但 min 偏低（部分呼吸暂停/REM 期低氧），靠 avg 规则漏过。

    但"整夜单点最低值"是消费级光电传感器里最易被运动伪影污染的量(抬手/戒指松动
    一瞬即可掉到 80 多)。因此 CRITICAL/HIGH 只在有"持续负荷"佐证(ODI / below_90%)
    时才拉;否则降级为 INFO 提示,避免伪影喊狼。决策见 2026-06-17 用户裁决:
    - 有逐秒佐证且 ODI/below90% 都可忽略 → 判伪影,降级 INFO。
    - 无逐秒佐证(多设备用户逐秒 SpO2 没进 SpO2Sample,只有日聚合 min)→ 不拉
      CRITICAL,降级 INFO 提示"可疑低值,建议补逐秒血氧/复测"。
    - 持续指标在且升高(ODI>=5 或 below90>=1%)→ 保持 CRITICAL/HIGH,真 OSA 不放过。
    取舍权衡(under-alarm 风险):逐秒数据缺失时持续低氧会被压成 INFO —— 这是用户
    在"自己腕式/戒指血氧实测可信、单点 min 反复伪报"前提下的明确选择;告警仍产出
    (不静默丢弃),只是不再以单点伪影制造 CRITICAL。
    """
    min_spo2 = twin.physiological.spo2_min_overnight
    if min_spo2 is None:
        return None

    if min_spo2 < 80:
        base_severity = Severity.CRITICAL
        tier = "严重低氧（<80%）"
    elif min_spo2 < 85:
        base_severity = Severity.CRITICAL
        tier = "明显低氧（<85%）"
    elif min_spo2 < 88:
        base_severity = Severity.HIGH
        tier = "低氧关注（<88%）"
    else:
        return None

    odi = twin.physiological.spo2_odi
    below90 = twin.physiological.spo2_below_90_pct
    has_corroboration = odi is not None or below90 is not None
    sustained_burden = (odi is not None and odi >= _SPO2_ODI_BURDEN) or (
        below90 is not None and below90 >= _SPO2_BELOW90_BURDEN
    )

    data_citation = {"spo2_min_overnight": min_spo2}
    if odi is not None:
        data_citation["spo2_odi"] = odi
    if below90 is not None:
        data_citation["spo2_below_90_pct"] = below90

    if sustained_burden:
        # 持续低氧负荷被佐证 —— 真信号,保持原严重度。
        burden_bits = []
        if odi is not None:
            burden_bits.append(f"ODI {odi}/h")
        if below90 is not None:
            burden_bits.append(f"低于90%时长 {below90}%")
        burden_txt = "，".join(burden_bits)
        return Alert(
            rule_id="vitals.spo2_min_nocturnal_severe",
            category="vitals",
            severity=base_severity,
            title="夜间血氧过低",
            message=(
                f"昨夜最低 SpO2 {min_spo2}% — {tier}；整夜氧减负荷异常（{burden_txt}）。"
                "持续夜间低氧与心血管事件、认知下降、代谢紊乱相关，常见于阻塞性睡眠呼吸暂停。"
            ),
            action=(
                "1-2 周内就诊呼吸/睡眠中心，做多导睡眠图（PSG）或家用监测；"
                "过渡期生活方式调整：侧卧、抬高床头 30°、避免饮酒、避免睡前服用镇静类药物；"
                "是否需要药物或器械治疗请由就诊医生评估决定。"
            ),
            data_citation=data_citation,
            requires_medical_attention=base_severity == Severity.CRITICAL,
        )

    if has_corroboration:
        # 有逐秒数据,但整夜负荷可忽略 → 单点 dip 判为传感器伪影,降级 INFO。
        return Alert(
            rule_id="vitals.spo2_min_nocturnal_severe",
            category="vitals",
            severity=Severity.INFO,
            title="夜间血氧单点偏低（疑似伪影）",
            message=(
                f"昨夜出现单点最低 SpO2 {min_spo2}%，但整夜氧减负荷正常"
                f"（ODI {odi if odi is not None else '—'}/h，低于90%时长 "
                f"{below90 if below90 is not None else '—'}%），"
                "符合运动/佩戴伪影特征，非持续性低氧。"
            ),
            action="如近期有打鼾加重、晨起头痛或白天嗜睡，再就诊评估；否则无需处理。",
            data_citation=data_citation,
            requires_medical_attention=False,
        )

    # 无逐秒佐证(只有日聚合 min,逐秒 SpO2 未进库)→ 不拉 CRITICAL,降级 INFO 提示复测。
    return Alert(
        rule_id="vitals.spo2_min_nocturnal_severe",
        category="vitals",
        severity=Severity.INFO,
        title="夜间血氧单点偏低（待确认）",
        message=(
            f"昨夜单点最低 SpO2 {min_spo2}%，但缺逐秒夜间血氧，无法确认是持续低氧还是"
            "传感器伪影。消费级腕式/戒指血氧单点最低值易受运动与佩戴影响。"
        ),
        action="若关注睡眠呼吸,补充逐秒血氧监测(戒指/手表整夜记录)或家用睡眠监测复测后再判读。",
        data_citation=data_citation,
        requires_medical_attention=False,
    )


@register
def spo2_severe_hypoxia(twin: HealthTwin) -> Optional[Alert]:
    """血氧 <88% 严重低氧。"""
    spo2 = twin.physiological.spo2_avg
    if spo2 is None:
        return None

    if spo2 < 88:
        return Alert(
            rule_id="vitals.spo2_severe_hypoxia",
            category="vitals",
            severity=Severity.CRITICAL,
            title="血氧严重偏低",
            message=(
                f"平均 SpO2 {spo2:.0f}%，低于 88%。若持续，可能代表呼吸衰竭、心衰、"
                "急性肺部感染等情况，需要立即评估。"
            ),
            action="立即复测（指夹式血氧计更准）；若多次确认 <90% 或伴气促/胸痛/意识改变，请立即就医或拨打急救。",
            data_citation={"spo2_avg": spo2},
            requires_medical_attention=True,
        )
    return None


@register
def spo2_mild_hypoxia(twin: HealthTwin) -> Optional[Alert]:
    """血氧 88-92% 轻度偏低。"""
    spo2 = twin.physiological.spo2_avg
    if spo2 is None:
        return None

    if 88 <= spo2 < 92:
        return Alert(
            rule_id="vitals.spo2_mild_hypoxia",
            category="vitals",
            severity=Severity.MEDIUM,
            title="血氧偏低",
            message=(
                f"平均 SpO2 {spo2:.0f}%，低于 92%。腕表测量准确度有限，建议用指夹式血氧计复核。"
                "睡眠时 SpO2 持续偏低可能提示睡眠呼吸暂停。"
            ),
            action="用指夹式血氧计复测；如复测确认偏低，考虑做多导睡眠监测排查 OSA；白天活动后测量以排除肺功能问题。",
            data_citation={"spo2_avg": spo2},
        )
    return None


@register
def spo2_osa_screening(twin: HealthTwin) -> Optional[Alert]:
    """ODI ≥ 5 提示阻塞性睡眠呼吸暂停风险。"""
    odi = twin.physiological.spo2_odi
    if odi is None or odi < 5:
        return None

    severity = Severity.MEDIUM if odi < 15 else Severity.HIGH
    if odi < 15:
        risk = "轻度"
    elif odi < 30:
        risk = "中度"
    else:
        risk = "重度"

    return Alert(
        rule_id="vitals.spo2_osa_screening",
        category="vitals",
        severity=severity,
        title="夜间血氧波动提示睡眠呼吸暂停风险",
        message=(
            f"夜间氧减指数 (ODI) 为 {odi:.1f} 次/小时（正常 <5），"
            f"风险等级: {risk}。ODI ≥5 是阻塞性睡眠呼吸暂停 (OSAHS) 的重要筛查指标。"
        ),
        action=(
            "建议进行多导睡眠监测 (PSG) 或家庭睡眠呼吸监测 (HSAT) 确诊；"
            "侧卧睡眠、避免睡前饮酒可改善轻度症状；BMI>28 者减重有显著效果。"
        ),
        data_citation={"odi": odi, "risk_level": risk},
        references=[
            "https://jcsm.aasm.org/doi/10.5664/jcsm.6746",
        ],
    )


@register
def spo2_sustained_low_overnight(twin: HealthTwin) -> Optional[Alert]:
    """夜间血氧持续低于 90% 超过 10% 的时间。"""
    pct = twin.physiological.spo2_below_90_pct
    if pct is None or pct < 10:
        return None

    return Alert(
        rule_id="vitals.spo2_sustained_low_overnight",
        category="vitals",
        severity=Severity.HIGH,
        title="夜间血氧持续偏低",
        message=(
            f"整夜有 {pct:.0f}% 的时间血氧低于 90%。"
            "长时间低氧血症会加速心脑血管损伤和认知功能下降。"
        ),
        action="建议尽快进行睡眠呼吸检查；考虑是否有慢阻肺、心衰等可能原因。",
        data_citation={"below_90_pct": pct},
        requires_medical_attention=True,
    )


# ─────────────────────────── Stress 持续偏高 ──────────────────────────


@register
def stress_persistently_high(twin: HealthTwin) -> Optional[Alert]:
    """Garmin 压力值 ≥75 持续偏高 —— 信息性提示。"""
    stress = twin.physiological.stress_level_current
    if stress is None or stress < 75:
        return None

    return Alert(
        rule_id="vitals.stress_persistently_high",
        category="vitals",
        severity=Severity.LOW,
        title="生理压力值偏高",
        message=(
            f"当前 Garmin 压力值 {stress}（≥75 为高）。持续高压力会降低 HRV、影响睡眠质量、"
            "升高炎症水平，是慢病的一个加速器。"
        ),
        action="尝试 3-5 分钟慢呼吸（4-7-8 节奏）；避免今晚摄入咖啡因；早睡一小时。",
        data_citation={"stress_level_current": stress},
    )


# ─────────────────────────── Sleep Debt 信号 ──────────────────────────


@register
def sleep_severely_short(twin: HealthTwin) -> Optional[Alert]:
    """最近一夜睡眠 < 5 小时。"""
    d = twin.physiological.sleep_duration_h_latest
    if d is None or d >= 5.0:
        return None

    return Alert(
        rule_id="vitals.sleep_severely_short",
        category="vitals",
        severity=Severity.MEDIUM,
        title="睡眠严重不足",
        message=(
            f"最近一夜总睡眠 {d:.1f} 小时，低于 5 小时会显著削弱认知、免疫和情绪调节能力，"
            "并升高日间事故风险（尤其是驾驶和高空作业）。"
        ),
        action="今天避免开车长途和重要决策；午间 20 分钟 power nap；今晚提前 1 小时入睡，避免咖啡因。",
        data_citation={"sleep_duration_h": d},
    )
