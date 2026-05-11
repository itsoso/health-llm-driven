"""对话记忆服务 — 从对话中提取并检索跨会话记忆.

P3-2 (2026-05-11) 升级:
- relevance decay: 查询排序时按时间指数衰减 (half_life=30d)
- 冲突解决: 同 type 内"语义簇"匹配 (前缀 N 字符) → 旧标 superseded, 新写入
- LLM 抽取兜底: 正则没匹配但消息含医疗关键词 → 调 LLM 抽取一次
- 只查 status='active', superseded 留库不展示
"""
import logging
import math
import re
from datetime import datetime, timezone
from typing import List, Optional

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

# P3-2 衰减半衰期 (天). 30 天后 score = 0.5 * original.
DECAY_HALF_LIFE_DAYS = 30.0

# 冲突匹配前缀长度 (字符). 同 type 内, 内容前 N 字符相同视为同语义簇.
# 中文 3 字常见前缀 (我喜欢 / 医生让 / 我对X / 在服用) 已能覆盖典型冲突.
# 局限: 无法识别实体差异 (e.g. "我对花粉过敏" 不会 supersede "我对花生过敏",
# 但 type 过滤已经让它们和别的 type 隔离). LLM judge 留给 Phase 3.5.
CONFLICT_PREFIX_LEN = 3

# LLM 兜底触发词 (出现这些词但正则没匹配 → 试 LLM 抽取一次)
_LLM_FALLBACK_TRIGGERS = re.compile(
    r"医生|过敏|手术|住院|结石|肌瘤|不耐|每天|长期|定期|复查|忌"
)


def _decay_score(base_score: float, created_at: Optional[datetime], now: Optional[datetime] = None) -> float:
    """按时间指数衰减相关度. half_life=DECAY_HALF_LIFE_DAYS 天后衰减到 1/2."""
    if not created_at:
        return base_score
    if now is None:
        now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    decay = math.pow(0.5, age_days / DECAY_HALF_LIFE_DAYS)
    return base_score * decay


def _supersede_conflicts(
    db: Session, user_id: int, memory_type: str, new_content: str
) -> List[int]:
    """同 type + 同语义簇的旧 active 记忆 → 标 superseded.

    语义簇判定: 内容前 CONFLICT_PREFIX_LEN 字相同.
    例: "我吃素" vs "我吃肉" 前 2 字"我吃"相同, 视为同簇 → 后写覆盖前.

    返回被 supersede 的旧记忆 id 列表.
    """
    if not new_content or len(new_content) < CONFLICT_PREFIX_LEN:
        return []

    prefix = new_content[:CONFLICT_PREFIX_LEN]
    now = datetime.now(timezone.utc)

    candidates = (
        db.query(ConversationMemory)
        .filter(
            ConversationMemory.user_id == user_id,
            ConversationMemory.memory_type == memory_type,
            ConversationMemory.status == "active",
            ConversationMemory.content.like(f"{prefix}%"),
            ConversationMemory.content != new_content,  # 完全相同不算冲突, 走 dedup
        )
        .all()
    )

    superseded_ids: List[int] = []
    for old in candidates:
        old.status = "superseded"
        old.superseded_at = now
        superseded_ids.append(old.id)
    return superseded_ids


def _extract_with_regex(user_msg: str) -> List[tuple[str, str]]:
    """正则路径: 返回 [(content, memory_type), ...]"""
    out: List[tuple[str, str]] = []
    for pattern, mem_type in MEMORY_PATTERNS:
        for match in re.findall(pattern, user_msg):
            content = match.strip()
            if len(content) >= 4:
                out.append((content, mem_type))
    return out


async def _extract_with_llm(user_msg: str) -> List[tuple[str, str]]:
    """LLM 兜底: 正则没抓到时跑一次 LLM 抽取. 失败返回空 (不影响主流程)."""
    try:
        from app.services.llm import get_llm_provider

        prompt = (
            "从下面这段用户健康对话里提取需要长期记住的事实, 输出 JSON 数组. "
            "每条字段: content (≤30 字, 去掉口语虚词) + type (allergy/medical/preference/instruction/fact). "
            "没有需要记的就返回 []. 只返回 JSON 数组本身, 不要解释.\n\n"
            f"用户消息:\n{user_msg}"
        )
        provider = get_llm_provider()
        result = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=400,
        )
        text = result if isinstance(result, str) else (result or {}).get("content", "")
        if not text:
            return []
        # 找 JSON 数组
        import json
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, count=1)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except Exception:
            try:
                start = text.index("[")
                end = text.rindex("]") + 1
                data = json.loads(text[start:end])
            except Exception:
                return []
        if not isinstance(data, list):
            return []
        out: List[tuple[str, str]] = []
        for item in data[:5]:  # 一次最多抽 5 条
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "")).strip()
            mem_type = str(item.get("type", "fact")).strip()
            if 4 <= len(content) <= 100 and mem_type in {
                "medical", "allergy", "preference", "instruction", "fact",
            }:
                out.append((content, mem_type))
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[Memory] LLM 兜底抽取失败: {e}")
        return []


