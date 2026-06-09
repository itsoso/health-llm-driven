# -*- coding: utf-8 -*-
"""主动化推广:泛型指标轨迹监测(Phase3)回归。

钉:方向复用 HIGHER_IS_BETTER(越低越好的体重/血糖等);改善/回退/持平判定 +
阈值;缺值/零基线不打扰;scan 多指标;db-backed evaluate_user_trajectories。
"""
from datetime import datetime, timedelta

from app.services.trajectory_watch import (
    WATCH_METRICS,
    diff_metric,
    scan_trajectories,
)

_WEIGHT = next(s for s in WATCH_METRICS if s["key"] == "weight")  # 越低越好, pct=0.03


def _twin(weight=None, glucose=None, ldl=None):
    return {
        "body_composition": {"weight_kg": weight},
        "labs": {"blood_glucose": glucose, "ldl": ldl},
    }


def test_diff_weight_improved():  # 体重降 = 改善(越低越好)
    c = diff_metric(_twin(weight=80.0), _twin(weight=76.0), _WEIGHT)
    assert c.kind == "improved" and c.notable is True
    assert c.prev == 80.0 and c.curr == 76.0
    assert "改善" in c.title


def test_diff_weight_regressed():
    c = diff_metric(_twin(weight=76.0), _twin(weight=80.0), _WEIGHT)
    assert c.kind == "regressed" and c.notable is True
    assert "不用慌" in c.message


def test_diff_stable_below_threshold():
    c = diff_metric(_twin(weight=80.0), _twin(weight=81.0), _WEIGHT)  # 1.25% < 3%
    assert c.kind == "stable" and c.notable is False


def test_diff_none_when_missing_or_zero():
    assert diff_metric(_twin(weight=80.0), _twin(), _WEIGHT) is None
    assert diff_metric(_twin(weight=0.0), _twin(weight=5.0), _WEIGHT) is None


def test_scan_collects_notable_across_metrics():
    older = _twin(weight=80.0, glucose=7.0, ldl=4.0)
    newer = _twin(weight=76.0, glucose=5.0, ldl=3.99)  # weight↓改善, glucose↓改善, ldl 几乎不变
    changes = scan_trajectories([newer, older])  # newest-first
    keys = {c.metric for c in changes}
    assert "weight" in keys and "blood_glucose" in keys
    assert "ldl" not in keys  # 变化 < 阈值,不算 notable
    assert all(c.notable for c in changes)


def test_evaluate_user_trajectories_db(db):
    from app.models.twin_snapshot import TwinSnapshot
    from app.tasks.trajectory_watch import evaluate_user_trajectories
    t0 = datetime(2026, 3, 1)
    db.add(TwinSnapshot(user_id=1, schema_version="1", content_hash="a", purpose="manual",
                        quality_grade="B", sources=["labs"], twin_json=_twin(weight=82.0), created_at=t0))
    db.add(TwinSnapshot(user_id=1, schema_version="1", content_hash="b", purpose="manual",
                        quality_grade="B", sources=["labs"], twin_json=_twin(weight=77.0),
                        created_at=t0 + timedelta(days=60)))
    db.commit()
    changes = evaluate_user_trajectories(db, 1)
    assert any(c.metric == "weight" and c.kind == "improved" for c in changes)


def test_eval_dashboard_counts_trajectory_watch(db):
    """eval 看板 proactive 现在聚合所有 *_watch(含 trajectory_watch)。"""
    from app.models.agent_audit_log import AgentAuditLog
    from app.services.agent_eval_service import agent_eval_dashboard
    db.add(AgentAuditLog(user_id=1, agent_type="trajectory_watch", action="proactive_trigger",
                         result_detail={"notable": True, "notified": True, "kind": "improved"}))
    db.commit()
    out = agent_eval_dashboard(db, days=30)
    assert out["proactive_agent"]["triggers"] == 1
    assert out["proactive_agent"]["notified"] == 1
