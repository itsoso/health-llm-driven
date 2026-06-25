"""每日疗程复查物化任务(materialize_course_reviews)回归。

钉:任务把「在用药 end_date 在窗口内 + 高把握映射」的用户物化成 ReviewSchedule 行,
让 agenda_service 的药程复查投影有行可显;幂等(重跑不重复建);窗口外不物化。

mock get_china_today(京历边界)做确定性 —— 同时治住 UTC runner 在午夜边界 date 漂的
flake(见 MEMORY)。任务内部 with SessionLocal() 用 _patch_session_local 接到 test db。
"""
from datetime import timedelta

from app.models.family_health import ReviewSchedule
from app.models.medication import Medication
from app.tasks import course_review_materialize as task_mod
from app.utils.timezone import get_china_today
from tests.conftest import create_authenticated_user


def _patch_session_local(monkeypatch, db):
    """让任务的 with SessionLocal() 用 test 的 db session, 避免真连数据库。"""
    class _CM:
        def __enter__(self_inner):
            return db

        def __exit__(self_inner, *a):
            return False

    monkeypatch.setattr(task_mod, "SessionLocal", lambda: _CM())


def _fix_today(monkeypatch, today):
    """钉死 medication_course_service.get_china_today —— 预筛与逐人物化共用同一边界。"""
    monkeypatch.setattr(
        "app.services.medication_course_service.get_china_today", lambda: today
    )


def _add_med(db, uid, name, end_in_days, today, is_active=True):
    db.add(Medication(
        user_id=uid, name=name, is_active=is_active,
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=end_in_days),
    ))
    db.commit()


def _reviews(db, uid):
    return db.query(ReviewSchedule).filter(ReviewSchedule.user_id == uid).all()


def test_task_materializes_review_for_upcoming_course(db, monkeypatch):
    today = get_china_today() + timedelta(days=100)  # 任意固定锚点, 不依赖 runner OS tz
    _fix_today(monkeypatch, today)
    user, _ = create_authenticated_user(db)
    # 伏诺拉生(P-CAB)→ 高把握映射「胃镜复查」, end_date 在 45 天窗口内
    _add_med(db, user.id, "伏诺拉生", end_in_days=10, today=today)
    _patch_session_local(monkeypatch, db)

    out = task_mod.materialize_course_reviews()

    assert out == {"users": 1, "created": 1, "skipped": 0}
    rows = _reviews(db, user.id)
    assert len(rows) == 1
    rs = rows[0]
    assert rs.item_name == "胃镜复查"
    assert rs.next_due_date == today + timedelta(days=10)
    assert rs.status == "pending"


def test_task_is_idempotent_on_rerun(db, monkeypatch):
    today = get_china_today() + timedelta(days=100)
    _fix_today(monkeypatch, today)
    user, _ = create_authenticated_user(db)
    _add_med(db, user.id, "伏诺拉生", end_in_days=10, today=today)
    _patch_session_local(monkeypatch, db)

    first = task_mod.materialize_course_reviews()
    second = task_mod.materialize_course_reviews()

    assert first["created"] == 1
    assert second["created"] == 0 and second["skipped"] == 1
    assert len(_reviews(db, user.id)) == 1  # 重跑不重复建


def test_task_skips_course_ending_outside_window(db, monkeypatch):
    today = get_china_today() + timedelta(days=100)
    _fix_today(monkeypatch, today)
    user, _ = create_authenticated_user(db)
    # end_date 在 45 天窗口外 → 既不进预筛集, 也不物化
    _add_med(db, user.id, "伏诺拉生", end_in_days=120, today=today)
    _patch_session_local(monkeypatch, db)

    out = task_mod.materialize_course_reviews()

    assert out == {"users": 0, "created": 0, "skipped": 0}
    assert _reviews(db, user.id) == []
