from datetime import datetime, timedelta, timezone
from inspect import getsource

import app.services.utterance_intent_classifier as utterance_intent_classifier
from app.services.utterance_intent_classifier import classify_agent_utterance

BJ = timezone(timedelta(hours=8))


def test_read_only_diet_record_noun_is_not_a_write_intent():
    intent = classify_agent_utterance("今天我的饮食的记录，帮我列个表格出来。")

    assert intent.primary == "read"
    assert intent.domain == "diet"
    assert intent.operation == "list"
    assert intent.scope == {"date": datetime.now(BJ).date().isoformat()}
    assert intent.is_write is False


def test_contrastive_correction_stays_read_only():
    intent = classify_agent_utterance("不是记录，是列出我今天吃的所有东西。")

    assert intent.primary == "read"
    assert intent.domain == "diet"
    assert intent.operation == "list"
    assert intent.is_write is False


def test_real_record_command_is_write_intent():
    intent = classify_agent_utterance("记录午餐吃了牛肉面")

    assert intent.primary == "write"
    assert intent.domain == "diet"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_clear_symptom_statement_is_write_intent():
    intent = classify_agent_utterance("还是有腰疼的症状。")

    assert intent.primary == "write"
    assert intent.domain == "symptom"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_symptom_question_stays_advice():
    intent = classify_agent_utterance("腰疼怎么办？")

    assert intent.primary == "advice"
    assert intent.is_write is False


def test_compound_record_and_analysis_keeps_write_capability():
    intent = classify_agent_utterance(
        "记录晚餐牛肉面，帮我分析今天的热量和蛋白质"
    )

    assert intent.primary == "write"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_analysis_using_record_as_evidence_does_not_become_a_write():
    intent = classify_agent_utterance(
        "从我的基因、生活习惯、睡眠、心率、HRV 记录出发，推断一下我胃溃疡的根因。"
    )

    assert intent.primary == "advice"
    assert intent.operation == "analyze"
    assert intent.is_write is False


def test_medication_side_effect_question_does_not_become_a_write():
    intent = classify_agent_utterance("吃了布洛芬后胃不舒服怎么办？")

    assert intent.primary == "advice"
    assert intent.is_write is False


def test_sleep_observation_without_a_request_is_not_misread_as_a_query():
    intent = classify_agent_utterance("我昨晚睡了十个小时，睡眠很好")

    assert intent.primary == "unknown"
    assert intent.operation == "none"
    assert intent.is_write is False


def test_negated_record_command_is_not_write_intent():
    intent = classify_agent_utterance("这个不用记录")

    assert intent.is_write is False
    assert intent.primary != "write"


def test_mutation_question_is_read_not_a_mutation_command():
    intent = classify_agent_utterance("我删除早餐了吗?")

    assert intent.primary == "read"
    assert intent.operation == "ask"
    assert intent.requires_reliable_tool_model is False


def test_destructive_command_requires_reliable_tool_model():
    intent = classify_agent_utterance("删除早餐 1")

    assert intent.primary == "mutate"
    assert intent.operation == "delete"
    assert intent.requires_reliable_tool_model is True


def test_analysis_adjustment_is_advice_not_mutation_command():
    intent = classify_agent_utterance("综合分析我最近的睡眠趋势，我该怎么调整")

    assert intent.primary == "advice"
    assert intent.operation == "analyze"
    assert intent.requires_reliable_tool_model is False


def test_destructive_command_after_analysis_preface_stays_mutation():
    intent = classify_agent_utterance("分析后帮我删除重复早餐")

    assert intent.primary == "mutate"
    assert intent.operation == "delete"
    assert intent.requires_reliable_tool_model is True


def test_plan_generation_is_a_write_intent():
    intent = classify_agent_utterance("生成本周健康计划")

    assert intent.primary == "write"
    assert intent.domain == "plan"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_plan_item_completion_is_a_mutation_intent():
    intent = classify_agent_utterance("完成今天的计划项")

    assert intent.primary == "mutate"
    assert intent.domain == "plan"
    assert intent.operation == "update"
    assert intent.is_write is True


def test_intervention_status_question_is_read_intent():
    intent = classify_agent_utterance("帮我看看干预周期")

    assert intent.primary == "read"
    assert intent.domain == "plan"
    assert intent.operation == "list"
    assert intent.is_write is False


def test_classifier_surface_does_not_use_regex():
    source = getsource(utterance_intent_classifier)

    assert "import re" not in source
    assert "re." not in source
    assert "re.compile" not in source
