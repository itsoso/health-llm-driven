import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.api import desktop as desktop_api
from app.models.system_knowledge import KBDocument
from app.services import genetic_report, system_knowledge_service
from app.services.system_knowledge_importer import import_system_kb_artifacts
from app.services.system_knowledge_eval import run_system_kb_eval_cases
from scripts import verify_runtime_only_kb_contract as contract_probe
from scripts.verify_runtime_only_kb_contract import (
    verify_enabled_runtime,
    verify_runtime_only_database,
    verify_runtime_only_policy,
)


REVIEW_MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "system_kb_v2_seed"
    / "review_manifest.json"
)


def _manifest():
    return json.loads(REVIEW_MANIFEST.read_text(encoding="utf-8"))


def test_runtime_only_policy_matches_manifest_hold_and_release_sets():
    report = verify_runtime_only_policy(_manifest())

    assert report == {
        "runtime_packs": 1,
        "target_documents": 11,
        "released_claims": 5,
    }


def test_runtime_only_policy_fails_closed_on_manifest_drift():
    manifest = deepcopy(_manifest())
    manifest["authority_packs"][0]["claim_ids"].append("claim:unexpected")

    with pytest.raises(RuntimeError, match="policy drift"):
        verify_runtime_only_policy(manifest)


def test_runtime_only_policy_fails_if_code_holds_unrelated_knowledge(monkeypatch):
    monkeypatch.setattr(
        contract_probe,
        "CLINICAL_RELEASE_HOLD_DOCUMENT_IDS",
        contract_probe.CLINICAL_RELEASE_HOLD_DOCUMENT_IDS
        | {"claim:unrelated"},
    )

    with pytest.raises(RuntimeError, match="hold set mismatch"):
        verify_runtime_only_policy(_manifest())


def test_runtime_only_policy_rejects_duplicate_document_id_across_fields():
    manifest = deepcopy(_manifest())
    first_claim = manifest["authority_packs"][0]["claim_ids"][0]
    manifest["authority_packs"][0]["entity_ids"].append(first_claim)

    with pytest.raises(RuntimeError, match="duplicate document ID"):
        verify_runtime_only_policy(manifest)


def test_runtime_only_policy_rejects_duplicate_id_across_enabled_and_revoked_packs():
    manifest = deepcopy(_manifest())
    first_claim = manifest["authority_packs"][0]["claim_ids"][0]
    manifest["authority_packs"].append(
        {
            "claim_ids": [first_claim],
            "entity_ids": [],
            "eval_case_ids": [],
            "serving_allowed": False,
            "serving_scope": "health_evidence_runtime",
            "generic_serving_allowed": False,
        }
    )

    with pytest.raises(RuntimeError, match="duplicate document ID"):
        verify_runtime_only_policy(manifest)


def test_guard_and_staged_contracts_allow_fully_revoked_pack_but_enabled_fails(db):
    manifest = deepcopy(_manifest())
    manifest["authority_packs"][0]["serving_allowed"] = False

    guard_report = verify_runtime_only_database(
        db,
        manifest=manifest,
        require_present=False,
        allow_fully_revoked=True,
    )
    assert guard_report["matched_documents"] == 0

    import_system_kb_artifacts(
        db,
        REVIEW_MANIFEST.parent,
        actor="test:runtime-contract-fully-revoked",
    )
    staged_report = verify_runtime_only_database(
        db,
        manifest=manifest,
        require_present=True,
        allow_fully_revoked=True,
    )
    assert staged_report["matched_documents"] == 11

    with pytest.raises(RuntimeError, match="sealed claim set mismatch"):
        verify_runtime_only_policy(manifest)
    with pytest.raises(RuntimeError, match="no release eval cases"):
        verify_enabled_runtime(db, manifest=manifest)


def test_activated_database_contract_proves_generic_hold_and_runtime_exact_set(db):
    manifest = _manifest()
    artifact_dir = REVIEW_MANIFEST.parent
    import_system_kb_artifacts(db, artifact_dir, actor="test:runtime-contract")

    report = verify_runtime_only_database(
        db,
        manifest=manifest,
        require_present=True,
    )

    assert report == {
        "target_documents": 11,
        "matched_documents": 11,
        "generic_eligible_documents": 0,
        "runtime_eligible_claims": 5,
        "desktop_held_documents": 0,
        "genetic_held_claims": 0,
    }


