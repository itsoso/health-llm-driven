"""卧室环境快照服务 (设计文档 §9 BedroomEnvironmentService 地基).

职责: 写入 / 读取卧室环境快照, 计算 stale. 只产结构化数据.

隐私 (设计文档 §11): 居住状态和睡眠环境数据**不发给通用 LLM**. 本模块产出的
快照**绝不**被 `app/twin/formatter.py` 的 `twin_to_prompt_blob` 引用 ——
有隐私守门测试 (tests/test_bedroom_environment.py) 防止日后误接.

降级: DB 异常 → rollback + log, 读路径返回 None/[] 让调用方感知"无数据",
写路径向上抛 (摄入失败必须让客户端知道, 不假装成功).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.bedroom_environment import BedroomEnvironmentSnapshot

logger = logging.getLogger(__name__)

# 快照新鲜窗口: 超过这个时长 (分钟) 视为 stale —— 传感器掉线/HA 停拉时不假装数据新鲜.
STALE_AFTER_MINUTES = 15

# 数值字段 (摄入时统一 float 化, 坏值丢弃不崩).
_NUMERIC_FIELDS = (
    "co2_ppm",
    "pm25",
    "temperature_c",
    "humidity_percent",
    "tvoc",
    "illuminance_lux",
)
_BOOL_FIELDS = ("occupancy", "bed_presence")
_CONFIDENCE_LEVELS = {"high", "medium", "low"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_aware(dt: datetime) -> datetime:
    """naive datetime 视为 UTC, 保证 stale 比较两侧都 tz-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_stale(captured_at: Optional[datetime], now: Optional[datetime] = None) -> bool:
    if captured_at is None:
        return True
    now = now or _now()
    return (now - _coerce_aware(captured_at)) > timedelta(minutes=STALE_AFTER_MINUTES)


def _serialize(row: BedroomEnvironmentSnapshot, stale: Optional[bool] = None) -> Dict[str, Any]:
    captured = _coerce_aware(row.captured_at) if row.captured_at else None
    return {
        "id": row.id,
        "room_id": row.room_id,
        "captured_at": captured.isoformat() if captured else None,
        "co2_ppm": row.co2_ppm,
        "pm25": row.pm25,
        "temperature_c": row.temperature_c,
        "humidity_percent": row.humidity_percent,
        "tvoc": row.tvoc,
        "illuminance_lux": row.illuminance_lux,
        "occupancy": row.occupancy,
        "bed_presence": row.bed_presence,
        "sources": row.sources,
        "confidence": row.confidence,
        "stale": row.stale if stale is None else stale,
    }


def record_snapshot(
    db: Session, user_id: int, payload: Dict[str, Any]
) -> BedroomEnvironmentSnapshot:
    """写一条快照. captured_at 缺省取当前. 坏数值丢弃不崩, 摄入失败向上抛.

    向后兼容: 所有指标字段都可空, 客户端只推它有的传感器读数.
    """
    payload = payload or {}

    # captured_at: 缺省当前; 字符串容错解析, 解析失败回退当前.
    captured_at = payload.get("captured_at")
    if isinstance(captured_at, str):
        try:
            captured_at = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError:
            logger.warning(
                "[BedroomEnv] captured_at 无法解析, 回退当前: %r", captured_at
            )
            captured_at = None
    if not isinstance(captured_at, datetime):
        captured_at = _now()
    captured_at = _coerce_aware(captured_at)

    # 数值字段: float 化, 坏值丢弃 (不让一条脏数据炸整条).
    numeric: Dict[str, Optional[float]] = {}
    for key in _NUMERIC_FIELDS:
        raw = payload.get(key)
        if raw is None:
            numeric[key] = None
            continue
        try:
            numeric[key] = float(raw)
        except (TypeError, ValueError):
            logger.warning("[BedroomEnv] 丢弃坏数值 %s=%r", key, raw)
            numeric[key] = None

    bools: Dict[str, Optional[bool]] = {}
    for key in _BOOL_FIELDS:
        raw = payload.get(key)
        bools[key] = None if raw is None else bool(raw)

    confidence = payload.get("confidence") or "medium"
    if confidence not in _CONFIDENCE_LEVELS:
        logger.warning("[BedroomEnv] 未知 confidence=%r, 回退 medium", confidence)
        confidence = "medium"

    sources = payload.get("sources")
    if sources is not None and not isinstance(sources, dict):
        logger.warning("[BedroomEnv] sources 非 dict, 忽略: %r", sources)
        sources = None

    snapshot = BedroomEnvironmentSnapshot(
        user_id=user_id,
        room_id=payload.get("room_id") or "bedroom",
        captured_at=captured_at,
        sources=sources,
        confidence=confidence,
        stale=False,
        **numeric,
        **bools,
    )
    try:
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
    except Exception:
        db.rollback()
        logger.exception("[BedroomEnv] 写入快照失败 user=%s", user_id)
        raise
    return snapshot


def get_current(
    db: Session, user_id: int, room_id: str = "bedroom"
) -> Optional[Dict[str, Any]]:
    """最近一条快照 (含动态 stale 判定). 无数据或 DB 异常 → None."""
    try:
        row = (
            db.query(BedroomEnvironmentSnapshot)
            .filter(
                BedroomEnvironmentSnapshot.user_id == user_id,
                BedroomEnvironmentSnapshot.room_id == room_id,
            )
            .order_by(BedroomEnvironmentSnapshot.captured_at.desc())
            .first()
        )
    except Exception:
        db.rollback()
        logger.exception("[BedroomEnv] 读取 current 失败 user=%s", user_id)
        return None
    if row is None:
        return None
    return _serialize(row, stale=_is_stale(row.captured_at))


def get_history(
    db: Session, user_id: int, room_id: str = "bedroom", days: int = 7
) -> List[Dict[str, Any]]:
    """近 N 天历史, 时间倒序. DB 异常 → []."""
    days = max(1, int(days)) if days else 7
    since = _now() - timedelta(days=days)
    try:
        rows = (
            db.query(BedroomEnvironmentSnapshot)
            .filter(
                BedroomEnvironmentSnapshot.user_id == user_id,
                BedroomEnvironmentSnapshot.room_id == room_id,
                BedroomEnvironmentSnapshot.captured_at >= since,
            )
            .order_by(BedroomEnvironmentSnapshot.captured_at.desc())
            .all()
        )
    except Exception:
        db.rollback()
        logger.exception("[BedroomEnv] 读取 history 失败 user=%s", user_id)
        return []
    now = _now()
    return [_serialize(r, stale=_is_stale(r.captured_at, now)) for r in rows]
