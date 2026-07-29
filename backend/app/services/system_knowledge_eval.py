"""Deterministic eval runner for reviewed system-KB eval_case artifacts.

Two layers of output, both computed in one pass over the reviewed eval_case docs:

1. Binary (backward-compatible): ``passed`` / ``failures`` per case, plus the
   aggregate ``total`` / ``passed`` / ``failed``. Unchanged semantics — existing
   callers keep working.
2. Ranked retrieval metrics (additive): each case that carries a rank-measurable
   expectation (a ``search_query`` + ``required_doc_ids``, and/or a ``lookup_twin``
   + ``required_claim_ids``) also gets per-leg hit RANK (1-based position of the
   first required target in the ordered result list, ``None`` if not found within
   the probe window). The aggregate adds ``recall@5``, ``recall@10`` and ``MRR``.

Metric definitions (documented so the numbers are honestly labeled):

* A *target* is one required doc_id (search leg) or claim_id (lookup leg).
* ``recall@k`` = mean over all rank-measurable targets of
  ``1 if target appears in the top-k ordered results else 0``. This is per-target
  recall, so a case requiring 2 docs contributes 2 targets.
* ``MRR`` = mean over rank-measurable *cases* of ``1 / rank_of_first_hit``
  (0 when no required target is found in the probe window). One case = one term,
  regardless of how many targets it requires; the reciprocal uses the best
  (smallest) rank among that case's targets.
* ``hit_rank`` on a case is the best rank across whichever legs apply.

The probe window is ``RANK_PROBE_LIMIT`` (default 30) — the same depth the
binary path already asked ``search_knowledge`` for. Ranks / recall only see this
window; a target below it is treated as a miss (rank ``None``), never fabricated.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.system_knowledge import KBDocument

# How deep into the ordered result list we look for a required target. Kept equal
# to the limit the binary search path already used so binary and ranked views
# agree on what "found" means.
RANK_PROBE_LIMIT = 30
_RUNTIME_ONLY_LOW_BACK_EVAL_IDS = frozenset(
    {
        "eval:low_back_neurologic_red_flags",
        "eval:low_back_self_management",
        "eval:low_back_imaging_boundary",
        "eval:chronic_low_back_holistic_care",
    }
)


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
    metrics = _aggregate_ranked_metrics(results)
    return {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "cases": results,
        "metrics": metrics,
    }


def _run_eval_case(db: Session, document: KBDocument) -> dict[str, Any]:
    metadata = document.metadata_json or {}
    expected = metadata.get("expected") or {}
    case_input = metadata.get("input") or {}
    case_id = str(metadata.get("case_id") or document.doc_id)
    failures: list[str] = []
    sealed_runtime_identity = (
        document.doc_id in _RUNTIME_ONLY_LOW_BACK_EVAL_IDS
        or case_id in _RUNTIME_ONLY_LOW_BACK_EVAL_IDS
    )
    runtime_eval = (
        document.doc_id in _RUNTIME_ONLY_LOW_BACK_EVAL_IDS
        and case_id == document.doc_id
    )
    if sealed_runtime_identity and case_id != document.doc_id:
        failures.append("eval_case_identity_mismatch")

    required_doc_ids = set(expected.get("required_doc_ids") or [])
    if required_doc_ids:
        missing = required_doc_ids - _reviewed_doc_ids(
            db,
            required_doc_ids,
            require_current_runtime_artifact=runtime_eval,
        )
        if missing:
            failures.append(f"missing_required_docs={sorted(missing)}")

    lookup_twin = expected.get("lookup_twin") or case_input.get("lookup_twin")
    required_claim_ids = set(expected.get("required_claim_ids") or [])
    advice_guard_result = _run_advice_guard_expectation(case_id, expected.get("advice_guard"))
    if advice_guard_result is not None:
        expected_allowed = advice_guard_result.get("expected_allowed")
        expected_reason = advice_guard_result.get("expected_reason")
        if expected_allowed is not None and advice_guard_result.get("allowed") != expected_allowed:
            failures.append(
                f"advice_guard_allowed={advice_guard_result.get('allowed')} expected={expected_allowed}"
            )
        if expected_reason and advice_guard_result.get("reason") != expected_reason:
            failures.append(
                f"advice_guard_reason={advice_guard_result.get('reason')} expected={expected_reason}"
            )

    # Ranked retrieval measurement (additive). Ranks are 1-based positions of the
    # first required target inside the ordered result list; None = not in probe window.
    search_rank: int | None = None
    search_targets: list[dict[str, Any]] = []
    lookup_rank: int | None = None
    lookup_targets: list[dict[str, Any]] = []

    search_query = expected.get("search_query") or case_input.get("search_query")
    if search_query and required_doc_ids:
        search_required_doc_ids = required_doc_ids - required_claim_ids
        ranked_ids = _search_doc_ids_ranked(
            db,
            str(search_query),
            runtime_eval=runtime_eval,
        )
        found = set(ranked_ids)
        missing_from_search = search_required_doc_ids - found
        if missing_from_search:
            failures.append(f"search_missing={sorted(missing_from_search)}")
        search_targets = _target_ranks(sorted(search_required_doc_ids), ranked_ids)
        search_rank = _best_rank(search_targets)

    if lookup_twin and required_claim_ids:
        ranked_claims = _lookup_claim_ids_ranked(db, lookup_twin)
        found_claims = set(ranked_claims)
        missing_claims = required_claim_ids - found_claims
        if missing_claims:
            failures.append(f"lookup_missing={sorted(missing_claims)}")
        lookup_targets = _target_ranks(sorted(required_claim_ids), ranked_claims)
        lookup_rank = _best_rank(lookup_targets)

    hit_rank = _best_rank(search_targets + lookup_targets)
    rank_measurable = bool(search_targets) or bool(lookup_targets)

    return {
        "case_id": case_id,
        "doc_id": document.doc_id,
        "passed": not failures,
        "failures": failures,
        # --- ranked metrics (additive) ---
        "rank_measurable": rank_measurable,
        "hit_rank": hit_rank,
        "search_rank": search_rank,
        "lookup_rank": lookup_rank,
        "advice_guard": advice_guard_result,
        "targets": search_targets + lookup_targets,
    }


def _aggregate_ranked_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold per-case ranked measurements into recall@5 / recall@10 / MRR."""
    measurable = [r for r in results if r.get("rank_measurable")]
    all_targets = [t for r in measurable for t in (r.get("targets") or [])]

    def recall_at(k: int) -> float:
        if not all_targets:
            return 0.0
        hits = sum(1 for t in all_targets if t.get("rank") is not None and t["rank"] <= k)
        return round(hits / len(all_targets), 4)

    # MRR: one term per measurable case, reciprocal of best rank (0 if no hit).
    reciprocals = []
    for r in measurable:
        best = r.get("hit_rank")
        reciprocals.append(1.0 / best if best else 0.0)
    mrr = round(sum(reciprocals) / len(reciprocals), 4) if reciprocals else 0.0

    return {
        "probe_limit": RANK_PROBE_LIMIT,
        "measurable_cases": len(measurable),
        "measurable_targets": len(all_targets),
        "recall@5": recall_at(5),
        "recall@10": recall_at(10),
        "mrr": mrr,
    }


