from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import settings
import app.services.clinical_claim_release as release_policy
from app.services.health_evidence import (
    LOW_BACK_MANDATORY_DISCRIMINATOR_IDS,
    RiskLevel,
    SafetyProfileContext,
    build_health_evidence_turn,
    classify_health_intent,
    compile_health_evidence_turn,
)
from app.services.health_evidence.delivery import sanitize_health_delivery
from app.twin.schema import AcuteHealthState, HealthTwin, TwinMeta


@pytest.fixture(autouse=True)
def _enable_health_evidence_runtime(monkeypatch):
    monkeypatch.setattr(
        settings,
        "health_evidence_runtime_enabled",
        True,
    )


def test_low_back_advice_compiles_a_typed_symptom_intent():
    intent = classify_health_intent("我腰疼怎么办")

    assert intent.intent_id == "health_advice.symptom.low_back_pain"
    assert intent.intent == "health_advice"
    assert intent.domain == "low_back_pain"
    assert intent.risk_level == RiskLevel.MEDIUM
    assert intent.requires_personal_context is True
    assert intent.requires_authority is True


def test_low_back_intent_has_stable_mandatory_discriminator_ids():
    intent = classify_health_intent("下背痛该怎么处理")

    assert intent.mandatory_discriminator_ids == LOW_BACK_MANDATORY_DISCRIMINATOR_IDS
    assert intent.mandatory_discriminator_ids == (
        "low_back.cauda_equina",
        "low_back.progressive_neurologic_deficit",
        "low_back.major_trauma",
        "low_back.systemic_red_flag",
    )


def test_unscreened_low_back_defaults_to_medium_but_explicit_cauda_equina_is_emergency():
    unscreened = classify_health_intent("腰痛")
    emergency = classify_health_intent("腰痛而且大小便失禁、会阴麻木")
    explicit_negative = classify_health_intent(
        "腰痛，但没有大小便失禁，也没有会阴麻木"
    )

    assert unscreened.risk_level == RiskLevel.MEDIUM
    assert emergency.risk_level == RiskLevel.EMERGENCY
    assert explicit_negative.risk_level == RiskLevel.MEDIUM


@pytest.mark.parametrize(
    "query",
    [
        (
            "腰痛，没有排尿困难，也没有尿失禁，"
            "没有会阴或鞍区麻木"
        ),
        "腰痛，没有肛周麻木，也没有双腿越来越无力",
        "lower back pain without urinary retention or saddle numbness",
        "lower back pain, I do not have urinary retention or saddle numbness",
        "lower back pain, I don't have urinary retention",
        "lower back pain, she doesn't have saddle numbness",
        "lower back pain without any new saddle numbness",
        "lower back pain, denies having saddle numbness",
        "腰痛未伴会阴麻木或排尿困难",
        "腰痛否认有会阴麻木",
        "腰痛，不是排尿困难，只是尿频",
    ],
)
def test_explicitly_negated_emergency_terms_do_not_promote_risk(query):
    intent = classify_health_intent(query)

    assert intent.risk_level == RiskLevel.MEDIUM


@pytest.mark.parametrize(
    "query",
    [
        "腰痛，没有排尿困难，但是有会阴麻木",
        "lower back pain, I don't have urinary retention, "
        "but now I have saddle numbness",
        "腰痛，否认会阴麻木，但现在排不出尿",
    ],
)
def test_affirmation_after_a_negated_clause_still_promotes_emergency(query):
    intent = classify_health_intent(query)

    assert intent.risk_level == RiskLevel.EMERGENCY


@pytest.mark.parametrize(
    "query",
    [
        (
            "腰痛，只有右侧坐骨神经痛但症状稳定，没有无力，"
            "也没有大小便或会阴变化"
        ),
        "腰痛，我的排尿困难已稳定多年，今天没有新变化",
        (
            "lower back pain, difficulty peeing has been stable for years "
            "and is unchanged"
        ),
        (
            "腰痛很严重，但不是突然出现，也没有快速加重，"
            "没有双腿、会阴或大小便变化"
        ),
    ],
)
def test_isolated_or_stable_findings_do_not_trigger_emergency_triage(query):
    intent = classify_health_intent(query)

    assert intent.risk_level == RiskLevel.MEDIUM


