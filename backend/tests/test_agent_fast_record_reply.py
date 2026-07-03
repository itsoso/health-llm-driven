"""Fast-record reply builder must never dump raw created-record JSON at the user.

Regression for the chat bug where "记录打喷嚏一个" returned the raw symptom
record JSON ({"id":19,"body_part":"respiratory","description":"打喷嚏",...})
instead of a human confirmation.
"""
import json

from app.services.agent_executor import (
    _fast_record_reply_from_tool_results,
    _friendly_record_confirmation,
    _post_record_quality_response,
)


def _tool_msg(payload) -> dict:
    return {"role": "tool", "content": json.dumps(payload, ensure_ascii=False)}


def test_symptom_record_json_becomes_friendly_line_not_raw_json():
    record = {
        "id": 19,
        "user_id": 3,
        "occurred_at": "2026-06-02T11:31:13.455118+08:00",
        "body_part": "respiratory",
        "description": "打喷嚏",
        "severity": 1,
        "triggers": [],
        "duration_minutes": None,
    }
    reply = _fast_record_reply_from_tool_results([_tool_msg(record)])
    assert reply == "已记录症状：打喷嚏（记录号 19,说「撤销」可删除）"  # 回显带记录号:撤销回合快路由只剩这行上下文
    assert "{" not in reply and "body_part" not in reply


def test_explicit_message_field_is_preferred():
    reply = _fast_record_reply_from_tool_results([_tool_msg({"message": "已记录饮水 250ml"})])
    assert reply == "已记录饮水 250ml"


def test_friendly_confirmation_covers_common_record_shapes():
    assert _friendly_record_confirmation({"systolic": 120, "diastolic": 80}) == "已记录血压 120/80 mmHg"
    assert _friendly_record_confirmation({"food_items": "牛肉面"}) == "已记录饮食：牛肉面"
    assert _friendly_record_confirmation({"weight": 71.2}) == "已记录体重 71.2 kg"
    assert _friendly_record_confirmation({"exercise_type": "俯卧撑", "reps": 20}) == "已记录运动：俯卧撑 20 次"
    assert _friendly_record_confirmation({"glucose_mg_dl": 99.1}) == "已记录血糖 99.1 mg/dL"
    assert _friendly_record_confirmation({"mood_score": 8}) == "已记录心情 8/10"
    assert _friendly_record_confirmation({
        "title": "臀中肌训练",
        "remind_at": "2026-06-30T10:30:00+08:00",
        "recurrence": "daily",
    }) == "已设置每日提醒：臀中肌训练"
    # Unknown shape → safe generic, never raw JSON.
    assert _friendly_record_confirmation({"id": 1, "foo": "bar"}) == "✅ 已记录"


def test_array_result_reports_lookup_not_creation():
    # 数组只来自 health_manage list(无创建路径返回数组)。对抗评审实测:
    # 撤销回合的 list 结果曾被答成"✅已记录 2 条"= 假写入宣称。
    reply = _fast_record_reply_from_tool_results([_tool_msg([{"id": 1}, {"id": 2}])])
    assert "已记录" not in reply
    assert reply == "查到 2 条记录（记录号: 1, 2）"


def test_plain_text_tool_result_passes_through():
    msg = {"role": "tool", "content": "未找到名为 '维生素X' 的活跃补剂"}
    reply = _fast_record_reply_from_tool_results([msg])
    assert reply == "未找到名为 '维生素X' 的活跃补剂"


def test_error_tool_result_passes_through():
    msg = {"role": "tool", "content": "Error: water amount 必须是整数毫升"}
    reply = _fast_record_reply_from_tool_results([msg])
    assert reply.startswith("Error")


