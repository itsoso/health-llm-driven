"""Global serving holds for medical claims awaiting independent clinical sign-off.

``review_status=reviewed`` is a content-workflow state, not sufficient evidence of
an independent clinician's approval. Claims listed here are excluded from every
System KB serving query and from the health authority router until a credentialed
review is recorded and this explicit hold is removed.
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
# from the same unsigned clinical pack must not leak through generic search.
CLINICAL_RELEASE_HOLD_CLAIM_IDS = CLINICAL_RELEASE_HOLD_DOCUMENT_IDS


def is_clinical_claim_serving_allowed(doc_id: object) -> bool:
    return (
        str(doc_id or "").strip()
        not in CLINICAL_RELEASE_HOLD_DOCUMENT_IDS
    )
