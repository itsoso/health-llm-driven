"""月度复盘报告测试.

覆盖:
- _month_range / _direction
- 空数据场景
- 有 ActionCard 成绩单场景
- get_or_generate 幂等 + force 重建
- _previous_month 跨年
"""
from datetime import date, datetime, timezone

from app.services.monthly_report_service import (
    MonthlyReportService,
    _month_range,
    _direction,
)
from app.tasks.monthly_report import _previous_month
from app.models.action_card import ActionCard


class TestHelpers:
    def test_month_range(self):
        s, e = _month_range(2026, 2)
        assert s == date(2026, 2, 1) and e == date(2026, 2, 28)
        s, e = _month_range(2024, 2)  # 闰年
        assert e == date(2024, 2, 29)
        s, e = _month_range(2026, 12)
        assert e == date(2026, 12, 31)

    def test_direction(self):
        assert _direction(5.0, "up") == "improved"
        assert _direction(-5.0, "up") == "regressed"
        assert _direction(5.0, "down") == "regressed"
        assert _direction(-5.0, "down") == "improved"
        assert _direction(0.1, "up") == "basically_flat"
        assert _direction(5.0, "context") == "changed"

    def test_previous_month_cross_year(self):
        assert _previous_month(date(2026, 1, 1)) == (2025, 12)
        assert _previous_month(date(2026, 5, 15)) == (2026, 4)


def _mk_card(
    user_id, specialist, score, metric="hrv",
    graded_at=None, title="测试建议",
):
    c = ActionCard(
        user_id=user_id,
        title=title,
        content="",
        metric_key=metric,
        creator_specialist=specialist,
        accuracy_score=score,
        graded_at=graded_at or datetime.now(timezone.utc),
    )
    return c


class TestGenerateEmpty:
    def test_empty_user_returns_structure(self, db):
        svc = MonthlyReportService()
        row = svc.get_or_generate(db, user_id=1, year=2026, month=3)
        data = row.report_data
        assert data["period"]["year"] == 2026
        assert data["period"]["month"] == 3
        assert data["period"]["days_in_month"] == 31
        assert data["ai_scorecard"]["overall"]["total_graded"] == 0
        assert data["metric_trends"] == []
        assert data["key_interventions"] == []
        assert data["narrative"]  # 兜底文本
        assert isinstance(data["next_focus"], list) and data["next_focus"]


class TestScorecard:
    def test_counts_hits_and_misses(self, db):
        # 2026-03 月份的评分卡
        mar_15 = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        for sp, score in [
            ("fuel_strategist", 85),
            ("fuel_strategist", 75),
            ("movement_coach", 20),
            ("recovery_coach", 55),
        ]:
            db.add(_mk_card(1, sp, score, graded_at=mar_15))
        db.commit()

        svc = MonthlyReportService()
        row = svc.get_or_generate(db, 1, 2026, 3)
        sc = row.report_data["ai_scorecard"]
        assert sc["overall"]["total_graded"] == 4
        assert sc["overall"]["hit_count"] == 2  # 85, 75 >= 70
        assert sc["overall"]["miss_count"] == 1  # 20 <= 30
        # 按 hit_rate 降序
        assert sc["by_specialist"][0]["name"] == "fuel_strategist"
        assert sc["by_specialist"][0]["hit_rate"] == 100.0
        assert len(sc["top_hits"]) == 2
        assert sc["top_hits"][0]["score"] == 85

    def test_out_of_window_excluded(self, db):
        feb_28 = datetime(2026, 2, 28, 23, 59, tzinfo=timezone.utc)
        apr_1 = datetime(2026, 4, 1, 0, 1, tzinfo=timezone.utc)
        mar_15 = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        db.add(_mk_card(1, "fuel_strategist", 85, graded_at=feb_28))
        db.add(_mk_card(1, "fuel_strategist", 85, graded_at=apr_1))
        db.add(_mk_card(1, "fuel_strategist", 85, graded_at=mar_15))
        db.commit()

        svc = MonthlyReportService()
        row = svc.get_or_generate(db, 1, 2026, 3)
        assert row.report_data["ai_scorecard"]["overall"]["total_graded"] == 1

    def test_clinician_gated_scores_are_excluded(self, db):
        mar_15 = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        db.add(_mk_card(1, "metabolic_specialist", 95, metric="ldl", graded_at=mar_15))
        db.add(_mk_card(1, "recovery_coach", 80, metric="hrv", graded_at=mar_15))
        db.commit()

        row = MonthlyReportService().get_or_generate(db, 1, 2026, 3)
        scorecard = row.report_data["ai_scorecard"]
        assert scorecard["overall"]["total_graded"] == 1
        assert scorecard["overall"]["hit_count"] == 1
        assert len(scorecard["top_hits"]) == 1
        top_hit = scorecard["top_hits"][0]
        assert top_hit["title"] == "测试建议"
        assert top_hit["metric"] == "hrv"
        assert top_hit["score"] == 80
        assert top_hit["specialist"] == "recovery_coach"


class TestIdempotency:
    def test_get_or_generate_returns_existing(self, db):
        svc = MonthlyReportService()
        r1 = svc.get_or_generate(db, 1, 2026, 3)
        r2 = svc.get_or_generate(db, 1, 2026, 3)
        assert r1.id == r2.id
        assert r1.generated_at == r2.generated_at

    def test_force_regen_updates_timestamp(self, db):
        svc = MonthlyReportService()
        r1 = svc.get_or_generate(db, 1, 2026, 3)
        # 加一张卡再重建
        db.add(_mk_card(
            1, "fuel_strategist", 90,
            graded_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        ))
        db.commit()
        r2 = svc.get_or_generate(db, 1, 2026, 3, force=True)
        assert r2.id == r1.id
        assert r2.report_data["ai_scorecard"]["overall"]["total_graded"] == 1


class TestNarrative:
    def test_narrative_mentions_hit_rate(self, db):
        mar_15 = datetime(2026, 3, 15, tzinfo=timezone.utc)
        for _ in range(3):
            db.add(_mk_card(1, "fuel_strategist", 85, graded_at=mar_15))
        db.commit()
        svc = MonthlyReportService()
        row = svc.get_or_generate(db, 1, 2026, 3)
        narrative = row.report_data["narrative"]
        assert "命中率" in narrative
        assert "营养" in narrative  # SPECIALIST_LABEL


class TestListAndAPI:
    def test_list_ordering(self, db):
        svc = MonthlyReportService()
        svc.get_or_generate(db, 1, 2026, 1)
        svc.get_or_generate(db, 1, 2026, 3)
        svc.get_or_generate(db, 1, 2025, 12)
        rows = svc.list_reports(db, 1)
        assert [(r.year, r.month) for r in rows] == [
            (2026, 3), (2026, 1), (2025, 12),
        ]

    def test_list_scoped_per_user(self, db):
        svc = MonthlyReportService()
        svc.get_or_generate(db, 1, 2026, 3)
        svc.get_or_generate(db, 2, 2026, 3)
        assert len(svc.list_reports(db, 1)) == 1
        assert len(svc.list_reports(db, 2)) == 1
