"""D1 读拉类进程内直读 —— 非敏感确定性分析维度 (garmin-sync 治理 Wave 3, 增量 B1).

背景与契约见 `agent_read_tools.py` 模块 docstring。本模块单独存放**分析维度**的 reader,
仅为守住 500 行文件预算(`agent_read_tools.py` 已 ~440 行)—— 契约一字不差:

- 签名 `read_x(db, user_id, ...) -> str`; 同步 DB 读(由 agent_executor._read_in_process
  在 fresh SessionLocal + 线程池里跑)。
- **user_id 隔离**: 每个查询显式 `filter(... user_id == user_id)`(或经同样按 user_id 过滤的
  service); user_id 为 None → 诚实 Error 串, 绝不裸查。
- **数据等价**: 输出与旧 HTTP 端点响应体**数据等价** —— comprehensive/sleep 复用
  `GarminAnalysisService`(0 LLM, 端点即其薄包装); spo2 两维**逐字段复刻** `app/api/spo2.py`
  的确定性算法(见 §layering)。golden-master 测试逐维度钉死。D1 是纯 transport 变更。
- **绝不调 build_twin**; 显示截断由调用方 `_truncate_for_display` 统一施加, 此处不截断。

§layering(硬约束 #6): service 层绝不 import api 层。`app/api/spo2.py` 的夜间血氧算法写在
api 文件内的私有函数里(无对应 service),故此处**复刻**这些确定性函数(与 water/diet/events
的 `_x_to_response` 复刻同一先例),并复用 `app/schemas/spo2.py` 的 Pydantic model 保序列化
一致。复刻的抗漂移护栏 = golden-master parity 测试(reader 输出 == 真 route 输出)。
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import desc as sa_desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ── comprehensive / sleep — 复用 GarminAnalysisService(确定性, 端点即薄包装)──────────


def read_comprehensive_analysis(db: Session, user_id: Optional[int], *, days: int = 7) -> str:
    """Garmin 综合分析 — 镜像 GET /garmin-analysis/me/comprehensive?days=N
    (garmin_analysis.py::get_my_comprehensive_analysis, 无 response_model → dict)。

    端点即 `GarminAnalysisService().get_comprehensive_analysis(db, uid, days)` 薄包装;
    该 service 内部按 user_id 过滤(merged_daily_rows),故用户隔离与端点同源。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询综合分析"
    from app.services.garmin_analysis import GarminAnalysisService

    result = GarminAnalysisService().get_comprehensive_analysis(db, user_id, int(days))
    return json.dumps(result, ensure_ascii=False, default=str)


