"""跑后 Garmin HR 回放任务 (Live Run Coach Phase 5 — R2/R3).

mobile 跑步时拿不到心率 (没接 BLE 心率带 / Apple Watch),
所以 R2/R3 这两条 HR-based 规则做不了实时. 跑完后 Garmin
同步会把活动落到 WorkoutRecord.heart_rate_data, 这个任务
回放 HR 时间序列, 把 R2/R3 事件补回到 LiveRunSession.events,
同时刷新 avg_hr / max_hr / z4_plus_minutes.

R2 (hr_zone_overload): 持续 5min+ 心率在 Z4+ (>=0.85 * max_hr)
R3 (total_load_exceeded): 本次 Z4+ 累计超过 session.max_z4_minutes

设计:
  - 旁路, 失败不影响 narrative
  - Garmin 同步可能延迟, 找不到匹配 activity 时最多重试 4 次,
    间隔 5min (5/10/15/20 → 总 50min 兜底)
  - 匹配规则: user_id + workout.start_time 在 session.started_at ±15min 内
    + workout_type 含 'run' / 'running' / 'jogging'
"""

import json
import logging
from datetime import date, datetime, timedelta, UTC
from typing import Optional, List, Dict

from celery.exceptions import Retry, MaxRetriesExceededError

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.live_run import LiveRunSession
from app.models.user import User
from app.models.daily_health import WorkoutRecord

logger = logging.getLogger(__name__)


# HR zone 阈值 (基于 max_hr 的百分比)
Z4_THRESHOLD = 0.85   # >=85% max_hr = Z4
SUSTAINED_Z4_SECONDS = 5 * 60   # R2: 5 分钟连续 Z4+


def _estimate_max_hr(user: User) -> int:
    """估算 max_hr: 220 - age, 缺数据用 185 兜底 (35 岁默认)."""
    if user.birth_date:
        age = (date.today() - user.birth_date).days // 365
        if 10 < age < 100:
            return 220 - age
    return 185


def _find_matching_workout(
    db, user_id: int, started_at: datetime, total_duration_s: int
) -> Optional[WorkoutRecord]:
    """匹配 Garmin 同步过来的 WorkoutRecord — user + 开始时间 ±15min + 跑步类型."""
    # 时间窗口
    lo = started_at - timedelta(minutes=15)
    hi = started_at + timedelta(minutes=15)

    candidates = (
        db.query(WorkoutRecord)
        .filter(WorkoutRecord.user_id == user_id)
        .filter(WorkoutRecord.start_time >= lo)
        .filter(WorkoutRecord.start_time <= hi)
        .all()
    )
    for w in candidates:
        wtype = (w.workout_type or "").lower()
        if "run" in wtype or "jog" in wtype:
            return w
    # 退化: 时间窗口内任意活动 (走路也行, 总比没数据好)
    return candidates[0] if candidates else None


def _parse_hr_series(workout: WorkoutRecord) -> List[Dict]:
    """heart_rate_data 是 JSON 字符串 [{time, hr}, ...]."""
    if not workout.heart_rate_data:
        return []
    try:
        data = json.loads(workout.heart_rate_data) if isinstance(workout.heart_rate_data, str) else workout.heart_rate_data
        if isinstance(data, list):
            return [p for p in data if isinstance(p, dict) and "hr" in p and "time" in p]
    except Exception as e:
        logger.warning(f"[hr-replay] parse heart_rate_data failed: {e}")
    return []


