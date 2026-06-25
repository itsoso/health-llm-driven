"""药程结束复查(ReviewSchedule)投影进议程 + 与 HealthProblem 复查去重(②)。

不碰 timeline_agenda_service / test_agenda_complete_medication(Codex 栈)。completion 不入
SUPPORTED_COMPLETE_TYPES,这里只验投影 + 去重 + tz。
"""
from datetime import timedelta

from app.models.family_health import ReviewSchedule
from app.models.health_problem import HealthProblem
from app.models.medication import Medication
from app.services import agenda_service, medication_course_service
from app.utils.timezone import get_china_today
from tests.conftest import create_authenticated_user


def _checkups(result):
    return [it for it in result["items"] if it.get("type") == "checkup"]


def _add_review(db, uid, item_name, days, status="pending", department="消化内科", priority="normal"):
    rs = ReviewSchedule(
        user_id=uid, item_name=item_name, status=status, category="specialist",
        next_due_date=get_china_today() + timedelta(days=days),
        department=department, priority=priority,
    )
    db.add(rs)
    db.commit()
    db.refresh(rs)
    return rs


def _add_problem(db, uid, name, days, what="复查", dept="消化内科"):
    p = HealthProblem(
        user_id=uid, name=name, risk_level="P1", status="active", responsible=dept,
        follow_up={"next_due": (get_china_today() + timedelta(days=days)).isoformat(),
                   "what_to_check": what},
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_review_schedule_projects_to_agenda(db):
    user, _ = create_authenticated_user(db)
    _add_review(db, user.id, "甲状腺功能", 5, department="内分泌科")
    cks = _checkups(agenda_service.today(db, user.id))
    assert any(
        c.get("title") == "复查:甲状腺功能"
        and (c.get("source") or {}).get("object_type") == "review_schedule"
        for c in cks
    )


def test_completed_review_not_projected(db):
    user, _ = create_authenticated_user(db)
    _add_review(db, user.id, "甲状腺功能", 5, status="completed")
    cks = _checkups(agenda_service.today(db, user.id))
    assert not any("甲状腺" in (c.get("title") or "") for c in cks)


def test_review_deduped_by_healthproblem(db):
    # 胃溃疡 HealthProblem 随访 + 胃镜复查 ReviewSchedule(同器官「胃」+ 邻近日期)→ 只出一条
    user, _ = create_authenticated_user(db)
    _add_problem(db, user.id, "胃溃疡(Hp 阴性,胃窦后壁)", 8, what="复查胃镜")
    _add_review(db, user.id, "胃镜复查", 10, department="消化内科")
    cks = _checkups(agenda_service.today(db, user.id))
    gastric = [c for c in cks if "胃" in (c.get("title") or "")]
    assert len(gastric) == 1, f"同一胃复查应去重成 1 条,实得 {[c.get('title') for c in gastric]}"
    # 留下的是临床锚定的 HealthProblem 那条,ReviewSchedule 被抑制
    assert (gastric[0].get("source") or {}).get("object_type") == "health_problem"


def test_review_not_deduped_different_organ(db):
    user, _ = create_authenticated_user(db)
    _add_problem(db, user.id, "胃溃疡(Hp 阴性)", 8, what="复查胃镜")
    _add_review(db, user.id, "甲状腺功能", 10, department="内分泌科")
    cks = _checkups(agenda_service.today(db, user.id))
    assert any("胃" in (c.get("title") or "") for c in cks)      # HealthProblem 胃复查
    assert any("甲状腺" in (c.get("title") or "") for c in cks)  # 不同器官,不被去重


def test_review_not_deduped_same_dept_different_organ(db):
    # 评审抓到的 under-alarm:同科室(消化内科)但不同器官——肠息肉随访(HealthProblem)
    # 不得吞掉胃镜复查(ReviewSchedule)。器官 token 不共现 → 两条都保留。
    user, _ = create_authenticated_user(db)
    _add_problem(db, user.id, "肠息肉随访", 8, what="结肠镜复查", dept="消化内科")
    _add_review(db, user.id, "胃镜复查", 10, department="消化内科")
    titles = [c.get("title") for c in _checkups(agenda_service.today(db, user.id))]
    assert any("肠息肉" in (t or "") for t in titles)             # HealthProblem
    assert any("胃镜" in (t or "") for t in titles), \
        f"同科室不同器官的胃镜复查不应被吞掉(under-alarm),实得 {titles}"


def test_upcoming_course_completions_uses_china_today(db, monkeypatch):
    # mock 京历今天=真实今天+100;药 end_date=fixed+10。用 get_china_today→在窗口内返回;
    # 若误用 date.today()(真实今天)→ end_date=real+110 落窗外→空。证明用了京历。
    user, _ = create_authenticated_user(db)
    fixed = get_china_today() + timedelta(days=100)
    monkeypatch.setattr(
        "app.services.medication_course_service.get_china_today", lambda: fixed
    )
    db.add(Medication(
        user_id=user.id, name="伏诺拉生", is_active=True,
        start_date=fixed - timedelta(days=40), end_date=fixed + timedelta(days=10),
    ))
    db.commit()
    out = medication_course_service.upcoming_course_completions(db, user.id)
    assert any(o["medication"] == "伏诺拉生" for o in out), \
        "应用 get_china_today(mock fixed),而非 date.today()"