@pytest.mark.parametrize(
    "query",
    [
        "腰痛，排尿困难已稳定多年，但今天突然完全排不出尿",
        "腰痛，我长期有排尿困难，但今天明显加重了",
        "腰痛，排尿困难，今天尿不出来，既往稳定多年",
        "腰痛，排尿困难、现在尿不出来，此前一直稳定",
        "腰痛，排尿困难，今天尿潴留，之前一直稳定",
        "腰痛，排尿困难，今天尿失禁，之前稳定",
        "腰痛，排尿困难，今天会阴麻木，之前稳定",
        (
            "lower back pain, difficulty peeing has been stable for years, "
            "but today I cannot empty my bladder"
        ),
        (
            "lower back pain, longstanding difficulty peeing, "
            "but much worse today"
        ),
        (
            "lower back pain, difficulty peeing, cannot urinate, "
            "stable before"
        ),
        (
            "lower back pain, difficulty peeing, saddle numbness, "
            "stable before"
        ),
    ],
)
def test_stable_urinary_history_never_masks_a_new_emergency_change(query):
    intent = classify_health_intent(query)

    assert intent.risk_level == RiskLevel.EMERGENCY


@pytest.mark.parametrize(
    "query",
    [
        "腰部疼痛且排不出尿、会阴麻木",
        "腰背疼而且大小便失禁",
        "我的背痛伴随尿潴留",
        "lower back ache with urinary retention",
        "腰痛，毫无预兆地排不出尿",
        "腰痛，无外伤但排不出尿",
        "腰痛，之前没有症状现在排不出尿",
        "lower back pain for no apparent reason with urinary retention",
        "腰痛并且双腿越来越没劲",
        "腰痛后双腿越来越软，走不稳",
        "腰痛，肛周麻木",
        "腰痛，两条腿越来越没劲",
        "腰痛，下肢进行性无力",
        "腰痛，憋得慌但尿不出",
        "腰痛，小便解不出来",
        "腰痛，生殖器麻木",
        "腰痛，小便完全解不出来",
        "腰痛，大小便控制不住",
        "腰痛，双腿越来越无力",
        "腰痛，两条腿越来越没力气",
        "腰痛，肛门周围麻木",
        "lower back pain and I cannot pee",
        "lower back pain, cannot pass urine",
        "腰痛，双腿渐渐没力气",
        "lumbar pain and urinary retention",
        "腰椎痛且排不出尿",
        "腰椎疼伴会阴麻木",
        "腰骶部疼痛且小便解不出来",
        "脊柱痛而且尿潴留",
        "low-back pain with urinary retention",
        "lower-back pain with saddle numbness",
        "lower back pain and can't urinate",
        "lower back pain with difficulty peeing",
        "lower back pain with weakness or tingling in both legs",
        "lower back pain with numbness around the genitals or buttocks",
        "腰痛，突然无法控制尿液",
        "腰痛，最近开始漏尿",
        "腰痛，尿意和便意消失",
        "lower back pain and I cannot empty my bladder",
        "lower back pain with numbness in my saddle area",
        "lower back pain with difficulty starting urination",
    ],
)
def test_low_back_emergency_synonyms_never_fall_through_to_general(query):
    intent = classify_health_intent(query)

    assert intent.intent_id == "health_advice.symptom.low_back_pain"
    assert intent.risk_level == RiskLevel.EMERGENCY


@pytest.mark.parametrize(
    "query",
    [
        "腰痛，刚发生严重车祸",
        "腰痛同时高热39.5度",
        "腰痛，从高处摔下来",
        "腰痛伴不明原因体重下降",
        "腰痛，我有癌症史",
        "腰痛且最近严重感染",
        "腰痛，伴有发热",
        "腰痛，昨天从楼梯摔下来",
        "腰痛，以前得过癌症",
        "腰痛，最近莫名瘦了十斤",
    ],
)
def test_low_back_systemic_or_trauma_red_flags_are_high_risk(query):
    intent = classify_health_intent(query)

    assert intent.intent_id == "health_advice.symptom.low_back_pain"
    assert intent.risk_level == RiskLevel.HIGH


def test_progressive_unilateral_leg_weakness_is_high_risk():
    intent = classify_health_intent("腰痛，右腿越来越无力")

    assert intent.intent_id == "health_advice.symptom.low_back_pain"
    assert intent.risk_level == RiskLevel.HIGH


def test_progressive_unilateral_weakness_is_publicly_detected_without_emergency_upgrade():
    turn = _compile_turn(
        "腰痛，右腿越来越无力",
        safety_profile=SafetyProfileContext(population="adults_16_plus"),
    )

    manifest = turn.public_manifest()

    assert turn.intent.risk_level == RiskLevel.HIGH
    assert any(
        item["id"] == "low_back.unilateral_progressive_neurologic_deficit"
        and item["priority"] == "urgent"
        for item in manifest["detected_red_flags"]
    )
    assert all(
        item["id"] != "low_back.progressive_neurologic_deficit"
        for item in manifest["missing_discriminators"]
    )


