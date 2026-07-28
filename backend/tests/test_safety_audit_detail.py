"""Audit detail 回传 alerts 列表, 支持单 alert 反查."""
from app.agents.audit import log_safety_evaluation
from app.models.agent_audit_log import AgentAuditLog


def test_log_safety_evaluation_persists_alerts_snapshot(db):
    """直接调用 service: result_detail={"alerts": [...]} 要被持久化到 DB."""
    alerts_snapshot = [
        {"rule_id": "acute_hrv_drop", "category": "vitals",
         "severity": 3, "title": "HRV 急剧下降",
         "message": "...", "data_citation": {"hrv": 28}},
        {"rule_id": "ddi_warfarin_nsaid", "category": "ddi",
         "severity": 4, "title": "出血风险",
         "message": "...", "data_citation": {}},
    ]

    log_safety_evaluation(
        db=db,
        user_id=1,
        alerts_count=2,
        result_summary="1crit/1med",
        twin_build_ms=12,
        evaluate_ms=8,
        twin_sources=["garmin"],
        result_detail={"alerts": alerts_snapshot},
    )

    row = db.query(AgentAuditLog).filter(
        AgentAuditLog.agent_type == "safety_guardian"
    ).first()
    assert row is not None
    assert row.result_detail is not None
    assert len(row.result_detail["alerts"]) == 2
    assert row.result_detail["alerts"][0]["rule_id"] == "acute_hrv_drop"
    assert row.result_detail["alerts"][1]["rule_id"] == "ddi_warfarin_nsaid"
    assert row.result_detail["alerts"][0]["data_citation"] == {"hrv": 28}


def test_safety_me_response_includes_audit_id(client, auth_user_and_headers, db):
    """Task 3: /safety/me 响应体必须包含 top-level audit_id 字段.

    Mobile ExplainSheet 依赖这个 id 调 /reasoning-trace/safety/{audit_id}.
    """
    user, headers = auth_user_and_headers

    # 清缓存, 确保真的走 evaluate + audit 分支
    try:
        from app.utils.redis_cache import RedisCache
        for sev in (0, 2):
            for lim in (8, 50):
                for dedup in (0, 1):
                    RedisCache.delete(f"safety:v3:{user.id}:s{sev}:l{lim}:d{dedup}")
    except Exception:
        pass

    resp = client.get("/api/v1/safety/me", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "audit_id" in body, (
        "response 必须有 audit_id top-level 字段 (Mobile ExplainSheet 用)"
    )
    # audit 写入成功时是 int, 旁路失败时是 None
    assert body["audit_id"] is None or isinstance(body["audit_id"], int)

    # 有 audit_id 时, /reasoning-trace/safety/{id} 必须能反查到
    if body["audit_id"] is not None and body["alerts"]:
        first_rule = body["alerts"][0]["rule_id"]
        r2 = client.get(
            f"/api/v1/reasoning-trace/safety/{body['audit_id']}",
            headers=headers,
            params={"rule_id": first_rule},
        )
        assert r2.status_code == 200, r2.text
        trace = r2.json()
        assert trace["source"] == "safety"
        assert "twin_evidence" in trace
        assert "related_facts" in trace
        assert "confidence" in trace
        assert "confidence_note" in trace


def test_safety_me_endpoint_persists_alerts_snapshot(client, auth_user_and_headers, db):
    """端到端: GET /api/v1/safety/me 的 audit row 必须有 result_detail.alerts."""
    user, headers = auth_user_and_headers

    # 清空可能的 Redis 缓存, 确保走到 evaluate + audit 分支
    try:
        from app.utils.redis_cache import RedisCache
        # 不同参数组合都要清
        for sev in (0, 2):
            for lim in (8, 50):
                for dedup in (0, 1):
                    RedisCache.delete(f"safety:v3:{user.id}:s{sev}:l{lim}:d{dedup}")
    except Exception:
        pass

    resp = client.get("/api/v1/safety/me", headers=headers)
    assert resp.status_code == 200, resp.text

    row = (
        db.query(AgentAuditLog)
        .filter(
            AgentAuditLog.user_id == user.id,
            AgentAuditLog.agent_type == "safety_guardian",
        )
        .order_by(AgentAuditLog.id.desc())
        .first()
    )
    assert row is not None, "safety_guardian audit row 应该已写入"
    assert row.result_detail is not None, (
        "result_detail 不能为 None, 后续 /reasoning-trace/safety/{id} 需要反查"
    )
    assert "alerts" in row.result_detail
    assert isinstance(row.result_detail["alerts"], list)
    # 每条 alert 结构必须含 rule_id (反查 key)
    for a in row.result_detail["alerts"]:
        assert "rule_id" in a
        assert "category" in a
        assert "severity" in a
        assert isinstance(a["severity"], int)
        # generated_at 是 isoformat 字符串
        assert "generated_at" in a
        assert isinstance(a["generated_at"], str)
