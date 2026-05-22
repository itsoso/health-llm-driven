"""
Conversation opener — AI 主动续接上次话题, 替代 chat tab 的"白板状态".

WHY (P1 改进点, 2026-05-04 产品规划):
打开 chat 时, 用户当前体验是空白 input + 4 个泛泛建议 chip. 实际生产数据
显示用户每天发 22 条对话 (151/7d) — 对话是绝对主入口, 但 22 个 query 都是
独立的, 没有"上次说到 X, 今天 Y" 的延续感.

opener 把 ActionCard 检验日 / anomaly_alert / case_thread / memory_fact 四类
已有信号转成"续接式"开场白 + 1-3 个 quick reply chip.

设计选择 — 不调 LLM:
- 模板式拼接, ≤ 100ms 返回 (纯 SQL + 字符串)
- 措辞会有点机械但 ship 后 7d 看用户感受再决定加 LLM 润色
- 模板优于"机械感"的代价: 第一版用户能立刻看到, 而不是等 2-5s LLM 转圈

签名: compute_conversation_opener(db, user_id) → Optional[OpenerSuggestion]

返回 None 表示当前没信号 — 前端退化到现有 SUGGESTIONS chip.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

CHINA_TZ = ZoneInfo("Asia/Shanghai")


@dataclass
class OpenerSuggestion:
    """一条 chat opener 建议. 序列化给前端 (asdict)."""
    text: str                                       # AI 主动开场白 (≤ 80 字)
    source: str                                     # 'action_card_due' / 'anomaly' / 'case_thread' / 'memory_fact'
    source_id: Optional[int] = None                 # 对应记录 id, 前端 deep link
    quick_replies: List[str] = field(default_factory=list)  # 1-3 个一键回复 chip
    deep_link: Optional[str] = None                 # 点开场白卡片本身跳哪
    priority: int = 0                               # 越大越先展示 (内部排序用)


def compute_conversation_opener(db: Session, user_id: int) -> Optional[OpenerSuggestion]:
    """
    按优先级试 4 类信号, 返回最高优先级的 opener. 都没命中返回 None.

    优先级:
        1. ActionCard 检验日 ≤ 2 天 (priority=100)
        2. 24h 内 anomaly_alert 未确认 (priority=80)
        3. 7 天内 case_thread 有更新 (priority=60)
        4. 7 天内新写入 memory_fact (优先级最低, priority=40)
    """
    # 旁路: 任何错误返回 None, 前端退化到 SUGGESTIONS
    try:
        opener = (
            _try_action_card_due(db, user_id)
            or _try_recent_anomaly(db, user_id)
            or _try_active_case_thread(db, user_id)
            or _try_recent_memory_fact(db, user_id)
        )
        return opener
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[conversation_opener] compute failed (bypass): {e}")
        return None


# ─────────────── strategy 1: ActionCard due ───────────────


def _try_action_card_due(db: Session, user_id: int) -> Optional[OpenerSuggestion]:
    """
    Active ActionCard 检验日距今 ≤ 2 天 (但还没 graded). 这是 trust loop 用户最该
    回答的问题: "你做了吗 / 效果如何?"
    """
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    soon = now + timedelta(days=2)

    card = (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == user_id,
            ActionCard.status == "active",
            ActionCard.check_back_date.isnot(None),
            ActionCard.check_back_date <= soon,
            ActionCard.graded_at.is_(None),
            ActionCard.adherence_confidence.is_(None),
            ActionCard.user_decision.is_(None),
        )
        .order_by(ActionCard.check_back_date.asc())
        .first()
    )
    if not card:
        return None

    # 距 check_back 还有几天 (中国时间)
    chk = card.check_back_date
    if chk.tzinfo is None:
        chk = chk.replace(tzinfo=timezone.utc)
    days_until = max(0, (chk.astimezone(CHINA_TZ).date() - datetime.now(CHINA_TZ).date()).days)

    title = (card.title or "").strip()[:40] or "之前的建议"

    if days_until == 0:
        text = f"今天就是「{title}」的检验日，做到了吗？"
    elif days_until == 1:
        text = f"明天就到「{title}」的检验日，目前情况怎么样？"
    else:  # 2
        text = f"还有 {days_until} 天到「{title}」检验日，进展如何？"

    return OpenerSuggestion(
        text=text,
        source="action_card_due",
        source_id=card.id,
        quick_replies=["做到了 ✅", "没做 ❌", "调整下计划"],
        deep_link=f"/action-cards/{card.id}",
        priority=100,
    )


# ─────────────── strategy 2: recent anomaly ───────────────


def _try_recent_anomaly(db: Session, user_id: int) -> Optional[OpenerSuggestion]:
    """
    24h 内 critical / warning anomaly_alert, 未 acknowledged 也未 suppressed.
    info 级跳过 (噪声).
    """
    from app.models.anomaly_alert import AnomalyAlert

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=24)).date()

    alert = (
        db.query(AnomalyAlert)
        .filter(
            AnomalyAlert.user_id == user_id,
            AnomalyAlert.detection_date >= cutoff,
            AnomalyAlert.severity.in_(["warning", "critical"]),
            AnomalyAlert.is_suppressed == False,  # noqa: E712
            AnomalyAlert.acknowledged == False,  # noqa: E712
        )
        .order_by(AnomalyAlert.severity.desc(), AnomalyAlert.detection_date.desc())
        .first()
    )
    if not alert:
        return None

    metric_label = _metric_human(alert.metric_name)
    val = alert.current_value
    val_str = f"{val:.0f}" if val is not None and val == int(val) else f"{val:.1f}" if val is not None else "?"

    text = f"你昨天 {metric_label} {val_str}，比平时{_deviation_word(alert.deviation_pct)}，现在感觉怎么样？"

    return OpenerSuggestion(
        text=text,
        source="anomaly",
        source_id=alert.id,
        quick_replies=["还好 / 已恢复", "确实不太对", "分析一下原因"],
        deep_link=f"/trace/anomaly_{alert.id}",
        priority=80,
    )


def _metric_human(name: str) -> str:
    return {
        "resting_heart_rate": "静息心率",
        "rhr": "静息心率",
        "hrv": "HRV",
        "sleep_score": "睡眠分",
        "stress_level": "压力值",
        "spo2_avg": "平均血氧",
        "spo2_low": "最低血氧",
        "body_battery": "电量",
    }.get(name, name)


def _deviation_word(pct: Optional[float]) -> str:
    if pct is None:
        return "异常"
    apct = abs(pct)
    if apct < 10:
        return "偏离一点"
    if apct < 25:
        return "明显偏离"
    return "差很多"


# ─────────────── strategy 3: active case_thread ───────────────


def _try_active_case_thread(db: Session, user_id: int) -> Optional[OpenerSuggestion]:
    """
    最近 3-7 天内有更新的 active case_thread. 如果上次更新 < 24h, 跳过 (太近用户还没遗忘).
    """
    from app.models.clinical_journal import CaseThread

    now = datetime.now(timezone.utc)
    too_recent = now - timedelta(hours=24)
    too_old = now - timedelta(days=7)

    thread = (
        db.query(CaseThread)
        .filter(
            CaseThread.user_id == user_id,
            CaseThread.status == "active",
            CaseThread.last_updated_at <= too_recent,
            CaseThread.last_updated_at >= too_old,
        )
        .order_by(CaseThread.last_updated_at.desc())
        .first()
    )
    if not thread:
        return None

    title = (thread.title or thread.theme or "").strip()[:40]
    if not title:
        return None

    # 距上次更新天数
    last = thread.last_updated_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    days_ago = max(1, (now - last).days)

    text = f"上次我们聊到「{title}」({days_ago} 天前)，这两天有变化吗？"

    return OpenerSuggestion(
        text=text,
        source="case_thread",
        source_id=thread.id,
        quick_replies=["好转了", "没变化", "更糟了"],
        deep_link=f"/(tabs)/journal",
        priority=60,
    )


# ─────────────── strategy 4: recent memory_fact ───────────────


def _try_recent_memory_fact(db: Session, user_id: int) -> Optional[OpenerSuggestion]:
    """
    7 天内新写入的 memory_fact (semantic / episodic 层, 跳过 working).
    层 working 是临时短期工作记忆, 不该作为 opener 信号.
    """
    from app.models.memory_fact import MemoryFact

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=7)

    fact = (
        db.query(MemoryFact)
        .filter(
            MemoryFact.user_id == user_id,
            MemoryFact.tier.in_(["semantic", "episodic"]),
            MemoryFact.last_reinforced_at >= cutoff,
            MemoryFact.superseded_by_id.is_(None),
        )
        .order_by(MemoryFact.last_reinforced_at.desc())
        .first()
    )
    if not fact:
        return None

    # 简单拼: subject predicate object — "你 提到 鼻炎"
    subj = (fact.subject or "你").strip()[:30]
    pred = _predicate_human(fact.predicate)
    obj = (fact.object_value or "").strip()[:50]

    if not obj:
        return None

    text = f"{subj} {pred} {obj}，最近还想再聊聊吗？"

    return OpenerSuggestion(
        text=text,
        source="memory_fact",
        source_id=fact.id,
        quick_replies=["想聊", "暂时不用"],
        priority=40,
    )


def _predicate_human(predicate: str) -> str:
    return {
        "has_symptom": "提到症状",
        "takes_medication": "在服用",
        "has_allergy": "对",
        "prefers": "偏好",
        "avoids": "避开",
        "history_of": "有过",
        "responds_to": "对...有反应",
    }.get(predicate, predicate)
