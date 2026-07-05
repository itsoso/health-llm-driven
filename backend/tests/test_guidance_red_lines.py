"""R4 guidance guardrails: guidance_validator + the two SafetyGuardian rules.

The validator is the token-level defense-in-depth (strips/softens text); the
rules turn residual prescriptive/imperative tokens into auditable alerts. Both
must let OBSERVATIONAL wording through untouched.
"""
from datetime import datetime, timezone

import pytest

from app.agents.safety_guardian.rules.guidance_red_lines import (
    diet_prescription_red_line,
    movement_imperative_red_line,
)
from app.agents.safety_guardian.schema import Severity
from app.config import settings
from app.services.guidance_validator import sanitize_guidance
from app.twin.schema import HealthTwin, TwinMeta


@pytest.fixture
def med_timing_on(monkeypatch):
    """Enable the ships-disabled third family for the med-timing tests only."""
    monkeypatch.setattr(settings, "med_timing_softening", True)
    yield


def _twin_with_guidance(text: str) -> HealthTwin:
    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(timezone.utc)))
    twin.acute.pending_guidance_texts = [text]
    return twin


# ─────────────────────── validator: positive (strips) ───────────────────────


def test_validator_strips_quantified_diet_prescription():
    r = sanitize_guidance("建议每天吃 50 克坚果, 避免摄入 200g 碳水。")
    assert r.flagged is True
    assert "每天吃 50 克" not in r.text
    assert "避免摄入 200g" not in r.text
    assert any("diet" in v for v in r.violations)


def test_validator_strips_imperative_eat_command():
    r = sanitize_guidance("别吃米饭, 不要喝含糖饮料。")
    assert r.flagged is True
    assert "别吃" not in r.text
    assert "不要喝" not in r.text


def test_validator_softens_imperative_movement():
    r = sanitize_guidance("立刻放慢, 必须做满 3 组。")
    assert r.flagged is True
    assert "立刻放慢" not in r.text
    assert "必须做满 3 组" not in r.text
    assert "自行调整" in r.text  # softened, not a bare command


# ─────────────────────── validator: negative (keeps observational) ──────────


def test_validator_keeps_observational_text_untouched():
    text = "这餐约 450kcal, 蛋白约 32g, 今日蛋白还差 35g, 可考虑下一餐加豆腐。相关非因果。"
    r = sanitize_guidance(text)
    assert r.flagged is False
    assert r.text == text
    assert r.violations == []


def test_validator_empty_string_safe():
    r = sanitize_guidance("")
    assert r.flagged is False
    assert r.text == ""


# ─────────────────────── rule: diet_prescription_red_line ───────────────────


def test_diet_prescription_rule_fires_on_quantified_prescription():
    twin = _twin_with_guidance("每天吃 50 克坚果。")
    alert = diet_prescription_red_line(twin)
    assert alert is not None
    assert alert.severity == Severity.CRITICAL
    assert alert.category == "guidance"
    assert alert.rule_id == "guidance_red_lines.diet_prescription_red_line"


def test_diet_prescription_rule_fires_on_imperative_eat():
    twin = _twin_with_guidance("别吃米饭, 停止吃糖。")
    alert = diet_prescription_red_line(twin)
    assert alert is not None
    assert alert.severity == Severity.CRITICAL


def test_diet_prescription_rule_silent_on_observational_text():
    twin = _twin_with_guidance("这餐约 450kcal, 今日蛋白还差 35g, 可考虑加豆腐。")
    assert diet_prescription_red_line(twin) is None


def test_diet_prescription_rule_silent_when_no_guidance_text():
    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(timezone.utc)))
    assert diet_prescription_red_line(twin) is None


# ─────────────────────── rule: movement_imperative_red_line ─────────────────


def test_movement_rule_fires_on_imperative_command():
    twin = _twin_with_guidance("立刻放慢, 必须做满 5 组。")
    alert = movement_imperative_red_line(twin)
    assert alert is not None
    assert alert.severity == Severity.HIGH
    assert alert.category == "guidance"


def test_movement_rule_silent_on_observational_text():
    twin = _twin_with_guidance("今天的运动量约 30 分钟, 强度由恢复状态决定, 可作参考。")
    assert movement_imperative_red_line(twin) is None


# ─────────────────────── registry wiring ───────────────────────


def test_guidance_rules_are_registered_in_engine():
    from app.agents.safety_guardian.engine import registry

    names = {name for name, _ in registry.all_rules()}
    assert "diet_prescription_red_line" in names
    assert "movement_imperative_red_line" in names


