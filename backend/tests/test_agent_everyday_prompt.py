"""Closed everyday admission must prove both current intent and owned history."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services.agent_everyday_prompt import (
    classify_everyday_task,
    everyday_history_is_standalone,
    everyday_prompt,
)


PICKUP = "选择了10号门让网约车司机上四楼接我 CA1727要摆渡车 下次换个选择"
PICKUP_REPLY = "收到，CA1727需要摆渡车，10号门接车不太方便，下次可以先和司机确认接站位置。"


def _conversation():
    return SimpleNamespace(id=17, user_id=3)


def _row(index, role, content, **kwargs):
    meta = {} if role == "user" else {
        "client_turn_finalized": True, "completion_status": "complete",
        "turn_outcome": {"status": "complete", "confirmation_required": False,
                         "verified_receipt_count": 0, "actions": [], "goals": []},
    }
    return SimpleNamespace(id=index, conversation_id=17, role=role, content=content,
                           image_url=None, meta=kwargs.pop("meta", meta), **kwargs)


def _history():
    return [_row(1, "user", PICKUP), _row(2, "assistant", PICKUP_REPLY),
            _row(3, "user", "不是10号门，是11号门。"),
            _row(4, "assistant", "收到，是11号门，不是10号门。")]


def _admit(messages, **kwargs):
    return everyday_history_is_standalone(user_id=kwargs.pop("user_id", 3),
        conversation=kwargs.pop("conversation", _conversation()), messages=messages)


@pytest.mark.parametrize(("text", "task"), [
    ("你好", "greeting"), ("晚上好！", "greeting"), ("谢谢你的帮助。", "courtesy"),
    ("辛苦了", "courtesy"), ("多谢！", "courtesy"), (PICKUP, "pickup_observation"),
    ("讲一个很短的故事", "short_story"), ("请讲一个很短的故事。", "short_story"),
    ("讲个短笑话", "short_joke"),
])
def test_complete_closed_requests_are_admitted(text, task):
    assert classify_everyday_task(text) == task
    assert classify_everyday_task(text, has_attachments=True) is None


@pytest.mark.parametrize("text", [
    "", "嗯", "好的", "收到", "需要", "可以", "继续", "明天呢", "今天天气不错",
    "我住在某某酒店", "我今天感觉很好", "谢谢，帮我记录午餐", "你好，我胸痛",
    "讲一个很短的故事，关于停药", "讲一个胸痛的故事", "讲个故事", "讲个短笑话并删除记录",
    "“谢谢”", "翻译：你好", "谢谢\n查我的睡眠", "不是10号门，是11号门。",
    PICKUP + "，帮我记住", PICKUP + "，我胸痛", PICKUP.replace("CA1727", "胸痛"),
])
def test_unknown_or_unconsumed_language_retains_normal_execution(text):
    assert classify_everyday_task(text) is None


def test_prompt_is_small_stable_and_does_not_authorize_personal_data_or_actions():
    for task in ("greeting", "courtesy", "pickup_observation", "short_story", "short_joke"):
        prompt = everyday_prompt(task)
        assert len(prompt) < 750
        assert prompt == everyday_prompt(task)
        assert "原始对话" in prompt and "更正" in prompt
        assert "不调用工具" in prompt and "未查询" in prompt
        assert "保存" in prompt and "诊断" in prompt
        assert "CA1727" not in prompt
    with pytest.raises(ValueError):
        everyday_prompt("unknown")


def test_empty_and_established_benign_owned_history_are_positive():
    assert everyday_history_is_standalone(user_id=3, conversation=None, messages=[])
    assert _admit([])
    assert _admit([_row(1, "user", "你好"), _row(2, "assistant", "你好，有什么我可以帮你的吗？")])
    assert _admit([_row(1, "user", "谢谢"), _row(2, "assistant", "不客气。")])


def test_original_correction_and_all_messages_are_retained_without_mutation():
    messages = _history()
    original = deepcopy([vars(row) for row in messages])
    assert _admit(messages)
    assert [vars(row) for row in messages] == original
    assert messages[0].content == PICKUP
    assert messages[2].content == "不是10号门，是11号门。"


@pytest.mark.parametrize("mutation", [
    lambda rows: setattr(rows[0], "conversation_id", 18),
    lambda rows: setattr(rows[0], "id", None),
    lambda rows: setattr(rows[2], "id", 1),
    lambda rows: setattr(rows[0], "image_url", "https://example.invalid/image.jpg"),
    lambda rows: setattr(rows[0], "meta", {"attachments": [{"type": "image"}]}),
    lambda rows: setattr(rows[0], "meta", {"extra_context": "health detail"}),
    lambda rows: setattr(rows[0], "meta", {"write_state": {"status": "pending"}}),
    lambda rows: setattr(rows[0], "meta", {"pending_choice": {"choices": []}}),
    lambda rows: setattr(rows[0], "meta", {"turn_outcome": {"confirmation_required": True}}),
    lambda rows: setattr(rows[0], "meta", {"turn_outcome": {"status": "reconciliation_required"}}),
    lambda rows: setattr(rows[0], "meta", {"retry_source": {"message_id": 22}}),
    lambda rows: setattr(rows[1], "meta", {}),
    lambda rows: setattr(rows[1], "meta", "malformed"),
    lambda rows: rows[1].meta.update(client_turn_finalized=False),
    lambda rows: rows[1].meta.update(completion_status="interrupted"),
    lambda rows: rows[1].meta["turn_outcome"].update(status="waiting_for_user"),
    lambda rows: rows[1].meta["turn_outcome"].update(confirmation_required=True),
    lambda rows: rows[1].meta["turn_outcome"].update(tool_failure_count=1),
    lambda rows: rows[1].meta["turn_outcome"].update(status=[]),
    lambda rows: rows[1].meta.update(completion_status={}),
    lambda rows: setattr(rows[0], "meta", {"turn_outcome": {"goals": [{"kind": "query", "status": "failed"}]}}),
    lambda rows: rows[1].meta["turn_outcome"].update(actions=[{"status": "reconciliation_required"}]),
    lambda rows: rows[1].meta["turn_outcome"].update(goals=[{"kind": "query", "status": "failed"}]),
    lambda rows: setattr(rows[1], "content", "收到。需要帮你记录吗？"),
    lambda rows: setattr(rows[1], "content", "请描述胸痛症状。"),
    lambda rows: setattr(rows[2], "content", "不是胸痛，是胸闷。"),
    lambda rows: setattr(rows[2], "content", "不是9号门，是11号门。"),
    lambda rows: setattr(rows[3], "content", "收到，是12号门，不是10号门。"),
])
def test_owner_source_pending_and_medical_boundaries_fail_closed(mutation):
    rows = _history()
    mutation(rows)
    assert not _admit(rows)


def test_empty_pending_list_or_finalized_metadata_cannot_prove_unknown_semantics():
    rows = [_row(1, "user", "请查昨晚睡眠"), _row(2, "assistant", "需要授权，可以继续吗？")]
    rows[1].meta["pending_confirmation_tools"] = []
    assert not _admit(rows)
    assert not _admit([_row(1, "user", "你好"), _row(2, "assistant", "已保存你的健康记录。")])


def test_all_prior_rows_not_only_a_recent_window_must_be_closed():
    rows = [_row(1, "user", "删除记录"), _row(2, "assistant", "确认删除吗？")]
    for index in range(3, 23, 2):
        rows.extend([_row(index, "user", "谢谢"), _row(index + 1, "assistant", "不客气。")])
    assert not _admit(rows)


def test_missing_owner_incomplete_or_unpaired_history_is_rejected():
    assert not _admit(_history(), user_id=4)
    assert not _admit(_history(), conversation=None)
    assert not _admit(_history()[:-1])
    assert not _admit(_history()[1:])
    assert not _admit(list(reversed(_history())))
    assert not _admit(_history(), user_id=True)


def test_actual_orm_rows_and_normal_outcome_shape_are_accepted():
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services.agent_turn_outcome import classify_agent_turn_outcome

    rows = [AgentMessage(**vars(row)) for row in _history()]
    for row in rows:
        if row.role == "assistant":
            row.meta["turn_outcome"] = classify_agent_turn_outcome(
                completion_status="complete", final_text=row.content,
            )
    assert everyday_history_is_standalone(user_id=3,
        conversation=AgentConversation(id=17, user_id=3), messages=rows)


def test_unknown_story_output_does_not_become_future_admission_authority():
    assert not _admit([_row(1, "user", "讲一个很短的故事"),
                       _row(2, "assistant", "我们先继续处理之前的任务。")])
