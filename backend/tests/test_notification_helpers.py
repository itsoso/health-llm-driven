"""notification_helpers 单元测试 (拆分后独立 helper)."""
from datetime import UTC, date, datetime, timedelta

import pytest

from app.tasks.notification_helpers.briefing import (
    status_emoji, build_hit_rate_block,
)
from app.tasks.notification_helpers.doctor_weekly import (
    build_medication_adherence_block, build_journal_summary_block,
)


def _mk_user(db):
    from app.models.user import User
    u = User(name="test")
    db.add(u); db.commit()
    return u


# ─────── status_emoji ───────

class TestStatusEmoji:
    def test_none_returns_question(self):
        assert status_emoji(None, 10, 5) == "❓"

    def test_higher_is_better_good(self):
        assert status_emoji(15, 10, 5, higher_is_better=True) == "✅"

    def test_higher_is_better_warn(self):
        assert status_emoji(7, 10, 5, higher_is_better=True) == "⚠️"

    def test_higher_is_better_bad(self):
        assert status_emoji(3, 10, 5, higher_is_better=True) == "🔴"

    def test_lower_is_better_good(self):
        assert status_emoji(5, 10, 20, higher_is_better=False) == "✅"

    def test_lower_is_better_bad(self):
        assert status_emoji(30, 10, 20, higher_is_better=False) == "🔴"


# ─────── build_hit_rate_block ───────

class TestBuildHitRateBlock:
    def test_no_cards_returns_empty(self, db):
        u = _mk_user(db)
        assert build_hit_rate_block(db, u.id) == ""

    def test_pending_only_shows_banner(self, db):
        from app.models.action_card import ActionCard
        u = _mk_user(db)
        db.add(ActionCard(
            user_id=u.id, title="待复查", content="x",
            check_back_date=datetime.now(UTC) + timedelta(days=3),
            graded_at=None, creator_specialist="anomaly_detector",
        ))
        db.commit()
        result = build_hit_rate_block(db, u.id)
        assert "1 张卡片待复查" in result
        assert "Specialist 信用" in result

    def test_graded_cards_rank_and_table(self, db):
        from app.models.action_card import ActionCard
        u = _mk_user(db)
        # 两个 specialist, recovery_coach 命中率高
        for score in [85, 90, 75]:  # recovery_coach 3/3 命中
            db.add(ActionCard(
                user_id=u.id, title="t", content="x",
                creator_specialist="recovery_coach",
                accuracy_score=score, graded_at=datetime.now(UTC) - timedelta(days=5),
            ))
        for score in [40, 30]:  # fuel_strategist 0/2 命中
            db.add(ActionCard(
                user_id=u.id, title="t", content="x",
                creator_specialist="fuel_strategist",
                accuracy_score=score, graded_at=datetime.now(UTC) - timedelta(days=5),
            ))
        db.commit()
        result = build_hit_rate_block(db, u.id, days=30)
        # recovery_coach 第一
        lines = result.splitlines()
        best_line = next(l for l in lines if "本期最该信的 specialist" in l)
        assert "recovery_coach" in best_line
        assert "| recovery_coach |" in result
        assert "| fuel_strategist |" in result

    def test_clinician_gated_cards_do_not_enter_specialist_ranking(self, db):
        from app.models.action_card import ActionCard

        u = _mk_user(db)
        db.add(ActionCard(
            user_id=u.id, title="降低 LDL", content="x", metric_key="ldl",
            creator_specialist="metabolic_specialist", accuracy_score=0,
            graded_at=datetime.now(UTC) - timedelta(days=1),
        ))
        db.commit()

        assert build_hit_rate_block(db, u.id) == ""


# ─────── build_medication_adherence_block ───────

class TestMedicationAdherence:
    def test_no_templates_empty_string(self, db):
        u = _mk_user(db)
        assert build_medication_adherence_block(db, u.id, date.today() - timedelta(days=7)) == ""

    def test_low_adherence_flagged(self, db):
        from app.models.checkin import CheckinTemplate, CheckinRecord
        u = _mk_user(db)
        t = CheckinTemplate(
            user_id=u.id, name="美托洛尔", category="medicine",
            frequency="daily", is_active=True, is_archived=False,
        )
        db.add(t); db.commit()
        # 仅 3/7 次 = 43% < 70%
        for i in range(3):
            db.add(CheckinRecord(
                user_id=u.id, template_id=t.id,
                checkin_date=date.today() - timedelta(days=i),
                value=1,
            ))
        db.commit()
        result = build_medication_adherence_block(db, u.id, date.today() - timedelta(days=7))
        assert "美托洛尔" in result
        assert "⚠️" in result  # low adherence mark
        assert "3/7" in result

    def test_good_adherence_no_warn(self, db):
        from app.models.checkin import CheckinTemplate, CheckinRecord
        u = _mk_user(db)
        t = CheckinTemplate(
            user_id=u.id, name="华法林", category="medicine",
            frequency="daily", is_active=True, is_archived=False,
        )
        db.add(t); db.commit()
        for i in range(7):
            db.add(CheckinRecord(
                user_id=u.id, template_id=t.id,
                checkin_date=date.today() - timedelta(days=i),
                value=1,
            ))
        db.commit()
        result = build_medication_adherence_block(db, u.id, date.today() - timedelta(days=7))
        assert "7/7" in result
        assert "⚠️" not in result


# ─────── build_journal_summary_block ───────

class TestJournalSummary:
    def test_no_entries_empty(self, db):
        u = _mk_user(db)
        assert build_journal_summary_block(db, u.id, date.today() - timedelta(days=7)) == ""

    def test_count_by_theme(self, db):
        from app.models.clinical_journal import ClinicalJournalEntry, CaseThread
        u = _mk_user(db)
        t1 = CaseThread(user_id=u.id, theme="rhinitis", title="鼻炎")
        t2 = CaseThread(user_id=u.id, theme="sleep_quality", title="睡眠")
        db.add(t1); db.add(t2); db.commit()
        for _ in range(3):
            db.add(ClinicalJournalEntry(
                user_id=u.id, case_thread_id=t1.id,
                subjective="s", objective="o", assessment="a", plan="p",
                created_by="orchestrator",
            ))
        db.add(ClinicalJournalEntry(
            user_id=u.id, case_thread_id=t2.id,
            subjective="s", objective="o", assessment="a", plan="p",
            created_by="briefing_task",
        ))
        db.commit()
        result = build_journal_summary_block(db, u.id, date.today() - timedelta(days=7))
        assert "4 条" in result  # 总数
        assert "鼻炎×3" in result
        assert "睡眠×1" in result

    def test_priority_with_warning_symbol(self, db):
        from app.models.clinical_journal import ClinicalJournalEntry, CaseThread
        u = _mk_user(db)
        t = CaseThread(user_id=u.id, theme="rhinitis", title="鼻炎")
        db.add(t); db.commit()
        db.add(ClinicalJournalEntry(
            user_id=u.id, case_thread_id=t.id,
            subjective="s", objective="o",
            assessment="⚠️ 鼻塞持续 3 天\n其他", plan="p",
            created_by="orchestrator",
        ))
        db.commit()
        result = build_journal_summary_block(db, u.id, date.today() - timedelta(days=7))
        assert "最需关注: ⚠️ 鼻塞持续 3 天" in result