@pytest.mark.parametrize(
    ("query", "expected_id"),
    [
        ("腰痛，伴有发热", "low_back.systemic_red_flag"),
        ("腰痛，昨天从楼梯摔下来", "low_back.major_trauma"),
        ("腰痛，以前得过癌症", "low_back.systemic_red_flag"),
        ("腰痛，最近莫名瘦了十斤", "low_back.systemic_red_flag"),
    ],
)
def test_already_stated_high_risk_facts_are_detected_and_not_asked_again(
    query,
    expected_id,
):
    turn = _compile_turn(
        query,
        safety_profile=SafetyProfileContext(population="adults_16_plus"),
    )

    manifest = turn.public_manifest()

    assert any(
        item["id"] == expected_id
        for item in manifest["detected_red_flags"]
    )
    assert all(
        item["id"] != expected_id
        for item in manifest["missing_discriminators"]
    )


def test_non_health_intent_defaults_low_without_health_requirements():
    intent = classify_health_intent("你好")

    assert intent.intent_id == "general.chat"
    assert intent.risk_level == RiskLevel.LOW
    assert intent.mandatory_discriminator_ids == ()
    assert intent.requires_personal_context is False
    assert intent.requires_authority is False


def test_intent_contract_is_immutable():
    intent = classify_health_intent("我腰疼怎么办")

    with pytest.raises(ValidationError):
        intent.risk_level = RiskLevel.LOW


def test_public_intent_projection_is_stable_and_does_not_expose_raw_query():
    intent = classify_health_intent("我腰疼怎么办")

    first = intent.to_public().model_dump(mode="json")
    second = intent.to_public().model_dump(mode="json")

    assert first == second
    assert "query" not in first
    assert "腰疼" not in str(first)


def test_mobile_and_mac_have_identical_clinical_intent_semantics():
    mobile = classify_health_intent("我腰疼怎么办", client="mobile")
    mac = classify_health_intent("我腰疼怎么办", client="mac")

    assert mobile == mac
    assert mobile.to_public() == mac.to_public()


NOW = datetime(2026, 7, 29, tzinfo=UTC)
_CLAIMS_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "system_kb_v2_seed"
    / "claims.jsonl"
)


def _authority_result(
    expected_id: str = "claim:c_low_back_serious_cause_screening_boundary",
) -> dict:
    for line in _CLAIMS_PATH.read_text(encoding="utf-8").splitlines():
        document = json.loads(line)
        if document.get("doc_id") == expected_id:
            return {"score": 0.9, "document": document}
    raise AssertionError(f"published claim missing: {expected_id}")


def _empty_twin() -> HealthTwin:
    return HealthTwin(meta=TwinMeta(user_id=7, generated_at=NOW))


def _compile_turn(
    query: str,
    *,
    results=None,
    client="mobile",
    safety_profile=None,
):
    return compile_health_evidence_turn(
        twin=_empty_twin(),
        intent=classify_health_intent(query, client=client),
        authority_results=[_authority_result()] if results is None else results,
        safety_profile=(
            safety_profile
            if safety_profile is not None
            else SafetyProfileContext(population="adults_16_plus")
        ),
        now=NOW,
    )


def test_runtime_parity_is_client_neutral_and_public_projection_is_private_safe():
    mobile = _compile_turn("我腰疼怎么办", client="mobile")
    mac = _compile_turn("我腰疼怎么办", client="mac")

    assert mobile == mac
    assert mobile.public_manifest() == mac.public_manifest()
    manifest = mobile.public_manifest()
    serialized = str(manifest)
    assert manifest["risk_level"] == "medium"
    assert manifest["sufficiency"] == "clarify"
    assert manifest["authority_sources"][0]["organization"] == "NICE"
    assert "query" not in manifest
    assert "腰疼" not in serialized
    assert "private_packet" not in serialized


def test_runtime_injects_exactly_one_bounded_personal_and_authority_envelope():
    turn = _compile_turn("我腰疼怎么办")

    prompt = turn.private_prompt()

    assert prompt.count("## 本轮个人健康证据") == 1
    assert prompt.count("## 权威医学证据") == 1
    assert prompt.count("## 健康证据运行时") == 1
    assert "sufficiency=clarify" in prompt


