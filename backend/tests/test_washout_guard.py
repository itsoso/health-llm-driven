"""R16 P3 跨周期洗脱期归因守卫。

无前序周期(单周期=现状)→ attributable 不降级;前序(同指标)在洗脱期内 → washout_pending +
置信度封 low(只降不升);不同指标不污染;fail-closed;读数渲染「归因待定」;门控指标不受影响。
"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.intervention_cycle import InterventionCycle, OutcomeMetric
from app.services import intervention_cycle_service as ics
from app.services import washout_guard as wg
from app.services.personal_models.outcome_readout import render_outcome_metric
from tests.conftest import create_authenticated_user

_T0 = date(2026, 3, 1)
_BASE_AT = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _cycle(db, uid, start, end, status="completed", metrics=("weight",)):
    c = InterventionCycle(
        user_id=uid, cycle_type="metabolic", status=status,
        start_date=start, planned_end_date=end,
    )
    db.add(c)
    db.flush()
    for m in metrics:
        db.add(OutcomeMetric(cycle_id=c.id, metric_code=m, baseline_value=80.0))
    db.commit()
    db.refresh(c)
    return c


# ───────────────────────── 单元:attribution_for_metric ─────────────────────────


def test_no_prior_cycle_attributable(db):
    user, _ = create_authenticated_user(db)
    cur = _cycle(db, user.id, _T0, _T0 + timedelta(days=90), status="active")
    state, until = wg.attribution_for_metric(db, user.id, cur, "weight", _BASE_AT)
    assert state == "attributable" and until is None


def test_prior_within_washout_pending(db):
    user, _ = create_authenticated_user(db)
    _cycle(db, user.id, _T0 - timedelta(days=100), _T0 - timedelta(days=10))  # 结束于基线前 10 天 (<21)
    cur = _cycle(db, user.id, _T0, _T0 + timedelta(days=90), status="active")
    state, until = wg.attribution_for_metric(db, user.id, cur, "weight", _BASE_AT)
    assert state == "washout_pending"
    assert until == _T0 - timedelta(days=10) + timedelta(days=wg.WASHOUT_DAYS_DEFAULT)


def test_prior_exactly_at_washout_boundary_pending(db):
    # 边界含(<=):前序恰好 washout 天前结束 → 仍 washout_pending(钉死,防未来误改成 <)
    user, _ = create_authenticated_user(db)
    _cycle(db, user.id, _T0 - timedelta(days=100), _T0 - timedelta(days=wg.WASHOUT_DAYS_DEFAULT))
    cur = _cycle(db, user.id, _T0, _T0 + timedelta(days=90), status="active")
    state, _ = wg.attribution_for_metric(db, user.id, cur, "weight", _BASE_AT)
    assert state == "washout_pending"


def test_prior_outside_washout_attributable(db):
    user, _ = create_authenticated_user(db)
    _cycle(db, user.id, _T0 - timedelta(days=200), _T0 - timedelta(days=40))  # 结束于基线前 40 天 (>21)
    cur = _cycle(db, user.id, _T0, _T0 + timedelta(days=90), status="active")
    state, _ = wg.attribution_for_metric(db, user.id, cur, "weight", _BASE_AT)
    assert state == "attributable"


def test_prior_different_metric_not_contaminating(db):
    user, _ = create_authenticated_user(db)
    _cycle(db, user.id, _T0 - timedelta(days=100), _T0 - timedelta(days=5), metrics=("hrv",))  # 前序跟 hrv
    cur = _cycle(db, user.id, _T0, _T0 + timedelta(days=90), status="active")
    state, _ = wg.attribution_for_metric(db, user.id, cur, "weight", _BASE_AT)
    assert state == "attributable"  # 不同指标不污染


def test_no_baseline_time_attributable(db):
    user, _ = create_authenticated_user(db)
    cur = _cycle(db, user.id, _T0, _T0 + timedelta(days=90), status="active")
    state, _ = wg.attribution_for_metric(db, user.id, cur, "weight", None)
    assert state == "attributable"


def test_fail_closed_on_exception():
    class BoomDB:
        def query(self, *a, **k):
            raise RuntimeError("boom")

    state, until = wg.attribution_for_metric(
        BoomDB(), 1, SimpleNamespace(id=1, cycle_type="x"), "weight", _BASE_AT
    )
    assert state == "washout_pending" and until is None  # fail-closed


# ───────────────────────── 集成:_denoised_status 叠加归因 ─────────────────────────


def _live_om(db, cur):
    om = cur.outcomes[0]
    om.baseline_value, om.latest_value = 80.0, 75.0
    om.delta, om.delta_pct, om.direction = -5.0, -6.25, "down"
    om.baseline_observed_at = _BASE_AT
    om.latest_observed_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    db.commit()
    return om


def test_denoised_status_stamps_washout_and_demotes(db):
    user, _ = create_authenticated_user(db)
    _cycle(db, user.id, _T0 - timedelta(days=100), _T0 - timedelta(days=10))  # prior weight, 洗脱期内
    cur = _cycle(db, user.id, _T0, _T0 + timedelta(days=90), status="active")
    om = _live_om(db, cur)
    ics._denoised_status(db, cur, om)
    assert om.attribution_state == "washout_pending"
    assert om.confidence == "low"  # 归因待定 → 封 low


def test_denoised_status_single_cycle_attributable_no_demote(db):
    user, _ = create_authenticated_user(db)
    cur = _cycle(db, user.id, _T0, _T0 + timedelta(days=90), status="active")  # 无前序
    om = _live_om(db, cur)
    ics._denoised_status(db, cur, om)
    assert om.attribution_state == "attributable"  # 单周期不降级(legacy)


# ───────────────────────── 读数渲染 ─────────────────────────


def _ns(**kw):
    base = dict(metric_code="weight", unit="kg", baseline_value=80.0, target_value=75.0,
               latest_value=75.0, delta=-5.0, delta_pct=-6.25, direction="down",
               status="improving", confidence="high", attribution_state="attributable")
    base.update(kw)
    return SimpleNamespace(**base)


def test_render_washout_demotes_nongated():
    out = render_outcome_metric(_ns(attribution_state="washout_pending"))
    assert out["attribution_state"] == "washout_pending"
    assert out["confidence_tier"] == "low"
    assert "归因待定" in out["display_label"]
    assert "改善" not in out["display_label"]  # 不自信归因于当前干预


def test_render_attributable_unchanged_nongated():
    out = render_outcome_metric(_ns(attribution_state="attributable"))
    assert out["confidence_tier"] == "high" and "改善" in out["display_label"]


def test_render_gated_still_clinician_review_under_washout():
    out = render_outcome_metric(_ns(metric_code="ldl", attribution_state="washout_pending"))
    assert out["requires_clinician"] is True and out["confidence_tier"] == "clinician_review"