def _target_ranks(target_ids: list[str], ranked_ids: list[str]) -> list[dict[str, Any]]:
    """For each required target, its 1-based position in ``ranked_ids`` or None."""
    position = {doc_id: idx + 1 for idx, doc_id in enumerate(ranked_ids)}
    return [{"id": target, "rank": position.get(target)} for target in target_ids]


def _best_rank(targets: list[dict[str, Any]]) -> int | None:
    ranks = [t["rank"] for t in targets if t.get("rank") is not None]
    return min(ranks) if ranks else None


def _reviewed_doc_ids(
    db: Session,
    doc_ids: set[str],
    *,
    require_current_runtime_artifact: bool = False,
) -> set[str]:
    if not doc_ids:
        return set()
    from app.services.health_evidence.authority import (
        is_current_health_evidence_document,
    )
    from app.services.system_knowledge_service import serialize_document

    return {
        doc.doc_id
        for doc in db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
        if not doc.is_archived and (doc.metadata_json or {}).get("review_status") == "reviewed"
        and (
            not require_current_runtime_artifact
            or is_current_health_evidence_document(serialize_document(doc))
        )
    }


def _search_doc_ids_ranked(
    db: Session,
    query: str,
    *,
    runtime_eval: bool = False,
) -> list[str]:
    """Ordered doc_ids from search_knowledge, preserving fusion rank (dedup, keep-first)."""
    from app.services.health_evidence.authority import (
        is_current_health_evidence_document,
    )
    from app.services.system_knowledge_service import (
        search_health_evidence_runtime_claims,
        search_knowledge,
    )

    search = (
        search_health_evidence_runtime_claims
        if runtime_eval
        else search_knowledge
    )
    result = search(db, query, limit=RANK_PROBE_LIMIT)
    ordered: list[str] = []
    seen: set[str] = set()
    for item in (result.get("results") or []):
        stored_document = item.get("document") or {}
        if (
            runtime_eval
            and not is_current_health_evidence_document(stored_document)
        ):
            continue
        doc_id = stored_document.get("doc_id")
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            ordered.append(doc_id)
    return ordered