def test_unknown_discriminators_clarify_but_explicit_emergency_uses_safe_fallback():
    clarify = _compile_turn("我腰疼怎么办")
    emergency = _compile_turn("腰痛、排不出尿而且会阴麻木")

    assert clarify.sufficiency == "clarify"
    assert {
        item["id"] for item in clarify.missing_discriminators
    } == set(LOW_BACK_MANDATORY_DISCRIMINATOR_IDS)
    assert emergency.sufficiency == "safe_fallback"
    assert emergency.intent.risk_level == RiskLevel.EMERGENCY
    assert emergency.public_manifest()["urgent_red_flags"] == []
    assert emergency.public_manifest()["detected_red_flags"]
    assert emergency.public_manifest()["safety_precautions"]


def test_partial_systemic_negatives_do_not_close_the_whole_discriminator():
    turn = _compile_turn(
        "腰痛，没有排尿困难，没有会阴麻木，没有双腿无力，"
        "没有严重外伤，没有发热"
    )

    assert "low_back.systemic_red_flag" in {
        item["id"] for item in turn.missing_discriminators
    }


def test_no_admitted_authority_evidence_fails_closed():
    turn = _compile_turn("我腰疼怎么办", results=[])

    assert turn.sufficiency == "safe_fallback"
    assert turn.authority_bundle.accepted == ()
    assert turn.public_manifest()["evidence_refs"]
    assert turn.public_manifest()["authority_sources"] == []


def test_public_trace_reports_only_selected_evidence_not_available_tables():
    turn = _compile_turn("我腰疼怎么办")
    manifest = turn.public_manifest()

    assert manifest["authority_evidence_refs"] == [
        "claim:c_low_back_serious_cause_screening_boundary"
    ]
    assert all(
        ref.startswith(("personal:", "claim:"))
        for ref in manifest["evidence_refs"]
    )
    assert "garmin_table" not in str(manifest)


def test_runtime_builds_one_frozen_twin_and_uses_a_deidentified_authority_query(
    monkeypatch,
):
    from app.services import system_knowledge_service
    from app.twin import builder as twin_builder

    calls = {"twin": 0, "queries": []}

    def fake_build_twin(db, user_id, use_cache):
        calls["twin"] += 1
        assert user_id == 7
        assert use_cache is True
        return _empty_twin()

    def fake_search_knowledge(db, query, **kwargs):
        calls["queries"].append(query)
        return {
            "results": [
                _authority_result(
                    "claim:c_low_back_imaging_not_routine_boundary"
                )
            ]
        }

    class _Query:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            class _Profile:
                age = 35
                allergies = []

            return _Profile()

    class _DB:
        def query(self, *_args, **_kwargs):
            return _Query()

    monkeypatch.setattr(twin_builder, "build_twin", fake_build_twin)
    monkeypatch.setattr(
        system_knowledge_service,
        "search_health_evidence_runtime_claims",
        fake_search_knowledge,
    )
    raw_query = "我的报告记录ID-991：腰痛，是否需要做 MRI？"
    turn = build_health_evidence_turn(
        _DB(),
        user_id=7,
        query=raw_query,
        intent=classify_health_intent(raw_query),
        now=NOW,
    )

    assert calls["twin"] == 1
    assert len(calls["queries"]) == 1
    assert "ID-991" not in calls["queries"][0]
    assert "MRI" not in calls["queries"][0]
    assert "影像检查" in calls["queries"][0]
    assert turn.authority_bundle.accepted


def test_recent_twin_emergency_promotes_effective_intent_and_safe_fallback():
    twin = HealthTwin(
        meta=TwinMeta(user_id=7, generated_at=NOW),
        acute=AcuteHealthState(
            symptom_texts_all=[
                "昨天腰痛加重",
                "今天排尿困难并且会阴发麻",
            ],
        ),
    )

    turn = compile_health_evidence_turn(
        twin=twin,
        intent=classify_health_intent("我腰疼怎么办"),
        authority_results=[_authority_result()],
        safety_profile=SafetyProfileContext(),
        now=NOW,
    )

    assert turn.intent.risk_level == RiskLevel.EMERGENCY
    assert turn.personal_packet.intent.risk_level == RiskLevel.EMERGENCY
    assert turn.sufficiency == "safe_fallback"
    manifest = turn.public_manifest()
    assert manifest["risk_level"] == "emergency"
    assert manifest["intent"]["risk_level"] == "emergency"
    assert any(
        ref.startswith("guardian:symptoms.cauda_equina_warning")
        for ref in manifest["personal_evidence_refs"]
    )
    assert any(
        "严重神经压迫" in item["label"]
        for item in manifest["detected_red_flags"]
    )


