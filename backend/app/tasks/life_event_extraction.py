"""转后异步生活事件抽取 Celery 任务。

agent 对话回合完成后 (agent.py 转后接缝) 入队, 从该回合的用户消息里抽生活事件。
真业务在 services/life_event_extractor.py; 本文件只是 Celery 外壳 + 会话生命周期。
"""
import logging

from app.celery_app import celery_app
from app.database import SessionLocal
from app.services.life_event_extractor import extract_life_events_from_message

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.life_event_extraction.extract_life_events")
def extract_life_events(user_id: int, source_message_id: int) -> dict:
    """从一条用户消息抽生活事件。返回各闸计数 summary。

    抽取内部失败 fail-loud (会 re-raise) —— 让任务标失败在 Celery 里可见, 而不是静默吞。
    """
    with SessionLocal() as db:
        summary = extract_life_events_from_message(db, user_id, source_message_id)
    if summary.get("created"):
        logger.info(
            "[life_event] user=%s message=%s created=%s",
            user_id, source_message_id, summary["created"],
        )
    return summary