def _replay_rules(
    hr_series: List[Dict],
    started_at: datetime,
    max_hr: int,
    max_z4_minutes: Optional[int],
) -> tuple[list, dict]:
    """走一遍 HR 序列, 输出 (events, stats).

    stats 含: avg_hr / max_hr_observed / z4_plus_seconds.
    """
    if not hr_series:
        return [], {}

    z4_floor = int(max_hr * Z4_THRESHOLD)

    sorted_series = sorted(hr_series, key=lambda p: p["time"])
    events = []
    z4_run_start: Optional[int] = None
    z4_total_s = 0
    hr_sum = 0
    hr_count = 0
    hr_max = 0
    last_t: Optional[int] = None
    r2_emitted_at: set = set()  # 防同一段内多次触发, 用 (start_t // 60) 去重
    r3_emitted = False

    for p in sorted_series:
        t = int(p["time"])
        hr = int(p["hr"])
        if hr <= 0:
            continue
        # 区间长度: 上一点到当前点
        delta = (t - last_t) if last_t is not None else 0
        last_t = t

        hr_sum += hr
        hr_count += 1
        if hr > hr_max:
            hr_max = hr

        in_z4 = hr >= z4_floor
        if in_z4:
            if z4_run_start is None:
                z4_run_start = t
            z4_total_s += delta
            run_len = t - z4_run_start
            # R2: 持续 5min 触发一次
            if run_len >= SUSTAINED_Z4_SECONDS:
                bucket = z4_run_start // 60
                if bucket not in r2_emitted_at:
                    r2_emitted_at.add(bucket)
                    events.append({
                        "ts": (started_at + timedelta(seconds=t)).isoformat(),
                        "rule_id": "hr_zone_overload",
                        "message": f"心率 {hr} bpm 已在 Z4+ 持续 {run_len // 60} 分钟, 建议降速",
                        "metric_snapshot": {"hr": hr, "z4_floor": z4_floor, "duration_s": run_len},
                    })
        else:
            z4_run_start = None

        # R3: 累计 Z4+ 超过当日上限
        if (
            not r3_emitted
            and max_z4_minutes
            and z4_total_s >= max_z4_minutes * 60
        ):
            r3_emitted = True
            events.append({
                "ts": (started_at + timedelta(seconds=t)).isoformat(),
                "rule_id": "total_load_exceeded",
                "message": f"今日 Z4+ 累计已达 {z4_total_s // 60} 分钟, 超过上限 {max_z4_minutes}, 建议收尾",
                "metric_snapshot": {"z4_minutes": z4_total_s // 60, "max_z4_minutes": max_z4_minutes},
            })

    stats = {
        "avg_hr": int(hr_sum / hr_count) if hr_count else None,
        "max_hr": hr_max if hr_max else None,
        "z4_plus_minutes": round(z4_total_s / 60, 1) if z4_total_s else 0.0,
    }
    return events, stats


@celery_app.task(
    name="app.tasks.live_run_hr_replay.replay_hr_rules",
    bind=True,
    max_retries=4,
    default_retry_delay=300,  # 5 min
)
def replay_hr_rules(self, run_id: int) -> dict:
    """对一次跑步回放 R2/R3 + 刷新 HR 字段."""
    try:
        with SessionLocal() as db:
            s = db.query(LiveRunSession).filter(LiveRunSession.id == run_id).first()
            if s is None:
                return {"status": "skipped", "reason": "session_not_found"}
            if s.aborted or (s.total_duration_s or 0) < 60:
                return {"status": "skipped", "reason": "too_short_or_aborted"}

            user = db.query(User).filter(User.id == s.user_id).first()
            if user is None:
                return {"status": "skipped", "reason": "user_not_found"}

            workout = _find_matching_workout(db, s.user_id, s.started_at, s.total_duration_s or 0)
            if workout is None:
                # Garmin 还没同步过来 — 重试
                if self.request.retries < self.max_retries:
                    logger.info(
                        f"[hr-replay] run={run_id} no matching workout, retry "
                        f"{self.request.retries + 1}/{self.max_retries}"
                    )
                    raise self.retry()
                return {"status": "skipped", "reason": "no_workout_match"}

            hr_series = _parse_hr_series(workout)
            if not hr_series:
                return {"status": "skipped", "reason": "no_hr_series"}

            max_hr_est = _estimate_max_hr(user)
            new_events, stats = _replay_rules(
                hr_series, s.started_at, max_hr_est, s.max_z4_minutes
            )

            # 合并事件, R1 (pace_drift) 来自 mobile, R2/R3 来自这里, 不去重
            existing = list(s.events or [])
            existing.extend(new_events)
            existing.sort(key=lambda e: e.get("ts", ""))
            s.events = existing

            # 刷新 HR 字段 (mobile 没填的时候补上)
            if stats.get("avg_hr") and not s.avg_hr:
                s.avg_hr = stats["avg_hr"]
            if stats.get("max_hr") and (not s.max_hr or s.max_hr < stats["max_hr"]):
                s.max_hr = stats["max_hr"]
            if stats.get("z4_plus_minutes") is not None:
                s.z4_plus_minutes = stats["z4_plus_minutes"]

            db.commit()

            logger.info(
                f"[hr-replay] run={run_id} ok: +{len(new_events)} events, "
                f"avg_hr={stats.get('avg_hr')}, z4+={stats.get('z4_plus_minutes')}min"
            )
            return {
                "status": "completed",
                "events_added": len(new_events),
                "stats": stats,
            }
    except Retry:
        raise
    except MaxRetriesExceededError:
        return {"status": "failed", "reason": "max_retries"}
    except Exception as e:
        logger.exception(f"[hr-replay] run={run_id} failed: {e}")
        return {"status": "failed", "reason": str(e)}