@pytest.mark.parametrize(
    ("query", "historical_symptom"),
    [
        ("what should I do about my lower back pain?", "saddle numbness"),
        ("what should I do about lumbar pain?", "urinary retention"),
    ],
)
def test_english_low_back_query_combines_with_recent_twin_red_flag(
    query,
    historical_symptom,
):
    twin = HealthTwin(
        meta=TwinMeta(user_id=7, generated_at=NOW),
        acute=AcuteHealthState(
            symptom_texts_all=[historical_symptom],
        ),
    )

    turn = compile_health_evidence_turn(
        twin=twin,
        intent=classify_health_intent(query),
        authority_results=[_authority_result()],
        safety_profile=SafetyProfileContext(population="adults_16_plus"),
        now=NOW,
    )

    assert turn.intent.risk_level == RiskLevel.EMERGENCY
    assert any(
        signal.signal_id.startswith(
            "guardian:symptoms.cauda_equina_warning"
        )
        for signal in turn.personal_packet.safety_signals
    )


@pytest.mark.parametrize(
    "historical_symptom",
    [
        "胸痛、冷汗并放射到左臂",
        "突然口角歪、说话不清",
        "喘不上气而且无法平卧",
        "剧烈腹痛并呕血",
    ],
)
def test_non_neurologic_guardian_emergency_uses_generic_accurate_copy(
    historical_symptom,
):
    twin = HealthTwin(
        meta=TwinMeta(user_id=7, generated_at=NOW),
        acute=AcuteHealthState(
            symptom_texts_all=["腰痛", historical_symptom],
        ),
    )
    turn = compile_health_evidence_turn(
        twin=twin,
        intent=classify_health_intent("我腰疼怎么办"),
        authority_results=[_authority_result()],
        safety_profile=SafetyProfileContext(population="adults_16_plus"),
        now=NOW,
    )

    verification = turn.verify("任意未发布模型文本")

    assert turn.intent.risk_level == RiskLevel.EMERGENCY
    assert "急症警示征象" in verification.text
    assert "严重神经警示征象" not in verification.text


def test_safety_profile_high_risk_promotes_turn_and_reaches_verifier(
    monkeypatch,
):
    from app.services.health_evidence import runtime
    from app.services.health_evidence.verifier import HealthAnswerVerification

    captured = {}

    def fake_verify(text, **kwargs):
        captured.update(kwargs)
        return HealthAnswerVerification(
            verdict="pass",
            text=text,
            reasons=(),
        )

    monkeypatch.setattr(runtime, "verify_health_answer", fake_verify)
    profile = SafetyProfileContext(
        risk_signals=(
            {
                "signal_id": "safety-profile:clinician-red-flag",
                "risk_level": RiskLevel.HIGH,
                "category": "safety_profile",
                "detail": "既往医生约定的就医红线已触发",
                "source_kind": "safety_profile",
            },
        ),
    )

    turn = compile_health_evidence_turn(
        twin=_empty_twin(),
        intent=classify_health_intent("我腰疼怎么办"),
        authority_results=[_authority_result()],
        safety_profile=profile,
        now=NOW,
    )
    result = turn.verify("候选回答")

    assert turn.intent.risk_level == RiskLevel.HIGH
    assert turn.personal_packet.intent.risk_level == RiskLevel.HIGH
    assert turn.sufficiency == "safe_fallback"
    assert turn.public_manifest()["risk_level"] == "high"
    assert captured["risk_level"] == "high"
    assert result.verdict == "pass"


def test_guardian_evaluation_failure_never_degrades_to_clarify(
    monkeypatch,
):
    from app.agents.safety_guardian import engine

    monkeypatch.setattr(
        engine,
        "evaluate_rules_with_status",
        lambda _twin: ([], 2),
    )

    turn = _compile_turn("我腰疼怎么办")

    assert turn.intent.risk_level == RiskLevel.HIGH
    assert turn.sufficiency == "safe_fallback"
    assert (
        "guardian:safety.evaluation_incomplete"
        in turn.public_manifest()["personal_evidence_refs"]
    )


