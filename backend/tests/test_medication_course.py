"""用药疗程 → 复查闭环。钉:窗口内有复查映射;无 end_date 不算;物化幂等;胃药→胃镜。"""
from datetime import date, timedelta

from app.models.family_health import ReviewSchedule
from app.models.medication import Medication
from app.services.medication_course_service import (
    upcoming_course_completions,
    ensure_review_schedules,
    course_prompt_blob,
)


def _med(db, uid, name, end_offset_days, active=True):
    end = date.today() + timedelta(days=end_offset_days) if end_offset_days is not None else None
    m = Medication(user_id=uid, name=name, is_active=active, start_date=date.today(), end_date=end)
    db.add(m)
    db.commit()
    return m


def test_upcoming_within_window_with_gastric_followup(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _med(db, user.id, "沃克(富马酸伏诺拉生片)", 20)   # 20 天后结束 → 窗口内
    _med(db, user.id, "替普瑞酮胶囊（施维舒）", 20)
    _med(db, user.id, "AKK益生菌", None)              # 无 end_date → 不算
    _med(db, user.id, "某药", 200)                     # 太远 → 不算

    items = upcoming_course_completions(db, user.id, within_days=45)
    assert len(items) == 2
    assert all(it["followup"]["item_name"] == "胃镜复查" for it in items)
    assert items[0]["followup"]["department"] == "消化内科"


def test_no_followup_for_unmapped_drug(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _med(db, user.id, "某未知药", 10)
    items = upcoming_course_completions(db, user.id, 45)
    assert len(items) == 1 and items[0]["followup"] is None  # 通用,不臆造具体复查


def test_materialize_is_idempotent(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _med(db, user.id, "沃克(富马酸伏诺拉生片)", 30)
    r1 = ensure_review_schedules(db, user.id)
    assert r1["created"] == 1
    r2 = ensure_review_schedules(db, user.id)   # 再跑不重复建
    assert r2["created"] == 0 and r2["skipped"] == 1
    n = db.query(ReviewSchedule).filter(ReviewSchedule.user_id == user.id).count()
    assert n == 1
    rs = db.query(ReviewSchedule).filter(ReviewSchedule.user_id == user.id).first()
    assert rs.item_name == "胃镜复查" and rs.priority == "high"


def test_prompt_blob_and_endpoints(client, db):
    from tests.conftest import create_authenticated_user
    user, token = create_authenticated_user(db)
    _med(db, user.id, "替普瑞酮胶囊（施维舒）", 15)
    blob = course_prompt_blob(db, user.id)
    assert "替普瑞酮" in blob and "胃镜复查" in blob

    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/v1/medication-course/upcoming", headers=headers)
    assert r.status_code == 200 and len(r.json()["items"]) == 1
    r2 = client.post("/api/v1/medication-course/materialize", headers=headers)
    assert r2.status_code == 200 and r2.json()["created"] == 1
    assert client.get("/api/v1/medication-course/upcoming").status_code in (401, 403)
