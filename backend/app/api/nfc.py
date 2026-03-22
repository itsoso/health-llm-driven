"""NFC 碰触快速记录 API

支持 iOS 快捷指令通过 NFC 自动化触发，实现：
- 饮水记录（碰一下 = 250ml）
- 大便计时（碰一下开始，再碰一下结束）
- 小便记录（碰一下即记录）
"""
import logging
from datetime import date, datetime, time, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.models.excretion import ExcretionRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfc", tags=["nfc"])

# 内存中的大便计时状态：user_id -> start_time (UTC)
_bowel_timers: dict[int, datetime] = {}

BEIJING_TZ = timezone(timedelta(hours=8))


class NfcTapRequest(BaseModel):
    """NFC 碰触请求"""
    action: str = Field(..., pattern="^(water|bowel|urine)$")
    amount_ml: Optional[int] = Field(250, ge=50, le=2000)  # 仅 water 使用
    drink_type: Optional[str] = "水"  # 仅 water 使用


class NfcTapResponse(BaseModel):
    """NFC 碰触响应"""
    status: str  # recorded / timer_started / timer_stopped
    message: str  # 人类可读的结果
    record_id: Optional[int] = None
    duration_minutes: Optional[int] = None  # 大便时长（仅 bowel stop）


@router.post("/tap", response_model=NfcTapResponse)
async def nfc_tap(
    req: NfcTapRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """NFC 碰触记录

    - water: 直接记录饮水（默认 250ml）
    - bowel: 第一次碰触开始计时，第二次碰触结束并记录
    - urine: 直接记录小便
    """
    now_utc = datetime.now(timezone.utc)
    now_beijing = now_utc.astimezone(BEIJING_TZ)
    today = now_beijing.date()
    current_time = now_beijing.time()

    if req.action == "water":
        return _record_water(db, current_user.id, today, current_time, req.amount_ml or 250, req.drink_type or "水")

    elif req.action == "bowel":
        return _handle_bowel(db, current_user.id, today, current_time, now_utc)

    elif req.action == "urine":
        return _record_urine(db, current_user.id, today, current_time)

    raise HTTPException(status_code=400, detail=f"未知动作: {req.action}")


@router.get("/bowel-status")
async def bowel_timer_status(
    current_user: User = Depends(get_current_user_required),
):
    """查询当前大便计时状态"""
    start = _bowel_timers.get(current_user.id)
    if start:
        elapsed = (datetime.now(timezone.utc) - start).total_seconds() / 60
        return {
            "timing": True,
            "started_at": start.astimezone(BEIJING_TZ).strftime("%H:%M:%S"),
            "elapsed_minutes": round(elapsed, 1),
        }
    return {"timing": False}


def _record_water(db: Session, user_id: int, today: date, current_time: time, amount_ml: int, drink_type: str):
    """记录饮水"""
    from app.models.daily_health import WaterIntake
    now_beijing = datetime.now(BEIJING_TZ)
    record = WaterIntake(
        user_id=user_id,
        record_date=today,
        intake_time=now_beijing,
        amount_ml=amount_ml,
        drink_type=drink_type,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info(f"NFC 饮水记录: user={user_id}, {amount_ml}ml")
    return NfcTapResponse(
        status="recorded",
        message=f"已记录饮{drink_type} {amount_ml}ml",
        record_id=record.id,
    )


def _handle_bowel(db: Session, user_id: int, today: date, current_time: time, now_utc: datetime):
    """大便计时：第一次碰触开始，第二次碰触结束"""
    start = _bowel_timers.get(user_id)

    if start is None:
        # 开始计时
        _bowel_timers[user_id] = now_utc
        logger.info(f"NFC 大便计时开始: user={user_id}")
        return NfcTapResponse(
            status="timer_started",
            message=f"开始计时 {current_time.strftime('%H:%M')}",
        )
    else:
        # 结束计时
        elapsed_seconds = (now_utc - start).total_seconds()
        duration_minutes = max(1, round(elapsed_seconds / 60))

        # 超过 60 分钟视为异常（忘记结束），按 0 分钟记录
        if duration_minutes > 60:
            logger.warning(f"NFC 大便计时超时 {duration_minutes}min，可能忘记结束")
            duration_minutes = 0

        del _bowel_timers[user_id]

        # 使用开始时间的日期和时间
        start_beijing = start.astimezone(BEIJING_TZ)

        record = ExcretionRecord(
            user_id=user_id,
            record_date=start_beijing.date(),
            record_time=start_beijing.time(),
            type="bowel",
            duration_minutes=duration_minutes,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        logger.info(f"NFC 大便记录: user={user_id}, {duration_minutes}分钟")
        return NfcTapResponse(
            status="timer_stopped",
            message=f"已记录大便 {duration_minutes}分钟",
            record_id=record.id,
            duration_minutes=duration_minutes,
        )


def _record_urine(db: Session, user_id: int, today: date, current_time: time):
    """记录小便"""
    record = ExcretionRecord(
        user_id=user_id,
        record_date=today,
        record_time=current_time,
        type="urine",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info(f"NFC 小便记录: user={user_id}")
    return NfcTapResponse(
        status="recorded",
        message=f"已记录小便 {current_time.strftime('%H:%M')}",
        record_id=record.id,
    )
