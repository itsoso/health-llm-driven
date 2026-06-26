"""R16 Phase 1 —— outcome_readout 诚实置信度渲染权威(修现网 R4 泄漏)。

现网 _outcome_dict / daily_operating_plan 给处方/激素指标(LDL/糖化/收缩压)吐裸
status(improving/worsening/met)+ 裸 delta_pct,无置信度、无 display_label、无临床门 = 活的
R4 违规(对被混杂指标下类裁决)。render_outcome_metric 是唯一出口:门控指标中和裸裁决、降级
clinician_review;非门控给描述式 label + RCV 置信度 + 相关非因果。
"""
from types import SimpleNamespace

from app.services.personal_models.outcome_readout import (
    ATTRIBUTION,
    render_outcome_metric,
)


def _om(**kw):
    base = dict(
        metric_code="weight", unit="kg", baseline_value=80.0, target_value=75.0,
        latest_value=78.0, delta=-2.0, delta_pct=-2.5, direction="down",
        status="improving", confidence="high",
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ───────────────── 门控(处方/激素)指标:绝不泄漏裸裁决 ─────────────────


def test_gated_ldl_neutralized_no_raw_verdict():
    out = render_outcome_metric(_om(metric_code="ldl", status="improving", delta_pct=-30.0))
    assert out["requires_clinician"] is True
    assert out["confidence_tier"] == "clinician_review"
    assert out["display_label"] == "需医生评估"
    # 裸裁决一律中和:status 不得是 improving/worsening/met,delta/方向不得外吐
    assert out["status"] == "clinician_review"
    assert out["delta_pct"] is None and out["delta"] is None and out["direction"] is None


def test_gated_via_substring_fallback():
    # 未登记的 metric_code 仍走子串兜底(fail-closed):home_bp_avg 含 'bp'
    out = render_outcome_metric(_om(metric_code="home_bp_avg", status="worsening", delta_pct=12.0))
    assert out["requires_clinician"] is True and out["status"] == "clinician_review"


def test_gated_hba1c_and_cortisol_gated():
    for code in ("hba1c", "fasting_glucose", "cortisol", "tsh", "sbp"):
        out = render_outcome_metric(_om(metric_code=code, status="improving"))
        assert out["requires_clinician"] is True, f"{code} 必须门控"
        assert out["status"] != "improving"


def test_contract_gated_output_has_no_verdict_word_anywhere():
    """契约:门控输出的**任何字段值**里都不得出现 improving/worsening/met(防反推效应)。"""
    out = render_outcome_metric(_om(metric_code="ldl_c", status="met", delta_pct=-40.0))
    leaked = [v for v in out.values() if isinstance(v, str) and v in ("improving", "worsening", "met")]
    assert leaked == [], f"门控指标泄漏了裸裁决: {leaked}"


# ───────────────── 非门控指标:描述式 + 诚实置信度 ─────────────────


def test_nongated_improving_descriptive_with_confidence():
    out = render_outcome_metric(_om(metric_code="weight", status="improving", confidence="high"))
    assert out["requires_clinician"] is False
    assert out["confidence_tier"] == "high"
    assert out["display_label"] == "周期内观察到改善"
    assert out["attribution"] == ATTRIBUTION == "temporal_association_not_causation"


def test_nongated_flat_is_inconclusive():
    out = render_outcome_metric(_om(metric_code="hrv", status="flat", confidence="low"))
    assert out["display_label"] == "暂不下结论" and out["requires_clinician"] is False


def test_pending_or_none_is_insufficient_low():
    # 非门控指标 (weight): pending → 数据不足/low (alt 已于 R16 扩门控, 改用非门控 code 测此路径)
    out = render_outcome_metric(_om(metric_code="weight", status="pending", confidence=None, delta_pct=None))
    assert out["display_label"] == "数据不足" and out["confidence_tier"] == "low"


def test_gated_metric_pending_is_clinician_review_not_insufficient():
    """R16 扩门控: 门控指标 (alt/UA/lipid_tc/ggt/ast) 即使 pending/无数据也 fail-closed 到
    需医生评估 (门控优先于 insufficient), 绝不外吐裸 status/delta。"""
    for code in ("alt", "ast", "ggt", "UA", "lipid_tc"):
        out = render_outcome_metric(_om(metric_code=code, status="pending", confidence=None, delta_pct=None))
        assert out["requires_clinician"] is True, code
        assert out["display_label"] == "需医生评估", code
        assert out["delta_pct"] is None and out["status"] == "clinician_review", code


def test_every_output_carries_tier_and_attribution():
    for code, st in [("ldl", "improving"), ("weight", "flat"), ("alt", "pending")]:
        out = render_outcome_metric(_om(metric_code=code, status=st))
        assert "confidence_tier" in out and out["attribution"] == ATTRIBUTION
        assert "requires_clinician" in out and "display_label" in out


# ───────────────── 对抗:证明守卫非稻草人(旧路径会泄漏) ─────────────────


def test_adversarial_old_path_would_leak_new_path_neutralizes():
    """同一条门控 om:裸 .status 是 'improving'(=旧 _outcome_dict 会原样外吐=泄漏),
    经 render 后 status 被中和成非裁决值 —— 证明新守卫真的拦住了真泄漏,不是稻草人。"""
    om = _om(metric_code="ldl", status="improving", delta_pct=-25.0)
    assert om.status == "improving"  # 旧路径 _outcome_dict 直接吐这个 = 泄漏
    out = render_outcome_metric(om)
    assert out["status"] != "improving"  # 新路径中和
    assert out["requires_clinician"] is True


# ───────────────── 集成:_outcome_dict 经 render 出口 ─────────────────


def test_outcome_dict_routes_through_render_for_gated():
    from app.api.intervention_cycles import _outcome_dict

    out = _outcome_dict(_om(metric_code="ldl", status="worsening", delta_pct=18.0))
    assert out["requires_clinician"] is True
    assert out["status"] != "worsening" and out["delta_pct"] is None


def test_intervention_status_tool_gates_prescription_metric(db):
    """对抗(双评审 BLOCKING):LLM 可调的 intervention_cycle(action=status) 工具
    此前给门控 LDL 吐裸『改善中』+ Δ% 进 LLM/用户 —— 第三个泄漏点。必须门控。"""
    from datetime import date, timedelta

    from app.models.intervention_cycle import InterventionCycle, OutcomeMetric
    from app.services.agent_executor import AgentExecutor
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    cyc = InterventionCycle(
        user_id=user.id, cycle_type="metabolic", status="active",
        start_date=date.today() - timedelta(days=30),
        planned_end_date=date.today() + timedelta(days=60),
    )
    db.add(cyc)
    db.flush()
    db.add(OutcomeMetric(
        cycle_id=cyc.id, metric_code="lipid_ldl", unit="mmol/L",
        baseline_value=3.5, target_value=3.0, latest_value=2.6,
        delta=-0.9, delta_pct=-25.7, direction="down", status="improving",
    ))
    db.add(OutcomeMetric(
        cycle_id=cyc.id, metric_code="weight", unit="kg",
        baseline_value=80.0, target_value=75.0, latest_value=78.0,
        delta=-2.0, delta_pct=-2.5, direction="down", status="improving",
    ))
    db.commit()

    out = AgentExecutor(db)._intervention_status(user.id)
    gated_lines = [ln for ln in out.splitlines() if "需医生评估" in ln]
    assert gated_lines, "门控 LDL 行应标『需医生评估』"
    # 门控行绝不含裸裁决词/变化幅度
    for ln in gated_lines:
        assert "改善中" not in ln and "变差" not in ln and "达标" not in ln
        assert "Δ" not in ln and "%" not in ln
    # 非门控 weight 行仍保留描述式裁决
    assert any("改善中" in ln for ln in out.splitlines())
