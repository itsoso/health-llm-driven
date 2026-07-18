# -*- coding: utf-8 -*-
"""安全 eval(red-team)+ 群体 harm 信号(反向飞轮)回归 — Next Horizon Tier 3。"""


# ───────────── 安全 eval(red-team 规则覆盖)─────────────

def test_safety_eval_all_pass():
    """对抗场景集必须全过(规则覆盖无回归);否则暴露安全漏洞。"""
    from app.services.safety_eval import run_safety_eval
    out = run_safety_eval()
    assert out["total"] >= 3
    assert out["pass_rate"] == 1.0, [s for s in out["scenarios"] if not s["passed"]]
    for s in out["scenarios"]:
        assert s["passed"] and s["max_severity_found"] >= s["expected_min_severity"]


def test_safety_eval_models_a_single_severe_bp_reading_as_high_not_diagnosis():
    from app.services.safety_eval import run_safety_eval

    out = run_safety_eval()
    scenario = next(s for s in out["scenarios"] if s["name"] == "severe_bp_reading")

    assert scenario["expected_min_severity"] == 3
    assert "危象" not in scenario["desc"]


def test_safety_eval_endpoint_admin(client, db):
    import uuid
    from datetime import date as _date
    from app.services.auth import auth_service
    from app.models.user import User
    admin = User(username=f"a_{uuid.uuid4().hex[:8]}", email=f"a_{uuid.uuid4().hex[:8]}@x.com",
                 hashed_password="x", name="a", birth_date=_date(1990, 1, 1), gender="男",
                 is_active=True, is_approved=True, is_admin=True)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    token = auth_service.create_access_token({"sub": str(admin.id)})
    r = client.get("/api/v1/admin/observability/safety-eval",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["pass_rate"] == 1.0


# ───────────── 群体 harm 信号(反向飞轮)─────────────

def _card(db, user_id, metric, outcome):
    from app.models.action_card import ActionCard
    db.add(ActionCard(user_id=user_id, title="t", content="x", metric_key=metric,
                      outcome=outcome, baseline_value="1", actual_value="1"))


def test_harm_signal_flags_worsening(db):
    from app.services.longevity_cohort_service import cohort_harm_signals
    # 某指标 6 张:4 worsened / 1 improved / 1 unchanged → worsened_rate 0.667 > 0.3 且 > improved
    for u in range(4):
        _card(db, u + 1, "ldl", "worsened")
    _card(db, 5, "ldl", "improved")
    _card(db, 6, "ldl", "unchanged")
    db.commit()
    out = cohort_harm_signals(db)
    sigs = {h["metric"]: h for h in out["harm_signals"]}
    assert "ldl" in sigs and sigs["ldl"]["worsened"] == 4
    assert sigs["ldl"]["worsened_rate"] > 0.3
    assert out["evidence_tier"] == "observational" and "非因果" in out["claim_boundary"]


def test_harm_signal_not_flagged_when_mostly_improved(db):
    from app.services.longevity_cohort_service import cohort_harm_signals
    for u in range(5):
        _card(db, u + 1, "weight", "improved")
    _card(db, 6, "weight", "worsened")
    db.commit()
    out = cohort_harm_signals(db)
    assert all(h["metric"] != "weight" for h in out["harm_signals"])  # 改善为主 → 不报 harm


def test_harm_signal_small_cohort_suppressed(db):
    from app.services.longevity_cohort_service import cohort_harm_signals
    _card(db, 1, "ldl", "worsened")
    _card(db, 2, "ldl", "worsened")  # 仅 2 < MIN_COHORT
    db.commit()
    out = cohort_harm_signals(db)
    assert out["harm_signals"] == []
