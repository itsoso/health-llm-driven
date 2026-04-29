"""
Open-Loop Manager — 主动循环管理 (vertical health agent 的灵魂).

每天 7:00 (北京) 跑一次, 扫所有用户的 "开放健康循环",
按严重度+到期度评分, 给每个用户最多推 2 条 APNs.

什么是"开放循环":
  - 过期 lab 复查      ("LDL 6 个月前 4.1, 建议 4 周内复查")
  - 到期 ActionCard    (信任循环卡片到期 — 已由 outcome_grader 评分)
  - Plan item 偏离    (连续 3 天没运动 / 没吃药)
  - 异常趋势刚出现     (HRV 连降 5 天 / 体重连升 3 周)
  - Garmin sync 中断   (3+ 天没数据)

设计原则:
  1. 每个 Loop 给一个 score 0-100 (严重度 + 到期度), 排序后取 top N
  2. 全局 N = 2/天/用户 (避免推送疲劳, 这个值是产品决策, 不是技术)
  3. 用户可对每条推送反馈: '不感兴趣' / '暂停 7 天' / '已处理' (后续接通)
  4. 旁路 fail-soft: 单 user 失败不影响其他

输出: APNs 推送 (复用现有 notification_service)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, date
from typing import List, Optional

from app.celery_app import celery_app
from app.database import SessionLocal
from app.utils.timezone import CHINA_TIMEZONE

logger = logging.getLogger(__name__)


# ────────────────────── 数据结构 ──────────────────────


@dataclass
class OpenLoop:
    """一个待跟进的开放循环."""
    user_id: int
    kind: str            # 'lab_overdue' / 'action_card_due' / 'plan_drift' / 'trend_anomaly' / 'sync_stale'
    title: str           # 给用户看的标题 (≤ 30字)
    body: str            # APNs 推送正文 (≤ 100字)
    score: int           # 0-100, 严重度 + 到期度
    deeplink: Optional[str] = None    # 点击推送跳哪
    # signal_key: 同 (user_id, kind, signal_key) 在去重窗口内不重复推
    # 例: kind=lab_overdue -> signal_key='LDL', kind=action_card_due -> signal_key='card_id=123'
    signal_key: str = ""
    metadata: dict = field(default_factory=dict)


# ────────────────────── 各类 loop 检测 ──────────────────────


def _detect_lab_overdue(db, user_id: int) -> List[OpenLoop]:
    """LDL/HbA1c/ALT 等关键化验 6+ 月没复查."""
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    LAB_RECHECK_INTERVALS = {
        # item_code/name 关键字 → 推荐复查间隔 (天) + 严重度因子
        "LDL": (180, 60),
        "HBA1C": (90, 80),
        "ALT": (180, 50),
        "AST": (180, 50),
        "GGT": (180, 50),
        "TG": (180, 40),
        "CREATININE": (180, 70),
        "URIC_ACID": (180, 50),
    }

    loops: List[OpenLoop] = []
    today = datetime.now(CHINA_TIMEZONE).date()

    for code_key, (interval_days, severity) in LAB_RECHECK_INTERVALS.items():
        # 找该用户最近一次该化验
        latest = db.query(MedicalExamItem.value, MedicalExam.exam_date).join(MedicalExam).filter(
            MedicalExam.user_id == user_id,
            (MedicalExamItem.item_code.ilike(f"%{code_key}%") |
             MedicalExamItem.item_name.ilike(f"%{code_key}%")),
            MedicalExamItem.value.isnot(None),
        ).order_by(MedicalExam.exam_date.desc()).first()

        if not latest:
            continue  # 没记录, 不主动催检

        value, last_date = latest
        days_since = (today - last_date).days
        overdue_days = days_since - interval_days
        if overdue_days <= 0:
            continue  # 还没到期

        # score = severity * (1 + overdue_days/interval, capped 2x)
        ratio = min(2.0, 1.0 + overdue_days / interval_days)
        score = int(severity * ratio)
        loops.append(OpenLoop(
            user_id=user_id,
            kind="lab_overdue",
            title=f"该复查 {code_key} 了",
            body=f"上次 {code_key} 是 {days_since} 天前 ({value}), "
                 f"超过推荐间隔 {overdue_days} 天",
            score=score,
            deeplink="health://medical-exams/upload",
            signal_key=code_key,
            metadata={"code": code_key, "last_value": value, "last_date": str(last_date),
                      "overdue_days": overdue_days},
        ))

    return loops


def _detect_action_card_due(db, user_id: int) -> List[OpenLoop]:
    """到期未评分的 ActionCard (outcome_grader 应该评了, 但用户也该看到结果)."""
    from app.models.action_card import ActionCard

    today_dt = datetime.now(timezone.utc)
    cards = db.query(ActionCard).filter(
        ActionCard.user_id == user_id,
        ActionCard.check_back_date.isnot(None),
        ActionCard.check_back_date <= today_dt,
        ActionCard.graded_at.isnot(None),
        ActionCard.graded_at >= today_dt - timedelta(days=2),  # 最近 2 天才评分的
    ).all()

    loops: List[OpenLoop] = []
    for c in cards:
        score_label = "命中 ✅" if (c.accuracy_score or 0) >= 70 else (
            "部分 ⚠️" if (c.accuracy_score or 0) >= 40 else "未达 ❌"
        )
        loops.append(OpenLoop(
            user_id=user_id,
            kind="action_card_due",
            title=f"{c.title[:18]}…评分出来了",
            body=f"{score_label} {c.accuracy_score}/100 — {c.grading_notes or '点开看详情'}",
            score=70 if (c.accuracy_score or 0) >= 70 else 60,
            deeplink=f"health://action-cards/{c.id}",
            signal_key=f"card_id={c.id}",
            metadata={"card_id": c.id, "score": c.accuracy_score},
        ))

    return loops


def _detect_sync_stale(db, user_id: int) -> List[OpenLoop]:
    """Garmin 3+ 天没数据."""
    from app.models.daily_health import GarminData

    today = datetime.now(CHINA_TIMEZONE).date()
    last_record = db.query(GarminData.record_date).filter(
        GarminData.user_id == user_id,
    ).order_by(GarminData.record_date.desc()).first()

    if not last_record:
        return []  # 用户从来没接 Garmin, 不催

    days_since = (today - last_record[0]).days
    if days_since < 3:
        return []

    return [OpenLoop(
        user_id=user_id,
        kind="sync_stale",
        title="Garmin 同步可能中断",
        body=f"已 {days_since} 天没收到 Garmin 数据. 检查手表蓝牙 / 重新登录 Garmin Connect.",
        score=min(80, 30 + days_since * 5),
        deeplink="health://settings/garmin",
        signal_key="garmin",
        metadata={"days_since": days_since, "last_record": str(last_record[0])},
    )]


def _detect_trend_anomaly(db, user_id: int) -> List[OpenLoop]:
    """HRV 连降 5 天 / 体重连升 3 周."""
    from app.models.daily_health import GarminData

    loops: List[OpenLoop] = []
    today = datetime.now(CHINA_TIMEZONE).date()
    week_ago = today - timedelta(days=7)

    # HRV 趋势: 最近 7 天平均 vs 之前 7 天平均, 跌幅 > 15% 报
    recent = db.query(GarminData.hrv).filter(
        GarminData.user_id == user_id,
        GarminData.record_date >= week_ago,
        GarminData.hrv.isnot(None),
    ).all()
    prev = db.query(GarminData.hrv).filter(
        GarminData.user_id == user_id,
        GarminData.record_date >= week_ago - timedelta(days=7),
        GarminData.record_date < week_ago,
        GarminData.hrv.isnot(None),
    ).all()
    if len(recent) >= 4 and len(prev) >= 4:
        ra = sum(r[0] for r in recent) / len(recent)
        pa = sum(r[0] for r in prev) / len(prev)
        if pa > 0 and (pa - ra) / pa > 0.15:
            loops.append(OpenLoop(
                user_id=user_id,
                kind="trend_anomaly",
                title="HRV 最近一周下滑",
                body=f"7 天均值 {ra:.0f}ms (前 7 天 {pa:.0f}ms, 下降 {(pa-ra)/pa*100:.0f}%). "
                     f"压力/睡眠/训练负荷需关注.",
                score=int(60 + min(30, (pa - ra) / pa * 100)),
                deeplink="health://digital-twin",
                signal_key="hrv_drop",
                metadata={"recent_hrv": round(ra, 1), "prev_hrv": round(pa, 1)},
            ))

    return loops


def _detect_plan_deviation(db, user_id: int) -> List[OpenLoop]:
    """exercise / medicine 类日打卡连续 3+ 天未完成 → 断点提示.

    数据源: CheckinTemplate.last_checkin_date (update_completion_rate 后冗余更新).
    只抓 frequency=daily + is_active + 非 archived 的 exercise/medicine 模板.
    last_checkin_date=None 视为冷启动, 不报 (不骚扰新用户).
    """
    from app.models.checkin import CheckinTemplate

    THRESHOLD_DAYS = 3
    today = datetime.now(CHINA_TIMEZONE).date()

    templates = db.query(CheckinTemplate).filter(
        CheckinTemplate.user_id == user_id,
        CheckinTemplate.is_active == True,   # noqa: E712
        CheckinTemplate.is_archived == False,  # noqa: E712
        CheckinTemplate.category.in_(["exercise", "medicine"]),
        CheckinTemplate.frequency == "daily",
    ).all()

    loops: List[OpenLoop] = []
    for t in templates:
        # 冷启动 (从未打卡) 不报; 该催的是 "打过但断了"
        if t.last_checkin_date is None:
            continue
        days_since = (today - t.last_checkin_date).days
        if days_since < THRESHOLD_DAYS:
            continue

        # medicine 严重度高于 exercise (忘药比漏运动后果更重)
        severity_base = 70 if t.category == "medicine" else 45
        score = min(95, severity_base + (days_since - THRESHOLD_DAYS) * 5)

        cat_label = "用药" if t.category == "medicine" else "运动"
        icon = t.icon or ("💊" if t.category == "medicine" else "🏃")
        loops.append(OpenLoop(
            user_id=user_id,
            kind="plan_drift",
            title=f"{icon} {t.name} 断了 {days_since} 天",
            body=f"{cat_label}「{t.name}」连续 {days_since} 天未完成. 重建节奏从今天开始.",
            score=score,
            deeplink=f"health://checkin/{t.id}",
            signal_key=f"template_id={t.id}",
            metadata={
                "template_id": t.id,
                "template_name": t.name,
                "category": t.category,
                "days_since": days_since,
                "last_date": str(t.last_checkin_date),
            },
        ))

    return loops


# ────────────────────── 主入口 ──────────────────────


def collect_open_loops(db, user_id: int) -> List[OpenLoop]:
    """汇总该用户所有开放循环, 按 score 倒序."""
    loops: List[OpenLoop] = []
    for detector in (
        _detect_lab_overdue,
        _detect_action_card_due,
        _detect_sync_stale,
        _detect_trend_anomaly,
        _detect_plan_deviation,
    ):
        try:
            loops.extend(detector(db, user_id) or [])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[open_loop] {detector.__name__} user={user_id} 失败 (跳过): {e}")
    loops.sort(key=lambda x: x.score, reverse=True)
    return loops


DEDUP_WINDOW_DAYS = 7  # 同一 (user, kind, signal_key) 在 7 天内不重复推


def _is_recently_pushed_or_snoozed(db, user_id: int, loop: OpenLoop) -> bool:
    """该信号在 dedup 窗口内已推过 OR 用户主动 snooze 了 → 跳过."""
    from app.models.open_loop_history import OpenLoopHistory

    cutoff = datetime.now(timezone.utc) - timedelta(days=DEDUP_WINDOW_DAYS)
    now_utc = datetime.now(timezone.utc)

    # 1) 在 snooze 窗口内 → 不推
    snoozed = db.query(OpenLoopHistory.id).filter(
        OpenLoopHistory.user_id == user_id,
        OpenLoopHistory.kind == loop.kind,
        OpenLoopHistory.signal_key == (loop.signal_key or ""),
        OpenLoopHistory.snoozed_until.isnot(None),
        OpenLoopHistory.snoozed_until > now_utc,
    ).first()
    if snoozed:
        return True

    # 2) 7 天内已推同 (kind, signal_key) → 不重发
    recent = db.query(OpenLoopHistory.id).filter(
        OpenLoopHistory.user_id == user_id,
        OpenLoopHistory.kind == loop.kind,
        OpenLoopHistory.signal_key == (loop.signal_key or ""),
        OpenLoopHistory.sent_at >= cutoff,
        OpenLoopHistory.delivery_ok == 1,
    ).first()
    return bool(recent)


def _record_history(db, user_id: int, loop: OpenLoop, ok: bool, error: str = "") -> None:
    """写入 open_loop_history (去重 + 后续 feedback 关联)."""
    from app.models.open_loop_history import OpenLoopHistory

    try:
        row = OpenLoopHistory(
            user_id=user_id,
            kind=loop.kind,
            signal_key=loop.signal_key or "",
            score=loop.score,
            title=loop.title,
            body=loop.body,
            deeplink=loop.deeplink,
            delivery_ok=1 if ok else 0,
            delivery_error=error or None,
        )
        db.add(row)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[open_loop] 写 history 失败 (旁路): {e}")


def _create_history_pending(db, user_id: int, loop: OpenLoop):
    """预写一条 delivery_ok=0 的 history, 返回 row (含 id). mobile 回调要这个 id."""
    from app.models.open_loop_history import OpenLoopHistory

    row = OpenLoopHistory(
        user_id=user_id,
        kind=loop.kind,
        signal_key=loop.signal_key or "",
        score=loop.score,
        title=loop.title,
        body=loop.body,
        deeplink=loop.deeplink,
        delivery_ok=0,  # pending, 推送完后更新
        delivery_error=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _finalize_history(db, history_id: int, ok: bool, error: str = "") -> None:
    """推送完成后更新 delivery_ok / delivery_error."""
    from app.models.open_loop_history import OpenLoopHistory

    try:
        row = db.query(OpenLoopHistory).filter(OpenLoopHistory.id == history_id).first()
        if row:
            row.delivery_ok = 1 if ok else 0
            row.delivery_error = error or None
            db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[open_loop] finalize history id={history_id} 失败 (旁路): {e}")


def _push_loop(db, user_id: int, loop: OpenLoop) -> bool:
    """通过 ios_push.send_push 发 APNs + 写 history. 含 dedup.

    流程: 先写 history (delivery_ok=0, 拿 id) → 把 history_id 塞进 APNs data →
    push → 用 id 回填 delivery_ok. 这样 mobile 点按钮回调时能带上
    history_id 直接打 POST /open-loop/{id}/feedback.
    """
    # dedup
    if _is_recently_pushed_or_snoozed(db, user_id, loop):
        logger.info(
            f"[open_loop] dedup skip user={user_id} kind={loop.kind} "
            f"signal_key={loop.signal_key} (7d 内已推 or snoozed)"
        )
        return False

    try:
        from app.models.notification import UserNotificationSetting
        from app.services.notification.ios_push import IOSPushService
        import asyncio

        setting = db.query(UserNotificationSetting).filter(
            UserNotificationSetting.user_id == user_id,
        ).first()
        if not setting:
            return False
        if not (setting.enabled and setting.ios_push_enabled and setting.ios_device_token):
            return False
        if not setting.health_alert_enabled:
            return False

        # 1) 预写 history (delivery_ok=0), 拿 id 给 APNs data
        try:
            history_row = _create_history_pending(db, user_id, loop)
            history_id = history_row.id
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[open_loop] 预写 history 失败, 降级无 id 推送: {e}")
            history_id = None

        service = IOSPushService()
        result = asyncio.run(service.send_push(
            device_token=setting.ios_device_token,
            title=loop.title,
            body=loop.body,
            category="OPEN_LOOP",  # iOS 上对应 actions: 已处理 / 暂停7天 / 不感兴趣
            data={
                "type": "open_loop",
                "history_id": str(history_id) if history_id else "",
                "kind": loop.kind,
                "signal_key": loop.signal_key or "",
                "deeplink": loop.deeplink or "",
                **{k: str(v) for k, v in loop.metadata.items()},
            },
        ))
        ok = bool(result and result.get("success"))
        err = "" if ok else (result or {}).get("error", "unknown")

        # 2) 回填 delivery_ok
        if history_id is not None:
            _finalize_history(db, history_id, ok=ok, error=err)
        else:
            # 降级路径: 没拿到 id, 走老 _record_history
            _record_history(db, user_id, loop, ok=ok, error=err)

        return ok
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[open_loop] APNs 推送失败 user={user_id}: {e}")
        _record_history(db, user_id, loop, ok=False, error=str(e))
        return False


@celery_app.task(time_limit=600, name="app.tasks.open_loop_manager.run_open_loop_check")
def run_open_loop_check(max_per_user: int = 2):
    """
    每天 7:00 (北京) 扫所有 active 用户的开放循环, 推送 top N.

    返回 {users_scanned, total_loops, pushed}.
    """
    from app.models.user import User

    pushed_total = 0
    loops_total = 0
    users_scanned = 0

    with SessionLocal() as db:
        users = db.query(User).filter(User.is_active == True).all()  # noqa: E712
        for u in users:
            users_scanned += 1
            try:
                loops = collect_open_loops(db, u.id)
                loops_total += len(loops)
                # Top max_per_user, 但 score < 50 不推 (噪音过滤)
                for loop in loops[:max_per_user]:
                    if loop.score < 50:
                        continue
                    if _push_loop(db, u.id, loop):
                        pushed_total += 1
                        logger.info(
                            f"[open_loop] pushed user={u.id} kind={loop.kind} "
                            f"score={loop.score} title={loop.title}"
                        )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[open_loop] user={u.id} 处理失败 (跳过): {e}")

    logger.info(
        f"[open_loop] 完成: users={users_scanned}, loops={loops_total}, pushed={pushed_total}"
    )
    return {"users_scanned": users_scanned, "total_loops": loops_total, "pushed": pushed_total}
