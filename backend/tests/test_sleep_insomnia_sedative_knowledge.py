"""Insomnia / sedative sleep-safety reviewed-KB integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

SLEEP_SAFETY_CLAIMS = {
    "cbti": "claim:c_sleep_insomnia_cbti_first_line_boundary",
    "sedative_alcohol": "claim:c_sleep_sedative_alcohol_impairment_boundary",
    "sedative_hypoxia": "claim:c_sleep_sedative_hypoxia_no_self_rescue_boundary",
    "drowsy_driving": "claim:c_sleep_drowsy_driving_safety_boundary",
}

SLEEP_SAFETY_CONTRAINDICATIONS = {
    "cbti": "contraindication:sleep_insomnia_no_self_sedative_or_sleep_restriction",
    "sedative_alcohol": "contraindication:sleep_sedative_alcohol_no_combination",
    "sedative_hypoxia": "contraindication:sleep_sedative_hypoxia_no_self_rescue",
    "drowsy_driving": "contraindication:sleep_drowsy_driving_no_push_through",
}

SLEEP_SAFETY_EVALS = {
    "cbti": "eval:sleep_insomnia_cbti_boundary",
    "sedative_alcohol": "eval:sleep_sedative_alcohol_boundary",
    "sedative_hypoxia": "eval:sleep_sedative_hypoxia_boundary",
    "drowsy_driving": "eval:sleep_drowsy_driving_boundary",
}


def _claim(doc_id: str) -> dict[str, Any]:
    for line in CLAIMS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("doc_id") == doc_id:
            return row
    raise AssertionError(f"missing seed claim: {doc_id}")


def _twin(
    *,
    conditions: list[str] | None = None,
    medications: list[dict[str, Any]] | None = None,
    sleep_hours: float | None = None,
    spo2_min: int | None = None,
    spo2_odi: float | None = None,
):
    from app.twin.schema import (
        ChronicConditionState,
        HealthTwin,
        MedicationState,
        PhysiologicalState,
        TwinMeta,
    )

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime(2026, 6, 27, tzinfo=UTC)))
    if conditions:
        twin.chronic = ChronicConditionState(active_conditions=conditions)
    if medications is not None:
        twin.medication = MedicationState(active_meds=medications, has_any=bool(medications))
    if sleep_hours is not None or spo2_min is not None or spo2_odi is not None:
        twin.physiological = PhysiologicalState(
            sleep_duration_h_latest=sleep_hours,
            spo2_min_overnight=spo2_min,
            spo2_odi=spo2_odi,
        )
    return twin


def _claim_ids_for_twin(db, twin) -> set[str]:
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    payload = system_kb_twin_payload_from_health_twin(twin)
    result = lookup_for_twin(db, payload)
    return {claim.get("doc_id") for claim in result.get("claims") or []}


def test_sleep_safety_claims_contraindications_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:sleep_safety_import")
    assert counts["skipped_documents"] == 0

    doc_ids = (
        set(SLEEP_SAFETY_CLAIMS.values())
        | set(SLEEP_SAFETY_CONTRAINDICATIONS.values())
        | set(SLEEP_SAFETY_EVALS.values())
    )
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == doc_ids
    for doc_id in SLEEP_SAFETY_CLAIMS.values():
        assert by_id[doc_id].doc_type == "claim"
    for doc_id in SLEEP_SAFETY_CONTRAINDICATIONS.values():
        assert by_id[doc_id].doc_type == "contraindication"
    for doc_id in SLEEP_SAFETY_EVALS.values():
        assert by_id[doc_id].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed", doc.doc_id


def test_insomnia_cbti_lookup_requires_insomnia_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:sleep_cbti_lookup")

    insomnia = _twin(conditions=["慢性失眠"])
    assert SLEEP_SAFETY_CLAIMS["cbti"] in _claim_ids_for_twin(db, insomnia)

    ordinary_sleep_goal = _twin(conditions=["训练后疲劳"])
    assert SLEEP_SAFETY_CLAIMS["cbti"] not in _claim_ids_for_twin(db, ordinary_sleep_goal)


def test_sedative_alcohol_lookup_requires_both_contexts(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:sleep_sedative_alcohol_lookup")

    risky = _twin(
        conditions=["睡前饮酒"],
        medications=[{"name": "唑吡坦", "generic_name": "zolpidem"}],
    )
    assert SLEEP_SAFETY_CLAIMS["sedative_alcohol"] in _claim_ids_for_twin(db, risky)

    no_alcohol = _twin(medications=[{"name": "唑吡坦", "generic_name": "zolpidem"}])
    assert SLEEP_SAFETY_CLAIMS["sedative_alcohol"] not in _claim_ids_for_twin(db, no_alcohol)


def test_sedative_hypoxia_lookup_requires_sedative_and_low_spo2(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:sleep_sedative_hypoxia_lookup")

    risky = _twin(
        medications=[{"name": "佐匹克隆", "generic_name": "zopiclone"}],
        spo2_min=86,
        spo2_odi=6,
    )
    assert SLEEP_SAFETY_CLAIMS["sedative_hypoxia"] in _claim_ids_for_twin(db, risky)

    normal_spo2 = _twin(
        medications=[{"name": "佐匹克隆", "generic_name": "zopiclone"}],
        spo2_min=94,
        spo2_odi=1,
    )
    assert SLEEP_SAFETY_CLAIMS["sedative_hypoxia"] not in _claim_ids_for_twin(db, normal_spo2)


def test_drowsy_driving_lookup_requires_sleep_debt_and_driving_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:sleep_drowsy_driving_lookup")

    risky = _twin(conditions=["长途驾驶", "白天嗜睡"], sleep_hours=4.3)
    assert SLEEP_SAFETY_CLAIMS["drowsy_driving"] in _claim_ids_for_twin(db, risky)

    sleep_debt_only = _twin(conditions=["白天嗜睡"], sleep_hours=4.3)
    assert SLEEP_SAFETY_CLAIMS["drowsy_driving"] not in _claim_ids_for_twin(
        db,
        sleep_debt_only,
    )


def test_system_kb_eval_runner_covers_sleep_safety_cases(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:sleep_safety_eval")

    report = run_system_kb_eval_cases(db, case_ids=set(SLEEP_SAFETY_EVALS.values()))

    assert report["total"] == 4
    assert report["failed"] == 0, report
    assert {case["case_id"] for case in report["cases"]} == set(SLEEP_SAFETY_EVALS.values())


def test_sleep_safety_claims_keep_actions_in_clinician_boundary():
    for doc_id in SLEEP_SAFETY_CLAIMS.values():
        claim = _claim(doc_id)
        blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
        meta = claim.get("metadata") or {}
        assert meta.get("claim_boundary"), doc_id
        assert any(token in blob for token in ("医生", "药师", "睡眠中心", "不替代", "边界")), doc_id
        for banned in [
            "自行服用",
            "自行加量",
            "自行停药",
            "自行换药",
            "自行调整",
            "直接停用",
            "推荐剂量",
            "每日服用",
            "每天服用",
            "治疗疾病",
            "确诊",
            "自行使用CPAP",
            "靠酒助眠",
        ]:
            assert banned not in blob, f"{doc_id} 越界: {banned}"
