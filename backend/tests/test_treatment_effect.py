"""Phase 1 — N-of-1 干预效应估计器 (层级贝叶斯) 测试.

TDD: 先写这些断言跑红, 再实现 personal_models/{intervention_priors,treatment_effect}.py 到绿。

设计契约 (docs/design-personal-predictive-model.md §Phase 1 + 安全审核裁决):
- 人群先验 (EffectPrior) + 个人观测 (observed_delta) → 共轭高斯后验 (个人化效应 + 80% CI)。
- 方向归一: direction="down" 时改善 = -delta; "up" 时改善 = +delta。
- verdict 中性、周期限定: improved_in_cycle / worsened_in_cycle / inconclusive /
  insufficient_data / clinician_review。
- 处方/激素相关 (requires_clinician=True) 一律降级 clinician_review; message 不出
  "效应估计 X" 因果归属句, 改描述 + 混杂提示 + 交医生。
- 低/中置信非处方 message 弱化为描述式 ("看起来"/"把握有限"); 确定语气只给 high。
- 措辞红线: 标"相关,非因果"(或处方分支"请由医生判断") + 不说"证明/治愈/保证"。
"""
import math

import pytest

from app.services.personal_models.intervention_priors import (
    DEFAULT_PRIOR,
    EffectPrior,
    get_prior,
)
from app.services.personal_models.treatment_effect import (
    DISPLAY_LABELS,
    EffectEstimate,
    estimate_cycle_effects,
    estimate_effect,
    metric_display_name,
)


# --------------------------------------------------------------------------
# 1. 共轭数学 — 手算对照 (prior μ=0, τ=1, obs_noise=0.2, mcid=0.3, delta=-0.6)
# --------------------------------------------------------------------------
def test_conjugate_math_exact_values():
    prior = EffectPrior(
        mu_pop=0.0,
        tau_pop=1.0,
        obs_noise=0.2,
        mcid=0.3,
        evidence_tier="B",
        requires_clinician=False,
    )
    est = estimate_effect(observed_delta=-0.6, prior=prior)

    # sigma_obs = sqrt(2)*0.2; prec_obs = 1/sigma_obs^2 = 12.5; prec_prior = 1.0
    # post_mean = (0*1.0 + (-0.6)*12.5) / 13.5 = -0.5555...
    # post_var  = 1/13.5 = 0.074074...
    assert est.posterior_effect == pytest.approx(-0.6 * 12.5 / 13.5, rel=1e-9)
    assert est.posterior_effect == pytest.approx(-0.555555556, abs=1e-6)

    post_var = 1.0 / 13.5
    half = 1.2816 * math.sqrt(post_var)
    assert est.ci_low == pytest.approx(-0.555555556 - half, abs=1e-6)
    assert est.ci_high == pytest.approx(-0.555555556 + half, abs=1e-6)
    assert est.ci_level == 0.8
    assert est.observed_delta == -0.6
    assert est.model_version == "phase1-hbayes-v1"


# --------------------------------------------------------------------------
# 2. 收缩 (shrinkage) — 极端观测被向 μ_pop 拉回
# --------------------------------------------------------------------------
def test_extreme_observation_shrinks_toward_population_mean():
    prior = EffectPrior(
        mu_pop=-0.3, tau_pop=0.5, obs_noise=0.4, mcid=0.3, evidence_tier="B"
    )
    observed = -2.0  # 远超人群典型
    est = estimate_effect(observed_delta=observed, prior=prior)

    # 后验应落在 μ_pop 与 observed 之间, 绝对值被收缩
    assert abs(est.posterior_effect) < abs(observed)
    assert prior.mu_pop > est.posterior_effect > observed  # -0.3 > post > -2.0