def read_sleep_analysis(db: Session, user_id: Optional[int], *, days: int = 7) -> str:
    """Garmin 睡眠质量分析 — 镜像 GET /garmin-analysis/me/sleep?days=N
    (garmin_analysis.py::analyze_my_sleep_quality, 无 response_model → dict)。

    端点即 `GarminAnalysisService().analyze_sleep_quality(db, uid, days)` 薄包装。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法分析睡眠质量"
    from app.services.garmin_analysis import GarminAnalysisService

    result = GarminAnalysisService().analyze_sleep_quality(db, user_id, int(days))
    return json.dumps(result, ensure_ascii=False, default=str)


# ── spo2 夜间血氧算法(复刻 app/api/spo2.py 私有函数, 不 import api 层)────────────────


def _compute_desaturation_events(values: List[int]) -> int:
    """复刻 app/api/spo2.py::_compute_desaturation_events。"""
    if len(values) < 2:
        return 0
    events = 0
    baseline = values[0]
    in_desat = False
    for v in values[1:]:
        if not in_desat and baseline - v >= 3:
            events += 1
            in_desat = True
        elif v >= baseline - 1:
            in_desat = False
            baseline = v
        if v > baseline:
            baseline = v
    return events


def _build_night_summary(record_date, samples, sleep_hours: Optional[float] = None):
    """复刻 app/api/spo2.py::_build_night_summary(返回 SpO2NightSummary)。"""
    from app.schemas.spo2 import SpO2NightSummary

    if not samples:
        return SpO2NightSummary(record_date=record_date)

    values = [s.spo2_value for s in samples]
    avg_val = sum(values) / len(values)
    below_90 = sum(1 for v in values if v < 90)
    desat = _compute_desaturation_events(values)

    hours = sleep_hours
    if hours is None and len(values) > 1:
        hours = len(values) / 60.0

    odi = round(desat / hours, 1) if hours and hours > 0 else None

    return SpO2NightSummary(
        record_date=record_date,
        avg_spo2=round(avg_val, 1),
        min_spo2=min(values),
        max_spo2=max(values),
        below_90_count=below_90,
        desaturation_events=desat,
        odi=odi,
        data_points=len(values),
    )


def _get_sleep_times(db: Session, user_id: int, record_date):
    """复刻 app/api/spo2.py::_get_sleep_times(返回 (start, end, duration_h))。"""
    from app.models.daily_health import GarminData

    garmin = (
        db.query(GarminData)
        .filter(GarminData.user_id == user_id, GarminData.record_date == record_date)
        .first()
    )
    if not garmin:
        return None, None, None
    start = (
        garmin.sleep_start_time.strftime("%H:%M")
        if hasattr(garmin.sleep_start_time, "strftime")
        else (str(garmin.sleep_start_time)[:5] if garmin.sleep_start_time else None)
    )
    end = (
        garmin.sleep_end_time.strftime("%H:%M")
        if hasattr(garmin.sleep_end_time, "strftime")
        else (str(garmin.sleep_end_time)[:5] if garmin.sleep_end_time else None)
    )
    duration_h = garmin.total_sleep_duration / 60.0 if garmin.total_sleep_duration else None
    return start, end, duration_h


def _build_nightly_response(db: Session, user_id: int, record_date, window: str = "sleep"):
    """复刻 app/api/spo2.py::get_nightly_spo2 主体(返回 SpO2NightlyResponse)。

    window='sleep'(默认): timeline/summary 截断到 sleep_start~sleep_end 睡眠期; 无 GarminData
    睡眠时段时 in_sleep_window 恒 True(不截断)。选夜由调用方确定,此处按给定 record_date 组装,
    samples order by epoch_ms asc(与端点同 —— 绝对时间序,防日间/凌晨样本乱序)。
    """
    from app.models.daily_health import SpO2Sample
    from app.schemas.spo2 import SpO2NightlyResponse, SpO2Point

    samples = (
        db.query(SpO2Sample)
        .filter(
            SpO2Sample.user_id == user_id,
            SpO2Sample.record_date == record_date,
        )
        .order_by(SpO2Sample.epoch_ms.asc())
        .all()
    )

    sleep_start, sleep_end, sleep_hours = _get_sleep_times(db, user_id, record_date)

    def in_sleep_window(s) -> bool:
        if not sleep_start or not sleep_end:
            return True
        tstr = (
            s.sample_time.strftime("%H:%M")
            if hasattr(s.sample_time, "strftime")
            else str(s.sample_time)[:5]
        )
        if sleep_start <= sleep_end:
            return sleep_start <= tstr <= sleep_end
        # 跨日: sleep_start (22:00) > sleep_end (06:00)
        return tstr >= sleep_start or tstr <= sleep_end

    filtered = [s for s in samples if in_sleep_window(s)] if window == "sleep" else samples

    summary = _build_night_summary(record_date, filtered, sleep_hours)

    timeline = [
        SpO2Point(
            timestamp=s.epoch_ms or 0,
            time=(
                s.sample_time.strftime("%H:%M")
                if hasattr(s.sample_time, "strftime")
                else str(s.sample_time)[:5]
            ),
            value=s.spo2_value,
        )
        for s in filtered
    ]

    window_start = timeline[0].time if timeline else None
    window_end = timeline[-1].time if timeline else None

    return SpO2NightlyResponse(
        record_date=record_date,
        summary=summary,
        timeline=timeline,
        sleep_start=sleep_start,
        sleep_end=sleep_end,
        window=window,
        window_start=window_start,
        window_end=window_end,
    )


def read_latest_night_spo2(db: Session, user_id: Optional[int]) -> str:
    """最近一晚夜间血氧 — 镜像 GET /spo2/me/latest-night
    (spo2.py::get_latest_night_spo2, response_model=SpO2NightlyResponse)。

    选夜逻辑逐字复刻端点: 取 user 的 max(record_date)(record_date = 醒来次日,一晚样本挂在
    该日),再对该日按 window='sleep' 默认组装。无采样 → 诚实 Error 串(端点此时 404;两路
    都给非数据信号,LLM 所见等价)。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询夜间血氧"
    from app.models.daily_health import SpO2Sample
    from app.schemas.spo2 import SpO2NightlyResponse

    latest = (
        db.query(SpO2Sample.record_date)
        .filter(SpO2Sample.user_id == user_id)
        .order_by(sa_desc(SpO2Sample.record_date))
        .first()
    )
    if not latest:
        return "Error: 暂无血氧采样数据"

    resp = _build_nightly_response(db, user_id, latest[0], window="sleep")
    return json.dumps(
        SpO2NightlyResponse.model_validate(resp).model_dump(mode="json"),
        ensure_ascii=False,
        default=str,
    )


