"""test_conversation_memory_p3 —— P3-2: decay + 冲突解决 + opener 拉取."""

from datetime import datetime, timedelta, timezone
import uuid

from app.models.conversation_memory import ConversationMemory
from app.models.user import User
from app.services.conversation_memory_service import (
    DECAY_HALF_LIFE_DAYS,
    _decay_score,
    _supersede_conflicts,
    extract_memories,
    get_relevant_memories,
    get_top_memory_for_opener,
)


def _make_user(db, name="memory_user"):
    u = User(
        username=f"{name}_{uuid.uuid4().hex[:8]}",
        email=f"{name}_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name=name,
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ── decay ───────────────────────────────────────────────────────────────


def test_decay_at_zero_age_no_change():
    now = datetime.now(timezone.utc)
    assert _decay_score(1.0, now, now) == 1.0


def test_decay_at_half_life_is_half():
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=DECAY_HALF_LIFE_DAYS)
    score = _decay_score(1.0, created, now)
    assert 0.49 < score < 0.51


def test_decay_at_double_half_life_is_quarter():
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=DECAY_HALF_LIFE_DAYS * 2)
    score = _decay_score(1.0, created, now)
    assert 0.24 < score < 0.26


def test_decay_handles_naive_datetime():
    now = datetime.now(timezone.utc)
    naive = (now - timedelta(days=10)).replace(tzinfo=None)
    score = _decay_score(1.0, naive, now)
    assert 0 < score < 1.0


# ── 冲突解决 ─────────────────────────────────────────────────────────────


def test_supersede_marks_old_within_same_cluster(db):
    user = _make_user(db, "supersede1")
    old = ConversationMemory(
        user_id=user.id,
        memory_type="preference",
        content="我喜欢吃素食",
        relevance_score=1.0,
        status="active",
    )
    db.add(old)
    db.commit()

    superseded_ids = _supersede_conflicts(
        db, user.id, "preference", "我喜欢吃肉很多"
    )
    db.commit()
    db.refresh(old)
    assert old.id in superseded_ids
    assert old.status == "superseded"
    assert old.superseded_at is not None


def test_supersede_does_not_touch_different_type(db):
    user = _make_user(db, "supersede2")
    old = ConversationMemory(
        user_id=user.id,
        memory_type="allergy",
        content="我对花粉过敏",
        status="active",
    )
    db.add(old)
    db.commit()

    superseded_ids = _supersede_conflicts(
        db, user.id, "preference", "我对甜食偏好"
    )
    db.refresh(old)
    assert old.status == "active"
    assert superseded_ids == []


def test_supersede_does_not_touch_different_cluster(db):
    user = _make_user(db, "supersede3")
    old = ConversationMemory(
        user_id=user.id,
        memory_type="medical",
        content="医生让吃二甲双胍",
        status="active",
    )
    db.add(old)
    db.commit()

    # 不同前缀, 不视为同语义簇
    superseded_ids = _supersede_conflicts(
        db, user.id, "medical", "我有结石"
    )
    db.refresh(old)
    assert old.status == "active"
    assert superseded_ids == []


def test_extract_memories_supersedes_conflicting(db):
    user = _make_user(db, "extract_conflict")
    extract_memories(
        "我喜欢吃素食每天",
        "好的",
        user.id,
        None,
        db,
        use_llm_fallback=False,
    )
    extract_memories(
        "我喜欢吃肉每天三餐",
        "好的",
        user.id,
        None,
        db,
        use_llm_fallback=False,
    )

    actives = (
        db.query(ConversationMemory)
        .filter(
            ConversationMemory.user_id == user.id,
            ConversationMemory.status == "active",
            ConversationMemory.memory_type == "preference",
        )
        .all()
    )
    superseded = (
        db.query(ConversationMemory)
        .filter(
            ConversationMemory.user_id == user.id,
            ConversationMemory.status == "superseded",
        )
        .all()
    )
    assert len(actives) == 1
    assert "肉" in actives[0].content
    assert len(superseded) == 1
    assert "素食" in superseded[0].content


# ── 查询只看 active ──────────────────────────────────────────────────────


def test_get_relevant_memories_excludes_superseded(db):
    user = _make_user(db, "active_only")
    db.add(ConversationMemory(
        user_id=user.id, memory_type="medical", content="老的医嘱",
        status="superseded",
    ))
    db.add(ConversationMemory(
        user_id=user.id, memory_type="allergy", content="对青霉素过敏",
        status="active",
    ))
    db.commit()

    text = get_relevant_memories(db, user.id)
    assert "青霉素" in text
    assert "老的医嘱" not in text


def test_decayed_ordering_prefers_newer(db):
    user = _make_user(db, "ordering")
    now = datetime.now(timezone.utc)
    old = ConversationMemory(
        user_id=user.id, memory_type="fact", content="老情况老情况",
        relevance_score=1.0, status="active",
        created_at=now - timedelta(days=120),  # 已严重衰减
    )
    fresh = ConversationMemory(
        user_id=user.id, memory_type="fact", content="新情况新情况",
        relevance_score=0.6, status="active",  # 基础分低, 但年轻
        created_at=now - timedelta(days=2),
    )
    db.add_all([old, fresh])
    db.commit()

    text = get_relevant_memories(db, user.id, limit=2)
    # decay 后, fresh 0.6 ≈ 0.55, old 1.0 * 0.5^4 ≈ 0.06 → fresh 在前
    fresh_pos = text.index("新情况")
    old_pos = text.index("老情况")
    assert fresh_pos < old_pos


# ── opener 拉取 ──────────────────────────────────────────────────────────


def test_opener_prefers_priority_types(db):
    user = _make_user(db, "opener_priority")
    db.add(ConversationMemory(
        user_id=user.id, memory_type="fact", content="一般背景",
        status="active",
    ))
    db.add(ConversationMemory(
        user_id=user.id, memory_type="allergy", content="对花粉过敏",
        status="active",
    ))
    db.commit()

    top = get_top_memory_for_opener(db, user.id, k=1)
    assert len(top) == 1
    assert top[0].memory_type == "allergy"


def test_opener_falls_back_to_other_types_when_short(db):
    user = _make_user(db, "opener_fallback")
    db.add(ConversationMemory(
        user_id=user.id, memory_type="fact", content="背景一",
        status="active",
    ))
    db.add(ConversationMemory(
        user_id=user.id, memory_type="instruction", content="不能跑步",
        status="active",
    ))
    db.commit()

    top = get_top_memory_for_opener(db, user.id, k=2)
    types = {m.memory_type for m in top}
    assert "fact" in types or "instruction" in types