# --------------------------------------------------------------------------
# 3. improved_in_cycle — 强改善 + 窄噪声 → 改善侧 80% CI 整段越过 MCID
# --------------------------------------------------------------------------
def test_strong_improvement_with_tight_noise_is_improved_in_cycle():
    prior = EffectPrior(
        mu_pop=-0.4, tau_pop=1.0, obs_noise=0.08, mcid=0.3,
        evidence_tier="A", requires_clinician=False,
    )
    est = estimate_effect(observed_delta=-1.2, prior=prior)  # direction default down
    assert est.verdict == "improved_in_cycle"
    # 改善侧 CI 整段 > MCID: 即 ci_high (最弱改善端) 仍越过 mcid
    assert -est.ci_high > prior.mcid


# --------------------------------------------------------------------------
# 4. inconclusive — 噪声大 / 效应小 → CI 跨 0
# --------------------------------------------------------------------------
def test_small_effect_large_noise_is_inconclusive():
    prior = EffectPrior(
        mu_pop=0.0, tau_pop=1.0, obs_noise=1.0, mcid=0.3, evidence_tier="C"
    )
    est = estimate_effect(observed_delta=-0.15, prior=prior)
    assert est.verdict == "inconclusive"
    assert est.ci_low < 0 < est.ci_high  # CI 跨 0


# --------------------------------------------------------------------------
# 5. worsened_in_cycle — 反方向越过 MCID (direction=down 但 delta 显著为正)
# --------------------------------------------------------------------------
def test_significant_wrong_direction_is_worsened_in_cycle():
    prior = EffectPrior(
        mu_pop=0.0, tau_pop=1.0, obs_noise=0.1, mcid=0.3, evidence_tier="B",
        direction="down",
    )
    est = estimate_effect(observed_delta=+1.0, prior=prior)
    assert est.verdict == "worsened_in_cycle"


# --------------------------------------------------------------------------
# 6. insufficient — sigma_obs<=0 退化 → 标 insufficient, 不抛
# --------------------------------------------------------------------------
def test_degenerate_obs_noise_is_insufficient_not_raising():
    prior = EffectPrior(
        mu_pop=0.0, tau_pop=1.0, obs_noise=0.0, mcid=0.3, evidence_tier="C"
    )
    est = estimate_effect(observed_delta=-0.6, prior=prior)
    assert est.verdict == "insufficient_data"
    assert "非因果" in est.message  # 措辞红线仍守


# --------------------------------------------------------------------------
# 7. 方向 direction="up" (HRV 升为好) — delta=+8 应判改善
# --------------------------------------------------------------------------
def test_direction_up_positive_delta_is_improvement():
    prior = EffectPrior(
        mu_pop=4.0, tau_pop=10.0, obs_noise=1.5, mcid=3.0, evidence_tier="B",
        direction="up",
    )
    est = estimate_effect(observed_delta=8.0, prior=prior)
    assert est.posterior_effect > 0
    assert est.verdict == "improved_in_cycle"


# --------------------------------------------------------------------------
# 8. default prior — 未知 (cycle_type, metric) → 怀疑先验 μ=0, 收缩向 0
# --------------------------------------------------------------------------
def test_unknown_pair_uses_default_skeptical_prior():
    prior = get_prior("nonexistent_cycle", "nonexistent_metric")
    assert prior is DEFAULT_PRIOR
    assert prior.mu_pop == 0.0  # 怀疑先验: 不假设有效
    assert prior.evidence_tier == "C"

    est = estimate_effect(observed_delta=-1.5, prior=prior)
    # 怀疑先验把效应向 0 收缩, 不臆造效应
    assert abs(est.posterior_effect) < abs(-1.5)


def test_known_pairs_present_in_priors():
    """循证先验至少覆盖几条 metabolic / sleep 键。"""
    from app.services.personal_models.intervention_priors import PRIORS

    for key in [("metabolic_90d", "ldl"), ("metabolic_90d", "weight")]:
        assert key in PRIORS
        p = PRIORS[key]
        assert p.tau_pop > 0
        assert p.obs_noise > 0
        assert p.mcid > 0


# --------------------------------------------------------------------------
# 8b. get_prior 处方关键词兜底 (S3) — 未登记的处方/激素指标强制 requires_clinician
# --------------------------------------------------------------------------
@pytest.mark.parametrize("metric_code", ["sbp", "apob", "testosterone", "tsh", "cortisol"])
def test_get_prior_prescription_keyword_forces_clinician(metric_code):
    """S3: 未登记的处方/激素指标即使走 DEFAULT_PRIOR 也强制 requires_clinician=True。"""
    prior = get_prior("some_unknown_cycle", metric_code)
    assert prior.requires_clinician is True


