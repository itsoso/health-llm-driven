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
