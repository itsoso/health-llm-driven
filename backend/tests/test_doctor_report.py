"""医生回路 (H3-7) 测试."""
from datetime import date, datetime, timedelta, timezone
import pytest

from app.models.user import User
from app.models.action_card import ActionCard
from app.models.anomaly_alert import AnomalyAlert
from app.models.clinical_journal import ClinicalJournalEntry
from app.models.daily_health import GarminData
from app.models.user_directive import UserDirective
from app.services.doctor_report_service import (
    build_doctor_export, record_doctor_feedback, list_doctor_feedback,
)


@pytest.fixture
def user(db):
    u = User(
        id=1, username="u1", name="张三",
        birth_date=date(1982, 3, 15),
        gender="男",
    )
    db.add(u)
    db.commit()
    return u


class TestExport:
    def test_empty_user_returns_skeleton(self, db, user):
        r = build_doctor_export(db, user.id, days=30)
        assert r["user_brief"]["name"] == "张三"
        assert r["user_brief"]["gender"] == "男"
        assert r["user_brief"]["age"] >= 42  # 至少 44 at today 2026
        assert r["vitals"]["samples"] == 0
        assert r["directives"] == []
        assert r["alerts"] == []
        assert r["ai_scorecard"]["total_graded"] == 0
        assert "健康情况摘要" in r["markdown"]

    def test_vitals_aggregation(self, db, user):
        today = date.today()
        for i in range(7):
            db.add(GarminData(
                user_id=user.id,
                record_date=today - timedelta(days=i),
                resting_heart_rate=60 + i,
                hrv=40,
                sleep_score=80,
                total_sleep_duration=450,
                stress_level=30,
                steps=8000,
            ))
        db.commit()

        r = build_doctor_export(db, user.id, days=30)
        assert r["vitals"]["samples"] == 7
        assert r["vitals"]["avg_rhr"] == 63  # round to 0
        assert r["vitals"]["avg_hrv"] == 40.0
        assert r["vitals"]["avg_sleep_hours"] == 7.5

    def test_directives_listed(self, db, user):
        db.add(UserDirective(
            user_id=user.id, kind="medication",
            instruction="每日早晨服异丙托溴铵 2 吸",
            severity="strong", source="doctor", status="active",
        ))
        db.add(UserDirective(
            user_id=user.id, kind="limit",
            instruction="戒酒", severity="mandatory",
            source="doctor", status="revoked",  # 非 active
        ))
        db.commit()

        r = build_doctor_export(db, user.id, days=30)
        assert len(r["directives"]) == 1
        assert "异丙托溴铵" in r["directives"][0]["instruction"]
        assert "异丙托溴铵" in r["markdown"]

    def test_alerts_in_window(self, db, user):
        now = datetime.now(timezone.utc)
        # Recent — 应包含
        db.add(AnomalyAlert(
            user_id=user.id, alert_type="hrv_drop",
            metric_name="hrv", severity="high",
            detection_date=date.today(),
            message="HRV 大幅下降",
            created_at=now - timedelta(days=1),
        ))
        # Too old — 不应包含
        db.add(AnomalyAlert(
            user_id=user.id, alert_type="sleep_low",
            metric_name="sleep_score", severity="warning",
            detection_date=date.today() - timedelta(days=60),
            message="睡眠很差",
            created_at=now - timedelta(days=60),
        ))
        db.commit()

        r = build_doctor_export(db, user.id, days=30)
        assert len(r["alerts"]) == 1
        assert r["alerts"][0]["alert_type"] == "hrv_drop"

    def test_scorecard(self, db, user):
        now = datetime.now(timezone.utc)
        for score in [85, 75, 20, 55]:
            db.add(ActionCard(
                user_id=user.id, title="测试", content="",
                metric_key="hrv",
                accuracy_score=score,
                graded_at=now - timedelta(days=2),
            ))
        db.commit()

        r = build_doctor_export(db, user.id, days=30)
        sc = r["ai_scorecard"]
        assert sc["total_graded"] == 4
        assert sc["hit_count"] == 2
        assert sc["hit_rate_pct"] == 50.0

    def test_scorecard_excludes_clinician_gated_metric(self, db, user):
        now = datetime.now(timezone.utc)
        db.add_all([
            ActionCard(
                user_id=user.id, title="LDL", content="", metric_key="ldl",
                accuracy_score=95, graded_at=now - timedelta(days=2),
            ),
            ActionCard(
                user_id=user.id, title="恢复", content="", metric_key="hrv",
                accuracy_score=80, graded_at=now - timedelta(days=2),
            ),
        ])
        db.commit()

        scorecard = build_doctor_export(db, user.id, days=30)["ai_scorecard"]
        assert scorecard == {
            "total_graded": 1,
            "hit_count": 1,
            "hit_rate_pct": 100.0,
            "avg_score": 80.0,
        }


class TestFeedback:
    def test_record_and_list(self, db, user):
        entry = record_doctor_feedback(
            db, user.id,
            summary="胸闷偶发",
            assessment="建议 PSG 排查 OSAHS",
            plan="下周约睡眠门诊",
            visit_date=date(2026, 4, 29),
        )
        assert entry.id is not None
        assert entry.created_by == "doctor"
        assert entry.subjective == "胸闷偶发"
        assert "OSAHS" in entry.assessment
        assert "2026-04-29" in entry.objective

        rows = list_doctor_feedback(db, user.id)
        assert len(rows) == 1
        assert rows[0].id == entry.id

    def test_filters_to_doctor_only(self, db, user):
        # orchestrator 写的也在 clinical_journal 里, 不应返回
        db.add(ClinicalJournalEntry(
            user_id=user.id, assessment="AI 产出",
            created_by="orchestrator",
        ))
        record_doctor_feedback(db, user.id, summary="", assessment="医生意见", plan="")

        rows = list_doctor_feedback(db, user.id)
        assert len(rows) == 1
        assert rows[0].created_by == "doctor"

    def test_scoped_per_user(self, db, user):
        other = User(id=2, username="u2", name="李四")
        db.add(other)
        db.commit()

        record_doctor_feedback(db, user.id, summary="", assessment="A", plan="")
        record_doctor_feedback(db, other.id, summary="", assessment="B", plan="")

        assert len(list_doctor_feedback(db, user.id)) == 1
        assert len(list_doctor_feedback(db, other.id)) == 1


class TestMarkdown:
    def test_contains_all_sections(self, db, user):
        # 准备最小化数据让所有 section 都写出来
        db.add(GarminData(
            user_id=user.id, record_date=date.today(),
            resting_heart_rate=60, hrv=45,
            sleep_score=80, total_sleep_duration=480,
            stress_level=25, steps=9000,
        ))
        db.add(UserDirective(
            user_id=user.id, kind="goal",
            instruction="LDL 控制在 2.6 以下",
            status="active", source="doctor",
        ))
        db.add(AnomalyAlert(
            user_id=user.id, alert_type="rhr_spike",
            metric_name="resting_heart_rate", severity="warning",
            detection_date=date.today(),
            message="静息心率升高",
            created_at=datetime.now(timezone.utc),
        ))
        db.add(ActionCard(
            user_id=user.id, title="喝水", content="",
            accuracy_score=85, graded_at=datetime.now(timezone.utc),
        ))
        db.commit()

        r = build_doctor_export(db, user.id, days=30)
        md = r["markdown"]
        assert "可穿戴核心指标" in md
        assert "当前医嘱" in md
        assert "LDL 控制" in md
        assert "近期关键告警" in md
        assert "AI 建议命中率" in md
        assert "本报告" in md  # 免责声明