def test_get_prior_explicit_bp_entries():
    """S3: ('metabolic_90d','sbp'/'dbp') 显式登记, direction=down, requires_clinician。"""
    from app.services.personal_models.intervention_priors import PRIORS

    for code in ("sbp", "dbp"):
        assert ("metabolic_90d", code) in PRIORS
        p = PRIORS[("metabolic_90d", code)]
        assert p.direction == "down"
        assert p.requires_clinician is True


def test_get_prior_non_prescription_metric_stays_false():
    """非处方未登记指标 (如随机字符) 不被误标 requires_clinician。"""
    prior = get_prior("x", "some_random_wellness_metric")
    assert prior.requires_clinician is False


# --------------------------------------------------------------------------
# 8c. 先验参数收口 (S4 / N2)
# --------------------------------------------------------------------------
def test_hba1c_mcid_is_ada_clinically_significant():
    """S4: HbA1c mcid 提到 0.5 (ADA 临床显著)。"""
    from app.services.personal_models.intervention_priors import PRIORS

    assert PRIORS[("metabolic_90d", "hba1c")].mcid == 0.5


def test_apob_prior_present_and_clinician_gated():
    """S4: 新增 apob 先验, requires_clinician=True, direction=down, tier B。"""
    from app.services.personal_models.intervention_priors import PRIORS

    assert ("metabolic_90d", "apob") in PRIORS
    p = PRIORS[("metabolic_90d", "apob")]
    assert p.requires_clinician is True
    assert p.direction == "down"
    assert p.evidence_tier == "B"


# --------------------------------------------------------------------------
# 9. 措辞安全 — 安全审核硬靶
# --------------------------------------------------------------------------
def _all_messages():
    msgs = []
    cases = [
        # (mu, tau, noise, mcid, tier, clinician, direction, delta)
        (-0.4, 1.0, 0.08, 0.3, "A", False, "down", -1.2),   # improved_in_cycle (high)
        (0.0, 1.0, 1.0, 0.3, "C", False, "down", -0.15),    # inconclusive
        (0.0, 1.0, 0.1, 0.3, "B", True, "down", -0.9),      # requires_clinician
        (0.0, 1.0, 0.0, 0.3, "C", False, "down", -0.6),     # insufficient
        (0.0, 1.0, 0.1, 0.3, "B", False, "down", +1.0),     # worsened_in_cycle (high)
    ]
    for mu, tau, noise, mcid, tier, clin, direction, delta in cases:
        prior = EffectPrior(
            mu_pop=mu, tau_pop=tau, obs_noise=noise, mcid=mcid,
            evidence_tier=tier, requires_clinician=clin, direction=direction,
        )
        msgs.append(estimate_effect(observed_delta=delta, prior=prior, metric_code="ldl"))
    return msgs


def test_messages_are_correlational_and_non_prescriptive():
    """所有 message 含"非因果"(非处方)或"请由医生判断"(处方); 永不出禁词。"""
    for est in _all_messages():
        assert "非因果" in est.message or "请由医生判断" in est.message
        for banned in ("证明", "治愈", "保证"):
            assert banned not in est.message


def test_prescription_metric_is_clinician_review_not_improved():
    """D1: 处方指标即使统计判改善, verdict 降级 clinician_review;
    message 不出"效应估计"因果句, 含混杂提示 + 交医生。"""
    prior = EffectPrior(
        mu_pop=-0.4, tau_pop=1.0, obs_noise=0.08, mcid=0.3, evidence_tier="B",
        requires_clinician=True, direction="down",
    )
    est = estimate_effect(observed_delta=-1.0, prior=prior, metric_code="ldl")
    assert est.requires_clinician is True
    assert est.verdict == "clinician_review"
    assert "效应估计" not in est.message       # 删掉因果归属句
    assert "请由医生判断" in est.message
    # 明确混杂 + 不区分
    assert "多重因素" in est.message or "用药" in est.message
    assert "本系统不区分" in est.message
    # post_mean/CI 仍保留在结构化字段供内部 (不进 message)
    assert est.posterior_effect is not None
    assert est.ci_low is not None and est.ci_high is not None


