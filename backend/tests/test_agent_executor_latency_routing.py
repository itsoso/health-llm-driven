from app.services.agent_output_quality import (
    clarification_reply,
    needs_input_clarification,
)


def test_one_character_input_uses_deterministic_clarification_lane():
    assert needs_input_clarification("睡") is True
    assert needs_input_clarification(" ? ") is True
    assert needs_input_clarification("睡眠") is False
    assert "补充" in clarification_reply()


def test_empty_input_is_owned_by_request_validation_not_clarification_lane():
    assert needs_input_clarification("") is False
    assert needs_input_clarification("   ") is False
