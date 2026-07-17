"""睡眠深度分析服务"""
import math
from typing import Dict, Any, List, Optional
from datetime import date, timedelta, time
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.daily_health import GarminData
from app.models.user import User


# 各年龄段深睡眠/REM正常比例 (min%, max%)
AGE_NORMS = {
    (0, 25):  {"deep": (20, 25), "rem": (20, 25), "light": (45, 55), "awake": (0, 5)},
    (26, 35): {"deep": (17, 22), "rem": (20, 25), "light": (50, 55), "awake": (5, 8)},
    (36, 45): {"deep": (15, 20), "rem": (18, 22), "light": (50, 60), "awake": (5, 10)},
    (46, 55): {"deep": (12, 18), "rem": (17, 20), "light": (55, 60), "awake": (8, 12)},
    (56, 65): {"deep": (10, 15), "rem": (15, 18), "light": (55, 65), "awake": (10, 15)},
    (66, 120): {"deep": (5, 12), "rem": (13, 18), "light": (60, 70), "awake": (12, 20)},
}

# NSF推荐睡眠时长(小时) by age
NSF_RECS = {
    (0, 25): (7, 9), (26, 64): (7, 9), (65, 120): (7, 8),
}


def _get_age(user: Optional[User]) -> Optional[int]:
    if not user or not user.birth_date:
        return None
    today = date.today()
    return today.year - user.birth_date.year - (
        (today.month, today.day) < (user.birth_date.month, user.birth_date.day)
    )


def _get_norm(age: Optional[int], table: dict) -> Any:
    if age is None:
        age = 35  # default to 26-35 group
    for (lo, hi), val in table.items():
        if lo <= age <= hi:
            return val
    return list(table.values())[2]  # fallback mid-range


def _safe_avg(values: List) -> float:
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else 0.0


def _time_to_minutes(t) -> Optional[float]:
    """接受 datetime.time / datetime / ISO 字符串 / None，统一转分钟数。"""
    if t is None:
        return None
    # 已经是 time 或 datetime 对象
    if hasattr(t, "hour") and hasattr(t, "minute"):
        return t.hour * 60 + t.minute
    # 字符串：尝试解析 'HH:MM' 或 ISO 格式
    if isinstance(t, str):
        s = t.strip()
        if not s:
            return None
        try:
            # 'HH:MM' 或 'HH:MM:SS'
            parts = s.split(":")
            if len(parts) >= 2:
                return int(parts[0]) * 60 + int(parts[1])
        except (ValueError, IndexError):
            pass
        try:
            # ISO datetime fallback
            from datetime import datetime as _dt
            dt = _dt.fromisoformat(s.replace("Z", "+00:00"))
            return dt.hour * 60 + dt.minute
        except (ValueError, TypeError):
            return None
    return None


def _std_dev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = sum(values) / len(values)
    return math.sqrt(sum((v - avg) ** 2 for v in values) / (len(values) - 1))


def _calc_stage_pcts(records: List[GarminData]) -> Dict[str, float]:
    """Calculate average stage percentages from records."""
    pcts = {"deep": [], "rem": [], "light": [], "awake": []}
    for r in records:
        total = r.total_sleep_duration or 1
        for stage, field in [("deep", r.deep_sleep_duration), ("rem", r.rem_sleep_duration),
                             ("light", r.light_sleep_duration), ("awake", r.awake_duration)]:
            if field is not None:
                pcts[stage].append(field / total * 100)
    return {k: round(_safe_avg(v), 1) for k, v in pcts.items()}


def _fetch_sleep_data(db: Session, user_id: int, days: int) -> List[Any]:
    # 多源按日合并: 同一晚 Apple Watch + RingConn + Garmin 各一行,
    # 不合并会把同一晚睡眠重复计入均值/架构占比。每指标按优先级取一值。
    from app.services.garmin_daily_merged import merged_daily_rows

    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    return merged_daily_rows(
        db, user_id, since=start_date, until=end_date,
        require_metrics=["total_sleep_duration"],
        # 合并行只暴露 METRIC_SOURCE_PRIORITY 的 key + require/extra_metrics。本模块还读
        # hrv_status / sleep_start_time,两者都是 GarminData 真列但**不在**优先级表里 ——
        # 不显式声明 → SimpleNamespace 上属性不存在 → AttributeError 打死整个分析
        # (生产实测 24h 内 698 次)。新增对合并行的属性访问时必须同步加进这里,
        # 由 tests/test_sleep_merged_row_contract.py 的契约测试兜底。
        extra_metrics=["hrv_status", "sleep_start_time"],
    )


