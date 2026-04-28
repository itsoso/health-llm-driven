"""Open-Loop Manager — 主动循环管理单测."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.tasks.open_loop_manager import (
    OpenLoop,
    collect_open_loops,
    _detect_lab_overdue,
    _detect_action_card_due,
    _detect_sync_stale,
    _detect_trend_anomaly,
)


# ────── lab_overdue ──────


def test_lab_overdue_detects_aged_ldl(db):
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    # 7 个月前的 LDL 化验
    exam = MedicalExam(
        user_id=1, exam_date=date.today() - timedelta(days=210),
        exam_type="blood", overall_assessment="LDL 偏高",
    )
    db.add(exam)
    db.flush()
    db.add(MedicalExamItem(
        exam_id=exam.id, category="lipid",
        item_name="LDL 胆固醇", item_code="LDL-C",
        value=4.1, unit="mmol/L",
    ))
    db.commit()

    loops = _detect_lab_overdue(db, user_id=1)
    assert len(loops) == 1
    assert loops[0].kind == "lab_overdue"
    assert "LDL" in loops[0].title
    # overdue ≈ 30 天, severity 60 → score >= 60
    assert loops[0].score >= 60


def test_lab_not_overdue_kept_quiet(db):
    """30 天前的化验, 还没到 180 天复查间隔."""
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    exam = MedicalExam(
        user_id=2, exam_date=date.today() - timedelta(days=30),
        exam_type="blood",
    )
    db.add(exam); db.flush()
    db.add(MedicalExamItem(exam_id=exam.id, item_name="LDL", item_code="LDL", value=2.5))
    db.commit()

    loops = _detect_lab_overdue(db, user_id=2)
    # 30 天没到 180 天阈值, 不应触发
    assert len(loops) == 0


def test_no_lab_history_no_loop(db):
    """从来没做过化验 → 不主动催检 (避免对新用户骚扰)."""
    loops = _detect_lab_overdue(db, user_id=999)
    assert loops == []


# ────── sync_stale ──────


def test_sync_stale_detects_3day_gap(db):
    from app.models.daily_health import GarminData

    # 最近一次记录 5 天前
    db.add(GarminData(
        user_id=3, record_date=date.today() - timedelta(days=5),
        steps=8000,
    ))
    db.commit()
    loops = _detect_sync_stale(db, user_id=3)
    assert len(loops) == 1
    assert loops[0].kind == "sync_stale"
    assert "5" in loops[0].body or "天" in loops[0].body


def test_sync_fresh_no_loop(db):
    from app.models.daily_health import GarminData

    db.add(GarminData(user_id=4, record_date=date.today(), steps=10000))
    db.commit()
    assert _detect_sync_stale(db, user_id=4) == []


def test_no_garmin_no_loop(db):
    """从未接 Garmin → 不催 (避免新用户烦)."""
    assert _detect_sync_stale(db, user_id=888) == []


# ────── action_card_due ──────


def test_action_card_recently_graded(db):
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    card = ActionCard(
        user_id=5, title="HRV 7 天回升", content="...",
        card_type="plan", metric_key="hrv",
        baseline_value="35", target_value=">42",
        creator_specialist="recovery_coach",
        check_back_date=now - timedelta(hours=6),
        graded_at=now - timedelta(hours=2),  # 2h 前刚评
        accuracy_score=85,
        actual_value="44", grading_notes="达成: 35 → 44",
    )
    db.add(card); db.commit()

    loops = _detect_action_card_due(db, user_id=5)
    assert len(loops) == 1
    assert loops[0].kind == "action_card_due"
    assert "命中" in loops[0].body or "85" in loops[0].body


def test_action_card_old_grading_not_pushed(db):
    """5 天前评的卡, 不再推 (用户应该早就看到了)."""
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    card = ActionCard(
        user_id=6, title="...", content="...",
        metric_key="hrv", baseline_value="30", target_value=">40",
        check_back_date=now - timedelta(days=5),
        graded_at=now - timedelta(days=5),
        accuracy_score=50,
    )
    db.add(card); db.commit()
    assert _detect_action_card_due(db, user_id=6) == []


# ────── trend_anomaly ──────


def test_hrv_drop_detected(db):
    from app.models.daily_health import GarminData

    today = date.today()
    # 前 7 天: HRV 50 (高)
    for d in range(8, 15):
        db.add(GarminData(user_id=7, record_date=today - timedelta(days=d), hrv=50))
    # 最近 7 天: HRV 35 (低), 跌幅 30% > 阈值 15%
    for d in range(0, 7):
        db.add(GarminData(user_id=7, record_date=today - timedelta(days=d), hrv=35))
    db.commit()

    loops = _detect_trend_anomaly(db, user_id=7)
    assert any(l.kind == "trend_anomaly" for l in loops)


def test_no_hrv_drop_no_alert(db):
    from app.models.daily_health import GarminData
    today = date.today()
    for d in range(0, 14):
        db.add(GarminData(user_id=8, record_date=today - timedelta(days=d), hrv=42 + d % 3))
    db.commit()
    loops = _detect_trend_anomaly(db, user_id=8)
    assert all(l.kind != "trend_anomaly" for l in loops)


# ────── 整合 ──────


def test_collect_sorts_by_score(db):
    """混合多个 loop, 应按 score 倒序."""
    from app.models.medical_exam import MedicalExam, MedicalExamItem
    from app.models.daily_health import GarminData

    today = date.today()

    # 高分: HbA1c 9 个月没复查 (severity 80, ratio ~2x = 160 → cap 至 score 计算上限)
    exam = MedicalExam(user_id=10, exam_date=today - timedelta(days=270))
    db.add(exam); db.flush()
    db.add(MedicalExamItem(exam_id=exam.id, item_name="HbA1c", item_code="HBA1C", value=6.5))

    # 低分: Garmin 4 天没数据
    db.add(GarminData(user_id=10, record_date=today - timedelta(days=4)))
    db.commit()

    loops = collect_open_loops(db, user_id=10)
    assert len(loops) >= 2
    scores = [l.score for l in loops]
    assert scores == sorted(scores, reverse=True)