def _search_doc_ids(db: Session, query: str) -> set[str]:
    return set(_search_doc_ids_ranked(db, query))


def _lookup_claim_ids_ranked(db: Session, twin: dict[str, Any]) -> list[str]:
    """Ordered claim doc_ids from lookup_for_twin, preserving lookup order (dedup)."""
    from app.services.system_knowledge_service import lookup_for_twin

    result = lookup_for_twin(db, twin)
    ordered: list[str] = []
    seen: set[str] = set()
    for claim in (result.get("claims") or []):
        doc_id = claim.get("doc_id")
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            ordered.append(doc_id)
    return ordered


def _lookup_claim_ids(db: Session, twin: dict[str, Any]) -> set[str]:
    return set(_lookup_claim_ids_ranked(db, twin))


def _run_advice_guard_expectation(
    case_id: str,
    guard_spec: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not guard_spec:
        return None

    from app.services.advice_guard import AdviceCandidate, AdviceGuard, AdviceGuardError

    payload = dict(guard_spec.get("candidate") or {})
    allowed_fields = {field.name for field in fields(AdviceCandidate)}
    defaults = {
        "user_id": 0,
        "source": "system_kb_eval",
        "source_id": case_id,
        "domain": "metabolic",
        "title": case_id,
        "body": "",
        "metric_key": "eval_case",
        "target_value": "boundary",
        "evidence_tier": "system_kb_eval",
        "confidence": "medium",
        "claim_boundary": "Health management guidance only; not diagnosis, prescription, or treatment.",
        "evidence_refs": ["claim:system_kb_eval_boundary"],
        "evidence_source_types": ["eval_case"],
        "verification_metric": "human_review",
        "risk_level": "medium",
    }
    defaults.update({key: value for key, value in payload.items() if key in allowed_fields})

    try:
        decision = AdviceGuard(existing=[]).evaluate(AdviceCandidate(**defaults))
        return {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "expected_allowed": guard_spec.get("allowed"),
            "expected_reason": guard_spec.get("reason"),
        }
    except AdviceGuardError as exc:
        return {
            "allowed": False,
            "reason": "contract_error",
            "error": str(exc),
            "expected_allowed": guard_spec.get("allowed"),
            "expected_reason": guard_spec.get("reason"),
        }
