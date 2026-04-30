"""Trust Loop Judgment Feedback API 单元测试."""
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.api.judgment_feedback import (
    JudgmentFeedbackRequest, _apply_side_effects,
    get_recent_negative_feedback,
)
from app.models.user_judgment_feedback import (
    FEEDBACK_VALUES, TARGET_TYPES, UserJudgmentFeedback,
)


def _mk_user(db):
    from app.models.user import User
    u = User(name="test")
    db.add(u); db.commit()
    return u


class TestConstants:
    def test_feedback_values_set(self):
        assert FEEDBACK_VALUES == {"helpful", "not_helpful", "irrelevant", "already_knew"}

    def test_target_types_set(self):
        assert "insight" in TARGET_TYPES
        assert "anomaly_alert" in TARGET_TYPES
        assert "llm_arbitration" in TARGET_TYPES


class TestModel:
    def test_create_basic(self, db):
        u = _mk_user(db)
        row = UserJudgmentFeedback(
            user_id=u.id, target_type="insight", target_id=42,
            feedback="not_helpful", note="不对", snapshot="test",
        )
        db.add(row); db.commit()
        assert row.id is not None
        assert row.target_type == "insight"


class TestSideEffects:
    def test_insight_feedback_syncs_to_daily_insight(self, db):
        """反馈 insight → 同步更新 DailyInsight.user_feedback."""
        from app.models.daily_insight import DailyInsight
        from datetime import date
        u = _mk_user(db)
        ins = DailyInsight(
            user_id=u.id, insight_date=date.today(),
            kind="test", rule_id="t", title="t", body="b",
            confidence=0.5, severity="info",
        )
        db.add(ins); db.commit()
        req = JudgmentFeedbackRequest(
            target_type="insight", target_id=ins.id,
            feedback="helpful",
        )
        _apply_side_effects(db, u.id, req)
        db.commit()
        db.refresh(ins)
        assert ins.user_feedback == "helpful"
        assert ins.feedback_at is not None

    def test_anomaly_not_helpful_suppresses(self, db):
        """反馈 anomaly_alert not_helpful → is_suppressed=True (告警降频)."""
        from app.models.anomaly_alert import AnomalyAlert
        from datetime import date
        u = _mk_user(db)
        a = AnomalyAlert(
            user_id=u.id, alert_type="hrv_drop", severity="warning",
            metric_name="hrv", current_value=40, baseline_value=55,
            detection_date=date.today(), message="test",
            is_suppressed=False,
        )
        db.add(a); db.commit()
        req = JudgmentFeedbackRequest(
            target_type="anomaly_alert", target_id=a.id, feedback="not_helpful",
        )
        _apply_side_effects(db, u.id, req)
        db.commit()
        db.refresh(a)
        assert a.is_suppressed is True

    def test_anomaly_helpful_does_not_suppress(self, db):
        """反馈 anomaly_alert helpful → 不标记 suppress."""
        from app.models.anomaly_alert import AnomalyAlert
        from datetime import date
        u = _mk_user(db)
        a = AnomalyAlert(
            user_id=u.id, alert_type="hrv_drop", severity="warning",
            metric_name="hrv", detection_date=date.today(), message="t",
            is_suppressed=False,
        )
        db.add(a); db.commit()
        req = JudgmentFeedbackRequest(
            target_type="anomaly_alert", target_id=a.id, feedback="helpful",
        )
        _apply_side_effects(db, u.id, req)
        db.commit()
        db.refresh(a)
        assert a.is_suppressed is False

    def test_nonexistent_target_fail_soft(self, db):
        """target_id 不存在, 不应 throw (fail-soft)."""
        u = _mk_user(db)
        req = JudgmentFeedbackRequest(
            target_type="insight", target_id=99999, feedback="helpful",
        )
        # 不应 raise
        _apply_side_effects(db, u.id, req)


class TestGetRecentNegative:
    def test_empty_returns_empty(self, db):
        u = _mk_user(db)
        assert get_recent_negative_feedback(db, u.id) == []

    def test_returns_only_negative(self, db):
        u = _mk_user(db)
        # 3 条: 1 helpful + 1 not_helpful + 1 irrelevant
        for i, fb in enumerate(["helpful", "not_helpful", "irrelevant"]):
            db.add(UserJudgmentFeedback(
                user_id=u.id, target_type="insight", target_id=i,
                feedback=fb, snapshot=f"s{i}",
            ))
        db.commit()
        result = get_recent_negative_feedback(db, u.id)
        assert len(result) == 2
        feedbacks = {r["feedback"] for r in result}
        assert feedbacks == {"not_helpful", "irrelevant"}

    def test_respects_days_window(self, db):
        u = _mk_user(db)
        # 一条 60 天前, 一条今天
        old = UserJudgmentFeedback(
            user_id=u.id, target_type="insight", target_id=1,
            feedback="not_helpful", snapshot="old",
        )
        db.add(old); db.commit()
        # 手动改 created_at
        old.created_at = datetime.now(UTC) - timedelta(days=60)
        db.commit()

        db.add(UserJudgmentFeedback(
            user_id=u.id, target_type="insight", target_id=2,
            feedback="not_helpful", snapshot="new",
        ))
        db.commit()

        result = get_recent_negative_feedback(db, u.id, days=30)
        assert len(result) == 1
        assert result[0]["snapshot"] == "new"

    def test_respects_limit(self, db):
        u = _mk_user(db)
        for i in range(10):
            db.add(UserJudgmentFeedback(
                user_id=u.id, target_type="insight", target_id=i,
                feedback="not_helpful",
            ))
        db.commit()
        result = get_recent_negative_feedback(db, u.id, limit=3)
        assert len(result) == 3


class TestIdempotency:
    """同 user+target 只能一条 (覆盖). 通过 API 层验证."""

    def test_second_submit_updates_same_row(self, db):
        u = _mk_user(db)
        from app.api.judgment_feedback import submit_feedback
        from unittest.mock import MagicMock
        # 模拟 dependency: current_user
        req1 = JudgmentFeedbackRequest(
            target_type="insight", target_id=100,
            feedback="helpful", note="first",
        )
        out1 = submit_feedback(req1, current_user=u, db=db)
        first_id = out1["id"]

        req2 = JudgmentFeedbackRequest(
            target_type="insight", target_id=100,
            feedback="not_helpful", note="changed my mind",
        )
        out2 = submit_feedback(req2, current_user=u, db=db)
        # 同一条 row 被 update, id 不变
        assert out2["id"] == first_id
        assert out2["feedback"] == "not_helpful"

        count = db.query(UserJudgmentFeedback).filter_by(
            user_id=u.id, target_type="insight", target_id=100
        ).count()
        assert count == 1

    def test_invalid_target_type_raises(self, db):
        u = _mk_user(db)
        from app.api.judgment_feedback import submit_feedback
        req = JudgmentFeedbackRequest(
            target_type="invalid_xyz", target_id=1, feedback="helpful",
        )
        with pytest.raises(HTTPException) as exc:
            submit_feedback(req, current_user=u, db=db)
        assert exc.value.status_code == 400

    def test_invalid_feedback_raises(self, db):
        u = _mk_user(db)
        from app.api.judgment_feedback import submit_feedback
        req = JudgmentFeedbackRequest(
            target_type="insight", target_id=1, feedback="bogus",
        )
        with pytest.raises(HTTPException) as exc:
            submit_feedback(req, current_user=u, db=db)
        assert exc.value.status_code == 400
