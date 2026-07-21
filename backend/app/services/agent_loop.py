"""
Agent Planning Loop — Agent Native 核心。

每次 Garmin 数据同步后，组装完整上下文调用 LLM 进行自主推理，
判断是否需要主动干预用户。

设计原则：
  - "无事发生"就是最大价值 — 不制造焦虑
  - 每天最多推送 3 条主动消息（Redis 节制）
  - 已有 anomaly/safety 告警时跳过（避免重复）
  - LLM 返回 {"action": "silent"} 时完全静默
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 每天最多推送的主动消息数
DAILY_PUSH_LIMIT = 3
DAILY_PUSH_REDIS_KEY = "agent_loop:push_count:{user_id}:{date}"
DAILY_PUSH_TTL = 86400  # 24h

AGENT_SYSTEM_PROMPT = """你是一个健康管家 Agent，刚收到用户最新的 Garmin 数据同步。
你的任务不是回答问题，而是**主动判断**是否需要通知用户。

规则（严格遵守）：
1. 如果没什么特别的变化，返回 {"action": "silent"} — 不打扰就是最好的服务
2. 只在以下情况才通知：
   - 发现跟用户正在执行的行动计划相关的显著变化
   - 检测到需要关注但规则引擎没覆盖的模式
   - 有时间敏感的提醒（如"鼻炎行动指南第2周了，该提升跑量了"）
3. 不要重复规则引擎已经发出的告警
4. 消息要简短（<100字），有具体数字，有行动建议
5. 不要制造焦虑

