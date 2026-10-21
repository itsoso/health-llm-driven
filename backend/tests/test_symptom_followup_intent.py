"""Symptom discussion must not acquire record authority from symptom words."""
import pytest

from app.services.utterance_intent_classifier import classify_agent_utterance


@pytest.mark.parametrize("message", [
    "傍晚仍然隐约肚子痛",
    "肚脐附近还有些疼",
    "疼痛现在集中在下腹部",
    "还是有腰疼的症状。",
    "今天腰痛 6 分",
    "之前疼痛明显，现在稍微减轻",
])
def test_symptom_narration_continues_analysis_without_write_authority(message):
    intent = classify_agent_utterance(message)

    assert (intent.primary, intent.domain, intent.operation) == (
        "advice", "symptom", "analyze",
    )
    assert not intent.is_write
    assert intent.requires_reliable_tool_model


@pytest.mark.parametrize("message", [
    "请记录我今天头疼",
    "帮我保存今天的腹痛症状",
    "新增症状记录：我今天腹痛",
    "记录我头痛，然后分析原因",
])
def test_explicit_symptom_record_commands_keep_write_authority(message):
    intent = classify_agent_utterance(message)

    assert intent.domain == "symptom"
    assert intent.operation == "create"
    assert intent.is_write


def test_explicit_symptom_update_remains_an_update_request():
    intent = classify_agent_utterance("更新我的症状记录，疼痛程度改成3分")

    assert intent.domain == "symptom"
    assert intent.operation == "update"
    assert intent.is_write


@pytest.mark.parametrize("message", [
    "请记录，我的头痛已经消失了。",
    "记录下来，稍微有点腹泻。",
    "现在还是隐隐约约腹痛",
])
def test_existing_exact_status_observation_contract_is_preserved(message):
    intent = classify_agent_utterance(message)

    assert intent.reason == "explicit_self_symptom_status_observation"
    assert intent.is_write


@pytest.mark.parametrize("message", [
    "我还有些头疼，不要记录",
    "朋友说他还有些头疼",
    "如果我还是腹痛",
    "解释这句话：请记录我今天头疼",
])
def test_unowned_or_negated_symptom_narration_never_grants_write(message):
    assert not classify_agent_utterance(message).is_write


def test_explicit_symptom_read_is_not_replaced_by_followup_analysis():
    intent = classify_agent_utterance("查看我的症状记录")

    assert intent.primary == "read"
    assert not intent.is_write