def test_diet_reply_is_two_sentences_headline_plus_note_not_a_wall():
    # founder 截图投诉:饮食回复是多段墙(食材枚举 + 宏量标签行 + 逐条宏量 + 建议)。
    # 移动端已用结构化饮食卡渲染这些数字 → 文本压到 ≤2 句(头条确认 + 一句备注),
    # 无卡客户端(Siri/watch)仍能自立。此处有胃溃疡背景 → 备注取个人提醒(高价值)。
    response = _post_record_quality_response(
        "diet",
        {
            "meal_type": "lunch",
            "food_items": "煎牛肉能量碗, 水煮蛋, 姜黄鲜柠维C茶",
            "calories": 770,
            "protein": 30,
            "carbs": 70,
            "fat": 17,
        },
        personal_context="[用户健康档案]\n慢性病: 胃溃疡(Hp 阴性), 高血压\n健康目标: 每日饮水2000ml",
    )

    assert response is not None
    reply = response["reply"]
    # 句 1:确认 + 头条数字。
    assert reply.startswith("已记录午餐：770 kcal，蛋白 30g。")
    # 句 2:一句人话备注 —— 胃溃疡背景优先给个人提醒(过敏/慢病更值得无卡端听见)。
    assert "胃溃疡" in reply and ("酸" in reply or "冷" in reply)
    # 墙的残骸不得复述进文本:标签行/逐条宏量/进度句/"下一步:"前缀/emoji。
    assert "碳水" not in reply and "脂肪" not in reply and "纤维" not in reply
    assert "今日蛋白" not in reply and "下一步" not in reply and "个人提醒" not in reply
    assert "✅" not in reply
    assert "{" not in reply
    assert reply.count("。") <= 2
    assert len(reply) <= 120

    # 无个人提醒时,备注回退到确定性的下一步建议(仍是当前代码已产出的字段)。
    plain = _post_record_quality_response(
        "diet",
        {"meal_type": "dinner", "food_items": "鸡胸肉沙拉", "calories": 420, "protein": 38},
        personal_context="",
    )
    assert plain is not None
    plain_reply = plain["reply"]
    assert plain_reply.startswith("已记录晚餐：420 kcal，蛋白 38g。")
    assert len(plain_reply) > len("已记录晚餐：420 kcal，蛋白 38g。")  # 有第二句备注
    assert plain_reply.count("。") <= 2

    # 缺数字时省略,绝不编造:无热量无蛋白 → 头条退化成 "已记录早餐。"
    no_numbers = _post_record_quality_response(
        "diet",
        {"meal_type": "breakfast", "food_items": "白粥"},
        personal_context="",
    )
    assert no_numbers is not None
    assert no_numbers["reply"].startswith("已记录早餐。")
    assert "kcal" not in no_numbers["reply"] and "蛋白 " not in no_numbers["reply"]

    # 只有热量没蛋白 → 头条只带热量。
    kcal_only = _post_record_quality_response(
        "diet",
        {"meal_type": "lunch", "food_items": "牛肉面", "calories": 560},
        personal_context="",
    )
    assert kcal_only is not None
    assert kcal_only["reply"].startswith("已记录午餐：560 kcal。")
    assert "蛋白 " not in kcal_only["reply"].split("。")[0]

    assert response["cards"][0]["type"] == "record_quality"
    assert response["cards"][0]["data"]["domain"] == "diet"
    # actions[0] 是"看下一餐建议"就地展开(chat 内),不是路由跳转;
    # 无 result → 无 record_id → "调整记录"兜底为跳饮食页(open-diet)。
    actions = response["cards"][0]["actions"]
    assert actions[0]["id"] == "show-next-meal"
    assert actions[0]["action"] == "ui.inline.expand"
    assert actions[0]["payload"]["target"] == "next_meal"
    # mobile registry.readInlineExpandPatch 硬性契约: 带 endpoint 直接拒;
    # payload.patch 必须是对象且 sanitize 后非空(expanded_sections ∈
    # {next_meal, adjust_record} / next_meal_detail 为对象), 否则客户端丢弃该按钮。
    assert "endpoint" not in actions[0]
    patch = actions[0]["payload"]["patch"]
    assert isinstance(patch, dict)
    assert patch["expanded_sections"] == ["next_meal"]
    next_meal_detail = patch["next_meal_detail"]
    assert isinstance(next_meal_detail, dict)
    assert next_meal_detail["title"] and next_meal_detail["summary"]
    assert isinstance(next_meal_detail["options"], list) and next_meal_detail["options"]
    assert actions[1]["id"] == "open-diet"
    assert actions[1]["action"] == "route.open"
    assert actions[1]["payload"]["route"] == "/diet"


def test_exercise_record_quality_response_is_actionable_without_medical_claims():
    response = _post_record_quality_response(
        "exercise",
        {
            "exercise_type": "俯卧撑",
            "reps": 30,
            "sets": 3,
            "duration": 8,
        },
        personal_context="[用户健康档案]\n慢性病: 高血压\n",
    )

    assert response is not None
    reply = response["reply"]
    assert "已记录运动" in reply
    assert "俯卧撑" in reply
    assert "下一步" in reply
    assert "诊断" not in reply
    assert len(reply) <= 200
