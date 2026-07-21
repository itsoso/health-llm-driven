"""NFC 碰触快速记录 API

支持 iOS 快捷指令通过 NFC 自动化触发，实现：
- 饮水记录（碰一下 = 250ml）
- 大便计时（碰一下开始，再碰一下结束）
- 小便记录（碰一下即记录）
- 补剂打卡（碰一下 = 打卡指定补剂）
- 补剂分组打卡（碰一下 = 打卡该时段所有补剂）
"""
import logging
from datetime import date, datetime, time, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.bowel_timer import BowelTimer
from app.models.user import User
from app.models.excretion import ExcretionRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfc", tags=["nfc"])

BEIJING_TZ = timezone(timedelta(hours=8))

# 防抖：(user_id, action) -> last_tap_utc
_last_tap: dict[tuple[int, str], datetime] = {}
_DEDUP_SECONDS = 8  # 同一动作 8 秒内去重


# ── Schemas ───────────────────────────────────────────────

class NfcTapRequest(BaseModel):
    """NFC 碰触请求"""
    action: str = Field(..., pattern="^(water|bowel|urine|supplement|supplement_group)$")
    amount_ml: Optional[int] = Field(250, ge=50, le=2000)  # 仅 water 使用
    drink_type: Optional[str] = "水"  # 仅 water 使用
    supplement_id: Optional[int] = None  # supplement action 用
    timing: Optional[str] = None  # supplement_group action 用（morning/noon/evening/bedtime）
    on_behalf_of: Optional[int] = None  # 代记：目标用户 ID（需管理员权限）


class NfcTapResponse(BaseModel):
    """NFC 碰触响应"""
    status: str  # recorded / timer_started / timer_stopped / timer_expired / debounced
    message: str  # 人类可读的结果
    record_id: Optional[int] = None
    duration_minutes: Optional[int] = None  # 大便时长（仅 bowel stop）


# ── 端点 ──────────────────────────────────────────────────

@router.post("/tap", response_model=NfcTapResponse)
def nfc_tap(
    req: NfcTapRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """NFC 碰触记录

    - water: 直接记录饮水（默认 250ml）
    - bowel: 第一次碰触开始计时，第二次碰触结束并记录
    - urine: 直接记录小便
    - on_behalf_of: 代记其他用户（需管理员权限）
    """
    # 确定目标用户
    target_user_id = current_user.id
    behalf_label = ""
    if req.on_behalf_of and req.on_behalf_of != current_user.id:
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="仅管理员可代记其他用户")
        target_user = db.query(User).filter(User.id == req.on_behalf_of).first()
        if not target_user:
            raise HTTPException(status_code=404, detail=f"用户 {req.on_behalf_of} 不存在")
        target_user_id = req.on_behalf_of
        behalf_label = f"（为{target_user.name or target_user.username}）"

    now_utc = datetime.now(timezone.utc)

    # 防抖：同一用户同一动作 8 秒内去重（bowel 除外，因为它是状态切换）
    if req.action != "bowel":
        if req.action == "supplement":
            dedup_key = (target_user_id, f"supplement_{req.supplement_id}")
        elif req.action == "supplement_group":
            dedup_key = (target_user_id, f"supplement_group_{req.timing}")
        else:
            dedup_key = (target_user_id, req.action)
        last = _last_tap.get(dedup_key)
        if last and (now_utc - last).total_seconds() < _DEDUP_SECONDS:
            return NfcTapResponse(
                status="debounced",
                message=f"重复碰触已忽略（{_DEDUP_SECONDS}秒内）",
            )
        _last_tap[dedup_key] = now_utc

    now_beijing = now_utc.astimezone(BEIJING_TZ)
    today = now_beijing.date()
    current_time = now_beijing.time()

    if req.action == "water":
        resp = _record_water(db, target_user_id, today, current_time, req.amount_ml or 250, req.drink_type or "水")
    elif req.action == "bowel":
        resp = _handle_bowel(db, target_user_id, today, current_time, now_utc)
    elif req.action == "urine":
        resp = _record_urine(db, target_user_id, today, current_time)
    elif req.action == "supplement":
        if not req.supplement_id:
            raise HTTPException(status_code=400, detail="supplement 动作需要提供 supplement_id")
        resp = _record_supplement(db, target_user_id, today, current_time, req.supplement_id)
    elif req.action == "supplement_group":
        if not req.timing:
            raise HTTPException(status_code=400, detail="supplement_group 动作需要提供 timing（morning/noon/evening/bedtime）")
        resp = _record_supplement_group(db, target_user_id, today, current_time, req.timing)
    else:
        raise HTTPException(status_code=400, detail=f"未知动作: {req.action}")

    if behalf_label:
        resp.message += behalf_label
    return resp


