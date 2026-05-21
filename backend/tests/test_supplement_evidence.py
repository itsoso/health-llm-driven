from app.services.supplement_evidence import (
    SupplementSafetyContext,
    enrich_supplement_recommendations,
    resolve_supplement_key,
)


def test_resolve_common_chinese_supplement_names():
    assert resolve_supplement_key("镁补充剂（睡眠支持）") == "magnesium"
    assert resolve_supplement_key("Omega-3 鱼油") == "omega_3"
    assert resolve_supplement_key("维生素D3") == "vitamin_d"
    assert resolve_supplement_key("肌酸一水合物") == "creatine"


def test_enrich_attaches_evidence_profile_and_refs():
    recommendations = [{"name": "肌酸", "dosage": "5g", "timing": "运动后"}]

    summary = enrich_supplement_recommendations(recommendations)

    rec = recommendations[0]
    assert summary["matched"] == 1
    assert rec["support_status"] == "supported"
    assert rec["evidence_profile"]["evidence_level"] == "A"
    assert "issn:creatine-position-stand" in rec["evidence_refs"]
    assert "训练容量" in rec["verification_metrics"]


def test_warfarin_blocks_vitamin_k2():
    recommendations = [{"name": "维生素 K2", "dosage": "180μg", "timing": "随餐"}]
    context = SupplementSafetyContext(medications=("华法林",))

    summary = enrich_supplement_recommendations(recommendations, context)

    rec = recommendations[0]
    assert summary["blocked"] == 1
    assert rec["support_status"] == "blocked"
    assert rec["safety_review"]["blocked"] is True
    assert "华法林" in rec["safety_review"]["blockers"][0]


def test_low_egfr_blocks_magnesium_self_supplementation():
    recommendations = [{"name": "甘氨酸镁", "dosage": "300mg", "timing": "睡前"}]
    context = SupplementSafetyContext(labs={"egfr": 25})

    summary = enrich_supplement_recommendations(recommendations, context)

    rec = recommendations[0]
    assert summary["blocked"] == 1
    assert rec["support_status"] == "blocked"
    assert "eGFR=25" in rec["safety_review"]["blockers"][0]


def test_dose_over_upper_limit_adds_warning():
    recommendations = [{"name": "维生素D3", "dosage": "5000 IU", "timing": "早餐后"}]

    summary = enrich_supplement_recommendations(recommendations)

    rec = recommendations[0]
    assert summary["blocked"] == 0
    assert rec["support_status"] == "supported"
    assert summary["warnings"]
    assert "超过" in summary["warnings"][0]["message"]
