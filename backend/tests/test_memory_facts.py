"""Memory Fact (LLM Wiki v2) 测试."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.memory_fact import MemoryFact
from app.services.memory_service import (
    write_fact, reinforce_fact, supersede_fact, get_active_facts,
    decay_all_facts, detect_contradictions, render_facts_for_prompt,
    dismiss_fact,
)


# ─────────── write_fact 基础 ───────────


class TestWriteFact:
    def test_creates_fact(self, db):
        f = write_fact(
            db, user_id=1, tier="semantic",
            subject="用户 LDL", predicate="is_above",
            object_value="3.4", object_unit="mmol/L",
            confidence=0.8,
            source={"type": "medical_exam", "id": 5},
            tags=["lipid"],
        )
        assert f is not None
        assert f.subject == "用户 LDL"
        assert f.predicate == "is_above"
        assert f.object_value == "3.4"
        assert f.confidence == 0.8
        assert "medical_exam" in str(f.sources)
        assert "lipid" in f.tags

    def test_invalid_tier_rejected(self, db):
        f = write_fact(db, user_id=1, tier="bogus",
                      subject="x", predicate="y", object_value="z")
        assert f is None

    def test_empty_fields_rejected(self, db):
        assert write_fact(db, user_id=1, tier="working",
                         subject="", predicate="x", object_value="y") is None
        assert write_fact(db, user_id=1, tier="working",
                         subject="x", predicate="", object_value="y") is None

    def test_duplicate_triggers_reinforce(self, db):
        f1 = write_fact(db, user_id=1, tier="semantic",
                       subject="A", predicate="is_value", object_value="42",
                       confidence=0.5,
                       source={"type": "manual", "id": "1"})
        assert f1 is not None
        c1 = f1.reinforcement_count
        # 同三元组 → reinforce
        f2 = write_fact(db, user_id=1, tier="semantic",
                       subject="A", predicate="is_value", object_value="42",
                       confidence=0.6,
                       source={"type": "manual", "id": "2"})
        assert f2.id == f1.id  # 同一条
        assert f2.reinforcement_count == c1 + 1
        assert f2.confidence > 0.5  # 提升
        assert len(f2.sources) == 2


# ─────────── reinforce / supersede ───────────


class TestReinforce:
    def test_boosts_confidence_and_count(self, db):
        f = write_fact(db, user_id=1, tier="semantic",
                      subject="x", predicate="equals", object_value="y",
                      confidence=0.5)
        original = f.confidence

        updated = reinforce_fact(db, f.id,
                                source={"type": "specialist_finding"})
        assert updated.confidence > original
        assert updated.reinforcement_count == 2
        assert len(updated.sources) == 1

    def test_caps_at_1(self, db):
        f = write_fact(db, user_id=1, tier="semantic",
                      subject="x", predicate="equals", object_value="y",
                      confidence=0.95)
        updated = reinforce_fact(db, f.id, confidence_boost=0.5)
        assert updated.confidence == 1.0


class TestSupersede:
    def test_creates_link(self, db):
        old = write_fact(db, user_id=1, tier="semantic",
                        subject="x", predicate="is_value", object_value="80")
        new = write_fact(db, user_id=1, tier="semantic",
                        subject="x", predicate="is_value", object_value="75")
        # 注意: 写两条同三元组会 reinforce. 这里 object_value 不同, 所以是两条
        assert old.id != new.id

        ok = supersede_fact(db, old.id, new.id)
        assert ok

        db.refresh(old)
        db.refresh(new)
        assert old.superseded_at is not None
        assert old.superseded_by_id == new.id
        assert new.supersedes_id == old.id

    def test_active_filter_excludes_superseded(self, db):
        old = write_fact(db, user_id=1, tier="semantic",
                        subject="x", predicate="is_value", object_value="80")
        new = write_fact(db, user_id=1, tier="semantic",
                        subject="x", predicate="is_value", object_value="75")
        supersede_fact(db, old.id, new.id)

        active = get_active_facts(db, 1)
        ids = [f.id for f in active]
        assert new.id in ids
        assert old.id not in ids


# ─────────── 遗忘曲线 ───────────


class TestDecay:
    def test_effective_confidence_decays(self, db):
        f = write_fact(db, user_id=1, tier="working",
                      subject="x", predicate="equals", object_value="y",
                      confidence=0.9, decay_rate=0.1)
        # 模拟 30 天前 reinforced
        f.last_reinforced_at = datetime.now(timezone.utc) - timedelta(days=30)
        db.commit()
        # exp(-0.1 × 30) ≈ 0.0498, 0.9 × 0.0498 ≈ 0.045 — 但 floor=0.05
        eff = f.effective_confidence
        assert eff < 0.1
        assert eff >= 0.05  # floor

    def test_no_decay_for_fixed_facts(self, db):
        f = write_fact(db, user_id=1, tier="semantic",
                      subject="基因", predicate="has_genotype",
                      object_value="MTHFR rs1801133 CT",
                      decay_rate=0.0)
        f.last_reinforced_at = datetime.now(timezone.utc) - timedelta(days=365)
        db.commit()
        assert f.effective_confidence == 0.5  # 保持原值

    def test_reinforcement_count_raises_floor(self, db):
        f = write_fact(db, user_id=1, tier="working",
                      subject="x", predicate="equals", object_value="y",
                      confidence=0.6, decay_rate=1.0)  # 超快衰减
        # reinforce 10 次 → floor = min(0.4, 0.5) = 0.4
        for _ in range(9):
            reinforce_fact(db, f.id)
        db.refresh(f)
        f.last_reinforced_at = datetime.now(timezone.utc) - timedelta(days=365)
        db.commit()
        assert f.effective_confidence >= 0.4


class TestDecayAll:
    def test_prunes_low_confidence_singletons(self, db):
        # 单次出现 + 低 confidence → 归档
        f = write_fact(db, user_id=1, tier="working",
                      subject="x", predicate="equals", object_value="y",
                      confidence=0.1, decay_rate=0.5)
        # 推到很久前
        f.last_reinforced_at = datetime.now(timezone.utc) - timedelta(days=30)
        db.commit()

        result = decay_all_facts(db, user_id=1)
        assert result["pruned"] >= 1

        db.refresh(f)
        assert f.superseded_at is not None  # 自动归档


# ─────────── 矛盾检测 ───────────


class TestContradictions:
    def test_above_below_conflict(self, db):
        write_fact(db, user_id=1, tier="semantic",
                  subject="LDL", predicate="is_above", object_value="3.4")

        rows = detect_contradictions(
            db, user_id=1,
            subject="LDL", predicate="is_below", object_value="3.0",
        )
        assert len(rows) == 1
        assert rows[0].predicate == "is_above"

    def test_responds_vs_does_not_respond(self, db):
        write_fact(db, user_id=1, tier="procedural",
                  subject="用户对鱼油", predicate="responds_to",
                  object_value="降 TG 显著")

        rows = detect_contradictions(
            db, user_id=1,
            subject="用户对鱼油", predicate="does_not_respond_to",
            object_value="无效",
        )
        assert len(rows) == 1

    def test_same_predicate_same_value_not_conflict(self, db):
        write_fact(db, user_id=1, tier="semantic",
                  subject="LDL", predicate="is_above", object_value="3.4")
        rows = detect_contradictions(
            db, user_id=1,
            subject="LDL", predicate="is_above", object_value="3.4",
        )
        assert len(rows) == 0  # 完全相同, 不矛盾


# ─────────── render ───────────


class TestRender:
    def test_empty_returns_empty(self):
        assert render_facts_for_prompt([]) == ""

    def test_renders_confidence_emoji(self, db):
        f1 = write_fact(db, user_id=1, tier="semantic",
                       subject="A", predicate="equals", object_value="1",
                       confidence=0.9, decay_rate=0.0)
        f2 = write_fact(db, user_id=1, tier="semantic",
                       subject="B", predicate="equals", object_value="2",
                       confidence=0.5, decay_rate=0.0)
        f3 = write_fact(db, user_id=1, tier="semantic",
                       subject="C", predicate="equals", object_value="3",
                       confidence=0.2, decay_rate=0.0)
        out = render_facts_for_prompt([f1, f2, f3])
        assert "🟢" in out  # high
        assert "🟡" in out  # medium
        assert "⚪" in out  # low
        # 最高 confidence 应该排第一
        assert out.index("A") < out.index("B") < out.index("C")

    def test_historical_gated_effect_is_rendered_as_neutral_observation(self, db):
        fact = write_fact(
            db, user_id=1, tier="procedural", subject="用户",
            predicate="responds_to", object_value="减少夜宵 → LP A",
            confidence=0.8, tags=["lp-a"],
        )

        out = render_facts_for_prompt([fact])

        assert "**observed_change**" in out
        assert "**responds_to**" not in out

    def test_subject_only_gated_effect_is_neutral_and_confidence_capped(self, db):
        fact = write_fact(
            db, user_id=1, tier="procedural", subject="用户 LP A",
            predicate="responds_to", object_value="减少夜宵",
            confidence=0.8,
        )

        out = render_facts_for_prompt([fact])

        assert "**observed_change**" in out
        assert "conf=0.40" in out

    def test_non_gated_effect_keeps_its_predicate_and_confidence(self, db):
        fact = write_fact(
            db, user_id=1, tier="procedural", subject="用户",
            predicate="responds_to", object_value="早睡 → HRV",
            confidence=0.8, tags=["hrv"],
        )

        out = render_facts_for_prompt([fact])

        assert "**responds_to**" in out
        assert "conf=0.80" in out

    def test_api_projection_neutralizes_subject_only_gated_effect(self, db):
        from app.api.memory_facts import _to_dict

        fact = write_fact(
            db, user_id=1, tier="procedural", subject="用户 Apo B",
            predicate="responds_to", object_value="减少夜宵", confidence=0.8,
        )

        payload = _to_dict(fact)

        assert payload["predicate"] == "observed_change"
        assert payload["confidence"] == 0.4
        assert payload["effective_confidence"] == 0.4
