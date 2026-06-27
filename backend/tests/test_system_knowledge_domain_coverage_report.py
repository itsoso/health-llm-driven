from datetime import UTC, datetime

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_service import get_knowledge_coverage_report


def test_coverage_report_groups_source_review_eval_and_stale_risk_by_domain(db):
    db.add_all(
        [
            KBDocument(
                doc_id="claim:c_nutrition_reviewed_with_eval",
                doc_type="claim",
                entity_type="condition",
                entity_id="metabolic-health",
                title="Reviewed nutrition claim",
                summary="有外部指南和 eval 覆盖的营养 claim。",
                confidence=0.82,
                evidence_level="B",
                sources=["guideline:nutrition-safe"],
                last_confirmed=datetime(2026, 6, 1, tzinfo=UTC),
                decay_rate="normal",
                metadata_json={
                    "domain": "nutrition",
                    "review_status": "reviewed",
                    "external_sources": [
                        {
                            "kind": "guideline",
                            "source": "guideline:nutrition-safe",
                            "review_status": "reviewed",
                        }
                    ],
                },
            ),
            KBDocument(
                doc_id="claim:c_nutrition_stale_without_source",
                doc_type="claim",
                entity_type="condition",
                entity_id="metabolic-health",
                title="Stale nutrition claim",
                summary="缺少外部来源且超过 fast decay 窗口的营养 claim。",
                confidence=0.6,
                evidence_level="C",
                sources=[],
                last_confirmed=datetime(2026, 1, 1, tzinfo=UTC),
                decay_rate="fast",
                metadata_json={"domain": "nutrition", "review_status": "reviewed"},
            ),
            KBDocument(
                doc_id="eval:nutrition_reviewed_claim",
                doc_type="eval_case",
                entity_type="condition",
                entity_id="metabolic-health",
                title="Nutrition eval",
                summary="覆盖 reviewed nutrition claim 的 eval。",
                metadata_json={
                    "domain": "nutrition",
                    "review_status": "reviewed",
                    "expected": {
                        "required_claim_ids": ["claim:c_nutrition_reviewed_with_eval"],
                        "required_doc_ids": ["claim:c_nutrition_reviewed_with_eval"],
                    },
                },
            ),
            KBDocument(
                doc_id="claim:c_sleep_draft",
                doc_type="claim",
                entity_type="condition",
                entity_id="sleep",
                title="Draft sleep claim",
                summary="草稿睡眠 claim 只能出现在治理报表，不能算 reviewed 覆盖。",
                confidence=0.4,
                evidence_level="D",
                metadata_json={"domains": ["sleep"], "review_status": "draft"},
            ),
        ]
    )
    db.commit()

    coverage = get_knowledge_coverage_report(
        db, now=datetime(2026, 6, 27, tzinfo=UTC)
    )

    nutrition = coverage["domain_coverage"]["nutrition"]
    assert nutrition["documents"]["total"] == 3
    assert nutrition["documents"]["by_type"] == {"claim": 2, "eval_case": 1}
    assert nutrition["review_status"] == {"reviewed": 3}
    assert nutrition["source_coverage"]["claim_total"] == 2
    assert nutrition["source_coverage"]["claims_with_external_sources"] == 1
    assert nutrition["source_coverage"]["external_source_rate"] == 0.5
    assert nutrition["source_coverage"]["by_kind"] == {"guideline": 1}
    assert nutrition["eval_coverage"]["claim_total"] == 2
    assert nutrition["eval_coverage"]["eval_cases_total"] == 1
    assert nutrition["eval_coverage"]["claims_with_eval"] == 1
    assert nutrition["eval_coverage"]["eval_coverage_rate"] == 0.5
    assert nutrition["stale_risk"]["stale_claims"] == 1
    assert nutrition["stale_risk"]["missing_last_confirmed_claims"] == 0
    assert nutrition["stale_risk"]["by_decay_rate"] == {"fast": 1, "normal": 0, "slow": 0}
    assert nutrition["stale_risk"]["items"][0]["doc_id"] == "claim:c_nutrition_stale_without_source"

    sleep = coverage["domain_coverage"]["sleep"]
    assert sleep["review_status"] == {"draft": 1}
    assert sleep["source_coverage"]["claim_total"] == 1
    assert sleep["source_coverage"]["claims_with_external_sources"] == 0
    assert sleep["eval_coverage"]["claims_with_eval"] == 0
    assert sleep["stale_risk"]["missing_last_confirmed_claims"] == 1
