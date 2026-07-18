"""Memory Lifecycle 测试 — decay + crystallization + stale entity."""
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.memory_lifecycle import (
    _crystallize_loop, _stale_entity_loop,
)
from app.models.memory_fact import MemoryFact
from app.models.health_kg import HealthEntity


# ─────────── crystallization ───────────


class TestCrystallize:
    def test_working_promoted_by_count(self, db):
        from app.services.memory_service import write_fact, reinforce_fact
        f = write_fact(db, user_id=1, tier="working",
                       subject="A", predicate="equals", object_value="1",
                       confidence=0.5)
        # 强行 reinforce 3 次 (超过阈值)
        reinforce_fact(db, f.id)
        reinforce_fact(db, f.id)
        db.refresh(f)
        assert f.reinforcement_count >= 3

        result = _crystallize_loop(db)
        assert result["working_to_episodic"] >= 1

        db.refresh(f)
        assert f.tier == "episodic"

    def test_working_promoted_by_confidence(self, db):
        from app.services.memory_service import write_fact
        f = write_fact(db, user_id=1, tier="working",
                       subject="A", predicate="equals", object_value="1",
                       confidence=0.85)  # 高 conf 直接升

        result = _crystallize_loop(db)
        assert result["working_to_episodic"] >= 1

        db.refresh(f)
        assert f.tier == "episodic"

    def test_episodic_promoted_to_semantic(self, db):
        from app.services.memory_service import write_fact, reinforce_fact
        f = write_fact(db, user_id=1, tier="episodic",
                       subject="A", predicate="equals", object_value="1",
                       confidence=0.7)
        for _ in range(4):
            reinforce_fact(db, f.id)
        db.refresh(f)
        assert f.reinforcement_count >= 5

        result = _crystallize_loop(db)
        assert result["episodic_to_semantic"] >= 1

        db.refresh(f)
        assert f.tier == "semantic"

    def test_low_count_low_conf_no_promote(self, db):
        from app.services.memory_service import write_fact
        f = write_fact(db, user_id=1, tier="working",
                       subject="A", predicate="equals", object_value="1",
                       confidence=0.5)
        # 单次 + 中 conf → 不升

        result = _crystallize_loop(db)
        assert result["working_to_episodic"] == 0

        db.refresh(f)
        assert f.tier == "working"

    def test_clinician_review_fact_never_crystallizes(self, db):
        f = MemoryFact(
            user_id=1, tier="working", subject="用户 TSH", predicate="observed_change",
            object_value="下降", confidence=0.95, reinforcement_count=6,
            tags=["clinician_review"],
        )
        db.add(f)
        db.commit()

        result = _crystallize_loop(db)

        assert result["working_to_episodic"] == 0
        db.refresh(f)
        assert f.tier == "working"


# ─────────── stale entity ───────────


class TestStaleEntity:
    def test_recent_entity_kept(self, db):
        from app.services.kg_service import upsert_entity
        e = upsert_entity(db, user_id=1, type="medication",
                          canonical_name="Recent",
                          source={"type": "manual"})
        # 默认 created_at = now → 不算 stale
        deactivated = _stale_entity_loop(db, stale_days=90)

        db.refresh(e)
        assert e.is_active is True

    def test_old_entity_deactivated(self, db):
        from app.services.kg_service import upsert_entity
        e = upsert_entity(db, user_id=1, type="medication",
                          canonical_name="Old",
                          source={"type": "manual"})
        # 把 sources 时间手动改为 100 天前
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        e.sources = [{"type": "manual", "added_at": old_ts}]
        # created_at 也推到 100 天前 (sources 是主判据但万一 fallback 走 created_at)
        e.created_at = datetime.now(timezone.utc) - timedelta(days=100)
        db.commit()

        deactivated = _stale_entity_loop(db, stale_days=90)
        assert deactivated >= 1

        db.refresh(e)
        assert e.is_active is False
