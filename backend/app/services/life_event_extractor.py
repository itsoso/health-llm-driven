"""转后异步生活事件抽取管线 (镜像 memory 抽取先例)。

背景: 生活事件时间线的存储/读/时间精度早已就绪 —— 复用 HealthEpisode
(episode_type="life_event", 见 api/episodes.py "复用既有表,不建新表"), 发生时间走
services/occurred_time.py 的确定性折算, 读走 health_query(events) → /episodes/me/life-events。
**唯一缺口**是把这些事件从对话里自动抓出来: 现有 health_record(event) 要模型显式调用,
用户被动提及 ("下午从家出发, 刚到公司") 不会触发。本管线在**转后**补上自动抽取。

分工 (R4): LLM(fast 档) 只产 title / 时间原文 / category; occurred_at + 精度由
occurred_time.resolve_occurred_at() 确定性算 —— 不让模型编时间。

防过度抽取四道闸 (简报记忆自强化到 1.0 的历史坑):
  ① category 白名单硬过滤 (_CATEGORY_WHITELIST)
  ② 每消息最多 3 条 (_PER_MESSAGE_CAP) + 每用户每天上限 20 条 (_DAILY_CAP), 超限丢弃 + warning
  ③ 纯健康数值记录 (喝水/体重/血压 —— 已有专表) 不抽, 别双写 (_looks_like_health_record)
  ④ 抽取失败 fail-loud 记 error 不吞 (LLM/解析异常 re-raise, 让 Celery 标失败可见)

幂等: 同一天 (北京) 同一归一化 title 只落一条 —— 覆盖同消息重跑 + 与 health_record(event)
显式路径的跨路重复。source_id=消息 id 留 provenance。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.occurred_time import BEIJING_TZ, resolve_occurred_at

logger = logging.getLogger(__name__)

# ① category 白名单 —— LLM 只能产这些类目, 其余一律丢 (也当"这不是生活事件"的过滤)。
_CATEGORY_WHITELIST = frozenset(
    {"travel", "arrival", "purchase", "delivery", "symptom_onset", "routine", "other"}
)

# ② 数量闸
_PER_MESSAGE_CAP = 3
_DAILY_CAP = 20
_RAW_EVENT_LIMIT = 12  # LLM 原始输出上限, 先截断再逐条过闸

_TITLE_MAX = 80  # 对齐 HealthEpisode.headline / LifeEventCreate.title 上限


# ── ③ 健康数值记录判定 (有专表, 不双写) ─────────────────────────

def _looks_like_health_record(title: str) -> bool:
    """喝水/体重/血压/血糖/血氧/心率 这类有专表的数值记录 → 不当生活事件抽。

    只命中健康**数值日志**, 不误伤合法生活事件 (如 "买了500g牛肉" 是 purchase, 不 drop)。
    """
    t = (title or "").lower()
    if re.search(r"[喝饮]", t) and re.search(r"水|饮料|茶|咖啡", t) and re.search(
        r"\d+\s*(ml|毫升|升)", t
    ):
        return True
    if re.search(r"[喝饮]水", t):  # "喝水" 本身即 water 专表域
        return True
    if re.search(r"体重\D{0,4}\d", t):
        return True
    if re.search(r"血压\D{0,4}\d", t):
        return True
    if re.search(r"血糖\D{0,4}\d", t):
        return True
    if re.search(r"血氧\D{0,4}\d", t):
        return True
    if re.search(r"心率\D{0,4}\d", t):
        return True
    return False


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", "", (title or "").strip().lower())


# ── LLM 抽取 (fast 档, 严格 JSON) ─────────────────────────────

_EXTRACT_PROMPT = """你从一段**用户自己发的消息**里抽取"生活事件"(不是健康指标记录)。

生活事件 = 有时间属性的行程/到达/购买/收货/症状起点/日常节点, 例如:
  出发去公司 / 到家了 / 下午3点半到医院 / 买了咖啡机 / 快递签收 / 头痛开始 / 起床。

