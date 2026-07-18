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
from datetime import datetime, timedelta, timezone
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
        # P2 故事化: title 用情感词, body 二段式 "为什么 + 做什么"
        # 避免"该复查了" 命令式, 用"现在可能..." 提示式
        body = (
            f"{days_since} 天前是 {value}，已经超过推荐复查间隔 {overdue_days} 天。"
            f"这周抽时间去测一下，看看变化。"
        )
        loops.append(OpenLoop(
            user_id=user_id,
            kind="lab_overdue",
            title=f"{code_key} 是时候复查了",
            body=body,
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

    from app.services.outcome_safety import is_efficacy_score_eligible_card

    loops: List[OpenLoop] = []
    for c in cards:
        # 临床管理混杂指标只能保留测量供专业人员解读，不能推送为 AI 成功/失败，
        # 也不能把未评分的 None 默认成 0 分。
        if c.accuracy_score is None or not is_efficacy_score_eligible_card(c):
            continue
        score_val = c.accuracy_score
        title_short = c.title[:24] if c.title else "之前那条建议"
        # P2 故事化: 按命中度给不同语气, 让用户感受 AI 在"复盘" 而非"通报"
        if score_val >= 70:
            title = f"✅ {title_short} 命中了"
            body = (
                f"那条建议 {score_val}/100，方向是对的 — "
                f"这种节奏能维持就保持。"
            )
        elif score_val >= 40:
            title = f"⚠️ {title_short} 部分达标"
            body = (
                f"打了 {score_val}/100，比 baseline 好但没到位 — "
                f"看看哪里可以再调一调。"
            )
        else:
            title = f"❌ {title_short} 这次没做到"
            body = (
                f"只有 {score_val}/100。先别急着自责，看看是建议不合适还是执行卡住了 — "
                f"AI 也会从这次学到。"
            )
        loops.append(OpenLoop(
            user_id=user_id,
            kind="action_card_due",
            title=title,
            body=body,
            score=70 if score_val >= 70 else 60,
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

    # P2 故事化: 不命令式催办, 说清楚"为什么这事重要" 让用户主动修
    return [OpenLoop(
        user_id=user_id,
        kind="sync_stale",
        title="Garmin 这几天没数据",
        body=(
            f"{days_since} 天没收到，AI 给不出准的判断。"
            f"打开 Garmin Connect 检查手表蓝牙，重新登录一次。"
        ),
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
            pct = (pa - ra) / pa * 100
            # P2 故事化: 给"为什么紧要" + 一条具体行动 (不是含糊"需关注")
            loops.append(OpenLoop(
                user_id=user_id,
                kind="trend_anomaly",
                title="HRV 这周明显往下掉",
                body=(
                    f"7 天均值 {ra:.0f}ms，比上周 {pa:.0f}ms 跌 {pct:.0f}%。"
                    f"今晚早睡 1 小时，明天训练强度调低 20% 试试。"
                ),
                score=int(60 + min(30, pct)),
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

        icon = t.icon or ("💊" if t.category == "medicine" else "🏃")
        # P2 故事化: 不"重建节奏从今天开始" 那种命令式, 改"今天 X 分钟也算"减负担
        if t.category == "medicine":
            # §5 推送隐私:用药打卡模板名往往就是药名,不进锁屏 title;
            # 名称走 metadata.template_name,App 解锁后应用内渲染。
            title = f"💊 用药打卡漏了 {days_since} 天"
            body = (
                f"已经 {days_since} 天没记打卡。漏一次用药对慢病管理影响最大 — "
                f"今天补一次，往后我们一起跟。"
            )
        else:  # exercise
            title = f"{icon} {t.name} 停了 {days_since} 天"
            body = (
                f"{days_since} 天没记。断点不可怕，今天补 5 分钟也算 — "
                f"先把节奏接回来。"
            )
        loops.append(OpenLoop(
            user_id=user_id,
            kind="plan_drift",
            title=title,
            body=body,
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


# 这些 critical salience key 当前没有任何 push 路径覆盖(SafetyGuardian 规则不含 readiness/
# 恢复状态;notifications 只用 readiness 做"抑制运动催促"的门控,不推送)。所以可安全转成
# proactive push,不会和安全告警重复。ACWR / BP / AQI 故意排除 —— 已被 SafetyGuardian
# (training_load / vitals)或环境告警覆盖,再推会双发。
_PUSH_SAFE_SALIENCE_KEYS = {
    "readiness": ("health://digital-twin", "今日恢复"),
    "acute_illness": ("health://digital-twin", "今日休息"),
}


def _detect_salient_state(db, user_id: int) -> List[OpenLoop]:
    """急性恢复状态 critical(恢复评分骤降 / 急性病症)→ 主动推送。

    复用 conversation_starters 的 salience 引擎(与 chips 同源,统一"此刻什么最重要"
    的判断),只取当前 push 链路尚未覆盖的 critical 信号,避免和 SafetyGuardian 重复。
    """
    from app.services.conversation_starters import compute_salient_signals

    loops: List[OpenLoop] = []
    for cand in compute_salient_signals(db, user_id, limit=8):
        if cand.priority < 100:  # 仅 critical
            continue
        mapped = _PUSH_SAFE_SALIENCE_KEYS.get(cand.key)
        if not mapped:
            continue
        deeplink, label = mapped
        loops.append(OpenLoop(
            user_id=user_id,
            kind="salient_state",
            title=f"{label}需要关注",
            body=cand.text[:100],
            score=min(cand.priority, 100),
            deeplink=deeplink,
            signal_key=cand.key,  # 同 key 7 天内不重复推
            metadata={"salience_key": cand.key, "priority": cand.priority},
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
        _detect_salient_state,
    ):
        try:
            loops.extend(detector(db, user_id) or [])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[open_loop] {detector.__name__} user={user_id} 失败 (跳过): {e}")
    loops.sort(key=lambda x: x.score, reverse=True)
    return loops


DEDUP_WINDOW_DAYS = 7  # 同一 (user, kind, signal_key) 在 7 天内不重复推
MORNING_SLEEP_FLOOR = "09:00"


def _is_in_quiet_hours_now(setting) -> bool:
    """检查当前北京时间是否在该用户的 quiet_hours 窗口内.

    和 push_service.PushService.is_quiet_hours 同语义, 但不依赖 PushService 初始化
    (open_loop 的 push 链路一直走 ios_push 直连, 不经 push_service).

    跨午夜情况: start > end 时 (如 22:00 - 09:00), 当前时间 >= start 或 < end 都算静默.
    """
    start = (setting.quiet_hours_start or "22:00").strip()
    end = (setting.quiet_hours_end or "09:00").strip()
    now_cn = datetime.now(CHINA_TIMEZONE).strftime("%H:%M")
    if now_cn < MORNING_SLEEP_FLOOR:
        return True
    if start > end:  # 跨午夜: 22:00 ~ 09:00
        return now_cn >= start or now_cn < end
    return start <= now_cn < end


def _lockscreen_safe_copy(loop: OpenLoop) -> tuple[str, str]:
    """Return category-level copy for APNs/Telegram visible surfaces.

    Detailed loop content remains in the protected app data/deep link and in
    the authenticated in-app history.  Medication, lab, diagnosis and metric
    details must never be placed in a lock-screen notification.
    """
    copy_by_kind = {
        "lab_overdue": ("化验指标提醒", "有一项健康复查需要关注，打开 App 查看详情。"),
        "plan_drift": ("健康计划提醒", "有一项健康计划需要关注，打开 App 查看详情。"),
        "action_card_due": ("行动复盘提醒", "有一项行动需要复盘，打开 App 查看详情。"),
        "trend_anomaly": ("健康趋势提醒", "有一项健康趋势需要关注，打开 App 查看详情。"),
        "sync_stale": ("数据同步提醒", "健康设备数据暂未更新，打开 App 查看详情。"),
        "salient_state": ("健康状态提醒", "有一项健康状态需要关注，打开 App 查看详情。"),
    }
    return copy_by_kind.get(loop.kind, ("健康提醒", "有一项健康提醒需要关注，打开 App 查看详情。"))


def _maybe_apply_snooze_renewal_prefix(db, user_id: int, loop: OpenLoop) -> None:
    """
    P8: 检测该 (kind, signal_key) 是否有 snoozed_until 在最近 24h 内过期的记录.
    如有, 在 loop.body 前加"我们说先暂停的, 现在到期了 — " 让推送有续约感,
    而不是再次"通知"用户.

    Mutates loop.body in-place. 失败 silent (推送照常发).
    """
    try:
        from app.models.open_loop_history import OpenLoopHistory

        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(hours=24)
        # 找有 snoozed_until 在过去 24h 内 (即"刚过期") 的同 signal 记录
        recent_expired = db.query(OpenLoopHistory.id).filter(
            OpenLoopHistory.user_id == user_id,
            OpenLoopHistory.kind == loop.kind,
            OpenLoopHistory.signal_key == (loop.signal_key or ""),
            OpenLoopHistory.snoozed_until.isnot(None),
            OpenLoopHistory.snoozed_until >= cutoff,
            OpenLoopHistory.snoozed_until <= now_utc,
        ).first()
        if recent_expired:
            loop.body = f"上次你说先暂停, 现在到期了 — {loop.body}"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[open_loop] snooze renewal prefix check failed (silent): {e}")


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
    """通过统一 PushService 发送 + 写 open-loop history. 含 dedup + fallback.

    流程: 先写 history (delivery_ok=0, 拿 id) → 把 history_id 塞进 APNs data →
    push → 用 id 回填 delivery_ok. 这样 mobile 点按钮回调时能带上
    history_id 直接打 POST /open-loop/{id}/feedback.

    PushService 负责静默时段、09:00 睡眠地板、用户开关、gatekeeper、渠道日志
    和失败回执；open-loop 只保留业务去重和自己的反馈历史。
    """
    # dedup
    if _is_recently_pushed_or_snoozed(db, user_id, loop):
        logger.info(
            f"[open_loop] dedup skip user={user_id} kind={loop.kind} "
            f"signal_key={loop.signal_key} (7d 内已推 or snoozed)"
        )
        return False

    # P8 (2026-05-04): snooze 到期续约 — 检测该 (kind, signal_key) 是否有
    # snoozed_until 刚在最近 24h 内过期的记录. 如有, body 前加续约前缀,
    # 让用户感受到"我们说先暂停的 X 现在到期了" 而不是普通推送.
    _maybe_apply_snooze_renewal_prefix(db, user_id, loop)

    history_id = None
    try:
        from app.models.notification import UserNotificationSetting
        from app.services.notification.push_service import PushService
        import asyncio

        setting = db.query(UserNotificationSetting).filter(
            UserNotificationSetting.user_id == user_id,
        ).first()
        if not setting:
            return False
        if not setting.enabled:
            return False
        if not setting.health_alert_enabled:
            return False

        # Defense-in-depth: quiet hours 守门 — cron 已移到 09:15 避开默认 22:00-09:00,
        # 但用户若把 quiet_hours 往后调 (例如 10:00) 或把结束设得更晚, 仍要尊重.
        # 严格不打扰睡眠: Open-Loop 直连 APNs 不允许按 score 穿透 quiet-hours,
        # 避免绕过 PushService 的统一静默策略。下次 cron 会重试, 不触发 dedup.
        if _is_in_quiet_hours_now(setting):
            logger.info(
                f"[open_loop] user={user_id} 在 quiet_hours 窗口内, score={loop.score}, "
                f"跳过 (不触 dedup, 下次 cron 会重试)"
            )
            return False

        # 1) 预写 history (delivery_ok=0), 拿 id 给 APNs data
        try:
            history_row = _create_history_pending(db, user_id, loop)
            history_id = history_row.id
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[open_loop] 预写 history 失败, 降级无 id 推送: {e}")
            history_id = None

        safe_title, safe_body = _lockscreen_safe_copy(loop)
        result = asyncio.run(PushService(db).send_notification(
            user_id=user_id,
            notification_type="open_loop",
            title=safe_title,
            content=safe_body,
            severity="warning",
            respect_quiet_hours=True,
            quiet_hours_policy="drop",
            dedup_window_hours=168,
            data={
                "type": "open_loop",
                "history_id": str(history_id) if history_id else "",
                "kind": loop.kind,
                "signal_key": loop.signal_key or "",
                # NOTE: key 必须是 deep_link (下划线), 与 mobile useNotifications.ts 对齐。
                "deep_link": loop.deeplink or "",
                # 详细内容只放受保护 data，解锁后由 App 结合 history_id 回取。
                "metadata": {k: str(v) for k, v in loop.metadata.items()},
            },
            log_delivery=True,
        ))
        ok = bool(result and result.get("success"))
        err = "" if ok else str((result or {}).get("reason") or (result or {}).get("error") or "unknown")
        channel_used = "push_service" if ok else None

        # 4) 回填 delivery_ok
        if history_id is not None:
            _finalize_history(db, history_id, ok=ok, error=err)
        else:
            _record_history(db, user_id, loop, ok=ok, error=err)

        if ok:
            logger.info(f"[open_loop] pushed user={user_id} kind={loop.kind} via {channel_used or 'none'}")
        return ok
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[open_loop] 推送异常 user={user_id}: {e}")
        if history_id is not None:
            _finalize_history(db, history_id, ok=False, error=str(e))
        else:
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
