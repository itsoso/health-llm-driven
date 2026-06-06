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


# ───────────── W2: VO2max / 体能年龄 第二信号 ─────────────

def test_vo2max_registered_directions():
    assert "vo2max" in FETCHERS and "fitness_age" in FETCHERS
    assert HIGHER_IS_BETTER["vo2max"] is True       # VO2max 越高越好
    assert HIGHER_IS_BETTER["fitness_age"] is False  # 体能年龄越低越好


def test_grade_vo2max_higher_is_better():
    improved, eff = grade_outcome("vo2max", "40", 44.0)  # 升 → 改善
    assert improved == "improved" and eff > 0
    worse, _ = grade_outcome("vo2max", "40", 36.0)
    assert worse == "worsened"


def _twin_with(vo2_fitness_age=None, vo2max_running=None, phenotypic_age=None, delta=None):
    from datetime import datetime
    from app.twin.schema import HealthTwin, TwinMeta
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime(2026, 6, 6)))
    t.physiological.vo2max_fitness_age = vo2_fitness_age
    t.physiological.vo2max_running = vo2max_running
    t.labs.phenotypic_age = phenotypic_age
    t.labs.phenotypic_age_delta_years = delta
    return t


def test_cardio_signal_helper():
    from app.agents.longevity_specialist.specialist import _cardio_signal
    f = _cardio_signal(_twin_with(vo2_fitness_age=38, vo2max_running=42.0), chrono=45.0)
    assert f is not None
    assert f["type"] == "cardio_fitness"
    assert f["vo2max"] == 42.0
    assert f["fitness_age"] == 38
    assert f["fitness_age_delta_years"] == -7.0  # 体能年轻 7 岁
    assert f["evidence_tier"] == "validated" and f["claim_boundary"]
    # 无任何 vo2 数据 → None
    assert _cardio_signal(_twin_with(), chrono=45.0) is None


def test_compose_protocol_runs_pillars():
    """W4: 真实编排四件套 → 至少恢复支柱有具体行动(不再是委托文字)。"""
    from app.agents.longevity_specialist.specialist import _compose_protocol
    t = _twin_with(phenotypic_age=47.0, delta=5.0)
    t.physiological.hrv_latest = 38.0
    t.physiological.sleep_duration_h_latest = 6.0
    t.physiological.sleep_score_latest = 60
    protocol = _compose_protocol(t)
    assert isinstance(protocol, list)
    assert len(protocol) >= 1
    for p in protocol:
        assert p["pillar"] and p["action"] and p["source"]
    # 睡眠/恢复支柱应在(recovery 对任意 twin 都能算 readiness)
    assert any(p["pillar"].startswith("睡眠") for p in protocol)


def test_episode_card_embeds_protocol():
    """W4: 协议写进 N-of-1 卡正文 → 用户拿到"具体做什么"。"""
    from app.agents.longevity_specialist.specialist import _propose_phenoage_episode
    protocol = [{"pillar": "运动", "action": "每周 3 次有氧", "source": "movement_coach"}]
    cards = _propose_phenoage_episode(pa=47.0, chrono=42.0, delta=5.0, protocol=protocol)
    assert len(cards) == 1
    assert "本周期行动" in cards[0].content
    assert "运动:每周 3 次有氧" in cards[0].content


def test_specialist_surfaces_cardio_even_without_phenoage():
    """无血检但有体能年龄 → specialist 仍给出心肺信号(不只报缺血检)。"""
    from app.agents.longevity_specialist.specialist import LongevitySpecialist
    from app.orchestrator.schema import Intent
    twin = _twin_with(vo2_fitness_age=40, vo2max_running=45.0)  # 无 phenotypic_age
    finding = LongevitySpecialist().run(twin, {})
    types = {f.get("type") for f in finding.findings}
    assert "cardio_fitness" in types
    assert "体能" in finding.summary or "VO2max" in finding.summary
