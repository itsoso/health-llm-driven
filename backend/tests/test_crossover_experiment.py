"""R16 P4 A·B·A·B 交叉实验:重复感知裁决 + 服务 + API。

裁决核心:on 相一致优于 off 相且干净分离 + 重复 ≥2 → replicated(封顶 moderate);门控指标永
clinician_review;重复不足→insufficient;有方向但重叠→suggestive;无效应→not_replicated。相关非因果。
"""
from datetime import date

from app.models.intervention_cycle import InterventionCycle, OutcomeMetric
from app.services import crossover_service as cx
from app.services.crossover_verdict import replication_verdict
from tests.conftest import create_authenticated_user


def _ph(arm, level):
    return {"arm": arm, "level": level}


# ───────────────────────── 裁决纯逻辑 ─────────────────────────


def test_verdict_replicated_clean_separation():
    v = replication_verdict([_ph("on", 70), _ph("off", 80), _ph("on", 72), _ph("off", 82)], "weight", "down")
    assert v["verdict"] == "replicated" and v["confidence"] == "moderate"
    assert v["requires_clinician"] is False
    assert v["attribution"] == "temporal_association_not_causation"
    assert v["n_on"] == 2 and v["n_off"] == 2


def test_verdict_gated_never_replicated():
    # 处方混杂指标即便干净重复也只 clinician_review
    v = replication_verdict([_ph("on", 2.4), _ph("off", 3.5), _ph("on", 2.5), _ph("off", 3.6)], "lipid_ldl", "down")
    assert v["verdict"] == "clinician_review" and v["requires_clinician"] is True


def test_verdict_insufficient_under_two():
    v = replication_verdict([_ph("on", 70), _ph("off", 80)], "weight", "down")
    assert v["verdict"] == "insufficient" and v["confidence"] == "low"


def test_verdict_suggestive_when_overlap():
    # mean_on(74.5) < mean_off(80) 有方向,但 max(on)=79 > min(off)=78 重叠 → suggestive
    v = replication_verdict([_ph("on", 70), _ph("off", 78), _ph("on", 79), _ph("off", 82)], "weight", "down")
    assert v["verdict"] == "suggestive" and v["confidence"] == "low"


def test_verdict_not_replicated_when_on_worse():
    v = replication_verdict([_ph("on", 82), _ph("off", 70), _ph("on", 80), _ph("off", 72)], "weight", "down")
    assert v["verdict"] == "not_replicated" and v["confidence"] == "low"


def test_verdict_tiny_separation_not_replicated():
    # 对抗评审 BLOCKING:0.2kg 分离(<< 体重 mcid 2.0)纯测量抖动 → 绝不 replicated,降 suggestive
    v = replication_verdict([_ph("on", 79.9), _ph("off", 80.0), _ph("on", 79.8), _ph("off", 80.1)], "weight", "down")
    assert v["verdict"] == "suggestive" and v["confidence"] == "low"


def test_verdict_block_order_not_replicated():
    # A/A/B/B 块状(非交替,只 1 次切换)即便大分离 → 不算重复反转 → suggestive(对抗 NIT)
    v = replication_verdict([_ph("on", 70), _ph("on", 72), _ph("off", 80), _ph("off", 82)], "weight", "down")
    assert v["verdict"] == "suggestive"


def test_verdict_up_direction_replicated():
    # up=升为好(如 HRV):on 一致高于 off 且干净 → replicated
    v = replication_verdict([_ph("on", 90), _ph("off", 70), _ph("on", 92), _ph("off", 72)], "hrv", "up")
    assert v["verdict"] == "replicated"


# ───────────────────────── 服务:建/串相/裁决 ─────────────────────────


def _mk_cycle(db, uid, code, latest):
    c = InterventionCycle(user_id=uid, cycle_type="metabolic", status="completed", start_date=date(2026, 1, 1))
    db.add(c)
    db.flush()
    db.add(OutcomeMetric(cycle_id=c.id, metric_code=code, latest_value=latest))
    db.commit()
    return c


def test_service_create_add_phases_replicated(db):
    user, _ = create_authenticated_user(db)
    cycles = [_mk_cycle(db, user.id, "weight", v) for v in (70, 80, 72, 82)]
    exp = cx.create_experiment(db, user.id, "weight", "down")
    assert exp.verdict == "insufficient"  # 空相
    for c, arm in zip(cycles, ("on", "off", "on", "off")):
        exp = cx.add_phase(db, exp, c.id, arm)
    assert exp.verdict == "replicated" and exp.confidence == "moderate"
    assert len(exp.phases) == 4 and exp.phases[0]["level"] == 70.0


def test_service_invalid_arm_raises(db):
    user, _ = create_authenticated_user(db)
    c = _mk_cycle(db, user.id, "weight", 70)
    exp = cx.create_experiment(db, user.id, "weight", "down")
    try:
        cx.add_phase(db, exp, c.id, "bogus")
        assert False, "非法 arm 应抛 ValueError"
    except ValueError:
        pass


# ───────────────────────── API 烟测 ─────────────────────────


def test_api_crossover_flow(client, db):
    user, token = create_authenticated_user(db)
    h = {"Authorization": f"Bearer {token}"}
    cycles = [_mk_cycle(db, user.id, "weight", v) for v in (70, 80, 72, 82)]

    r = client.post("/api/v1/crossover-experiments", headers=h, json={"metric_code": "weight", "direction": "down"})
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    assert r.json()["verdict"] == "insufficient"

    last = None
    for c, arm in zip(cycles, ("on", "off", "on", "off")):
        last = client.post(f"/api/v1/crossover-experiments/{eid}/phases", headers=h, json={"cycle_id": c.id, "arm": arm})
        assert last.status_code == 200, last.text
    assert last.json()["verdict"] == "replicated"

    # 非法 arm → 400
    rb = client.post(f"/api/v1/crossover-experiments/{eid}/phases", headers=h, json={"cycle_id": cycles[0].id, "arm": "x"})
    assert rb.status_code == 400

    # GET + 404
    assert client.get(f"/api/v1/crossover-experiments/{eid}", headers=h).json()["verdict"] == "replicated"
    assert client.get("/api/v1/crossover-experiments/99999", headers=h).status_code == 404
