"""P1:时滞因果(lag_association 纯函数 + 用药干预)+ 社会连接 check-in。"""
from datetime import date, timedelta

from sqlalchemy import text

from app.services.chronic_trends import lag_association
from app.services.causal_links import medication_intervention_effects
from app.services import connection_service


# ── lag_association 纯函数 ──
def test_lag_association_next_day_effect():
    # 事件日:5/1、5/8;次日(lag=1)指标偏高,对照偏低
    events = [date(2026, 5, 1), date(2026, 5, 8), date(2026, 5, 15)]
    series = [
        (date(2026, 5, 2), 60), (date(2026, 5, 9), 62), (date(2026, 5, 16), 64),  # 事件次日
        (date(2026, 5, 4), 50), (date(2026, 5, 11), 48), (date(2026, 5, 20), 52),  # 对照日
    ]
    r = lag_association(events, series, lag_days=1)
    assert r is not None and r.n_events == 3
    assert r.mean_after > r.mean_baseline and r.delta > 0
    assert r.meaningful  # 3 事件 + >10%


def test_lag_association_insufficient_returns_none():
    assert lag_association([], [(date(2026, 5, 2), 60)], 1) is None
    # 无对照日(全是事件次日)→ None
    assert lag_association([date(2026, 5, 1)], [(date(2026, 5, 2), 60)], 1) is None


# ── 用药干预 → 指标变化 ──
def _seed_obs(db, uid, code, value, d):
    db.execute(text(
        "INSERT INTO biomarker_observations (user_id, code, normalized_value, normalized_unit, observed_at) "
        "VALUES (:u, :c, :v, 'mmol/L', :d)"
    ), {"u": uid, "c": code, "v": value, "d": d})
    db.commit()


def _seed_med(db, uid, name, start):
    db.execute(text(
        "INSERT INTO medications (user_id, name, is_active, start_date) VALUES (:u, :n, 1, :s)"
    ), {"u": uid, "n": name, "s": start})
    db.commit()


def test_medication_intervention_before_after(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed_med(db, user.id, "阿托伐他汀（立普妥）", date(2026, 3, 1))
    _seed_obs(db, user.id, "lipid_ldl", 4.2, date(2026, 1, 1))   # 用药前
    _seed_obs(db, user.id, "lipid_ldl", 2.6, date(2026, 5, 1))   # 用药后(降了)
    effects = medication_intervention_effects(db, user.id)
    assert len(effects) == 1
    e = effects[0]
    assert e["metric_label"] == "LDL" and e["before_mean"] == 4.2 and e["after_mean"] == 2.6
    assert e["delta"] < 0 and e["pct"] < 0


def test_medication_no_obs_skipped(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed_med(db, user.id, "阿托伐他汀", date(2026, 3, 1))  # 无 LDL 观测 → 跳过
    assert medication_intervention_effects(db, user.id) == []


# ── 社会连接 check-in ──
def test_connection_checkin_flow(client, db):
    from tests.conftest import create_authenticated_user
    user, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}

    # 初始:没做过 → due
    r0 = client.get("/api/v1/chronic/connection", headers=headers)
    assert r0.status_code == 200 and r0.json()["has_checkin"] is False and r0.json()["due"] is True

    # 提交:孤独评分高 + 无密友
    r1 = client.post("/api/v1/chronic/connection",
                     json={"ucla_score": 8, "has_confidant": False, "in_stable_group": True},
                     headers=headers)
    assert r1.status_code == 200
    st = r1.json()["status"]
    assert st["has_checkin"] and st["due"] is False and st["ucla_score"] == 8
    assert "孤独" in st["interpretation"]

    # 越界分数被拒
    assert client.post("/api/v1/chronic/connection", json={"ucla_score": 99},
                       headers=headers).status_code == 400
    # 未鉴权
    assert client.get("/api/v1/chronic/connection").status_code in (401, 403)


def test_connection_status_due_after_quarter(client, db):
    from tests.conftest import create_authenticated_user
    from app.models.connection_checkin import ConnectionCheckin
    user, _ = create_authenticated_user(db)
    old = ConnectionCheckin(user_id=user.id, checkin_date=date.today() - timedelta(days=100),
                            ucla_score=4, has_confidant=True, in_stable_group=True)
    db.add(old)
    db.commit()
    st = connection_service.status(db, user.id)
    assert st["has_checkin"] and st["due"] is True and st["days_since"] == 100
