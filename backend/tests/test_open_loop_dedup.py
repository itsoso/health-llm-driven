"""Open-Loop dedup + history + feedback 单测."""
from datetime import datetime, timedelta, timezone

from app.models.open_loop_history import OpenLoopHistory
from app.tasks.open_loop_manager import (
    OpenLoop,
    _is_recently_pushed_or_snoozed,
    _record_history,
)


def _make_loop(**kw):
    defaults = dict(
        user_id=1,
        kind="lab_overdue",
        title="t",
        body="b",
        score=70,
        signal_key="LDL",
    )
    defaults.update(kw)
    return OpenLoop(**defaults)


class TestDedup:
    def test_first_push_not_deduped(self, db):
        loop = _make_loop()
        assert _is_recently_pushed_or_snoozed(db, 1, loop) is False

    def test_recent_push_deduped(self, db):
        loop = _make_loop()
        _record_history(db, 1, loop, ok=True)
        assert _is_recently_pushed_or_snoozed(db, 1, loop) is True

    def test_failed_delivery_not_dedup(self, db):
        """delivery_ok=0 (失败) 不应阻止下次重试."""
        loop = _make_loop()
        _record_history(db, 1, loop, ok=False, error="x")
        assert _is_recently_pushed_or_snoozed(db, 1, loop) is False

    def test_different_signal_key_not_deduped(self, db):
        _record_history(db, 1, _make_loop(signal_key="LDL"), ok=True)
        # HBA1C 是不同 signal, 应允许
        assert _is_recently_pushed_or_snoozed(db, 1, _make_loop(signal_key="HBA1C")) is False

    def test_different_kind_not_deduped(self, db):
        _record_history(db, 1, _make_loop(kind="lab_overdue"), ok=True)
        # action_card_due 是另一种 kind
        assert _is_recently_pushed_or_snoozed(db, 1, _make_loop(kind="action_card_due")) is False

    def test_different_user_not_deduped(self, db):
        _record_history(db, 1, _make_loop(), ok=True)
        # user 2 是新人
        assert _is_recently_pushed_or_snoozed(db, 2, _make_loop(user_id=2)) is False

    def test_8_days_old_not_deduped(self, db):
        loop = _make_loop()
        _record_history(db, 1, loop, ok=True)
        # 手动把 sent_at 改到 8 天前
        row = db.query(OpenLoopHistory).filter(
            OpenLoopHistory.user_id == 1).first()
        row.sent_at = datetime.now(timezone.utc) - timedelta(days=8)
        db.commit()
        assert _is_recently_pushed_or_snoozed(db, 1, loop) is False

    def test_snoozed_blocks_push(self, db):
        loop = _make_loop()
        _record_history(db, 1, loop, ok=True)
        row = db.query(OpenLoopHistory).filter(
            OpenLoopHistory.user_id == 1).first()
        row.snoozed_until = datetime.now(timezone.utc) + timedelta(days=10)
        db.commit()
        assert _is_recently_pushed_or_snoozed(db, 1, loop) is True

    def test_snooze_expired_allows_push(self, db):
        loop = _make_loop()
        _record_history(db, 1, loop, ok=True)
        row = db.query(OpenLoopHistory).filter(
            OpenLoopHistory.user_id == 1).first()
        # snooze 已过期, 但 sent_at 仍在 7 天内 → 仍 dedup
        row.snoozed_until = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
        # 仍 dedup 因为 7 天内已推过
        assert _is_recently_pushed_or_snoozed(db, 1, loop) is True

        # 把 sent_at 也推到 8 天前
        row.sent_at = datetime.now(timezone.utc) - timedelta(days=8)
        db.commit()
        assert _is_recently_pushed_or_snoozed(db, 1, loop) is False


class TestRecordHistory:
    def test_writes_full_row(self, db):
        loop = _make_loop(score=85, body="LDL 6 月没复查")
        _record_history(db, 1, loop, ok=True)
        row = db.query(OpenLoopHistory).filter(
            OpenLoopHistory.user_id == 1).first()
        assert row.kind == "lab_overdue"
        assert row.signal_key == "LDL"
        assert row.score == 85
        assert row.body == "LDL 6 月没复查"
        assert row.delivery_ok == 1

    def test_writes_failure(self, db):
        _record_history(db, 1, _make_loop(), ok=False, error="bad token")
        row = db.query(OpenLoopHistory).filter(
            OpenLoopHistory.user_id == 1).first()
        assert row.delivery_ok == 0
        assert "bad token" in (row.delivery_error or "")