返回 JSON（且仅返回 JSON）：
- 静默：{"action": "silent"}
- 通知：{"action": "notify", "title": "标题", "message": "内容", "severity": "info"}
  severity 只用 info 或 warning，critical 留给规则引擎"""


def _check_push_limit(user_id: int) -> bool:
    """检查今日推送次数是否已达上限"""
    try:
        from app.utils.redis_cache import get_redis_client
        client = get_redis_client()
        if not client:
            return True  # Redis 不可用时允许推送
        key = DAILY_PUSH_REDIS_KEY.format(user_id=user_id, date=datetime.now(UTC).strftime("%Y%m%d"))
        count = client.get(key)
        return (int(count) if count else 0) < DAILY_PUSH_LIMIT
    except Exception:
        return True


def _increment_push_count(user_id: int):
    """递增今日推送计数"""
    try:
        from app.utils.redis_cache import get_redis_client
        client = get_redis_client()
        if not client:
            return
        key = DAILY_PUSH_REDIS_KEY.format(user_id=user_id, date=datetime.now(UTC).strftime("%Y%m%d"))
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, DAILY_PUSH_TTL)
        pipe.execute()
    except Exception:
        pass


def _build_context(
    db: Session,
    user_id: int,
    twin,
    anomaly_alerts: List,
    safety_report,
) -> str:
    """组装 Agent 推理所需的完整上下文"""
    from app.twin.formatter import twin_to_prompt_blob
    from app.models.action_card import ActionCard

    parts = []

    # 1. Twin 快照
    twin_blob = twin_to_prompt_blob(twin)
    if twin_blob:
        parts.append(f"## 当前健康状态\n{twin_blob}")

    # 2. 本次检测的告警
    if anomaly_alerts:
        alert_lines = [f"- [{a.severity}] {a.message}" for a in anomaly_alerts]
        parts.append(f"## 本次异常告警（已通知用户，不要重复）\n" + "\n".join(alert_lines))
    else:
        parts.append("## 本次异常告警\n无")

    if safety_report and safety_report.alerts:
        safety_lines = [f"- [{a.severity.label_zh}] {a.title}" for a in safety_report.alerts[:5]]
        parts.append(f"## 安全规则告警\n" + "\n".join(safety_lines))

    # 3. 活跃的行动计划
    try:
        cards = db.query(ActionCard).filter(
            ActionCard.user_id == user_id,
            ActionCard.status == "active",
            ActionCard.card_type.in_(["guide", "plan", "recommendation"]),
        ).order_by(ActionCard.priority.desc()).limit(5).all()

        if cards:
            card_lines = []
            for c in cards:
                days = (datetime.now(UTC) - c.created_at.replace(tzinfo=UTC if c.created_at.tzinfo is None else c.created_at.tzinfo)).days if c.created_at else 0
                card_lines.append(f"- [{c.card_type}] {c.title}（创建{days}天前）")
            parts.append(f"## 用户正在执行的行动计划\n" + "\n".join(card_lines))
    except Exception:
        pass

    # 4. 用户记忆
    try:
        from app.services.conversation_memory_service import get_relevant_memories
        memories = get_relevant_memories(db, user_id, limit=3)
        if memories:
            parts.append(f"## 用户记忆\n{memories}")
    except Exception:
        pass

    return "\n\n".join(parts)


async def post_sync_reasoning(
    db: Session,
    user_id: int,
    twin,
    anomaly_alerts: List,
    safety_report,
) -> Dict[str, Any]:
    """
    Agent 自主推理循环。

    Returns:
        {"action": "silent"} 或 {"action": "notify", ...} 或 {"action": "skipped", "reason": "..."}
    """
    # 节制检查：anomaly/safety 已推送，跳过
    if anomaly_alerts:
        return {"action": "skipped", "reason": "anomaly_already_pushed"}

    if safety_report and any(int(a.severity) >= 3 for a in safety_report.alerts):
        return {"action": "skipped", "reason": "safety_critical_already_pushed"}

    # 节制检查：每日推送上限
    if not _check_push_limit(user_id):
        return {"action": "skipped", "reason": "daily_push_limit_reached"}

    # 组装上下文
    context = _build_context(db, user_id, twin, anomaly_alerts, safety_report)

    # 调用 LLM
    try:
        from app.services.llm.factory import create_llm_provider
        from app.services.llm.usage_tracker import set_caller
        set_caller("agent_loop.run", user_id=user_id)
        provider = create_llm_provider(None)  # 默认 provider
        if not provider:
            provider = create_llm_provider(None)

        response = await provider.chat(
            messages=[
                {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=0.3,
            max_tokens=300,
        )

        # 解析 JSON
        text = response.strip() if isinstance(response, str) else str(response)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        result = json.loads(text.strip())

        if result.get("action") == "notify":
            # 推送通知
            title = result.get("title", "健康管家提醒")
            message = result.get("message", "")
            severity = result.get("severity", "info")

            from app.services.notification.push_service import PushService
            from app.services.notification.evidence_policy import build_notification_evidence_data_for_user
            from app.services.notification.deeplinks import deeplink_for
            from app.services.notification.push_privacy import (
                GENERIC_LLM_PUSH_TITLE,
                llm_push_backstop,
            )

            # 点 ai_advice 推送时按内容落到饮食 / 健身页 (判不出领域则省略, 回首页)。
            blob = f"{title}\n{message}"
            if any(w in blob for w in ("饮食", "营养", "吃", "餐", "蛋白")):
                domain = "nutrition"
            elif any(w in blob for w in ("运动", "训练", "锻炼", "跑步", "强度", "拉伸")):
                domain = "exercise"
            else:
                domain = ""
            existing_data = {"source": "agent_loop", "severity": severity}
            advice_link = deeplink_for("ai_advice", domain=domain)
            if advice_link:
                existing_data["deep_link"] = advice_link

            # §5.6 backstop:LLM 文案点名药/补剂 → 锁屏降级泛化,原文只进 data
            safe_title, safe_message, redacted = llm_push_backstop(
                title, message, generic_title=GENERIC_LLM_PUSH_TITLE
            )
            if redacted:
                existing_data["full_title"] = title
                existing_data["full_content"] = message

            push_svc = PushService(db)
            await push_svc.send_notification(
                user_id=user_id,
                notification_type="ai_advice",
                title=safe_title,
                content=safe_message,
                data=build_notification_evidence_data_for_user(
                    db,
                    user_id=user_id,
                    notification_type="ai_advice",
                    source="agent_loop",
                    existing_data=existing_data,
                ),
            )
            _increment_push_count(user_id)
            logger.info(f"[agent_loop] user={user_id} → notify: {safe_title} (redacted={redacted})")

        else:
            logger.debug(f"[agent_loop] user={user_id} → silent")

        return result

    except json.JSONDecodeError:
        logger.warning(
            "[agent_loop] user=%s LLM 返回非 JSON response_len=%s",
            user_id,
            len(text) if text else 0,
        )
        return {"action": "error", "reason": "json_parse_failed"}
    except Exception as e:
        logger.warning("[agent_loop] user=%s 推理失败 error_type=%s", user_id, type(e).__name__)
        return {"action": "error", "reason": type(e).__name__}
