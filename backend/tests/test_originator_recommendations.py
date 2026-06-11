"""原研药推荐(抑制感知)。钉:只推在用且有原研的药;采纳/忽略后抑制;prompt blob。"""
from datetime import date

from app.models.medication import Medication
from app.services.originator_recommendations import (
    pending_originator_recs,
    originator_recs_prompt_blob,
    set_status,
)
from app.services.originator_drugs import _normalize


def _add_med(db, user_id, name, active=True):
    m = Medication(user_id=user_id, name=name, is_active=active, start_date=date(2026, 6, 1))
    db.add(m)
    db.commit()
    return m


def test_pending_only_active_meds_with_originator(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _add_med(db, user.id, "泮托拉唑钠肠溶胶囊（泮立苏）")  # 有原研(潘妥洛克)
    _add_med(db, user.id, "AKK益生菌")                      # 未收录 → 不推
    _add_med(db, user.id, "立普妥", active=False)           # 停用 → 不推

    recs = pending_originator_recs(db, user.id)
    names = {r["generic_name"] for r in recs}
    assert "泮托拉唑" in names
    assert all("益生菌" not in n for n in names)
    assert len(recs) == 1


def test_adopted_is_suppressed(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _add_med(db, user.id, "阿托伐他汀")
    assert len(pending_originator_recs(db, user.id)) == 1

    set_status(db, user.id, _normalize("阿托伐他汀"), "adopted")
    assert pending_originator_recs(db, user.id) == []  # 采纳后不再推荐

    # 用户主动要求 → 重置 → 重新出现
    set_status(db, user.id, _normalize("阿托伐他汀"), "suggested")
    assert len(pending_originator_recs(db, user.id)) == 1


def test_dismissed_is_suppressed(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _add_med(db, user.id, "瑞舒伐他汀")
    set_status(db, user.id, _normalize("瑞舒伐他汀"), "dismissed")
    assert pending_originator_recs(db, user.id) == []


def test_prompt_blob_empty_when_no_recs(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    assert originator_recs_prompt_blob(db, user.id) == ""
    _add_med(db, user.id, "缬沙坦")
    blob = originator_recs_prompt_blob(db, user.id)
    assert "代文" in blob and "勿重复推荐" in blob


def test_status_endpoint_adopt(client, db):
    from tests.conftest import create_authenticated_user
    user, token = create_authenticated_user(db)
    _add_med(db, user.id, "二甲双胍")
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/v1/prescriptions/recommendations/status",
                    json={"generic_name": "二甲双胍", "status": "adopted"}, headers=headers)
    assert r.status_code == 200, r.text
    # 采纳后 recommendations 端点不再返回
    r2 = client.get("/api/v1/prescriptions/recommendations", headers=headers)
    assert r2.json()["recommendations"] == []