# ─────────────────────── adversarial leak list (regression) ───────────────────────
#
# Every string below was a VERIFIED leak (validator returned it verbatim).
# They MUST now be flagged + stripped/softened so the gap cannot silently regress.

_EN_DIET_LEAKS = [
    "Eat 50g of nuts every day",
    "Don't eat rice",
    "Avoid carbs",
    "You must consume 200g protein daily",
    "Stop eating sugar",
    "Limit your intake to 500 calories",
]

_EN_MOVEMENT_LEAKS = [
    "Slow down immediately",
    "You must do 3 sets",
]

_ZH_SOFT_DIET_LEAKS = [
    "请减少米饭的摄入",
    "应当控制碳水摄入量",
    "建议你避免高糖食物",
    "把蛋白质提高到每天120克",
    "下一餐请勿摄入超过50克脂肪",
    # council #12: long noun-phrase gap between "把" and the verb (> old {0,12})
    # used to leak through the fixed-quantifier "把…{0,12}…克" pattern.
    "把你的身体状态允许的蛋白量逐步提升至120克",
    "把每天的碳水化合物摄入总量严格控制到200克以内",
]

_ZH_SOFT_MOVEMENT_LEAKS = [
    "你需要做满5组深蹲",
    "赶紧慢下来",
]


@pytest.mark.parametrize("text", _EN_DIET_LEAKS + _ZH_SOFT_DIET_LEAKS)
def test_validator_now_flags_previously_leaked_diet(text):
    r = sanitize_guidance(text)
    assert r.flagged is True, f"DIET leak slipped through validator: {text!r}"
    assert "[已移除非处方化建议]" in r.text


@pytest.mark.parametrize("text", _EN_MOVEMENT_LEAKS + _ZH_SOFT_MOVEMENT_LEAKS)
def test_validator_now_flags_previously_leaked_movement(text):
    r = sanitize_guidance(text)
    assert r.flagged is True, f"MOVEMENT leak slipped through validator: {text!r}"
    # softened, never a bare imperative
    assert "自行调整" in r.text


@pytest.mark.parametrize("text", _EN_DIET_LEAKS + _ZH_SOFT_DIET_LEAKS)
def test_diet_rule_fires_on_previously_leaked_diet(text):
    twin = _twin_with_guidance(text)
    alert = diet_prescription_red_line(twin)
    assert alert is not None, f"DIET red-line did not fire on: {text!r}"
    assert alert.severity == Severity.CRITICAL


@pytest.mark.parametrize("text", _EN_MOVEMENT_LEAKS + _ZH_SOFT_MOVEMENT_LEAKS)
def test_movement_rule_fires_on_previously_leaked_movement(text):
    twin = _twin_with_guidance(text)
    alert = movement_imperative_red_line(twin)
    assert alert is not None, f"MOVEMENT red-line did not fire on: {text!r}"
    assert alert.severity == Severity.HIGH


# ─────────────────────── false-positive guard (observational stays clean) ─────────
#
# Observational / post-hoc wording (both languages) MUST pass untouched —
# otherwise we'd strip the very text the product is allowed to emit.

_OBSERVATIONAL_CLEAN = [
    "这餐约450kcal",
    "今日蛋白还差35g",
    "相关非因果",
    "这餐约 450kcal, 蛋白约 32g, 今日蛋白还差 35g。相关非因果。",
    "about 450 kcal, ~35g protein remaining",
    "This meal is about 620 kcal with roughly 32g protein.",
    "今日还剩约 300 kcal 空间, 可作今日饮食参考。",
]


@pytest.mark.parametrize("text", _OBSERVATIONAL_CLEAN)
def test_validator_keeps_observational_clean(text):
    r = sanitize_guidance(text)
    assert r.flagged is False, f"observational text wrongly flagged: {text!r} -> {r.violations}"
    assert r.text == text


@pytest.mark.parametrize("text", _OBSERVATIONAL_CLEAN)
def test_rules_silent_on_observational(text):
    twin = _twin_with_guidance(text)
    assert diet_prescription_red_line(twin) is None, f"diet rule false-positive: {text!r}"
    assert movement_imperative_red_line(twin) is None, f"movement rule false-positive: {text!r}"


# ═════════════ third family: pseudo-prescriptive medication timing (P5) ═════════════
#
# ships-disabled behind ``settings.med_timing_softening`` (default False). Action =
# SOFTEN (not full redaction): the prescriptive dosing-timing span is rewritten to
# "遵医嘱/药师/说明书". Adversarial two-way coverage below (>=6 each direction).

