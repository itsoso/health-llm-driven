"""R1 · 运行中上下文 compaction — 长对话溢出"截断→摘要"(agent 能力路线图 Wave 1)。

现状:build_messages(limit=N) 对超窗历史**静默丢弃**(agent_executor 用 limit=15)。
第一刀只动被丢弃的部分:把溢出轮次折叠成一条前情摘要消息,窗口内行为逐字节不变
——纯增益,摘要不可用时 fail-open 回退现状截断。

设计纪律(路线图 R1 + 业界三条):
- **零请求路径延迟**:LLM 折叠只在回合结束后的后台任务里跑(save_message 触发),
  build_messages 只读缓存(Redis),缓存无效 = 现状截断,下一轮自愈。
- **切点不拆轮**(Pi):折叠边界只落在完整消息之间(本系统历史只存 user/assistant
  文本,天然满足;此处显式按消息粒度切)。
- **结构化优先**(Pi):写入回执行(已记录/已确认写入/记录号…)由**代码**从被折叠的
  assistant 文本里逐字提取保留,不经 LLM 摘要(LLM 只管叙事线)。
- **不丢存储**(write-before-forget 的结构性满足):折叠只影响**发给 LLM 的 prompt 视图**,
  DB 全量消息与会后记忆抽取(memory_dialog_extractor 读 DB)完全不受影响。
- fail-open:折叠 LLM 失败 → 不写缓存/保留旧缓存,build_messages 回退截断,绝不断回合。
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_FOLD_KEY = "history_fold:{cid}"
_FOLD_TTL_S = 7 * 24 * 3600
_SUMMARY_MAX_CHARS = 1400
_RECEIPT_LINE_MAX = 12
# 写入回执/记录行 —— 逐字保留(写诚实与可回查性依赖这些行,绝不交给 LLM 转述)
_RECEIPT_LINE_RE = re.compile(r"已记录|已确认写入|记录号|已设置提醒|已更新|#\d+")

_SUMMARY_HEADER = "[系统附注 — 对话前情摘要(早于最近窗口的轮次,系统生成,仅供上下文)]"
_SUMMARY_FOOTER = "[前情摘要结束]"

# 进行中折叠去重(同会话并发回合只跑一个折叠任务)
_INFLIGHT: set[int] = set()


# ── 缓存薄封装(测试 monkeypatch 点;Redis 不可用 = 特性自然退化为现状截断)──
def _cache_get(cid: int) -> Optional[Dict[str, Any]]:
    try:
        from app.utils.redis_cache import RedisCache
        val = RedisCache.get(_FOLD_KEY.format(cid=cid))
        return val if isinstance(val, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _cache_set(cid: int, payload: Dict[str, Any]) -> None:
    try:
        from app.utils.redis_cache import RedisCache
        RedisCache.set(_FOLD_KEY.format(cid=cid), payload, ttl=_FOLD_TTL_S)
    except Exception:  # noqa: BLE001
        pass


# ── 读路径(build_messages 调,同步、零 LLM)────────────────────────────
def get_valid_fold_summary(cid: int, last_overflow_id: int) -> Optional[str]:
    """溢出恰好被折叠到 last_overflow_id 时返回摘要文本,否则 None(=现状截断)。

    严格相等校验:窗口滑动后有新消息落出而缓存未跟上 → None,绝不用陈旧摘要冒充
    (宁可退回截断也不给 LLM 错位的前情)。后台 refresh 下一轮自愈。
    """
    cached = _cache_get(cid)
    if not cached:
        return None
    if cached.get("folded_thru_id") != last_overflow_id:
        return None
    text = str(cached.get("summary") or "").strip()
    return text or None


def build_summary_message(summary_text: str) -> Dict[str, str]:
    return {"role": "user", "content": f"{_SUMMARY_HEADER}\n{summary_text}\n{_SUMMARY_FOOTER}"}


# ── 写路径(save_message 触发,后台 fail-soft)────────────────────────
def schedule_fold_refresh(cid: int, keep_recent: int) -> None:
    """回合收尾后调:有运行中事件循环则后台折叠,否则(celery/同步上下文)静默跳过。"""
    if not getattr(settings, "llm_history_compaction", False):
        return
    if cid in _INFLIGHT:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _INFLIGHT.add(cid)
    task = loop.create_task(_refresh_fold(cid, keep_recent))
    task.add_done_callback(lambda _t: _INFLIGHT.discard(cid))


def _extract_receipt_lines(texts: List[str]) -> List[str]:
    lines: List[str] = []
    for t in texts:
        for line in (t or "").splitlines():
            s = line.strip()
            if s and _RECEIPT_LINE_RE.search(s):
                lines.append(s[:120])
    return lines[-_RECEIPT_LINE_MAX:]  # 保最近的 N 行(时间序尾部)


async def _summarize(prior_summary: str, turns: List[Dict[str, str]]) -> Optional[str]:
    """flash 档叙事折叠。失败返回 None(调用方 fail-open)。"""
    convo = "\n".join(
        f"{'用户' if m['role'] == 'user' else '小巴'}: {(m['content'] or '')[:500]}"
        for m in turns
    )
    prompt = (
        "把下面的健康对话片段压缩成简洁的前情摘要(叙事线:用户关心什么/发生了什么/"
        "有什么未决事项),不超过 900 字。不要编造,不要给建议,不要复述具体数值明细"
        "(数值行由系统另行保留)。\n"
        + (f"\n[已有前情摘要,在其基础上续写合并]\n{prior_summary}\n" if prior_summary else "")
        + f"\n[新增对话片段]\n{convo}\n\n只输出摘要正文。"
    )
    try:
        from app.services.llm.factory import create_provider_for_extraction
        provider = create_provider_for_extraction(
            getattr(settings, "history_compaction_model_id", "deepseek-v4-flash")
        )
        resp = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            model=None, temperature=0.2, max_tokens=1200, stream=False,
        )
        text = (resp.get("content") if isinstance(resp, dict) else
                getattr(getattr(resp.choices[0], "message", None), "content", None)
                if hasattr(resp, "choices") else None)
        text = (text or "").strip()
        return text[:_SUMMARY_MAX_CHARS] or None
    except Exception as e:  # noqa: BLE001
        logger.warning("[history_compaction] 折叠 LLM 失败(fail-open 保留现状): %s", e)
        return None


async def _refresh_fold(cid: int, keep_recent: int) -> None:
    """增量折叠:只对新落出窗口的消息跑 LLM,已折叠前缀复用旧摘要。自建会话,全程 fail-soft。"""
    try:
        from app.database import SessionLocal
        from app.models.agent_conversation import AgentMessage

        db = SessionLocal()
        try:
            history = (
                db.query(AgentMessage)
                .filter(AgentMessage.conversation_id == cid)
                .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
                .all()
            )
        finally:
            db.close()

        if len(history) <= keep_recent:
            return  # 无溢出
        overflow = history[:-keep_recent]
        last_overflow_id = overflow[-1].id

        cached = _cache_get(cid) or {}
        if cached.get("folded_thru_id") == last_overflow_id:
            return  # 已是最新
        prior_thru = cached.get("folded_thru_id")
        prior_summary = str(cached.get("summary") or "")
        prior_receipts: List[str] = list(cached.get("receipt_lines") or [])

        fresh = [m for m in overflow if not isinstance(prior_thru, int) or m.id > prior_thru]
        if not fresh:
            return
        turns = [{"role": m.role, "content": m.content or ""} for m in fresh]

        # 叙事(LLM, fail-open)+ 回执行(代码逐字提取, 绝不经 LLM)
        narrative_prior = prior_summary.split("【健康记录与回执】")[0].strip()
        narrative = await _summarize(narrative_prior, turns)
        if narrative is None:
            return  # 保留旧缓存;下一轮再试
        # 时间序:旧回执在前,新提取的在后;超限保最近 N 行
        receipts = (prior_receipts + _extract_receipt_lines(
            [m["content"] for m in turns if m["role"] == "assistant"]
        ))[-_RECEIPT_LINE_MAX:]

        summary = narrative
        if receipts:
            summary += "\n【健康记录与回执】\n" + "\n".join(f"- {r}" for r in receipts)

        _cache_set(cid, {
            "folded_thru_id": last_overflow_id,
            "summary": summary[:_SUMMARY_MAX_CHARS + 600],
            "receipt_lines": receipts,
        })
        logger.info(
            "[history_compaction] conv=%s 折叠至 msg#%s(新折 %d 条)",
            cid, last_overflow_id, len(fresh),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[history_compaction] refresh 失败(fail-open): %s", e)