def extract_memories(
    user_msg: str,
    ai_reply: str,
    user_id: int,
    conversation_id: Optional[int],
    db: Session,
    use_llm_fallback: bool = True,
) -> List[ConversationMemory]:
    """从用户消息中提取值得记住的事实, 保存到数据库.

    路径:
      1. 正则模式抽取 (主路径, 快, 高 precision)
      2. (P3-2) 正则没抓到且消息含医疗触发词 → LLM 兜底 (异步, 失败静默)
      3. 同 type 同语义簇旧记忆 → 标 superseded
      4. 完全相同内容 → 跳过 (dedup)

    use_llm_fallback=False: 跳过 LLM (单测 / 同步路径用).
    """
    extracted = _extract_with_regex(user_msg)

    # P3-2: 正则空 + 命中触发词 → LLM 兜底
    if not extracted and use_llm_fallback and _LLM_FALLBACK_TRIGGERS.search(user_msg):
        try:
            import asyncio
            extracted = asyncio.run(_extract_with_llm(user_msg))
        except RuntimeError:
            # 已在 event loop 里 (FastAPI 上下文), 跳过 LLM 兜底
            extracted = []
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Memory] LLM 兜底调度失败: {e}")
            extracted = []

    created: List[ConversationMemory] = []
    for content, mem_type in extracted:
        # 完全相同内容: 跳过 (dedup)
        existing = db.query(ConversationMemory).filter(
            ConversationMemory.user_id == user_id,
            ConversationMemory.content == content,
            ConversationMemory.status == "active",
        ).first()
        if existing:
            continue

        # 冲突: 同 type 同语义簇 → 旧标 superseded
        _supersede_conflicts(db, user_id, mem_type, content)

        mem = ConversationMemory(
            user_id=user_id,
            memory_type=mem_type,
            content=content,
            source_conversation_id=conversation_id,
            relevance_score=1.0,
            status="active",
        )
        db.add(mem)
        created.append(mem)

    if created:
        try:
            db.commit()
            logger.info(f"[Memory] 为用户 {user_id} 提取了 {len(created)} 条记忆")
        except Exception as e:  # noqa: BLE001
            db.rollback()
            logger.warning(f"[Memory] 保存记忆失败: {e}")
            created = []

    return created


def get_relevant_memories(db: Session, user_id: int, limit: int = 5) -> str:
    """获取用户最近的相关记忆, 格式化为上下文字符串.

    P3-2: 只查 status='active', 排序按 decayed_score (relevance × time-decay) 降序.
    """
    memories = db.query(ConversationMemory).filter(
        ConversationMemory.user_id == user_id,
        ConversationMemory.status == "active",
    ).order_by(
        ConversationMemory.relevance_score.desc(),
        ConversationMemory.created_at.desc(),
    ).limit(limit * 3).all()  # 多查一些, decay 后再 top-N

    if not memories:
        return ""

    now = datetime.now(timezone.utc)
    scored = [
        (m, _decay_score(m.relevance_score or 1.0, m.created_at, now))
        for m in memories
    ]
    scored.sort(key=lambda x: -x[1])
    top = [m for m, _s in scored[:limit]]

    type_labels = {
        "medical": "医嘱",
        "allergy": "过敏",
        "preference": "偏好",
        "instruction": "注意事项",
        "fact": "个人情况",
    }
    items = []
    for m in top:
        label = type_labels.get(m.memory_type, "记忆")
        items.append(f"[{label}] {m.content}")

    return "用户历史记忆:\n" + "\n".join(items)


def get_top_memory_for_opener(
    db: Session, user_id: int, k: int = 2,
) -> List[ConversationMemory]:
    """P3-3 用: 拉 top k 条 active 记忆 (allergy/medical/preference 优先), 给 chat opener 用."""
    priority_types = ["allergy", "medical", "preference"]

    primary = (
        db.query(ConversationMemory)
        .filter(
            ConversationMemory.user_id == user_id,
            ConversationMemory.status == "active",
            ConversationMemory.memory_type.in_(priority_types),
        )
        .order_by(
            ConversationMemory.relevance_score.desc(),
            ConversationMemory.created_at.desc(),
        )
        .limit(k * 2)
        .all()
    )
    if len(primary) >= k:
        return primary[:k]

    # 不够 → 补充其他 type
    others = (
        db.query(ConversationMemory)
        .filter(
            ConversationMemory.user_id == user_id,
            ConversationMemory.status == "active",
            ~ConversationMemory.memory_type.in_(priority_types),
        )
        .order_by(
            ConversationMemory.relevance_score.desc(),
            ConversationMemory.created_at.desc(),
        )
        .limit(k - len(primary))
        .all()
    )
    return primary + others
