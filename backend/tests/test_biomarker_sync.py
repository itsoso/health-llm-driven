"""medical_indicators → biomarker_observations 同步。钉:识别归一/跳过未知/幂等/周期刷新。"""
from datetime import date, datetime

from sqlalchemy import text

from app.models.biomarker_observation import BiomarkerObservation
from app.services.biomarker_sync import sync_indicators_to_biomarkers


def _seed_ind(db, user_id, name, value, d, unit="U/L"):
    db.execute(text(
        "INSERT INTO medical_indicators (user_id, name, value, unit, record_date) "
        "VALUES (:u, :n, :v, :unit, :d)"
    ), {"u": user_id, "n": name, "v": value, "unit": unit, "d": d})
    db.commit()


def test_sync_recognizes_and_writes(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed_ind(db, user.id, "谷氨酰转肽酶", 78, date(2025, 8, 1))
    _seed_ind(db, user.id, "甘油三酯", 2.1, date(2026, 5, 1), unit="mmol/L")
    _seed_ind(db, user.id, "某不存在的指标", 99, date(2026, 5, 1))  # definitions 外 → 跳过

    r = sync_indicators_to_biomarkers(db, user.id)
    assert r["scanned"] == 3 and r["recognized"] == 2 and r["written"] == 2
    obs = db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == user.id).all()
    codes = {o.code for o in obs}
    assert "GGT" in codes and "lipid_tg" in codes
    ggt = next(o for o in obs if o.code == "GGT")
    assert ggt.normalized_value == 78 and ggt.abnormal is True  # 78 > 60 ULN


def test_sync_is_idempotent(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed_ind(db, user.id, "谷草转氨酶", 32, date(2025, 8, 1))
    sync_indicators_to_biomarkers(db, user.id)
    sync_indicators_to_biomarkers(db, user.id)  # 再跑一次不应翻倍
    n = db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == user.id).count()
    assert n == 1


def test_sync_updates_existing_on_value_change(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed_ind(db, user.id, "谷氨酰转肽酶", 78, date(2025, 8, 1))
    sync_indicators_to_biomarkers(db, user.id)
    # 改同日期同指标的值(纠错场景)→ 更新非新增
    db.execute(text("UPDATE medical_indicators SET value = 70 WHERE user_id = :u"), {"u": user.id})
    db.commit()
    sync_indicators_to_biomarkers(db, user.id)
    obs = db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == user.id).all()
    assert len(obs) == 1 and obs[0].normalized_value == 70


def test_biomarker_sync_endpoint(client, db):
    from tests.conftest import create_authenticated_user
    user, token = create_authenticated_user(db)
    _seed_ind(db, user.id, "空腹血糖", 6.5, date(2026, 5, 1), unit="mmol/L")
    r = client.post("/api/v1/chronic/biomarker-sync",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["sync"]["written"] == 1
    assert client.post("/api/v1/chronic/biomarker-sync").status_code in (401, 403)


def test_refresh_cycle_targets_fills_empty(client, db):
    """根因修复:开周期时归一层空 → 空目标;sync 后 refresh 应补出目标。"""
    from tests.conftest import create_authenticated_user
    from app.models.intervention_cycle import InterventionCycle
    from app.services.intervention_cycle_service import refresh_cycle_targets
    user, _ = create_authenticated_user(db)
    # 异常指标:GGT 78(>60)
    _seed_ind(db, user.id, "谷氨酰转肽酶", 78, date(2026, 5, 1))
    cycle = InterventionCycle(user_id=user.id, cycle_type="metabolic_90d", status="active",
                              start_date=date(2026, 6, 1), planned_end_date=date(2026, 9, 1),
                              target_metrics=[])
    db.add(cycle)
    db.commit()
    assert cycle.target_metrics == []  # 空目标(根因)

    sync_indicators_to_biomarkers(db, user.id)
    refresh_cycle_targets(db, cycle)
    codes = {s["code"] for s in cycle.target_metrics}
    assert "GGT" in codes  # 现在有目标了
    assert len(cycle.outcomes) >= 1  # OutcomeMetric 也建了基线
