from __future__ import annotations

from datetime import UTC, datetime

from app.models.agent_audit_log import AgentAuditLog
from app.models.system_knowledge import KBAudit, KBDocument
from app.tasks.system_knowledge_lifecycle import run_system_kb_lifecycle_once


def test_run_system_kb_lifecycle_once_lints_decays_crystallizes_and_audits(db):
    db.add_all(
        [
            KBDocument(
                doc_id="claim:c_fast_stale",
                doc_type="claim",
                entity_type="condition",
                entity_id="metabolic-health",
                title="Fast stale claim",
                summary="Stale claim for confidence decay.",
                confidence=0.8,
                evidence_level="C",
                applies_when=["twin.goals.metabolic_health.active == true"],
                last_confirmed=datetime(2026, 1, 1, tzinfo=UTC),
                decay_rate="fast",
                metadata_json={"review_status": "reviewed"},
            ),
            AgentAuditLog(
                user_id=1,
                agent_type="specialist_batch",
                action="run",
                result_detail={
                    "findings": [
                        {
                            "specialist": "recovery_coach",
                            "kind": "movement",
                            "summary": "连续低恢复时降低跑步强度",
                            "evidence_refs": ["claim:c_recovery_reduce_intensity"],
                            "unsupported": False,
                        }
                    ]
                },
            ),
        ]
    )
    db.commit()

    result = run_system_kb_lifecycle_once(
        db,
        now=datetime(2026, 5, 17, tzinfo=UTC),
        crystallize_min_count=1,
        actor="test",
    )

    assert result["lint"]["summary"]["invalid_conditions"] == 0
    assert result["decay"]["updated"] == 1
    assert result["crystallize"]["draft_candidates"] == 1
    assert db.get(KBDocument, "claim:c_fast_stale").confidence == 0.72

    audit = db.query(KBAudit).filter(KBAudit.op == "lifecycle_report").one()
    assert audit.actor == "test"
    assert audit.diff["decay"]["updated"] == 1
    assert audit.diff["crystallize"]["draft_candidates"] == 1


def test_run_system_kb_lifecycle_once_runs_reviewed_eval_cases_and_audits(db):
    db.add_all(
        [
            KBDocument(
                doc_id="claim:c_lifecycle_eval_weight_loss_boundary",
                doc_type="claim",
                entity_type="goal",
                entity_id="weight-loss",
                title="减重目标只做行为边界",
                summary="减重目标下只整理行为和趋势，不生成处方或极端饮食。",
                confidence=0.72,
                evidence_level="B",
                applies_when=["twin.goals.weight_loss.active == true"],
                sources=["guideline:test"],
                metadata_json={"review_status": "reviewed"},
            ),
            KBDocument(
                doc_id="eval:lifecycle_eval_weight_loss_boundary",
                doc_type="eval_case",
                entity_type="goal",
                entity_id="weight-loss",
                title="Lifecycle eval",
                metadata_json={
                    "review_status": "reviewed",
                    "case_id": "eval:lifecycle_eval_weight_loss_boundary",
                    "input": {"lookup_twin": {"goals": {"weight_loss": {"active": True}}}},
                    "expected": {
                        "required_claim_ids": ["claim:c_lifecycle_eval_weight_loss_boundary"],
                    },
                },
            ),
        ]
    )
    db.commit()

    result = run_system_kb_lifecycle_once(
        db,
        now=datetime(2026, 6, 28, tzinfo=UTC),
        crystallize_min_count=100,
        actor="test",
    )

    assert result["eval"]["total"] == 1
    assert result["eval"]["passed"] == 1
    assert result["eval"]["failed"] == 0

    audit = db.query(KBAudit).filter(KBAudit.op == "lifecycle_report").one()
    assert audit.diff["eval"]["total"] == 1
    assert audit.diff["eval"]["passed"] == 1
    assert audit.diff["eval"]["failed"] == 0