class SleepAnalysisService:
    """睡眠深度分析服务"""

    def get_deep_analysis(
        self, db: Session, user_id: int, days: int = 14
    ) -> Dict[str, Any]:
        """多维度睡眠深度分析"""
        records = _fetch_sleep_data(db, user_id, days)
        if len(records) < 3:
            return {"status": "insufficient_data", "message": "需要至少3天数据", "days_analyzed": len(records)}

        user = db.query(User).filter(User.id == user_id).first()
        age = _get_age(user)
        norms = _get_norm(age, AGE_NORMS)

        # Basic averages
        score_avg = _safe_avg([r.sleep_score for r in records])
        dur_avg = _safe_avg([r.total_sleep_duration for r in records])

        # Architecture percentages
        stage_pcts = _calc_stage_pcts(records)
        architecture = {f"{k}_pct": v for k, v in stage_pcts.items()}
        # 深睡**小时**均值 (twin builder 读 architecture["deep_hours"] 填
        # physiological.sleep_deep_h_avg_14d;formatter 按 "{:.1f}h" 渲染,
        # cross_review 按 <0.8h 判冲突 —— 单位必须是小时,不是上面的百分比)。
        # 无深睡数据时给 None 而非 0.0:0.0 会被 cross_review 当成"深睡严重不足"
        # 触发假冲突(把"不知道"讲成"很差"= 编造)。
        _deep_mins = [r.deep_sleep_duration for r in records if r.deep_sleep_duration is not None]
        architecture["deep_hours"] = round(_safe_avg(_deep_mins) / 60, 2) if _deep_mins else None

        # Architecture assessment vs norms
        arch_assessment = {}
        for stage in ["deep", "rem"]:
            val = stage_pcts[stage]
            lo, hi = norms[stage]
            if val < lo:
                arch_assessment[stage] = {"status": "below_normal", "value": val, "norm_range": [lo, hi]}
            elif val > hi:
                arch_assessment[stage] = {"status": "above_normal", "value": val, "norm_range": [lo, hi]}
            else:
                arch_assessment[stage] = {"status": "normal", "value": val, "norm_range": [lo, hi]}

        # HRV recovery
        hrv_values = [r.hrv for r in records if r.hrv is not None]
        bb_charged = [r.body_battery_charged for r in records if r.body_battery_charged is not None]
        hrv_recovery = {
            "avg_sleep_hrv": round(_safe_avg(hrv_values), 1),
            "hrv_7day_avg": records[0].hrv_7day_avg if records and records[0].hrv_7day_avg else None,
            "hrv_status": records[0].hrv_status if records else None,
            "avg_body_battery_charged": round(_safe_avg(bb_charged), 1),
            "recovery_quality": "good" if _safe_avg(bb_charged) >= 60 else ("fair" if _safe_avg(bb_charged) >= 40 else "poor"),
        }

        # Consistency (bedtime variability, adjust for cross-midnight)
        adj_bt = [b + 1440 if b < 360 else b for b in
                  [_time_to_minutes(r.sleep_start_time) for r in records if r.sleep_start_time] if b is not None]
        bt_std = round(_std_dev(adj_bt), 1) if len(adj_bt) >= 2 else None
        consistency = {"bedtime_std_minutes": bt_std,
                       "assessment": "regular" if bt_std and bt_std < 30 else ("irregular" if bt_std and bt_std > 60 else "moderate")}

        # Recommendations (conditional)
        _conds = [
            (stage_pcts["deep"] < norms["deep"][0], "深睡眠偏低，建议增加白天运动并避免睡前2h剧烈运动"),
            (stage_pcts["rem"] < norms["rem"][0], "REM偏少，可能与酒精/屏幕有关，建议睡前1h放下手机"),
            (consistency["assessment"] == "irregular", "入睡时间波动大，建议固定作息，周末偏差不超过1小时"),
            (hrv_recovery["recovery_quality"] == "poor", "夜间恢复差，建议检查压力并尝试睡前放松练习"),
            (score_avg < 60, "睡眠评分偏低，建议优化环境（温度16-20°C、遮光、安静）"),
        ]
        recs = [msg for cond, msg in _conds if cond]

        return {
            "status": "success",
            "days_analyzed": len(records),
            "sleep_score_avg": round(score_avg, 1),
            "duration_avg_hours": round(dur_avg / 60, 1),
            "architecture": architecture,
            "architecture_assessment": arch_assessment,
            "hrv_recovery": hrv_recovery,
            "consistency": consistency,
            "age_group": f"{age}岁" if age else "未知",
            "recommendations": recs,
        }

    def get_sleep_debt(
        self, db: Session, user_id: int, days: int = 14
    ) -> Dict[str, Any]:
        """累积睡眠债务计算"""
        records = _fetch_sleep_data(db, user_id, days)
        if not records:
            return {"status": "no_data", "message": "无睡眠数据", "days_analyzed": 0}

        user = db.query(User).filter(User.id == user_id).first()
        age = _get_age(user)
        rec_lo, rec_hi = _get_norm(age, NSF_RECS)
        target_hours = (rec_lo + rec_hi) / 2  # mid-point

        daily_records, total_deficit = [], 0.0
        for r in records:
            actual = (r.total_sleep_duration or 0) / 60
            deficit = target_hours - actual
            total_deficit += max(0, deficit)
            daily_records.append({"date": str(r.record_date), "actual_hours": round(actual, 1),
                                  "target_hours": target_hours, "deficit_hours": round(max(0, deficit), 1)})
        avg_deficit = total_deficit / len(records)

        severity = "none" if total_deficit < 2 else "mild" if total_deficit < 5 else "moderate" if total_deficit < 10 else "severe"
        n = math.ceil(total_deficit / 1.5) if total_deficit > 0 else 0
        recovery_msg = {"none": "睡眠充足，无需补觉", "mild": f"轻度不足，建议接下来{n}晚每晚多睡1-1.5小时",
                        "moderate": f"中度债务，建议{n}晚逐步补回，避免周末一次性补觉",
                        "severe": f"严重债务，需要1-2周调整作息，每晚保证{rec_lo:g}-{rec_hi:g}小时（你的年龄段推荐）"}

        return {
            "status": "success",
            "days_analyzed": len(records),
            "target_hours": target_hours,
            "daily_records": daily_records,
            "cumulative_debt_hours": round(total_deficit, 1),
            "avg_daily_deficit_hours": round(avg_deficit, 1),
            "debt_severity": severity,
            "recovery_plan": recovery_msg[severity],
        }

    def get_sleep_architecture(
        self, db: Session, user_id: int, days: int = 14
    ) -> Dict[str, Any]:
        """睡眠架构分析 - 各阶段百分比 vs 年龄基准"""
        records = _fetch_sleep_data(db, user_id, days)
        if len(records) < 3:
            return {"status": "insufficient_data", "message": "需要至少3天数据", "days_analyzed": len(records)}

        user = db.query(User).filter(User.id == user_id).first()
        age = _get_age(user)
        norms = _get_norm(age, AGE_NORMS)

        # Stage averages (minutes and percentages)
        stage_pcts = _calc_stage_pcts(records)
        _field = {"deep": "deep_sleep_duration", "light": "light_sleep_duration",
                  "rem": "rem_sleep_duration", "awake": "awake_duration"}
        avg_mins = {s: _safe_avg([getattr(r, _field[s]) for r in records]) for s in _field}
        stages = {s: {"minutes": round(avg_mins[s], 1), "pct": stage_pcts[s]} for s in stage_pcts}

        # Deviations
        deviations = {}
        for s in ["deep", "rem", "light", "awake"]:
            lo, hi = norms[s]
            if stage_pcts[s] < lo:
                deviations[s] = f"偏低（{stage_pcts[s]}% vs 正常 {lo}-{hi}%）"
            elif stage_pcts[s] > hi:
                deviations[s] = f"偏高（{stage_pcts[s]}% vs 正常 {lo}-{hi}%）"

        # Daily stage trends
        stage_trends = [{"date": str(r.record_date), "deep_min": r.deep_sleep_duration,
                         "light_min": r.light_sleep_duration, "rem_min": r.rem_sleep_duration,
                         "awake_min": r.awake_duration, "total_min": r.total_sleep_duration} for r in records]

        # Efficiency
        total_mins = _safe_avg([r.total_sleep_duration for r in records])
        in_bed_mins = total_mins + avg_mins["awake"]
        efficiency = round((total_mins / in_bed_mins * 100) if in_bed_mins > 0 else 0, 1)

        return {
            "status": "success",
            "days_analyzed": len(records),
            "stages": stages,
            "age_norms": {k: {"min_pct": v[0], "max_pct": v[1]} for k, v in norms.items()},
            "deviations": deviations if deviations else {"message": "各阶段均在正常范围内"},
            "stage_trends": stage_trends,
            "efficiency": efficiency,
            "efficiency_assessment": "excellent" if efficiency > 90 else ("good" if efficiency > 85 else ("fair" if efficiency > 75 else "poor")),
        }


sleep_analysis_service = SleepAnalysisService()