def _correlate_single_night(db: Session, user_id: int, record_date):
    """复刻 app/api/spo2.py::_correlate_single_night(返回 NightCorrelation | None)。"""
    from app.models.daily_health import SleepLevelInterval, SpO2Sample
    from app.schemas.spo2 import NightCorrelation, SleepStageSpO2Stats

    samples = (
        db.query(SpO2Sample)
        .filter(SpO2Sample.user_id == user_id, SpO2Sample.record_date == record_date)
        .order_by(SpO2Sample.epoch_ms.asc())
        .all()
    )
    intervals = (
        db.query(SleepLevelInterval)
        .filter(
            SleepLevelInterval.user_id == user_id,
            SleepLevelInterval.record_date == record_date,
        )
        .order_by(SleepLevelInterval.start_epoch_ms.asc())
        .all()
    )

    if not samples or not intervals:
        return None

    stage_samples: Dict[str, List[int]] = {"deep": [], "light": [], "rem": [], "awake": []}
    stage_durations: Dict[str, float] = {"deep": 0, "light": 0, "rem": 0, "awake": 0}

    for iv in intervals:
        if iv.activity_level in stage_durations:
            stage_durations[iv.activity_level] += (iv.end_epoch_ms - iv.start_epoch_ms) / 60000.0

    for s in samples:
        if not s.epoch_ms:
            continue
        for iv in intervals:
            if iv.start_epoch_ms <= s.epoch_ms < iv.end_epoch_ms:
                if iv.activity_level in stage_samples:
                    stage_samples[iv.activity_level].append(s.spo2_value)
                break

    stages = []
    for stage_name in ["deep", "rem", "light", "awake"]:
        vals = stage_samples[stage_name]
        if not vals:
            stages.append(
                SleepStageSpO2Stats(
                    stage=stage_name,
                    duration_minutes=round(stage_durations[stage_name], 1),
                )
            )
            continue
        desat = _compute_desaturation_events(vals)
        stages.append(
            SleepStageSpO2Stats(
                stage=stage_name,
                avg_spo2=round(sum(vals) / len(vals), 1),
                min_spo2=min(vals),
                desaturation_events=desat,
                below_90_count=sum(1 for v in vals if v < 90),
                duration_minutes=round(stage_durations[stage_name], 1),
                data_points=len(vals),
            )
        )

    all_values = [s.spo2_value for s in samples]
    total_hours = sum(stage_durations.values()) / 60.0
    total_desat = _compute_desaturation_events(all_values)
    overall_odi = round(total_desat / total_hours, 1) if total_hours > 0 else None

    stages_with_data = [st for st in stages if st.data_points > 0 and st.avg_spo2 is not None]
    worst = (
        min(stages_with_data, key=lambda s: s.avg_spo2, default=None)
        if stages_with_data
        else None
    )

    risk = "normal"
    risk_detail = None
    if overall_odi is not None:
        if overall_odi >= 30:
            risk = "severe"
            risk_detail = f"ODI {overall_odi} 次/小时，重度异常，强烈建议尽快就医"
        elif overall_odi >= 15:
            risk = "moderate"
            risk_detail = f"ODI {overall_odi} 次/小时，中度异常，建议进行多导睡眠监测 (PSG)"
        elif overall_odi >= 5:
            risk = "mild"
            risk_detail = f"ODI {overall_odi} 次/小时，轻度异常，可能存在轻度 OSAHS"

    rem_data = stage_samples.get("rem", [])
    if rem_data and len(rem_data) >= 5:
        rem_below = sum(1 for v in rem_data if v < 90)
        if rem_below / len(rem_data) > 0.1 and risk == "normal":
            risk = "mild"
            risk_detail = f"REM 期间 {round(rem_below/len(rem_data)*100)}% 血氧 <90%，需关注"

    return NightCorrelation(
        record_date=record_date,
        stages=stages,
        overall_odi=overall_odi,
        worst_stage=worst.stage if worst else None,
        apnea_risk=risk,
        apnea_risk_detail=risk_detail,
    )


