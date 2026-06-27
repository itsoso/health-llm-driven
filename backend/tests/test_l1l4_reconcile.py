"""R16 P5 L1↔L4 对账:日粒度快信号 vs 化验慢真值校准裁决。

concordant(同向且都超噪声→代理校准良好,封顶 moderate)/ discordant(反向 或 一边动一边没动→别信
日粒度,降 low)/ insufficient / 门控→clinician_review。只降不升、相关非因果、基因无关。
"""
from datetime import date, datetime, timedelta, timezone

from app.services.l1l4_reconcile import (
    ATTRIBUTION,
    _l1_delta,
    classify_movement,
    reconcile_user_metric,
    reconcile_verdict,
)
from tests.conftest import create_authenticated_user


# ───────────────────────── 裁决纯逻辑 ─────────────────────────


def test_concordant_both_improved():
    # weight: L1 -5, L4 -4(都降、都 > mcid 2.0)→ 校准良好
    v = reconcile_verdict(-5.0, -4.0, "weight", "down")
    assert v["verdict"] == "concordant" and v["confidence"] == "moderate"
    assert v["requires_clinician"] is False and v["attribution"] == ATTRIBUTION


def test_discordant_opposite_direction():
    # L1 -5(改善)vs L4 +4(变差)→ 矛盾,别信日粒度
    v = reconcile_verdict(-5.0, 4.0, "weight", "down")
    assert v["verdict"] == "discordant" and v["confidence"] == "low"


def test_discordant_one_moved_other_stable():
    # L1 -5(动了)但 L4 -0.5(sub-floor 没动)→ 快信号未被真值确认 → discordant
    v = reconcile_verdict(-5.0, -0.5, "weight", "down")
    assert v["verdict"] == "discordant"


def test_insufficient_neither_moved():
    v = reconcile_verdict(-0.5, -0.3, "weight", "down")  # 都 < mcid 2.0
    assert v["verdict"] == "insufficient" and v["confidence"] == "low"


def test_gated_metric_clinician_review():
    # L4=LDL 门控 → 即便同向也不下校准裁决(化验受处方混杂)
    v = reconcile_verdict(-0.5, -0.4, "lipid_ldl", "down")
    assert v["verdict"] == "clinician_review" and v["requires_clinician"] is True


def test_related_codes_l1_glucose_l4_hba1c_gated():
    # 相关指标:日粒度 glucose(非门控)vs 化验 HbA1c(门控)→ clinician_review
    v = reconcile_verdict(-1.0, -0.5, "hba1c", "down", l1_metric_code="glucose")
    assert v["verdict"] == "clinician_review"


# ───────────────────────── classify_movement / _l1_delta ─────────────────────────


def test_classify_movement():
    assert classify_movement(-5.0, "weight", "down") == (True, True)    # down=改善
    assert classify_movement(4.0, "weight", "down") == (True, False)    # up=变差
    assert classify_movement(-0.5, "weight", "down") == (False, None)   # sub-floor(<mcid 2.0)
    assert classify_movement(None, "weight", "down") == (False, None)


def test_l1_delta_dense_vs_sparse():
    t0 = date(2026, 1, 1)
    dense = [(t0 + timedelta(days=d), 80.0 - d * 0.1) for d in range(0, 40)]
    d = _l1_delta(dense)
    assert d is not None and d < 0           # 整体下行
    sparse = [(t0, 80.0), (t0 + timedelta(days=90), 75.0)]  # 仅 2 点
    assert _l1_delta(sparse) is None


def test_l1_delta_short_span_not_collapsed():
    # 对抗评审 BLOCKING:10 天密集真降 -4.5,首尾 ±7d 窗会重叠 → 必须退回 raw 端点,不被压成 0
    t0 = date(2026, 1, 1)
    short_dense = [(t0 + timedelta(days=d), 80.0 - d * 0.5) for d in range(0, 10)]
    d = _l1_delta(short_dense)
    assert d is not None and abs(d) >= 2.0   # 没被窗重叠压到 floor 以下


def test_short_span_real_improvement_concordant_not_discordant(db):
    # 端到端:10 天真降的 L1 + 化验确认 → 必须 concordant,不能因窗重叠误判 discordant
    from app.models.biomarker_observation import BiomarkerObservation

    user, _ = create_authenticated_user(db)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db.add(BiomarkerObservation(user_id=user.id, code="weight", normalized_value=80.0,
                                normalized_unit="kg", observed_at=t0))
    db.add(BiomarkerObservation(user_id=user.id, code="weight", normalized_value=75.5,
                                normalized_unit="kg", observed_at=t0 + timedelta(days=9)))
    db.commit()
    d0 = date(2026, 1, 1)
    l1 = [(d0 + timedelta(days=d), 80.0 - d * 0.5) for d in range(0, 10)]
    v = reconcile_user_metric(db, user.id, "weight", l1, "down")
    assert v["verdict"] == "concordant"


# ───────────────────────── 服务:化验对 + L1 系列 ─────────────────────────


def test_service_reconcile_concordant(db):
    from app.models.biomarker_observation import BiomarkerObservation

    user, _ = create_authenticated_user(db)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db.add(BiomarkerObservation(user_id=user.id, code="weight", normalized_value=80.0,
                                normalized_unit="kg", observed_at=t0))
    db.add(BiomarkerObservation(user_id=user.id, code="weight", normalized_value=74.0,
                                normalized_unit="kg", observed_at=t0 + timedelta(days=90)))
    db.commit()
    d0 = date(2026, 1, 1)
    l1 = [(d0 + timedelta(days=d), 80.0 - d * 0.07) for d in range(0, 90)]  # 日粒度下行 ~6.2
    v = reconcile_user_metric(db, user.id, "weight", l1, "down")
    assert v["verdict"] == "concordant"   # L4 -6、L1 -6.2 同向


def test_service_insufficient_when_one_lab(db):
    from app.models.biomarker_observation import BiomarkerObservation

    user, _ = create_authenticated_user(db)
    db.add(BiomarkerObservation(user_id=user.id, code="weight", normalized_value=80.0,
                                normalized_unit="kg", observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    db.commit()
    d0 = date(2026, 1, 1)
    l1 = [(d0 + timedelta(days=d), 80.0 - d * 0.07) for d in range(0, 90)]
    v = reconcile_user_metric(db, user.id, "weight", l1, "down")
    assert v["verdict"] in ("insufficient", "discordant")  # 仅 1 次化验 → L4 delta None → 不下 concordant
    assert v["confidence"] == "low"
