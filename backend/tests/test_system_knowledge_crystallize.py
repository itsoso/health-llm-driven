from __future__ import annotations

from datetime import UTC, datetime

from app.models.agent_audit_log import AgentAuditLog
from app.services.system_knowledge_crystallize import draft_crystallized_claim_candidates


def test_draft_crystallized_claim_candidates_requires_repeated_consistent_outcomes(db):
    db.add_all(
        [
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
            AgentAuditLog(
                user_id=2,
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
            AgentAuditLog(
                user_id=3,
                agent_type="specialist_batch",
                action="run",
                result_detail={
                    "findings": [
                        {
                            "specialist": "recovery_coach",
                            "kind": "movement",
                            "summary": "连续低恢复时降低跑步强度",
                            "evidence_refs": [],
                            "unsupported": True,
                        }
                    ]
                },
            ),
        ]
    )
    db.commit()

    low_threshold = draft_crystallized_claim_candidates(
        db,
        min_count=2,
        now=datetime(2026, 5, 17, tzinfo=UTC),
    )
    high_threshold = draft_crystallized_claim_candidates(
        db,
        min_count=3,
        now=datetime(2026, 5, 17, tzinfo=UTC),
    )

    assert len(low_threshold["draft_claims"]) == 1
    claim = low_threshold["draft_claims"][0]
    assert claim["doc_id"].startswith("claim:c_crystallized_")
    assert claim["metadata"]["review_status"] == "draft"
    assert claim["metadata"]["observed_count"] == 2
    assert claim["metadata"]["outcome"] == "supported"
    assert claim["sources"] == ["system:agent-audit-log"]
    assert "+++ crystallized_claims.jsonl" in low_threshold["diff"]
    assert high_threshold["draft_claims"] == []