def test_recent_twin_high_guardian_alert_promotes_turn_to_safe_fallback():
    twin = HealthTwin(
        meta=TwinMeta(user_id=7, generated_at=NOW),
        acute=AcuteHealthState(
            symptom_texts_all=[
                "最近腰痛",
                "同时不明原因暴瘦并反复发烧",
            ],
        ),
    )

    turn = compile_health_evidence_turn(
        twin=twin,
        intent=classify_health_intent("我腰疼怎么办"),
        authority_results=[_authority_result()],
        safety_profile=SafetyProfileContext(),
        now=NOW,
    )

    assert turn.intent.risk_level == RiskLevel.HIGH
    assert turn.sufficiency == "safe_fallback"
    assert (
        "guardian:symptoms.red_flag_persistent_warning"
        in turn.public_manifest()["personal_evidence_refs"]
    )


def test_twin_build_failure_marks_safety_core_failed_and_uses_safe_fallback(
    monkeypatch,
):
    from app.services import system_knowledge_service
    from app.twin import builder as twin_builder

    def fail_build_twin(*_args, **_kwargs):
        raise RuntimeError("twin unavailable")

    def fake_search_knowledge(*_args, **_kwargs):
        return {"results": [_authority_result()]}

    class _Query:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return None

    class _DB:
        def query(self, *_args, **_kwargs):
            return _Query()

    monkeypatch.setattr(twin_builder, "build_twin", fail_build_twin)
    monkeypatch.setattr(
        system_knowledge_service,
        "search_health_evidence_runtime_claims",
        fake_search_knowledge,
    )

    turn = build_health_evidence_turn(
        _DB(),
        user_id=7,
        query="我腰疼怎么办",
        intent=classify_health_intent("我腰疼怎么办"),
        now=NOW,
    )

    gap_states = {
        gap.category: gap.state.value
        for gap in turn.personal_packet.gaps
    }
    assert gap_states == {
        "active_problem": "failed",
        "allergy": "failed",
        "chronic_condition": "failed",
        "medication": "failed",
        "symptom": "failed",
    }
    assert turn.intent.risk_level == RiskLevel.HIGH
    assert turn.sufficiency == "safe_fallback"
    assert (
        "twin:safety_context_incomplete"
        in turn.public_manifest()["personal_evidence_refs"]
    )


def test_safety_profile_load_failure_is_failed_not_absent_and_fails_closed(
    monkeypatch,
):
    from app.services import system_knowledge_service
    from app.twin import builder as twin_builder

    monkeypatch.setattr(
        twin_builder,
        "build_twin",
        lambda *_args, **_kwargs: _empty_twin(),
    )
    monkeypatch.setattr(
        system_knowledge_service,
        "search_health_evidence_runtime_claims",
        lambda *_args, **_kwargs: {"results": [_authority_result()]},
    )

    class _DB:
        def query(self, *_args, **_kwargs):
            raise RuntimeError("profile unavailable")

    turn = build_health_evidence_turn(
        _DB(),
        user_id=7,
        query="我腰疼怎么办",
        intent=classify_health_intent("我腰疼怎么办"),
        now=NOW,
    )

    allergy_gap = next(
        gap
        for gap in turn.personal_packet.gaps
        if gap.category == "allergy"
    )
    assert allergy_gap.state.value == "failed"
    assert allergy_gap.failed_partition == "safety_profile"
    assert turn.intent.risk_level == RiskLevel.HIGH
    assert turn.sufficiency == "safe_fallback"


def test_unknown_population_never_routes_authority_as_adult():
    turn = _compile_turn(
        "我腰疼怎么办",
        safety_profile=SafetyProfileContext(),
    )

    assert turn.authority_bundle.accepted == ()
    assert turn.authority_bundle.rejections[0].reason == (
        "missing_population_context"
    )
    assert turn.sufficiency == "clarify"
    assert "low_back.population_adult_16_plus" in {
        item["id"] for item in turn.missing_discriminators
    }


def test_explicit_turn_age_can_unlock_adult_authority_without_profile_age():
    turn = _compile_turn(
        "我35岁，腰痛，没有排尿困难，也没有会阴麻木；"
        "没有双腿麻木或无力；没有严重外伤；"
        "没有发热或严重感染，没有体重下降，没有癌症史",
        safety_profile=SafetyProfileContext(),
        results=[
            _authority_result(
                "claim:c_low_back_self_management_activity_boundary"
            )
        ],
    )

    assert turn.authority_bundle.accepted
    assert turn.missing_discriminators == ()
    assert turn.sufficiency == "sufficient"


