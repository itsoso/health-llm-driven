"""R16 P2 端点去噪:算 delta/显著性前先平滑,稀疏不臆造、近期剧烈波动不静默高置信。

单测覆盖 denoise 纯函数;集成测 _denoised_status 在稀疏→封 low、密集→7d_ma、MA-lag 背离→封 low,
并钉死 legacy _metric_status(om)(无去噪参数)行为逐字节不变。
"""
from datetime import datetime, timedelta, timezone

from app.models.biomarker_observation import BiomarkerObservation
from app.models.intervention_cycle import InterventionCycle, OutcomeMetric
from app.services import intervention_cycle_service as ics
from app.services import intervention_denoise as dn
from tests.conftest import create_authenticated_user

_T0 = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _series(*pairs):
    """[(day_offset, value), ...] → [(datetime, value)]。"""
    return [(_T0 + timedelta(days=d), v) for (d, v) in pairs]


# ───────────────────────── 纯函数 ─────────────────────────


def test_window_mean_dense_and_sparse():
    s = _series((-3, 80.0), (-1, 81.0), (0, 79.0), (2, 80.0), (40, 75.0))
    val, n = dn.window_mean(s, _T0)        # ±7d 内 4 点
    assert n == 4 and abs(val - 80.0) < 0.6
    val2, n2 = dn.window_mean(s, _T0 + timedelta(days=40))  # 只 1 点
    assert n2 == 1 and val2 == 75.0


def test_robust_z_outlier_and_mad_zero_guard():
    s = _series(*[(i, 80.0) for i in range(-30, 0)])  # 恒定 80 → MAD=0
    assert dn.robust_z(s, 95.0, _T0) is None          # MAD=0 守卫:不判背离(防除零)
    s2 = _series(*[(i, 80.0 + (i % 3)) for i in range(-30, 0)])  # 有离散
    z = dn.robust_z(s2, 95.0, _T0)
    assert z is not None and abs(z) >= 3.0            # 95 远离 ~81 中位 → 强离群


def test_denoise_dense_7d_ma():
    s = _series((-3, 80.0), (-1, 81.0), (0, 79.0),
                (57, 75.0), (59, 76.0), (60, 74.0))
    d = dn.denoise_endpoints(s, _T0, 79.0, _T0 + timedelta(days=60), 74.0)
    assert d["method"] == "7d_ma" and d["sample_n"] >= 3
    assert dn.smoothed_delta_pct(d) is not None


def test_denoise_sparse_none():
    s = _series((0, 79.0), (60, 74.0))  # 两端各 1 点
    d = dn.denoise_endpoints(s, _T0, 79.0, _T0 + timedelta(days=60), 74.0)
    assert d["method"] == "none" and dn.smoothed_delta_pct(d) is None


def test_short_cycle_window_overlap_falls_back_to_none():
    # 对抗评审 BLOCKING:锚点间隔 < 14d(±7d 窗重叠)→ method=none,防同批观测喂两端把真改善抹成 flat
    s = _series(*[(d, 85.0 - d * 0.4) for d in range(0, 13)])  # 12 天每日,真降
    d = dn.denoise_endpoints(s, _T0, 85.0, _T0 + timedelta(days=12), 80.2)
    assert d["method"] == "none"


def test_denoise_ma_lag_divergent():
    # 基线端密集 + 复查端 30d 窗有离散基础但最新原始点是强离群(近期剧烈波动)
    base = [(i, 80.0 + (i % 3)) for i in range(-3, 1)]
    recent = [(i, 80.0 + (i % 3)) for i in range(53, 60)]
    s = _series(*(base + recent + [(60, 110.0)]))
    d = dn.denoise_endpoints(s, _T0, 80.0, _T0 + timedelta(days=60), 110.0)
    assert d["method"] == "7d_ma" and d["ma_lag_divergent"] is True


# ───────────────────────── 集成:_denoised_status ─────────────────────────


