"""H1-A AI 画像页支撑 API 测试: dismiss + scorecard."""
from datetime import datetime, timedelta, timezone

from app.models.action_card import ActionCard
from app.services.memory_service import (
    write_fact, get_active_facts, dismiss_fact,
)


# ─────────── dismiss_fact (soft-delete) ───────────


class TestDismissFact:
    def test_dismiss_removes_from_active(self, db):
        f = write_fact(
            db, user_id=1, tier="procedural",
            subject="用户", predicate="responds_to",
            object_value="高蛋白早餐 → morning_hrv",
        )
        assert f.id in [x.id for x in get_active_facts(db, 1)]

        ok = dismiss_fact(db, f.id, reason="not_accurate")
        assert ok

        db.refresh(f)
        assert f.superseded_at is not None
        assert f.id not in [x.id for x in get_active_facts(db, 1)]

    def test_dismiss_appends_audit_source(self, db):
        f = write_fact(
            db, user_id=1, tier="semantic",
            subject="用户 LDL", predicate="is_above", object_value="3.4",
            source={"type": "medical_exam", "id": 10, "weight": 0.9},
        )
        dismiss_fact(db, f.id, reason="wrong_reading")
        db.refresh(f)

        src_types = [s.get("type") for s in (f.sources or [])]
        assert "medical_exam" in src_types
        assert "user_dismissal" in src_types
        dismissal = next(s for s in f.sources if s.get("type") == "user_dismissal")
        assert dismissal["reason"] == "wrong_reading"
        assert dismissal["weight"] == 0.0

    def test_dismiss_already_dismissed_returns_false(self, db):
        f = write_fact(
            db, user_id=1, tier="working",
            subject="x", predicate="is_value", object_value="1",
        )
        assert dismiss_fact(db, f.id)
        # 第二次 dismiss 应被拒
        assert not dismiss_fact(db, f.id)

    def test_dismiss_nonexistent_returns_false(self, db):
        assert not dismiss_fact(db, 99999)


# ─────────── scorecard API ───────────


def _make_card(
    db, user_id=1, specialist="fuel_strategist", metric="morning_hrv",
    title="建议 A", score=80, graded_days_ago=7,
):
    now = datetime.now(timezone.utc)
    card = ActionCard(
        user_id=user_id, title=title, content="",
        creator_specialist=specialist, metric_key=metric,
        accuracy_score=score,
        graded_at=now - timedelta(days=graded_days_ago),
        check_back_date=now - timedelta(days=graded_days_ago),
    )
    db.add(card); db.commit(); db.refresh(card)
    return card


class TestScorecardLogic:
    """直接测 scorecard 查询逻辑, 不走 HTTP 层 (避免 auth 依赖)."""

    def _compute(self, db, user_id=1, days=90, top_n=3):
        # 与 personal_outcome.py 里 get_my_scorecard 等价的纯查询 (抽出便于测试)
        from sqlalchemy import func, Integer
        from app.models.action_card import ActionCard as AC

        since = datetime.now(timezone.utc) - timedelta(days=days)
        base_q = db.query(AC).filter(
            AC.user_id == user_id,
            AC.graded_at.isnot(None),
            AC.graded_at >= since,
            AC.accuracy_score.isnot(None),
        )
        overall = db.query(
            func.count(AC.id).label("total"),
            func.sum((AC.accuracy_score >= 70).cast(Integer)).label("hits"),
            func.sum((AC.accuracy_score <= 30).cast(Integer)).label("misses"),
        ).filter(
            AC.user_id == user_id,
            AC.graded_at.isnot(None),
            AC.graded_at >= since,
            AC.accuracy_score.isnot(None),
        ).first()
        return {
            "total": int(overall.total or 0),
            "hits": int(overall.hits or 0),
            "misses": int(overall.misses or 0),
            "top_hits": base_q.filter(AC.accuracy_score >= 70)
                .order_by(AC.accuracy_score.desc()).limit(top_n).all(),
            "top_misses": base_q.filter(AC.accuracy_score <= 30)
                .order_by(AC.accuracy_score.asc()).limit(top_n).all(),
        }

    def test_empty_scorecard(self, db):
        r = self._compute(db)
        assert r["total"] == 0
        assert r["hits"] == 0
        assert r["misses"] == 0

    def test_counts_correct(self, db):
        _make_card(db, score=85)
        _make_card(db, score=50)  # mid, 不计入 hit/miss
        _make_card(db, score=20)
        _make_card(db, score=75)
        r = self._compute(db)
        assert r["total"] == 4
        assert r["hits"] == 2  # 85, 75
        assert r["misses"] == 1  # 20

    def test_top_hits_ordered_descending(self, db):
        _make_card(db, score=72, title="Hit 低")
        _make_card(db, score=95, title="Hit 最高")
        _make_card(db, score=80, title="Hit 中")
        r = self._compute(db, top_n=2)
        assert [c.title for c in r["top_hits"]] == ["Hit 最高", "Hit 中"]

    def test_top_misses_ordered_ascending(self, db):
        _make_card(db, score=10, title="Miss 最低")
        _make_card(db, score=25, title="Miss 中")
        _make_card(db, score=28, title="Miss 高")
        r = self._compute(db, top_n=2)
        assert [c.title for c in r["top_misses"]] == ["Miss 最低", "Miss 中"]

    def test_window_filter(self, db):
        _make_card(db, score=90, graded_days_ago=5)
        _make_card(db, score=90, graded_days_ago=200, title="太久远")
        r = self._compute(db, days=90)
        assert r["total"] == 1
