"""对话记忆服务 — 从对话中提取并检索跨会话记忆"""
import re
import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.conversation_memory import ConversationMemory

logger = logging.getLogger(__name__)

# 关键词模式：匹配用户透露的持久性事实
MEMORY_PATTERNS = [
    # 医嘱/医生建议
    (r"医生(?:说|建议|让|要求|嘱咐).{2,60}", "medical"),
    # 过敏
    (r"(?:我|本人)(?:对|有).{1,20}过敏", "allergy"),
    (r"过敏(?:原|源|物质).{1,30}", "allergy"),
    # 偏好
    (r"(?:我|本人)(?:喜欢|偏好|习惯|爱吃|不吃|不喝|忌口|素食|清真).{2,40}", "preference"),
    # 身体状况/受伤
    (r"(?:我|本人)(?:受伤|骨折|扭伤|拉伤|手术|住院).{2,40}", "fact"),
    (r"(?:我|本人)(?:有|患有|得了).{1,20}(?:病|症|炎|结石|肌瘤)", "medical"),
    # 运动限制
    (r"(?:不能|不可以|避免)(?:做|跑|游|骑|举).{2,30}", "instruction"),
    # 药物
    (r"(?:在吃|在服用|每天吃|长期吃).{2,30}(?:药|片|胶囊|素)", "medical"),
]


def extract_memories(
    user_msg: str,
    ai_reply: str,
    user_id: int,
    conversation_id: Optional[int],
    db: Session,
) -> List[ConversationMemory]:
    """从用户消息中提取值得记住的事实，保存到数据库"""
    created = []
    for pattern, mem_type in MEMORY_PATTERNS:
        matches = re.findall(pattern, user_msg)
        for match in matches:
            content = match.strip()
            if len(content) < 4:
                continue

            # 去重：同用户+相同内容不重复存储
            existing = db.query(ConversationMemory).filter(
                ConversationMemory.user_id == user_id,
                ConversationMemory.content == content,
            ).first()
            if existing:
                continue

            mem = ConversationMemory(
                user_id=user_id,
                memory_type=mem_type,
                content=content,
                source_conversation_id=conversation_id,
                relevance_score=1.0,
            )
            db.add(mem)
            created.append(mem)

    if created:
        try:
            db.commit()
            logger.info(f"[Memory] 为用户 {user_id} 提取了 {len(created)} 条记忆")
        except Exception as e:
            db.rollback()
            logger.warning(f"[Memory] 保存记忆失败: {e}")
            created = []

    return created


def get_relevant_memories(db: Session, user_id: int, limit: int = 5) -> str:
    """获取用户最近的相关记忆，格式化为上下文字符串"""
    memories = db.query(ConversationMemory).filter(
        ConversationMemory.user_id == user_id,
    ).order_by(
        ConversationMemory.relevance_score.desc(),
        ConversationMemory.created_at.desc(),
    ).limit(limit).all()

    if not memories:
        return ""

    type_labels = {
        "medical": "医嘱",
        "allergy": "过敏",
        "preference": "偏好",
        "instruction": "注意事项",
        "fact": "个人情况",
    }
    items = []
    for m in memories:
        label = type_labels.get(m.memory_type, "记忆")
        items.append(f"[{label}] {m.content}")

    return "用户历史记忆:\n" + "\n".join(items)
