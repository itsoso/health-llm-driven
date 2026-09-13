import pytest
from app.services.guidance_validator import enforce_medical_evidence_boundaries


@pytest.mark.parametrize(
    "text",
    [
        "要评估，我需要你直接告诉我：名称 + 剂量 + 每天什么时间吃。",
        "请告诉我补剂的名称、剂量，以及每天什么时间服用。",
    ],
)
def test_request_for_actual_regimen_is_not_a_new_prescription(text):
    assert not enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize(
    "text",
    [
        "请告诉我补剂名称，然后每天服用两片。",
        "请告诉我补剂名称。每天服用两片。",
        "补剂应该每天吃两片。",
        "需要告诉医生：把补剂增加到两片。",
    ],
)
def test_request_intro_cannot_launder_a_new_regimen(text):
    assert enforce_medical_evidence_boundaries(text).flagged
