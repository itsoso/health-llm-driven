"""
Dream Cycle — 夜间精炼引擎 (Thoth 启发).

为什么:
  Memory 不是写进来就完了. 原始 facts 有冗余 / 相似 / 可合并,
  也可以从"跨 subject 时间共现"推断出更高阶的关联 fact.
  这些 reasoning 不适合实时做 (贵 + 用户不等), 在用户睡觉时 (02:00-04:00)
  批量跑一次, 第二天 Twin / briefing / clarify 都受益.

3 阶段 (任一阶段失败不影响其它阶段):

Phase 1  Dedupe+Merge
  扫 active facts. 同一 (user, predicate) 下用 SequenceMatcher 算 object 相似度,
  ≥ 0.85 的合并 — 保留 conf 高的, 低 conf 那条 mark superseded_by + reinforce 高的.

Phase 2  Relation Inference (时间共现分析)
  扫最近 30 天 working/episodic facts, 找"X 发生后 Y 常发生"模式:
  - 同一用户 fact_A 的 subject 相似行为, 24-48h 后 fact_B 出现 → 写 correlates_with
  - 阈值: ≥ 3 次共现 + 置信度 = 共现率
  此阶段产出的是 meta-fact (predicate='correlates_with' 等), tier='episodic'

Phase 3  Weekly Insight (一用户一 LLM call, 便宜)
  每周日跑. 把用户上周所有 active memory_facts + Twin 摘要塞 LLM,
  让它蒸 1-3 条"insight" (subject='user.insight.*') 入库, 供下周 briefing 引用.

Karpathy "design for agents" 思想: memory_facts 本身就是结构化的, LLM 直接消费.
insight 再精炼一次, 等于给 future agent 发了更紧凑的 prompt.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


# ─── Phase 1: Dedupe + Merge ──────────────────────────────────────────

# 相似度阈值 — 0.85 是 Thoth 也用的值, 再高会漏合 (同义), 再低会误合
SIMILARITY_THRESHOLD = 0.85


def _normalize_text(s: str) -> str:
    """去掉标点/空格/大小写差异."""
    import re
    return re.sub(r"\s+", "", (s or "").lower().strip("。.,，!?？ "))


def _similar(a: str, b: str) -> float:
    na, nb = _normalize_text(a), _normalize_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def dedupe_merge_loop(db: Session, user_id_filter: int | None = None) -> Dict[str, int]:
    """
    扫 active facts 合并相似的. 保留 confidence 高的 (tie-break: 最近 reinforced).

    返回 {merged: N, checked_groups: M}
    """
    from app.models.memory_fact import MemoryFact
    from app.services.memory_service import reinforce_fact, supersede_fact

    q = db.query(MemoryFact).filter(MemoryFact.superseded_at.is_(None))
    if user_id_filter is not None:
        q = q.filter(MemoryFact.user_id == user_id_filter)
    all_facts = q.all()

    # 按 (user_id, predicate) 分桶
    buckets: Dict[Tuple[int, str], List[MemoryFact]] = defaultdict(list)
    for f in all_facts:
        buckets[(f.user_id, f.predicate)].append(f)

    merged = 0
    checked = 0
    for key, facts in buckets.items():
        if len(facts) < 2:
            continue
        checked += 1
        # 简化: O(n^2), facts per bucket 小 (通常 < 20)
        seen_merged: set[int] = set()
        for i in range(len(facts)):
            a = facts[i]
            if a.id in seen_merged:
                continue
            for j in range(i + 1, len(facts)):
                b = facts[j]
                if b.id in seen_merged:
                    continue
                sim = _similar(a.object_value, b.object_value)
                if sim < SIMILARITY_THRESHOLD:
                    continue
                # 决定 keep / drop
                # 优先 conf 高; tie 时选 reinforcement_count 多的
                keep, drop = (
                    (a, b)
                    if (a.confidence > b.confidence
                        or (a.confidence == b.confidence and a.reinforcement_count >= b.reinforcement_count))
                    else (b, a)
                )
                try:
                    # drop 被 supersede 到 keep
                    supersede_fact(
                        db,
                        old_fact_id=drop.id,
                        new_fact_id=keep.id,
                        reason=f"dream_cycle.dedupe (sim={sim:.2f})",
                    )
                    reinforce_fact(
                        db,
                        keep.id,
                        source={"type": "dream_cycle.merge", "from_fact_id": drop.id},
                    )
                    merged += 1
                    seen_merged.add(drop.id)
                except Exception as e:
                    logger.warning(f"[dream.dedupe] merge 失败 drop={drop.id} keep={keep.id}: {e}")

    return {"merged": merged, "checked_groups": checked}


# ─── Phase 2: Relation Inference ──────────────────────────────────────

def _subject_root(subject: str) -> str:
    """拿 subject 的 namespace root, 例: user.sleep.pillow → user.sleep"""
    parts = subject.split(".")
    if len(parts) >= 2:
        return ".".join(parts[:2])
    return subject


def relation_inference_loop(
    db: Session, user_id_filter: int | None = None, window_days: int = 30,
) -> Dict[str, int]:
    """
    扫最近 N 天 facts, 找时间共现模式.

    简化启发式:
      对每个用户, 按 subject_root 分组, 相邻 24h 内不同 root 出现过的,
      计数共现次数. ≥3 次的生成 'correlates_with' 元事实.
    """
    from app.models.memory_fact import MemoryFact
    from app.services.memory_service import write_fact

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    q = db.query(MemoryFact).filter(
        MemoryFact.superseded_at.is_(None),
        MemoryFact.last_reinforced_at >= cutoff,
    )
    if user_id_filter is not None:
        q = q.filter(MemoryFact.user_id == user_id_filter)
    facts = q.order_by(MemoryFact.user_id, MemoryFact.last_reinforced_at).all()

    # 按用户 → 按时间 → 共现计数
    # 共现定义: user X 在 24h 窗口内, subject_root A 和 subject_root B 都有 fact
    COOCCUR_WINDOW_HOURS = 24
    MIN_COOCCUR = 3

    # 按 user_id 分桶
    by_user: Dict[int, List[MemoryFact]] = defaultdict(list)
    for f in facts:
        by_user[f.user_id].append(f)

    inferred = 0
    skipped_meta = 0
    for uid, user_facts in by_user.items():
        # 共现计数 (root_A, root_B) → count
        cooccur: Dict[Tuple[str, str], int] = defaultdict(int)
        for i in range(len(user_facts)):
            a = user_facts[i]
            root_a = _subject_root(a.subject)
            # 跳过已经是元事实的 predicate (避免循环)
            if a.predicate in ("correlates_with", "triggers", "improves", "worsens_after"):
                continue
            for j in range(i + 1, len(user_facts)):
                b = user_facts[j]
                if b.last_reinforced_at - a.last_reinforced_at > timedelta(hours=COOCCUR_WINDOW_HOURS):
                    break
                root_b = _subject_root(b.subject)
                if root_a == root_b:
                    continue  # 同域不计
                if b.predicate in ("correlates_with", "triggers", "improves", "worsens_after"):
                    skipped_meta += 1
                    continue
                pair = tuple(sorted([root_a, root_b]))
                cooccur[pair] += 1

        # 写元事实 ≥ MIN_COOCCUR
        for (ra, rb), count in cooccur.items():
            if count < MIN_COOCCUR:
                continue
            # confidence 用共现次数 / 总天数归一化
            conf = min(0.9, 0.3 + 0.1 * count)
            try:
                write_fact(
                    db,
                    user_id=uid,
                    tier="episodic",
                    subject=ra,
                    predicate="correlates_with",
                    object_value=rb,
                    confidence=conf,
                    source={
                        "type": "dream_cycle.correlation",
                        "cooccur_count": count,
                        "window_days": window_days,
                    },
                    tags=["dream_cycle", "correlation"],
                )
                inferred += 1
            except Exception as e:
                logger.warning(f"[dream.relation] write_fact 失败 {ra}↔{rb}: {e}")

    return {"inferred": inferred, "skipped_meta": skipped_meta}


# ─── Phase 3: Weekly Insight (LLM 蒸) ─────────────────────────────────

async def _llm_weekly_insight(user_id: int, facts_summary: str) -> List[str]:
    """让 LLM 从一周 facts 蒸 1-3 条 insight (简短中文陈述句)."""
    try:
        from app.services.llm.factory import get_llm_provider
        from app.services.llm.usage_tracker import set_caller
        set_caller("dream_cycle.weekly_insight", user_id=user_id)
        provider = get_llm_provider()
        prompt = f"""以下是用户本周的健康事实. 从中提炼 1-3 条 **insight** (趋势/规律/关联),
