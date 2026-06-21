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
from app.services.guidance_validator import sanitize_guidance
from app.twin.schema import HealthTwin, TwinMeta


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
