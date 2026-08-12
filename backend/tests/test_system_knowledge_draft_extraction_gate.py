import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.models.system_knowledge import KBDocument, KBEdge
from app.services.system_knowledge_importer import import_system_kb_artifacts
from app.services.system_knowledge_ingest import (
    IngestResult,
    review_draft_artifacts,
    validate_artifact_review_gate,
    write_draft_artifacts,
)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _draft_result(tmp_path: Path) -> IngestResult:
    result = IngestResult(
        source_root=tmp_path / "source",
        base_artifact_dir=tmp_path / "base",
        entities=[
            {
                "doc_id": "entity:condition:test-draft-gate",
                "doc_type": "entity",
                "entity_type": "condition",
                "entity_id": "test-draft-gate",
                "title": "Draft gate condition",
                "summary": "Draft entity must stay outside serving.",
                "domains": ["safety"],
                "metadata": {"review_status": "draft"},
            }
        ],
        claims=[
            {
                "doc_id": "claim:c_test_draft_gate",
                "doc_type": "claim",
                "entity_type": "condition",
                "entity_id": "test-draft-gate",
                "title": "Draft gate claim",
                "summary": "Draft claim must be reviewed before serving import.",
                "applies_when": ["twin.test == true"],
                "sources": ["guideline:test"],
                "metadata": {"review_status": "draft"},
            }
        ],
        relations=[
            {
                "src_doc_id": "entity:condition:test-draft-gate",
                "dst_doc_id": "claim:c_test_draft_gate",
                "relation": "has_claim",
                "confidence": 0.91,
                "metadata": {"review_status": "draft"},
            }
        ],
    )
    result.manifest = {
        "compiled_at": datetime(2026, 6, 27, 12, tzinfo=UTC).isoformat(),
        "ingest": {"pipeline": "unit_test_llm", "review_status": "draft"},
    }
    return result


def test_draft_artifacts_require_reviewer_gate_before_serving_import(tmp_path, db):
    artifact_dir = tmp_path / "draft-artifacts"

    draft_manifest = write_draft_artifacts(
        _draft_result(tmp_path),
        artifact_dir,
        extractor="llm:unit-test",
        note="unit test draft extraction",
    )

    assert draft_manifest["status"] == "draft"
    assert draft_manifest["requires_review"] is True
    assert draft_manifest["serving_allowed"] is False
    assert _json(artifact_dir / "draft_manifest.json")["extractor"] == "llm:unit-test"

    draft_gate = validate_artifact_review_gate(artifact_dir)

    assert draft_gate["serving_allowed"] is False
    assert draft_gate["documents"]["draft"] == 2
    assert draft_gate["relations"]["draft"] == 1
    assert "draft_artifacts_present" in draft_gate["blocking_reasons"]

    draft_import = import_system_kb_artifacts(db, artifact_dir, actor="test-draft-import")

    draft_counts = {
        "documents": 0,
        "edges": 0,
        "skipped_documents": 2,
        "skipped_edges": 1,
    }
    assert {key: draft_import[key] for key in draft_counts} == draft_counts
    assert draft_import["changed_document_ids"] == []
    assert db.query(KBDocument).filter(KBDocument.doc_id == "claim:c_test_draft_gate").count() == 0
    assert db.query(KBEdge).count() == 0

    with pytest.raises(ValueError, match="reviewer"):
        review_draft_artifacts(artifact_dir, reviewer=" ")

    review_manifest = review_draft_artifacts(
        artifact_dir,
        reviewer="clinician:unit-test",
        reviewed_at=datetime(2026, 6, 27, 13, tzinfo=UTC),
    )
    reviewed_gate = validate_artifact_review_gate(artifact_dir)

    assert review_manifest["validation"]["serving_allowed"] is True
    assert reviewed_gate["serving_allowed"] is True
    assert reviewed_gate["documents"]["reviewed"] == 2
    assert reviewed_gate["relations"]["reviewed"] == 1
    assert reviewed_gate["documents"]["draft"] == 0
    assert _json(artifact_dir / "manifest.json")["review"]["status"] == "reviewed"

    reviewed_import = import_system_kb_artifacts(db, artifact_dir, actor="test-reviewed-import")

    reviewed_counts = {
        "documents": 2,
        "edges": 1,
        "skipped_documents": 0,
        "skipped_edges": 0,
    }
    assert {key: reviewed_import[key] for key in reviewed_counts} == reviewed_counts
    assert reviewed_import["changed_document_ids"] == [
        "claim:c_test_draft_gate",
        "entity:condition:test-draft-gate",
    ]
    claim = db.query(KBDocument).filter(KBDocument.doc_id == "claim:c_test_draft_gate").one()
    edge = db.query(KBEdge).one()
    assert claim.metadata_json["review_status"] == "reviewed"
    assert claim.metadata_json["reviewed_by"] == "clinician:unit-test"
    assert edge.metadata_json["review_status"] == "reviewed"
