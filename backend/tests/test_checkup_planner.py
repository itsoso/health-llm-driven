"""R7 体检/筛查规划器 —— 按年龄/性别生成人群筛查复查项,物化成 ReviewSchedule。

安全边界(同 ② course-review 已上线的提示性复查物化,非处方/非诊断):只产出**建议性**人群筛查项 +
「以医生意见为准」,advisory-only(不内嵌 TI-RADS/Fleischner 这类按具体病灶分期的临床判定——那些是
临床锚定的 HealthProblem.follow_up 的活)。物化成 ReviewSchedule,现有 agenda 投影 + 器官去重直接消费。
"""
from datetime import date, timedelta

from app.models.family_health import ReviewSchedule
from app.models.user_profile import UserProfile
from app.services import checkup_planner
from app.utils.timezone import get_china_today
from tests.conftest import create_authenticated_user


def _profile(db, uid, age=None, gender=None):
    p = db.query(UserProfile).filter(UserProfile.user_id == uid).first()
    if p is None:
        p = UserProfile(user_id=uid)
        db.add(p)
    # 显式设(age=None → 清空 birth_date,真正模拟「无年龄」)
    p.birth_date = date(get_china_today().year - age, 6, 1) if age is not None else None
    p.gender = gender
    if age is None:
        # 同时清掉 User 上的 birth_date —— 规划器的 User 兜底是正确行为,测试要真正无年龄
        from app.models.user import User
        u = db.query(User).filter(User.id == uid).first()
        if u is not None:
            u.birth_date = None
    db.commit()
    return p


def _items(db, uid):
    return {
        r.item_name
        for r in db.query(ReviewSchedule).filter(ReviewSchedule.user_id == uid).all()
    }


def test_age45_gets_colorectal_screening(db):
    user, _ = create_authenticated_user(db)
    _profile(db, user.id, age=46, gender="male")
    res = checkup_planner.ensure_checkup_schedules(db, user.id)
    assert res["created"] >= 1
    assert any("结直肠" in n for n in _items(db, user.id))


def test_age30_no_age_gated_screenings(db):
    user, _ = create_authenticated_user(db)
    _profile(db, user.id, age=30, gender="male")
    checkup_planner.ensure_checkup_schedules(db, user.id)
    items = _items(db, user.id)
    assert not any("结直肠" in n for n in items)  # 45 岁才起
    assert not any("血脂" in n for n in items)     # 40 岁才起


def test_female_gets_cervical_and_breast(db):
    user, _ = create_authenticated_user(db)
    _profile(db, user.id, age=45, gender="female")
    checkup_planner.ensure_checkup_schedules(db, user.id)
    items = _items(db, user.id)
    assert any("宫颈" in n for n in items)
    assert any("乳腺" in n for n in items)
    assert not any("前列腺" in n for n in items)  # 男性项不给女性


def test_male_psa_is_advisory_worded(db):
    user, _ = create_authenticated_user(db)
    _profile(db, user.id, age=55, gender="male")
    checkup_planner.ensure_checkup_schedules(db, user.id)
    psa = [n for n in _items(db, user.id) if "前列腺" in n or "PSA" in n]
    assert psa and ("讨论" in psa[0] or "利弊" in psa[0])  # 争议项必须 advisory 措辞
    assert not any("宫颈" in n for n in _items(db, user.id))  # 女性项不给男性


def test_idempotent_no_duplicate_on_rerun(db):
    user, _ = create_authenticated_user(db)
    _profile(db, user.id, age=50, gender="male")
    r1 = checkup_planner.ensure_checkup_schedules(db, user.id)
    r2 = checkup_planner.ensure_checkup_schedules(db, user.id)
    assert r1["created"] >= 1
    assert r2["created"] == 0 and r2["skipped"] >= 1  # 第二遍全跳过,不重复建
    # 每个 item 只一条
    items = [r.item_name for r in db.query(ReviewSchedule).filter(ReviewSchedule.user_id == user.id).all()]
    assert len(items) == len(set(items))


def test_no_birthdate_skips_safely(db):
    user, _ = create_authenticated_user(db)
    _profile(db, user.id, age=None, gender="male")  # 无出生日期 → 算不出年龄
    res = checkup_planner.ensure_checkup_schedules(db, user.id)
    assert res["created"] == 0 and res.get("reason") == "no_age"
    assert _items(db, user.id) == set()


def test_materialized_screening_visible_in_default_agenda(db):
    """回归(对抗评审 BLOCKING):物化的筛查项必须在 agenda 默认窗(14天)内真出现。

    _LEAD_DAYS 必须 ≤ 投影窗,否则新建项落窗外、十几天不可见 = 功能等于没接通。
    断言走真实消费者 agenda_service.today,而非只查 ReviewSchedule 行。
    """
    from app.services import agenda_service

    user, _ = create_authenticated_user(db)
    _profile(db, user.id, age=50, gender="male")
    res = checkup_planner.ensure_checkup_schedules(db, user.id)
    assert res["created"] >= 1
    cks = [it for it in agenda_service.today(db, user.id)["items"] if it.get("type") == "checkup"]
    assert any(
        any(kw in (c.get("title") or "") for kw in ("结直肠", "血脂", "血糖", "胃镜", "上消化道"))
        for c in cks
    ), f"R7 筛查项应在默认议程窗内可见,实得: {[c.get('title') for c in cks]}"


def test_gender_other_only_sex_agnostic(db):
    """gender=other → 不触发任何性别特异项(无 PSA/宫颈/乳腺),只剩通用年龄项。"""
    user, _ = create_authenticated_user(db)
    _profile(db, user.id, age=50, gender="other")
    checkup_planner.ensure_checkup_schedules(db, user.id)
    items = _items(db, user.id)
    assert not any(("前列腺" in n or "宫颈" in n or "乳腺" in n) for n in items)
    assert any("血脂" in n for n in items)  # 通用项仍在


def test_notes_carry_doctor_confirm_boundary(db):
    user, _ = create_authenticated_user(db)
    _profile(db, user.id, age=46, gender="male")
    checkup_planner.ensure_checkup_schedules(db, user.id)
    r = db.query(ReviewSchedule).filter(ReviewSchedule.user_id == user.id).first()
    assert r is not None
    assert "医生" in (r.notes or "")  # 必带「以医生意见为准」边界
    assert r.next_due_date >= get_china_today()  # 未来到期日,非过去
    assert r.status == "pending"
