# -*- coding: utf-8 -*-
"""Agent eval 看板(RFC 方向九)回归。

钉:活动量按 agent_type;orchestrator p50/p95;主动 Agent 命中/推送率;
闭环 outcome 分布;去标识(无 user_id);admin 鉴权。
"""
import uuid
from datetime import date as _date

from app.services.agent_eval_service import _percentile, agent_eval_dashboard


def _audit(db, agent_type, total_ms=None, detail=None):
    from app.models.agent_audit_log import AgentAuditLog
    db.add(AgentAuditLog(user_id=1, agent_type=agent_type, action="run",
                         total_ms=total_ms, result_detail=detail or {}))


def _card(db, outcome):
    from app.models.action_card import ActionCard
    db.add(ActionCard(user_id=1, title="t", content="x",
                      metric_key="phenotypic_age", outcome=outcome,
                      baseline_value="47", actual_value="44"))


def test_percentile_helper():
    assert _percentile([], 0.5) is None
    assert _percentile([100, 200, 300], 0.5) == 200.0
    assert _percentile([10], 0.95) == 10.0


def test_dashboard_aggregates(db):
    _audit(db, "orchestrator", total_ms=100)
    _audit(db, "orchestrator", total_ms=200)
    _audit(db, "orchestrator", total_ms=300)
    _audit(db, "safety_guardian")
    _audit(db, "longevity_watch", detail={"notable": True, "notified": True, "kind": "improved"})
    _audit(db, "longevity_watch", detail={"notable": False, "notified": False, "kind": "stable"})
    _card(db, "improved")
    _card(db, "improved")
    _card(db, "worsened")
    db.commit()

    out = agent_eval_dashboard(db, days=30)
    assert out["activity"]["orchestrator"] == 3
    assert out["activity"]["safety_guardian"] == 1
    assert out["orchestrator_latency_ms"]["count"] == 3
    assert out["orchestrator_latency_ms"]["p50"] == 200.0
    # 主动 Agent:2 触发,1 notable,1 notified
    pa = out["proactive_agent"]
    assert pa["triggers"] == 2 and pa["notable"] == 1 and pa["notified"] == 1
    assert pa["notable_rate"] == 0.5 and pa["improved"] == 1 and pa["stable"] == 1
    # 闭环:3 评分,2 improved
    cl = out["closed_loop"]
    assert cl["graded_total"] == 3 and cl["distribution"]["improved"] == 2
    assert cl["improvement_rate"] == round(2 / 3, 3)
    # 去标识
    assert "user_id" not in str(out)


def test_dashboard_empty(db):
    out = agent_eval_dashboard(db, days=30)
    assert out["activity"] == {}
    assert out["orchestrator_latency_ms"]["p50"] is None
    assert out["proactive_agent"]["notable_rate"] is None


def test_eval_endpoint_requires_admin(client, auth_user_and_headers):
    user, headers = auth_user_and_headers
    r = client.get("/api/v1/admin/observability/eval", headers=headers)
    assert r.status_code == 403


def test_eval_endpoint_ok_for_admin(client, db):
    from app.services.auth import auth_service
    from app.models.user import User
    admin = User(
        username=f"admin_{uuid.uuid4().hex[:8]}", email=f"a_{uuid.uuid4().hex[:8]}@x.com",
        hashed_password="x", name="admin", birth_date=_date(1990, 1, 1), gender="男",
        is_active=True, is_approved=True, is_admin=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    token = auth_service.create_access_token({"sub": str(admin.id)})
    r = client.get("/api/v1/admin/observability/eval",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert "proactive_agent" in r.json() and "closed_loop" in r.json()
