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
                    RedisCache.delete(f"safety:v2:{user.id}:s{sev}:l{lim}:d{dedup}")
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