def test_non_prescription_high_conf_keeps_personal_estimate_wording():
    """非处方 + high conf 改善 → improved_in_cycle, message 含"个人化估计"+CI+"非因果"。"""
    prior = EffectPrior(
        mu_pop=-0.4, tau_pop=1.0, obs_noise=0.08, mcid=0.3, evidence_tier="A",
        requires_clinician=False, direction="down",
    )
    est = estimate_effect(observed_delta=-5.0, prior=prior, metric_code="weight")
    assert est.verdict == "improved_in_cycle"
    assert est.confidence == "high"
    assert "个人化估计" in est.message
    assert "80% 区间" in est.message
    assert "非因果" in est.message


def test_non_prescription_low_conf_is_hedged_descriptive():
    """D2: 非处方 + low/med conf 但仍判改善 → message 含"看起来"+"把握有限"+CI,
    不出确定的"效应估计"裁决句。"""
    # 大效应 + 中等噪声: improvement 侧 CI 整段越过 MCID (improved), 但 ci_width >= mcid
    # → confidence=med/low。mu_pop 偏负让后验仍稳越 MCID。
    prior = EffectPrior(
        mu_pop=-5.0, tau_pop=6.0, obs_noise=2.0, mcid=2.0, evidence_tier="C",
        requires_clinician=False, direction="down",
    )
    est = estimate_effect(observed_delta=-6.0, prior=prior, metric_code="weight")
    assert est.verdict == "improved_in_cycle"
    assert est.confidence in ("low", "med")
    assert "看起来" in est.message
    assert "把握有限" in est.message
    assert "区间" in est.message
    assert "效应估计" not in est.message      # 确定裁决句只给 high
    assert "非因果" in est.message


def test_requires_clinician_message_directs_to_doctor():
    prior = EffectPrior(
        mu_pop=0.0, tau_pop=1.0, obs_noise=0.1, mcid=0.3, evidence_tier="B",
        requires_clinician=True, direction="down",
    )
    est = estimate_effect(observed_delta=-0.9, prior=prior, metric_code="ldl")
    assert est.requires_clinician is True
    assert est.verdict == "clinician_review"
    assert "请由医生判断" in est.message


def test_inconclusive_message_says_no_conclusion():
    prior = EffectPrior(
        mu_pop=0.0, tau_pop=1.0, obs_noise=1.0, mcid=0.3, evidence_tier="C",
    )
    est = estimate_effect(observed_delta=-0.15, prior=prior)
    assert est.verdict == "inconclusive"
    assert "暂不下结论" in est.message


# --------------------------------------------------------------------------
# 9b. verdict 重命名 + display_label (S1) + 中文显示名 (N1)
# --------------------------------------------------------------------------
def test_display_label_is_hedged_for_every_verdict():
    """S1: 每个 verdict 都有 hedge 措辞的 display_label。"""
    for v in (
        "improved_in_cycle",
        "worsened_in_cycle",
        "clinician_review",
        "inconclusive",
        "insufficient_data",
    ):
        assert v in DISPLAY_LABELS
        label = DISPLAY_LABELS[v]
        assert label and label.strip()
        # 不得是裸英文 verdict, 必须是中文 hedge
        assert v not in label
    # 关键 hedge 措辞校验
    assert DISPLAY_LABELS["improved_in_cycle"] == "周期内观察到改善"
    assert DISPLAY_LABELS["clinician_review"] == "需医生评估"
    assert DISPLAY_LABELS["inconclusive"] == "暂不下结论"
    assert DISPLAY_LABELS["insufficient_data"] == "数据不足"


