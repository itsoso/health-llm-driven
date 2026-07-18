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
    _detect_plan_deviation,
)
from app.utils.timezone import get_china_today


# ────── lab_overdue ──────


def test_lab_overdue_detects_aged_ldl(db):
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    # 7 个月前的 LDL 化验
    exam = MedicalExam(
        user_id=1, exam_date=get_china_today() - timedelta(days=210),
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
        user_id=2, exam_date=get_china_today() - timedelta(days=30),
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
        user_id=3, record_date=get_china_today() - timedelta(days=5),
        steps=8000,
    ))
    db.commit()
    loops = _detect_sync_stale(db, user_id=3)
    assert len(loops) == 1
    assert loops[0].kind == "sync_stale"
    assert "5" in loops[0].body or "天" in loops[0].body


def test_sync_fresh_no_loop(db):
    from app.models.daily_health import GarminData

    db.add(GarminData(user_id=4, record_date=get_china_today(), steps=10000))
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


def test_clinician_gated_action_card_is_not_pushed_as_ai_success_or_failure(db):
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=61, title="降低 LDL", content="...", metric_key="ldl",
        check_back_date=now - timedelta(hours=6),
        graded_at=now - timedelta(hours=2), accuracy_score=None,
        outcome="inconclusive",
    ))
    db.commit()

    assert _detect_action_card_due(db, user_id=61) == []


# ────── trend_anomaly ──────


def test_hrv_drop_detected(db):
    from app.models.daily_health import GarminData

    today = get_china_today()
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
    today = get_china_today()
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

    today = get_china_today()

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


# ────── plan_deviation ──────


def _make_tmpl(db, user_id, category="exercise", days_since_checkin=None, **overrides):
    """帮手: 建一个 daily CheckinTemplate, last_checkin_date 从今天倒推."""
    from app.models.checkin import CheckinTemplate
    defaults = dict(
        user_id=user_id,
        name=overrides.get("name", "跑步" if category == "exercise" else "维生素D"),
        category=category,
        frequency="daily",
        is_active=True,
        is_archived=False,
        icon=overrides.get("icon", "🏃" if category == "exercise" else "💊"),
    )
    defaults.update(overrides)
    if days_since_checkin is not None:
        defaults["last_checkin_date"] = get_china_today() - timedelta(days=days_since_checkin)
    t = CheckinTemplate(**defaults)
    db.add(t); db.commit(); db.refresh(t)
    return t


def test_plan_deviation_exercise_3_days_triggers(db):
    _make_tmpl(db, user_id=100, category="exercise", days_since_checkin=3, name="深蹲")
    loops = _detect_plan_deviation(db, user_id=100)
    assert len(loops) == 1
    assert loops[0].kind == "plan_drift"
    assert "深蹲" in loops[0].title
    assert "3 天" in loops[0].title
    # exercise base 45 → 3 天刚到阈值 → score = 45
    assert loops[0].score == 45


def test_plan_deviation_exercise_2_days_quiet(db):
    """2 天没打卡未到阈值 (3 天), 不报."""
    _make_tmpl(db, user_id=101, category="exercise", days_since_checkin=2)
    assert _detect_plan_deviation(db, user_id=101) == []


def test_plan_deviation_medicine_higher_severity(db):
    """同样 3 天断卡, medicine 基础分 70, 远高于 exercise 的 45."""
    _make_tmpl(db, user_id=102, category="medicine", days_since_checkin=3, name="二甲双胍")
    loops = _detect_plan_deviation(db, user_id=102)
    assert len(loops) == 1
    assert loops[0].score == 70
    assert "用药" in loops[0].body
    # §5 推送隐私 (2026-07-11): 药名不进锁屏可见的 title/body(药名可反推诊断),
    # 只留在 metadata.template_name, App 解锁后应用内渲染。
    assert "二甲双胍" not in loops[0].title
    assert "二甲双胍" not in loops[0].body
    assert loops[0].metadata["template_name"] == "二甲双胍"


def test_plan_deviation_score_grows_with_days(db):
    """断裂越久分越高 (每多一天 +5)."""
    _make_tmpl(db, user_id=103, category="medicine", days_since_checkin=7, name="钙片")
    loops = _detect_plan_deviation(db, user_id=103)
    # medicine base 70 + (7-3)*5 = 90
    assert loops[0].score == 90


def test_plan_deviation_score_capped_at_95(db):
    """再长的断裂不超过 95 (保留给更紧急信号)."""
    _make_tmpl(db, user_id=104, category="medicine", days_since_checkin=60)
    loops = _detect_plan_deviation(db, user_id=104)
    assert loops[0].score == 95


def test_plan_deviation_cold_start_silent(db):
    """从未打卡 (last_checkin_date=None) 的模板不报, 不骚扰新用户."""
    _make_tmpl(db, user_id=105, category="exercise", days_since_checkin=None)
    assert _detect_plan_deviation(db, user_id=105) == []


def test_plan_deviation_ignores_health_and_habit(db):
    """只抓 exercise/medicine, health/habit 不报."""
    _make_tmpl(db, user_id=106, category="health", days_since_checkin=5, name="测血压")
    _make_tmpl(db, user_id=106, category="habit", days_since_checkin=10, name="冥想")
    assert _detect_plan_deviation(db, user_id=106) == []


def test_plan_deviation_ignores_archived_and_inactive(db):
    """归档或停用的模板不报."""
    _make_tmpl(db, user_id=107, category="exercise",
               days_since_checkin=10, is_archived=True, name="跳绳1")
    _make_tmpl(db, user_id=107, category="medicine",
               days_since_checkin=10, is_active=False, name="已停药")
    assert _detect_plan_deviation(db, user_id=107) == []


def test_plan_deviation_ignores_non_daily_frequency(db):
    """weekly / monthly 频率的模板不被 3 天阈值误伤."""
    _make_tmpl(db, user_id=108, category="exercise",
               days_since_checkin=5, frequency="weekly")
    assert _detect_plan_deviation(db, user_id=108) == []


def test_plan_deviation_signal_key_uses_template_id(db):
    """signal_key 带 template_id, 保证 dedup 粒度是"某个打卡项", 而不是"运动"整类."""
    t1 = _make_tmpl(db, user_id=109, category="exercise", days_since_checkin=4, name="俯卧撑")
    t2 = _make_tmpl(db, user_id=109, category="medicine", days_since_checkin=4, name="益生菌")
    loops = _detect_plan_deviation(db, user_id=109)
    assert len(loops) == 2
    keys = {l.signal_key for l in loops}
    assert f"template_id={t1.id}" in keys
    assert f"template_id={t2.id}" in keys


def test_plan_deviation_collect_integration(db):
    """plan_deviation 已接入 collect_open_loops."""
    _make_tmpl(db, user_id=110, category="medicine", days_since_checkin=5, name="华法林")
    loops = collect_open_loops(db, user_id=110)
    assert any(l.kind == "plan_drift" for l in loops)
