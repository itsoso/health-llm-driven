"""Tests for Phase 1 N-of-1 effect estimator (docs/design-personal-predictive-model.md §4 Phase 1).

层级贝叶斯 (Normal-Normal 共轭) + 人群先验收缩 + 方向感知 is_effective + 降级不抛。
"""
import uuid
from datetime import date

from app.services.effect_estimator import (
    DEFAULT_PRIOR_MEAN,
    DEFAULT_PRIOR_VAR,
    POP_PRIOR_MIN_OBS,
    conjugate_posterior,
    effect_estimate_prompt_blob,
    effect_estimates_for_user,
    estimate_effect,
    estimate_from_deltas,
)


# ── 纯数学: 共轭后验 ──────────────────────────────────────────────────────

class TestConjugatePosterior:
    def test_n0_returns_prior(self):
        # N=0 → 后验 = 先验 (mean=prior, var=prior_var)
        mean, var, _ = conjugate_posterior([], prior_mean=0.0, prior_var=4.0)
        assert mean == 0.0
        assert var == 4.0

    def test_shrinks_between_prior_and_data(self):
        # 个人均值 -1.0, 先验 0.0 → 后验在两者之间
        mean, var, _ = conjugate_posterior(
            [-1.0, -1.0, -1.0], prior_mean=0.0, prior_var=4.0, obs_var=1.0,
        )
        assert -1.0 < mean < 0.0
        # 有数据 → 后验方差 < 先验方差
        assert var < 4.0

    def test_more_data_narrows_variance(self):
        _, var_n1, _ = conjugate_posterior([-1.0], prior_mean=0.0, prior_var=4.0, obs_var=1.0)
        _, var_n5, _ = conjugate_posterior([-1.0] * 5, prior_mean=0.0, prior_var=4.0, obs_var=1.0)
        assert var_n5 < var_n1

    def test_more_data_pulls_toward_personal_mean(self):
        mean_n1, _, _ = conjugate_posterior([-1.0], prior_mean=0.0, prior_var=4.0, obs_var=1.0)
        mean_n8, _, _ = conjugate_posterior([-1.0] * 8, prior_mean=0.0, prior_var=4.0, obs_var=1.0)
        # n 越大越靠近个人均值 -1.0
        assert abs(mean_n8 - (-1.0)) < abs(mean_n1 - (-1.0))


# ── estimate_from_deltas: 退化先验 / 收缩 / 方向 / 人群先验 ───────────────────

