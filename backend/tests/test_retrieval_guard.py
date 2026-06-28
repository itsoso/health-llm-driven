from __future__ import annotations

from datetime import UTC, datetime

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_service import search_knowledge


def test_retrieval_guard_redacts_direct_identifiers_but_keeps_medical_terms():
    from app.services.retrieval_guard import guard_retrieval_query

    guarded = guard_retrieval_query(
        "张三 13800138000 alice@example.com 身份证 11010119900307777X LDL 3.8 MTHFR rs1801133"
    )

    assert guarded.query == (
        "张三 [PHONE] [EMAIL] 身份证 [IDCARD] LDL 3.8 MTHFR rs1801133"
    )
    assert guarded.redacted is True
    assert guarded.pii_hits == {"idcard": 1, "phone": 1, "email": 1}
    assert "LDL" in guarded.query
    assert "MTHFR" in guarded.query
    assert "rs1801133" in guarded.query
    assert "13800138000" not in guarded.query
    assert "alice@example.com" not in guarded.query


def test_system_kb_search_returns_safe_query_and_guard_metadata(db):
    db.add(
        KBDocument(
            doc_id="claim:c_ldl_tracking",
            doc_type="claim",
            entity_type="biomarker",
            entity_id="ldl",
            title="LDL-C 跟踪",
            summary="LDL-C 升高需要结合整体心血管风险评估。",
            confidence=0.74,
            evidence_level="B",
            applies_when=[],
            sources=["guideline:test"],
            last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
            metadata_json={"review_status": "reviewed"},
        )
    )
    db.commit()

    payload = search_knowledge(db, "LDL 13800138000 alice@example.com", limit=5)

    assert payload["query"] == "LDL [PHONE] [EMAIL]"
    assert payload["retrieval_plan"]["input_guard"] == {
        "policy": "deterministic_direct_identifier_redaction_v1",
        "redacted": True,
        "pii_hits": {"phone": 1, "email": 1},
    }
    assert "LDL-C 跟踪" in [item["document"]["title"] for item in payload["results"]]
