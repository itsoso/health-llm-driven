"""D1 读拉类工具进程内直读实现 (garmin-sync 治理 Wave 3).

背景: agent_executor 的读工具过去对每个维度打 localhost 回环
(`_api_get(f"{base}{path}")`) 重入整个 FastAPI 中间件栈, 付跨-worker 饥饿 + 内层 60s
中间件连杀 + 双鉴权/双 JSON 税。本模块把这些**只读**维度改为进程内直读 —— 与
`health_read.py`(canonical 可穿戴/化验读层)同一"读层"概念, 但拆成独立模块以守 500 行预算
且随增量 B 增长。

**契约(每个 reader 都遵守)**:
- 签名 `read_x(db, user_id, ...) -> str`; 同步 DB 读(由 agent_executor._read_in_process
  在 fresh SessionLocal + 线程池里跑)。
- **user_id 隔离**: 每个查询显式 `filter(... user_id == user_id)`; user_id 为 None → 诚实
  Error 串, 绝不裸查。
- **数据等价**: 输出与旧 HTTP 端点的响应体**数据等价** —— 走与端点**相同的 response_model**
  序列化(或逐字段复刻端点的 dict 投影), 由 golden-master 测试逐维度钉死。D1 是纯 transport
  变更, LLM 所见绝不因换传输而漂移。
- **绝不调 build_twin**(其 Phase B 忽略传入 db 自开 SessionLocal 连真 PG)。只做具体表查询 /
  复用已有 service 读函数。
- 显示截断由调用方 `agent_executor._truncate_for_display` 统一施加(单一真源), 此处不截断。
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import desc as sa_desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 北京时区 —— water/diet 端点用它把"今天"解析成日期(与 agent_executor.BEIJING_TZ 同值)。
BEIJING_TZ = timezone(timedelta(hours=8))
# 每日目标饮水量(毫升)—— 复刻 app/api/water.py::DAILY_WATER_TARGET(golden-master 钉死)。
DAILY_WATER_TARGET = 2000


def read_weight(db: Session, user_id: Optional[int], *, limit: int = 10) -> str:
    """体重记录 — 镜像 GET /weight/records/me?limit=N (app/api/weight.py::get_my_weight_records)。

    端点无 start/end 过滤(tool 不传), order by record_date desc, limit N, 经
    WeightRecordResponse 序列化。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询体重"
    from app.models.weight import WeightRecord
    from app.schemas.weight import WeightRecordResponse

    rows = (
        db.query(WeightRecord)
        .filter(WeightRecord.user_id == user_id)
        .order_by(sa_desc(WeightRecord.record_date))
        .limit(limit)
        .all()
    )
    payload = [WeightRecordResponse.model_validate(r).model_dump(mode="json") for r in rows]
    return json.dumps(payload, ensure_ascii=False, default=str)


def read_genetic_profiles(db: Session, user_id: Optional[int]) -> str:
    """基因档案列表 — 镜像 GET /genetic/profiles/me (genetic_data.py::list_profiles)。

    仅暴露档案**元数据**(provider/date/report_id/notes), 不含变异位点(genetic variants 是
    另一维度, 增量 B)。逐字段复刻端点的 dict 投影以保数据等价。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询基因档案"
    from app.models.genetic_data import GeneticProfile

    profiles = (
        db.query(GeneticProfile)
        .filter(GeneticProfile.user_id == user_id)
        .order_by(sa_desc(GeneticProfile.test_date))
        .all()
    )
    payload = [
        {
            "id": p.id,
            "user_id": p.user_id,
            "test_provider": p.test_provider,
            "test_date": str(p.test_date),
            "report_id": p.report_id,
            "notes": p.notes,
            "created_at": str(p.created_at) if p.created_at else None,
        }
        for p in profiles
    ]
    return json.dumps(payload, ensure_ascii=False, default=str)


def read_genetic_variants(
    db: Session, user_id: Optional[int], *, category: str = "", indicator: str = ""
) -> str:
    """基因变异位点列表 — 镜像 GET /genetic/variants/me (genetic_data.py::list_variants)。

    **Tier-5 敏感**:严格 user_id + active-profile 双重隔离(profile 也按 user_id 解析,
    再 filter profile_id)——A 的会话绝不可能拿到 B 的变异。逐字段复刻端点的 14 字段 dict 投影。

    indicator 传入时按 gene_name 过滤(镜像 _exec_health_query 的 genetic+indicator 特殊路径:
    命中则只返回命中项;无命中回退全量,与旧路径数据等价)。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询基因变异"
    from app.models.genetic_data import GeneticVariant
    from app.services.genetic_report import _resolve_active_profile

    profile = _resolve_active_profile(db, user_id)
    if profile is None:
        variants = []
    else:
        q = db.query(GeneticVariant).filter(
            GeneticVariant.user_id == user_id,
            GeneticVariant.profile_id == profile.id,
        )
        if category:
            q = q.filter(GeneticVariant.category == category)
        variants = q.order_by(GeneticVariant.category, GeneticVariant.gene_name).all()
    payload = [
        {
            "id": v.id,
            "profile_id": v.profile_id,
            "rsid": v.rsid,
            "category": v.category,
            "gene_name": v.gene_name,
            "variant_name": v.variant_name,
            "genotype": v.genotype,
            "raw_genotype": v.raw_genotype,
            "result_label": v.result_label,
            "risk_level": v.risk_level,
            "mapping_source": v.mapping_source,
            "evidence_level": v.evidence_level,
            "description": v.description,
            "health_implications": v.health_implications,
        }
        for v in variants
    ]
    if indicator:
        up = indicator.upper()
        matched = [d for d in payload if up in str(d.get("gene_name") or "").upper()]
        if matched:
            return json.dumps(matched, ensure_ascii=False, default=str)
    return json.dumps(payload, ensure_ascii=False, default=str)