def test_activated_database_contract_rejects_wrong_runtime_doc_type(db):
    manifest = _manifest()
    import_system_kb_artifacts(
        db,
        REVIEW_MANIFEST.parent,
        actor="test:runtime-contract-wrong-type",
    )
    first_claim = manifest["authority_packs"][0]["claim_ids"][0]
    db.query(KBDocument).filter(KBDocument.doc_id == first_claim).update(
        {"doc_type": "entity"}
    )
    db.commit()

    with pytest.raises(RuntimeError, match="active reviewed pack mismatch"):
        verify_runtime_only_database(
            db,
            manifest=manifest,
            require_present=True,
        )


def test_activated_database_contract_rejects_archived_pack_member(db):
    manifest = _manifest()
    import_system_kb_artifacts(
        db,
        REVIEW_MANIFEST.parent,
        actor="test:runtime-contract-archived",
    )
    entity_id = manifest["authority_packs"][0]["entity_ids"][0]
    db.query(KBDocument).filter(KBDocument.doc_id == entity_id).update(
        {"is_archived": True}
    )
    db.commit()

    with pytest.raises(RuntimeError, match="active reviewed pack mismatch"):
        verify_runtime_only_database(
            db,
            manifest=manifest,
            require_present=True,
        )


def test_activated_database_contract_rejects_tampered_sealed_claim(db):
    manifest = _manifest()
    import_system_kb_artifacts(
        db,
        REVIEW_MANIFEST.parent,
        actor="test:runtime-contract-tamper",
    )
    first_claim = manifest["authority_packs"][0]["claim_ids"][0]
    db.query(KBDocument).filter(KBDocument.doc_id == first_claim).update(
        {"summary": "tampered"}
    )
    db.commit()

    with pytest.raises(RuntimeError, match="sealed artifact mismatch"):
        verify_runtime_only_database(
            db,
            manifest=manifest,
            require_present=True,
        )


def test_activated_database_contract_fails_if_import_is_incomplete(db):
    manifest = _manifest()
    first_claim = manifest["authority_packs"][0]["claim_ids"][0]
    db.add(
        KBDocument(
            doc_id=first_claim,
            doc_type="claim",
            title="partial",
            metadata_json={"review_status": "reviewed"},
            is_archived=False,
        )
    )
    db.commit()

    with pytest.raises(RuntimeError, match="incomplete"):
        verify_runtime_only_database(
            db,
            manifest=manifest,
            require_present=True,
        )


def test_guard_database_contract_allows_not_yet_imported_pack(db):
    report = verify_runtime_only_database(
        db,
        manifest=_manifest(),
        require_present=False,
    )

    assert report["matched_documents"] == 0
    assert report["generic_eligible_documents"] == 0
    assert report["runtime_eligible_claims"] == 0
    assert report["genetic_held_claims"] == 0


def test_database_contract_fails_if_genetic_surface_exposes_held_claim(
    db,
    monkeypatch,
):
    held_claim = _manifest()["authority_packs"][0]["claim_ids"][0]

    def _leaking_attach(_db, items):
        items[0]["evidence_refs"] = [held_claim]

    monkeypatch.setattr(
        genetic_report,
        "_attach_evidence_refs",
        _leaking_attach,
    )

    with pytest.raises(RuntimeError, match="Genetic evidence projection"):
        verify_runtime_only_database(
            db,
            manifest=_manifest(),
            require_present=False,
        )


def test_database_contract_fails_if_desktop_surface_drops_visible_sentinel(
    db,
    monkeypatch,
):
    real_knowledge_summary = desktop_api._knowledge_summary

    def _dropping_visible_summary(_db):
        summary = real_knowledge_summary(_db)
        summary["recent_documents"] = [
            item
            for item in summary["recent_documents"]
            if "runtime-visible" not in item["doc_id"]
        ]
        return summary

    monkeypatch.setattr(
        desktop_api,
        "_knowledge_summary",
        _dropping_visible_summary,
    )

    with pytest.raises(RuntimeError, match="Desktop.*visible sentinel"):
        verify_runtime_only_database(
            db,
            manifest=_manifest(),
            require_present=False,
        )


def test_database_contract_fails_if_genetic_surface_drops_visible_claim(
    db,
    monkeypatch,
):
    def _dropping_attach(_db, items):
        for item in items:
            item["evidence_refs"] = []

    monkeypatch.setattr(
        genetic_report,
        "_attach_evidence_refs",
        _dropping_attach,
    )

    with pytest.raises(RuntimeError, match="Genetic.*visible sentinel"):
        verify_runtime_only_database(
            db,
            manifest=_manifest(),
            require_present=False,
        )


