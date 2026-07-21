"""日常健康记录API"""
import logging
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required, require_self_or_admin
from app.database import get_db
from app.models.daily_health import (
    DietRecord,
    ExerciseRecord,
    GarminData,
    OutdoorActivity,
    SupplementIntake,
    WaterIntake,
)
from app.models.user import User
from app.schemas.daily_health import (
    DietRecordCreate,
    ExerciseRecordCreate,
    ExerciseRecordResponse,
    ExerciseRecordUpdate,
    GarminDataCreate,
    GarminDataResponse,
    OutdoorActivityCreate,
    SupplementIntakeCreate,
    WaterIntakeCreate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _invalidate_twin(user_id) -> None:
    """Fail-soft twin-cache invalidation after a write (rank7: also drops pregen)."""
    if not user_id:
        return
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(user_id)
    except Exception:  # noqa: BLE001 — a Redis error must never fail the write
        pass


# Garmin数据
@router.post("/garmin", response_model=GarminDataResponse)
def create_garmin_data(
    data: GarminDataCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建Garmin数据（需要登录）"""
    # 强制使用当前用户ID
    user_id = current_user.id

    # 检查是否已存在
    existing = db.query(GarminData).filter(
        GarminData.user_id == user_id,
        GarminData.record_date == data.record_date
    ).first()

    if existing:
        for key, value in data.model_dump(exclude={"user_id", "record_date"}).items():
            if value is not None:
                setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        _invalidate_twin(user_id)
        return existing

    # 创建新记录，使用当前用户ID
    data_dict = data.model_dump()
    data_dict["user_id"] = user_id
    db_data = GarminData(**data_dict)
    db.add(db_data)
    db.commit()
    db.refresh(db_data)
    _invalidate_twin(user_id)
    return db_data


@router.get("/garmin/user/{user_id}", response_model=List[GarminDataResponse])
def get_user_garmin_data(
    user_id: int,
    start_date: date = None,
    end_date: date = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户的Garmin数据（需要登录，只能查看自己的数据）"""
    # 只能查看自己的数据
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")

    query = db.query(GarminData).filter(GarminData.user_id == current_user.id)

    if start_date:
        query = query.filter(GarminData.record_date >= start_date)
    if end_date:
        query = query.filter(GarminData.record_date <= end_date)

    data_list = query.order_by(GarminData.record_date.desc()).offset(skip).limit(limit).all()
    return data_list


def _merge_garmin_rows_by_date(rows: List[GarminData]) -> List[GarminDataResponse]:
    """把多源 GarminData 行按 record_date 合并成「每天一行」的响应。

    同一天可能有 apple-watch / garmin / ringconn / oura 多行;逐指标走
    device_source_priority.merge_daily_by_priority 取最高优先级的**非空**值。非合并字段
    (id / 睡眠起止 / hrv_status 等) 取该天「非空指标最多」的那行做代表。单源天原样返回
    (back-compat: 旧 garmin-only 用户行为不变)。输入需已按 record_date 降序。

    不合并的话客户端读 days[0] 会落到某个单源行(如 garmin 行 steps 为空)→ 首页步数/
    活动/卡路里 显示 0,而其实 apple-watch 行有真实步数(field-drift bug)。
    """
    from app.services.device_source_priority import (
        METRIC_SOURCE_PRIORITY,
        merge_daily_by_priority,
    )

    by_date: dict = {}
    order: List[date] = []
    for r in rows:
        if r.record_date not in by_date:
            by_date[r.record_date] = []
            order.append(r.record_date)
        by_date[r.record_date].append(r)

    def _richness(row: GarminData) -> int:
        return sum(1 for m in METRIC_SOURCE_PRIORITY if getattr(row, m, None) is not None)

    out: List[GarminDataResponse] = []
    for d in order:
        group = by_date[d]
        if len(group) == 1:
            out.append(GarminDataResponse.model_validate(group[0]))
            continue
        merged = merge_daily_by_priority(group)
        rep = max(group, key=_richness)  # 代表行: 非合并字段 + id 从最丰富的源取
        base = GarminDataResponse.model_validate(rep).model_dump()
        for k, v in merged.items():
            if k == "_source_by_metric":
                continue
            if k in base:
                base[k] = v
        out.append(GarminDataResponse.model_validate(base))
    return out


@router.get("/garmin/me", response_model=List[GarminDataResponse])
def get_my_garmin_data(
    start_date: date = None,
    end_date: date = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的Garmin数据（需要登录）。

    多源合并: 同一 record_date 跨 apple-watch / garmin / ringconn 多行 → 合成每天一行
    (见 _merge_garmin_rows_by_date)。skip/limit 按「合并后的天数」生效;两个真实调用方
    (mobile dashboard / web) 都传 date range、不传 skip/limit。
    """
    logger.info(f"[Overview API] 用户 {current_user.id} 请求 Garmin 数据, start_date={start_date}, end_date={end_date}")

    query = db.query(GarminData).filter(GarminData.user_id == current_user.id)

    if start_date:
        query = query.filter(GarminData.record_date >= start_date)
    if end_date:
        query = query.filter(GarminData.record_date <= end_date)

    query = query.order_by(GarminData.record_date.desc(), GarminData.id.desc())

    # date range 调用取全量再按天合并;无 range 的旧调用兜底限量(每天最多约 5 源 → ×8 够凑 limit 天)。
    raw_rows = query.all() if (start_date or end_date) else query.limit(max(limit, 1) * 8).all()

    merged = _merge_garmin_rows_by_date(raw_rows)
    result = merged[skip: skip + limit]

    logger.info(
        f"[Overview API] 用户 {current_user.id} {len(raw_rows)} 原始行 → {len(merged)} 天 (返回 {len(result)})"
    )
    if result:
        first = result[0]
        logger.info(f"[Overview API] 最新(合并): date={first.record_date}, sleep_score={first.sleep_score}, steps={first.steps}, resting_hr={first.resting_heart_rate}")

    return result


# 锻炼记录
@router.post("/exercise", response_model=ExerciseRecordResponse)
def create_exercise_record(
    exercise: ExerciseRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """创建锻炼记录.

    幂等保护 (2026-05-11, 2026-05-13 调整): 1 秒窗口内, 同 user + 同 exercise_type
    + 同 reps + 同 sets + 同 duration_seconds 视为双击重复, 直接返回已有记录, 不重复写.

    历史 5s 窗口太长, 用户做"俯卧撑两组 1 组 15 个" 时 Agent 连续 POST 两次
    完全相同字段, 第 2 组被 dedup 吃掉. 移动端有 useRef 锁兜底防双击, 后端 1s
    够拦防真双击, 而 Agent / 用户连续打卡两组通常 ≥ 1.5s 间隔不会被误吃.
    """
    from datetime import datetime, timedelta, timezone

    payload = exercise.model_dump()
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=1)

    dedup_q = db.query(ExerciseRecord).filter(
        ExerciseRecord.user_id == current_user.id,
        ExerciseRecord.exercise_type == payload.get("exercise_type"),
        ExerciseRecord.reps == payload.get("reps"),
        ExerciseRecord.sets == payload.get("sets"),
        ExerciseRecord.duration_seconds == payload.get("duration_seconds"),
        ExerciseRecord.created_at >= cutoff,
    )
    existing = dedup_q.order_by(ExerciseRecord.created_at.desc()).first()
    if existing is not None:
        logger.info(
            f"[exercise] dedup hit: user={current_user.id} type={payload.get('exercise_type')} "
            f"reps={payload.get('reps')} 1s 窗口内已存 id={existing.id}, 跳过"
        )
        return existing

    db_exercise = ExerciseRecord(user_id=current_user.id, **payload)
    db.add(db_exercise)
    db.commit()
    db.refresh(db_exercise)
    _invalidate_twin(current_user.id)
    return db_exercise


@router.get("/exercise/me/today", response_model=List[ExerciseRecordResponse])
def get_today_exercises(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取今日锻炼记录"""
    from datetime import date as date_type
    today = date_type.today()
    records = db.query(ExerciseRecord).filter(
        ExerciseRecord.user_id == current_user.id,
        ExerciseRecord.record_date == today,
    ).order_by(ExerciseRecord.created_at.desc()).all()
    return records


@router.put("/exercise/{exercise_id}", response_model=ExerciseRecordResponse)
def update_exercise_record(
    exercise_id: int,
    payload: ExerciseRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新单条锻炼记录（本人）"""
    record = db.query(ExerciseRecord).filter(
        ExerciseRecord.id == exercise_id,
        ExerciseRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    _invalidate_twin(current_user.id)
    return record


@router.delete("/exercise/{exercise_id}")
def delete_exercise_record(
    exercise_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """删除单条锻炼记录（本人）"""
    record = db.query(ExerciseRecord).filter(
        ExerciseRecord.id == exercise_id,
        ExerciseRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(record)
    db.commit()
    _invalidate_twin(current_user.id)
    return {"message": "已删除", "id": exercise_id}


@router.get("/exercise/me", response_model=List[ExerciseRecordResponse])
def get_my_exercises(
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取近N天锻炼记录"""
    from datetime import date as date_type, timedelta
    start = date_type.today() - timedelta(days=days)
    records = db.query(ExerciseRecord).filter(
        ExerciseRecord.user_id == current_user.id,
        ExerciseRecord.record_date >= start,
    ).order_by(ExerciseRecord.created_at.desc()).all()
    return records


# 饮食记录
@router.post("/diet", response_model=dict)
def create_diet_record(
    diet: DietRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建饮食记录"""
    require_self_or_admin(current_user, diet.user_id, resource="饮食记录")
    db_diet = DietRecord(**diet.model_dump())
    db.add(db_diet)
    db.commit()
    db.refresh(db_diet)
    _invalidate_twin(getattr(db_diet, "user_id", None))
    return {"message": "创建成功", "id": db_diet.id}


# 饮水记录
@router.post("/water", response_model=dict)
def create_water_intake(
    water: WaterIntakeCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建饮水记录"""
    require_self_or_admin(current_user, water.user_id, resource="饮水记录")
    db_water = WaterIntake(**water.model_dump())
    db.add(db_water)
    db.commit()
    db.refresh(db_water)
    _invalidate_twin(getattr(db_water, "user_id", None))
    return {"message": "创建成功", "id": db_water.id}


# 补剂记录
@router.post("/supplement", response_model=dict)
def create_supplement_intake(
    supplement: SupplementIntakeCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建补剂记录"""
    require_self_or_admin(current_user, supplement.user_id, resource="补剂记录")
    db_supplement = SupplementIntake(**supplement.model_dump())
    db.add(db_supplement)
    db.commit()
    db.refresh(db_supplement)
    _invalidate_twin(getattr(db_supplement, "user_id", None))
    return {"message": "创建成功", "id": db_supplement.id}


# 户外活动记录
@router.post("/outdoor", response_model=dict)
def create_outdoor_activity(
    activity: OutdoorActivityCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建户外活动记录"""
    require_self_or_admin(current_user, activity.user_id, resource="户外活动记录")
    db_activity = OutdoorActivity(**activity.model_dump())
    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)
    _invalidate_twin(getattr(db_activity, "user_id", None))
    return {"message": "创建成功", "id": db_activity.id}