def _verified_persisted_health_answer() -> tuple[str, dict]:
    turn = _compile_turn(
        "我35岁，腰痛，没有排尿困难，也没有会阴麻木；"
        "没有双腿麻木或无力；没有严重外伤；"
        "没有发热或严重感染，没有体重下降，没有癌症史",
        safety_profile=SafetyProfileContext(),
        results=[
            _authority_result(
                "claim:c_low_back_self_management_activity_boundary"
            )
        ],
    )
    verification = turn.verify("请给我有权威依据的安全建议")
    manifest = turn.public_manifest(verification=verification)
    meta = {
        "health_evidence_manifest": manifest,
        "health_evidence_verification": verification.public_dict(
            manifest=manifest,
        ),
        "cards": [turn.card_descriptor(verification=verification)],
    }
    return verification.text, meta


def _bind_manifest_digest(meta: dict) -> None:
    manifest = meta["health_evidence_manifest"]
    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    meta["health_evidence_verification"]["manifest_sha256"] = (
        hashlib.sha256(payload).hexdigest()
    )


def test_persisted_health_answer_is_sanitized_when_runtime_release_is_revoked(
    monkeypatch,
):
    content, meta = _verified_persisted_health_answer()
    assert meta["health_evidence_manifest"]["authority_artifacts"]
    initial = sanitize_health_delivery(
        source_query="腰痛怎么办",
        assistant_content=content,
        assistant_meta=meta,
        enabled=False,
    )
    assert initial.sanitized is False

    monkeypatch.setattr(
        release_policy,
        "HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS",
        frozenset(),
    )
    revoked = sanitize_health_delivery(
        source_query="腰痛怎么办",
        assistant_content=content,
        assistant_meta=meta,
        enabled=False,
    )

    assert revoked.sanitized is True
    assert content not in revoked.content
    assert revoked.meta["cards"] == []


def test_persisted_health_answer_is_sanitized_on_artifact_version_mismatch():
    content, meta = _verified_persisted_health_answer()
    tampered_meta = deepcopy(meta)
    tampered_meta["health_evidence_manifest"]["authority_artifacts"][0][
        "sha256"
    ] = "0" * 64
    _bind_manifest_digest(tampered_meta)

    delivery = sanitize_health_delivery(
        source_query="腰痛怎么办",
        assistant_content=content,
        assistant_meta=tampered_meta,
        enabled=False,
    )

    assert delivery.sanitized is True
    assert content not in delivery.content


def test_persisted_health_answer_is_sanitized_on_manifest_digest_mismatch():
    content, meta = _verified_persisted_health_answer()
    tampered_meta = deepcopy(meta)
    tampered_meta["health_evidence_manifest"]["limitations"].append(
        "forged delivery metadata"
    )

    delivery = sanitize_health_delivery(
        source_query="腰痛怎么办",
        assistant_content=content,
        assistant_meta=tampered_meta,
        enabled=False,
    )

    assert delivery.sanitized is True
    assert content not in delivery.content


def test_medium_health_envelope_cannot_be_replayed_for_emergency_query():
    content, meta = _verified_persisted_health_answer()

    delivery = sanitize_health_delivery(
        source_query="腰痛而且排不出尿",
        assistant_content=content,
        assistant_meta=meta,
        enabled=False,
    )

    assert delivery.sanitized is True
    assert content not in delivery.content
    assert "联系当地急救服务" in delivery.content


@pytest.mark.parametrize(
    "source_query",
    [
        "腰痛怎么办",
        "没有",
    ],
)
def test_valid_health_envelope_survives_medium_or_continuation_query(
    source_query,
):
    content, meta = _verified_persisted_health_answer()

    delivery = sanitize_health_delivery(
        source_query=source_query,
        assistant_content=content,
        assistant_meta=meta,
        enabled=False,
    )

    assert delivery.sanitized is False
    assert delivery.content == content


@pytest.mark.parametrize(
    "mutation",
    ["empty", "duplicate", "forged_extra"],
)
def test_sufficient_delivery_requires_exact_unique_nonempty_authority_refs(
    mutation,
):
    content, meta = _verified_persisted_health_answer()
    forged = deepcopy(meta)
    manifest = forged["health_evidence_manifest"]
    verification = forged["health_evidence_verification"]
    claim_id = manifest["authority_evidence_refs"][0]
    artifact = dict(manifest["authority_artifacts"][0])
    if mutation == "empty":
        manifest["authority_evidence_refs"] = []
        manifest["authority_artifacts"] = []
        manifest["evidence_refs"] = [
            ref
            for ref in manifest["evidence_refs"]
            if ref != claim_id
        ]
        verification["evidence_refs_used"] = []
    elif mutation == "duplicate":
        manifest["authority_evidence_refs"].append(claim_id)
        manifest["evidence_refs"].append(claim_id)
        verification["evidence_refs_used"].append(claim_id)
    else:
        extra = "claim:forged-extra-authority-ref"
        manifest["authority_evidence_refs"].append(extra)
        manifest["evidence_refs"].append(extra)
        manifest["authority_artifacts"].append(
            {**artifact, "doc_id": extra}
        )
    _bind_manifest_digest(forged)

    delivery = sanitize_health_delivery(
        source_query="腰痛怎么办",
        assistant_content=content,
        assistant_meta=forged,
        enabled=False,
    )

    assert delivery.sanitized is True
    assert content not in delivery.content