class TestEstimateFromDeltas:
    def test_n0_degenerate_prior_wide_ci_not_effective(self):
        # N=0, 无人群 → 默认先验 (0, 大方差), 宽 CI, is_effective=False
        est = estimate_from_deltas("lipid_ldl", [], direction="down")
        assert est.n_observations == 0
        assert est.effect == DEFAULT_PRIOR_MEAN
        assert est.prior_var == DEFAULT_PRIOR_VAR
        assert est.is_effective is False
        assert est.confidence == "low"
        # 宽 CI 跨 0
        assert est.ci_low < 0 < est.ci_high
        assert "尚未在你身上验证" in est.interpretation

    def test_n1_shrinks_toward_personal(self):
        # 单观测 -0.8, 默认先验 0 → 后验在 (-0.8, 0)
        est = estimate_from_deltas("lipid_ldl", [-0.8], direction="down")
        assert est.n_observations == 1
        assert -0.8 < est.effect < 0.0

    def test_ci_narrows_with_more_observations(self):
        e1 = estimate_from_deltas("lipid_ldl", [-0.6], direction="down")
        e3 = estimate_from_deltas("lipid_ldl", [-0.6, -0.6, -0.6], direction="down")
        width1 = e1.ci_high - e1.ci_low
        width3 = e3.ci_high - e3.ci_low
        assert width3 < width1
        # n=3 一致强信号 → 后验更靠近 -0.6
        assert abs(e3.effect - (-0.6)) < abs(e1.effect - (-0.6))

    def test_direction_down_effective(self):
        # 一致较大下降 → CI 整段 < 0 → down 方向有效
        est = estimate_from_deltas(
            "lipid_ldl", [-1.2, -1.1, -1.3, -1.2], direction="down",
        )
        assert est.effect < 0
        assert est.ci_high < 0
        assert est.is_effective is True
        assert "有效" in est.interpretation

    def test_direction_up_effective(self):
        # 升为好 (e.g. HDL), 一致上升 → CI 整段 > 0 → up 方向有效
        est = estimate_from_deltas(
            "lipid_hdl", [0.5, 0.55, 0.6, 0.5], direction="up",
        )
        assert est.effect > 0
        assert est.ci_low > 0
        assert est.is_effective is True

    def test_direction_up_wrong_sign_not_effective(self):
        # 期望升, 实际降 → 对 up 方向不算有效
        est = estimate_from_deltas(
            "lipid_hdl", [-0.5, -0.4, -0.6], direction="up",
        )
        assert est.effect < 0
        assert est.is_effective is False

    def test_population_prior_used_when_enough(self):
        # 人群 >= POP_PRIOR_MIN_OBS → 用人群均值作先验 (非默认 0)
        pop = [-1.0] * POP_PRIOR_MIN_OBS
        est = estimate_from_deltas(
            "lipid_ldl", [], direction="down", population_deltas=pop,
        )
        assert est.population_n == POP_PRIOR_MIN_OBS
        assert abs(est.prior_mean - (-1.0)) < 1e-9
        # N=0 → 后验 = 人群先验均值
        assert abs(est.effect - (-1.0)) < 1e-9

    def test_population_too_few_falls_back_default_prior(self):
        # 人群 < 阈值 → 退化默认先验 (μ₀=0, 大方差), population_n=0
        pop = [-1.0] * (POP_PRIOR_MIN_OBS - 1)
        est = estimate_from_deltas(
            "lipid_ldl", [], direction="down", population_deltas=pop,
        )
        assert est.population_n == 0
        assert est.prior_mean == DEFAULT_PRIOR_MEAN
        assert est.prior_var == DEFAULT_PRIOR_VAR

    def test_to_dict_shape(self):
        est = estimate_from_deltas("lipid_ldl", [-0.5, -0.6], direction="down")
        d = est.to_dict()
        for k in (
            "metric_code", "direction", "effect", "ci_low", "ci_high", "ci_level",
            "n_observations", "n_cycles", "confidence", "is_effective", "interpretation",
            "prior_mean", "population_n",
        ):
            assert k in d


# ── DB service: 隔离 / 人群先验 / 汇总 / 降级 ──────────────────────────────