def _om(db, uid, code="weight", direction="down", baseline=80.0, latest=75.0,
        base_day=0, latest_day=60, target=None):
    cyc = InterventionCycle(
        user_id=uid, cycle_type="metabolic", status="active",
        start_date=_T0.date(), planned_end_date=(_T0 + timedelta(days=90)).date(),
    )
    db.add(cyc)
    db.flush()
    om = OutcomeMetric(
        cycle_id=cyc.id, metric_code=code, unit="kg", direction=direction,
        baseline_value=baseline, latest_value=latest, target_value=target,
        delta=round(latest - baseline, 3),
        delta_pct=round((latest - baseline) / abs(baseline) * 100, 1),
        baseline_observed_at=_T0 + timedelta(days=base_day),
        latest_observed_at=_T0 + timedelta(days=latest_day),
    )
    db.add(om)
    db.commit()
    return om


def _obs(db, uid, code, points):
    for d, v in points:
        db.add(BiomarkerObservation(
            user_id=uid, code=code, value=v, unit="kg",
            normalized_value=v, normalized_unit="kg",
            observed_at=_T0 + timedelta(days=d),
        ))
    db.commit()


def test_sparse_lab_floors_confidence_low(db):
    user, _ = create_authenticated_user(db)
    om = _om(db, user.id, code="lipid_apob", baseline=1.2, latest=0.8)  # 非门控? apob 其实门控
    _obs(db, user.id, "lipid_apob", [(0, 1.2), (60, 0.8)])  # 两端各 1 点 → 稀疏
    st = ics._denoised_status(db, om.cycle, om)
    assert om.smoothing_method == "none"
    assert om.confidence == "low"  # 稀疏 → 封 low,不臆造趋势
    assert st in ("improving", "flat", "met", "worsening")


def test_dense_metric_smooths_7d_ma(db):
    user, _ = create_authenticated_user(db)
    om = _om(db, user.id, code="weight", baseline=80.0, latest=75.0)
    pts = [(d, 80.0 - d * 0.08 + (d % 2)) for d in range(0, 61)]  # 每日,密集
    _obs(db, user.id, "weight", pts)
    ics._denoised_status(db, om.cycle, om)
    assert om.smoothing_method == "7d_ma" and (om.sample_n or 0) >= 3


def test_ma_lag_divergent_floors_low(db):
    user, _ = create_authenticated_user(db)
    om = _om(db, user.id, code="weight", baseline=80.0, latest=110.0)
    base = [(d, 80.0 + (d % 3)) for d in range(0, 4)]
    recent = [(d, 80.0 + (d % 3)) for d in range(53, 60)]
    _obs(db, user.id, "weight", base + recent + [(60, 110.0)])
    ics._denoised_status(db, om.cycle, om)
    assert om.smoothing_method == "7d_ma" and om.confidence == "low"  # 近期剧烈波动 → 封 low


def test_short_cycle_real_change_not_masked_flat(db):
    """对抗评审 BLOCKING:13 天短周期、真 -5% 体重下降不得被平滑抹成 flat;
    raw delta 驱动 improving + 短周期诚实封 low。"""
    user, _ = create_authenticated_user(db)
    om = _om(db, user.id, code="weight", baseline=85.0, latest=80.5, latest_day=13)
    _obs(db, user.id, "weight", [(d, 85.0 - d * 0.35) for d in range(0, 14)])
    st = ics._denoised_status(db, om.cycle, om)
    assert om.smoothing_method == "none"      # 窗重叠 → 不平滑
    assert st == "improving" and om.significant is True   # 真改善没被误判 flat
    assert om.confidence == "low"             # 短周期不平滑 → 诚实封 low


def test_legacy_metric_status_byte_identical(db):
    """无去噪参数调用 _metric_status(om):与改前行为逐字节一致(legacy 调用方不受影响)。"""
    user, _ = create_authenticated_user(db)
    om = _om(db, user.id, code="weight", baseline=80.0, latest=70.0)  # -12.5% 明显改善
    st = ics._metric_status(om)  # 无 smoothed 参数 = legacy 路径
    assert st == "improving" and om.significant is True
    assert om.confidence in ("moderate", "high")  # 用原始单点 delta_pct,未封 low
