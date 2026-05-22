from app.models.agent_audit_log import AgentAuditLog
from app.models.system_knowledge import KBDocument
from app.services.specialist_evidence_backfill import backfill_specialist_evidence_refs
from app.services.system_knowledge_service import get_knowledge_coverage_report


def _claim(doc_id: str, title: str) -> KBDocument:
    return KBDocument(
        doc_id=doc_id,
        doc_type="claim",
        entity_type="intervention",
        entity_id=doc_id.removeprefix("claim:c_"),
        title=title,
        summary=title,
        confidence=0.7,
        evidence_level="B",
        metadata_json={"review_status": "reviewed"},
    )


def test_backfill_specialist_evidence_refs_dry_run_does_not_mutate(db):
    db.add(_claim("claim:c_training_readiness_high_load_boundary", "Readiness 高分训练边界"))
    db.add(
        AgentAuditLog(
            user_id=1,
            agent_type="specialist_batch",
            action="run",
            findings_count=1,
            result_detail={
                "findings": [
                    {
                        "summary": "Readiness 88/100 - 状态极佳，可高强度训练",
                        "specialist": "recovery_coach",
                        "category": "recovery",
                        "data": {"score": 88},
                    }
                ]
            },
        )
    )
    db.commit()

    result = backfill_specialist_evidence_refs(db, dry_run=True)

    assert result["findings_with_refs"] == 1
    row = db.query(AgentAuditLog).first()
    finding = row.result_detail["findings"][0]
    assert finding.get("evidence_refs") is None


def test_backfill_specialist_evidence_refs_attaches_refs_and_marks_data_gap(db):
    db.add_all(
        [
            _claim("claim:c_training_readiness_high_load_boundary", "Readiness 高分训练边界"),
            _claim("claim:c_acwr_training_load_boundary", "ACWR 训练负荷边界"),
            _claim("claim:c_hydration_progress_boundary", "饮水进度边界"),
            _claim("claim:c_protein_target_training_boundary", "蛋白目标边界"),
            _claim("claim:c_allergic_rhinitis_symptom_tracking_boundary", "鼻炎症状边界"),
        ]
    )
    db.add(
        AgentAuditLog(
            user_id=1,
            agent_type="specialist_batch",
            action="run",
            findings_count=4,
            result_detail={
                "findings": [
                    {
                        "summary": "训练 过载风险（ACWR 1.56）· 今日建议 low",
                        "specialist": "movement_coach",
                        "category": "movement",
                        "data": {"acwr": 1.56},
                    },
                    {
                        "summary": "热量 290/2727 kcal · 蛋白 0/98g · 水 500/2000ml",
                        "specialist": "fuel_strategist",
                        "category": "nutrition",
                        "data": {"water_pct": 25.0, "protein_today_g": 0.0},
                    },
                    {
                        "summary": "鼻炎 轻度（喷嚏 0 / 洗鼻 1）",
                        "specialist": "rhinitis_specialist",
                        "category": "chronic",
                        "data": {"severity": "mild"},
                    },
                    {
                        "summary": "需补充: 暂无血压数据, 也未识别在服降压药",
                        "specialist": "hypertension_specialist",
                        "category": "chronic",
                        "data": {"data_gap": True},
                    },
                ]
            },
        )
    )
    db.commit()

    result = backfill_specialist_evidence_refs(db, dry_run=False)

    assert result["audit_logs_updated"] == 1
    assert result["findings_with_refs"] == 3
    assert result["findings_not_applicable"] == 1

    coverage = get_knowledge_coverage_report(db)["specialist_findings"]
    assert coverage["total"] == 4
    assert coverage["applicable_total"] == 3
    assert coverage["with_evidence_refs"] == 3
    assert coverage["not_applicable"] == 1
    assert coverage["evidence_ref_rate"] == 1.0
