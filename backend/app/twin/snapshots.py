"""Twin snapshot 服务 — 持久化 + 检索版本化 Twin 快照 (PRD P1, G1).

用法:
    from app.twin.builder import build_twin
    from app.twin.snapshots import snapshot_twin, latest_snapshot

    twin = build_twin(db, user_id)
    snap = snapshot_twin(db, user_id, twin, purpose="plan")   # 落库 (同状态自动去重)
    plan.twin_snapshot_id = snap.id                            # 下游引用

设计:
- twin 鸭子类型: 接受 pydantic HealthTwin (model_dump) 或已序列化 dict, 不强依赖 schema.
- content_hash 去重: 同用户最近一条快照若内容哈希相同, 直接复用 (不重复落库).
- quality_grade: 由活跃数据源数量粗分 A/B/C/D (v1 启发式, 后续接 DataQuality 细化).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.twin_snapshot import TwinSnapshot, SNAPSHOT_PURPOSES


def _serialize(twin: Any) -> dict:
    """把 twin (pydantic / dataclass / dict) 统一成 JSON-safe dict."""
    if isinstance(twin, dict):
        return twin
    if hasattr(twin, "model_dump"):  # pydantic v2
        return twin.model_dump(mode="json")
    if hasattr(twin, "dict"):  # pydantic v1
        return json.loads(json.dumps(twin.dict(), default=str, ensure_ascii=False))
    raise TypeError(f"snapshot_twin: 不支持的 twin 类型 {type(twin)!r}")


def _hash(data: dict) -> str:
    blob = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _extract_sources(data: dict) -> list:
    meta = data.get("meta") if isinstance(data, dict) else None
    if isinstance(meta, dict):
        src = meta.get("data_sources")
        if isinstance(src, list):
            return src
    return []


def _grade(sources: list) -> str:
    """v1 粗分: 按活跃数据源数量。后续接 DataQuality(新鲜度/完整度)细化。"""
    n = len(sources or [])
    if n >= 5:
        return "A"
    if n >= 3:
        return "B"
    if n >= 1:
        return "C"
    return "D"


def snapshot_twin(
    db: Session,
    user_id: int,
    twin: Any,
    *,
    purpose: str = "manual",
    dedupe: bool = True,
) -> TwinSnapshot:
    """落库一份 Twin 快照并返回。

    dedupe=True 时, 若该用户最近一条快照内容哈希相同, 直接复用 (避免重复落库)。
    注意: 复用时不修改其 purpose (快照不可变); 需要不同 purpose 绑定就传 dedupe=False。
    """
    data = _serialize(twin)
    content_hash = _hash(data)
    sources = _extract_sources(data)

    if dedupe:
        existing = (
            db.query(TwinSnapshot)
            .filter(TwinSnapshot.user_id == user_id, TwinSnapshot.content_hash == content_hash)
            .order_by(TwinSnapshot.created_at.desc())
            .first()
        )
        if existing is not None:
            return existing

    snap = TwinSnapshot(
        user_id=user_id,
        schema_version="1",
        content_hash=content_hash,
        purpose=purpose if purpose in SNAPSHOT_PURPOSES else "manual",
        quality_grade=_grade(sources),
        sources=sources,
        twin_json=data,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def latest_snapshot(db: Session, user_id: int, purpose: Optional[str] = None) -> Optional[TwinSnapshot]:
    q = db.query(TwinSnapshot).filter(TwinSnapshot.user_id == user_id)
    if purpose:
        q = q.filter(TwinSnapshot.purpose == purpose)
    return q.order_by(TwinSnapshot.created_at.desc()).first()


def get_snapshot(db: Session, snapshot_id: int) -> Optional[TwinSnapshot]:
    return db.query(TwinSnapshot).filter(TwinSnapshot.id == snapshot_id).first()