def read_spo2_sleep_correlation(db: Session, user_id: Optional[int], *, days: int = 7) -> str:
    """睡眠阶段 × 血氧关联 — 镜像 GET /spo2/me/sleep-correlation?days=N
    (spo2.py::get_spo2_sleep_correlation, response_model=SpO2SleepCorrelationResponse)。

    窗口 = [today-(days-1), today](端点用 date.today(), 服务器 = Asia/Shanghai); 遍历窗内
    有采样的日期, 逐夜 _correlate_single_night, 再逐字复刻端点的 summary 聚合(per-stage 均值/
    worst_stage/风险分布/overall_assessment/disclaimer)。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询睡眠血氧关联"
    from datetime import timedelta

    from app.models.daily_health import SpO2Sample
    from app.schemas.spo2 import SpO2SleepCorrelationResponse

    days = int(days)
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    dates_with_data = (
        db.query(SpO2Sample.record_date)
        .filter(
            SpO2Sample.user_id == user_id,
            SpO2Sample.record_date >= start_date,
            SpO2Sample.record_date <= end_date,
        )
        .distinct()
        .order_by(SpO2Sample.record_date)
        .all()
    )

    nights = []
    for (rd,) in dates_with_data:
        nc = _correlate_single_night(db, user_id, rd)
        if nc:
            nights.append(nc)

    summary = None
    if nights:
        stage_agg: Dict[str, List[float]] = {"deep": [], "rem": [], "light": [], "awake": []}
        odi_list = []
        risk_counts = {"normal": 0, "mild": 0, "moderate": 0, "severe": 0}

        for n in nights:
            if n.overall_odi is not None:
                odi_list.append(n.overall_odi)
            risk_counts[n.apnea_risk] = risk_counts.get(n.apnea_risk, 0) + 1
            for st in n.stages:
                if st.avg_spo2 is not None and st.stage in stage_agg:
                    stage_agg[st.stage].append(st.avg_spo2)

        per_stage_avg = {}
        for stage, vals in stage_agg.items():
            if vals:
                per_stage_avg[stage] = round(sum(vals) / len(vals), 1)

        worst_stage = min(per_stage_avg, key=per_stage_avg.get) if per_stage_avg else None

        summary = {
            "nights_analyzed": len(nights),
            "avg_odi": round(sum(odi_list) / len(odi_list), 1) if odi_list else None,
            "per_stage_avg_spo2": per_stage_avg,
            "worst_stage": worst_stage,
            "risk_distribution": risk_counts,
            "overall_assessment": (
                "重度风险"
                if risk_counts.get("severe", 0) > 0
                else "中度风险"
                if risk_counts.get("moderate", 0) > 0
                else "轻度风险"
                if risk_counts.get("mild", 0) > 0
                else "正常"
            ),
            "disclaimer": "腕表 SpO2 仅供筛查参考，确诊 OSAHS 需多导睡眠监测 (PSG)",
        }

    resp = SpO2SleepCorrelationResponse(days=days, nights=nights, summary=summary)
    return json.dumps(
        SpO2SleepCorrelationResponse.model_validate(resp).model_dump(mode="json"),
        ensure_ascii=False,
        default=str,
    )
