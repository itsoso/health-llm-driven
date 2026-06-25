"""Write 自治层 —— 首切片(Enter-key thesis 第一步:系统首次在无人确认下执行写)。

**范围严格收窄到唯一一种 kind**:`measurement_prompt`(「今天测一下血压/体重」这类
良性、可逆、非医疗、非依从的提醒)。其它一切 kind 永不自治。

R4 / 安全不变量(blocking review 重点):
- **硬 allowlist 仅 {measurement_prompt}** —— medical-grade / adherence_nudge / doctor_booking /
  food_order / alarm_set / reorder_nudge 永不自治(不在 allowlist → 恒走人确认)。
  自治写依从事实会污染 twin.medication.adherence → DDI/PGx/SafetyGuardian(已知地雷),故硬排除。
- **CRITICAL 安全告警活跃 → 抑制自治**:有急症时一切让位,不做任何后台自动写。
- **每用户每日上限**(AUTONOMY_DAILY_CAP),防失控。
- **复用 write_intent_service.confirm 的原子认领/回滚/幂等**,不另开第二条执行路径;
  产物(SmartReminder)可逆(用户可 dismiss)。
- **默认开启**(write_autonomy_enabled=True),可一键关。
- **任何异常 fail-safe**:不自治、留给人确认,绝不假装执行。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.config import settings
from app.models.write_intent import WriteIntent
from app.utils.timezone import get_china_today

logger = logging.getLogger(__name__)

# 唯一允许自治执行的 kind:良性、可逆、非医疗、非依从。扩容须经安全评审 + 本注释更新。
AUTONOMY_ALLOWLIST = frozenset({"measurement_prompt"})
AUTONOMY_DAILY_CAP = 4
_BEIJING = timezone(timedelta(hours=8))


def autonomy_enabled() -> bool:
    """全局开关(默认 True)。可经 settings.write_autonomy_enabled 一键关。"""
    return bool(getattr(settings, "write_autonomy_enabled", True))


def is_autonomy_allowlisted(kind: str) -> bool:
    return kind in AUTONOMY_ALLOWLIST


def _auto_executed_today(db: Session, user_id: int) -> int:
    """今天(北京日历日)已自治执行(trust_tier='auto', status='executed')的条数。"""
    since = datetime.now(timezone.utc) - timedelta(days=2)  # 粗界限行数,再按北京日历日精确过滤
    rows = (
        db.query(WriteIntent.decided_at)
        .filter(
            WriteIntent.user_id == user_id,
            WriteIntent.trust_tier == "auto",
            WriteIntent.status == "executed",
            WriteIntent.decided_at.isnot(None),
            WriteIntent.decided_at >= since,
        )
        .all()
    )
    today = get_china_today()
    n = 0
    for (dt,) in rows:
        d = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        if d.astimezone(_BEIJING).date() == today:
            n += 1
    return n


def _safety_blocks_autonomy(db: Session, user_id: int) -> bool:
    """当前是否有 CRITICAL 告警,**或**安全规则评估有任何条目失败 → 抑制自治。

    关键(评审 BLOCKING):用 evaluate_rules_with_status 拿 failed_rule_count —— 普通 evaluate_safety
    会吞掉单条规则异常(critical_count 仍 0),若某 CRITICAL 规则在脏 twin 上崩了,门会假绿放行自治。
    部分筛查失败 = 可能漏了 CRITICAL → fail-safe 抑制。安全门用最新 twin(use_cache=False),不吃缓存。
    任何异常 → 抑制(绝不默许自治)。
    """
    try:
        from app.agents.safety_guardian.engine import evaluate_rules_with_status
        from app.agents.safety_guardian.schema import Severity
        from app.twin.builder import build_twin

        alerts, failed_rule_count = evaluate_rules_with_status(build_twin(db, user_id, use_cache=False))
        if failed_rule_count > 0:
            logger.warning(
                "[write_autonomy] %s 条安全规则评估失败 → fail-safe 抑制自治(可能漏 CRITICAL)",
                failed_rule_count,
            )
            return True
        return any(a.severity >= Severity.CRITICAL for a in alerts)
    except Exception as e:  # noqa: BLE001 — 安全检查失败必须 fail-safe 抑制,不能默许自治
        logger.warning("[write_autonomy] safety gate check failed → 抑制自治: %s", e)
        return True


def auto_execute_pending(db: Session, user_id: int) -> Dict[str, Any]:
    """对该用户 allowlisted 的 pending WriteIntent,gate 全过则无需人确认自动执行(走既有 confirm)。

    返回 {auto_executed, reason}。供 generate_measurement_prompts 之后(或后台任务)调用。
    gate 任一不过 → auto_executed=0 + reason,WriteIntent 维持 pending 留人确认。
    """
    if not autonomy_enabled():
        return {"auto_executed": 0, "reason": "disabled"}
    if _safety_blocks_autonomy(db, user_id):
        return {"auto_executed": 0, "reason": "safety_gate_blocked"}
    budget = AUTONOMY_DAILY_CAP - _auto_executed_today(db, user_id)
    if budget <= 0:
        return {"auto_executed": 0, "reason": "daily_cap"}

    pendings = (
        db.query(WriteIntent)
        .filter(
            WriteIntent.user_id == user_id,
            WriteIntent.status == "pending",
            WriteIntent.kind.in_(tuple(AUTONOMY_ALLOWLIST)),
        )
        .order_by(WriteIntent.created_at.asc())
        .limit(budget)
        .all()
    )
    if not pendings:
        return {"auto_executed": 0, "reason": "no_eligible_pending"}

    from app.services import write_intent_service  # 懒导入断循环(write_intent_service 反向引用本模块)

    executed = 0
    for wi in pendings:
        # 标 trust_tier=auto(审计可区分自治 vs 人确认),再走既有 confirm(原子认领/回滚/幂等)
        wi.trust_tier = "auto"
        db.flush()
        try:
            res = write_intent_service.confirm(db, user_id, wi.id)
        except Exception as e:  # noqa: BLE001 — 单条失败不拖累其余;confirm 已 fail-loud 回滚该条
            logger.warning("[write_autonomy] auto-confirm wi=%s 失败,跳过: %s", wi.id, e)
            continue
        if res.get("status") == "executed" and not res.get("idempotent"):
            executed += 1
    return {"auto_executed": executed, "reason": "ok"}