def test_valid_delivery_reconstructs_canonical_card_sources_and_risk():
    content, meta = _verified_persisted_health_answer()
    manifest = meta["health_evidence_manifest"]
    forged = deepcopy(meta)
    forged["cards"] = [
        {
            "type": "health_evidence",
            "data": {"risk_level": "low", "fake": True},
            "actions": [{"type": "unsafe"}],
        },
        {"type": "fake_health_card", "data": {"diagnosis": "forged"}},
    ]
    forged["sources_used"] = ["fake-paid-source"]
    forged["risk_level"] = "low"

    delivery = sanitize_health_delivery(
        source_query="腰痛怎么办",
        assistant_content=content,
        assistant_meta=forged,
        enabled=False,
    )

    assert delivery.sanitized is False
    assert delivery.content == content
    assert delivery.meta["cards"] == [
        {
            "type": "health_evidence",
            "data": manifest,
            "actions": [],
        }
    ]
    expected_sources = [
        source["organization"]
        for source in manifest["authority_sources"]
    ]
    if manifest["context_categories_used"]:
        expected_sources.append(
            "个人健康上下文："
            + "、".join(manifest["context_categories_used"])
        )
    assert delivery.meta["sources_used"] == expected_sources
    assert delivery.meta["risk_level"] == manifest["risk_level"]


def test_user_profile_age_under_16_never_routes_adult_authority(
    monkeypatch,
):
    from app.services import system_knowledge_service
    from app.twin import builder as twin_builder

    monkeypatch.setattr(
        twin_builder,
        "build_twin",
        lambda *_args, **_kwargs: _empty_twin(),
    )
    monkeypatch.setattr(
        system_knowledge_service,
        "search_health_evidence_runtime_claims",
        lambda *_args, **_kwargs: {"results": [_authority_result()]},
    )

    class _Profile:
        age = 15
        allergies = []

    class _Query:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return _Profile()

    class _DB:
        def query(self, *_args, **_kwargs):
            return _Query()

    turn = build_health_evidence_turn(
        _DB(),
        user_id=7,
        query="我腰疼怎么办",
        intent=classify_health_intent("我腰疼怎么办"),
        now=NOW,
    )

    assert turn.authority_bundle.accepted == ()
    assert turn.authority_bundle.rejections[0].reason == "wrong_population"
    assert turn.sufficiency == "safe_fallback"


@pytest.mark.parametrize(
    ("query", "expected_use_case"),
    [
        ("我腰疼怎么办", "initial_assessment"),
        (
            "腰痛，没有排尿困难，也没有尿失禁，没有会阴或鞍区麻木；"
            "没有双腿麻木或无力；没有外伤；没有发热或感染，"
            "没有体重下降，也没有癌症史",
            "self_management_after_red_flag_screen",
        ),
        (
            "腰痛持续超过3个月，医生已经排除特异性病因",
            "chronic_primary_care",
        ),
        (
            "腰痛，是否需要马上做 MRI 影像检查？",
            "imaging_decision",
        ),
        (
            "腰痛而且排不出尿、会阴麻木",
            "symptom_triage",
        ),
    ],
)
def test_authority_use_case_requires_confirmed_turn_facts(
    monkeypatch,
    query,
    expected_use_case,
):
    from app.services.health_evidence import runtime

    captured = {}
    real_router = runtime.route_authority_results

    def capture_router(results, **kwargs):
        captured.update(kwargs)
        return real_router(results, **kwargs)

    monkeypatch.setattr(runtime, "route_authority_results", capture_router)

    _compile_turn(query)

    assert captured["population"] == "adults_16_plus"
    assert captured["use_case"] == expected_use_case


def test_explicitly_negative_screen_closes_all_four_discriminators():
    turn = _compile_turn(
        "腰痛，没有排尿困难，也没有尿失禁，没有会阴或鞍区麻木；"
        "没有双腿麻木或无力；没有外伤；没有发热或感染，"
        "没有体重下降，也没有癌症史"
    )

    assert turn.missing_discriminators == ()
