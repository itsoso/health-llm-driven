"""Global medical-document holds with one explicit runtime-only release scope.

``review_status=reviewed`` is a content-workflow state, not sufficient evidence of
an independent clinician's approval. Documents listed here stay excluded from every
generic System KB serving query. Five source-verified claims have a separately
recorded product-owner decision allowing only the sealed health-evidence runtime;
that scoped exception does not release claim detail, generic search, entities, or
eval documents.
"""

from __future__ import annotations


CLINICAL_RELEASE_HOLD_DOCUMENT_IDS = frozenset(
    {
        "claim:c_low_back_emergency_neurologic_red_flags",
        "claim:c_low_back_serious_cause_screening_boundary",
        "claim:c_low_back_self_management_activity_boundary",
        "claim:c_low_back_imaging_not_routine_boundary",
        "claim:c_chronic_low_back_holistic_care_boundary",
        "entity:condition:low-back-pain",
        "eval:low_back_neurologic_red_flags",
        "eval:low_back_self_management",
        "eval:low_back_imaging_boundary",
        "eval:chronic_low_back_holistic_care",
    }
)
# Backward-compatible name used by the claim detail and candidate-pack tests.
# The serving hold is intentionally broader than claims: eval/entity documents
# from the same runtime-only pack must not leak through generic search.
CLINICAL_RELEASE_HOLD_CLAIM_IDS = CLINICAL_RELEASE_HOLD_DOCUMENT_IDS

HEALTH_EVIDENCE_RUNTIME_SERVING_SCOPE = "health_evidence_runtime"
HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS = frozenset(
    {
        "claim:c_low_back_emergency_neurologic_red_flags",
        "claim:c_low_back_serious_cause_screening_boundary",
        "claim:c_low_back_self_management_activity_boundary",
        "claim:c_low_back_imaging_not_routine_boundary",
        "claim:c_chronic_low_back_holistic_care_boundary",
    }
)


def is_clinical_claim_serving_allowed(
    doc_id: object,
    serving_scope: object = None,
) -> bool:
    normalized_id = str(doc_id or "").strip()
    normalized_scope = str(serving_scope or "").strip()
    if normalized_scope == HEALTH_EVIDENCE_RUNTIME_SERVING_SCOPE:
        return normalized_id in HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS
    if normalized_id not in CLINICAL_RELEASE_HOLD_DOCUMENT_IDS:
        return True
    return False