def test_enabled_runtime_runs_all_released_low_back_eval_cases(db):
    manifest = _manifest()
    import_system_kb_artifacts(
        db,
        REVIEW_MANIFEST.parent,
        actor="test:runtime-contract-enabled",
    )

    report = verify_enabled_runtime(db, manifest=manifest)

    assert report == {
        "runtime_eval_cases": 5,
        "runtime_eval_failures": 0,
    }


def test_enabled_runtime_falsifies_query_ignoring_retrieval_that_returns_all_claims(
    db,
    monkeypatch,
):
    manifest = _manifest()
    import_system_kb_artifacts(
        db,
        REVIEW_MANIFEST.parent,
        actor="test:runtime-contract-query-ignoring-retrieval",
    )
    released_claim_ids = list(
        manifest["authority_packs"][0]["claim_ids"]
    )
    released_documents = {
        document.doc_id: document
        for document in db.query(KBDocument)
        .filter(KBDocument.doc_id.in_(released_claim_ids))
        .all()
    }
    query_calls: list[str] = []

    def _query_ignoring_search(_db, query, *, limit):
        query_calls.append(query)
        return {
            "results": [
                {
                    "document": system_knowledge_service.serialize_document(
                        released_documents[doc_id]
                    )
                }
                for doc_id in released_claim_ids
            ]
        }

    monkeypatch.setattr(
        system_knowledge_service,
        "search_health_evidence_runtime_claims",
        _query_ignoring_search,
    )

    eval_ids = frozenset(
        manifest["authority_packs"][0]["eval_case_ids"]
    )
    report = run_system_kb_eval_cases(
        db,
        exact_doc_ids=eval_ids,
        limit=len(eval_ids),
    )

    assert len(query_calls) == len(eval_ids)
    assert report["failed"] == len(eval_ids) - 1
    assert sum(
        case["hit_rank"] == 1 for case in report["cases"]
    ) == 1
    assert all(
        case["passed"] is (case["hit_rank"] == 1)
        for case in report["cases"]
    )
    with pytest.raises(RuntimeError, match="enabled runtime eval failed"):
        verify_enabled_runtime(db, manifest=manifest)


def test_runtime_eval_artifact_rejects_expected_query_different_from_input():
    with pytest.raises(RuntimeError, match="executable search query mismatch"):
        contract_probe._eval_artifact_material(
            doc_id="eval:sealed",
            case_id="eval:sealed",
            case_input={"search_query": "authoritative input query"},
            expected={
                "search_query": "different expected query",
                "required_doc_ids": ["claim:sealed"],
            },
        )


def test_enabled_runtime_queries_exact_manifest_doc_ids_without_case_crowd_out(db):
    manifest = _manifest()
    import_system_kb_artifacts(
        db,
        REVIEW_MANIFEST.parent,
        actor="test:runtime-contract-eval-crowd-out",
    )
    first_eval_id = manifest["authority_packs"][0]["eval_case_ids"][0]
    first_eval = (
        db.query(KBDocument)
        .filter(KBDocument.doc_id == first_eval_id)
        .one()
    )
    db.add(
        KBDocument(
            doc_id="eval:000-runtime-case-alias",
            doc_type="eval_case",
            title="must not crowd out exact manifest eval",
            metadata_json={
                **deepcopy(first_eval.metadata_json or {}),
                "case_id": first_eval_id,
                "review_status": "reviewed",
            },
            is_archived=False,
        )
    )
    db.commit()

    report = verify_enabled_runtime(db, manifest=manifest)

    assert report == {
        "runtime_eval_cases": 5,
        "runtime_eval_failures": 0,
    }


def test_enabled_runtime_rejects_tampered_eval_expected_metadata(db):
    manifest = _manifest()
    import_system_kb_artifacts(
        db,
        REVIEW_MANIFEST.parent,
        actor="test:runtime-contract-eval-tamper",
    )
    first_eval_id = manifest["authority_packs"][0]["eval_case_ids"][0]
    first_eval = (
        db.query(KBDocument)
        .filter(KBDocument.doc_id == first_eval_id)
        .one()
    )
    first_eval.metadata_json = {
        **(first_eval.metadata_json or {}),
        "expected": {},
    }
    db.commit()

    with pytest.raises(RuntimeError, match="eval artifact mismatch"):
        verify_enabled_runtime(db, manifest=manifest)


