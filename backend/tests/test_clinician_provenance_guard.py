from dataclasses import FrozenInstanceError
import importlib
import inspect
import json
from pathlib import Path

import pytest


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "clinician_provenance_guard_safety_cases.json"
)
PROVIDERS = {
    "医生",
    "医师",
    "大夫",
    "主治医生",
    "康复师",
    "物理治疗师",
}


def _module():
    try:
        return importlib.import_module(
            "app.services.clinician_provenance_guard"
        )
    except ModuleNotFoundError:
        pytest.fail("clinician_provenance_guard is not implemented yet")


def _slice(raw, start, end):
    if start is None or end is None:
        assert start is end is None
        return None
    return raw[start:end]


def _cases():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _cases(), ids=lambda row: row["id"])
def test_fixed_safety_corpus(case):
    guard = _module()

    decision = guard.classify_clinician_turn(case["text"])

    assert decision.raw == case["text"]
    assert decision.kind == case["kind"]
    assert decision.reason_code == case["reason_code"]
    assert decision.authorizes_feedback_write is (
        case["kind"] == "explicit_doctor_feedback_write"
    )
    assert _slice(
        decision.raw,
        decision.provider_start,
        decision.provider_end,
    ) == case.get("provider")
    assert _slice(
        decision.raw,
        decision.content_start,
        decision.content_end,
    ) == case.get("content")
    assert _slice(
        decision.raw,
        decision.command_start,
        decision.command_end,
    ) == case.get("command")


def test_decision_is_frozen_and_only_explicit_kind_authorizes():
    guard = _module()
    explicit = guard.classify_clinician_turn(
        "请记录医生诊断：臀肌无力"
    )
    context = guard.classify_clinician_turn("医生说是臀肌无力")

    with pytest.raises(FrozenInstanceError):
        explicit.kind = "none"
    assert explicit.authorizes_feedback_write is True
    assert context.authorizes_feedback_write is False


def test_non_writes_never_expose_an_authorizing_command_span():
    guard = _module()

    for case in _cases():
        decision = guard.classify_clinician_turn(case["text"])
        if case["kind"] != "explicit_doctor_feedback_write":
            assert decision.command_start is None
            assert decision.command_end is None


def test_provider_vocabulary_is_covered_by_handwritten_corpus():
    covered = {case.get("provider") for case in _cases()}

    assert PROVIDERS <= covered


def test_guard_is_deterministic_and_does_not_use_regex_or_llm():
    guard = _module()
    source = inspect.getsource(guard)
    text = "医生说是臀肌无力。请记录医生诊断：臀肌无力"

    assert guard.classify_clinician_turn(text) == guard.classify_clinician_turn(
        text
    )
    assert "import re" not in source
    assert "re.compile" not in source
    assert "llm" not in source.lower()


def test_guard_does_not_grow_a_general_action_taxonomy():
    guard = _module()
    source = inspect.getsource(guard)

    for forbidden in (
        "ActionKind",
        "delete_actions",
        "update_actions",
        "sync_actions",
        "plan_actions",
        "reminder_actions",
        "media_actions",
    ):
        assert forbidden not in source
