"""
Knowledge Graph 服务 — entity / relation / 检索.

核心 API:
- upsert_entity: 创建或更新, alias 自动合并
- match_entity: 输入 query 文本 → 找到对应 entity (canonical 或 alias 匹配)
- create_relation: 创建有向边, 同三元组已存在则 evidence_count++
- get_relations: 按 (subject_id, predicate?) 取边
- expand_neighborhood: 2-hop 图遍历 (LLM Wiki v2 graph traversal)
- mention_to_entities: 给定一段文字, 抽出提到的所有 entity

不引入额外 LLM 调用; entity 抽取由 specialist findings / extractor 喂.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.health_kg import (
    EntityRelation, HealthEntity, ENTITY_TYPES, RELATION_TYPES,
)

logger = logging.getLogger(__name__)


def upsert_entity(
    db: Session,
    *,
    user_id: int,
    type: str,
    canonical_name: str,
    aliases: Optional[List[str]] = None,
    attributes: Optional[Dict[str, Any]] = None,
    confidence: float = 0.7,
    source: Optional[Dict[str, Any]] = None,
) -> Optional[HealthEntity]:
    """创建/更新 entity. canonical_name + type 唯一."""
    if type not in ENTITY_TYPES:
        logger.warning(f"[kg] 未知 entity type: {type}")
        return None
    if not canonical_name:
        return None

    try:
        existing = db.query(HealthEntity).filter(
            HealthEntity.user_id == user_id,
            HealthEntity.type == type,
            HealthEntity.canonical_name == canonical_name,
        ).first()

        if existing:
            # 合并 aliases (去重)
            if aliases:
                merged = list({*(existing.aliases or []), *aliases})
                existing.aliases = merged
            # 合并 attributes (新覆盖旧)
            if attributes:
                attrs = dict(existing.attributes or {})
                attrs.update(attributes)
                existing.attributes = attrs
            # 添加 source
            if source:
                srcs = list(existing.sources or [])
                srcs.append({**source, "added_at": datetime.now(timezone.utc).isoformat()})
                existing.sources = srcs
            # confidence 取较高
            existing.confidence = max(existing.confidence, confidence)
            db.commit()
            db.refresh(existing)
            return existing

        ent = HealthEntity(
            user_id=user_id,
            type=type,
            canonical_name=canonical_name[:200],
            aliases=aliases or [],
            attributes=attributes or {},
            confidence=confidence,
            sources=[source] if source else [],
        )
        db.add(ent)
        db.commit()
        db.refresh(ent)
        logger.info(f"[kg] 新 entity #{ent.id} {type}: {canonical_name}")
        return ent
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[kg] upsert_entity 失败: {e}")
        return None


def match_entity(
    db: Session, user_id: int, mention: str,
    *, type: Optional[str] = None,
) -> Optional[HealthEntity]:
    """在用户的 entity 库中查找 mention 对应的 entity.

    优先级: canonical_name 精确 → canonical_name ilike → aliases 包含.
    """
    if not mention:
        return None
    mention_clean = mention.strip()

    q = db.query(HealthEntity).filter(
        HealthEntity.user_id == user_id,
        HealthEntity.is_active == True,  # noqa: E712
    )
    if type:
        q = q.filter(HealthEntity.type == type)

    # 1) 精确
    exact = q.filter(HealthEntity.canonical_name == mention_clean).first()
    if exact:
        return exact

    # 2) ilike canonical
    ilk = q.filter(HealthEntity.canonical_name.ilike(f"%{mention_clean}%")).first()
    if ilk:
        return ilk

    # 3) aliases 包含 — JSON 操作不能依赖 PG-only 语法 (跨 SQLite 兼容)
    candidates = q.all()
    for c in candidates:
        for a in (c.aliases or []):
            if a == mention_clean or mention_clean in a or a in mention_clean:
                return c
    return None


def create_relation(
    db: Session,
    *,
    user_id: int,
    subject_id: int,
    predicate: str,
    object_id: int,
    confidence: float = 0.5,
    source: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
) -> Optional[EntityRelation]:
    """创建/增强 relation. 同三元组已存在则 evidence_count++."""
    if predicate not in RELATION_TYPES:
        logger.warning(f"[kg] 未知 predicate: {predicate}")
        return None
    if subject_id == object_id:
        logger.warning(f"[kg] 自环关系拒绝: {subject_id}")
        return None

    try:
        existing = db.query(EntityRelation).filter(
            EntityRelation.user_id == user_id,
            EntityRelation.subject_id == subject_id,
            EntityRelation.predicate == predicate,
            EntityRelation.object_id == object_id,
        ).first()

        if existing:
            existing.evidence_count = (existing.evidence_count or 0) + 1
            existing.confidence = min(1.0, max(existing.confidence, confidence) + 0.05)
            if source:
                srcs = list(existing.sources or [])
                srcs.append({**source, "added_at": datetime.now(timezone.utc).isoformat()})
                existing.sources = srcs
            db.commit()
            db.refresh(existing)
            return existing

        rel = EntityRelation(
            user_id=user_id,
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            confidence=confidence,
            evidence_count=1,
            sources=[source] if source else [],
            notes=(notes or None),
        )
        db.add(rel)
        db.commit()
        db.refresh(rel)
        return rel
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[kg] create_relation 失败: {e}")
        return None


def get_relations(
    db: Session,
    *,
    user_id: int,
    subject_id: Optional[int] = None,
    object_id: Optional[int] = None,
    predicate: Optional[str] = None,
    limit: int = 100,
) -> List[EntityRelation]:
    """灵活查询 relations."""
    q = db.query(EntityRelation).filter(
        EntityRelation.user_id == user_id,
        EntityRelation.is_active == True,  # noqa: E712
    )
    if subject_id:
        q = q.filter(EntityRelation.subject_id == subject_id)
    if object_id:
        q = q.filter(EntityRelation.object_id == object_id)
    if predicate:
        q = q.filter(EntityRelation.predicate == predicate)
    return q.order_by(EntityRelation.confidence.desc()).limit(limit).all()


def expand_neighborhood(
    db: Session, user_id: int, entity_id: int,
    *, hops: int = 2, max_per_hop: int = 10,
) -> List[Dict[str, Any]]:
    """2-hop 图遍历: 给一个 entity, 返回它周围所有相关 entities + edges.

    返回:
      [
        {"hop": 1, "entity": {...}, "via_predicate": "treats", "direction": "out"},
        {"hop": 2, "entity": {...}, "via_predicate": "interacts_with", "direction": "in"},
        ...
      ]
    """
    visited: Set[int] = {entity_id}
    results: List[Dict[str, Any]] = []
    frontier: Set[int] = {entity_id}

    for hop in range(1, hops + 1):
        next_frontier: Set[int] = set()
        if not frontier:
            break

        # OUT edges (subject in frontier)
        out_rels = db.query(EntityRelation).filter(
            EntityRelation.user_id == user_id,
            EntityRelation.is_active == True,  # noqa: E712
            EntityRelation.subject_id.in_(list(frontier)),
        ).order_by(EntityRelation.confidence.desc()).limit(max_per_hop * 5).all()

        # IN edges (object in frontier)
        in_rels = db.query(EntityRelation).filter(
            EntityRelation.user_id == user_id,
            EntityRelation.is_active == True,  # noqa: E712
            EntityRelation.object_id.in_(list(frontier)),
        ).order_by(EntityRelation.confidence.desc()).limit(max_per_hop * 5).all()

        for rel in out_rels:
            target = rel.object_id
            if target in visited:
                continue
            ent = rel.object
            if ent and ent.is_active:
                results.append({
                    "hop": hop,
                    "entity_id": ent.id,
                    "entity_type": ent.type,
                    "entity_name": ent.canonical_name,
                    "via_predicate": rel.predicate,
                    "direction": "out",
                    "confidence": rel.confidence,
                    "evidence_count": rel.evidence_count,
                })
                next_frontier.add(target)
                visited.add(target)
            if len([r for r in results if r["hop"] == hop]) >= max_per_hop:
                break

        for rel in in_rels:
            target = rel.subject_id
            if target in visited:
                continue
            ent = rel.subject
            if ent and ent.is_active:
                results.append({
                    "hop": hop,
                    "entity_id": ent.id,
                    "entity_type": ent.type,
                    "entity_name": ent.canonical_name,
                    "via_predicate": rel.predicate,
                    "direction": "in",
                    "confidence": rel.confidence,
                    "evidence_count": rel.evidence_count,
                })
                next_frontier.add(target)
                visited.add(target)
            if len([r for r in results if r["hop"] == hop]) >= max_per_hop:
                break

        frontier = next_frontier

    return results


def mention_to_entities(
    db: Session, user_id: int, text: str,
    *, max_entities: int = 5,
) -> List[HealthEntity]:
    """从一段文字抽出可能的 entity.

    简单实现: 拉取该 user 所有 active entities, 看 canonical_name / aliases
    是否在 text 中出现. 适合短查询 (用户当前问题). 长文本应分句.
    """
    if not text:
        return []

    all_entities = db.query(HealthEntity).filter(
        HealthEntity.user_id == user_id,
        HealthEntity.is_active == True,  # noqa: E712
    ).all()

    matched: List[Tuple[HealthEntity, int]] = []
    for ent in all_entities:
        terms = [ent.canonical_name] + list(ent.aliases or [])
        for term in terms:
            if term and term in text:
                # 越长的匹配越优先 (避免子串误判)
                matched.append((ent, len(term)))
                break

    matched.sort(key=lambda x: x[1], reverse=True)
    seen: Set[int] = set()
    out: List[HealthEntity] = []
    for ent, _ in matched:
        if ent.id in seen:
            continue
        seen.add(ent.id)
        out.append(ent)
        if len(out) >= max_entities:
            break
    return out


def render_neighborhood_for_prompt(
    db: Session, user_id: int, query_text: str,
    *, max_seeds: int = 3, hops: int = 2, max_per_hop: int = 5,
) -> str:
    """LLM prompt 注入: 给定 query 文本, 找出 mention 的 entities,
    展开 2-hop 邻域, 拼成 markdown.
    """
    seeds = mention_to_entities(db, user_id, query_text, max_entities=max_seeds)
    if not seeds:
        return ""

    lines = ["## 知识图谱 (从你的问题展开 2-hop)"]
    for seed in seeds:
        nbrs = expand_neighborhood(db, user_id, seed.id,
                                   hops=hops, max_per_hop=max_per_hop)
        if not nbrs:
            continue
        lines.append(f"\n### 🎯 {seed.canonical_name} ({seed.type})")
        for n in nbrs[:max_per_hop * hops]:
            arrow = "→" if n["direction"] == "out" else "←"
            lines.append(
                f"  hop{n['hop']} {arrow} **{n['via_predicate']}** "
                f"{n['entity_name']} ({n['entity_type']}, "
                f"conf={n['confidence']:.2f})"
            )
    if len(lines) == 1:
        return ""  # 没找到任何邻域
    return "\n".join(lines)