def read_supplement_daily_guide(db: Session, user_id: Optional[int]) -> str:
    """每日补剂动态指南 — 镜像 GET /supplements/daily-guide
    (supplements.py::get_supplement_daily_guide → get_daily_supplement_guide)。

    复用既有 service 函数(非 LLM, 确定性), target_date=None → 今天, 与端点一致。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法获取补剂指南"
    from app.services.daily_supplement_guide import get_daily_supplement_guide

    guide = get_daily_supplement_guide(db, user_id, None)
    return json.dumps(guide, ensure_ascii=False, default=str)


def read_blood_pressure(db: Session, user_id: Optional[int], *, limit: int = 10) -> str:
    """血压记录 — 镜像 GET /blood-pressure/records/me?limit=N
    (blood_pressure.py::get_my_blood_pressure_records)。

    tool 只传 limit(不传 start/end), order by record_date desc, 经
    BloodPressureRecordResponse 序列化，并复用 API 的权威展示/安全字段
    （category、category_color、safety_guidance）—— 与端点逐字段一致
    (golden-master 校验)。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询血压"
    from app.models.blood_pressure import BloodPressureRecord
    from app.schemas.blood_pressure import (
        BloodPressureRecordResponse,
        BloodPressureSafetyGuidance,
    )
    from app.utils.blood_pressure_classify import blood_pressure_display

    records = (
        db.query(BloodPressureRecord)
        .filter(BloodPressureRecord.user_id == user_id)
        .order_by(sa_desc(BloodPressureRecord.record_date))
        .limit(limit)
        .all()
    )
    payload = []
    for r in records:
        resp = BloodPressureRecordResponse.model_validate(r)
        display = blood_pressure_display(r.systolic, r.diastolic)
        resp.category = display["category"]
        resp.category_color = display["category_color"]
        safety_guidance = display["safety_guidance"]
        resp.safety_guidance = (
            BloodPressureSafetyGuidance.model_validate(safety_guidance)
            if safety_guidance is not None
            else None
        )
        payload.append(resp.model_dump(mode="json"))
    return json.dumps(payload, ensure_ascii=False, default=str)


def _water_record_to_response(record):
    """复刻 app/api/water.py::_convert_to_response(不 import api 层)。"""
    from datetime import time as dt_time

    from app.schemas.water import WaterRecordResponse

    drink_time = None
    if hasattr(record, "intake_time") and record.intake_time:
        if isinstance(record.intake_time, datetime):
            drink_time = record.intake_time.time()
        elif isinstance(record.intake_time, dt_time):
            drink_time = record.intake_time

    return WaterRecordResponse(
        id=record.id,
        user_id=record.user_id,
        record_date=record.record_date,
        amount=record.amount or 0,
        drink_time=drink_time,
        drink_type=record.drink_type if hasattr(record, "drink_type") else None,
        notes=record.notes if hasattr(record, "notes") else None,
        created_at=record.created_at,
        updated_at=record.updated_at if hasattr(record, "updated_at") else None,
    )