_MED_TIMING_LEAKS = [
    # verified eval leaks (裁判点名的灰区措辞)
    "6小时内可补服,超过12小时跳过",
    "建议睡前使用鼻喷剂",
    # realistic same-family leaks
    "漏服后6小时内可以补服,超过12小时就跳过这次",
    "每8小时服用一次",
    "睡前用一次鼻喷剂",
    "第2周开始减量",
    "第4周停药",
    "建议餐前30分钟服用他汀",
    "记得每12小时吃一次布洛芬",
]

# Must NOT soften: public label facts, food-timing science, relayed doctor/pharmacist
# orders, KB citations, and negated warnings ("不要自行…"). These are science comms
# or transcription, NOT the system prescribing.
_MED_TIMING_CLEAN = [
    "PPI 一般建议餐前30分钟服用是公开说明书内容",  # label-fact framing
    "维生素D随餐吸收更好",  # food-timing absorption, no dosing schedule
    "医生开的医嘱是每天两次",  # relaying a doctor's order
    "不要自行决定每8小时加一次",  # negated warning
    "根据说明书,奥美拉唑通常在早餐前服用",  # label citation
    "临床指南提到他汀多在睡前服用",  # clinical-guideline citation
    "医嘱是睡前使用鼻喷剂,记得遵医嘱。",  # doctor-order relay w/ dosage form
    "这餐约450kcal, 今日蛋白还差35g",  # observational (other-family clean)
    "切勿睡前自行加用鼻喷剂",  # negated (切勿) imperative
    "处方上写的是餐后服用,以处方为准",  # prescription-relay framing
]


@pytest.mark.parametrize("text", _MED_TIMING_LEAKS)
def test_med_timing_softens_pseudo_prescription(med_timing_on, text):
    r = sanitize_guidance(text)
    assert r.flagged is True, f"med-timing leak slipped through: {text!r}"
    assert "遵医嘱" in r.text, f"not softened to a defer-to-clinician note: {r.text!r}"
    assert any(v.startswith("med_timing:") for v in r.violations)
    # softened, never left as a bare imperative dosing schedule
    assert text not in r.text


@pytest.mark.parametrize("text", _MED_TIMING_CLEAN)
def test_med_timing_clean_not_softened(med_timing_on, text):
    r = sanitize_guidance(text)
    med_hits = [v for v in r.violations if v.startswith("med_timing:")]
    assert med_hits == [], f"med-timing false-positive on {text!r}: {med_hits}"


# ─────────────────────── ships-disabled: default flag off = zero change ───────────


@pytest.mark.parametrize("text", _MED_TIMING_LEAKS)
def test_med_timing_disabled_by_default_leaves_text_untouched(text):
    # No fixture → settings.med_timing_softening is its default (False).
    assert settings.med_timing_softening is False
    r = sanitize_guidance(text)
    # None of these strings trip the DIET/MOVEMENT families, so with the third
    # family off they must pass through byte-for-byte.
    assert r.text == text, f"third family leaked while disabled: {text!r} -> {r.text!r}"
    assert not any(v.startswith("med_timing:") for v in r.violations)


# ─────────────────────── clause isolation (mixed strings) ───────────────────────


def test_med_timing_softens_only_the_prescriptive_clause(med_timing_on):
    # clause 1 is a system prescription (soften); clause 2 is a negated warning (keep).
    text = "建议睡前使用鼻喷剂。不要自行每8小时加一次。"
    r = sanitize_guidance(text)
    assert r.flagged is True
    assert "遵医嘱" in r.text
    assert "不要自行每8小时加一次" in r.text  # negated clause left intact


def test_med_timing_label_fact_clause_kept_prescriptive_clause_softened(med_timing_on):
    text = "说明书写每8小时一次。建议睡前使用鼻喷剂。"
    r = sanitize_guidance(text)
    assert r.flagged is True
    assert "说明书写每8小时一次" in r.text  # label-fact clause untouched
    assert "遵医嘱" in r.text  # prescriptive clause softened


# ─────────────────────── first-two families unaffected by the flag ───────────────


def test_med_timing_flag_does_not_change_diet_or_movement_families(med_timing_on):
    # Diet + movement families must behave identically regardless of the flag.
    r_diet = sanitize_guidance("别吃米饭, 每天吃 50 克坚果。")
    assert r_diet.flagged is True
    assert "[已移除非处方化建议]" in r_diet.text
    r_move = sanitize_guidance("立刻放慢, 必须做满 3 组。")
    assert r_move.flagged is True
    assert "自行调整" in r_move.text


def test_med_timing_empty_and_observational_stay_clean(med_timing_on):
    assert sanitize_guidance("").flagged is False
    r = sanitize_guidance("这餐约 450kcal, 今日蛋白还差 35g。相关非因果。")
    assert r.flagged is False