规则:
1. 只抽用户**亲历**的事件, 不抽 AI 建议/推测/未来计划。
2. category 必须是这些之一 (英文): travel(出行/在路上) / arrival(到达某地) /
   purchase(购买) / delivery(收/寄快递) / symptom_onset(症状起点) /
   routine(起床/睡觉/吃饭等日常) / other。
3. **不要**抽健康数值记录 (喝水多少ml / 体重 / 血压 / 血糖 / 心率) —— 那些有专门记录, 跳过。
4. title 简短 (≤20字), 中文, 只描述事件本身。
5. time_text: 把消息里跟这条事件相关的**时间原文**原样填 ("21:07" / "下午" / "3点半"),
   没提时间就填空字符串 ""。不要自己编时间、不要换算。
6. 最多 3 条; 没有可抽的生活事件就返回空数组。

严格 JSON (无 markdown 代码块, 无解释):
{"events": [
  {"title": "落地北京", "category": "arrival", "time_text": "21:07"},
  {"title": "从家出发", "category": "travel", "time_text": "下午"}
]}

消息:
---
%s
---
"""


async def _llm_extract_events(text: str) -> List[Dict[str, Any]]:
    """调 fast 档模型抽 title/category/time_text。fail-loud: 异常 re-raise (闸 ④)。"""
    from app.services.llm.factory import (
        create_provider_for_model_id,
        get_llm_provider,
    )
    from app.services.llm.usage_tracker import set_caller

    try:
        from app.services.llm.model_registry import pick_fast_tool_model_id

        fast_id = pick_fast_tool_model_id()
        provider = (
            create_provider_for_model_id(fast_id) if fast_id else get_llm_provider()
        )
    except Exception:
        provider = get_llm_provider()

    set_caller("life_event.extractor")
    raw = await provider.chat(
        messages=[
            {"role": "system", "content": "你是生活事件抽取器, 严格按要求输出 JSON。"},
            {"role": "user", "content": _EXTRACT_PROMPT % text[:1500]},
        ],
        temperature=0.1,
        max_tokens=500,
    )
    if isinstance(raw, dict):
        raw = raw.get("content", "") or ""
    return _parse_events_json(raw)


def _parse_events_json(raw: str) -> List[Dict[str, Any]]:
    """容错解析 LLM 输出成 events[]。解析不出 JSON → 返回空 (空消息很正常, 非异常)。"""
    if not raw:
        return []
    text = raw.strip()
    if "```" in text:
        for part in text.split("```"):
            p = part.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                text = p
                break
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    events = parsed.get("events") if isinstance(parsed, dict) else None
    return events if isinstance(events, list) else []


# ── 编排 ──────────────────────────────────────────────────────

def _anchor_from_message(created_at: datetime) -> datetime:
    """消息 created_at (naive=UTC 墙钟 / aware) → 北京 tz-aware。生活事件全程北京锚。"""
    dt = created_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BEIJING_TZ)


def _resolve_time(time_text: Optional[str], anchor: datetime):
    """time_text → (occurred_at, precision)。空/不可解析 → (消息时间, "inferred")(闸: 诚实精度)。"""
    t = (time_text or "").strip()
    if not t:
        return anchor, "inferred"
    try:
        return resolve_occurred_at(t, now=anchor)
    except ValueError:
        # 模型给了无法确定性折算的时间原文 → 退回消息时间, 标 inferred (不假装精确)。
        logger.info("[life_event] 时间原文无法折算, 退 inferred: %r", t)
        return anchor, "inferred"


def extract_life_events_from_message(
    db: Session,
    user_id: int,
    source_message_id: int,
    *,
    llm_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, int]:
    """从一条用户消息抽生活事件写入 HealthEpisode(life_event)。返回各闸计数 summary。

    llm_events 注入 (测试/已算好) 时跳过 LLM; None 时走 fast 档 LLM (闸 ④ fail-loud)。
    """
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.episode import HealthEpisode

    summary = {
        "created": 0,
        "dropped_category": 0,
        "dropped_health_record": 0,
        "dropped_message_cap": 0,
        "dropped_daily_cap": 0,
        "skipped_duplicate": 0,
    }

    msg = (
        db.query(AgentMessage)
        .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
        .filter(
            AgentMessage.id == source_message_id,
            AgentConversation.user_id == user_id,
            AgentMessage.role == "user",
        )
        .first()
    )
    if msg is None:
        logger.warning(
            "[life_event] user=%s message=%s 不是该用户的 user 消息, 跳过",
            user_id, source_message_id,
        )
        return summary

    text = (msg.content or "").strip()
    if not text:
        return summary

    anchor = _anchor_from_message(msg.created_at)

    if llm_events is None:
        # 闸 ④: LLM 失败 fail-loud —— 记 error 并 re-raise, Celery 标失败可见。
        try:
            import asyncio

            llm_events = asyncio.run(_llm_extract_events(text))
        except Exception:
            logger.error(
                "[life_event] LLM 抽取失败 user=%s message=%s",
                user_id, source_message_id, exc_info=True,
            )
            raise

    if not isinstance(llm_events, list) or not llm_events:
        return summary

    # 当天 (北京) 已有生活事件: 供 ② 每日上限 + 幂等去重 (同天同归一化 title 只落一条)。
    day_start = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    same_day = (
        db.query(HealthEpisode)
        .filter(
            HealthEpisode.user_id == user_id,
            HealthEpisode.episode_type == "life_event",
            HealthEpisode.occurred_at >= day_start,
            HealthEpisode.occurred_at < day_end,
        )
        .all()
    )
    existing_count = len(same_day)
    seen_titles = {_normalize_title(ep.headline or "") for ep in same_day}

    now_utc = datetime.now(timezone.utc)
    created = 0
    for ev in llm_events[:_RAW_EVENT_LIMIT]:
        if not isinstance(ev, dict):
            continue
        title = str(ev.get("title") or "").strip()[:_TITLE_MAX]
        category = str(ev.get("category") or "").strip().lower()
        time_text = ev.get("time_text")
        if not title:
            continue

        # ① 白名单硬过滤
        if category not in _CATEGORY_WHITELIST:
            summary["dropped_category"] += 1
            logger.warning(
                "[life_event] 丢弃越界 category=%r title=%r user=%s",
                category, title, user_id,
            )
            continue

        # ③ 健康数值记录 (专表域) 不双写
        if _looks_like_health_record(title):
            summary["dropped_health_record"] += 1
            logger.warning(
                "[life_event] 丢弃健康数值记录 (专表域) title=%r user=%s", title, user_id
            )
            continue

        # 幂等: 同天同归一化 title 只落一条
        norm = _normalize_title(title)
        if norm in seen_titles:
            summary["skipped_duplicate"] += 1
            continue

        # ② 每消息上限
        if created >= _PER_MESSAGE_CAP:
            summary["dropped_message_cap"] += 1
            logger.warning(
                "[life_event] 超每消息上限 %d, 丢弃 title=%r user=%s",
                _PER_MESSAGE_CAP, title, user_id,
            )
            continue

        # ② 每日上限
        if existing_count + created >= _DAILY_CAP:
            summary["dropped_daily_cap"] += 1
            logger.warning(
                "[life_event] 超每日上限 %d, 丢弃 title=%r user=%s",
                _DAILY_CAP, title, user_id,
            )
            continue

        occurred_at, precision = _resolve_time(time_text, anchor)
        ep = HealthEpisode(
            user_id=user_id,
            episode_type="life_event",
            source_type="chat",
            source_id=source_message_id,
            occurred_at=occurred_at,
            status="closed",  # 生活事件落地即闭合 (对齐 create_life_event)
            closed_at=now_utc,
            risk_level="L0",
            headline=title,
            context_snapshot={
                "occurred_raw": (time_text or "").strip() or None,
                "occurred_precision": precision,
                "notes": None,
                "category": category,
                "source": "auto_extract",
                "source_message_id": source_message_id,
            },
        )
        db.add(ep)
        seen_titles.add(norm)
        created += 1

    if created:
        db.commit()
    summary["created"] = created
    return summary
