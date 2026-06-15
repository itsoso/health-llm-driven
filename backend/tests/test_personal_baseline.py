"""Tests for Phase 0 personal baseline + deviation (docs/design-personal-predictive-model.md §4).

纯统计数学 + 冷启动/不确定度 + 单向指标 + user 隔离 + Twin 集成。
"""
import uuid
from datetime import date, datetime, timedelta

from app.services.personal_baseline import (
    METRIC_SPECS,
    MIN_DAYS_FOR_BASELINE,
    Z_DEVIATION_THRESHOLD,
    _MetricSpec,
    compute_metric_baseline,
    compute_personal_baselines,
)
from app.twin.formatter import twin_to_prompt_blob


# ── 纯数学 ──────────────────────────────────────────────────────────────

HRV_SPEC = next(s for s in METRIC_SPECS if s.key == "hrv")
SPO2_SPEC = next(s for s in METRIC_SPECS if s.key == "spo2_avg")


def _series(values, end=None):
    """把数值列表变成连续逐日 (date, value), 最后一天 = end (默认今天)。"""
    end = end or date.today()
    n = len(values)
    return [(end - timedelta(days=n - 1 - i), v) for i, v in enumerate(values)]


class TestBaselineMath:
    def test_mean_std_z_correct(self):
        # 20 个 50, 最后一天突降到 38。mean≈49.4, std 小 → z 明显为负。
        vals = [50.0] * 19 + [38.0]
        mb = compute_metric_baseline(HRV_SPEC, _series(vals))
        assert mb is not None
        # latest 是最后一天 = 38
        assert mb.latest == 38.0
        assert mb.n_days == 20
        # mean = (19*50 + 38)/20 = 49.4
        assert abs(mb.baseline_mean - 49.4) < 1e-6
        assert mb.z is not None and mb.z < -2.0
        assert mb.is_deviation is True
        assert mb.message and "HRV" in mb.message

    def test_within_baseline_not_deviation(self):
        # 全在常态: 50±2 抖动, 最后一天 51 → |z| 小 → 不标
        vals = [48, 50, 52, 49, 51, 50, 48, 52, 50, 49,
                51, 50, 49, 51, 50, 48, 52, 50, 49, 51]
        mb = compute_metric_baseline(HRV_SPEC, [(d, float(v)) for d, v in _series(vals)])
        assert mb is not None
        assert mb.is_deviation is False
        assert mb.z is not None and abs(mb.z) < Z_DEVIATION_THRESHOLD

    def test_z_threshold_boundary(self):
        # 构造 latest 恰好 z<=-2 触发 (high baseline, sharp drop)
        vals = [60.0] * 30 + [40.0]
        mb = compute_metric_baseline(HRV_SPEC, _series(vals))
        assert mb is not None
        assert mb.is_deviation is True

    def test_trend_falling(self):
        # 前期高 (60), 近 7 天降到 50 → trend falling
        vals = [60.0] * 23 + [50.0] * 7
        mb = compute_metric_baseline(HRV_SPEC, _series(vals))
        assert mb is not None
        assert mb.trend == "falling"

    def test_constant_series_no_z(self):
        # std≈0 → 不算 z, 不误报 deviation
        vals = [55.0] * 20
        mb = compute_metric_baseline(HRV_SPEC, _series(vals))
        assert mb is not None
        assert mb.z is None
        assert mb.is_deviation is False


class TestColdStart:
    def test_below_min_days_returns_none(self):
        vals = [50.0] * (MIN_DAYS_FOR_BASELINE - 1)
        mb = compute_metric_baseline(HRV_SPEC, _series(vals))
        assert mb is None  # 不拿 13 天当基线误导

    def test_low_confidence_flag(self):
        # 14 <= n < 30 → low_confidence True 但仍产出
        vals = [50.0, 60.0] * 8  # 16 天, std>0
        mb = compute_metric_baseline(HRV_SPEC, _series(vals))
        assert mb is not None
        assert mb.low_confidence is True

    def test_high_confidence_when_enough(self):
        vals = [50.0 + (i % 3) for i in range(40)]
        mb = compute_metric_baseline(HRV_SPEC, _series(vals))
        assert mb is not None
        assert mb.low_confidence is False


class TestLowSideOnly:
    def test_spo2_low_side_flagged(self):
        # SpO2 突降 → 标 deviation
        vals = [97.0] * 30 + [88.0]
        mb = compute_metric_baseline(SPO2_SPEC, _series(vals))
        assert mb is not None
        assert mb.is_deviation is True
        assert mb.z is not None and mb.z < 0

    def test_spo2_high_side_not_flagged(self):
        # SpO2 高于基线不是异常 (越低越危险, 只标低侧)
        vals = [92.0] * 30 + [99.0]
        mb = compute_metric_baseline(SPO2_SPEC, _series(vals))
        assert mb is not None
        assert mb.z is not None and mb.z > 2.0   # z 确实很高
        assert mb.is_deviation is False          # 但高侧不标


# ── DB service: user 隔离 + 多源合并 ──────────────────────────────────────

