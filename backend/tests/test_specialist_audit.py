"""Task 1.2: log_specialist_findings 旁路审计测试.

支持 /reasoning-trace/specialist/{audit_id}?specialist=... 反查单条 finding.
"""

from app.agents.audit import log_specialist_findings
from app.models.agent_audit_log import AgentAuditLog


def test_log_specialist_findings_persists_snapshot(db):
    findings_snapshot = [
        {"specialist": "recovery_coach", "kind": "readiness",
         "summary": "readiness=54 偏低", "data": {"readiness": 54},
         "proposed_cards": []},
        {"specialist": "fuel_strategist", "kind": "nutrition_gap",
         "summary": "蛋白缺口", "data": {"deficit_g": 20},
         "proposed_cards": []},
    ]

    audit_id = log_specialist_findings(
        db=db,
        user_id=1,
        findings=findings_snapshot,
        orchestrator_run_id=None,
    )
    assert audit_id is not None

    row = db.query(AgentAuditLog).filter(
        AgentAuditLog.agent_type == "specialist_batch"
    ).first()
    assert row is not None
    assert len(row.result_detail["findings"]) == 2
    assert row.findings_count == 2
    assert row.result_detail["findings"][0]["specialist"] == "recovery_coach"


def test_log_specialist_findings_empty_list_ok(db):
    audit_id = log_specialist_findings(db=db, user_id=1, findings=[])
    assert audit_id is not None
    row = db.query(AgentAuditLog).filter(
        AgentAuditLog.agent_type == "specialist_batch"
    ).first()
    assert row.findings_count == 0
    assert row.result_detail["findings"] == []


def test_log_specialist_findings_failure_is_silent(db, monkeypatch):
    """旁路审计失败不抛异常 (和其他 audit 函数一致)."""
    def _boom(self):
        raise RuntimeError("db is angry")
    monkeypatch.setattr("sqlalchemy.orm.Session.commit", _boom)
    # 不应抛, 返回 None
    result = log_specialist_findings(db=db, user_id=1, findings=[])
    assert result is None


def test_specialist_finding_model_dump_mode_json_coerces_datetime():
    """保证 SpecialistFinding.model_dump(mode='json') 把 datetime 转 str.

    Orchestrator 的 audit snapshot 依赖这一点防 PG JSONB 崩.
    SQLite 测试路径会 json.dumps(default=str) 静默 coerce, 所以单测必须直接
    验证 mode='json' 的输出, 而不是往 DB 里灌.
    """
    from datetime import datetime, timezone
    import json

    from app.orchestrator.schema import SpecialistFinding

    f = SpecialistFinding(
        specialist_name="longitudinal_analyst",
        category="trend",
        summary="test",
        findings=[],
        raw={"at": datetime(2026, 5, 1, tzinfo=timezone.utc), "delta": 1.5},
        proposed_cards=[],
    )
    d = f.model_dump(mode="json")
    # JSON-safe: json.dumps 不该抛
    json.dumps(d)
    assert isinstance(d["raw"]["at"], str)
    assert "2026-05-01" in d["raw"]["at"]


def test_orchestrator_audit_handles_datetime_in_raw(db):
    """Regression: 模拟 orchestrator bypass 把 model_dump(mode='json') 后的
    snapshot 喂给 log_specialist_findings, 确认 datetime 已经是 str, 不会崩.
    """
    from datetime import datetime, timezone

    findings_snapshot = [{
        "specialist": "longitudinal_analyst",
        "kind": "trend",
        "summary": "3-month HRV trend",
        "data": {
            # 模拟 orchestrator 已经 model_dump(mode='json') 后的值
            "start_date": datetime(2026, 2, 1, tzinfo=timezone.utc).isoformat(),
            "delta_pct": -12.5,
        },
        "proposed_cards": [],
    }]
    audit_id = log_specialist_findings(db=db, user_id=1, findings=findings_snapshot)
    assert audit_id is not None