def test_enabled_runtime_rejects_tampered_eval_input_metadata(db):
    manifest = _manifest()
    import_system_kb_artifacts(
        db,
        REVIEW_MANIFEST.parent,
        actor="test:runtime-contract-eval-input-tamper",
    )
    first_eval_id = manifest["authority_packs"][0]["eval_case_ids"][0]
    first_eval = (
        db.query(KBDocument)
        .filter(KBDocument.doc_id == first_eval_id)
        .one()
    )
    first_eval.metadata_json = {
        **(first_eval.metadata_json or {}),
        "input": {"search_query": "tampered runtime query"},
    }
    db.commit()

    with pytest.raises(RuntimeError, match="eval artifact mismatch"):
        verify_enabled_runtime(db, manifest=manifest)


def test_cli_acquires_and_proves_release_lock_through_database_probe(
    monkeypatch,
):
    from app import database

    events = []

    class _FakeSession:
        def rollback(self):
            events.append("rollback")

        def close(self):
            events.append("close")

    fake_db = _FakeSession()
    monkeypatch.setattr(database, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(
        contract_probe,
        "acquire_system_kb_release_mutation_lock",
        lambda db: events.append("lock"),
        raising=False,
    )
    monkeypatch.setattr(
        contract_probe,
        "_assert_system_kb_release_mutation_lock_held",
        lambda db: events.append("lock-held"),
        raising=False,
    )
    monkeypatch.setattr(
        contract_probe,
        "verify_runtime_only_policy",
        lambda manifest, **kwargs: {
            "runtime_packs": 1,
            "target_documents": 11,
            "released_claims": 5,
        },
    )

    def _database_probe(db, **kwargs):
        events.append("database")
        return {
            "target_documents": 11,
            "matched_documents": 0,
            "generic_eligible_documents": 0,
            "runtime_eligible_claims": 0,
            "desktop_held_documents": 0,
            "genetic_held_claims": 0,
        }

    monkeypatch.setattr(
        contract_probe,
        "verify_runtime_only_database",
        _database_probe,
    )
    monkeypatch.setattr(
        contract_probe.settings,
        "health_evidence_runtime_enabled",
        False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_runtime_only_kb_contract.py",
            "--phase",
            "guard",
            "--review-manifest",
            str(REVIEW_MANIFEST),
        ],
    )

    assert contract_probe.main() == 0
    assert events == [
        "lock",
        "lock-held",
        "database",
        "lock-held",
        "lock-held",
        "rollback",
        "close",
    ]


def test_cli_probe_fails_loud_instead_of_releasing_transaction_lock(
    monkeypatch,
):
    from app import database

    events = []

    class _FakeSession:
        def rollback(self):
            events.append("underlying-rollback")

        def close(self):
            events.append("close")

    fake_db = _FakeSession()
    monkeypatch.setattr(database, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(
        contract_probe,
        "acquire_system_kb_release_mutation_lock",
        lambda db: events.append("lock"),
        raising=False,
    )
    monkeypatch.setattr(
        contract_probe,
        "_assert_system_kb_release_mutation_lock_held",
        lambda db: events.append("lock-held"),
        raising=False,
    )
    monkeypatch.setattr(
        contract_probe,
        "verify_runtime_only_policy",
        lambda manifest, **kwargs: {
            "runtime_packs": 1,
            "target_documents": 11,
            "released_claims": 5,
        },
    )

    def _database_probe(db, **kwargs):
        events.append("database")
        db.rollback()
        raise AssertionError("probe rollback must fail before this line")

    monkeypatch.setattr(
        contract_probe,
        "verify_runtime_only_database",
        _database_probe,
    )
    monkeypatch.setattr(
        contract_probe.settings,
        "health_evidence_runtime_enabled",
        False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_runtime_only_kb_contract.py",
            "--phase",
            "guard",
            "--review-manifest",
            str(REVIEW_MANIFEST),
        ],
    )

    with pytest.raises(RuntimeError, match="attempted to rollback"):
        contract_probe.main()

    assert events == [
        "lock",
        "lock-held",
        "database",
        "underlying-rollback",
        "close",
    ]


def test_postgres_cli_guard_probe_keeps_exact_release_lock_held(
    db,
    monkeypatch,
):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("exact advisory lock assertion requires PostgreSQL")

    from app import database

    monkeypatch.setattr(
        database,
        "SessionLocal",
        sessionmaker(bind=db.get_bind()),
    )
    monkeypatch.setattr(
        contract_probe.settings,
        "health_evidence_runtime_enabled",
        False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_runtime_only_kb_contract.py",
            "--phase",
            "guard",
            "--review-manifest",
            str(REVIEW_MANIFEST),
        ],
    )

    assert contract_probe.main() == 0
