"""Immutable turn context construction and time prompt rendering."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
import logging
from typing import Any, Optional, Sequence
from uuid import uuid4

from sqlalchemy.orm import Session

from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, TurnSnapshot


BEIJING_TZ = timezone(timedelta(hours=8))
logger = logging.getLogger(__name__)


def build_execution_context(
    db: Session,
    *,
    user_id: Optional[int],
    channel: str,
    now_utc: Optional[datetime] = None,
    run_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> ExecutionContext:
    """Resolve the user timezone once, then freeze time for the full turn."""
    try:
        from app.utils.timezone import get_user_timezone

        user_timezone = get_user_timezone(db, user_id) if user_id is not None else BEIJING_TZ
    except Exception as exc:  # noqa: BLE001 - retain deterministic fallback with visibility
        logger.warning(
            "[agent_kernel.context] timezone lookup failed user=%s; fallback=Asia/Shanghai error=%s",
            user_id,
            exc,
        )
        user_timezone = BEIJING_TZ
    timezone_name = _timezone_label(user_timezone)
    return ExecutionContext.now(
        user_id=user_id,
        channel=channel,
        timezone_name=timezone_name,
        now_utc=now_utc,
        run_id=run_id or f"run-{uuid4().hex}",
        turn_id=turn_id or f"turn-{uuid4().hex}",
    )


def build_turn_snapshot(
    db: Session,
    *,
    user_id: Optional[int],
    channel: str,
    text: str,
    client_capabilities: Optional[dict[str, Any]] = None,
    client_time_context: Optional[dict[str, Any]] = None,
    media: Optional[Sequence[dict[str, Any]]] = None,
    source_message_id: Optional[str] = None,
    client_turn_id: Optional[str] = None,
    now_utc: Optional[datetime] = None,
    run_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    policy_mode: str = "enforce",
) -> TurnSnapshot:
    """Create the one immutable envelope/context/intent snapshot for a turn."""
    context = build_execution_context(
        db,
        user_id=user_id,
        channel=channel,
        now_utc=now_utc,
        run_id=run_id,
        turn_id=turn_id,
    )
    media_items = tuple(
        dict(item)
        for item in (media or ())
        if isinstance(item, dict)
    )
    envelope = AgentEnvelope(
        user_id=user_id,
        channel=channel,
        text=text or "",
        client_capabilities=dict(client_capabilities or {}),
        client_time_context=dict(client_time_context or {}),
        media=media_items,
        source_message_id=(str(source_message_id).strip() or None) if source_message_id else None,
        client_turn_id=(str(client_turn_id).strip() or None) if client_turn_id else None,
    )
    return TurnSnapshot(
        envelope=envelope,
        context=context,
        intent=build_intent_frame(envelope, context),
        policy_mode=policy_mode,
    )


def format_turn_time_context_prompt(
    context: ExecutionContext,
    *,
    client_time_context: Optional[dict[str, Any]] = None,
) -> str:
    """Render the only time context allowed in prompts for this turn."""
    now = context.current_time
    generated_utc = now.astimezone(UTC)
    client_lines: list[str] = []
    if isinstance(client_time_context, dict):
        client_now = str(client_time_context.get("client_now_iso") or "").strip()[:80]
        client_tz = str(client_time_context.get("timezone") or "").strip()[:64]
        client_locale = str(client_time_context.get("locale") or "").strip()[:32]
        raw_offset = client_time_context.get("timezone_offset_minutes")
        offset_text = ""
        if isinstance(raw_offset, (int, float)):
            offset_text = f"，UTC offset minutes={int(raw_offset)}"
        if client_now or client_tz or offset_text or client_locale:
            client_lines.append(
                "- 客户端上报本地时间: "
                f"{client_now or '未提供'}"
                f"{f'，timezone={client_tz}' if client_tz else ''}"
                f"{offset_text}"
                f"{f'，locale={client_locale}' if client_locale else ''}"
            )
    client_block = "\n".join(client_lines) if client_lines else "- 客户端上报本地时间: 未提供"
    return (
        "## 当前时间上下文（系统生成，最高优先级）\n"
        f"- 本轮执行生成时间 UTC: {generated_utc.isoformat(timespec='seconds')}\n"
        f"- 用户生效时区: {context.timezone}\n"
        f"- 用户本地当前时间: {now.isoformat(timespec='seconds')}\n"
        f"- 用户本地当前时刻（可直接对用户引用）: {now:%H:%M}\n"
        f"- 用户本地今天: {now.date().isoformat()}（{_weekday_cn(now)}），当前时段: {_period_cn(now.hour)}\n"
        f"{client_block}\n"
        "时间规则:\n"
        "1. 所有今天/昨天/明天/昨晚/刚才/几小时后/几点提醒/起床或入睡建议，必须以上面的“用户本地当前时间”为基准。\n"
        "2. 回答任何时间相关问题时，先使用该当前时间做推导；必须精确到分钟，不得只说“现在23点”，不得猜测“现在约几点”，不得沿用历史消息里的旧日期或旧时间。\n"
        "3. 推荐今晚/今天剩余的入睡、起床准备、饮食、训练、用药或提醒窗口时，开始时间不得早于用户本地当前时间；如果理想窗口已经过去，必须明确说已经过去，并给出从当前时刻往后的可执行窗口或改为明天方案。\n"
        "4. 如果客户端上报时间与服务器生成的用户本地时间明显不一致，提示用户可能存在设备时间或时区差异，并以服务器生成时间为主。"
    )


def _timezone_label(value: timezone) -> str:
    key = getattr(value, "key", None)
    if isinstance(key, str) and key:
        return key
    if value.utcoffset(datetime.now(UTC)) == timedelta(hours=8):
        return "Asia/Shanghai"
    return str(value)


def _weekday_cn(value: datetime) -> str:
    return ("周一", "周二", "周三", "周四", "周五", "周六", "周日")[value.weekday()]


def _period_cn(hour: int) -> str:
    if 5 <= hour < 9:
        return "早晨"
    if 9 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 22:
        return "晚上"
    return "夜间"
