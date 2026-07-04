"""
干预效果评估任务 — Agent Native Phase 2。

每周一 11:00 自动运行，对活跃的 guide/plan 类型 ActionCard
调用 LLM 评估干预效果，通过 Telegram 推送评估报告。
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.action_card import ActionCard
from app.models.user import User

logger = logging.getLogger(__name__)

ASSESSMENT_PROMPT = """你正在评估一个用户的健康行动计划执行效果。

**行动计划**: {title}
**创建日期**: {created_at}
**已执行天数**: {days_active}
**累计评估次数**: {assessment_count}

**计划内容（摘要）**:
{content_summary}

**用户当前健康状态（Digital Health Twin）**:
{twin_blob}

请评估：
1. 计划中的目标有没有在改善？用 Twin 中的具体数字作为证据。
2. 有没有需要调整的建议？
3. 总体评分：1-10分（10=完全达标，5=未见明显变化，1=恶化）

返回 JSON（且仅返回 JSON）：
{{"score": N, "summary": "一句话总结", "evidence": ["证据1", "证据2"], "adjustments": ["建议1"]}}"""


@celery_app.task(time_limit=300)
def assess_active_interventions():
    """评估所有活跃的干预计划"""
    logger.info("[干预评估] 开始")

    with SessionLocal() as db:
        cards = db.query(ActionCard).filter(
            ActionCard.status == "active",
            ActionCard.card_type.in_(["guide", "plan"]),
        ).all()

        if not cards:
            logger.info("[干预评估] 无活跃干预计划")
            return {"assessed": 0}

        assessed = 0
        for card in cards:
            try:
                result = _assess_single_card(db, card)
                if result:
                    assessed += 1
            except Exception as e:
                logger.warning(f"[干预评估] 卡片 {card.id} 评估失败: {e}")

        db.commit()

    logger.info(f"[干预评估] 完成，评估 {assessed} 张卡片")
    return {"assessed": assessed}


def _assess_single_card(db, card: ActionCard) -> dict:
    """评估单张 ActionCard"""
    from app.twin.builder import build_twin
    from app.twin.formatter import twin_to_prompt_blob
    from app.services.llm.factory import create_llm_provider
    from app.services.llm.usage_tracker import set_caller

    user_id = card.user_id
    set_caller("intervention_assessment.assess_card", user_id=user_id)

    # 构建 Twin
    twin = build_twin(db, user_id)
    twin_blob = twin_to_prompt_blob(twin)
    if not twin_blob:
        return None

    # 组装 prompt
    days_active = (datetime.now(UTC) - card.created_at.replace(
        tzinfo=UTC if card.created_at.tzinfo is None else card.created_at.tzinfo
    )).days if card.created_at else 0

    prompt = ASSESSMENT_PROMPT.format(
        title=card.title,
        created_at=str(card.created_at.date()) if card.created_at else "未知",
        days_active=days_active,
        assessment_count=card.assessment_count or 0,
        content_summary=card.content[:800] if card.content else "无",
        twin_blob=twin_blob,
    )

    # 调用 LLM
    provider = create_llm_provider(None)
    if not provider:
        provider = create_llm_provider(None)

    response = asyncio.run(provider.chat(
        messages=[
            {"role": "system", "content": "你是健康干预效果评估专家。基于数据给出客观评估。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=400,
    ))

    # 解析结果
    text = response.strip() if isinstance(response, str) else str(response)
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        logger.warning(f"[干预评估] 卡片 {card.id} LLM 返回非 JSON")
        result = {"score": 5, "summary": "评估结果解析失败", "evidence": [], "adjustments": []}

    # 更新卡片
    card.latest_assessment = result
    card.last_assessed_at = datetime.now(UTC)
    card.assessment_count = (card.assessment_count or 0) + 1

    # Telegram 推送评估报告
    try:
        from app.services.notification.telegram_push import TelegramPushService
        tg = TelegramPushService()
        if tg.configured:
            user = db.query(User).filter(User.id == user_id).first()
            user_name = user.name if user else f"用户{user_id}"
            score = result.get("score", "?")
            summary = result.get("summary", "")
            evidence = result.get("evidence", [])
            adjustments = result.get("adjustments", [])

            score_emoji = "🟢" if score >= 7 else ("🟡" if score >= 4 else "🔴")
            msg = (
                f"{score_emoji} *{user_name} 干预评估*\n\n"
                f"📋 {card.title}（第{days_active}天）\n"
                f"评分: {score}/10\n"
                f"总结: {summary}\n"
            )
            if evidence:
                msg += "\n证据:\n" + "\n".join(f"  • {e}" for e in evidence[:3])
            if adjustments:
                msg += "\n\n调整建议:\n" + "\n".join(f"  → {a}" for a in adjustments[:3])

            asyncio.run(tg.send_message(msg))
    except Exception as e:
        logger.warning(f"[干预评估] Telegram 推送失败: {e}")

    return result
