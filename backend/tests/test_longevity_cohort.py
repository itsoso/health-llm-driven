# -*- coding: utf-8 -*-
"""抗衰群体证据聚合(Phase3 P3-3)回归。

钉:跨用户聚合已评分生物年龄卡;去标识(无 user_id + 小样本抑制);
改善率/平均年轻岁数;admin 鉴权;非生物年龄指标不计入;观察性不夸大。
"""
from datetime import datetime


def _card(db, user_id, metric, outcome, baseline=None, actual=None):
    from app.models.action_card import ActionCard
    c = ActionCard(
        user_id=user_id, title="t", content="x", metric_key=metric, outcome=outcome,
        baseline_value=str(baseline) if baseline is not None else None,
        actual_value=str(actual) if actual is not None else None,
        graded_at=datetime(2026, 6, 1),
    )
    db.add(c)
    return c


def test_cohort_aggregates_and_deidentifies(db):
    from app.services.longevity_cohort_service import cohort_biological_age_outcomes
    # 6 张 phenotypic_age 已评分(达 MIN_COHORT=5):4 improved / 1 worsened / 1 unchanged
    _card(db, 1, "phenotypic_age", "improved", 47, 44)   # -3
    _card(db, 2, "phenotypic_age", "improved", 50, 46)   # -4
    _card(db, 3, "phenotypic_age", "improved", 45, 43)   # -2
    _card(db, 4, "phenotypic_age", "improved", 48, 45)   # -3
    _card(db, 5, "phenotypic_age", "worsened", 44, 47)
    _card(db, 6, "phenotypic_age", "unchanged", 46, 46)
    db.commit()

    out = cohort_biological_age_outcomes(db)
    pa = out["metrics"]["phenotypic_age"]
    assert pa["n"] == 6 and pa["improved"] == 4
    assert pa["improvement_rate"] == round(4 / 6, 3)
    assert pa["mean_improvement_years"] == 3.0  # (3+4+2+3)/4
    assert "suppressed" not in pa
    # 去标识:输出里不含任何 user 字段
    assert "user_id" not in str(out)
    assert out["evidence_tier"] == "observational" and out["claim_boundary"]


def test_small_cohort_suppressed(db):
    from app.services.longevity_cohort_service import cohort_biological_age_outcomes
    _card(db, 1, "vo2max", "improved", 40, 44)
    _card(db, 2, "vo2max", "improved", 42, 45)
    db.commit()
    out = cohort_biological_age_outcomes(db)
    vo = out["metrics"]["vo2max"]
    assert vo["suppressed"] is True
    assert "improvement_rate" not in vo  # 小样本不出具体数


def test_ignores_non_bioage_metrics(db):
    from app.services.longevity_cohort_service import cohort_biological_age_outcomes
    for i in range(6):
        _card(db, i + 1, "weight", "improved", 80, 76)
    db.commit()
    out = cohort_biological_age_outcomes(db)
    assert "weight" not in out["metrics"]


def test_admin_endpoint_requires_admin(client, auth_user_and_headers):
    user, headers = auth_user_and_headers  # 普通用户(非 admin)
    r = client.get("/api/v1/admin/longevity/cohort", headers=headers)
    assert r.status_code == 403


def test_admin_endpoint_ok_for_admin(client, db):
    import uuid
    from datetime import date as _date
    from app.services.auth import auth_service
    from app.models.user import User
    admin = User(
        username=f"admin_{uuid.uuid4().hex[:8]}",
        email=f"admin_{uuid.uuid4().hex[:8]}@x.com",
        hashed_password="x", name="admin",
        birth_date=_date(1990, 1, 1), gender="男",
        is_active=True, is_approved=True, is_admin=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    token = auth_service.create_access_token({"sub": str(admin.id)})
    r = client.get("/api/v1/admin/longevity/cohort",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert "metrics" in r.json()