def _mk_user(db, prefix):
    from app.models.user import User

    u = User(
        username=f"{prefix}_{uuid.uuid4().hex[:6]}",
        email=f"{prefix}_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x", name="pb user",
        birth_date=date(1990, 1, 1), gender="男",
        is_active=True, is_approved=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _seed_garmin(db, user_id, column, values, end=None, data_source="garmin"):
    from app.models.daily_health import GarminData

    end = end or date.today()
    n = len(values)
    for i, v in enumerate(values):
        d = end - timedelta(days=n - 1 - i)
        db.add(GarminData(user_id=user_id, record_date=d,
                          data_source=data_source, **{column: v}))
    db.commit()


class TestServiceDB:
    def test_user_isolation(self, db):
        u1 = _mk_user(db, "iso1")
        u2 = _mk_user(db, "iso2")
        # u1: HRV 突降; u2: 平稳
        _seed_garmin(db, u1.id, "hrv", [60.0] * 30 + [40.0])
        _seed_garmin(db, u2.id, "hrv", [50.0] * 31)

        r1 = compute_personal_baselines(db, u1.id)
        r2 = compute_personal_baselines(db, u2.id)
        hrv1 = next(m for m in r1 if m.key == "hrv")
        hrv2 = next(m for m in r2 if m.key == "hrv")
        assert hrv1.is_deviation is True
        assert hrv2.is_deviation is False
        # u2 的值不污染 u1 基线
        assert abs(hrv1.baseline_mean - ((60 * 30 + 40) / 31)) < 1e-6

    def test_multi_source_merge_spo2_worst(self, db):
        # 同日 ringconn 88 / apple-watch 95 → 合并取最差 88 (WORST_VALUE)
        u = _mk_user(db, "ms")
        end = date.today()
        # 30 天高基线 (ringconn — 血氧整源剔除 garmin,基线须非 garmin 源), 最后一天双源
        _seed_garmin(db, u.id, "spo2_avg", [97.0] * 30,
                     end=end - timedelta(days=1), data_source="ringconn")
        from app.models.daily_health import GarminData
        db.add(GarminData(user_id=u.id, record_date=end,
                          data_source="ringconn", spo2_avg=88.0))
        db.add(GarminData(user_id=u.id, record_date=end,
                          data_source="apple-watch", spo2_avg=95.0))
        db.commit()

        res = compute_personal_baselines(db, u.id)
        spo2 = next(m for m in res if m.key == "spo2_avg")
        assert spo2.latest == 88.0     # 取最差, 不被 95 掩盖
        assert spo2.is_deviation is True

    def test_cold_start_metric_skipped(self, db):
        u = _mk_user(db, "cs")
        _seed_garmin(db, u.id, "hrv", [50.0] * 5)  # 仅 5 天
        res = compute_personal_baselines(db, u.id)
        assert all(m.key != "hrv" for m in res)  # 不产出


# ── Twin 集成 ──────────────────────────────────────────────────────────────

class TestTwinIntegration:
    # 说明: build_twin 的并行 phase 用各自的 SessionLocal()(指向真实库, 非测试
    # in-memory StaticPool), 故无法在测试里端到端跑 _fill_personal_baseline 经 build_twin
    # ——这与既有 spo2/hrv_nightly 测试同一约束。这里直接调 filler(用测试 db 会话),
    # 再断言 schema + formatter 集成。
    def test_filler_populates_twin_and_blob(self, db):
        from app.models.daily_health import GarminData
        from app.twin.builder import _fill_personal_baseline
        from app.twin.schema import HealthTwin, TwinMeta

        u = _mk_user(db, "twin")
        # HRV 突降触发 deviation, 30+ 天数据。两个指标同一行 (避免同日多行撞唯一约束)。
        hrv_vals = [60.0] * 30 + [42.0]
        end = date.today()
        n = len(hrv_vals)
        for i, v in enumerate(hrv_vals):
            d = end - timedelta(days=n - 1 - i)
            db.add(GarminData(user_id=u.id, record_date=d, data_source="garmin",
                              hrv=v, resting_heart_rate=55))
        db.commit()

        twin = HealthTwin(meta=TwinMeta(user_id=u.id, generated_at=datetime.utcnow()))
        _fill_personal_baseline(db, u.id, twin, set())

        pbs = twin.physiological.personal_baselines
        assert pbs, "personal_baselines 应被填充"
        hrv = next((m for m in pbs if m.key == "hrv"), None)
        assert hrv is not None
        assert hrv.is_deviation is True
        assert hrv.message and "HRV" in hrv.message

        blob = twin_to_prompt_blob(twin)
        assert "个人基线" in blob
        assert "HRV" in blob

    def test_no_baseline_no_blob_section(self, db):
        # 数据不足 → twin 不含个人基线, blob 不含该段, 不误导
        from app.twin.builder import _fill_personal_baseline
        from app.twin.schema import HealthTwin, TwinMeta

        u = _mk_user(db, "empty")
        _seed_garmin(db, u.id, "hrv", [50.0] * 5)
        twin = HealthTwin(meta=TwinMeta(user_id=u.id, generated_at=datetime.utcnow()))
        _fill_personal_baseline(db, u.id, twin, set())
        assert twin.physiological.personal_baselines == []
        blob = twin_to_prompt_blob(twin)
        assert "个人基线偏离" not in blob
