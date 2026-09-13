"""Drafting an answer and repairing a conversation never grant persistence."""

import pytest

from app.services.utterance_intent_classifier import classify_agent_utterance


@pytest.mark.parametrize(
    "message",
    [
        "制定康复计划",
        "起草今天的计划",
        "给我今天计划",
        "生成本周健康计划",
        "帮我拟个今天的计划",
        "帮我安排一下今天的计划",
        "给我一个今日方案",
        "先看看昨天的睡眠，再起草今天的计划",
        "给我拟个饮食计划",
        "起草今天计划，不要保存",
        "别保存，先给我看看今天的计划草稿",
        "修改今天的计划草稿",
        "把今天计划草稿调整一下",
    ],
)
def test_plan_drafting_is_answer_generation_without_write_authority(message):
    intent = classify_agent_utterance(message)
    assert (intent.primary, intent.domain, intent.operation) == (
        "advice",
        "plan",
        "analyze",
    )
    assert intent.reason == "plan_draft_request"
    assert intent.is_write is False


@pytest.mark.parametrize(
    "message,operation",
    [
        ("保存今天的计划", "create"),
        ("把这个方案加入今天计划", "create"),
        ("起草今天计划并保存", "create"),
        ("保存今天的饮食计划", "create"),
        ("执行今天的计划", "update"),
        ("完成今天的计划项", "update"),
        ("更新今天的计划", "update"),
        ("给我今天计划并加入首页", "create"),
        ("保存这个计划草稿", "create"),
        ("保存这个健康计划到首页", "create"),
        ("保存健康计划到首页", "create"),
        ("请保存这个计划草稿到首页", "create"),
        ("把这个健康计划保存到首页", "create"),
    ],
)
def test_explicit_plan_actions_keep_the_write_capability_requirement(
    message, operation
):
    intent = classify_agent_utterance(message)
    assert intent.domain == "plan" and intent.operation == operation
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    [
        "不要保存今天计划",
        "先别执行今天的计划",
        "不要完成今天的计划项",
        "保存今天计划，算了取消",
        "执行今天计划，算了不要执行",
        "朋友说：保存今天计划",
        "解释这句话：执行今天计划",
        "‘加入今天计划’是什么意思",
        "如果明天需要，再保存今天计划",
        "你已经保存今天计划了吗？",
        "能执行今天的计划吗？",
        "给我今天计划，不要加入首页",
        "朋友让我起草今天计划并保存",
        "起草今天计划并保存。仅举例",
        "把这个方案加入今天计划，先别",
        "别把这个方案加入今天计划",
        "保存今天计划，先别",
        "保存今天饮食计划，先别",
        "不要保存这个健康计划到首页",
        "保存这个健康计划到首页，先别",
        "朋友说：保存这个健康计划到首页",
        "‘保存这个健康计划到首页’是什么意思",
        "如果明天需要，再保存这个健康计划到首页",
        "保存这个健康计划到首页了吗？",
        "医生说：保存这个健康计划到首页",
        "帮我起草一个要保存到首页的计划",
    ],
)
def test_plan_mentions_negation_quotes_and_cancellation_do_not_authorize_writes(
    message,
):
    assert classify_agent_utterance(message).is_write is False


@pytest.mark.parametrize(
    "message",
    [
        "怎么变弱智了？",
        "你怎么变笨了",
        "回答越来越差了",
        "这么差，你为什么这么不能理解我呢",
        "你没听懂我的意思",
        "不是这个意思",
        "你又答非所问了",
        "你理解错了，重新理解一下我的意思",
        "这回答太差了",
    ],
)
def test_conversation_feedback_does_not_become_a_health_query(message):
    intent = classify_agent_utterance(message)
    assert (intent.primary, intent.domain, intent.operation) == (
        "chat",
        "unknown",
        "none",
    )
    assert intent.reason == "conversation_feedback"
    assert intent.is_write is False


@pytest.mark.parametrize(
    "message,domain",
    [
        ("你没听懂，记录我喝了500ml水", "water"),
        ("记录我喝了500ml水，然后起草今天计划", "water"),
        ("起草今天计划，再记录我喝了500ml水", "water"),
        ("记录午餐吃了米饭", "diet"),
        ("吃了两粒红景天", "supplement"),
        ("保存今天饮水量500ml并起草计划", "water"),
        ("不要保存今天计划，记录我喝了500ml水", "water"),
    ],
)
def test_real_health_write_is_not_hidden_by_feedback_or_a_draft_task(message, domain):
    intent = classify_agent_utterance(message)
    assert intent.is_write is True and intent.domain == domain


@pytest.mark.parametrize(
    "message", ["你没听懂，查一下昨天的睡眠", "不是这个意思，我头疼怎么办"]
)
def test_feedback_with_a_health_task_keeps_the_actual_task(message):
    intent = classify_agent_utterance(message)
    assert intent.primary in {"read", "advice"}
    assert intent.reason != "conversation_feedback"
    assert intent.is_write is False
