from datetime import UTC, datetime

from app.models.system_knowledge import KBDocument


def test_admin_operations_dashboard_reports_protocol_review_gaps(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add_all(
        [
            KBDocument(
                doc_id="protocol:sleep:caffeine_cutoff",
                doc_type="protocol",
                entity_type="intervention",
                entity_id="caffeine-cutoff",
                title="下午咖啡因截止",
                summary="14:00 后停止咖啡因，验证入睡潜伏期。",
                body="14:00 后停止咖啡因，验证入睡潜伏期。",
                evidence_level="B",
                confidence=0.72,
                applies_when=["twin.sleep.sleep_latency_minutes > 30"],
                sources=["dedao:sleep-course"],
                metadata_json={
                    "review_status": "draft",
                    "risk_level": "low",
                    "protocol_id": "protocol:sleep:caffeine_cutoff",
                    "verification": {
                        "metric": "sleep_latency_minutes",
                        "window_days": 7,
                        "expected_direction": "decrease",
                    },
                    "paid_source_policy": "transformed_summary_only",
                },
                last_confirmed=datetime(2026, 5, 20, tzinfo=UTC),
            ),
            KBDocument(
                doc_id="protocol:medication:statin_boundary",
                doc_type="protocol",
                entity_type="intervention",
                entity_id="statin-boundary",
                title="他汀用药边界",
                summary="只生成医生沟通问题，不自行调整药物。",
                body="只生成医生沟通问题，不自行调整药物。",
                evidence_level="B",
                confidence=0.7,
                sources=["dedao:medication-course"],
                metadata_json={
                    "review_status": "reviewed",
                    "risk_level": "high",
                    "protocol_id": "protocol:medication:statin_boundary",
                    "verification": {"metric": "doctor_review_completed", "window_days": 30},
                    "paid_source_policy": "transformed_summary_only",
                },
                last_confirmed=datetime(2026, 5, 20, tzinfo=UTC),
            ),
            KBDocument(
                doc_id="protocol:nutrition:paid_leak",
                doc_type="protocol",
                entity_type="intervention",
                entity_id="paid-leak",
                title="付费内容泄漏样例",
                summary="这是一段付费课程正文，不能被原样放入 protocol artifact。",
                body="这是一段付费课程正文，不能被原样放入 protocol artifact。" * 4,
                evidence_level="C",
                confidence=0.61,
                sources=["dedao:nutrition-course"],
                metadata_json={
                    "review_status": "needs_review",
                    "risk_level": "low",
                    "protocol_id": "protocol:nutrition:paid_leak",
                    "verification": {"metric": "fiber_intake_g", "window_days": 7},
                    "paid_source_policy": "raw_excerpt",
                },
                last_confirmed=datetime(2026, 5, 20, tzinfo=UTC),
            ),
            KBDocument(
                doc_id="contra:training:low_recovery_high_intensity",
                doc_type="contraindication",
                title="恢复不足时阻断高强度训练",
                metadata_json={
                    "review_status": "reviewed",
                    "severity": "moderate",
                    "blocks": ["protocol:movement:hiit"],
                },
            ),
            KBDocument(
                doc_id="eval:health_advice_verify_mthfr_001",
                doc_type="eval_case",
                title="MTHFR TT 补剂过度承诺",
                metadata_json={
                    "review_status": "reviewed",
                    "expected": {"must_not_include": ["必须吃"]},
                },
            ),
        ]
    )
    db.commit()

    response = client.get("/api/v1/admin/knowledge/operations_dashboard", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    review = payload["coverage"]["protocol_review"]
    assert review["protocols_total"] == 3
    assert review["draft_protocols"] == 1
    assert review["contraindications_total"] == 1
    assert review["eval_cases_total"] == 1
    assert review["paid_content_lint_violations"] == 1
    assert review["high_risk_protocols_missing_external_evidence"] == 1
    assert review["issues"]["paid_content_lint_violations"][0]["doc_id"] == "protocol:nutrition:paid_leak"
    assert review["issues"]["high_risk_protocols_missing_external_evidence"][0]["doc_id"] == (
        "protocol:medication:statin_boundary"
    )
    assert "protocol_review_needed" in payload["action_items"]
    assert "protocol_paid_content_lint_violations" in payload["action_items"]
    assert "high_risk_protocol_external_evidence_missing" in payload["action_items"]