def read_daily_water(db: Session, user_id: Optional[int]) -> str:
    """今日饮水汇总 — 镜像 GET /water/records/me/date/{today}
    (water.py::get_my_daily_water_summary)。

    today = 北京时区当日(与 agent_executor endpoint_map 同源)。逐字段复刻端点的
    DailyWaterSummary 聚合(total_amount / progress / records_count / records)。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询饮水"
    from app.models.daily_health import WaterIntake
    from app.schemas.water import DailyWaterSummary

    record_date = datetime.now(BEIJING_TZ).date()
    records = (
        db.query(WaterIntake)
        .filter(WaterIntake.user_id == user_id, WaterIntake.record_date == record_date)
        .order_by(WaterIntake.created_at)
        .all()
    )
    total_amount = sum(r.amount or 0 for r in records)
    progress = round((total_amount / DAILY_WATER_TARGET) * 100, 1) if DAILY_WATER_TARGET > 0 else 0
    summary = DailyWaterSummary(
        record_date=record_date,
        total_amount=total_amount,
        target_amount=DAILY_WATER_TARGET,
        progress_percentage=min(progress, 100),
        records_count=len(records),
        records=[_water_record_to_response(r) for r in records],
    )
    return json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, default=str)


def _diet_record_to_response(record):
    """复刻 app/api/diet.py::_convert_to_response(不 import api 层)。

    image_url 签名走**共用** util `diet_response_image_url`(与 api 同一函数对象)——
    非确定性签名字段无法 parity-test,共用防静默漂移(单一真源)。其余字段确定性,
    由 golden-master 逐字段钉死。
    """
    from datetime import time as dt_time

    from app.schemas.diet import DietRecordResponse, MealType
    from app.utils.diet_image_url import diet_response_image_url

    meal_time = None
    if hasattr(record, "meal_time") and record.meal_time:
        if isinstance(record.meal_time, str):
            try:
                meal_time = datetime.strptime(record.meal_time, "%H:%M").time()
            except (ValueError, TypeError):
                meal_time = None
        elif isinstance(record.meal_time, dt_time):
            meal_time = record.meal_time

    return DietRecordResponse(
        id=record.id,
        user_id=record.user_id,
        record_date=record.record_date,
        meal_type=MealType(record.meal_type) if record.meal_type else MealType.EXTRA,
        meal_time=meal_time,
        food_items=record.food_items or "",
        food_id=getattr(record, "food_id", None),
        source=getattr(record, "source", None),
        calories=record.calories,
        protein=record.protein,
        carbs=record.carbs,
        fat=record.fat,
        fiber=record.fiber,
        notes=record.notes,
        image_url=diet_response_image_url(getattr(record, "image_url", None), record.user_id),
        ai_recognized=getattr(record, "ai_recognized", 0),
        ai_confidence=getattr(record, "ai_confidence", None),
        health_tips=getattr(record, "health_tips", None),
        created_at=record.created_at,
        updated_at=record.updated_at if hasattr(record, "updated_at") else None,
    )


def read_daily_diet(db: Session, user_id: Optional[int]) -> str:
    """今日饮食汇总 — 镜像 GET /diet/records/me/date/{today}
    (diet.py::get_my_daily_diet_summary)。

    today = 北京时区当日。逐字段复刻端点的 DailyDietSummary 聚合(热量/宏量四舍五入到 1 位 +
    meals_count + meals)。每餐经复刻的 _diet_record_to_response(含 image_url 签名 + schema
    的 display_message post-init)。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询饮食"
    from app.models.daily_health import DietRecord
    from app.schemas.diet import DailyDietSummary

    record_date = datetime.now(BEIJING_TZ).date()
    records = (
        db.query(DietRecord)
        .filter(DietRecord.user_id == user_id, DietRecord.record_date == record_date)
        .order_by(DietRecord.created_at)
        .all()
    )
    total_calories = sum(r.calories or 0 for r in records)
    total_protein = sum(r.protein or 0 for r in records)
    total_carbs = sum(r.carbs or 0 for r in records)
    total_fat = sum(r.fat or 0 for r in records)
    total_fiber = sum(r.fiber or 0 for r in records)
    summary = DailyDietSummary(
        record_date=record_date,
        total_calories=total_calories,
        total_protein=round(total_protein, 1),
        total_carbs=round(total_carbs, 1),
        total_fat=round(total_fat, 1),
        total_fiber=round(total_fiber, 1),
        meals_count=len(records),
        meals=[_diet_record_to_response(r) for r in records],
    )
    return json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, default=str)


