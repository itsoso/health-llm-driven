from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.models.system_knowledge import KBAudit, KBDocument
from app.services.clinical_claim_release import (
    CLINICAL_RELEASE_HOLD_DOCUMENT_IDS,
)
from scripts.quarantine_runtime_only_kb import (
    quarantine_runtime_only_documents,
    runtime_only_document_ids,
)


SEED_MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "system_kb_v2_seed"
    / "review_manifest.json"
)


def _manifest():
    return json.loads(SEED_MANIFEST.read_text(encoding="utf-8"))


def _expected_document_types() -> dict[str, str]:
    return {
        doc_id: (
            "claim"
            if doc_id.startswith("claim:")
            else "entity"
            if doc_id.startswith("entity:")
            else "eval_case"
        )
        for doc_id in CLINICAL_RELEASE_HOLD_DOCUMENT_IDS
    }


def test_runtime_only_document_ids_equal_the_sealed_release_policy():
    assert runtime_only_document_ids(_manifest()) == tuple(
        sorted(CLINICAL_RELEASE_HOLD_DOCUMENT_IDS)
    )


def test_runtime_only_manifest_fails_closed_if_generic_hold_is_not_explicit():
    manifest = _manifest()
    manifest["authority_packs"][0]["generic_serving_allowed"] = True
    with pytest.raises(ValueError, match="generic_serving_allowed=false"):
        runtime_only_document_ids(manifest)


def test_runtime_only_manifest_rejects_extra_document():
    manifest = _manifest()
    manifest["authority_packs"][0]["claim_ids"].append("claim:unexpected")

    with pytest.raises(ValueError, match="sealed document policy mismatch"):
        runtime_only_document_ids(manifest)


def test_runtime_only_manifest_rejects_missing_document():
    manifest = _manifest()
    manifest["authority_packs"][0]["eval_case_ids"].pop()

    with pytest.raises(ValueError, match="sealed document policy mismatch"):
        runtime_only_document_ids(manifest)


def test_runtime_only_manifest_rejects_duplicate_document():
    manifest = _manifest()
    duplicated = manifest["authority_packs"][0]["claim_ids"][0]
    manifest["authority_packs"][0]["claim_ids"].append(duplicated)

    with pytest.raises(ValueError, match="duplicate document ID"):
        runtime_only_document_ids(manifest)


def test_runtime_only_manifest_rejects_cross_type_document():
    manifest = _manifest()
    claim_id = manifest["authority_packs"][0]["claim_ids"].pop()
    manifest["authority_packs"][0]["entity_ids"].append(claim_id)

    with pytest.raises(ValueError, match="sealed document type mismatch"):
        runtime_only_document_ids(manifest)


@pytest.mark.parametrize(
    "malformed_id",
    [
        "",
        " claim:c_low_back_emergency_neurologic_red_flags",
        7,
    ],
)
def test_runtime_only_manifest_rejects_malformed_document_id(malformed_id):
    manifest = _manifest()
    manifest["authority_packs"][0]["claim_ids"][0] = malformed_id

    with pytest.raises(ValueError, match="invalid ID"):
        runtime_only_document_ids(manifest)


def test_revoked_copy_cannot_expand_or_duplicate_the_sealed_quarantine():
    manifest = _manifest()
    duplicate_pack = deepcopy(manifest["authority_packs"][0])
    duplicate_pack["serving_allowed"] = False
    manifest["authority_packs"].append(duplicate_pack)

    with pytest.raises(ValueError, match="duplicate document ID"):
        runtime_only_document_ids(manifest)


def test_quarantine_archives_exact_typed_documents_and_audits_counts_only(db):
    target_ids = runtime_only_document_ids(_manifest())
    expected_types = _expected_document_types()
    for doc_id in (*target_ids, "claim:generic"):
        db.add(
            KBDocument(
                doc_id=doc_id,
                doc_type=expected_types.get(doc_id, "claim"),
                title=f"title:{doc_id}",
                summary=f"summary:{doc_id}",
                body=f"body:{doc_id}",
                is_archived=False,
                metadata_json={"review_status": "reviewed"},
            )
        )
    db.commit()

    report = quarantine_runtime_only_documents(
        db,
        manifest=_manifest(),
        actor="rollback:test",
    )

    assert report == {
        "target_documents": len(target_ids),
        "matched_documents": len(target_ids),
        "archived_documents": len(target_ids),
    }
    stored = {
        row.doc_id: row.is_archived
        for row in db.query(KBDocument).order_by(KBDocument.doc_id).all()
    }
    assert stored["claim:generic"] is False
    assert all(stored[doc_id] is True for doc_id in target_ids)
    audit = (
        db.query(KBAudit)
        .filter(KBAudit.op == "rollback_kb_quarantine")
        .one()
    )
    assert audit.actor == "rollback:test"
    assert audit.diff == report
    assert set(audit.diff) == {
        "target_documents",
        "matched_documents",
        "archived_documents",
    }
    assert not any(doc_id in str(audit.diff) for doc_id in target_ids)


def test_quarantine_succeeds_when_none_of_the_sealed_documents_exist(db):
    report = quarantine_runtime_only_documents(
        db,
        manifest=_manifest(),
        actor="rollback:test-empty-db",
    )

    assert report == {
        "target_documents": len(CLINICAL_RELEASE_HOLD_DOCUMENT_IDS),
        "matched_documents": 0,
        "archived_documents": 0,
    }


def test_quarantine_succeeds_when_only_part_of_the_sealed_policy_exists(db):
    doc_id, doc_type = next(iter(_expected_document_types().items()))
    db.add(
        KBDocument(
            doc_id=doc_id,
            doc_type=doc_type,
            is_archived=False,
            metadata_json={"review_status": "reviewed"},
        )
    )
    db.commit()

    report = quarantine_runtime_only_documents(
        db,
        manifest=_manifest(),
        actor="rollback:test-partial",
    )

    assert report["matched_documents"] == 1
    assert report["archived_documents"] == 1
    assert db.get(KBDocument, doc_id).is_archived is True


def test_quarantine_rejects_active_expected_id_with_wrong_database_type(db):
    doc_id = next(iter(CLINICAL_RELEASE_HOLD_DOCUMENT_IDS))
    expected_type = _expected_document_types()[doc_id]
    wrong_type = "entity" if expected_type != "entity" else "claim"
    db.add(
        KBDocument(
            doc_id=doc_id,
            doc_type=wrong_type,
            is_archived=False,
            metadata_json={"review_status": "reviewed"},
        )
    )
    db.commit()

    with pytest.raises(RuntimeError, match="quarantine incomplete"):
        quarantine_runtime_only_documents(
            db,
            manifest=_manifest(),
            actor="rollback:test-cross-type-db",
        )

    assert db.get(KBDocument, doc_id).is_archived is False
    assert (
        db.query(KBAudit)
        .filter(KBAudit.op == "rollback_kb_quarantine")
        .count()
        == 0
    )


def test_quarantine_fails_closed_when_manifest_has_no_runtime_only_targets(db):
    with pytest.raises(ValueError, match="sealed document policy mismatch"):
        quarantine_runtime_only_documents(
            db,
            manifest={"authority_packs": []},
            actor="rollback:test-empty-manifest",
        )
