"""行为关联规则库（P1b-03）。

输入：一夜的 NightAnalysis + 当日上下文（药物/补剂/运动/饮食/鼻炎）
输出：CorrelationFinding 列表（可操作建议）

设计原则：
  - 每条规则独立函数，返回 Optional[CorrelationFinding]，便于单测
  - 不调 LLM —— 确定性规则 + 结构化输出
  - 规则失败（缺数据）静默跳过，不抛
  - 对用户 itsoso 的特殊药物（异丙托溴铵）有专门规则

使用：
    findings = run_rules(
        night=NightAnalysis(...),
        med_logs=[...],
        supplement_records=[...],
        workouts=[...],
        diet_records=[...],
        rhinitis_logs=[...],
        weather=...,
    )
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Dict, List, Optional
import re

from app.services.sleep.nocturnal_spo2_analyzer import NightAnalysis


# ---------------------------------------------------------------------------
# 通用输出结构
# ---------------------------------------------------------------------------

@dataclass
class CorrelationFinding:
    category: str                # medication | supplement | exercise | diet | environment
    subject: str                 # 规则对象（例如 "异丙托溴铵"、"HIIT 训练"）
    rule: str                    # 规则 id (snake_case)
    hypothesis: str              # 假设文本（面向用户）
    suggested_action: str        # 可操作建议
    severity: str = "info"       # info | warning | alert
    confidence: str = "medium"   # low | medium | high
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NightContext:
    """规则执行时共享的当日上下文。"""
    night_date: date
    med_logs: List[Dict[str, Any]] = field(default_factory=list)          # {name, taken_time, status}
    active_meds: List[Dict[str, Any]] = field(default_factory=list)       # {name, frequency, is_active}
    supplement_records: List[Dict[str, Any]] = field(default_factory=list)  # {name, taken, taken_time}
    workouts: List[Dict[str, Any]] = field(default_factory=list)          # {workout_type, end_time, avg_hr, hr_max_pct, duration_min}
    diet_records: List[Dict[str, Any]] = field(default_factory=list)      # {food_items, meal_type, meal_time, alcohol_units}
    rhinitis_severity: Optional[int] = None                               # 0-10
    air_quality_pm25: Optional[float] = None
    sleep_start_ts: Optional[datetime] = None


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

def _parse_time_str(s: Any) -> Optional[time]:
    if not s:
        return None
    if isinstance(s, time):
        return s
    m = re.match(r'^(\d{1,2}):(\d{2})', str(s))
    if not m:
        return None
    try:
        return time(int(m.group(1)), int(m.group(2)))
    except (ValueError, TypeError):
        return None


def _hours_between(earlier: Optional[datetime], later: Optional[datetime]) -> Optional[float]:
    if not earlier or not later:
        return None
    return (later - earlier).total_seconds() / 3600


def _med_taken_today(ctx: NightContext, name_pattern: str) -> List[Dict[str, Any]]:
    pat = re.compile(name_pattern, re.IGNORECASE)
    return [
        m for m in ctx.med_logs
        if m.get('status') == 'taken' and pat.search(m.get('name', ''))
    ]


def _rem_events(night: NightAnalysis) -> int:
    return sum(1 for e in night.events if (e.sleep_stage or '').lower() == 'rem')


# ---------------------------------------------------------------------------
# 规则 A - 药物
# ---------------------------------------------------------------------------

def rule_ipratropium_late_dose(night: NightAnalysis, ctx: NightContext) -> Optional[CorrelationFinding]:
    """异丙托溴铵末次剂量距入睡 > 8h → 药效高峰已过，建议调整时间。

    异丙托溴铵 peak ~1.5h，作用时长 6-8h。若用在太早，夜间阻塞期无效。
    """
    takes = _med_taken_today(ctx, r'异丙托溴铵|ipratropium')
    if not takes or not ctx.sleep_start_ts or night.odi < 2:
        return None

    # 找当日最晚一次服药
    latest_time = None
    for t in takes:
        tt = _parse_time_str(t.get('taken_time'))
        if tt and (latest_time is None or tt > latest_time):
            latest_time = tt
    if not latest_time:
        return None

    latest_dt = datetime.combine(ctx.night_date, latest_time)
    gap_hours = _hours_between(latest_dt, ctx.sleep_start_ts)
    if gap_hours is None or gap_hours <= 8:
        return None

    return CorrelationFinding(
        category="medication",
        subject="异丙托溴铵",
        rule="ipratropium_late_dose",
        hypothesis=f"末次用药 {latest_time.strftime('%H:%M')} 距入睡 {gap_hours:.1f}h，"
                   f"异丙托溴铵作用约 6-8h，夜间阻塞期药效已过。",
        suggested_action="与医生商量后，将末次用药时间调整到 21:30-22:00（遵医嘱）。",
        severity="warning",
        confidence="medium" if night.odi < 5 else "high",
        evidence={
            "last_dose_time": latest_time.strftime("%H:%M"),
            "sleep_start_ts": ctx.sleep_start_ts.isoformat(),
            "gap_hours": round(gap_hours, 1),
            "odi": night.odi,
        },
    )


def rule_ipratropium_skipped(night: NightAnalysis, ctx: NightContext) -> Optional[CorrelationFinding]:
    """异丙托溴铵是激活药（active_meds 里有），但当日未服 + ODI 升高。"""
    active_ipra = any(
        re.search(r'异丙托溴铵|ipratropium', m.get('name', ''), re.IGNORECASE)
        for m in ctx.active_meds
    )
    if not active_ipra:
        return None
    took = _med_taken_today(ctx, r'异丙托溴铵|ipratropium')
    if took:
        return None
    if night.odi < 3:
        return None

    return CorrelationFinding(
        category="medication",
        subject="异丙托溴铵",
        rule="ipratropium_skipped_high_odi",
        hypothesis=f"当日未服异丙托溴铵且 ODI={night.odi}/h 偏高 — 漏服可能导致夜间阻塞加重。",
        suggested_action="配置夜间用药提醒，或与医生评估是否需要长效替代方案。",
        severity="warning",
        confidence="medium",
        evidence={"odi": night.odi, "events": night.events_count},
    )


def rule_respiratory_depressant(night: NightAnalysis, ctx: NightContext) -> Optional[CorrelationFinding]:
    """当日服用苯二氮䓬/阿片/镇静抗组胺 + ODI 升高 → 高优先提示。"""
    dep_pattern = r'(地西泮|阿普唑仑|劳拉西泮|苯二氮|benzodiazepine|哌替啶|吗啡|羟考酮|opioid|opioid|苯海拉明|diphenhydramine|西替利嗪|氯雷他定)'
    # 氯雷他定/西替利嗪是第二代，实际不是明显镇静，但此处保守列入
    takes = _med_taken_today(ctx, dep_pattern)
    if not takes or night.odi < 4:
        return None

    names = sorted({t.get('name', '?') for t in takes})
    return CorrelationFinding(
        category="medication",
        subject="，".join(names),
        rule="respiratory_depressant_high_odi",
        hypothesis=f"当日服用呼吸/中枢可能抑制的药物（{names}），且 ODI={night.odi}/h。"
                   f"这类药物可能加重夜间阻塞性事件。",
        suggested_action="与医生讨论剂量或换药可行性；绝不自行停药。",
        severity="alert",
        confidence="medium",
        evidence={"meds": names, "odi": night.odi},
    )


# ---------------------------------------------------------------------------
# 规则 B - 补剂
# ---------------------------------------------------------------------------

def rule_bedtime_magnesium_helps(night: NightAnalysis, ctx: NightContext) -> Optional[CorrelationFinding]:
    """晚上服镁剂 + ODI < 2 → 可能正向关联，维持方案。

    是正面规则，低 confidence（样本需长期比对才可信）。
    """
    mag_bedtime = any(
        re.search(r'镁|magnesium|甘氨酸镁|L-threonate', s.get('name', ''), re.IGNORECASE)
        and s.get('taken')
        and _parse_time_str(s.get('taken_time'))
        and _parse_time_str(s.get('taken_time')) >= time(19, 0)
        for s in ctx.supplement_records
    )
    if not mag_bedtime or night.odi > 3:
        return None

    return CorrelationFinding(
        category="supplement",
        subject="睡前镁剂",
        rule="bedtime_magnesium_helps",
        hypothesis=f"晚间服用镁剂且 ODI={night.odi}/h 处于低位 — 可能正向关联。",
        suggested_action="维持现有方案；4 周后可做对比确认。",
        severity="info",
        confidence="low",
        evidence={"odi": night.odi},
    )


# ---------------------------------------------------------------------------
# 规则 C - 运动
# ---------------------------------------------------------------------------

def rule_late_intense_training(night: NightAnalysis, ctx: NightContext) -> Optional[CorrelationFinding]:
    """高强度训练结束 < 3h 入睡 + ODI 升高。"""
    if not ctx.sleep_start_ts:
        return None
    threshold_hours = 3
    offenders = []
    for w in ctx.workouts:
        end_ts = w.get('end_time')
        if not isinstance(end_ts, datetime):
            continue
        gap = _hours_between(end_ts, ctx.sleep_start_ts)
        if gap is None or gap <= 0 or gap > threshold_hours:
            continue
        hr_max_pct = w.get('hr_max_pct') or 0
        duration = w.get('duration_min') or 0
        if hr_max_pct >= 0.85 and duration >= 20:
            offenders.append({**w, 'gap_hours': round(gap, 1)})

    if not offenders or night.odi < 3:
        return None

    top = offenders[0]
    return CorrelationFinding(
        category="exercise",
        subject=top.get('workout_type', '高强度训练'),
        rule="late_high_intensity_training",
        hypothesis=f"高强度训练（{top.get('workout_type', '?')}）结束距入睡 {top['gap_hours']}h，"
                   f"交感神经未充分平复，夜间 ODI={night.odi}/h。",
        suggested_action="高强度训练移至入睡前 4h 以上；晚间建议低强度或拉伸。",
        severity="warning",
        confidence="high",
        evidence={"workout": top, "odi": night.odi},
    )


def rule_garmin_overreaching(night: NightAnalysis, ctx: NightContext) -> Optional[CorrelationFinding]:
    """Garmin training_status = overreaching + ODI 升高 + HRV 下降。"""
    # training_status 信息从 ctx.workouts 第 1 项拿不到；由调用方在 ctx 上附 training_status_flag
    status = None
    for w in ctx.workouts:
        if w.get('garmin_training_status') == 'overreaching':
            status = 'overreaching'
            break
    if status != 'overreaching' or night.odi < 3:
        return None
    return CorrelationFinding(
        category="exercise",
        subject="累积训练负荷",
        rule="overreaching_sleep_degradation",
        hypothesis=f"Garmin 状态为 overreaching + 夜间 ODI={night.odi}/h，"
                   f"近期训练过载可能加重睡眠质量下降。",
        suggested_action="下一周 deload：总量降 30-40%，以低强度有氧 + 力量为主。",
        severity="warning",
        confidence="high",
        evidence={"odi": night.odi, "training_status": status},
    )


# ---------------------------------------------------------------------------
# 规则 D - 饮食 / 环境 / 鼻炎
# ---------------------------------------------------------------------------

def rule_alcohol(night: NightAnalysis, ctx: NightContext) -> Optional[CorrelationFinding]:
    """当日酒精 ≥ 1 standard drink + 事件集中前半夜。"""
    total_units = sum(float(d.get('alcohol_units', 0) or 0) for d in ctx.diet_records)
    if total_units < 1 or night.odi < 3:
        return None

    if not night.events:
        return None
    first_half_events = 0
    for e in night.events:
        if ctx.sleep_start_ts:
            mid = ctx.sleep_start_ts + timedelta(hours=4)
            if e.start_ts <= mid:
                first_half_events += 1
    first_half_ratio = first_half_events / max(len(night.events), 1)

    if first_half_ratio < 0.6:
        return None

    return CorrelationFinding(
        category="diet",
        subject="酒精",
        rule="alcohol_induced_desaturation",
        hypothesis=f"当日酒精 {total_units} 标准杯 + 氧降事件 {first_half_ratio*100:.0f}% 集中前半夜 "
                   f"— 酒精松弛上气道，是已知 OSA 加重因素。",
        suggested_action="晚间不饮酒，或将摄入量减半并与睡眠间隔 3h 以上。",
        severity="alert",
        confidence="high",
        evidence={"alcohol_units": total_units, "first_half_ratio": round(first_half_ratio, 2)},
    )


def rule_rhinitis_severe(night: NightAnalysis, ctx: NightContext) -> Optional[CorrelationFinding]:
    """当日鼻炎严重度 ≥ 中 + ODI 升高。"""
    if ctx.rhinitis_severity is None or ctx.rhinitis_severity < 5:
        return None
    if night.odi < 3:
        return None
    return CorrelationFinding(
        category="environment",
        subject="鼻炎发作",
        rule="rhinitis_secondary_osa",
        hypothesis=f"当日鼻炎严重度 {ctx.rhinitis_severity}/10 + 夜间 ODI={night.odi}/h — "
                   f"鼻阻塞可继发 OSA 样事件。",
        suggested_action="睡前鼻腔冲洗 + 鼻喷糖皮质激素 + 侧卧；确保异丙托溴铵已用。",
        severity="warning",
        confidence="high",
        evidence={"rhinitis_severity": ctx.rhinitis_severity, "odi": night.odi},
    )


def rule_high_pm25(night: NightAnalysis, ctx: NightContext) -> Optional[CorrelationFinding]:
    """卧室 PM2.5 > 75 + ODI 升高（需用户接卧室传感器；当前用城市 AQ 兜底）。"""
    if ctx.air_quality_pm25 is None or ctx.air_quality_pm25 < 75:
        return None
    if night.odi < 3:
        return None
    return CorrelationFinding(
        category="environment",
        subject="空气质量",
        rule="high_pm25",
        hypothesis=f"当日 PM2.5 = {ctx.air_quality_pm25} μg/m³ + ODI={night.odi}/h — "
                   f"空气颗粒物可能触发气道反应。",
        suggested_action="卧室开空气净化器 + 关窗；过敏季节戴口罩外出。",
        severity="info",
        confidence="medium",
        evidence={"pm25": ctx.air_quality_pm25, "odi": night.odi},
    )


def rule_rem_concentrated(night: NightAnalysis, ctx: NightContext) -> Optional[CorrelationFinding]:
    """氧降事件多数在 REM 期 → 典型 OSA 模式。"""
    if night.events_count < 4:
        return None
    rem_count = _rem_events(night)
    ratio = rem_count / night.events_count
    if ratio < 0.5:
        return None
    return CorrelationFinding(
        category="diagnostic",
        subject="睡眠结构",
        rule="rem_concentrated_events",
        hypothesis=f"氧降事件 {rem_count}/{night.events_count} ({ratio*100:.0f}%) 集中 REM 期 — "
                   f"这是阻塞性睡眠呼吸暂停的典型分布。",
        suggested_action="建议做一次正式睡眠呼吸监测（PSG 或家用 WatchPAT）确诊。",
        severity="alert",
        confidence="high",
        evidence={"rem_events": rem_count, "total_events": night.events_count, "rem_ratio": round(ratio, 2)},
    )


def rule_severe_hypoxia(night: NightAnalysis, ctx: NightContext) -> Optional[CorrelationFinding]:
    """最低 SpO2 < 88% (临床严重低氧) → alert，不管 ODI/REM 比例。

    88% 是临床公认的"需要医疗关注"阈值。85% 以下更严重。
    """
    if night.min_spo2 is None:
        return None
    min_val = night.min_spo2
    if min_val >= 88:
        return None

    if min_val < 80:
        severity = "alert"
        msg = f"最低 SpO2 {min_val}% — 严重低氧（<80% 属紧急阈值）"
    elif min_val < 85:
        severity = "alert"
        msg = f"最低 SpO2 {min_val}% — 明显低氧（<85% 属医疗关注阈值）"
    else:
        severity = "warning"
        msg = f"最低 SpO2 {min_val}% — 低氧（<88% 需关注）"

    return CorrelationFinding(
        category="diagnostic",
        subject="夜间低氧",
        rule="severe_hypoxia",
        hypothesis=f"{msg}。持续夜间低氧与心血管事件、认知下降、代谢紊乱相关。",
        suggested_action=(
            "建议 1-2 周内就诊呼吸科/睡眠中心做多导睡眠图（PSG）。"
            "过渡期可尝试侧卧、抬高床头 30°、睡前使用异丙托溴铵。"
        ),
        severity=severity,
        confidence="high",
        evidence={
            "min_spo2": min_val,
            "events_count": night.events_count,
            "odi": night.odi,
        },
    )


def rule_high_odi(night: NightAnalysis, ctx: NightContext) -> Optional[CorrelationFinding]:
    """ODI ≥ 5 (轻度) / ≥15 (中度) / ≥30 (重度) — 临床 ODI 分级。"""
    if night.odi < 5:
        return None
    if night.odi < 15:
        severity = "warning"
        grade = "轻度"
    elif night.odi < 30:
        severity = "alert"
        grade = "中度"
    else:
        severity = "alert"
        grade = "重度"
    return CorrelationFinding(
        category="diagnostic",
        subject="氧减指数",
        rule="high_odi",
        hypothesis=f"ODI={night.odi}/h（{grade}），超过临床关注阈值（5/h）。",
        suggested_action="建议正规睡眠呼吸监测确诊；同时排查鼻炎、体重、饮酒等可改变因素。",
        severity=severity,
        confidence="high",
        evidence={"odi": night.odi, "grade": grade},
    )


# ---------------------------------------------------------------------------
# 规则注册 + 执行器
# ---------------------------------------------------------------------------

_RULES: List[Callable[[NightAnalysis, NightContext], Optional[CorrelationFinding]]] = [
    rule_ipratropium_late_dose,
    rule_ipratropium_skipped,
    rule_respiratory_depressant,
    rule_bedtime_magnesium_helps,
    rule_late_intense_training,
    rule_garmin_overreaching,
    rule_alcohol,
    rule_rhinitis_severe,
    rule_high_pm25,
    rule_rem_concentrated,
    rule_severe_hypoxia,
    rule_high_odi,
]


def run_rules(night: NightAnalysis, ctx: NightContext) -> List[CorrelationFinding]:
    """按 SEVERITY (alert > warning > info) 排序所有规则输出。"""
    findings: List[CorrelationFinding] = []
    for rule_fn in _RULES:
        try:
            f = rule_fn(night, ctx)
            if f:
                findings.append(f)
        except Exception:
            # 规则失败不影响其他规则
            continue

    sev_order = {"alert": 0, "warning": 1, "info": 2}
    conf_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (sev_order.get(f.severity, 3), conf_order.get(f.confidence, 3)))
    return findings
