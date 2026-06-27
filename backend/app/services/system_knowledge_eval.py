"""Deterministic eval runner for reviewed system-KB eval_case artifacts."""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.system_knowledge import KBDocument


def run_system_kb_eval_cases(
    db: Session,
    *,
    case_ids: Iterable[str] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Run reviewed eval_case rows against local KB search and Twin lookup."""
    wanted = set(case_ids or [])
    query = (
        db.query(KBDocument)
        .filter(KBDocument.doc_type == "eval_case", KBDocument.is_archived.is_(False))
        .order_by(KBDocument.doc_id.asc())
    )
    cases = [
        doc for doc in query.all()
        if (doc.metadata_json or {}).get("review_status") == "reviewed"
        and (not wanted or ((doc.metadata_json or {}).get("case_id") or doc.doc_id) in wanted or doc.doc_id in wanted)
    ][:limit]

    results = [_run_eval_case(db, doc) for doc in cases]
    passed = sum(1 for result in results if result["passed"])
    failed = len(results) - passed
    return {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "cases": results,
    }


def _run_eval_case(db: Session, document: KBDocument) -> dict[str, Any]:
    metadata = document.metadata_json or {}
    expected = metadata.get("expected") or {}
    case_input = metadata.get("input") or {}
    case_id = str(metadata.get("case_id") or document.doc_id)
    failures: list[str] = []

    required_doc_ids = set(expected.get("required_doc_ids") or [])
    if required_doc_ids:
        missing = required_doc_ids - _reviewed_doc_ids(db, required_doc_ids)
        if missing:
            failures.append(f"missing_required_docs={sorted(missing)}")

    search_query = expected.get("search_query") or case_input.get("search_query")
    if search_query and required_doc_ids:
        found = _search_doc_ids(db, str(search_query))
        missing_from_search = required_doc_ids - found
        if missing_from_search:
            failures.append(f"search_missing={sorted(missing_from_search)}")

    lookup_twin = expected.get("lookup_twin") or case_input.get("lookup_twin")
    required_claim_ids = set(expected.get("required_claim_ids") or [])
    if lookup_twin and required_claim_ids:
        found_claims = _lookup_claim_ids(db, lookup_twin)
        missing_claims = required_claim_ids - found_claims
        if missing_claims:
            failures.append(f"lookup_missing={sorted(missing_claims)}")

    return {
        "case_id": case_id,
        "doc_id": document.doc_id,
        "passed": not failures,
        "failures": failures,
    }


def _reviewed_doc_ids(db: Session, doc_ids: set[str]) -> set[str]:
    if not doc_ids:
        return set()
    return {
        doc.doc_id
        for doc in db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
        if not doc.is_archived and (doc.metadata_json or {}).get("review_status") == "reviewed"
    }


def _search_doc_ids(db: Session, query: str) -> set[str]:
    from app.services.system_knowledge_service import search_knowledge

    result = search_knowledge(db, query, limit=30)
    return {
        (item.get("document") or {}).get("doc_id")
        for item in (result.get("results") or [])
        if (item.get("document") or {}).get("doc_id")
    }


def _lookup_claim_ids(db: Session, twin: dict[str, Any]) -> set[str]:
    from app.services.system_knowledge_service import lookup_for_twin

    result = lookup_for_twin(db, twin)
    return {
        claim.get("doc_id")
        for claim in (result.get("claims") or [])
        if claim.get("doc_id")
    }
