"""Outcome → MemoryFact → Orchestrator 闭环测试.

覆盖:
1. extract_from_action_card_outcome 三段式 (responds / partially_responds / does_not_respond)
2. _build_per_specialist_track_block 拼装 (空 / 有数据 / 只本次 active specialist)
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.action_card import ActionCard
from app.models.memory_fact import MemoryFact
from app.services.memory_extractor import extract_from_action_card_outcome
from app.orchestrator.orchestrator import _build_per_specialist_track_block


def _make_card(
    db, user_id=1, specialist="fuel_strategist", metric="morning_hrv",
    title="高蛋白早餐 30g", score=80, graded_days_ago=7,
):
    now = datetime.now(timezone.utc)
    card = ActionCard(
        user_id=user_id,
        title=title,
        content="",
        creator_specialist=specialist,
        metric_key=metric,
        accuracy_score=score,
        graded_at=now - timedelta(days=graded_days_ago),
        check_back_date=now - timedelta(days=graded_days_ago),
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


# ─────────── 三段式评分 → predicate ───────────


class TestExtractOutcomeTiered:
    def test_high_score_responds_to(self, db):
        card = _make_card(db, score=85)
        fid = extract_from_action_card_outcome(db, card)
        assert fid is not None
        fact = db.query(MemoryFact).filter(MemoryFact.id == fid).one()
        assert fact.predicate == "responds_to"
        assert fact.tier == "procedural"
        assert fact.subject == "用户"
        assert "高蛋白早餐 30g" in fact.object_value
        assert "morning_hrv" in fact.object_value
        assert "fuel_strategist" in fact.tags
        assert "morning_hrv" in fact.tags
        assert fact.confidence > 0.5

    def test_low_score_does_not_respond(self, db):
        card = _make_card(db, score=20)
        fid = extract_from_action_card_outcome(db, card)
        fact = db.query(MemoryFact).filter(MemoryFact.id == fid).one()
        assert fact.predicate == "does_not_respond_to"
        assert fact.confidence > 0.5

    def test_mid_score_partially_responds(self, db):
        card = _make_card(db, score=50)
        fid = extract_from_action_card_outcome(db, card)
        fact = db.query(MemoryFact).filter(MemoryFact.id == fid).one()
        assert fact.predicate == "partially_responds_to"
        # 中段 confidence 固定 0.4 (单次样本, 方向模糊)
        assert fact.confidence == pytest.approx(0.4)

    def test_boundary_30_is_does_not_respond(self, db):
        card = _make_card(db, score=30)
        fid = extract_from_action_card_outcome(db, card)
        fact = db.query(MemoryFact).filter(MemoryFact.id == fid).one()
        assert fact.predicate == "does_not_respond_to"

    def test_boundary_70_is_responds(self, db):
        card = _make_card(db, score=70)
        fid = extract_from_action_card_outcome(db, card)
        fact = db.query(MemoryFact).filter(MemoryFact.id == fid).one()
        assert fact.predicate == "responds_to"

    def test_ungraded_card_skipped(self, db):
        card = ActionCard(
            user_id=1, title="x", content="", creator_specialist="fuel_strategist",
            metric_key="hrv", accuracy_score=None,
        )
        db.add(card)
        db.commit()
        assert extract_from_action_card_outcome(db, card) is None


class TestClinicianGatedOutcomeMemory:
    """处方/药物混杂指标不得沉淀为干预有效性结论。"""

    @pytest.mark.parametrize("metric", ["apo_b", " Apo B ", "lp-a", " LP A "])
    def test_metric_aliases_write_neutral_observation(self, db, metric):
        card = _make_card(db, metric=metric, score=85, title="减少夜宵")

        fact_id = extract_from_action_card_outcome(db, card)

        fact = db.query(MemoryFact).filter(MemoryFact.id == fact_id).one()
        assert fact.predicate == "observed_change"
        assert fact.confidence == pytest.approx(0.4)
        assert "clinician_review" in (fact.tags or [])


# ─────────── per-specialist track block 拼装 ───────────


class TestTrackBlock:
    def test_empty_returns_empty_string(self, db):
        assert _build_per_specialist_track_block(db, 1, [], days=90) == ""
        # 有 specialist 但无评分卡也返回 ""
        assert _build_per_specialist_track_block(db, 1, ["fuel_strategist"], days=90) == ""

    def test_only_active_specialists_surface(self, db):
        _make_card(db, specialist="fuel_strategist", score=85, title="建议 A")
        _make_card(db, specialist="movement_coach", score=80, title="建议 B")
        _make_card(db, specialist="recovery_coach", score=75, title="建议 C")

        # 只本次 active 的 specialist 出现
        block = _build_per_specialist_track_block(
            db, 1, ["fuel_strategist", "movement_coach"], days=90,
        )
        assert "fuel_strategist:" in block
        assert "movement_coach:" in block
        assert "recovery_coach" not in block
        assert "建议 A" in block
        assert "建议 C" not in block

    def test_high_and_low_both_shown(self, db):
        _make_card(db, specialist="fuel_strategist", score=85, title="有效干预")
        _make_card(db, specialist="fuel_strategist", score=20, title="无效干预")

        block = _build_per_specialist_track_block(db, 1, ["fuel_strategist"], days=90)
        assert "✅ 高命中" in block
        assert "❌ 低命中" in block
        assert "有效干预" in block
        assert "无效干预" in block

    def test_mid_score_excluded_from_block(self, db):
        _make_card(db, specialist="fuel_strategist", score=55, title="中段干预")
        block = _build_per_specialist_track_block(db, 1, ["fuel_strategist"], days=90)
        # 30 < score < 70 不进高低命中 (只 partially_responds_to 到 memory)
        assert block == ""

    def test_clinician_gated_metric_never_enters_hit_or_miss_track(self, db):
        _make_card(db, metric="ldl", score=85, title="降低 LDL 的建议")
        _make_card(db, metric="hrv", score=20, title="恢复建议")

        block = _build_per_specialist_track_block(db, 1, ["fuel_strategist"], days=90)

        assert "降低 LDL 的建议" not in block
        assert "恢复建议" in block

    def test_window_filter_excludes_old_cards(self, db):
        # 365 天前的 card, 90 天窗口应过滤掉
        _make_card(
            db, specialist="fuel_strategist", score=85,
            title="旧建议", graded_days_ago=365,
        )
        block = _build_per_specialist_track_block(db, 1, ["fuel_strategist"], days=90)
        assert block == ""

    def test_top_n_limits_per_specialist(self, db):
        for i in range(5):
            _make_card(
                db, specialist="fuel_strategist", score=70 + i,
                title=f"建议#{i}", graded_days_ago=i + 1,
            )
        block = _build_per_specialist_track_block(
            db, 1, ["fuel_strategist"], days=90, top_n=2,
        )
        # 5 条高命中只取 top 2
        high_lines = [line for line in block.splitlines() if "✅" in line]
        assert len(high_lines) == 2