def read_workouts(db: Session, user_id: Optional[int], *, days: int = 7) -> str:
    """运动记录(Garmin 同步的跑步/骑行等)— 镜像 GET /workout/me?days=N
    (workout.py::get_my_workouts)。

    tool 只传 days(不传 workout_type/start_date/end_date), 走端点的 days 分支:
    query_start = today-(days-1) 若 days>1 否则 today; order by workout_date desc, start_time
    desc; 经 WorkoutSummary 序列化。today 用 get_china_today()(与端点同源)。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询运动"
    from app.models.daily_health import WorkoutRecord
    from app.schemas.workout import WorkoutSummary
    from app.utils.timezone import get_china_today

    days = int(days)
    today = get_china_today()
    query_start = today - timedelta(days=days - 1) if days > 1 else today
    query_end = today
    records = (
        db.query(WorkoutRecord)
        .filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_date >= query_start,
            WorkoutRecord.workout_date <= query_end,
        )
        .order_by(WorkoutRecord.workout_date.desc(), WorkoutRecord.start_time.desc())
        .all()
    )
    payload = [
        WorkoutSummary(
            id=r.id,
            workout_date=r.workout_date,
            workout_type=r.workout_type,
            workout_name=r.workout_name,
            duration_seconds=r.duration_seconds,
            distance_meters=r.distance_meters,
            avg_heart_rate=r.avg_heart_rate,
            calories=r.calories,
            feeling=r.feeling,
            has_ai_analysis=r.ai_analysis is not None,
        ).model_dump(mode="json")
        for r in records
    ]
    return json.dumps(payload, ensure_ascii=False, default=str)


def read_manual_exercises(db: Session, user_id: Optional[int], *, days: int = 7) -> str:
    """手动录入锻炼(俯卧撑/瑜伽等)— 镜像 GET /daily-health/exercise/me?days=N
    (daily_health.py::get_my_exercises)。

    start = date.today()-days(端点用 naive 本地 date.today(), 服务器 = Asia/Shanghai);
    filter record_date >= start; order by created_at desc; 经 ExerciseRecordResponse 序列化
    (含 schema 的 display_message post-init)。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询锻炼"
    from app.models.daily_health import ExerciseRecord
    from app.schemas.daily_health import ExerciseRecordResponse

    days = int(days)
    start = date.today() - timedelta(days=days)
    records = (
        db.query(ExerciseRecord)
        .filter(ExerciseRecord.user_id == user_id, ExerciseRecord.record_date >= start)
        .order_by(sa_desc(ExerciseRecord.created_at))
        .all()
    )
    payload = [ExerciseRecordResponse.model_validate(r).model_dump(mode="json") for r in records]
    return json.dumps(payload, ensure_ascii=False, default=str)


def _life_event_out(ep):
    """复刻 app/api/episodes.py::_life_event_out(不 import api 层)。"""
    from app.schemas.episode import LifeEventOut
    from app.services.occurred_time import precision_display

    snap = ep.context_snapshot or {}
    precision = str(snap.get("occurred_precision") or "exact")
    raw = snap.get("occurred_raw")
    return LifeEventOut(
        id=ep.id,
        title=ep.headline or "",
        occurred_at=ep.occurred_at,
        occurred_precision=precision,
        occurred_display=precision_display(ep.occurred_at, precision, raw),
        notes=snap.get("notes"),
    )


def read_life_events(db: Session, user_id: Optional[int], *, days: int = 7) -> str:
    """生活事件时间线 — 镜像 GET /episodes/me/life-events?days=N
    (episodes.py::list_life_events)。

    since = now(utc)-days; filter episode_type=='life_event' + occurred_at>=since;
    order by occurred_at asc; limit 200; 经复刻的 _life_event_out(用 precision_display 服务)
    序列化为 LifeEventOut。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询生活事件"
    from app.models.episode import HealthEpisode

    days = int(days)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(HealthEpisode)
        .filter(
            HealthEpisode.user_id == user_id,
            HealthEpisode.episode_type == "life_event",
            HealthEpisode.occurred_at >= since,
        )
        .order_by(HealthEpisode.occurred_at.asc())
        .limit(200)
        .all()
    )
    payload = [_life_event_out(ep).model_dump(mode="json") for ep in rows]
    return json.dumps(payload, ensure_ascii=False, default=str)


def read_supplement_stats(db: Session, user_id: Optional[int], *, days: int = 7) -> str:
    """补剂依从统计 — 镜像 GET /supplements/me/stats?days=N
    (supplements.py::get_my_supplement_stats, 无 response_model → inline list[dict])。

    end_date = date.today(); start_date = end_date-(days-1); 遍历 is_active 补剂定义,
    统计窗内 taken 次数。逐字段复刻端点的 dict 投影。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询补剂统计"
    from app.models.supplement import SupplementDefinition, SupplementRecord

    days = int(days)
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    supplements = (
        db.query(SupplementDefinition)
        .filter(SupplementDefinition.user_id == user_id, SupplementDefinition.is_active)
        .all()
    )
    stats = []
    for supp in supplements:
        records = (
            db.query(SupplementRecord)
            .filter(
                SupplementRecord.user_id == user_id,
                SupplementRecord.supplement_id == supp.id,
                SupplementRecord.record_date >= start_date,
                SupplementRecord.record_date <= end_date,
            )
            .all()
        )
        taken_count = sum(1 for r in records if r.taken)
        stats.append(
            {
                "supplement_id": supp.id,
                "supplement_name": supp.name,
                "category": supp.category,
                "total_days": days,
                "taken_days": taken_count,
                "completion_rate": round(taken_count / days * 100, 1),
            }
        )
    return json.dumps(stats, ensure_ascii=False, default=str)