def _mk_user(db, prefix):
    from app.models.user import User

    u = User(
        username=f"{prefix}_{uuid.uuid4().hex[:6]}",
        email=f"{prefix}_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x", name="ee user",
        birth_date=date(1990, 1, 1), gender="男",
        is_active=True, is_approved=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _mk_cycle_with_deltas(db, user_id, metric_code, deltas, *,
                          cycle_type="metabolic_90d", direction="down", unit="mmol/L"):
    """为 user 建一个周期, 每个 delta 建一个独立周期里的 OutcomeMetric (一周期一观测)。

    deltas: list of float — 每个值建一个周期 + 一条 OutcomeMetric。
    """
    from app.models.intervention_cycle import InterventionCycle, OutcomeMetric

    cycles = []
    for dlt in deltas:
        cyc = InterventionCycle(
            user_id=user_id, cycle_type=cycle_type, status="completed",
            start_date=date(2026, 1, 1),
        )
        db.add(cyc); db.commit(); db.refresh(cyc)
        db.add(OutcomeMetric(
            cycle_id=cyc.id, metric_code=metric_code, unit=unit,
            baseline_value=5.0, latest_value=5.0 + dlt, delta=dlt,
            direction=direction, status="improving",
        ))
        cycles.append(cyc)
    db.commit()
    return cycles


class TestEstimateEffectDB:
    def test_user_isolation_and_population_prior(self, db):
        # u_other 群体提供先验 (3 个 -1.0); u_self 自己 1 个 -0.5
        u_self = _mk_user(db, "ee_self")
        u_other = _mk_user(db, "ee_other")
        _mk_cycle_with_deltas(db, u_other.id, "lipid_ldl", [-1.0, -1.0, -1.0])
        _mk_cycle_with_deltas(db, u_self.id, "lipid_ldl", [-0.5])

        res = estimate_effect(db, u_self.id, "lipid_ldl", cycle_type="metabolic_90d")
        assert res["n_observations"] == 1   # 只数自己的
        assert res["population_n"] == 3      # 人群先验来自他人
        # 后验严格收缩在人群先验 (-1.0) 与个人均值 (-0.5) 之间
        assert -1.0 < res["effect"] < -0.5

    def test_no_cycles_returns_prior_not_effective(self, db):
        u = _mk_user(db, "ee_empty")
        res = estimate_effect(db, u.id, "lipid_ldl", cycle_type="metabolic_90d")
        assert res["n_observations"] == 0
        assert res["population_n"] == 0
        assert res["is_effective"] is False

    def test_direction_picked_up_from_db(self, db):
        u = _mk_user(db, "ee_dir")
        _mk_cycle_with_deltas(db, u.id, "lipid_hdl", [0.4, 0.5, 0.45],
                              direction="up", unit="mmol/L")
        res = estimate_effect(db, u.id, "lipid_hdl", cycle_type="metabolic_90d")
        assert res["direction"] == "up"
        assert res["effect"] > 0


class TestSummaryAndBlob:
    def test_effect_estimates_for_user_active_cycle(self, db):
        from app.models.intervention_cycle import InterventionCycle, OutcomeMetric

        u = _mk_user(db, "ee_sum")
        cyc = InterventionCycle(
            user_id=u.id, cycle_type="metabolic_90d", status="active",
            start_date=date(2026, 1, 1),
        )
        db.add(cyc); db.commit(); db.refresh(cyc)
        for code, dlt, dirn in [("lipid_ldl", -0.6, "down"), ("lipid_hdl", 0.3, "up")]:
            db.add(OutcomeMetric(
                cycle_id=cyc.id, metric_code=code, unit="mmol/L",
                baseline_value=5.0, latest_value=5.0 + dlt, delta=dlt,
                direction=dirn, status="improving",
            ))
        db.commit()

        res = effect_estimates_for_user(db, u.id)
        codes = {e["metric_code"] for e in res}
        assert codes == {"lipid_ldl", "lipid_hdl"}

    def test_effect_estimates_for_user_no_cycle_empty(self, db):
        u = _mk_user(db, "ee_nocyc")
        assert effect_estimates_for_user(db, u.id) == []

    def test_prompt_blob_present_when_cycle(self, db):
        from app.models.intervention_cycle import InterventionCycle, OutcomeMetric

        u = _mk_user(db, "ee_blob")
        cyc = InterventionCycle(
            user_id=u.id, cycle_type="metabolic_90d", status="active",
            start_date=date(2026, 1, 1),
        )
        db.add(cyc); db.commit(); db.refresh(cyc)
        db.add(OutcomeMetric(
            cycle_id=cyc.id, metric_code="lipid_ldl", unit="mmol/L",
            baseline_value=5.0, latest_value=3.8, delta=-1.2,
            direction="down", status="improving",
        ))
        db.commit()

        blob = effect_estimate_prompt_blob(db, u.id)
        assert "干预效应估计" in blob
        assert "effect=" in blob

    def test_prompt_blob_empty_when_no_cycle(self, db):
        u = _mk_user(db, "ee_blobempty")
        assert effect_estimate_prompt_blob(db, u.id) == ""


class TestDegradation:
    def test_estimate_effect_does_not_raise_on_broken_db(self):
        # 传入会抛的假 db → 不崩, 回退纯先验 (N=0)
        class _BrokenDB:
            def query(self, *a, **k):
                raise RuntimeError("boom")

            def rollback(self):
                pass

        res = estimate_effect(_BrokenDB(), 1, "lipid_ldl")
        assert res["n_observations"] == 0
        assert res["is_effective"] is False

    def test_prompt_blob_empty_on_broken_db(self):
        class _BrokenDB:
            def query(self, *a, **k):
                raise RuntimeError("boom")

            def rollback(self):
                pass

        assert effect_estimate_prompt_blob(_BrokenDB(), 1) == ""
