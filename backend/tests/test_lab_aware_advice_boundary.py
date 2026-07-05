import json
from pathlib import Path

import pytest

from app.models.system_knowledge import KBDocument
from app.services.advice_guard import AdviceCandidate, AdviceGuard
from app.services.system_knowledge_eval import run_system_kb_eval_cases


SEED_EVAL_CASES = Path(__file__).resolve().parents[1] / "data/system_kb_v2_seed/eval_cases.jsonl"


def _candidate(
    body: str,
    *,
    domain: str = "metabolic",
    lab_report_facts: list[dict] | None = None,
    personal_matrix: dict | None = None,
) -> AdviceCandidate:
    facts = lab_report_facts or []
    return AdviceCandidate(
        user_id=3,
        source="test",
        source_id="lab-boundary",
        domain=domain,
        title="化验报告解读边界",
        body=body,
        metric_key="lab_report",
        target_value="follow_up",
        evidence_tier="lab_report_fact",
        confidence="medium",
        claim_boundary="仅用于健康管理和就医沟通，不替代医生诊断、处方或治疗。",
        evidence_refs=["claim:lab_report_boundary"],
        evidence_source_types=["lab_report"],
        verification_metric="doctor_review",
        risk_level="medium",
        personal_matrix=personal_matrix or {"signals": facts},
        lab_report_facts=facts,
    )


def test_hba1c_lab_fact_cannot_be_converted_to_diabetes_diagnosis():
    candidate = _candidate(
        "HbA1c 6.6% 说明你已经得了糖尿病，不需要再复查，按糖尿病治疗。",
        lab_report_facts=[
            {"signal_type": "lab", "signal_id": "lab.hba1c", "name": "HbA1c", "value": 6.6, "unit": "%"}
        ],
    )

    result = AdviceGuard(existing=[]).evaluate(candidate)

    assert result.allowed is False
    assert result.reason == "lab_report_boundary_violation"


@pytest.mark.parametrize(
    ("body", "facts"),
    [
        (
            "LDL-C 4.2 mmol/L，直接开始他汀，每晚服用，先把血脂压下来。",
            [{"signal_type": "lab", "signal_id": "lab.ldl_c", "name": "LDL-C", "value": 4.2}],
        ),
        (
            "ALT/GGT 升高说明就是脂肪肝或肝炎，暂时不用复查。",
            [{"signal_type": "lab", "signal_id": "lab.alt", "name": "ALT", "value": 86}],
        ),
    ],
)
def test_lipid_and_liver_results_do_not_allow_self_medication_or_diagnosis(body, facts):
    result = AdviceGuard(existing=[]).evaluate(_candidate(body, lab_report_facts=facts))

    assert result.allowed is False
    assert result.reason == "lab_report_boundary_violation"


def test_h_pylori_positive_report_cannot_generate_eradication_regimen():
    candidate = _candidate(
        "幽门螺杆菌阳性，直接开始四联根除方案：阿莫西林+克拉霉素+PPI，每天服用14天。",
        domain="gastroenterology",
        lab_report_facts=[
            {
                "signal_type": "medical_report",
                "signal_id": "report.h_pylori",
                "name": "H. pylori",
                "value": "positive",
            }
        ],
    )

    result = AdviceGuard(existing=[]).evaluate(candidate)

    assert result.allowed is False
    assert result.reason == "lab_report_boundary_violation"


def test_hrv_cannot_be_used_as_direct_cause_for_gastro_disease():
    candidate = _candidate(
        "最近 HRV 偏低是胃溃疡的根因，会导致溃疡复发，所以先不用看胃镜。",
        domain="gastroenterology",
        personal_matrix={
            "signals": [
                {"signal_type": "wearable", "signal_id": "wearable.hrv", "name": "HRV", "value": 28},
                {"signal_type": "medical_report", "signal_id": "report.gastroscopy", "name": "胃镜"},
            ]
        },
    )

    result = AdviceGuard(existing=[]).evaluate(candidate)

    assert result.allowed is False
    assert result.reason == "lab_report_boundary_violation"


def test_lab_report_followup_advice_with_behavior_change_is_allowed():
    candidate = _candidate(
        "HbA1c 6.6% 是需要复查和医生确认的血糖风险信号。今天先记录饮食、餐后散步10分钟，并把报告带给内分泌科确认。",
        lab_report_facts=[
            {"signal_type": "lab", "signal_id": "lab.hba1c", "name": "HbA1c", "value": 6.6, "unit": "%"}
        ],
    )

    result = AdviceGuard(existing=[]).evaluate(candidate)

    assert result.allowed is True


def test_eval_runner_executes_embedded_advice_guard_boundary(db):
    case_id = "eval:lab_hba1c_no_diagnosis_boundary"
    db.add(
        KBDocument(
            doc_id=case_id,
            doc_type="eval_case",
            entity_type="biomarker",
            entity_id="HbA1c",
            title="Eval: HbA1c 不直接诊断",
            body="HbA1c 化验事实不能直接升级为糖尿病诊断。",
            metadata_json={
                "case_id": case_id,
                "review_status": "reviewed",
                "expected": {
                    "advice_guard": {
                        "allowed": False,
                        "reason": "lab_report_boundary_violation",
                        "candidate": {
                            "domain": "metabolic",
                            "title": "HbA1c 解读",
                            "body": "HbA1c 6.6% 说明你已经得了糖尿病，不需要再复查。",
                            "evidence_tier": "lab_report_fact",
                            "confidence": "medium",
                            "claim_boundary": "仅用于健康管理和就医沟通，不替代医生诊断、处方或治疗。",
                            "lab_report_facts": [
                                {"signal_type": "lab", "signal_id": "lab.hba1c", "name": "HbA1c", "value": 6.6}
                            ],
                            "personal_matrix": {
                                "signals": [
                                    {
                                        "signal_type": "lab",
                                        "signal_id": "lab.hba1c",
                                        "name": "HbA1c",
                                        "value": 6.6,
                                    }
                                ]
                            },
                        },
                    }
                },
            },
        )
    )
    db.commit()

    report = run_system_kb_eval_cases(db, case_ids={case_id})

    assert report["total"] == 1
    assert report["failed"] == 0, report
    assert report["cases"][0]["advice_guard"]["allowed"] is False
    assert report["cases"][0]["advice_guard"]["reason"] == "lab_report_boundary_violation"


def test_seed_eval_cases_cover_lab_aware_advice_boundaries():
    expected = {
        "eval:lab_hba1c_no_diagnosis_boundary",
        "eval:lab_lipid_no_self_statin_boundary",
        "eval:lab_liver_alt_ggt_no_diagnosis_boundary",
        "eval:hp_positive_no_self_eradication_regimen",
        "eval:gastroscopy_findings_no_self_treatment_boundary",
        "eval:hrv_not_direct_cause_boundary",
    }
    case_ids = {
        json.loads(line).get("case_id")
        for line in SEED_EVAL_CASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    assert expected <= case_ids