def test_estimate_carries_display_label():
    prior = EffectPrior(
        mu_pop=-0.4, tau_pop=1.0, obs_noise=0.08, mcid=0.3, evidence_tier="A",
    )
    est = estimate_effect(observed_delta=-5.0, prior=prior, metric_code="weight")
    assert est.display_label == DISPLAY_LABELS[est.verdict]
    assert est.to_dict()["display_label"] == est.display_label


def test_metric_display_name_chinese():
    """N1: metric_code → 中文显示名; message 用中文名, 不裸大写 code。"""
    assert metric_display_name("ldl") == "LDL"
    assert metric_display_name("hba1c") == "糖化血红蛋白"
    assert metric_display_name("weight") == "体重"
    assert metric_display_name("sbp") == "收缩压"
    # 未登记 → 回退原 code (不报错)
    assert metric_display_name("unknown_metric") == "unknown_metric"
    # message 里用的是中文名而非裸 LDL/HBA1C... (weight 走非处方分支)
    prior = EffectPrior(
        mu_pop=-0.4, tau_pop=1.0, obs_noise=0.08, mcid=0.3, evidence_tier="A",
    )
    est = estimate_effect(observed_delta=-5.0, prior=prior, metric_code="weight")
    assert "体重" in est.message


# --------------------------------------------------------------------------
# 10. service + API
# --------------------------------------------------------------------------
def _make_cycle_with_metrics(db, user_id, *, baseline_latest_pairs):
    from datetime import datetime, timezone, date

    from app.models.intervention_cycle import InterventionCycle, OutcomeMetric

    cycle = InterventionCycle(
        user_id=user_id,
        cycle_type="metabolic_90d",
        status="active",
        start_date=date(2026, 1, 1),
    )
    db.add(cycle)
    db.flush()
    now = datetime.now(timezone.utc)
    for code, unit, base, latest, direction in baseline_latest_pairs:
        db.add(OutcomeMetric(
            cycle_id=cycle.id,
            metric_code=code,
            unit=unit,
            baseline_value=base,
            latest_value=latest,
            delta=(None if base is None or latest is None else latest - base),
            direction=direction,
            baseline_observed_at=now,
            latest_observed_at=now,
        ))
    db.commit()
    db.refresh(cycle)
    return cycle