每条 ≤ 40 字, 陈述句, 不要建议和假设, 不要编造数据.
只输出 JSON 数组 (不要代码块标记):
["你本周深睡眠占比持续偏低", "..."]

事实:
{facts_summary[:2000]}
"""
        raw = await provider.chat(
            messages=[
                {"role": "system", "content": "你是数据摘要专家, 严格输出 JSON."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
            temperature=0.2,
        )
        if isinstance(raw, dict):
            raw = raw.get("content", "") or ""
        text = (raw or "").strip()
        # 剥可能的 ``` 包裹
        if "```" in text:
            parts = text.split("```")
            for p in parts:
                p = p.strip()
                if p.startswith("json"):
                    p = p[4:].strip()
                if p.startswith("["):
                    text = p
                    break
        # 抽第一个 [ ... ]
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end < 0:
            return []
        try:
            arr = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
        return [s for s in arr if isinstance(s, str) and 5 < len(s) <= 80][:3]
    except Exception as e:
        logger.warning(f"[dream.insight] user={user_id} LLM failed: {e}")
        return []


def weekly_insight_loop(db: Session, only_user_id: int | None = None) -> Dict[str, int]:
    """
    每周日 04:30 跑. 为每个 active 用户蒸 1-3 条 insight 写 semantic.
    实时 async 太复杂, 这里用 run_async 兼容 Celery 环境.
    """
    from app.models.memory_fact import MemoryFact
    from app.models.user import User
    from app.services.memory_service import write_fact
    from app.utils.async_helpers import run_async

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    user_q = db.query(User.id).filter(User.is_active == True)  # noqa: E712
    if only_user_id:
        user_q = user_q.filter(User.id == only_user_id)
    user_ids = [uid for (uid,) in user_q.all()]

    written = 0
    skipped_empty = 0
    for uid in user_ids:
        # 本周 active facts
        week_facts = db.query(MemoryFact).filter(
            MemoryFact.user_id == uid,
            MemoryFact.superseded_at.is_(None),
            MemoryFact.last_reinforced_at >= cutoff,
        ).order_by(MemoryFact.confidence.desc()).limit(30).all()
        if len(week_facts) < 5:
            skipped_empty += 1
            continue

        from app.services.memory_service import effective_memory_predicate

        summary_lines = [
            f"- {f.subject} {effective_memory_predicate(f.predicate, subject=f.subject, object_value=f.object_value, tags=f.tags or [])} {f.object_value}"
            for f in week_facts
        ]
        summary = "\n".join(summary_lines)

        insights = run_async(_llm_weekly_insight(uid, summary))
        if not insights:
            continue

        for i, ins in enumerate(insights):
            try:
                write_fact(
                    db,
                    user_id=uid,
                    tier="semantic",
                    subject=f"user.insight.weekly.{datetime.now(timezone.utc).date().isoformat()}",
                    predicate="is_value",
                    object_value=ins,
                    confidence=0.5,  # LLM 蒸的 insight 保守给 0.5
                    source={"type": "dream_cycle.weekly_insight", "index": i},
                    tags=["dream_cycle", "insight", "weekly"],
                    decay_rate=0.03,  # 慢衰减, 让 insight 能留一段时间
                )
                written += 1
            except Exception as e:
                logger.warning(f"[dream.insight] write_fact 失败 user={uid}: {e}")

    return {"written": written, "skipped_empty_users": skipped_empty}


# ─── Celery 入口 ──────────────────────────────────────────────────────

@celery_app.task(
    time_limit=1800,
    name="app.tasks.dream_cycle.run_dream_cycle",
)
def run_dream_cycle(run_weekly: bool = False, only_user_id: int | None = None):
    """
    夜间 Dream Cycle 入口.

    run_weekly=True 时额外跑 Phase 3 (Weekly Insight, 贵). 平时只跑 Phase 1/2.
    only_user_id 用于手动触发单用户 (调试).
    """
    with SessionLocal() as db:
        summary: Dict[str, Any] = {}
        # Phase 1
        try:
            summary.update({"dedupe": dedupe_merge_loop(db, only_user_id)})
        except Exception as e:
            logger.error(f"[dream.phase1] failed: {e}", exc_info=True)
            summary["dedupe"] = {"error": str(e)}
        # Phase 2
        try:
            summary.update({"relation": relation_inference_loop(db, only_user_id)})
        except Exception as e:
            logger.error(f"[dream.phase2] failed: {e}", exc_info=True)
            summary["relation"] = {"error": str(e)}
        # Phase 3 (仅周日)
        if run_weekly:
            try:
                summary.update({"insight": weekly_insight_loop(db, only_user_id)})
            except Exception as e:
                logger.error(f"[dream.phase3] failed: {e}", exc_info=True)
                summary["insight"] = {"error": str(e)}

    logger.info(f"[dream_cycle] 完成: {summary}")
    return summary
