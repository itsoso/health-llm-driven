"""弱模型(如 deepseek-v4-pro)记录后把工具结果/参数裸 JSON 当最终回复回显,
不能裸露给用户——应被工具结果合成的"已记录…"替换。

用户截图回归:Mac 上记早餐/俯卧撑,助手正文是
{"record_date":"2026-06-16","meal_type":"breakfast",...,"a   (截断)
{"id":231,"user_id":3,...,"reps":20                          (后端返回的记录)
"""
from app.services.agent_executor import (
    _looks_like_bare_tool_json,
    _fast_record_reply_from_tool_results,
)


# ── 裸 JSON 检测 ────────────────────────────────────────────────────────────
def test_detects_created_record_json_even_truncated():
    assert _looks_like_bare_tool_json('{"id":231,"user_id":3,"reps":20')  # 截断无尾 }
    assert _looks_like_bare_tool_json(
        '{"record_date":"2026-06-16","meal_type":"breakfast","food_items":"小笼包 3个","a'
    )


def test_detects_complete_json_object_and_fenced():
    assert _looks_like_bare_tool_json('{"a": 1, "b": 2}')
    assert _looks_like_bare_tool_json('```json\n{"id": 5, "x": 1}\n```')


def test_prose_is_not_bare_json():
    assert not _looks_like_bare_tool_json("已记录 20 个俯卧撑。")
    assert not _looks_like_bare_tool_json("你今天血压偏高,建议休息。")
    assert not _looks_like_bare_tool_json("")
    # 正文里带个 JSON 片段但以人话开头 → 不算整条裸 JSON
    assert not _looks_like_bare_tool_json("好的,数据是 {\"a\":1}")


# ── 合成确认替换裸 JSON ─────────────────────────────────────────────────────
def test_synthesizes_confirmation_from_created_record_tool_result():
    # 模拟工具结果消息(后端返回的运动记录),应合成人话而非回显 JSON
    messages = [
        {"role": "user", "content": "记录刚才做了20个俯卧撑"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "tool_call_id": "1",
         "content": '{"id":231,"user_id":3,"exercise_type":"俯卧撑","reps":20}'},
    ]
    reply = _fast_record_reply_from_tool_results(messages)
    assert reply.strip()
    assert not _looks_like_bare_tool_json(reply)  # 合成出来的是人话,不再是裸 JSON


def test_no_tool_results_yields_empty_so_caller_keeps_original():
    # 没有工具结果时合成为空 → 调用方 gate 住不替换(避免误伤用户主动要的 JSON)
    messages = [{"role": "user", "content": "给我一段 JSON"}]
    assert _fast_record_reply_from_tool_results(messages).strip() == ""