def test_estimate_cycle_effects_returns_one_row_per_metric(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    _make_cycle_with_metrics(
        db, user.id,
        baseline_latest_pairs=[
            ("ldl", "mmol/L", 3.6, 3.0, "down"),
            ("weight", "kg", 82.0, 79.0, "down"),
        ],
    )
    results = estimate_cycle_effects(db, user.id)
    assert len(results) == 2
    codes = {r["metric_code"] for r in results}
    assert codes == {"ldl", "weight"}
    for r in results:
        assert r["model_version"] == "phase1-hbayes-v1"
        assert "verdict" in r and "ci_low" in r and "ci_high" in r


def test_estimate_cycle_effects_missing_value_is_insufficient_not_skipped(db, auth_user_and_headers):
    """baseline 或 latest 缺 → 产 insufficient 占位, 不静默跳过 (Rule#1)。"""
    user, _ = auth_user_and_headers
    _make_cycle_with_metrics(
        db, user.id,
        baseline_latest_pairs=[
            ("ldl", "mmol/L", 3.6, None, "down"),    # latest 缺
        ],
    )
    results = estimate_cycle_effects(db, user.id)
    assert len(results) == 1
    assert results[0]["verdict"] == "insufficient_data"


def test_treatment_effect_endpoint_shape(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    _make_cycle_with_metrics(
        db, user.id,
        baseline_latest_pairs=[("ldl", "mmol/L", 3.6, 2.4, "down")],
    )
    resp = client.get("/api/v1/personal-models/treatment-effect", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "estimates" in body
    assert len(body["estimates"]) == 1
    e = body["estimates"][0]
    assert e["metric_code"] == "ldl"
    # ldl 是处方指标 + 强改善 → 降级 clinician_review + 交医生措辞
    assert e["verdict"] == "clinician_review"
    assert "请由医生判断" in e["message"]
    assert e["display_label"] == "需医生评估"
    assert e["model_version"] == "phase1-hbayes-v1"


def test_prescription_metric_triggers_audit(db, auth_user_and_headers, monkeypatch):
    """S2: requires_clinician / improved/worsened/clinician_review 裁决旁路写 audit。"""
    import app.services.personal_models.treatment_effect as te

    calls = []

    def _spy(**kwargs):
        calls.append(kwargs)
        return 1

    monkeypatch.setattr(te, "_audit_estimate", _spy)

    user, _ = auth_user_and_headers
    _make_cycle_with_metrics(
        db, user.id,
        baseline_latest_pairs=[("ldl", "mmol/L", 3.6, 2.4, "down")],
    )
    results = estimate_cycle_effects(db, user.id)
    assert len(results) == 1
    assert results[0]["verdict"] == "clinician_review"
    # 至少为这条处方裁决写了一次 audit, 含 user / cycle / verdict
    assert len(calls) >= 1
    rec = calls[0]
    assert rec["user_id"] == user.id
    assert rec["verdict"] == "clinician_review"
    assert "metric_code" in rec and "cycle_id" in rec


def test_audit_failure_does_not_break_main_flow(db, auth_user_and_headers, monkeypatch):
    """S2: audit 写入失败不影响主流程 (旁路)。"""
    import app.services.personal_models.treatment_effect as te

    def _boom(**kwargs):
        raise RuntimeError("audit backend down")

    monkeypatch.setattr(te, "_audit_estimate", _boom)

    user, _ = auth_user_and_headers
    _make_cycle_with_metrics(
        db, user.id,
        baseline_latest_pairs=[("ldl", "mmol/L", 3.6, 2.4, "down")],
    )
    # 不应抛
    results = estimate_cycle_effects(db, user.id)
    assert len(results) == 1
    assert results[0]["verdict"] == "clinician_review"


def test_cross_user_cycle_isolation(client, db, auth_user_and_headers):
    """跨用户 cycle_id 取不到自己的 (user_id 隔离)。"""
    from tests.conftest import create_authenticated_user

    user_a, headers_a = auth_user_and_headers
    user_b, _ = create_authenticated_user(db)

    cycle_b = _make_cycle_with_metrics(
        db, user_b.id,
        baseline_latest_pairs=[("ldl", "mmol/L", 3.6, 3.0, "down")],
    )
    # user_a 请求 user_b 的 cycle_id → 服务层隔离, 拿不到 → 空
    results = estimate_cycle_effects(db, user_a.id, cycle_id=cycle_b.id)
    assert results == []

    resp = client.get(
        f"/api/v1/personal-models/treatment-effect?cycle_id={cycle_b.id}",
        headers=headers_a,
    )
    assert resp.status_code == 200
    assert resp.json()["estimates"] == []


# --------------------------------------------------------------------------
# 11. R16 (2026-06-26 · founder/clinician call): 扩展 clinician gate 覆盖药物混杂的
#     代谢周期默认靶标 —— 门控 TC + UA + ALT + GGT; TG / HDL 仍非门控 (生活方式主导)。
#     临床依据: TC 跟随已门控的 LDL (他汀混杂); UA 受降尿酸药主导; ALT/GGT 肝酶升高
#     可能是药物性肝损伤 (DILI) 应交医生 + 多药混杂。
# --------------------------------------------------------------------------
@pytest.mark.parametrize("metric_code", [
    "lipid_tc", "tc", "total_cholesterol",
    "ua", "uric_acid",
    "alt", "ggt",
    # 大小写无关 (collector 可能给大写 canonical code)
    "UA", "ALT", "GGT",
])
def test_r16_confoundable_codes_are_clinician_gated(metric_code):
    """TC / UA / ALT / GGT (含别名 + 大写) → requires_clinician=True。"""
    assert get_prior("metabolic_90d", metric_code).requires_clinician is True
    # 即便落到未知 cycle 的 DEFAULT_PRIOR, 精确集兜底仍门控
    assert get_prior("some_unknown_cycle", metric_code).requires_clinician is True


def test_r16_alt_explicit_prior_flipped_to_clinician_gated():
    """ALT 显式先验由 requires_clinician=False 上调为 True (与精确集一致, 数据不自相矛盾)。"""
    from app.services.personal_models.intervention_priors import PRIORS

    p = PRIORS[("metabolic_90d", "alt")]
    assert p.requires_clinician is True
    assert p.direction == "down"


@pytest.mark.parametrize("metric_code", ["lipid_tg", "lipid_hdl", "tg", "hdl", "triglycerides"])
def test_r16_lifestyle_lipids_stay_non_gated(metric_code):
    """TG / HDL 生活方式主导 + 处方低发 → 不门控 (否则废掉周期合法读出 = over-gating 回归)。"""
    assert get_prior("metabolic_90d", metric_code).requires_clinician is False


@pytest.mark.parametrize("metric_code", [
    "salt_intake",        # 含子串 "alt" —— 不得误门控
    "watch_steps",        # 含子串 "tc"
    "match_score",        # 含子串 "tc"
    "annual_checkup",     # 含子串 "ua"
    "manual_log",         # 含子串 "ua"
])
def test_r16_exact_set_is_not_substring_match(metric_code):
    """新门控 code 走**精确集**而非子串 —— 含相同字母的无关指标不得被误门控。

    这正是不把短 code (ua/tc/alt/ggt) 放进 _CLINICIAN_GATED_KEYWORDS 子串集的原因。
    """
    assert get_prior("metabolic_90d", metric_code).requires_clinician is False


@pytest.mark.parametrize("metric_code", ["ua", "uric_acid", "lipid_tc", "alt", "ggt"])
def test_r16_gated_code_significant_change_routes_clinician_review(metric_code):
    """门控 code 即使统计判方向 → verdict 一律降级 clinician_review (经 get_prior → estimate_effect)。"""
    prior = get_prior("metabolic_90d", metric_code)
    est = estimate_effect(observed_delta=-60.0, prior=prior, metric_code=metric_code)
    assert est.requires_clinician is True
    assert est.verdict == "clinician_review"
    assert est.verdict not in ("improved_in_cycle", "worsened_in_cycle")
    assert "请由医生判断" in est.message
    assert est.display_label == "需医生评估"


def test_r16_tg_significant_change_is_directional_not_clinician_review():
    """TG 非门控: 显著改善仍出方向裁决, 不被降级 (over-gating 回归护栏)。"""
    prior = get_prior("metabolic_90d", "lipid_tg")
    assert prior.requires_clinician is False
    est = estimate_effect(observed_delta=-5.0, prior=prior, metric_code="lipid_tg")
    assert est.verdict in ("improved_in_cycle", "worsened_in_cycle")
    assert est.verdict != "clinician_review"


def test_r16_estimate_cycle_effects_gates_confoundables_not_tg(db, auth_user_and_headers):
    """端到端 (estimate_cycle_effects): UA/TC/ALT/GGT 行 → clinician_review;
    TG 行 → 方向裁决, 不被降级。"""
    user, _ = auth_user_and_headers
    _make_cycle_with_metrics(
        db, user.id,
        baseline_latest_pairs=[
            ("ua", "umol/L", 480.0, 360.0, "down"),      # Δ -120 → 显著
            ("lipid_tc", "mmol/L", 9.0, 4.0, "down"),    # Δ -5.0 → 显著
            ("alt", "U/L", 80.0, 35.0, "down"),          # Δ -45 → 显著
            ("ggt", "U/L", 90.0, 45.0, "down"),          # Δ -45 → 显著
            ("lipid_tg", "mmol/L", 6.0, 1.0, "down"),    # Δ -5.0 → 显著 (非门控)
        ],
    )
    results = estimate_cycle_effects(db, user.id)
    by_code = {r["metric_code"]: r for r in results}
    for code in ("ua", "lipid_tc", "alt", "ggt"):
        assert by_code[code]["requires_clinician"] is True, code
        assert by_code[code]["verdict"] == "clinician_review", code
    assert by_code["lipid_tg"]["requires_clinician"] is False
    assert by_code["lipid_tg"]["verdict"] == "improved_in_cycle"