@router.get("/bowel-status")
def bowel_timer_status(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """查询当前大便计时状态"""
    timer = db.query(BowelTimer).filter(BowelTimer.user_id == current_user.id).first()
    if timer:
        start = timer.start_time
        # 兼容 SQLite（无时区）和 PostgreSQL（有时区）
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - start).total_seconds() / 60
        return {
            "timing": True,
            "started_at": start.astimezone(BEIJING_TZ).strftime("%H:%M:%S"),
            "elapsed_minutes": round(elapsed, 1),
        }
    return {"timing": False}


# ── 内部函数 ──────────────────────────────────────────────

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
    """大便计时：第一次碰触开始，第二次碰触结束（持久化到 DB）"""
    timer = db.query(BowelTimer).filter(BowelTimer.user_id == user_id).first()

    if timer is None:
        # 开始计时
        timer = BowelTimer(user_id=user_id, start_time=now_utc)
        db.add(timer)
        db.commit()
        logger.info(f"NFC 大便计时开始: user={user_id}")
        return NfcTapResponse(
            status="timer_started",
            message=f"开始计时 {current_time.strftime('%H:%M')}",
        )
    else:
        # 结束计时
        start = timer.start_time
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        elapsed_seconds = (now_utc - start).total_seconds()
        duration_minutes = max(1, round(elapsed_seconds / 60))

        # 删除计时器
        db.delete(timer)

        # 超过 60 分钟视为过期（忘记结束），丢弃记录
        if duration_minutes > 60:
            db.commit()
            logger.warning(f"NFC 大便计时过期 {duration_minutes}min，丢弃记录")
            return NfcTapResponse(
                status="timer_expired",
                message=f"计时已过期（{duration_minutes}分钟），记录已丢弃，请重新开始",
            )

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


def _record_supplement(db: Session, user_id: int, today: date, current_time: time, supplement_id: int):
    """打卡单个补剂"""
    from app.models.supplement import SupplementDefinition, SupplementRecord

    supp = db.query(SupplementDefinition).filter(
        SupplementDefinition.id == supplement_id,
        SupplementDefinition.user_id == user_id,
        SupplementDefinition.is_active == True,
    ).first()
    if not supp:
        raise HTTPException(status_code=404, detail=f"补剂 {supplement_id} 不存在或已停用")

    # Upsert: 同一天同一补剂只保留一条
    record = db.query(SupplementRecord).filter(
        SupplementRecord.supplement_id == supplement_id,
        SupplementRecord.record_date == today,
    ).first()
    if record:
        record.taken = True
        record.taken_time = current_time
    else:
        record = SupplementRecord(
            supplement_id=supplement_id,
            user_id=user_id,
            record_date=today,
            taken=True,
            taken_time=current_time,
        )
        db.add(record)
    db.commit()
    db.refresh(record)

    logger.info(f"NFC 补剂打卡: user={user_id}, {supp.name}")
    return NfcTapResponse(
        status="recorded",
        message=f"已打卡 {supp.name}（{supp.dosage or ''}）",
        record_id=record.id,
    )


def _record_supplement_group(db: Session, user_id: int, today: date, current_time: time, timing: str):
    """按时段分组打卡所有补剂"""
    from app.models.supplement import SupplementDefinition, SupplementRecord

    supps = db.query(SupplementDefinition).filter(
        SupplementDefinition.user_id == user_id,
        SupplementDefinition.timing == timing,
        SupplementDefinition.is_active == True,
    ).all()

    if not supps:
        return NfcTapResponse(
            status="recorded",
            message=f"{timing} 时段没有活跃补剂",
        )

    names = []
    for supp in supps:
        record = db.query(SupplementRecord).filter(
            SupplementRecord.supplement_id == supp.id,
            SupplementRecord.record_date == today,
        ).first()
        if record:
            record.taken = True
            record.taken_time = current_time
        else:
            record = SupplementRecord(
                supplement_id=supp.id,
                user_id=user_id,
                record_date=today,
                taken=True,
                taken_time=current_time,
            )
            db.add(record)
        names.append(supp.name)

    db.commit()
    logger.info(f"NFC 分组打卡: user={user_id}, timing={timing}, count={len(names)}")

    TIMING_LABEL = {"morning": "早上", "noon": "午间", "evening": "晚间", "bedtime": "睡前"}
    label = TIMING_LABEL.get(timing, timing)
    return NfcTapResponse(
        status="recorded",
        message=f"已打卡{label} {len(names)} 种补剂：{', '.join(names)}",
    )
