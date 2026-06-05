# -*- coding: utf-8 -*-
"""抗衰 N-of-1 闭环(Step 3B)回归。

钉住三件事:
1. phenotypic_age 是已注册的可评分 metric,方向=越低越好(grade_outcome)
2. fetch_metric 能路由 phenotypic_age → 取最新血检算 PhenoAge
3. LongevitySpecialist 偏老(delta≥1)时提一张 12 周 N-of-1 卡;年轻/持平不打扰
"""
from datetime import date
from unittest.mock import patch

from app.tasks.metrics import FETCHERS, HIGHER_IS_BETTER, fetch_metric, grade_outcome


def test_phenotypic_age_registered_lower_is_better():
    assert "phenotypic_age" in FETCHERS
    assert "biological_age" in FETCHERS
    assert HIGHER_IS_BETTER["phenotypic_age"] is False
    assert HIGHER_IS_BETTER["biological_age"] is False


def test_grade_phenotypic_age_direction():
    """身体年龄从 47 → 44 = 改善(越低越好);→ 50 = 恶化。"""
    out_improved, eff = grade_outcome("phenotypic_age", "47", 44.0)
    assert out_improved == "improved"
    assert eff > 0  # 标准化方向:正=朝目标(变年轻)
    out_worse, _ = grade_outcome("phenotypic_age", "47", 50.0)
    assert out_worse == "worsened"
    out_same, _ = grade_outcome("phenotypic_age", "47", 47.1)
    assert out_same == "unchanged"


def test_fetch_metric_routes_phenotypic_age():
    """fetch_metric('phenotypic_age') 路由到取值器 → 复用 phenoage_from_labs。"""
    fake_labs = {
        "albumin": 45.0, "creatinine": 80.0, "blood_glucose": 5.0, "crp": 0.1,
        "lymphocyte_pct": 30.0, "mcv": 90.0, "rdw": 13.0, "alp": 60.0, "wbc": 6.0,
    }
    with patch("app.twin._collectors.fetch_latest_labs", return_value=fake_labs), \
         patch("app.twin._collectors.fetch_user_age", return_value=50):
        val = fetch_metric(None, 1, "phenotypic_age", date(2026, 6, 5))
    assert val is not None
    assert 35 < val < 55  # 健康 50 岁 ~ 41.7


def test_fetch_metric_phenotypic_age_no_labs_returns_none():
    with patch("app.twin._collectors.fetch_latest_labs", return_value={}):
        assert fetch_metric(None, 1, "phenotypic_age", date(2026, 6, 5)) is None


def test_specialist_proposes_episode_when_older():
    from app.agents.longevity_specialist.specialist import _propose_phenoage_episode
    cards = _propose_phenoage_episode(pa=47.0, chrono=42.0, delta=5.0)
    assert len(cards) == 1
    c = cards[0]
    assert c.metric_key == "phenotypic_age"
    assert c.verification_days == 84
    assert c.baseline_value == "47.0"
    assert c.target_value == "<45.0"  # 目标降 2 岁
    assert "不作诊断" in c.content  # 诚实边界随卡输出


def test_specialist_no_episode_when_younger_or_flat():
    from app.agents.longevity_specialist.specialist import _propose_phenoage_episode
    assert _propose_phenoage_episode(pa=40.0, chrono=45.0, delta=-5.0) == []
    assert _propose_phenoage_episode(pa=45.0, chrono=45.0, delta=0.0) == []
    assert _propose_phenoage_episode(pa=45.0, chrono=45.0, delta=None) == []
