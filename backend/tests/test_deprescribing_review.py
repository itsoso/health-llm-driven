"""多药梳理 / 减药候选。钉:多药/同类重复/长期候选/过期未停命中;安全话术不说停药。"""
from datetime import date, timedelta

from app.services.deprescribing_review import review_medications


def _m(name, start=None, end=None):
    return {"name": name, "start_date": start, "end_date": end}


def test_polypharmacy_flag():
    meds = [_m(n) for n in ["药A", "药B", "药C", "药D", "药E"]]  # 5 种
    r = review_medications(meds)
    assert r["is_polypharmacy"] and r["active_count"] == 5
    assert any(f["code"] == "polypharmacy" for f in r["flags"])


def test_below_threshold_not_polypharmacy():
    r = review_medications([_m("药A"), _m("药B")])
    assert not r["is_polypharmacy"]
    assert not any(f["code"] == "polypharmacy" for f in r["flags"])


def test_duplicate_class():
    # 两种 PPI/P-CAB → 同类重复
    r = review_medications([_m("泮托拉唑钠肠溶片"), _m("沃克(富马酸伏诺拉生)")])
    dup = [f for f in r["flags"] if f["code"] == "duplicate_class"]
    assert dup and "抑酸药" in dup[0]["detail"]


def test_long_term_candidate_ppi():
    old_start = date.today() - timedelta(weeks=12)
    r = review_medications([_m("泮托拉唑", start=old_start)])
    lt = [f for f in r["flags"] if f["code"] == "long_term_candidate"]
    assert lt and "12 周" in lt[0]["detail"]
    # 用药才 2 周 → 不算长期候选
    r2 = review_medications([_m("泮托拉唑", start=date.today() - timedelta(weeks=2))])
    assert not any(f["code"] == "long_term_candidate" for f in r2["flags"])


def test_expired_still_active():
    r = review_medications([_m("替普瑞酮", end=date.today() - timedelta(days=5))])
    assert any(f["code"] == "expired_still_active" for f in r["flags"])


def test_disclaimer_never_says_stop():
    r = review_medications([_m("泮托拉唑", start=date.today() - timedelta(weeks=20))])
    assert "医生" in r["disclaimer"]        # 最终决策在医生
    assert "非建议停药" in r["disclaimer"]  # 红线:明确声明"非建议停药",而非命令停药
    # suggestion 用"评估/讨论/确认"而非命令式停药
    assert all("立即停" not in f["suggestion"] and "请停药" not in f["suggestion"]
               for f in r["flags"])


def test_endpoint(client, db):
    from tests.conftest import create_authenticated_user
    from app.models.medication import Medication
    user, token = create_authenticated_user(db)
    for n in ["泮托拉唑", "沃克", "他汀类立普妥", "西替利嗪", "氯雷他定"]:
        db.add(Medication(user_id=user.id, name=n, is_active=True, start_date=date.today()))
    db.commit()
    r = client.get("/api/v1/medication/deprescribing-review/me",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_polypharmacy"] and len(body["flags"]) >= 1
    assert client.get("/api/v1/medication/deprescribing-review/me").status_code in (401, 403)
